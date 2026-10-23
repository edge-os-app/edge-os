/** Client types and calls for the connected financial journey (#58). Every call is owner-scoped on the server. */
import { request } from "./api";

/** Monad mainnet block explorer. The app trades on chain 143. */
export const MONAD_EXPLORER_BASE = "https://monadscan.com";

export interface Amount { asset_id: string; raw: string; decimals: number }

export interface FundingFlow {
  flow_id: string; agent_id: string; wallet_id: string; network_id: number; kind: string; asset: Amount;
  transport: string; recipient: string | null; state: "PENDING" | "CONFIRMED" | "FAILED" | "UNKNOWN";
  reference: string; transaction_reference: string | null; reason: string | null; created_at: string; updated_at: string;
}

/** One identity-bound holdings observation, kept apart from deposit history and reservations. */
export interface CurrentHoldings {
  state: "OBSERVED" | "UNAVAILABLE"; reason?: string | null; evidence_class: string | null; assets: Amount[];
  source?: string; finality?: string; observed_at?: string | null; wallet_address?: string | null;
  chain_id?: number | null; block_number?: number | null; missing?: string[];
}

/** The owner's view of the original transaction: identities and stages, never signed bytes. */
export interface OriginalTransaction {
  stage: string; reason?: string; reasons?: string[]; evidence_class: string; chain_id: number;
  wallet_address: string; candidate_hash?: string; transaction_hash?: string; nonce?: number | string;
  fee_envelope?: { gas_limit: number | string; max_fee_per_gas: number | string; max_priority_fee_per_gas: number | string };
  signing_request_id?: string; signed_bytes_sha256?: string; signed_bytes_length?: number;
  broadcast_returned?: string | null; stages: { stage: string; at: string }[];
  scope?: string; release_id?: string; release_sha256?: string; binding_sha256?: string; approved_minimum?: Amount;
  quote_observation?: { requested_at: string; received_at: string; elapsed_seconds: number; provider_created_at: string | null };
}

export interface FundingView {
  agent_id: string; wallet_id: string; network_id: number; provider_mode: "fixture" | "unavailable" | "controlled";
  declaration: { trading_asset: Amount; gas_asset: Amount } | null;
  flows: FundingFlow[];
  deposit_balances: { asset_class: string; asset_id: string; credited_deposits: Amount; pending_deposits: Amount }[];
  current_holdings: CurrentHoldings;
  allowances: { asset_id: string; decimals: number; approved_raw: string; consumed_raw: string; reserved_raw: string; remaining_raw: string }[];
}

export interface ReviewedTerms {
  terms_version: string; operating_purpose: "TRIAL" | "ONGOING"; trial_objective?: string | null;
  allocation: Amount[]; allowances: { name: string; amount: Amount }[]; attempt_budget: number;
  gas_budget: Amount | null; expiry: string; supported_actions: string[]; supported_assets: string[];
  supported_routes: string[]; route: { adapter: string; identity_state?: "KNOWN" | "UNKNOWN"; identity?: string | null };
  signer?: string; policy?: { policy_id: string; status: "UNQUALIFIED" | "UNKNOWN"; content_sha256: string };
  evidence: { status: string; source: string };
  stop_effects: string[];
}

export interface Activation {
  state: "FIXTURE_QUALIFIED" | "CONTROLLED_QUALIFIED" | "UNAVAILABLE"; reason: string | null; evidence_class: string | null;
  mandate_id?: string; policy_binding?: string; execution_revision_id?: string; expires_at?: string;
  scope?: string; release_sha256?: string; binding_sha256?: string;
}

export interface ControlledAction {
  scope: string; release_id: string; release_sha256: string; binding_sha256: string; evidence_class: string;
  input: Amount; minimum_output: Amount; recipient: string; entrypoint: string; method: string; allowance_raw: string;
  gas: { gas_limit: string; max_fee_per_gas: string; max_priority_fee_per_gas: string; budget_raw: string };
  fees: { fee_bps: number; referrer_fee_bps: number; fee_collector_address: string; referrer_address: string; is_in_token_fee: boolean };
  expires_at: string; signer_id: string; policy_id: string; policy_content_sha256: string;
  recurring: "UNAVAILABLE"; exit_execution: "UNAVAILABLE";
}

export interface ConsentReview {
  review_id: string; agent_id: string; wallet_id: string; network_id: string; strategy_id: string;
  strategy_revision_id: string; content_sha256: string; manifest_sha256: string; terms_hash: string;
  review_hash: string; status: "INACTIVE"; content: { terms: ReviewedTerms; unknowns?: string[]; [key: string]: unknown };
  created_at: string;
}

export interface ConsentAdoption {
  adoption_id: string; review_id: string; review_hash: string; consent_hash: string; status: "INACTIVE";
  content: Record<string, unknown>; created_at: string;
}

export interface AssetIdentity { asset_id: string; decimals: number }

export interface ConsentState {
  agent_id: string; adoptions: ConsentAdoption[]; reviews: ConsentReview[]; activation: Activation;
  assets: { quote: AssetIdentity; base: AssetIdentity; gas: AssetIdentity } | null;
  identity: Record<string, string> | null;
  provider_mode?: string; controlled_action?: ControlledAction | null;
}

export interface EvaluationJob {
  job_id: string; agent_id: string; request_key: string; decision_slot: string; state: string;
  publication_revision_id: string; execution_revision_id: string; consent_adoption_id: string;
  decision_id: string | null; action_id: string | null; outcome: string | null; reason: string | null; runs: number;
  created_at: string; updated_at: string;
  provenance?: { observations?: { evidence_class?: string; source?: string; collected_at?: string; finality?: string;
    delivery_profile_sha256?: string; warmup_buckets?: number; forward_observation?: { event?: string; observed_at?: string } } };
}

export interface Decision { decision_id: string; decision_at: string; status: string; operation: string | null; reasons: string[] }
export interface QueueEntry { queue_id: string; action_id: string; operation: string; position_id: string; state: string; blocking_reason: string | null }
export interface Position { position_id: string; asset_id: string; decimals: number; inventory_raw: string; quote_asset_id: string }

export interface AgentActions {
  agent_id: string; provider_mode: string; identity: Record<string, string>; jobs: EvaluationJob[];
  decisions: Decision[]; queue: QueueEntry[]; positions: Position[]; blocking_reason: string | null;
}

export interface ActionDetail {
  action_id: string; agent_id: string; wallet_id: string; network_id: string; operation: string; revision_id: string;
  mandate_id: string; policy_binding: string; payload_hash: string;
  payload: { quantity: Amount; input: { quote_input: Amount | null; expected_quote: Amount | null } };
  decision: Decision; queue: QueueEntry | null; admission: { status: string; reason: string | null }[];
  reservations: { scope: string; asset_id: string; decimals: number; raw: string; state: string }[];
  receipts: { outcome: string; breach: boolean; created_at: string; content: { actual_input?: Amount | null;
    actual_output?: Amount | null; actual_gas?: Amount | null; source_ref?: string; [key: string]: unknown } }[];
  attempts: { attempt_id: string; state: string; outcome: string | null; detail: string | null;
    content: { original_references?: Record<string, string | null>; original_transaction?: OriginalTransaction | null } }[];
  refusal: WalletPolicyRefusal | null;
  recovery: { state: string; blocking_reason: string | null } | null;
}

export interface Stop { stop_id: string; scope: string; mode: string; trigger: string; position_id: string | null; created_at: string }
export interface Removal { request_id: string; state: string; reason: string; requested_at: string; updated_at: string; evidenced_signer: string | null }
/** The newest attempt's definite refusal, when the API classifies one. */
export interface WalletPolicyRefusal { reason: string; message: string }

/** P27 LOCAL recurring operation: one explicit deployment per adopted consent and its durable projection. */
export interface RecurringDeployment {
  deployment_id: string; state: "ACTIVE" | "ENDED"; end_reason: string | null; request_key: string;
  activated_at: string; ended_at: string | null;
  identity: { agent_id: string; wallet_id: string; network_id: string; strategy_id: string; publication_revision_id: string;
    execution_revision_id: string; content_hash: string; manifest_hash: string; consent_adoption_id: string; consent_hash: string };
}

export interface RecurringOccurrence extends EvaluationJob {
  deployment_id: string | null;
  evaluation: { outcome: string; reason: string | null; decision_id: string | null; inputs_observed_at: string | null;
    inputs_collected_at: string | null; evaluated_at: string; evidence_class: string | null } | null;
  submission: { attempt_id: string; state: string; outcome: string | null; started_at: string; completed_at: string | null } | null;
}

export interface RecurringProjection {
  deployment: RecurringDeployment | null;
  producer?: { last_tick_at: string | null; cursor_slot: string | null; producer_silent: boolean; next_due_slot: string | null; no_next_reason: string | null;
    occurrences: number; missed_slots: number; missed_intervals: { from: string; to: string; count: number; reason: string; recorded_at: string }[] };
  occurrences?: RecurringOccurrence[]; pending_reconciliation?: string[]; stops?: string[]; removal?: string[];
  wait_reason?: string | null; read_at?: string;
}

const agentPath = (agentId: string) => `/v1/agents/${encodeURIComponent(agentId)}`;
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }).then((r) => r.body);

export const financial = {
  funding: (agentId: string) => request<FundingView>(`${agentPath(agentId)}/funding`).then((r) => r.body),
  declare: (agentId: string) => post<{ trading_asset: Amount; gas_asset: Amount }>(`${agentPath(agentId)}/funding/declaration`),
  prepareDeposit: (agentId: string, body: { asset_class: "TRADING" | "NATIVE_GAS"; raw: string; reference: string }) =>
    post<FundingFlow>(`${agentPath(agentId)}/funding/flows`, body),
  reconcileDeposits: (agentId: string) => post<{ results: unknown[] }>(`${agentPath(agentId)}/funding/reconcile`),
  consent: (agentId: string) => request<ConsentState>(`${agentPath(agentId)}/consent`).then((r) => r.body),
  review: (agentId: string, terms: ReviewedTerms) => post<ConsentReview>(`${agentPath(agentId)}/consent/review`, { terms }),
  adopt: (agentId: string, reviewId: string, reviewHash: string) =>
    post<ConsentAdoption & { activation: Activation }>(`${agentPath(agentId)}/consent/adopt`,
      { review_id: reviewId, expected_review_hash: reviewHash }),
  actions: (agentId: string) => request<AgentActions>(`${agentPath(agentId)}/actions`).then((r) => r.body),
  schedule: (agentId: string, requestKey: string) => post<EvaluationJob>(`${agentPath(agentId)}/actions`, { request_key: requestKey }),
  action: (actionId: string) => request<ActionDetail>(`/v1/actions/${encodeURIComponent(actionId)}`).then((r) => r.body),
  reconcileAction: (actionId: string) =>
    post<{ receipt_outcome: string; case_state: string; decision_status: string }>(`/v1/actions/${encodeURIComponent(actionId)}/reconcile`),
  stops: (agentId: string) => request<{ stops: Stop[] }>(`${agentPath(agentId)}/stops`).then((r) => r.body),
  stop: (agentId: string, mode: "STOP_NEW_ENTRIES" | "HALT_ALL_SWAPS") =>
    post<Stop>(`${agentPath(agentId)}/stops`, { mode, scope: "AGENT_WALLET_NETWORK" }),
  removals: (agentId: string) => request<{ removals: Removal[] }>(`${agentPath(agentId)}/removal`).then((r) => r.body),
  requestRemoval: (agentId: string, requestKey: string, reason: string) =>
    post<Removal>(`${agentPath(agentId)}/removal`, { request_key: requestKey, reason }),
  reconcileRemoval: (agentId: string) => post<{ state: string }>(`${agentPath(agentId)}/removal/reconcile`),
  deployment: (agentId: string) => request<RecurringProjection>(`${agentPath(agentId)}/deployment`).then((r) => r.body),
  activateDeployment: (agentId: string, requestKey: string, consentHash: string) =>
    post<RecurringDeployment>(`${agentPath(agentId)}/deployment`, { request_key: requestKey, expected_consent_hash: consentHash }),
  endDeployment: (agentId: string) => post<RecurringDeployment>(`${agentPath(agentId)}/deployment/end`),
};

/** Exact base units with their decimals, never a float. */
export function formatRaw(raw: string, decimals: number): string {
  if (!/^\d+$/.test(raw)) return raw;
  if (decimals === 0) return raw;
  const padded = raw.padStart(decimals + 1, "0");
  const whole = padded.slice(0, -decimals);
  const fraction = padded.slice(-decimals).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

/** A per-agent key kept until the server answers, so a lost reply repeats the same request instead of a new one. */
export function heldKey(scope: string, agentId: string): string {
  const storageKey = `edge-os:${scope}:${agentId}`;
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored) return stored;
  } catch { /* storage may be blocked; the server still treats a repeated key as the same request */ }
  const key = `ui-${crypto.randomUUID()}`;
  try { window.sessionStorage.setItem(storageKey, key); } catch { /* ignore */ }
  return key;
}

/** The held key, if any, without creating one. */
export function peekKey(scope: string, agentId: string): string | null {
  try { return window.sessionStorage.getItem(`edge-os:${scope}:${agentId}`); } catch { return null; }
}

export function releaseKey(scope: string, agentId: string): void {
  try { window.sessionStorage.removeItem(`edge-os:${scope}:${agentId}`); } catch { /* ignore */ }
}
