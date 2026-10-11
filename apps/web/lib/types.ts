export type Job = "COMPARE" | "INVESTIGATE_EFFECT" | "CREATE_STRATEGY" | "SIMULATE" | "OBSERVE_FORWARD" | "REQUEST_LIVE";
export type InputClass = "CONCRETE_THESIS" | "LOOSE_INTUITION" | "BOUNDED_NO_THESIS";
export type OutcomeName =
  | "NEEDS_CLARIFICATION" | "UNSUPPORTED" | "UNRESOLVED" | "INVALID_INPUT" | "COMPILED" | "CONFLICTED" | "PUBLISHED";

export interface Envelope<T> {
  schema_version: string;
  record_type: string;
  record_id: string;
  owner_id: string;
  operation_id: string;
  created_at: string;
  content: T;
}

export interface FieldEvidence {
  field_name: string;
  state: "KNOWN" | "MISSING" | "CONFLICTING";
  origin: "USER_STATED" | "USER_CONFIRMED" | "APPLICATION_CONFIGURED" | "AGENT_PROPOSED";
  source_ref: string;
  interpretation_revision: string;
  evidence_status: string;
  value?: unknown;
  adoption?: "ADOPTED" | "PENDING";
  /** Present when state is CONFLICTING: each statement with the words it came from. */
  conflicts?: { value: unknown; source_ref: string }[];
}

export interface Intake {
  original_request: string;
  restrictions: string[];
  requested_job: Job;
  input_class: InputClass;
  declared_market?: { network: string; base_asset: string; quote_asset: string };
}

export interface Interpretation {
  intake_record_id: string;
  interpretation_revision_id: string;
  input_class: InputClass;
  requested_job: Job;
  field_evidence: FieldEvidence[];
  clarification_history: Clarification[];
  preserved_restrictions: string[];
  meaning_status: string;
  syntax_status: string;
  evidence_readiness: string;
}

export interface Clarification {
  previous_revision_id: string;
  question_id: string;
  question: string;
  answer_ref: string;
  changed_fields: string[];
  preserved_restrictions: string[];
  resulting_revision_id: string;
}

export interface Finding { code: string; path: string; detail: string }

export interface Outcome {
  operation_id: string;
  stage: string;
  outcome: OutcomeName;
  code: string;
  findings: Finding[];
  retry: string;
  intake_record_id: string | null;
}

export interface QuestionOption { id: string; label: string }
export interface Question {
  question_id: string;
  /** CHOICE: listed options, or the user's own words. TEXT: the user's own words only. ADOPT: one bundled review. */
  kind: "CHOICE" | "ADOPT" | "TEXT";
  text: string;
  field_name?: string;
  options: QuestionOption[];
  items?: { field_name: string; label: string; summary: string; origin: string; question: string; value?: unknown }[];
}

export type AttemptStatus = "STARTED" | "COMPLETED" | "TRUNCATED" | "PROVIDER_FAILED" | "TIMED_OUT" | "INTERRUPTED" | "UNKNOWN";
export interface AttemptUsage { source: "PROVIDER_REPORTED" | "UNKNOWN"; input_tokens: number | null; output_tokens: number | null; total_tokens: number | null }

/** One recorded interpreter attempt. It holds structured values and hashes, never the generated text. */
export interface Attempt {
  attempt_id: string;
  sequence: number;
  retry_of: string | null;
  purpose: "INTERPRET" | "FOLLOW_UP";
  status: AttemptStatus;
  completion: "COMPLETE" | "TRUNCATED" | "NONE" | "UNKNOWN";
  started_at: string;
  finished_at: string | null;
  latency_ms: number | null;
  usage: AttemptUsage;
  request_count: number | null;
  response_sha256: string | null;
  parse_result: string | null;
  error_class: string | null;
  revision_id: string | null;
  identity: {
    prompt_version: string; system_prompt_sha256: string; task_sha256: string; response_shape_sha256: string;
    manifest_sha256: string; config_sha256: string; runtime_label: string; model: string | null; route: string | null;
    hermes_commit: string | null; answer_ref: string | null; previous_revision_id: string | null;
  };
}

/** A result that arrived after its attempt was closed as unknown. Evidence only: it never becomes a revision. */
export interface LateResult {
  observation_id: string;
  attempt_id: string;
  observed_at: string;
  status: string;
  response_sha256: string | null;
  authoritative: false;
  usage: AttemptUsage;
}

export interface RetryState { allowed: boolean; retry_of: string | null; reason: string | null }
export interface ReplyState { state: "REJECTED" | "FAILED" | "UNCERTAIN" | "PENDING_SAVE" | "UNFINISHED"; reason_code: string | null; attempt_id: string }

export interface RevisionSummary {
  revision_id: string;
  strategy_id: string;
  parent_revision_id: string | null;
  publication_id: string;
  operation_id: string;
  content_sha256: string;
  manifest_sha256: string;
  created_at: string;
}

export interface Bundle {
  interpreter: { kind: string; id: string; notice: string };
  intake: Envelope<Intake>;
  interpretations: Envelope<Interpretation>[];
  clarifications: Envelope<Clarification>[];
  outcomes: { interpretation_revision_id: string | null; record: Envelope<Outcome> }[];
  attempts: Attempt[];
  late_results: LateResult[];
  drafts: Envelope<{ draft_id: string; strategy_id: string; source_syntax: Strategy; interpretation_revision_id: string }>[];
  publications: Envelope<Record<string, unknown>>[];
  revisions: RevisionSummary[];
  head: {
    interpretation_revision_id: string | null;
    outcome: OutcomeName | null;
    questions: Question[];
    draft_id: string | null;
    strategy_id: string | null;
    retry: RetryState;
    reply: ReplyState | null;
  };
}

export type Expression = { op: string; [key: string]: unknown };
export interface Strategy {
  strategy_id: string;
  domain: string;
  entry: Expression;
  exit: Expression;
  invalidation: Expression | { state: string; source_ref: string };
  sizing: { kind: string; amount: string; unit: string };
  cost_assumptions: { fee_rate: string; slippage_rate: string; source_ref: string };
  risk_limits: { max_quote_notional: string; max_open_positions: number };
  action_scope: string[];
  execution_permission: { state: string; mandate_ref: string | null };
  warmup_buckets: number;
  decision_interval_seconds: number;
  data_inputs: string[];
  additions: boolean;
  partial_exits: boolean;
  market: { network: string };
}

export interface RequestSummary {
  intake_record_id: string;
  created_at: string;
  original_request: string;
  requested_job: Job;
  input_class: InputClass;
  outcome: OutcomeName | null;
  published: boolean;
  /** Present when the interpreter is Hermes: the stored facts about the latest attempt (see `readingOf`). */
  reading?: import("./interpretation").ReadingFacts;
  /** The first finding code of the latest saved outcome, when there is one. */
  outcome_code?: string | null;
}

export interface InvestigationHorizon { value: number; unit: "SECONDS" | "MINUTES" | "HOURS" | "DAYS" }
export interface InvestigationPartition {
  partition_id: string;
  role: "DESCRIPTIVE" | "TRAINING" | "VALIDATION" | "HOLDOUT";
  start: string;
  end: string;
}
export interface InvestigationEvaluation {
  evaluation_id: string;
  trial_id: string;
  variant_id: string;
  horizon: InvestigationHorizon;
  partition_ids: string[];
}

export interface InvestigationConfiguration {
  question: string;
  pool_binding: { profile_id: string; qualification: "UNQUALIFIED_FIXTURE"; limitations: string[] };
  variants: { variant_id: string; hypothesis: string }[];
  direction: "OUTPERFORM" | "UNDERPERFORM" | "DESCRIPTIVE";
  horizons: InvestigationHorizon[];
  sources: string[];
  candidate_limit: number;
  parameter_limit: number;
  compute_limit: { max_evaluations: number; max_runtime_seconds: number; max_cost_usd: "0" };
  period: { start: string; end: string };
  partitions: InvestigationPartition[];
  permitted_access: "FIXTURE_ONLY"[];
  stopping_rule: string;
  evaluation_plan: InvestigationEvaluation[];
  budget_version: "p08-research-budget/2";
  optional_tools: { creator_history: "UNAVAILABLE" | "NOT_REQUIRED"; wallet_pnl: "UNAVAILABLE" | "NOT_REQUIRED"; social_signals: "UNAVAILABLE" | "NOT_REQUIRED" };
}

export interface InvestigationEdgeSpec {
  edge_id: string;
  version: number;
  parent_declaration_id: string | null;
  hypothesis: string;
  claim: { status: "HYPOTHESIS" | "DESCRIPTIVE_ONLY"; text: string };
  falsification: { status: "DECLARED" | "DESCRIPTIVE_ONLY"; criteria: string };
  alternatives: string[];
  unknowns: string[];
}

export interface FieldAdoption {
  origin: "USER_STATED" | "USER_CONFIRMED" | "APPLICATION_CONFIGURED" | "AGENT_PROPOSED";
  source_ref: string;
  adoption: "PENDING" | "ADOPTED";
}

export interface InvestigationProposal {
  schema_version: "p08.investigation-declaration/2";
  proposal_version: string;
  interpretation_revision_id: string | null;
  request_record_id: string;
  edge_spec: InvestigationEdgeSpec;
  configuration: InvestigationConfiguration;
  adopted_fields: string[];
  field_origins: Record<string, FieldAdoption>;
  trial_ids: string[];
  evaluation_ids: string[];
  notice: string;
}

export interface InvestigationEnvelope {
  schema_version: "p08.investigation-declaration/2";
  record_type: "InvestigationDeclaration";
  record_id: string;
  owner_id: string;
  operation_id: string;
  created_at: string;
  content: {
    original_request: string;
    restrictions: string[];
    input_class: InputClass;
    requested_job: Job;
    interpretation_revision_id: string | null;
    edge_spec: InvestigationEdgeSpec;
    configuration: InvestigationConfiguration;
    adopted_fields: string[];
    field_origins: Record<string, Omit<FieldAdoption, "adoption"> & { adoption: "ADOPTED" }>;
    trial_ids: string[];
    evaluation_ids: string[];
    declaration_state: "PRE_OUTCOME_DECLARED";
    outcome_labels_read: false;
  };
}

export interface InvestigationAccessEvent {
  event_id: string;
  declaration_id: string;
  created_at: string;
  schema_version: "p08.investigation-access/1";
  event: "DECLARATION_SAVED";
  outcome_labels_read: false;
  provider_queries: 0;
  study_started: false;
}

export interface InvestigationSaveResult {
  declaration: InvestigationEnvelope;
  access_history: InvestigationAccessEvent[];
  study_started: false;
  idempotent_replay: boolean;
}

export interface EffectRunBinding {
  evaluation_id: string;
  trial_id: string;
  variant_id: string;
  price_expression: Expression;
  volume_expression: Expression;
  essential_inputs: ("price" | "quote_volume")[];
}

export interface EffectRunBody {
  operation_id: string;
  idempotency_key: string;
  fixture_id: "synthetic-effect-comparison/1";
  adoption: "ADOPT";
  schedule: { version: "p09.decision-clock/1"; start: string; end: string; interval_seconds: number };
  bindings: EffectRunBinding[];
  incremental_volume_declared: boolean;
}

export interface EffectRunEnvelope {
  schema_version: "p09.effect-run-declaration/1";
  record_type: "EffectRunDeclaration";
  record_id: string;
  owner_id: string;
  p08_declaration_id: string;
  created_at: string;
  content: Record<string, unknown>;
}

export interface EffectReportEnvelope {
  schema_version: "p09.effect-report/1";
  record_type: "EffectReport";
  record_id: string;
  owner_id: string;
  created_at: string;
  content: Record<string, any>;
}

export interface EffectRunEvent {
  event_id: string;
  sequence: number;
  created_at: string;
  content: Record<string, unknown>;
}

export interface EffectRunResult {
  run: EffectRunEnvelope;
  events: EffectRunEvent[];
  report: EffectReportEnvelope | null;
}

export interface Sample {
  scenario_id: string;
  label: string;
  text: string;
  input_class: InputClass;
  requested_job: Job;
  restrictions: string[];
  declared_market: { network: string; base_asset: string; quote_asset: string } | null;
}

export interface PublicationResult {
  operation_id: string;
  publication_id: string;
  revision_id: string;
  content_sha256: string;
  manifest_sha256: string;
  created_at: string;
  outcome: string;
}

export interface SpotReplayDependency {
  series: "price" | "quote_volume";
  offset_buckets: number;
}

export interface SpotReplayBody {
  idempotency_key: string;
  strategy_id: string;
  strategy_revision_id: string;
  dataset_fixture_id: "p13.wc01/1";
  run_configuration_id: string;
  window_start: string;
  window_end: string;
  initial_cash_quote: string;
  initial_base_amount: string;
  initial_basis_quote: string;
  essential_fields: {
    entry: { state: "BOUND" | "UNBOUND"; essential_dependencies?: SpotReplayDependency[] };
    exit: { state: "BOUND" | "UNBOUND"; essential_dependencies?: SpotReplayDependency[] };
  };
}

export interface SpotReplayInputSnapshot {
  profile_version: string;
  strategy_revision_id: string;
  strategy_id: string;
  strategy_sha256: string;
  strategy: {
    sizing: { amount: string; unit: string };
    warmup_buckets: number;
    cost_assumptions: { fee_rate: string; slippage_rate: string; source_ref: string };
  };
  run_configuration_id: string;
  dataset_fixture_id: string;
  dataset_revision_id: string;
  dataset_qualification: string;
  evidence_class: string;
  window_start: string;
  window_end: string;
  initial_cash_quote: string;
  initial_base_amount: string;
  initial_basis_quote: string;
  essential_evidence: {
    fields: Record<"entry" | "exit", {
      state: "BOUND" | "UNBOUND";
      essential_dependencies?: SpotReplayDependency[] | null;
    }>;
  };
}

export type WalletSetupState = "REQUESTED" | "PENDING" | "UNKNOWN" | "CONFIRMED" | "FAILED";
export type WalletSetupCancellationIntent = "NONE" | "REQUESTED_BEFORE_DISPATCH" | "REQUESTED_AFTER_DISPATCH";

/** One durable agent wallet setup. Local fixture data in this build; never real wallet evidence. */
export interface WalletSetupRecord {
  setup_id: string;
  owner_id: string;
  agent_id: string;
  network_id: number;
  strategy_id: string;
  strategy_revision_id: string;
  content_sha256: string;
  manifest_sha256: string;
  state: WalletSetupState;
  cancellation_intent: WalletSetupCancellationIntent;
  creation_dispatched: boolean;
  wallet_id: string | null;
  reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface WalletSetupPrepareBody {
  network_id: 143 | 10143;
  strategy_id: string;
  strategy_revision_id: string;
  request_key: string;
}

export interface SpotReplayRecord {
  schema_version: "p13.spot-replay-run/1";
  record_type: "SpotReplayRun";
  replay_id: string;
  created_at: string;
  content_sha256: string;
  content: {
    owner_id: string;
    strategy_revision_id: string;
    dataset_fixture_id: string;
    run_configuration_id: string;
    inputs: SpotReplayInputSnapshot;
    result: {
      status: "COMPLETE" | "UNAVAILABLE";
      reason?: { code: string; path: string; detail: string };
      evidence_class: "SYNTHETIC_FIXTURE";
      repeatability_id: string | null;
      samples: Record<string, unknown>[];
      events: Record<string, unknown>[];
      trades: Record<string, unknown>[];
      metrics: Record<string, string | number | null>;
      metric_statuses: Record<string, string>;
      metric_reasons: Record<string, string[]>;
      open_position: Record<string, unknown> | null;
    };
    notice: string;
  };
}
