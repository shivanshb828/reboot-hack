from triagedesk.v1.patient_case_rbt import PatientCase
from reboot.aio.auth.authorizers import allow
from reboot.aio.contexts import ReaderContext, TransactionContext, WriterContext, WorkflowContext


class PatientCaseServicer(PatientCase.singleton.Servicer):
    """
    Servicer for individual patient case state machines.
    Each patient gets a unique state ID; this class handles any instance.

    PatientCase.singleton.Servicer gives us explicit `state` parameters —
    switch to PatientCase.Servicer (self.state property) for multi-instance
    concurrency isolation once implementing method bodies.
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
        # Reader: safe for concurrent calls — returns a snapshot of state.
        raise NotImplementedError

    async def admit(
        self,
        context: TransactionContext,
        state: PatientCase.State,
        request: PatientCase.AdmitRequest,
    ) -> PatientCase.AdmitResponse:
        # Transaction: atomically checks BedRegistry and claims the bed.
        # Use context to call BedRegistry.ref("global").check_bed() and
        # BedRegistry.ref("global").reserve_bed() before mutating state.
        raise NotImplementedError

    async def log_dose(
        self,
        context: WriterContext,
        state: PatientCase.State,
        request: PatientCase.LogDoseRequest,
    ) -> PatientCase.LogDoseResponse:
        # Writer: appends to dose_log; owns this state exclusively.
        raise NotImplementedError

    @classmethod
    async def notify_oncall(
        cls,
        context: WorkflowContext,
        request: PatientCase.NotifyOncallRequest,
    ) -> PatientCase.NotifyOncallResponse:
        # Workflow: durable, survives crashes. Use context.loop() to guard
        # against double-notifying by checking notify_status at loop start.
        raise NotImplementedError
