import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RequestPage } from "../components/RequestPage";

const mocks = vi.hoisted(() => ({ get: vi.fn(), revision: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { status = 503; detail = "Unavailable"; },
  api: { get: (...args: unknown[]) => mocks.get(...args), revision: (...args: unknown[]) => mocks.revision(...args) },
}));

const strategy = {
  strategy_id: "strategy-1", domain: "SPOT", entry: { op: "constant", value: "1" },
  exit: { op: "constant", value: "1" }, invalidation: { state: "NOT_REQUESTED", source_ref: "user" },
  sizing: { kind: "FIXED_QUOTE", amount: "100", unit: "QUOTE:USDC" },
  cost_assumptions: { fee_rate: "0.003", slippage_rate: "0.005", source_ref: "user" },
  risk_limits: { max_quote_notional: "100", max_open_positions: 1 }, action_scope: [],
  execution_permission: { state: "NOT_GRANTED", mandate_ref: null }, warmup_buckets: 0,
  decision_interval_seconds: 300, data_inputs: [], additions: false, partial_exits: false,
  market: { network: "MONAD" },
};

const bundle = {
  interpreter: { kind: "FIXTURE", id: "test", notice: "" },
  intake: { record_id: "intake-1", created_at: "2026-01-01T00:00:00Z", content: { original_request: "test request", restrictions: [], input_class: "CONCRETE_THESIS", requested_job: "CREATE_STRATEGY" } },
  interpretations: [], clarifications: [], outcomes: [],
  drafts: [{ record_id: "draft-1", content: { source_syntax: strategy } }], publications: [],
  revisions: [{ strategy_id: "strategy-1", revision_id: "revision-1", content_sha256: "content-hash", manifest_sha256: "manifest-hash", created_at: "2026-01-01T00:00:00Z" }],
  head: { interpretation_revision_id: null, outcome: "PUBLISHED", questions: [], draft_id: "draft-1", strategy_id: "strategy-1" },
};

beforeEach(() => {
  mocks.get.mockReset().mockResolvedValue(bundle);
  mocks.revision.mockReset().mockResolvedValue({
    revision_id: "revision-1", content_sha256: "content-hash", manifest_sha256: "manifest-hash",
    stored_hash_matches_content: true, stored_manifest_hash_matches_content: false,
  });
});

describe("stored revision verification", () => {
  it("does not call a revision verified when its stored meaning manifest is corrupt", async () => {
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByText("Could not be confirmed.")).toBeInTheDocument();
    expect(screen.queryByText("Read back from the database. Its hash matches.")).toBeNull();
    expect(screen.queryByText(/Opened source record/)).toBeNull();
    expect(screen.queryByText(/source record .* is not in this detail/)).toBeNull();
  });

  it("shows the exact owner-verified source record on its saved Research detail", async () => {
    render(<RequestPage id="intake-1" sourceRecordId="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByText((_, element) => element?.tagName === "P" && element.textContent?.includes("Opened source record intake-1."))).toBeInTheDocument();
    expect(screen.getByText("test request")).toBeInTheDocument();
  });

  it("does not claim a source absent from the loaded owner-scoped request bundle", async () => {
    render(<RequestPage id="intake-1" sourceRecordId="unrelated-source" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByText((_, element) => element?.tagName === "P"
      && element.textContent?.includes("The saved request opened, but source record unrelated-source is not in this detail."))).toBeInTheDocument();
    expect(screen.queryByText(/Opened source record unrelated-source/)).toBeNull();
    expect(screen.getByText("test request")).toBeInTheDocument();
  });
});
