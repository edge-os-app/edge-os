import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ServiceAccountState } from "../components/ServiceAccountState";

const mocks = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock("../lib/account-views", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/account-views")>()),
  loadServiceProjection: (...args: unknown[]) => mocks.load(...args),
}));

const OWNER = "11111111-1111-4111-8111-111111111111";
const QUOTE = { asset_id: "monad-testnet:10143/0x2222", decimals: 6 };
const BASE = { asset_id: "monad-testnet:10143/0x1111", decimals: 18 };

function record(kind: string, content: Record<string, unknown>) {
  return { schema_version: "account-view-projection/1", record_type: "AccountViewProjection", record_id: `projection:${kind}`,
    source: { table: `local.${kind}`, id: "x" },
    content: { owner_id: OWNER, evidence_class: "SERVICE_PROJECTION", record_kind: kind, agent_id: "agent-a",
      wallet_id: "w", network_id: "10143", updated_at: "2026-10-12T00:00:00Z", ...content } };
}

beforeEach(() => mocks.load.mockReset());

describe("saved connected state (F1)", () => {
  it("shows projected rows with unknown values kept unknown and deposits apart from results", async () => {
    mocks.load.mockResolvedValue({ schema_version: "account-view-projection/1", source: "SERVICE_PROJECTION", ports: "FIXTURE",
      notice: "Projected from the saved connected-service rows; nothing is written.", records: [
        record("CAPITAL_FLOW", { status: "CONFIRMED", flow_id: "f", flow_kind: "DEPOSIT", quantity: { ...QUOTE, raw: "1000000000" },
          included_in_realized_result: false, reason: null }),
        record("POSITION", { status: "OPEN", position_state: "OPEN", position_id: "p", asset_id: BASE.asset_id,
          quantity: { ...BASE, raw: "50000000000000000000" }, basis: { state: "KNOWN", amount: { ...QUOTE, raw: "100000000" } },
          realized_result: { state: "KNOWN", amount: { ...QUOTE, raw: "0" } }, estimated_unrealized_result: { state: "UNKNOWN", amount: null },
          mark: { state: "UNKNOWN", amount: null } }),
        record("MONITORING", { status: "BLOCKED", health: "ATTENTION", evaluation_attempts: 2, evaluation_completions: 1,
          pending_reconciliation: true }),
      ] });
    render(<ServiceAccountState agentId="agent-a" />);
    const list = await screen.findByRole("list", { name: "Projected records" });
    expect(list).toHaveTextContent("DEPOSIT: 1000 monad-testnet:10143/0x2222 Not a trading result.");
    expect(list).toHaveTextContent("Held 50 monad-testnet:10143/0x1111");
    expect(list).toHaveTextContent("unrealized result and mark unknown");
    expect(list).toHaveTextContent("reconcile the original action before another evaluation");
    expect(screen.getByText(/Ports: authored local fixtures/)).toBeInTheDocument();
  });

  it("explains an empty state and retries a failed read", async () => {
    mocks.load.mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({ schema_version: "account-view-projection/1",
      source: "SERVICE_PROJECTION", ports: "UNAVAILABLE", notice: "n", records: [] });
    render(<ServiceAccountState agentId="agent-a" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No connected-service state is saved for this agent.")).toBeInTheDocument();
  });

  it("reads the saved state again on Refresh (Review A N2)", async () => {
    const empty = { schema_version: "account-view-projection/1", source: "SERVICE_PROJECTION", ports: "FIXTURE", notice: "n", records: [] };
    mocks.load.mockResolvedValueOnce(empty).mockResolvedValueOnce({ ...empty, records: [
      record("AGENT", { status: "CONFIRMED", permission_state: "NO_REMOVAL_REQUESTED" })] });
    render(<ServiceAccountState agentId="agent-a" />);
    expect(await screen.findByText("No connected-service state is saved for this agent.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Refresh saved state" }));
    expect(await screen.findByRole("list", { name: "Projected records" })).toHaveTextContent("Agent: CONFIRMED");
    expect(mocks.load).toHaveBeenCalledTimes(2);
  });
});
