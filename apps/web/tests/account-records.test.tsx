import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AccountViewRecord, AgentContextRecord } from "../lib/account-views";
import { AccountViews } from "../components/AccountViews";
import { AgentRecords } from "../components/AgentRecords";
import { AgentContext } from "../components/AgentContext";
import { FundRecords } from "../components/FundRecords";
import { PositionRecords } from "../components/PositionRecords";

const mocks = vi.hoisted(() => ({ adopt: vi.fn(), correct: vi.fn(), disable: vi.fn(), clear: vi.fn(), get: vi.fn(), load: vi.fn(), getAccountView: vi.fn() }));
vi.mock("../lib/account-views", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/account-views")>();
  return { ...original, loadAccountViews: (...args: unknown[]) => mocks.load(...args),
    getAccountView: (...args: unknown[]) => mocks.getAccountView(...args), agentContextApi: {
    get: (...args: unknown[]) => mocks.get(...args), adopt: (...args: unknown[]) => mocks.adopt(...args), correct: (...args: unknown[]) => mocks.correct(...args),
    disable: (...args: unknown[]) => mocks.disable(...args), clear: (...args: unknown[]) => mocks.clear(...args),
  } };
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
  it("shows a submitted sale under its exact position and keeps marks unknown", async () => {
    const user = userEvent.setup();
    render(<PositionRecords records={[position, ownedSale, otherSale, wrongAssetSale]} />);
    await user.click(screen.getByText(/position-a-1/));
    expect(screen.getByText(/action-a-sale-1 · SUBMITTED/)).toBeInTheDocument();
    expect(screen.queryByText(/action-b-sale-1/)).toBeNull();
    expect(screen.queryByText(/action-wrong-asset-sale/)).toBeNull();
    expect(screen.getByText("Estimated unrealized result.").parentElement).toHaveTextContent("Unknown");
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

  it("resolves context source links to the rendered owner-scoped record", async () => {
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
    const link = await screen.findByRole("link", { name: "Open source record" });
    expect(link).toHaveAttribute("href", "#/agents?record=source-record-id");
    expect(document.getElementById("record-source-record-id")).not.toBeNull();
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
    mocks.correct.mockRejectedValueOnce(new Error("stale version")).mockResolvedValueOnce(corrected);
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
    expect(await screen.findByRole("alert")).toHaveTextContent("Reload it and check the current version.");
    expect(onChange).not.toHaveBeenCalled();
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
