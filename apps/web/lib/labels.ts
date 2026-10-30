/**
 * Plain labels for API codes shown in the web UI.
 *
 * Each table maps a code to a plain label only when the API source states the meaning.
 * Unknown codes use the caller's fallback. The raw code stays available for the panel's
 * Details control, so no value is lost.
 */

export function plain(table: Record<string, string>, code: string | null | undefined, fallback = "Unknown"): string {
  if (code === null || code === undefined || code === "") return fallback;
  return table[code] ?? fallback;
}

/** `apps/api/src/edge_os_api/core/request_schemas.py:428` and `core/research/released_source_runtime.py:46-47`. */
export const EVIDENCE_CLASS: Record<string, string> = {
  PROVIDER_ACTUAL: "real provider data",
  SYNTHETIC_FIXTURE: "example data (not real)",
  AUTHORED_RECORDING: "recorded example responses",
  RECORDED_RESPONSE: "recorded example responses",
  RECORDED_NATIVE_RESPONSE: "recorded example responses",
  AUTHORED_HTTP_RESPONSE: "recorded example responses",
  RELEASE_STAND_IN_RESPONSE: "recorded example responses",
  REAL_SOURCE: "real source data",
  PROVIDER_HISTORY: "provider history",
  PROVIDER_UNQUALIFIED: "unverified provider data",
};

/** `apps/api/src/edge_os_api/nansen_research/report_builder.py:189-211`. */
export const NANSEN_ANSWER_STATE: Record<string, string> = {
  SUPPORTED_OBSERVATIONS: "Answered from the observed data (this is not proof of an edge)",
  PARTIAL: "Partly answered",
  UNAVAILABLE: "Not answered: the data was not available",
};

/** Finding verdicts used by the Nansen and history report builders. */
export const VERDICT: Record<string, string> = {
  SUPPORTED: "Supported by the returned records",
  LIMITED: "Limited",
  UNRESOLVED: "Unresolved",
  UNAVAILABLE: "Unavailable",
  UNKNOWN: "Unknown",
};

/** `apps/api/src/edge_os_api/funding/types.py:44`. */
export const FLOW_STATE: Record<string, string> = {
  PENDING: "Pending",
  CONFIRMED: "Confirmed",
  FAILED: "Failed",
  UNKNOWN: "Unknown",
};

/** `apps/api/src/edge_os_api/funding/types.py:37`. */
export const FLOW_KIND: Record<string, string> = {
  DEPOSIT: "Deposit",
  WITHDRAWAL: "Withdrawal",
};

/** `apps/api/src/edge_os_api/wallet_setup/types.py:15`. */
export const SETUP_STATE: Record<string, string> = {
  REQUESTED: "Saved, not started",
  PENDING: "Creating",
  UNKNOWN: "Outcome unknown",
  CONFIRMED: "Wallet confirmed",
  FAILED: "Setup failed",
};

/** `apps/api/src/edge_os_api/wallet_setup/types.py:24`. */
export const CANCELLATION_INTENT: Record<string, string> = {
  NONE: "None",
  REQUESTED_BEFORE_DISPATCH: "Requested before start",
  REQUESTED_AFTER_DISPATCH: "Requested after start",
};

/** `apps/api/src/edge_os_api/consent/routes.py:87-91`. */
export const ACTIVATION_STATE: Record<string, string> = {
  FIXTURE_QUALIFIED: "Example qualification",
  CONTROLLED_QUALIFIED: "One controlled action qualified",
  UNAVAILABLE: "Unavailable",
};

/** `apps/api/src/edge_os_api/execution/models.py:199` (evaluation job states). */
export const ACTION_JOB_STATE: Record<string, string> = {
  QUEUED: "Saved",
  DECIDED: "Decided",
  ENQUEUED: "Accepted for checks",
  SUBMITTED: "Outcome not settled",
  COMPLETED: "Finished",
  UNAVAILABLE: "Unavailable",
};

/** `apps/api/src/edge_os_api/execution/models.py:38-39` (queue states). */
export const QUEUE_STATE: Record<string, string> = {
  QUEUED: "Waiting",
  CLAIMED: "Claimed",
  REVALIDATION_DENIED: "Refused by revalidation",
  ADMISSION_DENIED: "Refused by admission",
  BREACHED: "Breached",
  RECONCILE_MISMATCH: "Reconciliation mismatch",
  SUBMISSION_NOT_OWNED: "Not owned",
  SUBMITTED_CONFIRMED: "Sent and confirmed",
  SUBMITTED_REVERTED: "Sent and reverted",
  SUBMITTED_UNKNOWN: "Sent, outcome unknown",
  DENIED_UNSENT: "Refused, not sent",
};

/** `apps/api/src/edge_os_api/revocation/types.py:26`. */
export const REMOVAL_STATE: Record<string, string> = {
  NOT_REQUESTED: "Not requested",
  REQUESTED: "Requested",
  PENDING: "Pending",
  UNKNOWN: "Unknown",
  CONFIRMED: "Confirmed",
  FAILED: "Failed",
};

/** `apps/api/src/edge_os_api/accounts/views.py` record kinds. */
export const RECORD_KIND: Record<string, string> = {
  AGENT: "Agent",
  POSITION: "Position",
  ACTION: "Action",
  CAPITAL_FLOW: "Deposit or withdrawal",
  MONITORING: "Checks",
  EDGE_EVIDENCE: "Evidence",
  PERMISSION_SNAPSHOT: "Permission",
};

/** `apps/web/lib/types.ts` payload binding states. */
export const PAYLOAD_BINDING_STATUS: Record<string, string> = {
  PASS: "matches",
  MISMATCH: "does not match",
  INCOMPLETE: "is not complete",
  NOT_REQUIRED: "is not required",
};
