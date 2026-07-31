# TriageDesk — Reboot Hackathon Proof of Work

## 1. Project summary

TriageDesk is a healthcare on-call and triage application built on top of Reboot. It targets three specific production failure modes that are endemic to distributed systems in clinical settings: double-assignment of a hospital bed under concurrent load, duplicate medication dose entries on retry, and a crash in the window between an on-call page being sent and the patient record being updated to reflect it. The project also includes a voice-capable MCP application (patient summary card) intended for hands-free nurse workflows.

---

## 2. What Reboot provided vs. what we explicitly engineered

### Free from the platform

**Idempotent React calls.** Reboot's React hooks (`useGetStatus`) set up a streaming subscription to state — the MCP card re-renders whenever `notify_status`, `assigned_bed`, or `dose_log` changes on the server. No polling, no manual cache invalidation.

**Serialized writers preventing bed-assignment races.** `BedRegistry.reserve_bed()` is a `WriterContext` handler on the singleton `BedRegistry("global")` state machine. Reboot serializes all writers on the same state ID, so every `reserve_bed()` call sees the definitive committed view of `bed_to_patient` — no explicit locking or compare-and-swap needed in application code (`bed_registry_servicer.py:6-14`).

**gRPC-layer idempotency for log_dose.** Reboot deduplicates calls with the same idempotency key at the gRPC middleware layer, before the Python method is invoked. The `log_dose` append runs exactly once per logical request regardless of client retries. This is a platform guarantee; we did not write deduplication logic in `log_dose` itself (`patient_case_servicer.py:111-119`).

### Explicitly engineered

**`notify_oncall` workflow memoization via `at_least_once_per_workflow`.** This is the one mechanism where we had to make deliberate design choices that the platform does not make for you automatically. The docstring in `patient_case_servicer.py` (lines 30-45) captures the exact semantics:

```
at_least_once_per_workflow("send_page", ...) stores mock_send_page's
RETURN VALUE in RocksDB the moment the function returns.  On replay:
  • Crash AFTER mock_send_page returned  →  stored result returned from
    RocksDB without calling the function again.  (Demo scenario.)
  • Crash DURING asyncio.sleep           →  "at least once": function is
    retried on the next loop iteration.  Real SMS APIs accept idempotency
    keys that make even this case safe.
```

We also added `effect_validation=EffectValidation.DISABLED` explicitly, because Reboot's dev-mode dry-run re-invocation would otherwise call `mock_send_page` twice during effect validation — a subtle interaction with the memoization boundary that required deliberate handling (`patient_case_servicer.py:148-162`).

**Atomic workflow spawn inside admit transaction.** The `notify_oncall` workflow is scheduled via `context.schedule()` inside the `TransactionContext` of `admit()`. If the transaction rolls back (e.g., because `reserve_bed` failed), the workflow spawn is also rolled back — the on-call notification is only ever created on a successful admission (`patient_case_servicer.py:101-104`).

---

## 3. The three failure modes we targeted

Of the five failure modes from the event brief, we targeted three:

| Failure mode from brief | Our mapping |
|---|---|
| Two buyers, one item | Two concurrent `admit()` calls racing for one bed |
| Retry that charges twice | Duplicate dose entry on `log_dose` retry |
| Crash between charge and email | Crash between bed assignment and on-call notification |
| The timeout that lied | **Not targeted** |
| The 200 that hid a failure | **Not targeted** |

We did not implement any error-hiding scenarios or timeout-related failure modes. The three we targeted are the ones with clear Reboot primitives to demonstrate.

---

## 4. Failure modes in detail

### Failure mode 1: Two admits racing for one bed

**Risk without the fix:** Two nurses admit different patients to the same bed in the same second. Both `admit()` calls read `bed_to_patient` as empty, both write the assignment, the second write overwrites the first. One patient has no bed in the record; the other has a bed that's physically occupied by someone else.

**What we did:** `admit()` is a `TransactionContext`. It calls `BedRegistry.ref("global").reserve_bed(context, ...)`, enlisting `reserve_bed` in the same distributed transaction. Because all writers on `BedRegistry("global")` are serialized by Reboot, the second concurrent call sees the committed result of the first — including the bed assignment — before it can commit. `reserve_bed` checks `state.bed_to_patient.get(bed_id)` and returns `bed_unavailable` if the bed is already occupied by a different patient (`bed_registry_servicer.py:29-35`).

**Repro command:**
```bash
PYTHONPATH=backend/api:backend/src python backend/src/test_concurrent_admit.py
```

`asyncio.gather` fires both `admit()` calls simultaneously. The test asserts exactly one success and one `bed_unavailable` failure, then verifies `BedRegistry` maps to the winner.

---

### Failure mode 2: Duplicate dose entry on retry

**Risk without the fix:** A nurse logs a dose, the network blips, the client retries. Both requests reach the server. `dose_log` gets the same entry appended twice. A pharmacist or audit trail sees a double dose.

**What we did:** `log_dose` relies on Reboot's gRPC middleware idempotency key deduplication. Reboot intercepts the retry before the Python method is invoked and returns the already-committed response. The `dose_log.append` runs exactly once per logical operation regardless of how many times the client retries (`patient_case_servicer.py:111-119`, docstring lines 42-45).

**Repro command:** There is no standalone automated test for this failure mode. The mechanism is a Reboot platform guarantee exercised at the transport layer, not application logic. To observe it manually, send two identical `log_dose` RPCs with the same idempotency key and confirm `dose_log` length increments by one, not two.

---

### Failure mode 3: Crash between bed assignment and on-call notification

**Risk without the fix:** `admit()` succeeds, the on-call pager fires, the server crashes before the patient record is updated to `notify_status = "sent"`. On restart, the workflow retries, fires the pager a second time. The on-call physician gets paged twice for the same admission — or worse, the page is never confirmed as delivered.

**What we did:** `at_least_once_per_workflow("send_page", context, _call_pager, type=str, ...)` checkpoints the return value of `mock_send_page` to RocksDB the moment it returns. On workflow restart, Reboot finds `"send_page"` already in the RocksDB memoize store and returns the stored result without calling `mock_send_page` again. The subsequent `notify_status = "sent"` write then runs once and converges (`patient_case_servicer.py:128-176`).

**Repro command:**
```bash
PYTHONPATH=api:backend/api:backend/src python backend/src/test_notify_workflow.py
```

The test has two parts. Part 1 verifies the normal path (`mock_send_page` called exactly once). Part 2 monkey-patches `mock_send_page` with a barrier that signals after the function returns but before the state write commits, then calls `rbt.down()` in that window to simulate a crash, then calls `rbt.up()` to restart. The assertion: `mock_notifier._call_count == 1` after restart — the memoized result was returned from RocksDB without re-invoking the pager.

---

## 5. MCP patient summary card

There are two distinct frontends. The **web frontend** (`web/src/App.tsx`) is the full interactive TriageDesk UI — it has an Admit form that calls `admit()`, a Dose Log form that calls `logDose()`, and a Live Bed Registry panel that reactively tracks bed assignments. The **MCP patient summary card** (`frontend/mcp/patient_summary_card/App.tsx`) is a separate embedded component designed as the MCP-surfaced view for hands-free/voice workflows.

**What the MCP card shows:** patient case ID, a color-coded notify-status pill (`pending` / `sent` / `failed`), and three live metrics — admission status, assigned bed, and dose count. It uses `usePatientCase()` and `patientCase.useGetStatus()` to subscribe to server state reactively; the card re-renders automatically when any of these fields change without polling.

**What the MCP card does NOT do:** The MCP card component (`App.tsx`) has no action buttons, no form inputs, and makes no mutation calls. The `UsePatientCaseApi` type it receives does expose `admit` and `logDose` as callable methods, but the component does not invoke them. Mutations (admit, log dose) happen through the web frontend, not through the MCP card as currently implemented.

**Voice-triggered admit flow:** We did not verify a voice-triggered admit flow that refreshes this card. The `patient_case_id` field and tool-triggers-card-refresh mechanism described in the project concept were not implemented and tested end-to-end. Claiming this works would be inaccurate.

The card demonstrates the correct MCP integration point — a context-aware, reactively updating view of a Reboot state machine surfaced as an MCP UI — but the interactive layer (mutations from within the card, voice triggers) was not completed.

---

## 6. Evidence

The following placeholders should be replaced with actual output before submission:

**Concurrent admit test output**
```
[PASTE OUTPUT OF: PYTHONPATH=backend/api:backend/src python backend/src/test_concurrent_admit.py]
```
Expected: one `success=True`, one `success=False` with `bed_unavailable`, BedRegistry confirms winner.

**Duplicate dose_log deduplication**
```
[PASTE OUTPUT OF MANUAL REPRO: two identical log_dose RPCs with same idempotency key,
 showing dose_log length = 1 after both arrive]
```
No automated test exists for this; platform behavior only.

**Chaos-monkey workflow resume test output**
```
[PASTE OUTPUT OF: PYTHONPATH=api:backend/api:backend/src python backend/src/test_notify_workflow.py]
```
Expected: Part 1 PASS (1 call), Part 2 PASS (still 1 call after restart), ALL TESTS PASSED.

**MCP card / voice flow screen recording**
```
[LINK TO SCREEN RECORDING — if recorded]
[OR: note that a live demo is available but was not recorded]
```
Note: the recording should show the reactive status pill updating after a successful admit, not interactive mutations from within the card (which were not implemented).
