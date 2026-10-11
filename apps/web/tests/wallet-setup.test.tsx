import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import type { WalletSetupRecord } from "../lib/types";
import { WalletSetup } from "../components/WalletSetup";

const mocks = vi.hoisted(() => ({ get: vi.fn(), prepare: vi.fn(), dispatch: vi.fn(), resume: vi.fn(), cancel: vi.fn() }));
vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return { ...original, api: { ...original.api,
    walletSetup: (...args: unknown[]) => mocks.get(...args),
    prepareWalletSetup: (...args: unknown[]) => mocks.prepare(...args),
    dispatchWalletSetup: (...args: unknown[]) => mocks.dispatch(...args),
    resumeWalletSetup: (...args: unknown[]) => mocks.resume(...args),
    cancelWalletSetup: (...args: unknown[]) => mocks.cancel(...args),
  } };
});

const REVISION = { strategyId: "strategy-a", strategyRevisionId: "11111111-1111-4111-8111-111111111111" };

function record(over: Partial<WalletSetupRecord>): WalletSetupRecord {
  return { setup_id: "setup-a", owner_id: "owner-a", agent_id: "agent-a", network_id: 10143,
    strategy_id: "strategy-a", strategy_revision_id: REVISION.strategyRevisionId,
    content_sha256: "a".repeat(64), manifest_sha256: "b".repeat(64), state: "REQUESTED",
    cancellation_intent: "NONE", creation_dispatched: false, wallet_id: null, reason: null,
    created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z", ...over };
}

beforeEach(() => { vi.resetAllMocks(); });

describe("wallet setup UI", () => {
  it("shows a confirmed empty state and creates nothing on load or refresh", async () => {
    mocks.get.mockRejectedValue(new ApiError(404, "not_found", "The requested wallet setup was not found."));
    render(<WalletSetup agentId="agent-a" revision={REVISION} />);
    expect(await screen.findByText("No wallet setup saved")).toBeInTheDocument();
    expect(screen.getByText(/authored local fixture/i)).toBeInTheDocument();
    expect(mocks.prepare).not.toHaveBeenCalled();
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });

  it("saves the setup first, then offers creation, and binds the exact revision", async () => {
    mocks.get.mockRejectedValue(new ApiError(404, "not_found", "missing"));
    mocks.prepare.mockResolvedValue(record({ state: "REQUESTED" }));
    mocks.dispatch.mockResolvedValue(record({ state: "CONFIRMED", wallet_id: "fixture:owner-a:agent-a" }));
    render(<WalletSetup agentId="agent-a" revision={REVISION} />);
    await screen.findByText("No wallet setup saved");

    await userEvent.click(screen.getByRole("button", { name: "Save wallet setup" }));
    expect(await screen.findByText("Saved, not dispatched")).toBeInTheDocument();
    expect(mocks.prepare).toHaveBeenCalledWith("agent-a", expect.objectContaining({
      network_id: 10143, strategy_id: "strategy-a", strategy_revision_id: REVISION.strategyRevisionId }));
    expect(mocks.dispatch).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Create wallet now" }));
    expect(await screen.findByText("Wallet confirmed")).toBeInTheDocument();
    expect(mocks.dispatch).toHaveBeenCalledTimes(1);
  });

  it("keeps an unknown outcome uncertain and never replays creation", async () => {
    mocks.get.mockResolvedValue(record({ state: "UNKNOWN", reason: "RESPONSE_LOST", creation_dispatched: true }));
    mocks.resume.mockResolvedValue(record({ state: "UNKNOWN", reason: "RECONCILE_NO_EXACT_ID", creation_dispatched: true }));
    render(<WalletSetup agentId="agent-a" />);
    expect(await screen.findByText("Outcome unknown")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Check the saved setup again" }));
    expect(mocks.resume).toHaveBeenCalledTimes(1);
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });

  it("shows a cancelled intent truthfully and offers no creation", async () => {
    mocks.get.mockResolvedValue(record({ state: "FAILED", reason: "CANCELLED_BEFORE_DISPATCH",
      cancellation_intent: "REQUESTED_BEFORE_DISPATCH" }));
    render(<WalletSetup agentId="agent-a" />);
    expect(await screen.findByText("Cancelled before dispatch")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });

  it("reports a rejected prepare without dispatching", async () => {
    mocks.get.mockRejectedValue(new ApiError(404, "not_found", "missing"));
    mocks.prepare.mockRejectedValue(new ApiError(409, "changed_setup_identity", "This agent already holds a different setup."));
    render(<WalletSetup agentId="agent-a" revision={REVISION} />);
    await screen.findByText("No wallet setup saved");
    await userEvent.click(screen.getByRole("button", { name: "Save wallet setup" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This agent already holds a different setup.");
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });
});
