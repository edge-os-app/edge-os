import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthRoot, useAuth } from "../lib/auth";

function Probe() {
  const auth = useAuth();
  return <div data-testid="probe">{auth.status}|{auth.fixtureLabel ?? "no-fixture"}|{auth.unavailableReason ?? ""}</div>;
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
});
