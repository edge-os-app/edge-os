import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthRoot, useAuth } from "../lib/auth";

const hoisted = vi.hoisted(() => ({ emitLoginError: null as null | (() => void) }));
// The Privy bridge is replaced so the sign-in state machine can be driven without a Privy app.
vi.mock("../lib/privy-bridge", async () => {
  const React = await import("react");
  return {
    default: ({ render }: { render: (source: unknown) => React.ReactNode }) => {
      const [errors, setErrors] = React.useState(0);
      hoisted.emitLoginError = () => setErrors((n) => n + 1);
      return render({ ready: true, authenticated: false, getAccessToken: async () => null, login: () => {}, logout: () => {}, loginErrors: errors });
    },
  };
});

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <div data-testid="probe">{auth.status}|{auth.fixtureLabel ?? "no-fixture"}|{auth.unavailableReason ?? ""}|{auth.signInMessage ?? ""}|{auth.signInSlow ? "slow" : ""}</div>
      <button onClick={auth.login}>login</button>
      <button onClick={auth.logout}>logout</button>
    </div>
  );
}

const jsonResponse = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));

beforeEach(() => { delete window.__EDGE_OS_TEST_AUTH__; vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test"); });
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("auth session", () => {
  it("is unavailable, not signed in, when sign-in is not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_PRIVY_APP_ID", "");
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("unavailable|no-fixture|Sign-in is not configured"));
  });

  it("labels an injected test session and sends its token as a bearer header", async () => {
    const fetchMock = vi.fn(() => jsonResponse(200, { user_id: "u1" }));
    vi.stubGlobal("fetch", fetchMock);
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "token-123" };
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("ready|TEST AUTH FIXTURE"));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/v1/me");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-123");
  });

  it("falls back to signed out when the API rejects the credential", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(401, { code: "auth_invalid", findings: [] })));
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "bad" };
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("signed-out"));
  });

  it("reports the service as unavailable on 503, with a plain reason", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(503, { code: "auth_unavailable", findings: [] })));
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "t" };
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("cannot verify sign-in"));
  });

  it("fixture session: signing out and in again returns to the app", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(200, { user_id: "u1" })));
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "token-123" };
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("ready|"));
    fireEvent.click(screen.getByText("logout"));
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("signed-out|"));
    fireEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("ready|"));
  });

  it("a sign-in that ends in an error goes back to signed-out with a message", async () => {
    vi.stubEnv("NEXT_PUBLIC_PRIVY_APP_ID", "app-test");
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("signed-out|"));
    fireEvent.click(screen.getByText("login"));
    expect(screen.getByTestId("probe")).toHaveTextContent("signing-in|");
    act(() => hoisted.emitLoginError?.()); // the person closed the Privy window or sign-in failed
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("signed-out|"));
    expect(screen.getByTestId("probe")).toHaveTextContent(/did not finish/i);
  });

  it("a sign-in that is slow says so after a minute and stays usable, without leaving the sign-in window", async () => {
    vi.stubEnv("NEXT_PUBLIC_PRIVY_APP_ID", "app-test");
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("signed-out|"));
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByText("login"));
      await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
      expect(screen.getByTestId("probe")).toHaveTextContent("signing-in|");  // still waiting: the person may be typing a code
      expect(screen.getByTestId("probe")).toHaveTextContent("slow");
    } finally { vi.useRealTimers(); }
  });

  it("a rejected session returns to signed-out with a message, and signing in again works", async () => {
    let rejectNext = false;
    vi.stubGlobal("fetch", vi.fn((url: string) => (rejectNext && url.endsWith("/v1/research/requests"))
      ? jsonResponse(401, { code: "auth_invalid", findings: [] }) : jsonResponse(200, { user_id: "u1", requests: [], has_more: false })));
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "t" };
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("ready|"));
    rejectNext = true;
    const { api } = await import("../lib/api");
    await act(async () => { await api.list().catch(() => {}); });
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("signed-out|"));
    expect(screen.getByTestId("probe")).toHaveTextContent(/session was rejected/i);
    rejectNext = false;
    fireEvent.click(screen.getByText("login"));
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("ready|")); // a real second sign-in, not a dead loop
  });

  it("signing out removes what this app stored in the tab", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(200, { user_id: "u1" })));
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "t" };
    window.sessionStorage.setItem("edge-os:research-draft:u1", "{}");
    window.sessionStorage.setItem("other-app:keep", "1");
    render(<AuthRoot><Probe /></AuthRoot>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("ready|"));
    fireEvent.click(screen.getByText("logout"));
    expect(window.sessionStorage.getItem("edge-os:research-draft:u1")).toBeNull();
    expect(window.sessionStorage.getItem("other-app:keep")).toBe("1");
  });
});
