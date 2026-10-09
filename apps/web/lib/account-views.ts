import { request } from "./api";

export type RecordKind = "AGENT" | "POSITION" | "ACTION" | "CAPITAL_FLOW" | "MONITORING" | "EDGE_EVIDENCE";

export interface AssetAmount {
  asset_id: string;
  raw: string;
  decimals: number;
}

export interface ValueState {
  state: "KNOWN" | "UNKNOWN";
  amount?: AssetAmount;
}

export interface AccountViewContent {
  owner_id: string;
  evidence_class: "SYNTHETIC_AUTHORED";
  record_kind: RecordKind;
  agent_id: string;
  wallet_id?: string | null;
  network_id?: string | null;
  asset_id?: string | null;
  position_id?: string | null;
  strategy_revision?: string | null;
  mandate_id?: string | null;
  action_id?: string | null;
  flow_id?: string | null;
  status: string;
  updated_at: string;
  quantity?: AssetAmount | null;
  wallet_balance?: AssetAmount | null;
  available_balance?: AssetAmount | null;
  reserved_amount?: AssetAmount | null;
  remaining_authority?: AssetAmount | null;
  native_gas?: AssetAmount | null;
  gas?: AssetAmount | null;
  basis?: ValueState | null;
  realized?: ValueState | null;
  unrealized?: ValueState | null;
  mark?: ValueState | null;
  position_state?: "OPEN" | "CLOSED" | null;
  health?: string | null;
  permission_state?: string | null;
  flow_kind?: "DEPOSIT" | "WITHDRAWAL" | "TRANSFER_IN" | "TRANSFER_OUT" | null;
  included_in_realized_result?: boolean | null;
  reason?: string | null;
  evaluation_attempts?: number | null;
  evaluation_completions?: number | null;
  input_updated_at?: string | null;
  next_work?: string | null;
  blocking_reason?: string | null;
  pending_reconciliation?: boolean | null;
  edge_revision?: string | null;
  edge_evidence_status?: string | null;
}

export interface AccountViewRecord {
  schema_version?: string;
  record_type?: string;
  record_id: string;
  owner_id: string;
  operation_id?: string;
  created_at?: string;
  content: AccountViewContent;
}

export interface PositionFilters {
  agent_id?: string;
  wallet_id?: string;
  asset_id?: string;
  strategy_revision?: string;
}

export interface ContextEntry {
  context_id: string;
  kind: "PREFERENCE" | "CORRECTION" | "LESSON";
  status: "ADOPTED" | "SUGGESTED";
  text: string;
  source_refs: string[];
}

export interface AgentContextRecord {
  owner_id: string;
  agent_id: string;
  memory_version: number;
  state: "ACTIVE" | "DISABLED" | "CLEARED";
  entries: ContextEntry[];
}

export function formatAmount(amount: AssetAmount): string {
  if (!/^(0|[1-9][0-9]*)$/.test(amount.raw) || !Number.isInteger(amount.decimals) || amount.decimals < 0 || amount.decimals > 255) return "Unknown";
  const digits = BigInt(amount.raw).toString();
  if (amount.decimals === 0) return digits;
  const padded = digits.padStart(amount.decimals + 1, "0");
  const whole = padded.slice(0, -amount.decimals);
  const fraction = padded.slice(-amount.decimals).replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

export function formatValue(value?: ValueState | null): string {
  return value?.state === "KNOWN" && value.amount ? formatAmount(value.amount) : "Unknown";
}

export function filterPositions(records: AccountViewRecord[], filters: PositionFilters): AccountViewRecord[] {
  return records.filter(({ content }) => content.record_kind === "POSITION"
    && (!filters.agent_id || content.agent_id === filters.agent_id)
    && (!filters.wallet_id || content.wallet_id === filters.wallet_id)
    && (!filters.asset_id || content.asset_id === filters.asset_id)
    && (!filters.strategy_revision || content.strategy_revision === filters.strategy_revision));
}

export function actionsForPosition(records: AccountViewRecord[], position: AccountViewRecord): AccountViewRecord[] {
  const target = position.content;
  if (target.record_kind !== "POSITION") return [];
  return records.filter(({ owner_id, content }) => content.record_kind === "ACTION"
    && owner_id === position.owner_id
    && content.agent_id === target.agent_id
    && content.wallet_id === target.wallet_id
    && content.network_id === target.network_id
    && content.asset_id === target.asset_id
    && content.position_id === target.position_id
    && content.strategy_revision === target.strategy_revision
    && content.mandate_id === target.mandate_id);
}

export interface AccountViewPage {
  records: AccountViewRecord[];
  next_offset: number | null;
}

export async function getAccountView(recordId: string): Promise<AccountViewRecord> {
  return request<AccountViewRecord>(`/v1/account-views/${encodeURIComponent(recordId)}`).then((result) => result.body);
}

export async function loadAccountViews(filters: PositionFilters = {}, offset = 0): Promise<AccountViewPage> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value);
  query.set("limit", "100");
  query.set("offset", String(offset));
  const suffix = query.size ? `?${query}` : "";
  return request<AccountViewPage>(`/v1/account-views${suffix}`).then((result) => result.body);
}

const contextPath = (agentId: string) => `/v1/agents/${encodeURIComponent(agentId)}/context`;

export const agentContextApi = {
  get: (agentId: string) => request<AgentContextRecord>(contextPath(agentId)).then((result) => result.body),
  correct: (agentId: string, expected_version: number, context_id: string, replacement: string) =>
    request<AgentContextRecord>(`${contextPath(agentId)}/corrections`, {
      method: "POST", body: JSON.stringify({ expected_version, context_id, replacement }),
    }).then((result) => result.body),
  adopt: (agentId: string, expected_version: number, context_id: string) =>
    request<AgentContextRecord>(`${contextPath(agentId)}/suggestions/adopt`, {
      method: "POST", body: JSON.stringify({ expected_version, context_id }),
    }).then((result) => result.body),
  disable: (agentId: string, expected_version: number) =>
    request<AgentContextRecord>(`${contextPath(agentId)}/disable`, {
      method: "POST", body: JSON.stringify({ expected_version }),
    }).then((result) => result.body),
  clear: (agentId: string, expected_version: number) =>
    request<AgentContextRecord>(`${contextPath(agentId)}/clear`, {
      method: "POST", body: JSON.stringify({ expected_version }),
    }).then((result) => result.body),
};
