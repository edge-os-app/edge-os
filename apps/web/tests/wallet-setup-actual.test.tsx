import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { WalletSetupRecord } from "../lib/types";
import { WalletSetup } from "../components/WalletSetup";

const mocks = vi.hoisted(() => ({ get: vi.fn(), dispatch: vi.fn(), resume: vi.fn(), provider: vi.fn(), begin: vi.fn(),
  complete: vi.fn(), sdk: vi.fn() }));
vi.mock("../lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/api")>();
  return { ...original, api: { ...original.api,
    walletProvider: (...args: unknown[]) => mocks.provider(...args),
    walletSetup: (...args: unknown[]) => mocks.get(...args),
    dispatchWalletSetup: (...args: unknown[]) => mocks.dispatch(...args),
    resumeWalletSetup: (...args: unknown[]) => mocks.resume(...args),
  } };
});
vi.mock("../lib/wallet-setup-api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/wallet-setup-api")>();
  return { ...original, walletSetupApi: {
    beginBrowserCreation: (...args: unknown[]) => mocks.begin(...args),
    completeBrowserCreation: (...args: unknown[]) => mocks.complete(...args),
  } };
});
const auth = vi.hoisted(() => ({ userId: "user-a" }));
vi.mock("../lib/auth", () => ({ useOptionalAuth: () => ({ userId: auth.userId, createEmbeddedWallet: (...args: unknown[]) => mocks.sdk(...args) }) }));

const ADDRESS = "0x" + "ab".repeat(20);
const WALLET = { id: "wallet-1", address: ADDRESS, chainType: "ethereum", walletIndex: 1 };

function record(over: Partial<WalletSetupRecord>): WalletSetupRecord {
  return { setup_id: "setup-a", owner_id: "owner-a", agent_id: "agent-a", network_id: 10143,
    strategy_id: "strategy-a", strategy_revision_id: "11111111-1111-4111-8111-111111111111",
    content_sha256: "a".repeat(64), manifest_sha256: "b".repeat(64), state: "REQUESTED",
    cancellation_intent: "NONE", creation_dispatched: false, wallet_id: null, reason: null,
    created_at: "2026-10-16T00:00:00Z", updated_at: "2026-10-16T00:00:00Z", ...over };
}

const pending = record({ state: "PENDING", creation_dispatched: true });
const confirmed = record({ state: "CONFIRMED", creation_dispatched: true, wallet_id: "wallet-1" });

beforeEach(() => {
  vi.resetAllMocks();
  window.localStorage.clear();
  auth.userId = "user-a";
  mocks.provider.mockResolvedValue({ provider: "privy_lookup", create_calls: null, lookup_calls: null });
  mocks.get.mockResolvedValue(record({}));
});

async function clickCreate() {
  render(<WalletSetup agentId="agent-a" />);
  await userEvent.click(await screen.findByRole("button", { name: "Create wallet now" }));
}

describe("actual Privy wallet creation", () => {
  it("commits intent first, creates once and completes with the exact returned wallet", async () => {
    mocks.begin.mockResolvedValue({ ...pending, create_permitted: true });
    mocks.sdk.mockResolvedValue(WALLET);
    mocks.complete.mockResolvedValue(confirmed);
    await clickCreate();
    await waitFor(() => expect(screen.getByTestId("wallet-setup-state")).toHaveTextContent("Wallet confirmed"));
    expect(mocks.begin.mock.invocationCallOrder[0]).toBeLessThan(mocks.sdk.mock.invocationCallOrder[0]);
    expect(mocks.sdk).toHaveBeenCalledTimes(1);
    expect(mocks.complete).toHaveBeenCalledWith("agent-a", { wallet_id: "wallet-1", address: ADDRESS, wallet_index: 1 });
    expect(mocks.dispatch).not.toHaveBeenCalled(); // the fixture dispatch is never used on the actual path
  });

  it("makes no SDK call when the server refuses the begin", async () => {
    mocks.begin.mockResolvedValue({ ...pending, create_permitted: false });
    await clickCreate();
    await waitFor(() => expect(screen.getByTestId("wallet-setup-state")).toHaveTextContent("Creation pending"));
    expect(mocks.sdk).not.toHaveBeenCalled();
    expect(mocks.complete).not.toHaveBeenCalled();
  });

  it("sends an address-only claim for the server to resolve when the SDK returns no ID", async () => {
    mocks.begin.mockResolvedValue({ ...pending, create_permitted: true });
    mocks.sdk.mockResolvedValue({ ...WALLET, id: null });
    mocks.complete.mockResolvedValue(confirmed);
    await clickCreate();
    await waitFor(() => expect(screen.getByTestId("wallet-setup-state")).toHaveTextContent("Wallet confirmed"));
    expect(mocks.complete).toHaveBeenCalledWith("agent-a", { wallet_id: null, address: ADDRESS, wallet_index: 1 });
    expect(mocks.sdk).toHaveBeenCalledTimes(1);
  });

  it("never shows or sends another signed-in owner's retained claim", async () => {
    auth.userId = "user-b";
    window.localStorage.setItem("edge-os:wallet-claim:user-a:agent-a", JSON.stringify(WALLET));
    mocks.get.mockResolvedValue(pending);
    mocks.resume.mockResolvedValue(pending);
    render(<WalletSetup agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "Check the saved setup again" }));
    await waitFor(() => expect(mocks.resume).toHaveBeenCalledTimes(1)); // server-retained claim resume, not user-a's
    expect(mocks.complete).not.toHaveBeenCalled();
    expect(mocks.sdk).not.toHaveBeenCalled();
  });

  it("resends the retained claim after a lost completion reply without a second SDK call", async () => {
    mocks.begin.mockResolvedValue({ ...pending, create_permitted: true });
    mocks.sdk.mockResolvedValue(WALLET);
    mocks.complete.mockRejectedValueOnce(new Error("lost")).mockResolvedValue(confirmed);
    mocks.get.mockResolvedValueOnce(record({})).mockResolvedValue(pending);
    await clickCreate();
    await userEvent.click(await screen.findByRole("button", { name: "Check the saved setup again" }));
    await waitFor(() => expect(screen.getByTestId("wallet-setup-state")).toHaveTextContent("Wallet confirmed"));
    expect(mocks.sdk).toHaveBeenCalledTimes(1);
    expect(mocks.complete).toHaveBeenCalledTimes(2);
    expect(mocks.complete.mock.calls[1]).toEqual(["agent-a", { wallet_id: "wallet-1", address: ADDRESS, wallet_index: 1 }]);
  });

  it("a refreshed page resumes from the retained claim without beginning or creating", async () => {
    window.localStorage.setItem("edge-os:wallet-claim:user-a:agent-a", JSON.stringify(WALLET));
    mocks.get.mockResolvedValue(pending);
    mocks.complete.mockResolvedValue(confirmed);
    render(<WalletSetup agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "Check the saved setup again" }));
    await waitFor(() => expect(screen.getByTestId("wallet-setup-state")).toHaveTextContent("Wallet confirmed"));
    expect(mocks.begin).not.toHaveBeenCalled();
    expect(mocks.sdk).not.toHaveBeenCalled();
  });

  it("an unrecognised provider answer is unavailable, never actual creation", async () => {
    mocks.provider.mockResolvedValue({ provider: "privy", create_calls: 3, lookup_calls: 3 });
    render(<WalletSetup agentId="agent-a" />);
    await screen.findByTestId("wallet-setup-state");
    expect(screen.queryByRole("button", { name: "Create wallet now" })).toBeNull();
  });
});
