import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InterpretationAttempts } from "../components/InterpretationAttempts";
import { RequestPage } from "../components/RequestPage";
import { describeAttemptCost, describeModelCost } from "../lib/interpretation";
import type { Attempt, AttemptSpend, ModelCost } from "../lib/types";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { status = 503; detail = "Unavailable"; },
  api: {
    get: (...a: unknown[]) => mocks.get(...a),
    investigations: () => new Promise(() => {}), investigationProposal: () => new Promise(() => {}),
  },
}));

const attempt = (id: string, sequence: number, spend: AttemptSpend): Attempt => ({
  attempt_id: id, sequence, retry_of: null, purpose: "INTERPRET", status: "COMPLETED", completion: "COMPLETE",
  started_at: "2026-10-10T08:00:00Z", finished_at: "2026-10-10T08:00:02Z", latency_ms: 2500,
  usage: { source: "PROVIDER_REPORTED", input_tokens: 1423, output_tokens: 611, total_tokens: 2034 }, request_count: 1,
  response_sha256: "a".repeat(64), parse_result: "ACCEPTED", error_class: null, revision_id: null, spend,
  identity: { prompt_version: "p05-interpretation/4", system_prompt_sha256: "b".repeat(64), task_sha256: "c".repeat(64),
    response_shape_sha256: "d".repeat(64), manifest_sha256: "e".repeat(64), config_sha256: "f".repeat(64),
    runtime_label: "LIVE", model: "model/1", route: "relay", hermes_commit: null, answer_ref: null, previous_revision_id: null },
});

const settled: AttemptSpend = { state: "SETTLED", charge_usd: "0.0074285" };
const unknown: AttemptSpend = { state: "UNKNOWN", charge_usd: "0.054848" }; // the held reservation, not a cost
const missing: AttemptSpend = { state: null, charge_usd: null }; // no spend record was saved

const costRow = (item: HTMLElement) => within(item).getByText("Model cost").nextElementSibling as HTMLElement;

describe("model cost on the saved research result", () => {
  it("shows each settled cost exactly, and unknown for an unknown or missing spend record", () => {
    const cost: ModelCost = { settled_usd: "0.0074285", settled_calls: 1, unknown_calls: 2 };
    render(<InterpretationAttempts attempts={[attempt("a1", 1, settled), attempt("a2", 2, unknown), attempt("a3", 3, missing)]}
      modelCost={cost} lateResults={[]} open />);
    const [first, second, third] = screen.getAllByRole("listitem");
    expect(costRow(first)).toHaveTextContent("$0.0074285");
    expect(costRow(second)).toHaveTextContent("Unknown");
    expect(costRow(third)).toHaveTextContent("Unknown");
    expect(screen.queryByText(/0\.054848/)).toBeNull(); // a reservation is never shown as the cost
    expect(screen.getByTestId("model-cost-total")).toHaveTextContent("Total model cost: at least $0.0074285, 2 calls unknown");
  });

  it("shows the total when every call settled", () => {
    render(<InterpretationAttempts attempts={[attempt("a1", 1, settled), attempt("a2", 2, settled)]}
      modelCost={{ settled_usd: "0.014857", settled_calls: 2, unknown_calls: 0 }} lateResults={[]} open={false} />);
    expect(screen.getByTestId("model-cost-total")).toHaveTextContent(/^Total model cost: \$0\.014857$/);
  });

  it("never shows zero when no call settled", () => {
    render(<InterpretationAttempts attempts={[attempt("a1", 1, unknown), attempt("a2", 2, missing)]}
      modelCost={{ settled_usd: null, settled_calls: 0, unknown_calls: 2 }} lateResults={[]} open />);
    expect(screen.getByTestId("model-cost-total")).toHaveTextContent("Total model cost: unknown, 2 calls unknown");
    expect(document.body.textContent).not.toMatch(/\$0(\.0+)?\b/);
  });

  it("describes amounts as stored and refuses anything that is not a settled decimal", () => {
    expect(describeAttemptCost(settled)).toBe("$0.0074285");
    expect(describeAttemptCost(unknown)).toBe("Unknown");
    expect(describeAttemptCost(missing)).toBe("Unknown");
    expect(describeAttemptCost({ state: "RELEASED", charge_usd: "0" })).toBe("Unknown");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: null })).toBe("Unknown");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "-1" })).toBe("Unknown");
    expect(describeModelCost({ settled_usd: "0.0074285", settled_calls: 1, unknown_calls: 1 })).toBe("at least $0.0074285, 1 call unknown");
    expect(describeModelCost({ settled_usd: null, settled_calls: 0, unknown_calls: 1 })).toBe("unknown, 1 call unknown");
    expect(describeModelCost({ settled_usd: "0.3", settled_calls: 2, unknown_calls: 0 })).toBe("$0.3");
  });
});

describe("charges the runner stored in exponent form", () => {
  it("shows them as plain decimals, digit for digit", () => {
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "5E-7" })).toBe("$0.0000005");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "1E-9" })).toBe("$0.000000001");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "1E+1" })).toBe("$10");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "1.25E+2" })).toBe("$125");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "1.5E-3" })).toBe("$0.0015");
    expect(describeAttemptCost({ state: "SETTLED", charge_usd: "1E+999" })).toBe("Unknown"); // not a plausible amount
  });
});

describe("the saved request page", () => {
  it("shows the study total the API computed beside the attempts", async () => {
    mocks.get.mockResolvedValue({
      interpreter: { kind: "HERMES_LIVE_RELEASE", id: "release-1", notice: "" },
      intake: { record_id: "intake-1", created_at: "2026-10-10T08:00:00Z", content: { original_request: "Buy when up", restrictions: [], input_class: "CONCRETE_THESIS", requested_job: "CREATE_STRATEGY" } },
      interpretations: [], clarifications: [], publications: [], drafts: [], revisions: [], outcomes: [], late_results: [],
      attempts: [attempt("a1", 1, settled), attempt("a2", 2, missing)],
      model_cost: { settled_usd: "0.0074285", settled_calls: 1, unknown_calls: 1 },
      head: { interpretation_revision_id: null, outcome: null, questions: [], draft_id: null, strategy_id: null,
        retry: { allowed: false, retry_of: null, reason: "nothing_to_retry" }, reply: null },
    });
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByTestId("model-cost-total")).toHaveTextContent("Total model cost: at least $0.0074285, 1 call unknown");
  });
});
