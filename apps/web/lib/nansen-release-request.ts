import type { NansenReportBody } from "./api";

// The fixed Nansen request a composed operating release permits (`listing.operating_release`). The server compares
// every field of a new request with it and stays the final authority; this parser only refuses, before anything is
// sent, a release object the server could not accept, so the form never posts a guess or the authored defaults.

export type NansenReleaseRequest = Omit<NansenReportBody, "operation_id" | "request_key"> & {
  holder_query: { label_type: string; aggregate_by_entity: boolean; order_field: string; value_usd_min: number | null };
  flow_query: { label: string };
};
export type NansenReleaseEvidence = "PROVIDER_ACTUAL" | "RELEASE_STAND_IN_RESPONSE";
export interface NansenOperatingRelease {
  release_id: string; sha256: string; kind: "ACTUAL" | "STAND_IN"; evidence_class: NansenReleaseEvidence;
  request: NansenReleaseRequest;
}
export type NansenReleaseState =
  | { mode: "legacy" }
  | { mode: "released"; release: NansenOperatingRelease }
  | { mode: "blocked"; reason: string };

const EVIDENCE_FOR_KIND: Record<string, NansenReleaseEvidence> = { ACTUAL: "PROVIDER_ACTUAL", STAND_IN: "RELEASE_STAND_IN_RESPONSE" };
const REQUEST_KEYS = ["compute_seconds", "deadline_seconds", "flow_query", "holder_query", "limits", "operations",
  "token_address", "token_symbol", "window"];
const LIMIT_CAPS: Record<string, number> = { max_requests: 20, max_pages: 10, max_bytes: 5_000_000, per_page: 1000 };

class Refused extends Error {}

function record(value: unknown, what: string, keys: string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Refused(`the ${what} is missing or not an object`);
  const found = Object.keys(value).sort();
  if (found.join() !== [...keys].sort().join()) throw new Refused(`the ${what} fields are not the expected set`);
  return value as Record<string, unknown>;
}

function text(value: unknown, what: string, max: number): string {
  if (typeof value !== "string" || !value.length || value.length > max) throw new Refused(`the ${what} is not valid text`);
  return value;
}

function whole(value: unknown, what: string, max: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > max) {
    throw new Refused(`the ${what} is not a whole number from 1 to ${max}`);
  }
  return value;
}

function request(value: unknown): NansenReleaseRequest {
  const body = record(value, "release request", REQUEST_KEYS);
  const token_address = text(body.token_address, "token address", 42);
  if (!/^0x[0-9a-fA-F]{40}$/.test(token_address)) throw new Refused("the token address is not a 0x contract address");
  const window = record(body.window, "window", ["start_utc", "end_utc"]);
  const start_utc = text(window.start_utc, "window start", 40), end_utc = text(window.end_utc, "window end", 40);
  const [from, to] = [Date.parse(start_utc), Date.parse(end_utc)];
  if (!Number.isFinite(from) || !Number.isFinite(to) || from >= to) throw new Refused("the window does not start before it ends");
  const operations = body.operations;
  if (!Array.isArray(operations) || !operations.length || new Set(operations).size !== operations.length
    || !operations.every((item) => item === "holders" || item === "flows")) {
    throw new Refused("the records to collect are not holders and/or flows, each once");
  }
  const holder = record(body.holder_query, "holder query", ["label_type", "aggregate_by_entity", "order_field", "value_usd_min"]);
  if (typeof holder.aggregate_by_entity !== "boolean"
    || !(holder.value_usd_min === null || (typeof holder.value_usd_min === "number" && Number.isInteger(holder.value_usd_min)))) {
    throw new Refused("the holder query has a value of the wrong type");
  }
  const flow = record(body.flow_query, "flow query", ["label"]);
  const limits = record(body.limits, "limits", [...Object.keys(LIMIT_CAPS), "max_credits"]);
  const max_credits = text(limits.max_credits, "credit limit", 37);
  if (!/^(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$/.test(max_credits)) throw new Refused("the credit limit is not a decimal amount");
  return {
    token_address, token_symbol: text(body.token_symbol, "token symbol", 20), window: { start_utc, end_utc },
    operations: [...operations] as NansenReleaseRequest["operations"],
    holder_query: { label_type: text(holder.label_type, "holder label", 40), aggregate_by_entity: holder.aggregate_by_entity,
      order_field: text(holder.order_field, "holder order", 40), value_usd_min: holder.value_usd_min as number | null },
    flow_query: { label: text(flow.label, "flow label", 40) },
    limits: { max_requests: whole(limits.max_requests, "request limit", LIMIT_CAPS.max_requests),
      max_pages: whole(limits.max_pages, "page limit", LIMIT_CAPS.max_pages),
      max_bytes: whole(limits.max_bytes, "byte limit", LIMIT_CAPS.max_bytes), max_credits,
      per_page: whole(limits.per_page, "page size", LIMIT_CAPS.per_page) },
    deadline_seconds: whole(body.deadline_seconds, "deadline", 3600), compute_seconds: whole(body.compute_seconds, "compute limit", 3600),
  };
}

/** Reads the release part of a Nansen listing. A listing without `operating_release` keeps the authored form. */
export function readNansenRelease(listing: unknown): NansenReleaseState {
  if (typeof listing !== "object" || listing === null || !("operating_release" in listing)
    || (listing as { operating_release?: unknown }).operating_release === undefined) {
    return { mode: "legacy" };
  }
  try {
    const release = record((listing as { operating_release: unknown }).operating_release, "operating release",
      ["release_id", "sha256", "kind", "evidence_class", "request"]);
    const evidence = EVIDENCE_FOR_KIND[String(release.kind)];
    if (!evidence) throw new Refused("the release kind is not ACTUAL or STAND_IN");
    if (release.evidence_class !== evidence) throw new Refused(`the evidence class ${String(release.evidence_class)} does not match a ${String(release.kind)} release`);
    const sha256 = text(release.sha256, "release hash", 64);
    if (!/^[0-9a-f]{64}$/.test(sha256)) throw new Refused("the release hash is not a SHA-256 value");
    return { mode: "released", release: { release_id: text(release.release_id, "release name", 200), sha256, kind: release.kind as "ACTUAL" | "STAND_IN", evidence_class: evidence,
      request: request(release.request) } };
  } catch (failure) {
    if (failure instanceof Refused) return { mode: "blocked", reason: `The operating release could not be read: ${failure.message}.` };
    throw failure;
  }
}
