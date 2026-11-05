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
  // `apps/api/src/edge_os_api/execution/connected_identity.py:45,245` approval labels.
  SYNTHETIC_FIXTURE_QUALIFICATION: "example data (not real)",
  PROVIDER_ACTUAL_QUALIFICATION: "real provider data",
};

/** `apps/api/src/edge_os_api/nansen_research/report_builder.py:189-211`. */
export const NANSEN_ANSWER_STATE: Record<string, string> = {
  SUPPORTED_OBSERVATIONS: "Answered from the observed data (this is not proof of an edge)",
  PARTIAL: "Partly answered",
  UNAVAILABLE: "Not answered: the data was not available",
};

/** `apps/api/src/edge_os_api/research/history_dataset.py:315-327` and the report builders. */
export const VERDICT: Record<string, string> = {
  QUALIFIED: "Qualified",
  SUPPORTED: "Supported by the returned records",
  LIMITED: "Limited",
  UNRESOLVED: "Unresolved",
  UNAVAILABLE: "Unavailable",
  UNKNOWN: "Unknown",
};

/** `apps/api/src/edge_os_api/funding/types.py:44`. */
export const FLOW_STATE: Record<string, string> = {
  REQUESTED: "Requested",
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

/** `apps/api/src/edge_os_api/accounts/views.py:175-181` record kinds. */
export const RECORD_KIND: Record<string, string> = {
  AGENT: "Agent",
  POSITION: "Position",
  ACTION: "Action",
  CAPITAL_FLOW: "Deposit or withdrawal",
  MONITORING: "Checks",
  EDGE_EVIDENCE: "Evidence",
  PERMISSION_SNAPSHOT: "Permission",
};

/** `apps/api/src/edge_os_api/research/history_payload_binding.py:12-13,62` payload binding states. */
export const PAYLOAD_BINDING_STATUS: Record<string, string> = {
  PASS: "The saved data matches the recorded delivery. It does not prove where the data came from.",
  MISMATCH: "The saved data does not match the recorded delivery. Do not use it as a market or a replay.",
  INCOMPLETE: "The delivery check did not finish. Do not use this data as a market or a replay.",
  NOT_REQUIRED: "This saved data needs no delivery check.",
};

/** A response without the field keeps the not-required display, as `payloadBindingText` does. */
export function deliveryCheckText(status: string | null | undefined): string {
  return plain(PAYLOAD_BINDING_STATUS, status ?? "NOT_REQUIRED",
    "The delivery check state is unknown. Do not use this data as a market or a replay.");
}

/** `apps/api/src/edge_os_api/research/history_dataset.py:320-328` limits of a saved dataset. */
export const DATASET_LIMIT: Record<string, string> = {
  SOURCE_UNAVAILABLE: "the source was unavailable",
  PARTIAL_COVERAGE: "coverage is partial",
  VERDICT_LIMITED: "the verdict is limited",
  VERDICT_UNRESOLVED: "the verdict is unresolved",
};

/** `apps/api/src/edge_os_api/recovery/types.py:66` (operation) — this build uses ENTRY and EXIT. */
export const OPERATION: Record<string, string> = {
  ENTRY: "Entry",
  ADDITION: "Addition",
  EXIT: "Exit",
};

/** `apps/api/src/edge_os_api/execution/models.py:36` (decision states). */
export const DECISION_STATUS: Record<string, string> = {
  SIGNAL: "Signal",
  NO_SIGNAL: "No signal",
  INELIGIBLE: "Not eligible",
};

/** `apps/api/src/edge_os_api/admission/models.py:70` (action status). */
export const ADMISSION_STATUS: Record<string, string> = {
  PROPOSED: "Proposed",
  ADMITTED: "Allowed",
  DENIED: "Refused",
  CANCELLED: "Cancelled",
  CONFIRMED: "Confirmed",
  REVERTED: "Reverted",
  SUBMISSION_UNKNOWN: "Outcome unknown",
  BREACHED: "Breached",
};

/** `apps/api/src/edge_os_api/execution/original_transaction.py:1118` (receipt outcomes). */
export const RECEIPT_OUTCOME: Record<string, string> = {
  CONFIRMED: "Confirmed",
  REVERTED: "Reverted",
  UNKNOWN: "Unknown",
  PREBROADCAST_DENIED: "Refused before sending",
  SUBMISSION_UNKNOWN: "Outcome unknown",
};

/** `apps/api/src/edge_os_api/recovery/models.py:83` (recovery case states). */
export const RECOVERY_STATE: Record<string, string> = {
  OPEN: "Open",
  CONFIRMED: "Confirmed",
  REVERTED: "Reverted",
  DENIED_UNSENT: "Refused, not sent",
  UNKNOWN: "Unknown",
  BREACHED: "Breached",
  RECONCILE_MISMATCH: "Reconciliation mismatch",
  DISCREPANCY: "Discrepancy",
  NO_ADMISSION_DECISION: "No admission decision",
  NO_SUBMISSION_ATTEMPT: "No submission attempt",
  NOT_OPENED: "Not opened",
};

/** `apps/api/src/edge_os_api/admission/models.py:125` (reservation states). */
export const RESERVATION_STATE: Record<string, string> = {
  RESERVED: "Reserved",
  CONSUMED: "Used",
  RELEASED: "Released",
};

/** `apps/api/src/edge_os_api/stops/models.py:37` (stop modes). */
export const STOP_MODE: Record<string, string> = {
  STOP_NEW_ENTRIES: "Stop new entries",
  HALT_ALL_SWAPS: "Halt all swaps",
};

/** `apps/api/src/edge_os_api/stops/models.py:36` stop scopes. */
export const STOP_SCOPE: Record<string, string> = {
  POSITION: "This position",
  AGENT_WALLET_NETWORK: "This agent's wallet and network",
};

/** `apps/api/src/edge_os_api/core/request_schemas.py:204` (partition roles). */
export const PARTITION_ROLE: Record<string, string> = {
  DESCRIPTIVE: "Descriptive",
  TRAINING: "Training",
  VALIDATION: "Validation",
  HOLDOUT: "Holdout",
};

/** `apps/api/src/edge_os_api/core/request_schemas.py:230` (direction). */
export const DIRECTION: Record<string, string> = {
  DESCRIPTIVE: "Describe only",
  OUTPERFORM: "Triggered decisions outperform",
  UNDERPERFORM: "Triggered decisions underperform",
};

/** `apps/api/src/edge_os_api/research/comparison_runs.py:553-572,622` (report outcomes). */
export const REPORT_OUTCOME: Record<string, string> = {
  SUPPORTED: "Supported",
  LIMITED: "Limited",
  CONTRADICTORY: "Contradictory",
  UNRESOLVED: "Unresolved",
  UNAVAILABLE: "Unavailable",
  UNSUPPORTED: "Not supported",
  SOURCE_LOSS: "Source lost",
  LIMITED_DATA: "Limited data",
  DESCRIBED: "Described",
  INSUFFICIENT_DATA: "Not enough data",
  FAILED: "Failed",
  UNKNOWN: "Unknown",
};

/** `apps/api/src/edge_os_api/research/comparison_runs.py:553-554` (claims). */
export const CLAIM_STATUS: Record<string, string> = {
  NOT_CLAIMED: "not claimed",
  CLAIMED: "claimed",
  NONE: "none",
  NOT_GRANTED: "not granted",
  GRANTED: "granted",
  UNRESOLVED: "unresolved",
};

/** `apps/api/src/edge_os_api/research/nansen_reports.py:144-146` (saved settlement summary). */
export const SETTLEMENT_STATE: Record<string, string> = {
  KNOWN: "Known",
  UNKNOWN: "Unknown",
};

/** `apps/api/src/edge_os_api/execution/models.py:41` (attempt states). */
export const SUBMISSION_STATE: Record<string, string> = {
  IN_FLIGHT: "In progress",
  TERMINAL: "Finished",
  PENDING: "Pending",
  CONFIRMED: "Confirmed",
  REVERTED: "Reverted",
  UNKNOWN: "Unknown",
  FAILED: "Failed",
  SUBMISSION_UNKNOWN: "Outcome unknown",
};

/** `apps/api/src/edge_os_api/research/history_dataset.py:243-249,298-301` provider-use states. */
export const PROVIDER_USE: Record<string, string> = {
  MEASURED_CLIENT_CALLS: "measured from client calls",
  SUPPLIED_EVIDENCE: "supplied with the saved evidence",
  INVALID: "invalid",
  UNKNOWN: "Unknown",
};

/** `apps/api/src/edge_os_api/research/comparison_runs.py:553` statistical status values. */
export const STATISTICAL_STATUS: Record<string, string> = {
  UNRESOLVED: "unresolved",
  DESCRIPTIVE_ONLY: "descriptive only",
  ASSESSED: "assessed",
  NOT_ASSESSED: "not assessed",
};

/** `apps/api/src/edge_os_api/research/effect_comparison.py:290` statistical reasons. */
export const STATISTICAL_REASON: Record<string, string> = {
  STAT_Q01_PROFILE_NOT_QUALIFIED: "the data profile is not qualified",
};

/** `apps/api/src/edge_os_api/research/effect_comparison.py:219,232` extra volume comparison states. */
export const INCREMENTAL_VOLUME_STATUS: Record<string, string> = {
  NOT_DECLARED: "not declared",
  DESCRIPTIVE_ONLY: "descriptive only",
};

/** `apps/api/src/edge_os_api/execution/models.py:251` evaluation outcomes. */
export const EVALUATION_OUTCOME: Record<string, string> = {
  // `apps/api/src/edge_os_api/execution/worker.py:801` saves the action status when a cancel is refused.
  ...ADMISSION_STATUS,
  SIGNAL: "Signal",
  NO_SIGNAL: "No signal",
  INELIGIBLE: "Not eligible",
  UNAVAILABLE: "Unavailable",
  DENIED: "Denied",
  ADMISSION_DENIED: "Refused by admission",
  CONFIRMED: "Confirmed",
  REVERTED: "Reverted",
  SUBMITTED_CONFIRMED: "submitted confirmed",
  SUBMITTED_REVERTED: "submitted reverted",
  SUBMITTED_UNKNOWN: "submitted, outcome unknown",
  DENIED_UNSENT: "refused, not sent",
  // `apps/api/src/edge_os_api/execution/worker.py:633,706,806-815` outcomes saved for an unsent or queued action.
  INTENT_EXPIRED: "Expired, not sent",
  DEPLOYMENT_ENDED: "Operation ended, not sent",
  REVALIDATION_DENIED: "Refused by revalidation",
  SUBMISSION_NOT_OWNED: "Not owned",
  CLAIMED: "Claimed",
  BREACHED: "Breached",
  RECONCILE_MISMATCH: "Reconciliation mismatch",
};

/** `apps/api/src/edge_os_api/accounts/service_projection.py:91` permission_state values. */
export const PERMISSION_STATE: Record<string, string> = {
  NO_REMOVAL_REQUESTED: "No removal requested",
  REMOVAL_NOT_REQUESTED: "No removal requested",
  REMOVAL_REQUESTED: "Removal requested",
  REMOVAL_PENDING: "Removal pending",
  REMOVAL_UNKNOWN: "Removal unknown",
  REMOVAL_CONFIRMED: "Removal confirmed",
  REMOVAL_FAILED: "Removal failed",
};

/** `apps/api/src/edge_os_api/accounts/views.py:175-181` record statuses. */
export const RECORD_STATUS: Record<string, string> = {
  REQUESTED: "Requested", PENDING: "Pending", UNKNOWN: "Unknown", CONFIRMED: "Confirmed", FAILED: "Failed",
  RUNNING: "Running", STOPPED: "Stopped", STALE: "Stale", BLOCKED: "Blocked", OPEN: "Open", CLOSED: "Closed",
  PROPOSED: "Proposed", QUEUED: "Queued", SUBMITTED: "Submitted", REVERTED: "Reverted", DENIED: "Denied",
  CANCELLED: "Cancelled", SUBMISSION_UNKNOWN: "Outcome unknown", HYPOTHESIS: "Hypothesis",
  DESCRIPTIVE_ONLY: "Descriptive only", UNRESOLVED: "Unresolved", SUPPORTED: "Supported", CONFLICTED: "Conflicted",
  CURRENT: "Current", EARLIER: "Earlier", CHANGE_APPLIED: "Change applied", CHANGE_PENDING: "Change pending",
  REMOVED: "Removed", ACTIVE: "Active", ENDED: "Ended", NEVER_ACTIVE: "Never active",
};

/** `apps/api/src/edge_os_api/agent_health/snapshot.py:43-50` unknown input fields. */
export const HEALTH_FIELD: Record<string, string> = {
  native_gas_aggregate: "native gas total",
  dataset_qualification: "saved data approval",
  revision_edge_evidence: "evidence for this version",
  control_state_basis: "stop and removal basis",
  selected_completion_outcome: "chosen completion outcome",
  job_manifest_hash: "saved job manifest",
};

/** `apps/api/src/edge_os_api/agent_health/snapshot.py:213-224` warning kinds. */
export const HEALTH_WARNING_KIND: Record<string, string> = {
  ACCOUNT_RECOVERY_OPEN_OR_UNKNOWN: "not settled",
};

/** `apps/api/src/edge_os_api/nansen_research/models.py:74-94` (holder and flow query values). */
export const HOLDER_LABEL: Record<string, string> = {
  all_holders: "All holders",
  whale: "Whales",
  public_figure: "Public figures",
  smart_money: "Smart money",
  exchange: "Exchanges",
};
export const HOLDER_ORDER: Record<string, string> = {
  address: "address",
  token_amount: "token amount",
  ownership_percentage: "ownership percentage",
  value_usd: "USD value",
};
export const FLOW_LABEL: Record<string, string> = {
  top_100_holders: "top 100 holders",
  whale: "Whales",
  public_figure: "Public figures",
  smart_money: "Smart money",
  exchange: "Exchanges",
};
