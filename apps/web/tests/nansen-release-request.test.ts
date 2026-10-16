import { describe, expect, it } from "vitest";
import { readNansenRelease } from "../lib/nansen-release-request";

// SYNTHETIC fixture in the server's `operating_release` shape. Not a provider reply and not sponsor proof.
function released(over: Record<string, unknown> = {}, request: Record<string, unknown> = {}) {
  return {
    release_id: "nansen-flows-2026-10", sha256: "b".repeat(64), kind: "ACTUAL", evidence_class: "PROVIDER_ACTUAL",
    request: {
      token_address: "0xd8e004acba279417c04c0633cb5a21ceca207777", token_symbol: "MOE",
      window: { start_utc: "2026-10-08T00:00:00Z", end_utc: "2026-10-09T00:00:00Z" }, operations: ["flows"],
      holder_query: { label_type: "all_holders", aggregate_by_entity: false, order_field: "token_amount", value_usd_min: null },
      flow_query: { label: "smart_money" },
      limits: { max_requests: 3, max_pages: 1, max_bytes: 90000, max_credits: "2.5", per_page: 50 },
      deadline_seconds: 240, compute_seconds: 12, ...request },
    ...over };
}

describe("readNansenRelease", () => {
  it("keeps the authored form when the listing names no release", () => {
    expect(readNansenRelease({ available: true, jobs: [] })).toEqual({ mode: "legacy" });
  });

  it("returns the whole fixed flows-only request with its non-default limits and queries", () => {
    const state = readNansenRelease({ available: true, jobs: [], operating_release: released() });
    expect(state.mode).toBe("released");
    if (state.mode !== "released") return;
    expect(state.release).toEqual({ release_id: "nansen-flows-2026-10", sha256: "b".repeat(64), kind: "ACTUAL",
      evidence_class: "PROVIDER_ACTUAL", request: released().request });
    expect(state.release.request.limits).toEqual({ max_requests: 3, max_pages: 1, max_bytes: 90000, max_credits: "2.5", per_page: 50 });
  });

  it("accepts a holder-only stand-in release", () => {
    const state = readNansenRelease({ operating_release: released({ kind: "STAND_IN", evidence_class: "RELEASE_STAND_IN_RESPONSE" },
      { operations: ["holders"], holder_query: { label_type: "all_holders", aggregate_by_entity: true, order_field: "token_amount", value_usd_min: 1000 } }) });
    expect(state.mode).toBe("released");
  });

  it.each([
    ["a null release", null],
    ["a release without a request", released({ request: undefined })],
    ["an unknown evidence class", released({ evidence_class: "PROVIDER_MAYBE" })],
    ["a kind that conflicts with its evidence class", released({ kind: "STAND_IN" })],
    ["an unknown operation", released({}, { operations: ["holders", "trades"] })],
    ["a repeated operation", released({}, { operations: ["flows", "flows"] })],
    ["a window that ends before it starts", released({}, { window: { start_utc: "2026-10-09T00:00:00Z", end_utc: "2026-10-08T00:00:00Z" } })],
    ["a text limit", released({}, { limits: { max_requests: "3", max_pages: 1, max_bytes: 90000, max_credits: "2.5", per_page: 50 } })],
    ["a limit above the server cap", released({}, { limits: { max_requests: 21, max_pages: 1, max_bytes: 90000, max_credits: "2.5", per_page: 50 } })],
    ["a numeric credit limit", released({}, { limits: { max_requests: 3, max_pages: 1, max_bytes: 90000, max_credits: 2.5, per_page: 50 } })],
    ["an incomplete holder query", released({}, { holder_query: { label_type: "all_holders" } })],
    ["an extra request field", released({}, { max_cost: 1 })],
    ["a broken token address", released({}, { token_address: "0x12" })],
  ])("blocks a new request for %s with a reason", (_name, operating_release) => {
    const state = readNansenRelease({ operating_release });
    expect(state.mode).toBe("blocked");
    if (state.mode === "blocked") expect(state.reason).toMatch(/\S/);
  });

  it("never falls back to the authored request for a malformed release", () => {
    expect(readNansenRelease({ operating_release: "release" }).mode).toBe("blocked");
  });

  it("returns a copy that a later change to the listing cannot alter", () => {
    const listing = { operating_release: released() };
    const state = readNansenRelease(listing);
    (listing.operating_release.request.limits as Record<string, unknown>).max_requests = 20;
    if (state.mode === "released") expect(state.release.request.limits.max_requests).toBe(3);
  });
});
