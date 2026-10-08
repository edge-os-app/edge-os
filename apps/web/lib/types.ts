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
  kind: "CHOICE" | "ADOPT";
  text: string;
  field_name?: string;
  options: QuestionOption[];
  items?: { field_name: string; label: string; summary: string; origin: string; question: string }[];
}

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
  drafts: Envelope<{ draft_id: string; strategy_id: string; source_syntax: Strategy; interpretation_revision_id: string }>[];
  publications: Envelope<Record<string, unknown>>[];
  revisions: RevisionSummary[];
  head: {
    interpretation_revision_id: string | null;
    outcome: OutcomeName | null;
    questions: Question[];
    draft_id: string | null;
    strategy_id: string | null;
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
