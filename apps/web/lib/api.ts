import type { Bundle, EffectRunBody, EffectRunResult, InvestigationProposal, InvestigationSaveResult,
  PublicationResult, RequestSummary, Sample, SpotReplayBody, SpotReplayRecord, WalletProviderInfo,
  WalletSetupPrepareBody, WalletSetupRecord } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, public detail: string, public findings: { path: string; detail: string }[] = []) {
    super(`${status} ${code}`);
  }
}

export type TokenSource = () => Promise<string | null>;

let tokenSource: TokenSource = async () => null;
let onUnauthorized: () => void = () => {};

/** Wire the single token function. Production wires Privy's getAccessToken. Nothing else supplies a token. */
export function setTokenSource(source: TokenSource): void { tokenSource = source; }
export function setUnauthorizedHandler(handler: () => void): void { onUnauthorized = handler; }

export function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
}

const REQUEST_TIMEOUT_MS = 30_000;
/** A call that waits for the interpreter can take longer than a read. */
export const INTERPRETER_TIMEOUT_MS = 120_000;

async function send(path: string, init: RequestInit, token: string | null, timeoutMs: number): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${apiBase()}${path}`, { ...init, headers, cache: "no-store", signal: controller.signal });
  } finally { clearTimeout(timer); }
}

export async function request<T>(path: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<{ status: number; body: T }> {
  let response: Response;
  try {
    response = await send(path, init, await tokenSource(), timeoutMs);
    if (response.status === 401) {
      const first = await response.clone().json().catch(() => ({}));
      if (first.code === "auth_expired") response = await send(path, init, await tokenSource(), timeoutMs);
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError(0, "timeout", "The service did not answer in time. Check the saved record before repeating a change.");
    throw new ApiError(0, "network_error", "The service could not be reached.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    const findings = Array.isArray(body.findings) ? body.findings : [];
    throw new ApiError(response.status, body.code ?? "error", findings[0]?.detail ?? "The request failed.", findings);
  }
  return { status: response.status, body: body as T };
}

// #58 recorded-history research. Every source is a SYNTHETIC recorded-response bundle; nothing calls a provider.
export interface HistoryMarket { network: string; pool_address: string; base_asset: string; quote_asset: string }
export interface HistorySource {
  source_id: string; title: string; evidence_class: string; content_label: string; profile_version: string;
  profile_sha256: string; market: HistoryMarket; window: { start: string; end: string }; history_provider: string;
  page_requests_recorded: number;
  transport: null | { history_provider: string; provider_version: string; corroboration_provider: string;
    corroboration_sample_size: number; provider_requests_needed: number; clients?: "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT" };
  /** False when this server has no composition for the source; a job on it is refused before any effect. */
  available?: boolean;
}
export interface TransportSummary {
  envio_pages_framed: number; client_calls: Record<string, number>; chain_id: number | null; chain_network: string | null;
  corroboration: { class: string; sample_size: number; population_size: number; mismatches: number };
  corroboration_reason: string | null; recorded_declarations: string[];
  /** Present only when the accepted P07 HTTP clients served the calls over the application's authored transport. */
  clients?: "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT"; client_classes?: Record<string, string>; transport_label?: string;
}
export interface HistoryRule {
  evaluation_id: string; trial_id: string; variant_id: string; price_expression: Record<string, unknown>;
  volume_expression: Record<string, unknown>; essential_inputs: ("price" | "quote_volume")[]; rule_source: "USER_ADOPTED";
}
export interface HistoryDeclarationContent {
  schema_version: string; original_request: string; declaration_state: string; outcome_labels_read: boolean;
  edge_spec: { hypothesis: string; claim: { status: string; text: string } };
  configuration: {
    source: { source_id: string; profile_sha256: string; evidence_class: string }; market: HistoryMarket;
    window: { start: string; end: string }; direction: string; resource_bounds: Record<string, number>;
    evaluation_plan: { evaluation_id: string; variant_id: string; partition_ids: string[] }[];
    partitions: { partition_id: string; role: string; start: string; end: string }[];
  };
  rule_map: { rules: HistoryRule[]; binding_state: string; control: string };
  frozen: { configuration_sha256: string; rule_map_sha256: string; source_profile_sha256: string; frozen_at: string };
}
export interface HistoryDeclaration {
  declaration: { record_id: string; schema_version: string; created_at: string; content: HistoryDeclarationContent };
  access_history: { event: string; provider_queries: number; outcome_labels_read: boolean }[];
}
export interface BudgetAmounts { provider_requests: number; compute_seconds: number }
export interface ResearchBudget {
  limits: BudgetAmounts; reserved: BudgetAmounts; consumed: BudgetAmounts; unknown_liability: BudgetAmounts;
  available: BudgetAmounts;
}
export interface ReportVariant {
  evaluation_id: string; variant_id: string; outcome: string; triggered_minus_control_mean: string | null;
  triggered_observed: number; control_observed: number;
}
export interface InvestigationReport {
  report_id: string; content_sha256: string; stored_hash_matches_content: boolean; created_at: string;
  content: {
    outcome: string; outcome_reasons: string[]; outcome_accessed: boolean; statistical_status: string;
    claims: Record<string, string>; variants: ReportVariant[]; contrary_findings: Record<string, string>[];
    protected_evaluations: { evaluation_id: string; role: string; state: string }[];
    protected_partitions: { partition_id: string; role: string; state: string }[]; dataset_id: string;
    source_id: string; evidence_class: string; content_label: string; dataset_verdict: { overall: string };
    rule_map_sha256: string; hypothesis: string; notice: string;
  };
}
export interface InvestigationJob {
  job_id: string; declaration_id: string; request_key: string; operation_id: string; state: string;
  terminal_reason: string | null; budget: Record<string, BudgetAmounts>; deadline_at: string;
  cancel_requested_at: string | null; created_at: string;
  events: { kind: string; attempt_id: string | null; created_at: string; content: Record<string, unknown> }[];
  dataset: null | { dataset_id: string; content_sha256: string; hashes_verified: Record<string, boolean>;
    summary: { source_id: string; status: string; stop_reason: string; verdict: { overall: string };
      binding_state: string; unavailable_states: string[]; provider_requests: Record<string, number> | null;
      provider_requests_state: string; evidence_class: string; content_label: string };
    transport: TransportSummary | null };
  report: InvestigationReport | null;
  kind?: "HISTORY_INVESTIGATION" | "NANSEN_REPORT";
  nansen_report?: NansenReportSummary | null;
}
// #58 RESEARCH-PORTS-LOCAL Nansen reports: AUTHORED replies replayed locally; never provider data.
export interface NansenSettlement {
  provider_requests: { state: string; measured: number; lost: number };
  nansen_credits: { state: string; measured: number; deducted: string | null; reserved_by_package: string };
}
export interface NansenReportSummary {
  report_id: string; content_sha256: string; answer_state: string; question: string; token_symbol: string;
  evidence_class: string; settlement: NansenSettlement;
  outcomes: { operation: string; status: string; stop_reason: string | null }[];
}
export interface NansenFinding { code: string; verdict: string; statement: string; source_refs: string[]; limitations: string[] }
export interface NansenReportRecord {
  report_id: string; job_id: string; content_sha256: string; hashes_verified: Record<string, boolean>; created_at: string;
  content: {
    evidence_class: string; transport_label: string; notice: string; request_sha256: string; report_sha256: string;
    settlement: NansenSettlement; outcomes: NansenReportSummary["outcomes"];
    report: { question: string; token_address: string; token_symbol: string; answer_state: string;
      window: { start_utc: string; end_utc: string }; findings: NansenFinding[];
      limitations: { claim: string; missing_dependency: string }[]; unknowns: string[];
      coverage: { attempts: number; pages: number; holder_rows: number; flow_buckets: number; expected_buckets: number;
        missing_buckets: number; incomplete_buckets: number; complete_seconds: number | null;
        pagination_is_last_page: boolean | null; stop_reason: string | null };
      source_hashes: string[] };
  };
}
export interface NansenReportBody {
  operation_id: string; request_key: string; token_address: string; token_symbol: string;
  window: { start_utc: string; end_utc: string }; operations: ("holders" | "flows")[];
  limits: { max_requests: number; max_pages: number; max_bytes: number; max_credits: string; per_page: number };
  deadline_seconds: number; compute_seconds: number;
}
export interface DatasetSummary {
  dataset_id: string; created_at: string; content_sha256: string; hashes_verified: Record<string, boolean>;
  quote_unit: string | null; source_id: string; evidence_class: string; content_label: string;
  profile_evidence_class: string; status: string; verdict: { overall: string }; binding_state: string;
  unavailable_states: string[]; market_binding: Record<string, unknown> | null; market_binding_id: string | null;
  window_start: string; window_end: string; declaration_id: string; job_id: string;
  readable_until: string;
  declared_rules: { evaluation_id: string; variant_id: string; price_expression: Record<string, unknown>;
    volume_expression: Record<string, unknown> }[];
}
export interface MarketAdoptionBody {
  idempotency_key: string; expected_interpretation_revision_id: string; expected_parent_revision_id: string | null;
  dataset_id: string; adoption: "ADOPT_DATASET_MARKET"; quote_unit: string; evaluation_id: string;
  exit_rule: Record<string, unknown>; sizing_amount: string;
  max_quote_notional: string;
}
export interface MarketAdoptionResult {
  adoption: { interpretation_revision_id: string; draft_id: string; dataset_id: string; declaration_id: string;
    market_binding_id: string; quote_unit: string; base_revision_id: string | null };
  replayed: boolean;
  bundle: Bundle;
}
/** A replay of one saved strategy revision on one of the owner's saved history datasets. */
export type HistorySpotReplayBody = Omit<SpotReplayBody, "dataset_fixture_id"> & { history_dataset_id: string };

export const api = {
  me: () => request<{ user_id: string }>("/v1/me").then((r) => r.body),
  interpreter: () => request<{ interpreter: { kind: string; id: string; notice: string }; samples: Sample[] }>("/v1/interpreter").then((r) => r.body),
  list: () => request<{ requests: RequestSummary[]; has_more: boolean }>("/v1/research/requests").then((r) => r.body),
  get: (id: string) => request<Bundle>(`/v1/research/requests/${id}`).then((r) => r.body),
  investigationProposal: (id: string) => request<InvestigationProposal>(`/v1/research/requests/${id}/investigation-proposal`).then((r) => r.body),
  investigations: (id: string) => request<{ declarations: InvestigationSaveResult["declaration"][]; access_history: InvestigationSaveResult["access_history"] }>(`/v1/research/requests/${id}/investigations`).then((r) => r.body),
  investigation: (id: string, declarationId: string) => request<InvestigationSaveResult>(`/v1/research/requests/${id}/investigations/${declarationId}`).then((r) => r.body),
  saveInvestigation: (id: string, body: unknown) => request<InvestigationSaveResult>(`/v1/research/requests/${id}/investigations`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  effectRuns: (id: string) => request<{ runs: EffectRunResult[] }>(`/v1/research/requests/${id}/effect-runs`).then((r) => r.body),
  effectRun: (id: string, runId: string) => request<EffectRunResult>(`/v1/research/requests/${id}/effect-runs/${runId}`).then((r) => r.body),
  adoptEffectRun: (id: string, declarationId: string, body: EffectRunBody) =>
    request<EffectRunResult>(`/v1/research/requests/${id}/investigations/${declarationId}/effect-runs`,
      { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  executeEffectRun: (id: string, runId: string, body: { operation_id: string; idempotency_key: string }) =>
    request<EffectRunResult>(`/v1/research/requests/${id}/effect-runs/${runId}/attempts`,
      { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  createSpotReplay: (body: SpotReplayBody | HistorySpotReplayBody) =>
    request<SpotReplayRecord>("/v1/spot-replays", { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  spotReplay: (id: string) => request<SpotReplayRecord>(`/v1/spot-replays/${id}`).then((r) => r.body),
  historySources: () => request<{ label: string; mode: string; sources: HistorySource[] }>("/v1/research/history-sources").then((r) => r.body),
  historyInvestigations: (id: string) =>
    request<{ declarations: HistoryDeclaration[] }>(`/v1/research/requests/${id}/history-investigations`).then((r) => r.body),
  historyInvestigation: (id: string, declarationId: string) =>
    request<HistoryDeclaration>(`/v1/research/requests/${id}/history-investigations/${declarationId}`).then((r) => r.body),
  saveHistoryInvestigation: (id: string, body: unknown) =>
    request<HistoryDeclaration>(`/v1/research/requests/${id}/history-investigations`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  investigationJobs: (id: string, declarationId: string) =>
    request<{ jobs: InvestigationJob[] }>(`/v1/research/requests/${id}/history-investigations/${declarationId}/jobs`).then((r) => r.body),
  startInvestigationJob: (id: string, declarationId: string, body: { operation_id: string; request_key: string }) =>
    request<InvestigationJob>(`/v1/research/requests/${id}/history-investigations/${declarationId}/jobs`,
      { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  investigationJob: (jobId: string) => request<InvestigationJob>(`/v1/research/investigation-jobs/${jobId}`).then((r) => r.body),
  cancelInvestigationJob: (jobId: string) =>
    request<InvestigationJob>(`/v1/research/investigation-jobs/${jobId}/cancel`, { method: "POST" }).then((r) => r.body),
  nansenReports: (id: string) =>
    request<{ jobs: InvestigationJob[] }>(`/v1/research/requests/${id}/nansen-reports`).then((r) => r.body),
  startNansenReport: (id: string, body: NansenReportBody) =>
    request<InvestigationJob>(`/v1/research/requests/${id}/nansen-reports`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  nansenReport: (reportId: string) => request<NansenReportRecord>(`/v1/research/nansen-reports/${reportId}`).then((r) => r.body),
  investigationReport: (reportId: string) =>
    request<InvestigationReport>(`/v1/research/investigation-reports/${reportId}`).then((r) => r.body),
  historyDatasets: () => request<{ datasets: DatasetSummary[] }>("/v1/research/history-datasets").then((r) => r.body),
  researchBudget: () => request<ResearchBudget>("/v1/research/budget").then((r) => r.body),
  adoptMarket: (id: string, body: MarketAdoptionBody) =>
    request<MarketAdoptionResult>(`/v1/research/requests/${id}/market-adoptions`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  submit: (body: unknown) => request<Bundle>("/v1/research/requests", { method: "POST", body: JSON.stringify(body) }, INTERPRETER_TIMEOUT_MS).then((r) => r.body),
  /** One listed choice, or the user's own words. The interpreter reads words, so that call can take longer. */
  answer: (id: string, body: { previous_revision_id: string; question_id: string } & ({ choice_id: string } | { answer_text: string })) =>
    request<Bundle>(`/v1/research/requests/${id}/clarifications`, { method: "POST", body: JSON.stringify(body) }, INTERPRETER_TIMEOUT_MS).then((r) => r.body),
  /** Explicit retry. It names the earlier attempt it follows and starts a separate attempt. */
  retryInterpretation: (id: string, retryOf: string | null) =>
    request<Bundle>(`/v1/research/requests/${id}/interpretation-retries`, { method: "POST", body: JSON.stringify({ retry_of: retryOf }) }, INTERPRETER_TIMEOUT_MS).then((r) => r.body),
  publish: (strategyId: string, body: unknown) =>
    request<PublicationResult>(`/v1/strategies/${strategyId}/revisions`, { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  revision: (strategyId: string, revisionId: string) =>
    request<{ revision_id: string; content_sha256: string; manifest_sha256: string; created_at: string; stored_hash_matches_content: boolean; stored_manifest_hash_matches_content: boolean }>(
      `/v1/strategies/${strategyId}/revisions/${revisionId}`).then((r) => r.body),
  operation: (id: string) => request<PublicationResult>(`/v1/operations/${id}`).then((r) => r.body),
  /** The active wallet-creation provider mode. Reports `unavailable` in any non-local configuration. */
  walletProvider: () => request<WalletProviderInfo>("/v1/wallet-setup/provider").then((r) => r.body),
  /** Owner-scoped wallet-setup reads and mutations. A missing setup is a 404 ApiError. */
  walletSetup: (agentId: string) =>
    request<WalletSetupRecord>(`/v1/wallet-setup/agents/${encodeURIComponent(agentId)}`).then((r) => r.body),
  prepareWalletSetup: (agentId: string, body: WalletSetupPrepareBody) =>
    request<WalletSetupRecord>(`/v1/wallet-setup/agents/${encodeURIComponent(agentId)}/prepare`,
      { method: "POST", body: JSON.stringify(body) }).then((r) => r.body),
  dispatchWalletSetup: (agentId: string) =>
    request<WalletSetupRecord>(`/v1/wallet-setup/agents/${encodeURIComponent(agentId)}/dispatch`,
      { method: "POST" }).then((r) => r.body),
  resumeWalletSetup: (agentId: string) =>
    request<WalletSetupRecord>(`/v1/wallet-setup/agents/${encodeURIComponent(agentId)}/resume`,
      { method: "POST" }).then((r) => r.body),
  cancelWalletSetup: (agentId: string) =>
    request<WalletSetupRecord>(`/v1/wallet-setup/agents/${encodeURIComponent(agentId)}/cancel`,
      { method: "POST" }).then((r) => r.body),
};
