import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthRoot, useAuth, type Source } from "../lib/auth";
import { Shell } from "../components/Shell";
import { signedInIdentity } from "../lib/signed-in-identity";

const hoisted = vi.hoisted(() => ({
  setSource: null as null | ((change: Partial<Source>) => void),
  privy: { ready: true, authenticated: true, user: null as unknown },
}));
vi.mock("@privy-io/react-auth", () => ({
  PrivyProvider: ({ children }: { children: React.ReactNode }) => children,
  useCreateWallet: () => ({ createWallet: vi.fn() }),
  useLogin: () => ({ login: vi.fn() }),
  usePrivy: () => ({ ...hoisted.privy, getAccessToken: async () => null, logout: async () => {} }),
}));
// The Privy bridge is replaced so a test can drive the provider state without a Privy app.
vi.mock("../lib/privy-bridge", async () => {
  const React = await import("react");
  return {
    default: ({ render }: { render: (source: Source) => React.ReactNode }) => {
      const [source, setSource] = React.useState<Source>({ ready: false, authenticated: false,
        getAccessToken: async () => "token", login: () => {}, logout: () => {}, identity: null });
      hoisted.setSource = (change) => setSource((now) => ({ ...now, ...change }));
      return render(source);
    },
  };
});

const WALLET = "0x1234567890abcdef1234567890abcdef1234abcd";

describe("the signed-in identity value", () => {
  it("shows a shortened wallet address and keeps the full address", () => {
    expect(signedInIdentity({ wallet: { address: WALLET }, email: { address: "person@example.com" } }))
      .toEqual({ shown: "0x1234…abcd", full: WALLET });
  });

  it("shows the email when the account has no wallet", () => {
    expect(signedInIdentity({ email: { address: "person@example.com" } }))
      .toEqual({ shown: "person@example.com", full: "person@example.com" });
  });

  it("shows nothing when the account has neither", () => {
    expect(signedInIdentity({})).toBeNull();
  });

  it("shows nothing when there is no user", () => {
    expect(signedInIdentity(null)).toBeNull();
  });
});

vi.mock("../components/ResearchHome", () => ({ ResearchHome: () => <p>Research home</p> }));
vi.mock("../components/Conversation", () => ({ Conversation: () => null }));

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <p data-testid="status">{auth.status}</p>
      <p data-testid="identity">{auth.identity?.shown ?? "none"}</p>
      <button type="button" onClick={auth.logout}>Sign out</button>
    </div>
  );
}

const IDENTITY = { shown: "0x1234…abcd", full: WALLET };
const expectState = (status: string, identity: string) => waitFor(() => {
  expect(screen.getByTestId("status")).toHaveTextContent(status);
  expect(screen.getByTestId("identity")).toHaveTextContent(identity);
});

describe("the signed-in identity in the auth context", () => {
  beforeEach(() => {
    delete window.__EDGE_OS_TEST_AUTH__;
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
    vi.stubEnv("NEXT_PUBLIC_PRIVY_APP_ID", "app-id");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ user_id: "owner-1" }),
      { status: 200, headers: { "content-type": "application/json" } })));
  });
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

  async function renderBridge() {
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(hoisted.setSource).not.toBeNull());
  }

  it("gives nothing while Privy is not ready", async () => {
    await renderBridge();
    act(() => hoisted.setSource?.({ identity: IDENTITY }));
    await expectState("loading", "none");
  });

  it("gives nothing while signed out", async () => {
    await renderBridge();
    act(() => hoisted.setSource?.({ ready: true, identity: IDENTITY }));
    await expectState("signed-out", "none");
  });

  it("gives the identity once the service accepts the session, and clears it on sign out", async () => {
    await renderBridge();
    act(() => hoisted.setSource?.({ ready: true, authenticated: true, identity: IDENTITY }));
    await expectState("ready", "0x1234…abcd");
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await expectState("signed-out", "none");
  });

  it("shows the identity directly above Sign out, with the full value in the title", async () => {
    render(<AuthRoot><Shell /></AuthRoot>);
    await waitFor(() => expect(hoisted.setSource).not.toBeNull());
    act(() => hoisted.setSource?.({ ready: true, authenticated: true, identity: IDENTITY }));
    const shown = await screen.findByText("0x1234…abcd");
    expect(shown).toHaveAttribute("title", WALLET);
    expect(shown.nextElementSibling).toBe(screen.getByRole("button", { name: "Sign out" }));
  });

  it("shows only Sign out for an account with neither a wallet nor an email", async () => {
    render(<AuthRoot><Shell /></AuthRoot>);
    await waitFor(() => expect(hoisted.setSource).not.toBeNull());
    act(() => hoisted.setSource?.({ ready: true, authenticated: true, identity: null }));
    const signOut = await screen.findByRole("button", { name: "Sign out" });
    expect(signOut.previousElementSibling).toBeNull();
  });
});

describe("the identity that the Privy bridge reports", () => {
  async function reported() {
    const { default: PrivyBridge } = await vi.importActual<typeof import("../lib/privy-bridge")>("../lib/privy-bridge");
    let source: Source | null = null;
    render(<PrivyBridge appId="app-id" render={(next) => { source = next; return null; }} />);
    return (source as Source | null)?.identity;
  }
  const user = { wallet: { address: WALLET }, email: { address: "person@example.com" } };

  it("reports the wallet of a signed-in Privy user", async () => {
    hoisted.privy = { ready: true, authenticated: true, user };
    expect(await reported()).toEqual(IDENTITY);
  });

  it("reports nothing when Privy is not ready", async () => {
    hoisted.privy = { ready: false, authenticated: true, user };
    expect(await reported()).toBeNull();
  });

  it("reports nothing when Privy says the person is signed out", async () => {
    hoisted.privy = { ready: true, authenticated: false, user };
    expect(await reported()).toBeNull();
  });
});
