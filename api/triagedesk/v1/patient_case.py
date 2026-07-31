from typing import Optional
from reboot.api import API, Type, Model, Field, Methods, Reader, Writer, Transaction, Workflow, Tool


# ── State ─────────────────────────────────────────────────────────────────────

class PatientCaseState(Model):
    status: str = Field(tag=1, default="")      # e.g. "waiting", "admitted", "notified"
    assigned_bed: Optional[str] = Field(tag=2, default=None)
    dose_log: list[str] = Field(tag=3, default_factory=list)
    notify_status: str = Field(tag=4, default="")  # e.g. "pending", "sent", "failed"


# ── get_status (Reader) ───────────────────────────────────────────────────────

class GetStatusRequest(Model):
    pass


class GetStatusResponse(Model):
    status: str = Field(tag=1, default="")
    assigned_bed: Optional[str] = Field(tag=2, default=None)
    dose_log: list[str] = Field(tag=3, default_factory=list)
    notify_status: str = Field(tag=4, default="")


# ── admit (Transaction) ───────────────────────────────────────────────────────
# Must be a Transaction (not Writer) because it atomically checks and updates
# BedRegistry — a separate state machine — before mutating PatientCase state.

class AdmitRequest(Model):
    bed_id: str = Field(tag=1, default="")


class AdmitResponse(Model):
    success: bool = Field(tag=1, default=False)
    message: str = Field(tag=2, default="")


# ── log_dose (Writer) ─────────────────────────────────────────────────────────

class LogDoseRequest(Model):
    drug: str = Field(tag=1, default="")


class LogDoseResponse(Model):
    pass


# ── notify_oncall (Workflow) ──────────────────────────────────────────────────
# Durable workflow — survives mid-execution crashes and resumes without
# double-notifying by checking notify_status at the top of context.loop().

class NotifyOncallRequest(Model):
    pass


class NotifyOncallResponse(Model):
    pass


# ── API definition ────────────────────────────────────────────────────────────

api = API(
    PatientCase=Type(
        state=PatientCaseState,
        methods=Methods(
            get_status=Reader(
                request=GetStatusRequest,
                response=GetStatusResponse,
                mcp=Tool(name="get_patient_status", title="Get Patient Case Status"),
            ),
            admit=Transaction(
                request=AdmitRequest,
                response=AdmitResponse,
                mcp=Tool(name="admit_patient", title="Admit Patient to Bed"),
            ),
            log_dose=Writer(
                request=LogDoseRequest,
                response=LogDoseResponse,
                mcp=Tool(name="log_dose", title="Log Drug Administration"),
            ),
            notify_oncall=Workflow(
                request=NotifyOncallRequest,
                response=NotifyOncallResponse,
                mcp=Tool(name="notify_oncall", title="Notify On-Call Staff"),
            ),
        ),
    )
)
