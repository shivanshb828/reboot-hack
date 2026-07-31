from datetime import datetime, timezone
from typing import Any
from triagedesk.v1.patient_case_rbt import PatientCase
from triagedesk.v1.bed_registry_rbt import BedRegistry
from reboot.aio.auth.authorizers import allow
from reboot.aio.contexts import (
    EffectValidation,
    ReaderContext,
    TransactionContext,
    WriterContext,
    WorkflowContext,
)
from reboot.aio.workflows import at_least_once_per_workflow
import mock_notifier  # imported as module so test monkey-patches are visible

BED_REGISTRY_ID = "global"


class PatientCaseServicer(PatientCase.singleton.Servicer):
    """
    admit() race-safety
    ────────────────────
    admit() is a Transaction.  BedRegistry.reserve_bed() is enlisted in the
    same distributed transaction: Reboot serialises all Writers on the same
    BedRegistry("global") state ID, so exactly one of two concurrent admit()
    calls can commit a given bed.  The notify_oncall workflow is scheduled
    atomically inside the same transaction — if the transaction rolls back,
    no workflow is ever created.

    notify_oncall() memoization
    ────────────────────────────
    at_least_once_per_workflow("send_page", ...) stores mock_send_page's
    RETURN VALUE in RocksDB the moment the function returns.  On replay:
      • Crash AFTER mock_send_page returned  →  stored result returned from
        RocksDB without calling the function again.  (Demo scenario.)
      • Crash DURING asyncio.sleep           →  "at least once": function is
        retried on the next loop iteration.  Real SMS APIs accept idempotency
        keys that make even this case safe.

    log_dose idempotency
    ─────────────────────
    Reboot deduplicates calls with the same idempotency key at the gRPC
    middleware layer, before the Python method is invoked.  The append runs
    exactly once per logical request regardless of retries.
    """

    def authorizer(self):
        return PatientCase.Authorizer(
            get_status=allow(),
            admit=allow(),
            log_dose=allow(),
            notify_oncall=allow(),
        )

    async def get_status(
        self,
        context: ReaderContext,
        state: PatientCase.State,
        request: PatientCase.GetStatusRequest,
    ) -> PatientCase.GetStatusResponse:
        return PatientCase.GetStatusResponse(
            status=state.status,
            assigned_bed=state.assigned_bed,
            dose_log=list(state.dose_log),
            notify_status=state.notify_status,
        )

    async def admit(
        self,
        context: TransactionContext,
        state: PatientCase.State,
        request: PatientCase.AdmitRequest,
    ) -> PatientCase.AdmitResponse:
        if state.assigned_bed:
            return PatientCase.AdmitResponse(
                success=False,
                message=f"already_admitted: patient already in bed '{state.assigned_bed}'",
            )

        result = await BedRegistry.ref(BED_REGISTRY_ID).reserve_bed(
            context,
            BedRegistry.ReserveBedRequest(
                bed_id=request.bed_id,
                patient_case_id=context.state_id,
            ),
        )

        if not result.success:
            return PatientCase.AdmitResponse(
                success=False,
                message=result.message,
            )

        state.assigned_bed = request.bed_id
        state.status = "admitted"

        # Spawn the on-call notification workflow durably as part of this
        # Transaction.  If the Transaction rolls back, the spawn is also
        # rolled back — the workflow is only ever created on a successful
        # admission.  Returns a TaskId (ignored — fire-and-forget).
        await PatientCase.ref(context.state_id).schedule().notify_oncall(
            context,
            PatientCase.NotifyOncallRequest(),
        )

        return PatientCase.AdmitResponse(
            success=True,
            message=f"admitted to bed '{request.bed_id}'",
        )

    async def log_dose(
        self,
        context: WriterContext,
        state: PatientCase.State,
        request: PatientCase.LogDoseRequest,
    ) -> PatientCase.LogDoseResponse:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state.dose_log.append(f"{ts}: {request.drug}")
        return PatientCase.LogDoseResponse()

    @classmethod
    async def notify_oncall(
        cls,
        context: WorkflowContext,
        request: PatientCase.NotifyOncallRequest,
    ) -> PatientCase.NotifyOncallResponse:
        async for _ in context.loop("notify"):
            # ── Idempotency guard ──────────────────────────────────────────
            # If state already shows "sent" (e.g. loop restarted after the
            # write below already committed), we're done.
            state = await PatientCase.ref().per_iteration("read-status").read(context)
            if state.notify_status == "sent":
                break

            case_id = context.state_id

            # ── Durable external call ──────────────────────────────────────
            # at_least_once_per_workflow checkpoints mock_send_page's return
            # value to RocksDB once the function returns.
            #
            # On replay:
            #   • result already in RocksDB → returned immediately, function
            #     NOT called again.  This is provably true regardless of what
            #     the Pydantic state says at that moment.
            #   • result NOT in RocksDB (crashed during asyncio.sleep) →
            #     function is retried ("at least once" semantics).
            #
            # effect_validation=DISABLED: suppresses Reboot's dev-mode dry-run
            # re-invocation of this function (which would call mock_send_page
            # twice in dev mode for effect validation).
            # `type=str` is required here because `lambda` has no return
            # annotation and at_least_once cannot infer what to pickle.
            async def _call_pager() -> str:
                return await mock_notifier.mock_send_page(case_id)

            await at_least_once_per_workflow(
                "send_page",
                context,
                _call_pager,
                type=str,
                effect_validation=EffectValidation.DISABLED,
            )

            # ── Atomic state update ────────────────────────────────────────
            # If the server crashes between at_least_once returning and this
            # write committing:
            #   1. Workflow restarts → loop top reads notify_status="pending"
            #   2. at_least_once finds "send_page" already in RocksDB → skips
            #      mock_send_page entirely
            #   3. This write runs again → converges to "sent"
            async def _mark_sent(state: Any) -> None:
                state.notify_status = "sent"

            await PatientCase.ref().per_workflow("set-sent").write(
                context, _mark_sent
            )
            break

        return PatientCase.NotifyOncallResponse()
