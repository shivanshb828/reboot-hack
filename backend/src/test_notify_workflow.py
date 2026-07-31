"""
notify_oncall workflow test — proves:

1. After admit(), notify_status eventually becomes "sent".
2. mock_send_page is called exactly once even across a simulated restart.

The restart is simulated with rbt.down() + rbt.up() while the workflow is
in flight.  Reboot persists workflow task state to RocksDB, so up() picks
up where the workflow left off; at_least_once_per_workflow returns the
stored result without re-invoking mock_send_page.

Run:
    PYTHONPATH=api:backend/api:backend/src python backend/src/test_notify_workflow.py
"""

import asyncio
import logging
import mock_notifier
from reboot.aio.applications import Application
from reboot.aio.tests import Reboot
from triagedesk.v1.patient_case_rbt import PatientCase
from triagedesk.v1.bed_registry_rbt import BedRegistry
from patient_case_servicer import PatientCaseServicer
from bed_registry_servicer import BedRegistryServicer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
)

PATIENT_ID = "patient-demo-01"
BED_ID = "bed-001"


async def wait_for_notify_sent(ctx, *, timeout: float = 10.0) -> PatientCase.GetStatusResponse:
    """Poll get_status until notify_status == 'sent' or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        status = await PatientCase.ref(PATIENT_ID).get_status(
            ctx, PatientCase.GetStatusRequest()
        )
        if status.notify_status == "sent":
            return status
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"notify_status never reached 'sent'. Last value: '{status.notify_status}'"
            )
        await asyncio.sleep(0.3)


async def run():
    rbt = Reboot()
    await rbt.start()

    app = Application(servicers=[PatientCaseServicer, BedRegistryServicer])

    # ── Part 1: normal path ────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  PART 1 — Normal workflow: admit → notify_oncall → sent")
    print(f"{'='*64}")

    mock_notifier._call_count = 0
    await rbt.up(app)
    ctx = rbt.create_external_context(name="test-p1")

    admit_resp = await PatientCase.ref(PATIENT_ID).admit(
        ctx, PatientCase.AdmitRequest(bed_id=BED_ID)
    )
    print(f"\n  admit() → success={admit_resp.success}  '{admit_resp.message}'")
    assert admit_resp.success, f"Admission failed: {admit_resp.message}"

    status = await wait_for_notify_sent(ctx, timeout=10.0)
    print(f"  notify_status = '{status.notify_status}'  ✓")
    print(f"  mock_send_page call count = {mock_notifier._call_count}")
    assert mock_notifier._call_count == 1, (
        f"Expected 1 call, got {mock_notifier._call_count}"
    )
    print("  ✓  PASS: workflow converged, mock_send_page called exactly once")
    await rbt.down()

    # ── Part 2: simulated mid-execution restart ────────────────────────────
    print(f"\n{'='*64}")
    print("  PART 2 — Restart after mock_send_page but before state write")
    print(f"{'='*64}")
    print("  (Simulating: server killed in the window between '[PAGER] <<< SENT'")
    print("   and notify_status being written.)\n")

    # Use a fresh patient ID and bed to avoid state collision with Part 1.
    PATIENT2 = "patient-demo-02"
    BED2 = "bed-002"
    mock_notifier._call_count = 0

    # Arm a one-shot barrier: mock_send_page signals when it has returned
    # (i.e. the at_least_once result is now memoized), then blocks until we
    # release it.  That's the window we crash into.
    page_completed = asyncio.Event()
    release_after_page = asyncio.Event()
    original_mock = mock_notifier.mock_send_page

    async def instrumented_send_page(case_id: str) -> str:
        result = await original_mock(case_id)
        # Signal: mock_send_page has returned; result is now in-flight to RocksDB.
        page_completed.set()
        # Hold here until the test releases us — simulating slow I/O in
        # the state write that gives us a chance to call rbt.down().
        await asyncio.sleep(0.4)
        release_after_page.set()
        return result

    mock_notifier.mock_send_page = instrumented_send_page

    try:
        await rbt.up(app)
        ctx2 = rbt.create_external_context(name="test-p2")

        admit2 = await PatientCase.ref(PATIENT2).admit(
            ctx2, PatientCase.AdmitRequest(bed_id=BED2)
        )
        print(f"  admit() → success={admit2.success}  '{admit2.message}'")
        assert admit2.success

        # Wait until mock_send_page has completed and its result is
        # being written to the memoize store.
        await asyncio.wait_for(page_completed.wait(), timeout=8.0)
        print(f"  [PAGER] returned — call count so far: {mock_notifier._call_count}")
        print("  Simulating server kill (rbt.down()) now...")

        await rbt.down()

        # Restart the application (simulates `rbt dev run` auto-restart).
        # Reboot resumes the workflow task from its persisted state.
        print("  Server restarting (rbt.up())...")
        await rbt.up(app)
        ctx3 = rbt.create_external_context(name="test-p2-resumed")

        status2 = await wait_for_notify_sent(ctx3, timeout=10.0)
        print(f"\n  notify_status = '{status2.notify_status}'  ✓")
        print(f"  mock_send_page call count after restart = {mock_notifier._call_count}")

        assert status2.notify_status == "sent", (
            f"Expected 'sent', got '{status2.notify_status}'"
        )
        assert mock_notifier._call_count == 1, (
            f"mock_send_page called {mock_notifier._call_count} times — "
            "expected exactly 1 (memoization should have prevented retry)"
        )

        print()
        print("  ✓  PASS: workflow converged after restart WITHOUT calling")
        print("     mock_send_page a second time — at_least_once memoization")
        print("     returned the stored result from RocksDB.")

    finally:
        mock_notifier.mock_send_page = original_mock
        await rbt.stop()

    print(f"\n{'='*64}")
    print("  ALL TESTS PASSED")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    asyncio.run(run())
