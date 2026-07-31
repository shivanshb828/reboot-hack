"""
Concurrent-admit race test for TriageDesk.

Fires two admit() calls for the same bed from two different PatientCase state
machines simultaneously.  Exactly one must succeed and one must get
"bed_unavailable" — proving Reboot's transaction serialisation prevents a
double-assignment.

Run from the project root:
    PYTHONPATH=backend/api:backend/src python backend/src/test_concurrent_admit.py
"""

import asyncio
import sys
from reboot.aio.applications import Application
from reboot.aio.tests import Reboot
from triagedesk.v1.patient_case_rbt import PatientCase
from triagedesk.v1.bed_registry_rbt import BedRegistry
from patient_case_servicer import PatientCaseServicer
from bed_registry_servicer import BedRegistryServicer

BED_ID = "bed-42"
PATIENT_A = "patient-alpha"
PATIENT_B = "patient-beta"


async def run():
    rbt = Reboot()
    await rbt.start()
    await rbt.up(
        Application(servicers=[PatientCaseServicer, BedRegistryServicer])
    )

    try:
        ctx = rbt.create_external_context(name="race-test")

        # Fire both admit() calls concurrently from two different patient
        # case state machines, both targeting the same bed.
        result_a, result_b = await asyncio.gather(
            PatientCase.ref(PATIENT_A).admit(
                ctx, PatientCase.AdmitRequest(bed_id=BED_ID)
            ),
            PatientCase.ref(PATIENT_B).admit(
                ctx, PatientCase.AdmitRequest(bed_id=BED_ID)
            ),
        )

        print(f"\n{'='*60}")
        print(f"  CONCURRENT ADMIT RACE TEST — bed '{BED_ID}'")
        print(f"{'='*60}")
        print(f"  {PATIENT_A}: success={result_a.success}  message='{result_a.message}'")
        print(f"  {PATIENT_B}: success={result_b.success}  message='{result_b.message}'")
        print(f"{'='*60}")

        successes = [r for r in (result_a, result_b) if r.success]
        failures  = [r for r in (result_a, result_b) if not r.success]

        assert len(successes) == 1, (
            f"Expected exactly 1 success, got {len(successes)}: {successes}"
        )
        assert len(failures) == 1, (
            f"Expected exactly 1 failure, got {len(failures)}: {failures}"
        )
        assert "bed_unavailable" in failures[0].message, (
            f"Failure message should contain 'bed_unavailable', got: '{failures[0].message}'"
        )

        print(f"\n  ✓  PASS: exactly one admit succeeded, one got bed_unavailable")
        print(f"  ✓  No double-assignment possible — BedRegistry.reserve_bed")
        print(f"     is serialised by Reboot before PatientCase state is touched.\n")

        # Also verify BedRegistry reflects the winner.
        check = await BedRegistry.ref("global").check_bed(
            ctx, BedRegistry.CheckBedRequest(bed_id=BED_ID)
        )
        winner = PATIENT_A if result_a.success else PATIENT_B
        assert check.assigned, "BedRegistry should show the bed as assigned"
        assert check.patient_case_id == winner, (
            f"BedRegistry maps to '{check.patient_case_id}', expected '{winner}'"
        )
        print(f"  ✓  BedRegistry confirms bed '{BED_ID}' → '{check.patient_case_id}'")
        print()

    finally:
        await rbt.stop()


if __name__ == "__main__":
    asyncio.run(run())
