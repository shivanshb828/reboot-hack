import type { FC } from "react";
import {
  type UsePatientCaseApi,
  usePatientCase,
} from "@api/triagedesk/v1/patient_case_rbt_react";
import "./index.css";

type NotifyStatus = "pending" | "sent" | "failed";

export const PatientSummaryCardApp: FC = () => {
  const { patientCase, isLoading } = usePatientCase();

  if (isLoading) {
    return <Shell message="Loading patient case..." />;
  }

  if (patientCase === undefined) {
    return <Shell message="No patient case selected." />;
  }

  return <PatientSummaryCard patientCase={patientCase} />;
};

const PatientSummaryCard: FC<{ patientCase: UsePatientCaseApi }> = ({
  patientCase,
}) => {
  const { response, isLoading, aborted } = patientCase.useGetStatus();

  if (aborted !== undefined) {
    return <Shell tone="error" message={aborted.message} />;
  }

  if (isLoading && response === undefined) {
    return <Shell message="Subscribing to patient status..." />;
  }

  const status = response?.status || "waiting";
  const assignedBed = response?.assignedBed || "unassigned";
  const doseCount = response?.doseLog?.length ?? 0;
  const notifyStatus = normalizeNotifyStatus(response?.notifyStatus);

  return (
    <article className="card" aria-label="Patient summary card">
      <header className="cardHeader">
        <div>
          <p className="eyebrow">Patient Case</p>
          <h1>{patientCase.state_id}</h1>
        </div>
        <span className={`notifyPill ${notifyStatus}`}>{notifyStatus}</span>
      </header>

      <dl className="metrics">
        <div className="metric">
          <dt>Status</dt>
          <dd>{status}</dd>
        </div>
        <div className="metric">
          <dt>Assigned bed</dt>
          <dd>{assignedBed}</dd>
        </div>
        <div className="metric">
          <dt>Dose count</dt>
          <dd>{doseCount}</dd>
        </div>
      </dl>
    </article>
  );
};

const Shell: FC<{ message: string; tone?: "neutral" | "error" }> = ({
  message,
  tone = "neutral",
}) => <div className={`shell ${tone}`}>{message}</div>;

const normalizeNotifyStatus = (value: string | undefined): NotifyStatus => {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "sent") {
    return "sent";
  }
  if (normalized === "failed") {
    return "failed";
  }
  return "pending";
};
