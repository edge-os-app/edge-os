import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AccountViewRecord, AgentContextRecord } from "../lib/account-views";
import { formatResult } from "../lib/account-views";
import { ApiError } from "../lib/api";
import { AccountViews } from "../components/AccountViews";
import { AgentRecords } from "../components/AgentRecords";
import { AgentContext } from "../components/AgentContext";
import { FundRecords } from "../components/FundRecords";
import { PositionRecords } from "../components/PositionRecords";

const mocks = vi.hoisted(() => ({ adopt: vi.fn(), correct: vi.fn(), disable: vi.fn(), clear: vi.fn(), get: vi.fn(), load: vi.fn(), getAccountView: vi.fn(), resolveSource: vi.fn() }));
vi.mock("../lib/account-views", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/account-views")>();
  return { ...original, loadAccountViews: (...args: unknown[]) => mocks.load(...args),
    getAccountView: (...args: unknown[]) => mocks.getAccountView(...args), agentContextApi: {
    get: (...args: unknown[]) => mocks.get(...args), adopt: (...args: unknown[]) => mocks.adopt(...args), correct: (...args: unknown[]) => mocks.correct(...args),
    disable: (...args: unknown[]) => mocks.disable(...args), clear: (...args: unknown[]) => mocks.clear(...args),
  }, resolveContextSource: (...args: unknown[]) => mocks.resolveSource(...args) };
});

const position: AccountViewRecord = { record_id: "position-record", owner_id: "owner-a", content: {
  owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "POSITION", agent_id: "agent-a", wallet_id: "wallet-a",
  network_id: "monad:143", asset_id: "monad:143/asset:MOE", position_id: "position-a-1",
  strategy_revision: "strategy-a-v3", mandate_id: "mandate-a-v1", position_state: "OPEN", status: "OPEN",
  updated_at: "2026-10-09T11:00:00Z", quantity: { asset_id: "monad:143/asset:MOE", raw: "15", decimals: 0 },
  basis: { state: "UNKNOWN" }, realized: { state: "UNKNOWN" }, unrealized: { state: "UNKNOWN" }, mark: { state: "UNKNOWN" },
} };
const ownedSale: AccountViewRecord = { record_id: "sale-record", owner_id: "owner-a", content: {
  ...position.content, record_kind: "ACTION", action_id: "action-a-sale-1", status: "SUBMITTED",
  updated_at: "2026-10-09T11:05:00Z", quantity: { asset_id: "monad:143/asset:MOE", raw: "3", decimals: 0 },
  reason: "awaiting reconciliation",
} };
const otherSale: AccountViewRecord = { record_id: "other-sale-record", owner_id: "owner-a", content: {
  ...ownedSale.content, agent_id: "agent-b", wallet_id: "wallet-b", position_id: "position-b-1", action_id: "action-b-sale-1",
  status: "CONFIRMED",
} };
const wrongAssetSale: AccountViewRecord = { record_id: "wrong-asset-sale-record", owner_id: "owner-a", content: {
  ...ownedSale.content, action_id: "action-wrong-asset-sale", asset_id: "monad:143/asset:OTHER",
  quantity: { asset_id: "monad:143/asset:OTHER", raw: "3", decimals: 0 },
} };

beforeEach(() => {
  vi.resetAllMocks();
  mocks.load.mockResolvedValue({ records: [], next_offset: null });
});

describe("direct account records", () => {
  it("formats P19 signed quote results without losing raw precision or unknown state", async () => {
    expect(formatResult({ state: "KNOWN", amount: { asset_id: "quote:USD", raw: "-2000000", decimals: 6 } })).toBe("−2");
    expect(formatResult({ state: "KNOWN", amount: { asset_id: "quote:USD", raw: "1000000000000000001", decimals: 18 } })).toBe("1.000000000000000001");
    expect(formatResult({ state: "KNOWN", amount: { asset_id: "quote:USD", raw: "0", decimals: 8 } })).toBe("0");
    expect(formatResult({ state: "UNKNOWN" })).toBe("Unknown");
  });

  it("shows negative realized results as quote-denominated values", async () => {
    const signedPosition: AccountViewRecord = { ...position, schema_version: "account-view/2", content: {
      ...position.content, realized: null, unrealized: null,
      realized_result: { state: "KNOWN", amount: { asset_id: "quote:USD", raw: "-2000000", decimals: 6 } },
      estimated_unrealized_result: { state: "UNKNOWN" },
    } };
    const user = userEvent.setup();
    render(<PositionRecords records={[signedPosition]} />);
    await user.click(screen.getByText(/position-a-1/));
    expect(screen.getByText(/Realized quote result/).parentElement).toHaveTextContent("−2 quote:USD");
    expect(screen.getByText(/Estimated unrealized quote result/).parentElement).toHaveTextContent("Unknown");
  });

  it("preserves the authored basis-to-proceeds explanation for a known closed-position loss", async () => {
    const lossPosition: AccountViewRecord = { ...position, schema_version: "account-view/2", content: {
      ...position.content,
      position_state: "CLOSED",
      basis: { state: "KNOWN", amount: { asset_id: "quote:USD", raw: "10", decimals: 0 } },
      realized_result: { state: "KNOWN", amount: { asset_id: "quote:USD", raw: "-2", decimals: 0 } },
      estimated_unrealized_result: { state: "UNKNOWN" },
      reason: "Synthetic illustration: quote proceeds 8 minus removed basis 10 equals realized result -2 USDC.",
    } };
    const user = userEvent.setup();
    render(<PositionRecords records={[lossPosition]} />);
    await user.click(screen.getByText(/position-a-1/));
    expect(screen.getByText(/Saved note/).parentElement).toHaveTextContent("proceeds 8 minus removed basis 10 equals realized result -2 USDC");
    expect(screen.getByText(/Historical attributed quantity/).parentElement).toHaveTextContent("Current residual wallet inventory is unavailable.");
  });

  it("shows a submitted sale under its exact position and keeps marks unknown", async () => {
    const user = userEvent.setup();
    render(<PositionRecords records={[position, ownedSale, otherSale, wrongAssetSale]} />);
    await user.click(screen.getByText(/position-a-1/));
    expect(screen.getByText(/action-a-sale-1 · SUBMITTED/)).toBeInTheDocument();
    expect(screen.queryByText(/action-b-sale-1/)).toBeNull();
    expect(screen.queryByText(/action-wrong-asset-sale/)).toBeNull();
    expect(screen.getByText("Estimated unrealized quote result.").parentElement).toHaveTextContent("Unknown");
  });

  it("labels deposit history as a capital flow and shows gas separately", () => {
    const agent: AccountViewRecord = { record_id: "agent-record", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "AGENT", agent_id: "agent-a", wallet_id: "wallet-a",
      network_id: "monad:143", status: "STOPPED", health: "SYNTHETIC_HEALTH", updated_at: "2026-10-09T11:00:00Z",
      wallet_balance: { asset_id: "monad:143/asset:WMON", raw: "12", decimals: 0 },
      native_gas: { asset_id: "monad:143/asset:MON", raw: "50000000000000000", decimals: 18 },
    } };
    const deposit: AccountViewRecord = { record_id: "deposit-record", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "CAPITAL_FLOW", agent_id: "agent-a", wallet_id: "wallet-a",
      network_id: "monad:143", asset_id: "monad:143/asset:WMON", flow_id: "flow-a-1", flow_kind: "DEPOSIT",
      status: "CONFIRMED", included_in_realized_result: false, updated_at: "2026-10-09T10:00:00Z",
      quantity: { asset_id: "monad:143/asset:WMON", raw: "12", decimals: 0 },
    } };
    render(<FundRecords records={[agent, deposit]} />);
    expect(screen.getByText(/Native gas/).parentElement).toHaveTextContent("0.05 monad:143/asset:MON");
    expect(screen.getByText(/Capital flow, not trading profit/)).toBeInTheDocument();
  });

  it("shows wallet actions under only their exact deposit or withdrawal flow", () => {
    const flow = (id: string, kind: "DEPOSIT" | "WITHDRAWAL"): AccountViewRecord => ({
      record_id: `flow-record-${id}`, owner_id: "owner-a", content: {
        owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "CAPITAL_FLOW", agent_id: "agent-a",
        wallet_id: "wallet-a", network_id: "monad:143", flow_id: id, flow_kind: kind, status: "CONFIRMED",
        included_in_realized_result: false, updated_at: "2026-10-09T10:00:00Z",
      },
    });
    const action = (id: string, flowId: string, status: string, walletId = "wallet-a"): AccountViewRecord => ({
      record_id: `action-record-${id}`, owner_id: "owner-a", content: {
        owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "ACTION", agent_id: "agent-a",
        wallet_id: walletId, network_id: "monad:143", action_id: id, flow_id: flowId, status,
        updated_at: "2026-10-09T10:05:00Z", reason: `Synthetic ${status.toLowerCase()} reason.`,
        gas: { asset_id: "monad:143/asset:MON", raw: "7", decimals: 18 },
      },
    });
    const rows = [flow("deposit-1", "DEPOSIT"), flow("withdrawal-1", "WITHDRAWAL"),
      action("deposit-pending", "deposit-1", "QUEUED"), action("withdrawal-unknown", "withdrawal-1", "SUBMISSION_UNKNOWN"),
      action("withdrawal-done", "withdrawal-1", "CONFIRMED"), action("withdrawal-failed", "withdrawal-1", "REVERTED"),
      action("wrong-wallet", "deposit-1", "CONFIRMED", "wallet-b")];
    render(<FundRecords records={rows} />);
    expect(screen.getByText(/deposit-pending · QUEUED/)).toBeInTheDocument();
    expect(screen.getByText(/withdrawal-unknown · SUBMISSION_UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText(/withdrawal-done · CONFIRMED/)).toBeInTheDocument();
    expect(screen.getByText(/withdrawal-failed · REVERTED/)).toBeInTheDocument();
    expect(screen.getByText(/wrong-wallet/)).toBeInTheDocument();
    expect(screen.getByText("Wallet actions whose flow is not loaded")).toBeInTheDocument();
    expect(screen.getAllByText(/Native gas: 0\.000000000000000007/)).toHaveLength(5);
  });

  it("shows synthetic monitoring and revision-linked evidence without a performance claim", async () => {
    const agent: AccountViewRecord = { record_id: "agent-record", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "AGENT", agent_id: "agent-a",
      wallet_id: "wallet-a", network_id: "monad:143", status: "STOPPED", health: "SYNTHETIC_HEALTH", updated_at: "2026-10-09T11:00:00Z",
    } };
    const monitor: AccountViewRecord = { record_id: "monitor-record", owner_id: "owner-a", content: {
      ...agent.content, record_kind: "MONITORING", status: "STALE", input_updated_at: "2026-10-09T10:00:00Z",
      evaluation_attempts: 4, evaluation_completions: 2, next_work: "no trade", blocking_reason: "inputs are stale", pending_reconciliation: true,
    } };
    const edge: AccountViewRecord = { record_id: "edge-record", owner_id: "owner-a", content: {
      ...position.content, record_kind: "EDGE_EVIDENCE", strategy_revision: "strategy-a-v3", edge_revision: "edge-a-r2",
      edge_evidence_status: "UNRESOLVED", status: "UNRESOLVED", reason: "Synthetic only.",
    } };
    render(<AgentRecords records={[agent, monitor]} />);
    expect(screen.getByText(/4 attempts \/ 2 completions/)).toBeInTheDocument();
    expect(screen.getByText(/Pending reconciliation: Yes/)).toBeInTheDocument();

    const user = userEvent.setup();
    render(<PositionRecords records={[position, edge]} />);
    await user.click(screen.getByText(/position-a-1/));
    expect(screen.getByText(/edge-a-r2 · UNRESOLVED/)).toBeInTheDocument();
  });

  it("renders exact permission snapshot history and never-active failed approval terms", async () => {
    const agent: AccountViewRecord = { record_id: "agent-permission", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "AGENT", agent_id: "agent-a",
      wallet_id: "wallet-a", network_id: "monad:143", status: "RUNNING", updated_at: "2026-10-09T11:00:00Z",
    } };
    const snapshot: AccountViewRecord = { record_id: "permission-failed", schema_version: "account-view/2", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "PERMISSION_SNAPSHOT", agent_id: "agent-a",
      wallet_id: "wallet-a", network_id: "monad:143", strategy_revision: "strategy-a-v5", mandate_id: "mandate-a-v3",
      approval_id: "approval-a-v5", predecessor_approval_id: "approval-a-v4", activation_state: "NEVER_ACTIVE",
      status: "FAILED", updated_at: "2026-10-09T08:02:00Z", terms_hash: "sha256:a6020055d1ffdc1b76df8c9f08bb3f3616d4681703345979be6a4972543e704b",
      signer_binding: "synthetic-signer-a-v2", policy_binding: "synthetic-policy-a-v5",
      requested_at: "2026-10-09T08:00:00Z", checked_at: "2026-10-09T08:01:00Z", failed_at: "2026-10-09T08:02:00Z",
      terms: { adopted_capital: [{ asset_id: "quote:USD", raw: "600", decimals: 0 }], supported_assets: ["asset:MOE"],
        supported_routes: ["synthetic-route"], actions: ["BUY", "SELL"], limits: [{ name: "max action", amount: { asset_id: "quote:USD", raw: "125", decimals: 0 } }],
        expiry: "2027-03-31T00:00:00Z", stop_effects: ["STOP_NEW_ENTRIES"] },
    } };
    const otherWallet: AccountViewRecord = { ...snapshot, record_id: "permission-other-wallet", content: {
      ...snapshot.content, wallet_id: "wallet-b", approval_id: "approval-b-v1",
    } };
    const pending: AccountViewRecord = { ...snapshot, record_id: "permission-pending", content: {
      ...snapshot.content, approval_id: "approval-a-change-pending", predecessor_approval_id: "approval-a-v4",
      status: "CHANGE_PENDING", approved_at: "2026-10-09T13:01:00Z", checked_at: null, applied_at: null,
      failed_at: null, cancelled_at: null,
    } };
    const failedInitial: AccountViewRecord = { ...snapshot, record_id: "permission-first-failed", content: {
      ...snapshot.content, approval_id: "approval-a-initial-failed", predecessor_approval_id: null,
      approved_at: "2026-10-09T15:01:00Z", checked_at: "2026-10-09T15:02:00Z",
    } };
    const user = userEvent.setup();
    render(<AgentRecords records={[agent, snapshot, otherWallet, pending, failedInitial]} />);
    expect(screen.getByText("Permission approval history · synthetic records")).toBeInTheDocument();
    expect(screen.getByText(/approval-a-v5 · FAILED · NEVER_ACTIVE/)).toBeInTheDocument();
    expect(screen.getByText(/approval-a-initial-failed · FAILED · NEVER_ACTIVE/)).toBeInTheDocument();
    expect(screen.queryByText(/approval-b-v1/)).toBeNull();
    await user.click(screen.getByText(/approval-a-v5 · FAILED · NEVER_ACTIVE/));
    const failedSnapshot = screen.getByText(/approval-a-v5 · FAILED · NEVER_ACTIVE/).closest("details");
    expect(failedSnapshot).not.toBeNull();
    expect(failedSnapshot?.querySelector("dl")).toHaveTextContent("owner-a · agent-a · wallet-a · monad:143");
    expect(failedSnapshot?.querySelector("dl")).toHaveTextContent("600 quote:USD");
    expect(failedSnapshot?.querySelector("dl")).toHaveTextContent("2026-10-09T08:02:00Z");
    await user.click(screen.getByText(/approval-a-initial-failed · FAILED · NEVER_ACTIVE/));
    expect(screen.getByText(/No earlier approval \(initial attempt\)/)).toBeInTheDocument();
    await user.click(screen.getByText(/approval-a-change-pending · CHANGE_PENDING · NEVER_ACTIVE/));
    const pendingSnapshot = screen.getByText(/approval-a-change-pending · CHANGE_PENDING · NEVER_ACTIVE/).closest("details");
    expect(pendingSnapshot).not.toBeNull();
    expect(pendingSnapshot?.querySelector("dl")).toHaveTextContent("Not yet checked");
    expect(pendingSnapshot?.querySelector("dl")).toHaveTextContent("Not applied (never active)");
  });

  it("keeps a lesson suggested until the owner adopts it", async () => {
    const user = userEvent.setup();
    const context: AgentContextRecord = { owner_id: "owner-a", agent_id: "agent-a", memory_version: 1, state: "ACTIVE", entries: [
      { context_id: "lesson-1", kind: "LESSON", status: "SUGGESTED", text: "A sample result is not a live receipt.", source_refs: [] },
    ] };
    const adopted = { ...context, memory_version: 2, entries: [{ ...context.entries[0], status: "ADOPTED" as const }] };
    mocks.adopt.mockResolvedValue(adopted);
    const onChange = vi.fn();
    render(<AgentContext record={context} onChange={onChange} onClose={vi.fn()} />);
    expect(screen.getByText(/SUGGESTED/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Adopt suggestion" }));
    expect(mocks.adopt).toHaveBeenCalledWith("agent-a", 1, "lesson-1");
    expect(onChange).toHaveBeenCalledWith(adopted);
  });

  it("reconciles a committed suggestion after a lost reply without sending a second write", async () => {
    const user = userEvent.setup();
    const context: AgentContextRecord = { owner_id: "owner-a", agent_id: "agent-a", memory_version: 1, state: "ACTIVE", entries: [
      { context_id: "lesson-commit", kind: "LESSON", status: "SUGGESTED", text: "A sample result is not a receipt.", source_refs: [] },
    ] };
    const adopted: AgentContextRecord = { ...context, memory_version: 2,
      entries: [{ ...context.entries[0], status: "ADOPTED" }] };
    mocks.adopt.mockRejectedValueOnce(new ApiError(0, "network_error", "reply lost"));
    mocks.get.mockResolvedValueOnce(adopted);
    const onChange = vi.fn();
    render(<AgentContext record={context} onChange={onChange} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Adopt suggestion" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("outcome is not confirmed");
    expect(screen.getByRole("button", { name: "Adopt suggestion" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Check saved context" }));

    expect(await screen.findByRole("status")).toHaveTextContent("version 2 contains the requested change");
    expect(onChange).toHaveBeenCalledWith(adopted);
    expect(mocks.adopt).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledTimes(1);
  });

  it("keeps a correction draft and uncertain intent when reconciliation fails", async () => {
    const user = userEvent.setup();
    const context: AgentContextRecord = { owner_id: "owner-a", agent_id: "agent-a", memory_version: 4, state: "ACTIVE", entries: [
      { context_id: "lesson-correct", kind: "CORRECTION", status: "ADOPTED", text: "Old saved wording.", source_refs: [] },
    ] };
    const corrected: AgentContextRecord = { ...context, memory_version: 5,
      entries: [{ ...context.entries[0], text: "Exact pending replacement." }] };
    mocks.correct.mockRejectedValueOnce(new ApiError(0, "network_error", "reply lost"));
    mocks.get.mockRejectedValueOnce(new ApiError(0, "network_error", "read failed")).mockResolvedValueOnce(corrected);
    const onChange = vi.fn();
    render(<AgentContext record={context} onChange={onChange} onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Correct context" }));
    const editor = screen.getByLabelText("Corrected context");
    await user.clear(editor);
    await user.type(editor, "Exact pending replacement.");
    await user.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("outcome is not confirmed");
    await user.click(screen.getByRole("button", { name: "Check saved context" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("remains uncertain");
    expect(editor).toHaveValue("Exact pending replacement.");
    await user.click(screen.getByRole("button", { name: "Check saved context" }));
    expect(await screen.findByRole("status")).toHaveTextContent("version 5 contains the requested change");
    expect(mocks.correct).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledTimes(2);
  });

  it("resolves context source links before opening the supported owner-scoped destination", async () => {
    const context: AgentContextRecord = { owner_id: "owner-a", agent_id: "agent-a", memory_version: 1, state: "ACTIVE", entries: [
      { context_id: "preference-1", kind: "PREFERENCE", status: "ADOPTED", text: "See the source.", source_refs: ["source-record-id"] },
    ] };
    mocks.get.mockResolvedValue(context);
    const agent: AccountViewRecord = { record_id: "source-record-id", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "AGENT", agent_id: "agent-a",
      wallet_id: "wallet-a", network_id: "monad:143", status: "STOPPED", updated_at: "2026-10-09T11:00:00Z",
    } };
    render(<AgentRecords records={[agent]} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Inspect agent context" }));
    mocks.resolveSource.mockResolvedValueOnce({ source_record_id: "source-record-id", source_record_type: "IntakeRequest",
      destination_type: "RESEARCH", destination_record_id: "intake-record-id" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Open source record" }));
    expect(mocks.resolveSource).toHaveBeenCalledWith("source-record-id");
    expect(window.location.hash).toBe("#/research/intake-record-id?source=source-record-id");
  });

  it("keeps saved context visible when a source cannot be owner-verified", async () => {
    const context: AgentContextRecord = { owner_id: "owner-a", agent_id: "agent-a", memory_version: 3, state: "ACTIVE", entries: [
      { context_id: "lesson-private", kind: "LESSON", status: "ADOPTED", text: "Saved context remains unchanged.", source_refs: ["foreign-source-id"] },
    ] };
    mocks.resolveSource.mockRejectedValueOnce(new ApiError(404, "not_found", "missing"));
    const beforeHash = window.location.hash;
    const user = userEvent.setup();
    render(<AgentContext record={context} onChange={vi.fn()} onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Open source record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your saved context is unchanged");
    expect(screen.getByText("Saved context remains unchanged.")).toBeInTheDocument();
    expect(screen.getByText(/version 3/)).toBeInTheDocument();
    expect(window.location.hash).toBe(beforeHash);
  });

  it("loads an exact saved source row when it is outside the current account page", async () => {
    const ownerScopedSource = { ...position, record_id: "older-source-record" };
    mocks.load.mockResolvedValue({ records: [], next_offset: 100 });
    mocks.getAccountView.mockResolvedValue(ownerScopedSource);
    render(<AccountViews initialView="Funds" sourceRecordId="older-source-record" />);
    expect(await screen.findByRole("heading", { name: "Account", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText(/position-a-1/)).toBeInTheDocument();
    expect(mocks.getAccountView).toHaveBeenCalledWith("older-source-record");
  });

  it("opens an exact wallet-level action from Funds even when its flow is not loaded", async () => {
    const action: AccountViewRecord = { record_id: "action-source-id", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "ACTION", agent_id: "agent-a",
      wallet_id: "wallet-a", network_id: "monad:143", flow_id: "flow-not-loaded", action_id: "action-source-1",
      status: "SUBMISSION_UNKNOWN", updated_at: "2026-10-09T12:00:00Z", reason: "synthetic unknown outcome",
    } };
    mocks.load.mockResolvedValue({ records: [], next_offset: null });
    mocks.getAccountView.mockResolvedValue(action);
    render(<AccountViews initialView="Positions" sourceRecordId="action-source-id" />);
    expect(await screen.findByText(/action-source-1 · SUBMISSION_UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText("Wallet actions whose flow is not loaded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Funds" })).toHaveAttribute("aria-pressed", "true");
  });

  it("opens an exact paginated position action with its owner-matched parent and deduplicates Load more", async () => {
    const user = userEvent.setup();
    mocks.load.mockResolvedValueOnce({ records: [], next_offset: 100 })
      .mockResolvedValueOnce({ records: [position, ownedSale], next_offset: null })
      .mockResolvedValueOnce({ records: [position, ownedSale], next_offset: null });
    mocks.getAccountView.mockResolvedValue(ownedSale);

    render(<AccountViews initialView="Agents" sourceRecordId={ownedSale.record_id} />);

    expect(await screen.findByText(/action-a-sale-1 · SUBMITTED/)).toBeInTheDocument();
    expect(screen.getByText(/position-a-1 · monad:143\/asset:MOE · OPEN/)).toBeInTheDocument();
    expect(screen.getAllByText(/action-a-sale-1 · SUBMITTED/)).toHaveLength(1);
    expect(mocks.load).toHaveBeenNthCalledWith(2, {
      agent_id: "agent-a", wallet_id: "wallet-a", network_id: "monad:143", asset_id: "monad:143/asset:MOE",
      position_id: "position-a-1", strategy_revision: "strategy-a-v3", record_kind: "POSITION",
    });

    await user.click(screen.getByRole("button", { name: "Load more records" }));
    expect(await screen.findByText(/action-a-sale-1 · SUBMITTED/)).toBeInTheDocument();
    expect(screen.getAllByText(/action-a-sale-1 · SUBMITTED/)).toHaveLength(1);
    expect(document.querySelectorAll(`#record-${ownedSale.record_id}`)).toHaveLength(1);
  });

  it("keeps an exact source action visible without assigning an owner-mismatched position", async () => {
    const foreignPosition = { ...position, record_id: "foreign-position-record", owner_id: "owner-b",
      content: { ...position.content, owner_id: "owner-b" } };
    mocks.load.mockResolvedValueOnce({ records: [], next_offset: 100 })
      .mockResolvedValueOnce({ records: [foreignPosition], next_offset: null });
    mocks.getAccountView.mockResolvedValue(ownedSale);
    render(<AccountViews initialView="Agents" sourceRecordId={ownedSale.record_id} />);

    const exactSource = await screen.findByRole("region", { name: "Exact source action" });
    expect(exactSource).toContainElement(document.getElementById(`record-${ownedSale.record_id}`));
    expect(exactSource).toHaveTextContent("The owner-matched parent position is unavailable");
    expect(screen.queryByText(/position-a-1 · monad:143\/asset:MOE · OPEN/)).toBeNull();
    expect(document.getElementById(`record-${foreignPosition.record_id}`)).toBeNull();
  });

  it("opens an exact wallet-level action from Funds even when its flow is not loaded", async () => {
    const action: AccountViewRecord = { record_id: "action-source-id", owner_id: "owner-a", content: {
      owner_id: "owner-a", evidence_class: "SYNTHETIC_AUTHORED", record_kind: "ACTION", agent_id: "agent-a",
      wallet_id: "wallet-a", network_id: "monad:143", flow_id: "flow-not-loaded", action_id: "action-source-1",
      status: "SUBMISSION_UNKNOWN", updated_at: "2026-10-09T12:00:00Z", reason: "synthetic unknown outcome",
    } };
    mocks.load.mockResolvedValue({ records: [], next_offset: null });
    mocks.getAccountView.mockResolvedValue(action);
    render(<AccountViews initialView="Positions" sourceRecordId="action-source-id" />);
    expect(await screen.findByText(/action-source-1 · SUBMISSION_UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText("Wallet actions whose flow is not loaded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Funds" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps failed edits visible, then versions correction, disable, and confirmed clear", async () => {
    const user = userEvent.setup();
    const context: AgentContextRecord = { owner_id: "owner-a", agent_id: "agent-a", memory_version: 1, state: "ACTIVE", entries: [
      { context_id: "preference-1", kind: "PREFERENCE", status: "ADOPTED", text: "Show evidence.", source_refs: [] },
    ] };
    const corrected: AgentContextRecord = { ...context, memory_version: 2, entries: [
      { ...context.entries[0], kind: "CORRECTION", text: "Show dated evidence." },
    ] };
    const disabled: AgentContextRecord = { ...corrected, memory_version: 3, state: "DISABLED" };
    const cleared: AgentContextRecord = { ...disabled, memory_version: 4, state: "CLEARED", entries: [] };
    mocks.correct.mockRejectedValueOnce(new ApiError(422, "invalid", "Synthetic validation rejection."))
      .mockResolvedValueOnce(corrected);
    mocks.get.mockResolvedValueOnce(context);
    mocks.disable.mockResolvedValueOnce(disabled);
    mocks.clear.mockResolvedValueOnce(cleared);
    const onChange = vi.fn();
    const onClose = vi.fn();
    const view = render(<AgentContext record={context} onChange={onChange} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Correct context" }));
    const editor = screen.getByLabelText("Corrected context");
    await user.clear(editor);
    await user.type(editor, "Show dated evidence.");
    await user.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The save was rejected.");
    expect(onChange).not.toHaveBeenCalled();
    expect(editor).toHaveValue("Show dated evidence.");
    expect(screen.getByRole("button", { name: "Save correction" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Check saved context" }));
    expect(await screen.findByRole("status")).toHaveTextContent("was checked");
    await user.click(screen.getByRole("button", { name: "Save correction" }));
    expect(onChange).toHaveBeenLastCalledWith(corrected);

    view.rerender(<AgentContext record={corrected} onChange={onChange} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Disable future context" }));
    expect(mocks.disable).toHaveBeenCalledWith("agent-a", 2);
    expect(onChange).toHaveBeenLastCalledWith(disabled);

    view.rerender(<AgentContext record={disabled} onChange={onChange} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Clear context" }));
    expect(screen.getByRole("group", { name: "Confirm clear context" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm clear" }));
    expect(mocks.clear).toHaveBeenCalledWith("agent-a", 3);
    expect(onChange).toHaveBeenLastCalledWith(cleared);
  });

  it("opens the direct Funds view and retries a failed account load", async () => {
    const user = userEvent.setup();
    mocks.load.mockRejectedValueOnce(new Error("Unavailable"));
    render(<AccountViews />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Account records could not be loaded.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await user.click(await screen.findByRole("button", { name: "Funds" }));
    expect(screen.getByText("No saved fund records.")).toBeInTheDocument();
    expect(mocks.load).toHaveBeenCalledTimes(2);
  });

  it("loads the next bounded page before attributing a later saved action", async () => {
    const user = userEvent.setup();
    mocks.load.mockResolvedValueOnce({ records: [position], next_offset: 100 });
    mocks.load.mockResolvedValueOnce({ records: [ownedSale], next_offset: null });
    render(<AccountViews initialView="Positions" />);
    await user.click(await screen.findByRole("button", { name: "Load more records" }));
    await user.click(screen.getByText(/position-a-1/));
    expect(screen.getByText(/action-a-sale-1 · SUBMITTED/)).toBeInTheDocument();
    expect(mocks.load).toHaveBeenNthCalledWith(2, {}, 100);
  });
});
