import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setTokenSource, setUnauthorizedHandler } from "../lib/api";

const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

beforeEach(() => { vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test/"); });
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); setTokenSource(async () => null); setUnauthorizedHandler(() => {}); });

describe("api client", () => {
  it("refreshes the token once after auth_expired and retries", async () => {
    const tokens = ["old", "fresh"]; setTokenSource(async () => tokens.shift() ?? null);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(reply(401, { code: "auth_expired", findings: [] }))
      .mockResolvedValueOnce(reply(200, { user_id: "u" }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await api.me()).toEqual({ user_id: "u" });
    const auth = fetchMock.mock.calls.map(([, init]) => new Headers((init as RequestInit).headers).get("Authorization"));
    expect(auth).toEqual(["Bearer old", "Bearer fresh"]);
  });

  it("does not retry other 401 codes and tells the session to sign out", async () => {
    setTokenSource(async () => "t"); const signedOut = vi.fn(); setUnauthorizedHandler(signedOut);
    const fetchMock = vi.fn().mockResolvedValue(reply(401, { code: "auth_invalid", findings: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(signedOut).toHaveBeenCalled();
  });

  it("never puts the token in the URL and sends no owner field", async () => {
    setTokenSource(async () => "secret-token");
    const fetchMock = vi.fn().mockResolvedValue(reply(201, {}));
    vi.stubGlobal("fetch", fetchMock);
    await api.submit({ original_request: "x", restrictions: [], requested_job: "CREATE_STRATEGY", input_class: "LOOSE_INTUITION" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/v1/research/requests");
    expect(url).not.toContain("secret-token");
    expect(String(init.body)).not.toMatch(/owner/);
  });

  it("gives up on a service that never answers and says so", async () => {
    vi.useFakeTimers();
    try {
      setTokenSource(async () => "t");
      vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      })));
      const pending = api.list().catch((error: unknown) => error);
      await vi.advanceTimersByTimeAsync(31_000);
      expect(await pending).toMatchObject({ status: 0, code: "timeout" });
    } finally { vi.useRealTimers(); }
  });

  it("reports an unreachable service as a network error", async () => {
    setTokenSource(async () => "t"); vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(api.list()).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("sends the user's own words, or a retry that names its earlier attempt, to the saved request", async () => {
    setTokenSource(async () => "t");
    const fetchMock = vi.fn().mockResolvedValue(reply(201, {}));
    vi.stubGlobal("fetch", fetchMock);
    await api.answer("req-1", { previous_revision_id: "rev-1", question_id: "choose-entry", answer_text: "up more than 2%" });
    await api.retryInterpretation("req-1", "attempt-1");
    await api.retryInterpretation("req-1", null);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url]) => url)).toEqual([
      "http://api.test/v1/research/requests/req-1/clarifications",
      "http://api.test/v1/research/requests/req-1/interpretation-retries",
      "http://api.test/v1/research/requests/req-1/interpretation-retries"]);
    expect(JSON.parse(String(calls[0][1].body))).toEqual({ previous_revision_id: "rev-1", question_id: "choose-entry", answer_text: "up more than 2%" });
    expect(JSON.parse(String(calls[1][1].body))).toEqual({ retry_of: "attempt-1" });
    expect(JSON.parse(String(calls[2][1].body))).toEqual({ retry_of: null });
  });
});
