import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ logout: vi.fn() }));
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ status: "ready", fixtureLabel: null, unavailableReason: null, userId: "owner-1",
    signInMessage: null, signInSlow: false, explicitSignOut: false, login: vi.fn(), logout: mocks.logout,
    createEmbeddedWallet: null }),
}));
vi.mock("../components/ResearchHome", () => ({ ResearchHome: () => <p>Research home</p> }));
vi.mock("../components/RequestPage", () => ({ RequestPage: () => <p>Request page</p> }));
vi.mock("../components/Later", () => ({ Later: () => <p>Later</p> }));
vi.mock("../components/AccountViews", () => ({ AccountViews: () => <p>Account views</p> }));

import { Shell } from "../components/Shell";

const NOTICE = "build-scope-notice";

async function renderAt(hash: string) {
  window.location.hash = hash;
  render(<Shell />);
  await waitFor(() => expect(window.location.hash).toBe(hash));
}

describe("build-scope notice", () => {
  beforeEach(() => { window.location.hash = ""; mocks.logout.mockReset(); });

  it("shows the account notice on an account view", async () => {
    await renderAt("#/agents");
    expect(await screen.findByTestId(NOTICE)).toBeInTheDocument();
  });

  it("shows the account notice on the later account view", async () => {
    await renderAt("#/positions");
    expect(await screen.findByTestId(NOTICE)).toBeInTheDocument();
  });

  it("does not show the account notice on the research page", async () => {
    await renderAt("#/research");
    expect(await screen.findByText("Research home")).toBeInTheDocument();
    expect(screen.queryByTestId(NOTICE)).not.toBeInTheDocument();
  });

  it("does not show the account notice on a research request page", async () => {
    await renderAt("#/research/request-1");
    expect(await screen.findByText("Request page")).toBeInTheDocument();
    expect(screen.queryByTestId(NOTICE)).not.toBeInTheDocument();
  });
});
