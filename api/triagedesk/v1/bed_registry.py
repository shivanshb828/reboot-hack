from reboot.api import API, Type, Model, Field, Methods, Reader, Writer, Tool


# ── State ─────────────────────────────────────────────────────────────────────
# Singleton (always ref'd as "global") — maps bed_id -> patient_case_id.
# Empty string value means the bed slot exists but is unoccupied.

class BedRegistryState(Model):
    bed_to_patient: dict[str, str] = Field(tag=1, default_factory=dict)


# ── reserve_bed (Writer) ──────────────────────────────────────────────────────
# Called from PatientCase.admit() Transaction to atomically claim a bed.

class ReserveBedRequest(Model):
    bed_id: str = Field(tag=1, default="")
    patient_case_id: str = Field(tag=2, default="")


class ReserveBedResponse(Model):
    success: bool = Field(tag=1, default=False)
    message: str = Field(tag=2, default="")


# ── release_bed (Writer) ──────────────────────────────────────────────────────

class ReleaseBedRequest(Model):
    bed_id: str = Field(tag=1, default="")


class ReleaseBedResponse(Model):
    pass


# ── check_bed (Reader) ────────────────────────────────────────────────────────

class CheckBedRequest(Model):
    bed_id: str = Field(tag=1, default="")


class CheckBedResponse(Model):
    assigned: bool = Field(tag=1, default=False)
    patient_case_id: str = Field(tag=2, default="")


# ── API definition ────────────────────────────────────────────────────────────

api = API(
    BedRegistry=Type(
        state=BedRegistryState,
        methods=Methods(
            reserve_bed=Writer(
                request=ReserveBedRequest,
                response=ReserveBedResponse,
                mcp=Tool(name="reserve_bed", title="Reserve a Bed for a Patient"),
            ),
            release_bed=Writer(
                request=ReleaseBedRequest,
                response=ReleaseBedResponse,
                mcp=Tool(name="release_bed", title="Release a Bed"),
            ),
            check_bed=Reader(
                request=CheckBedRequest,
                response=CheckBedResponse,
                mcp=Tool(name="check_bed", title="Check Bed Availability"),
            ),
        ),
    )
)
