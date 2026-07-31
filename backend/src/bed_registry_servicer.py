from triagedesk.v1.bed_registry_rbt import BedRegistry
from reboot.aio.auth.authorizers import allow
from reboot.aio.contexts import ReaderContext, WriterContext


class BedRegistryServicer(BedRegistry.singleton.Servicer):
    """
    Singleton servicer for the global bed registry (always ref'd as "global").
    Tracks bed_id -> patient_case_id assignments across the entire system.

    All writers on a single BedRegistry state ID are serialised by Reboot, so
    every reserve_bed() call sees the definitive committed view of bed_to_patient
    — no external lock needed.
    """

    def authorizer(self):
        return BedRegistry.Authorizer(
            reserve_bed=allow(),
            release_bed=allow(),
            check_bed=allow(),
        )

    async def reserve_bed(
        self,
        context: WriterContext,
        state: BedRegistry.State,
        request: BedRegistry.ReserveBedRequest,
    ) -> BedRegistry.ReserveBedResponse:
        current = state.bed_to_patient.get(request.bed_id, "")
        if current and current != request.patient_case_id:
            # Bed is already owned by a *different* patient case.
            return BedRegistry.ReserveBedResponse(
                success=False,
                message=f"bed_unavailable: bed '{request.bed_id}' is assigned to '{current}'",
            )
        state.bed_to_patient[request.bed_id] = request.patient_case_id
        return BedRegistry.ReserveBedResponse(success=True, message="")

    async def release_bed(
        self,
        context: WriterContext,
        state: BedRegistry.State,
        request: BedRegistry.ReleaseBedRequest,
    ) -> BedRegistry.ReleaseBedResponse:
        state.bed_to_patient.pop(request.bed_id, None)
        return BedRegistry.ReleaseBedResponse()

    async def check_bed(
        self,
        context: ReaderContext,
        state: BedRegistry.State,
        request: BedRegistry.CheckBedRequest,
    ) -> BedRegistry.CheckBedResponse:
        occupant = state.bed_to_patient.get(request.bed_id, "")
        return BedRegistry.CheckBedResponse(
            assigned=bool(occupant),
            patient_case_id=occupant,
        )
