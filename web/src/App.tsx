import React, { FormEvent, useEffect, useState } from "react";
import { useBedRegistry } from "./api/triagedesk/v1/bed_registry_rbt_react";
import { usePatientCase } from "./api/triagedesk/v1/patient_case_rbt_react";

const BED_REGISTRY_ID = "global";
const FALLBACK_CASE_ID = "triage-preview";
const TRACKED_BEDS_STORAGE_KEY = "triagedesk.trackedBeds";

type AlertTone = "idle" | "success" | "warning" | "error";

type AlertState = {
  tone: AlertTone;
  message: string;
};

const defaultAlert: AlertState = {
  tone: "idle",
  message: "",
};

const loadTrackedBeds = () => {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = window.localStorage.getItem(TRACKED_BEDS_STORAGE_KEY);
    const parsed = stored ? JSON.parse(stored) : [];
    return Array.isArray(parsed)
      ? parsed.filter((bedId): bedId is string => typeof bedId === "string")
      : [];
  } catch {
    return [];
  }
};

const normalizeId = (value: string, fallback: string) => {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : fallback;
};

const formatAbort = (aborted: { message: string } | undefined) =>
  aborted ? aborted.message : "Request failed.";

const App = () => {
  const [admitCaseId, setAdmitCaseId] = useState("case-1001");
  const [bedId, setBedId] = useState("bed-a1");
  const [watchCaseId, setWatchCaseId] = useState("case-1001");
  const [drug, setDrug] = useState("");
  const [trackBedId, setTrackBedId] = useState("");
  const [trackedBeds, setTrackedBeds] = useState<string[]>(loadTrackedBeds);
  const [admitAlert, setAdmitAlert] = useState<AlertState>(defaultAlert);
  const [doseAlert, setDoseAlert] = useState<AlertState>(defaultAlert);

  const admitPatientCase = usePatientCase({
    id: normalizeId(admitCaseId, FALLBACK_CASE_ID),
  });
  const watchedPatientCase = usePatientCase({
    id: normalizeId(watchCaseId, FALLBACK_CASE_ID),
  });
  const { response: caseStatus, isLoading, aborted } =
    watchedPatientCase.useGetStatus();

  useEffect(() => {
    window.localStorage.setItem(
      TRACKED_BEDS_STORAGE_KEY,
      JSON.stringify(trackedBeds)
    );
  }, [trackedBeds]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === TRACKED_BEDS_STORAGE_KEY) {
        setTrackedBeds(loadTrackedBeds());
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const addTrackedBed = (nextBedId: string) => {
    const normalizedBedId = nextBedId.trim();
    if (normalizedBedId.length === 0) {
      return;
    }

    setTrackedBeds((current) =>
      current.includes(normalizedBedId)
        ? current
        : [...current, normalizedBedId].sort()
    );
  };

  const handleAdmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedBedId = bedId.trim();
    if (admitCaseId.trim().length === 0 || normalizedBedId.length === 0) {
      setAdmitAlert({
        tone: "warning",
        message: "Patient case ID and bed ID are required.",
      });
      return;
    }

    setAdmitAlert(defaultAlert);
    addTrackedBed(normalizedBedId);

    const { response, aborted } = await admitPatientCase.admit({
      bedId: normalizedBedId,
    });

    if (aborted !== undefined) {
      setAdmitAlert({ tone: "error", message: formatAbort(aborted) });
      return;
    }

    setAdmitAlert({
      tone: response.success ? "success" : "warning",
      message: `${response.success ? "Admitted" : "Bed unavailable"}${
        response.message ? `: ${response.message}` : ""
      }`,
    });
  };

  const handleLogDose = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedDrug = drug.trim();
    if (watchCaseId.trim().length === 0 || normalizedDrug.length === 0) {
      setDoseAlert({
        tone: "warning",
        message: "Patient case ID and drug name are required.",
      });
      return;
    }

    setDoseAlert(defaultAlert);

    const { aborted } = await watchedPatientCase.logDose({
      drug: normalizedDrug,
    });

    if (aborted !== undefined) {
      setDoseAlert({ tone: "error", message: formatAbort(aborted) });
      return;
    }

    setDrug("");
    setDoseAlert({ tone: "success", message: "Dose logged." });
  };

  const handleTrackBed = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    addTrackedBed(trackBedId);
    setTrackBedId("");
  };

  const doseLog = caseStatus?.doseLog ?? [];
  const notifyStatus = normalizeNotifyStatus(caseStatus?.notifyStatus);

  return (
    <main style={styles.page}>
      <section style={styles.header}>
        <div>
          <h1 style={styles.title}>TriageDesk</h1>
          <p style={styles.subtitle}>Patient admission and shift handoff</p>
        </div>
        <div style={styles.connectionPill}>
          {aborted ? "Reader error" : isLoading ? "Connecting" : "Live"}
        </div>
      </section>

      <section style={styles.grid}>
        <form style={styles.panel} onSubmit={handleAdmit}>
          <PanelTitle title="Admit Patient" />
          <label style={styles.label}>
            Patient case ID
            <input
              style={styles.input}
              value={admitCaseId}
              onChange={(event) => setAdmitCaseId(event.target.value)}
              placeholder="case-1001"
            />
          </label>
          <label style={styles.label}>
            Bed ID
            <input
              style={styles.input}
              value={bedId}
              onChange={(event) => setBedId(event.target.value)}
              placeholder="bed-a1"
            />
          </label>
          <button
            style={styles.primaryButton}
            disabled={admitPatientCase.admit.pending.length > 0}
          >
            Admit
          </button>
          <Alert alert={admitAlert} />
        </form>

        <section style={styles.panel}>
          <PanelTitle title="Live Bed Registry" />
          <form style={styles.inlineForm} onSubmit={handleTrackBed}>
            <input
              style={styles.input}
              value={trackBedId}
              onChange={(event) => setTrackBedId(event.target.value)}
              placeholder="bed-a1"
            />
            <button style={styles.secondaryButton}>Track</button>
          </form>

          <div style={styles.list}>
            {trackedBeds.length === 0 ? (
              <EmptyState text="No beds tracked." />
            ) : (
              trackedBeds.map((trackedBedId) => (
                <BedAssignmentRow
                  key={trackedBedId}
                  bedId={trackedBedId}
                  onRemove={() =>
                    setTrackedBeds((current) =>
                      current.filter((value) => value !== trackedBedId)
                    )
                  }
                />
              ))
            )}
          </div>
        </section>

        <section style={styles.panel}>
          <PanelTitle title="Patient Case" />
          <label style={styles.label}>
            Case ID
            <input
              style={styles.input}
              value={watchCaseId}
              onChange={(event) => setWatchCaseId(event.target.value)}
              placeholder="case-1001"
            />
          </label>

          <div style={styles.statusGrid}>
            <Metric label="Status" value={caseStatus?.status || "waiting"} />
            <Metric
              label="Assigned bed"
              value={caseStatus?.assignedBed || "None"}
            />
            <div style={styles.metric}>
              <span style={styles.metricLabel}>Notify status</span>
              <span style={notifyPillStyles[notifyStatus]}>
                {notifyStatus}
              </span>
            </div>
          </div>

          {aborted ? (
            <Alert
              alert={{
                tone: "error",
                message: formatAbort(aborted),
              }}
            />
          ) : null}
        </section>

        <form style={styles.panel} onSubmit={handleLogDose}>
          <PanelTitle title="Dose Log" />
          <div style={styles.inlineForm}>
            <input
              style={styles.input}
              value={drug}
              onChange={(event) => setDrug(event.target.value)}
              placeholder="Drug name"
            />
            <button
              style={styles.secondaryButton}
              disabled={watchedPatientCase.logDose.pending.length > 0}
            >
              Log Dose
            </button>
          </div>
          <Alert alert={doseAlert} />
          <div style={styles.list}>
            {doseLog.length === 0 ? (
              <EmptyState text="No doses logged." />
            ) : (
              doseLog.map((entry, index) => (
                <div key={`${entry}-${index}`} style={styles.row}>
                  <span style={styles.rowPrimary}>{entry}</span>
                </div>
              ))
            )}
          </div>
        </form>
      </section>
    </main>
  );
};

const BedAssignmentRow = ({
  bedId,
  onRemove,
}: {
  bedId: string;
  onRemove: () => void;
}) => {
  const bedRegistry = useBedRegistry({ id: BED_REGISTRY_ID });
  const { response, isLoading, aborted } = bedRegistry.useCheckBed({ bedId });
  const assigned = response?.assigned ?? false;
  const patientCaseId = response?.patientCaseId ?? "";

  return (
    <div style={styles.row}>
      <div>
        <span style={styles.rowPrimary}>{bedId}</span>
        <span style={styles.rowSecondary}>
          {aborted
            ? formatAbort(aborted)
            : isLoading
              ? "Checking"
              : assigned
                ? patientCaseId
                : "Available"}
        </span>
      </div>
      <div style={styles.rowActions}>
        <span style={assigned ? styles.assignedBadge : styles.availableBadge}>
          {assigned ? "Assigned" : "Open"}
        </span>
        <button style={styles.iconButton} onClick={onRemove} type="button">
          x
        </button>
      </div>
    </div>
  );
};

const PanelTitle = ({ title }: { title: string }) => (
  <h2 style={styles.panelTitle}>{title}</h2>
);

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div style={styles.metric}>
    <span style={styles.metricLabel}>{label}</span>
    <strong style={styles.metricValue}>{value}</strong>
  </div>
);

const EmptyState = ({ text }: { text: string }) => (
  <div style={styles.empty}>{text}</div>
);

const Alert = ({ alert }: { alert: AlertState }) =>
  alert.tone === "idle" ? null : (
    <div style={{ ...styles.alert, ...alertStyles[alert.tone] }}>
      {alert.message}
    </div>
  );

const normalizeNotifyStatus = (value: string | undefined) => {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "sent") {
    return "sent";
  }
  if (normalized === "failed") {
    return "failed";
  }
  return "pending";
};

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    padding: 24,
    background: "#f6f7f9",
    color: "#17202a",
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    boxSizing: "border-box",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 16,
    maxWidth: 1180,
    margin: "0 auto 20px",
  },
  title: {
    margin: 0,
    fontSize: 32,
    fontWeight: 760,
    letterSpacing: 0,
  },
  subtitle: {
    margin: "4px 0 0",
    color: "#637083",
    fontSize: 14,
  },
  connectionPill: {
    border: "1px solid #cdd6e1",
    borderRadius: 999,
    padding: "8px 12px",
    background: "#ffffff",
    fontSize: 13,
    fontWeight: 700,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 16,
    maxWidth: 1180,
    margin: "0 auto",
  },
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    minHeight: 220,
    padding: 16,
    border: "1px solid #d9e0e8",
    borderRadius: 8,
    background: "#ffffff",
    boxShadow: "0 1px 2px rgba(16, 24, 40, 0.05)",
  },
  panelTitle: {
    margin: "0 0 4px",
    fontSize: 17,
    fontWeight: 760,
    letterSpacing: 0,
  },
  label: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    color: "#425066",
    fontSize: 13,
    fontWeight: 700,
  },
  input: {
    width: "100%",
    minWidth: 0,
    height: 40,
    boxSizing: "border-box",
    border: "1px solid #c9d3df",
    borderRadius: 6,
    padding: "0 10px",
    color: "#17202a",
    background: "#ffffff",
    fontSize: 14,
  },
  inlineForm: {
    display: "grid",
    gridTemplateColumns: "1fr auto",
    gap: 8,
  },
  primaryButton: {
    height: 42,
    border: "1px solid #0f766e",
    borderRadius: 6,
    background: "#0f766e",
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 760,
  },
  secondaryButton: {
    height: 40,
    border: "1px solid #23415f",
    borderRadius: 6,
    background: "#23415f",
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 760,
    padding: "0 14px",
  },
  iconButton: {
    width: 28,
    height: 28,
    border: "1px solid #d0d7df",
    borderRadius: 6,
    background: "#ffffff",
    color: "#526071",
    cursor: "pointer",
    fontSize: 14,
    lineHeight: 1,
  },
  alert: {
    borderRadius: 6,
    padding: "10px 12px",
    fontSize: 13,
    fontWeight: 650,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    marginTop: 4,
  },
  row: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    minHeight: 48,
    padding: "10px 12px",
    border: "1px solid #e2e7ee",
    borderRadius: 6,
    background: "#fbfcfd",
  },
  rowPrimary: {
    display: "block",
    color: "#17202a",
    fontSize: 14,
    fontWeight: 760,
    wordBreak: "break-word",
  },
  rowSecondary: {
    display: "block",
    marginTop: 3,
    color: "#637083",
    fontSize: 12,
    wordBreak: "break-word",
  },
  rowActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  assignedBadge: {
    borderRadius: 999,
    padding: "5px 8px",
    background: "#e8f3ff",
    color: "#174a7c",
    fontSize: 12,
    fontWeight: 760,
  },
  availableBadge: {
    borderRadius: 999,
    padding: "5px 8px",
    background: "#ebf7ee",
    color: "#1f6b3a",
    fontSize: 12,
    fontWeight: 760,
  },
  empty: {
    padding: "16px 12px",
    border: "1px dashed #cdd6e1",
    borderRadius: 6,
    color: "#637083",
    fontSize: 13,
    textAlign: "center",
  },
  statusGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
    gap: 10,
  },
  metric: {
    minHeight: 66,
    padding: 12,
    border: "1px solid #e2e7ee",
    borderRadius: 6,
    background: "#fbfcfd",
  },
  metricLabel: {
    display: "block",
    color: "#637083",
    fontSize: 12,
    fontWeight: 700,
    marginBottom: 6,
  },
  metricValue: {
    display: "block",
    color: "#17202a",
    fontSize: 15,
    wordBreak: "break-word",
  },
};

const alertStyles: Record<Exclude<AlertTone, "idle">, React.CSSProperties> = {
  success: {
    border: "1px solid #b7dfc1",
    background: "#eef9f1",
    color: "#1f6b3a",
  },
  warning: {
    border: "1px solid #f1d58d",
    background: "#fff8e7",
    color: "#8a5a00",
  },
  error: {
    border: "1px solid #f0b4b4",
    background: "#fff0f0",
    color: "#9d2525",
  },
};

const notifyPillStyles: Record<string, React.CSSProperties> = {
  pending: {
    display: "inline-flex",
    borderRadius: 999,
    padding: "6px 10px",
    background: "#fff8e7",
    color: "#8a5a00",
    fontSize: 13,
    fontWeight: 800,
    textTransform: "capitalize",
  },
  sent: {
    display: "inline-flex",
    borderRadius: 999,
    padding: "6px 10px",
    background: "#eef9f1",
    color: "#1f6b3a",
    fontSize: 13,
    fontWeight: 800,
    textTransform: "capitalize",
  },
  failed: {
    display: "inline-flex",
    borderRadius: 999,
    padding: "6px 10px",
    background: "#fff0f0",
    color: "#9d2525",
    fontSize: 13,
    fontWeight: 800,
    textTransform: "capitalize",
  },
};

export default App;
