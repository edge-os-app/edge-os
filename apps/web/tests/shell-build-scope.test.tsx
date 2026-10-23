import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ logout: vi.fn(), consent: vi.fn() }));
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ status: "ready", fixtureLabel: null, unavailableReason: null, userId: "owner-1",
    signInMessage: null, signInSlow: false, explicitSignOut: false, login: vi.fn(), logout: mocks.logout,
    createEmbeddedWallet: null }),
}));
vi.mock("../lib/financial", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/financial")>();
  return { ...original, financial: { ...original.financial, consent: mocks.consent } };
});
vi.mock("../components/ResearchHome", () => ({ ResearchHome: () => <p>Research home</p> }));
vi.mock("../components/RequestPage", () => ({ RequestPage: () => <p>Request page</p> }));
vi.mock("../components/Later", () => ({ Later: () => <p>Later</p> }));
vi.mock("../components/AccountViews", () => ({ AccountViews: () => <p>Account views</p> }));

import { Shell } from "../components/Shell";

const NOTICE = "build-scope-notice";
const CONTROLLED_NOTICE = "controlled-scope-notice";
const OLD_NOTICE = "Build scope. Account views show authored synthetic records only, not live wallet data. "
  + "Saving a Research rule grants no trading permission. This build does not connect a wallet or move funds.";

function text(node: HTMLElement | null): string {
  return (node?.textContent ?? "").replace(/\s+/g, " ").trim();
}

async function renderAt(hash: string) {
  window.location.hash = hash;
  render(<Shell />);
  await waitFor(() => expect(window.location.hash).toBe(hash));
}

describe("build-scope notice", () => {
  beforeEach(() => { window.location.hash = ""; mocks.logout.mockReset(); mocks.consent.mockReset(); });

  it("shows the exact old notice on an account view with no agent", async () => {
    await renderAt("#/agents");
    expect(text(await screen.findByTestId(NOTICE))).toBe(OLD_NOTICE);
    expect(screen.queryByTestId(CONTROLLED_NOTICE)).toBeNull();
    expect(mocks.consent).not.toHaveBeenCalled();
  });

  it("shows the exact old notice on the later account view", async () => {
    await renderAt("#/positions");
    expect(text(await screen.findByTestId(NOTICE))).toBe(OLD_NOTICE);
    expect(screen.queryByTestId(CONTROLLED_NOTICE)).toBeNull();
  });

  it("does not show the account notice on the research page", async () => {
    await renderAt("#/research");
    expect(await screen.findByText("Research home")).toBeInTheDocument();
    expect(screen.queryByTestId(NOTICE)).toBeNull();
    expect(screen.queryByTestId(CONTROLLED_NOTICE)).toBeNull();
  });

  it("does not show the account notice on a research request page", async () => {
    await renderAt("#/research/request-1");
    expect(await screen.findByText("Request page")).toBeInTheDocument();
    expect(screen.queryByTestId(NOTICE)).toBeNull();
    expect(screen.queryByTestId(CONTROLLED_NOTICE)).toBeNull();
  });

  it("shows the controlled notice only when the agent's API mode says controlled", async () => {
    mocks.consent.mockResolvedValue({ provider_mode: "controlled" });
    await renderAt("#/agents?agent=agent-a");
    expect(await screen.findByTestId(CONTROLLED_NOTICE)).toHaveTextContent(
      "Trading mode. Trades run from your agent wallet within the limits you signed. Every trade needs its release.");
    expect(screen.queryByTestId(NOTICE)).toBeNull();
    expect(mocks.consent).toHaveBeenCalledWith("agent-a");
  });

  it("keeps the exact old notice when the API mode is not controlled", async () => {
    mocks.consent.mockResolvedValue({ provider_mode: "fixture" });
    await renderAt("#/positions?agent=agent-a");
    expect(text(await screen.findByTestId(NOTICE))).toBe(OLD_NOTICE);
    expect(screen.queryByTestId(CONTROLLED_NOTICE)).toBeNull();
  });

  it("keeps the exact old notice while loading and after a failed read, with no retry", async () => {
    mocks.consent.mockRejectedValue(new Error("offline"));
    await renderAt("#/funds?agent=agent-a");
    expect(text(await screen.findByTestId(NOTICE))).toBe(OLD_NOTICE);
    await waitFor(() => expect(mocks.consent).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId(CONTROLLED_NOTICE)).toBeNull();
  });
});
