from triagedesk.v1.bed_registry_rbt import BedRegistry
from reboot.aio.auth.authorizers import allow
from reboot.aio.contexts import ReaderContext, WriterContext


class BedRegistryServicer(BedRegistry.singleton.Servicer):
    """
    Singleton servicer for the global bed registry (always ref'd as "global").
    Tracks bed_id -> patient_case_id assignments across the entire system.
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
        # Writer: claim a bed for a patient if it is currently free.
        # Returns success=False if bed_id is already in bed_to_patient.
        raise NotImplementedError

    async def release_bed(
        self,
        context: WriterContext,
        state: BedRegistry.State,
        request: BedRegistry.ReleaseBedRequest,
    ) -> BedRegistry.ReleaseBedResponse:
        # Writer: remove a bed_id from the assignments map.
        raise NotImplementedError

    async def check_bed(
        self,
        context: ReaderContext,
        state: BedRegistry.State,
        request: BedRegistry.CheckBedRequest,
    ) -> BedRegistry.CheckBedResponse:
        # Reader: concurrent-safe lookup of current bed assignment.
        raise NotImplementedError
