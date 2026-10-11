import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import type { WalletSetupRecord } from "../lib/types";
import { WalletSetup } from "../components/WalletSetup";

const mocks = vi.hoisted(() => ({ get: vi.fn(), prepare: vi.fn(), dispatch: vi.fn(), resume: vi.fn(), cancel: vi.fn(), provider: vi.fn() }));
vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return { ...original, api: { ...original.api,
    walletProvider: (...args: unknown[]) => mocks.provider(...args),
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.provider.mockResolvedValue({ provider: "fixture", create_calls: 0, lookup_calls: 0 });
});

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

  it("suppresses creation after an uncertain dispatch until a read confirms the state", async () => {
    mocks.get.mockResolvedValueOnce(record({ state: "REQUESTED" }))
      .mockResolvedValue(record({ state: "UNKNOWN", reason: "RESPONSE_LOST", creation_dispatched: true }));
    mocks.dispatch.mockRejectedValue(new ApiError(0, "timeout", "The service did not answer in time."));
    render(<WalletSetup agentId="agent-a" />);
    await screen.findByText("Saved, not dispatched");

    await userEvent.click(screen.getByRole("button", { name: "Create wallet now" }));
    // The reconcile read returns UNKNOWN; creation is not offered.
    expect(await screen.findByText("Outcome unknown")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
    expect(mocks.get).toHaveBeenCalledTimes(2);
  });

  it("keeps creation paused when the reconcile read also fails", async () => {
    mocks.get.mockResolvedValueOnce(record({ state: "REQUESTED" }))
      .mockRejectedValue(new ApiError(503, "service_unavailable", "A required service is unavailable."));
    mocks.dispatch.mockRejectedValue(new ApiError(0, "network_error", "The service could not be reached."));
    render(<WalletSetup agentId="agent-a" />);
    await screen.findByText("Saved, not dispatched");

    await userEvent.click(screen.getByRole("button", { name: "Create wallet now" }));
    expect(await screen.findByRole("button", { name: "Check the saved setup" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
    expect(screen.queryByTestId("wallet-setup-state")).toBeNull();
  });

  it("clears the prior agent's record when a new read starts", async () => {
    mocks.get.mockResolvedValueOnce(record({ state: "REQUESTED", agent_id: "agent-a" }));
    render(<WalletSetup revision={REVISION} />);
    await userEvent.type(screen.getByLabelText("Agent ID"), "agent-a");
    await userEvent.click(screen.getByTestId("wallet-setup-check"));
    expect(await screen.findByText("Saved, not dispatched")).toBeInTheDocument();

    const pending = deferred<WalletSetupRecord>();
    mocks.get.mockReturnValueOnce(pending.promise);
    await userEvent.clear(screen.getByLabelText("Agent ID"));
    await userEvent.type(screen.getByLabelText("Agent ID"), "agent-b");
    await userEvent.click(screen.getByTestId("wallet-setup-check"));
    // The prior agent's actions are hidden while the new read is pending.
    await waitFor(() => expect(screen.queryByTestId("wallet-setup-state")).toBeNull());
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
  });

  it("ignores a late response from an older agent read", async () => {
    const slowA = deferred<WalletSetupRecord>();
    const fastB = deferred<WalletSetupRecord>();
    mocks.get.mockReturnValueOnce(slowA.promise).mockReturnValueOnce(fastB.promise);
    render(<WalletSetup revision={REVISION} />);
    await userEvent.type(screen.getByLabelText("Agent ID"), "agent-a");
    await userEvent.click(screen.getByTestId("wallet-setup-check"));
    await userEvent.clear(screen.getByLabelText("Agent ID"));
    await userEvent.type(screen.getByLabelText("Agent ID"), "agent-b");
    await userEvent.click(screen.getByTestId("wallet-setup-check"));

    fastB.resolve(record({ state: "CONFIRMED", wallet_id: "fixture:owner-a:agent-b", agent_id: "agent-b" }));
    expect(await screen.findByText("Wallet confirmed")).toBeInTheDocument();
    slowA.resolve(record({ state: "REQUESTED", agent_id: "agent-a" }));
    await waitFor(() => expect(screen.queryByText("Saved, not dispatched")).toBeNull());
    expect(screen.getByText("Wallet confirmed")).toBeInTheDocument();
  });

  it("keeps a newer agent selection when an older mutation returns late", async () => {
    const slowPrepare = deferred<WalletSetupRecord>();
    mocks.get.mockRejectedValue(new ApiError(404, "not_found", "missing"));
    mocks.prepare.mockReturnValueOnce(slowPrepare.promise);
    render(<WalletSetup revision={REVISION} />);
    await userEvent.type(screen.getByLabelText("Agent ID"), "agent-a");
    await userEvent.click(screen.getByTestId("wallet-setup-check"));
    await screen.findByText("No wallet setup saved");
    await userEvent.click(screen.getByRole("button", { name: "Save wallet setup" })); // agent-a save is pending

    await userEvent.clear(screen.getByLabelText("Agent ID"));
    await userEvent.type(screen.getByLabelText("Agent ID"), "agent-b");
    await userEvent.click(screen.getByTestId("wallet-setup-check"));
    await screen.findByText("No wallet setup saved");

    // agent-a's save now returns a record; it must not restore agent-a's actions under the agent-b selection.
    slowPrepare.resolve(record({ state: "REQUESTED", agent_id: "agent-a" }));
    await waitFor(() => expect(screen.queryByTestId("wallet-setup-state")).toBeNull());
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel before creating" })).toBeNull();
  });

  it("shows no creation when no provider is configured and reports the mode truthfully", async () => {
    mocks.provider.mockResolvedValue({ provider: "unavailable", create_calls: null, lookup_calls: null });
    mocks.get.mockRejectedValue(new ApiError(404, "not_found", "missing"));
    render(<WalletSetup agentId="agent-a" revision={REVISION} />);
    expect(await screen.findByText(/Real wallet creation is unavailable in this build/i)).toBeInTheDocument();
    await screen.findByText("No wallet setup saved");
    expect(screen.queryByRole("button", { name: "Save wallet setup" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
    expect(screen.queryByText(/authored local fixture/i)).toBeNull();
  });
});
