import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InterpretationAttempts } from "../components/InterpretationAttempts";
import { RequestPage } from "../components/RequestPage";
import { describeAttemptCost, describeCredit, describeCreditSpend, describeModelBudget, describeModelCost, describeRoute, describeRouteSummary } from "../lib/interpretation";
import type { Attempt, AttemptSpend, ModelBudget, ModelCost } from "../lib/types";

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

const cost = (settledUsd: string | null, settledCalls: number, unknownCalls: number, held: string | null = null): ModelCost =>
  ({ settled_usd: settledUsd, settled_calls: settledCalls, unknown_calls: unknownCalls, unit: "CREDIT",
     settled_credit: settledUsd, held_credit: held });
const costRow = (item: HTMLElement) => within(item).getByText("Model cost").nextElementSibling as HTMLElement;

describe("model cost on the saved research result", () => {
  it("shows each settled cost exactly, and unknown for an unknown or missing spend record", () => {
    const total: ModelCost = cost("0.0074285", 1, 2);
    render(<InterpretationAttempts attempts={[attempt("a1", 1, settled), attempt("a2", 2, unknown), attempt("a3", 3, missing)]}
      modelCost={total} lateResults={[]} open />);
    const [first, second, third] = screen.getAllByRole("listitem");
    expect(costRow(first)).toHaveTextContent("$0.0074285");
    expect(costRow(second)).toHaveTextContent("Unknown");
    expect(costRow(third)).toHaveTextContent("Unknown");
    expect(screen.queryByText(/0\.054848/)).toBeNull(); // a reservation is never shown as the cost
    expect(screen.getByTestId("model-cost-total")).toHaveTextContent("Total model cost: at least $0.0074285, 2 calls unknown");
  });

  it("shows the total when every call settled", () => {
    render(<InterpretationAttempts attempts={[attempt("a1", 1, settled), attempt("a2", 2, settled)]}
      modelCost={cost("0.014857", 2, 0)} lateResults={[]} open={false} />);
    expect(screen.getByTestId("model-cost-total")).toHaveTextContent(/^Total model cost: \$0\.014857$/);
  });

  it("never shows zero when no call settled", () => {
    render(<InterpretationAttempts attempts={[attempt("a1", 1, unknown), attempt("a2", 2, missing)]}
      modelCost={cost(null, 0, 2)} lateResults={[]} open />);
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
    expect(describeModelCost(cost("0.0074285", 1, 1))).toBe("at least $0.0074285, 1 call unknown");
    expect(describeModelCost(cost(null, 0, 1))).toBe("unknown, 1 call unknown");
    expect(describeModelCost(cost("0.3", 2, 0))).toBe("$0.3");
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
      model_cost: cost("0.0074285", 1, 1),
      head: { interpretation_revision_id: null, outcome: null, questions: [], draft_id: null, strategy_id: null,
        retry: { allowed: false, retry_of: null, reason: "nothing_to_retry" }, reply: null },
    });
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByTestId("model-cost-total")).toHaveTextContent("Total model cost: at least $0.0074285, 1 call unknown");
  });
});

// --- CREDIT (ORBIO_CREDIT_DESIGN 2a) ---------------------------------------------------------------------------------
// CREDIT is Orbio's unit, exactly USD 1 of usage, so an amount in CREDIT is the same exact decimal string as in USD.
// UNKNOWN is never shown as zero, and a budget that is not set is not 0.

const heldUnknown: AttemptSpend = { state: "UNKNOWN", charge_usd: "0.17216" };
const budget: ModelBudget = { unit: "CREDIT", state: "SET", owner_cap_credit: "2", global_cap_credit: "2", settled_credit: "0.02784",
  held_credit: "0.17216", held_calls: 1, available_credit: "1.8", over_credit: "0" };

describe("CREDIT amounts", () => {
  it("prints the exact stored decimal with the CREDIT unit and refuses anything else", () => {
    expect(describeCredit("0.0074285")).toBe("0.0074285 CREDIT");
    expect(describeCredit("5E-7")).toBe("0.0000005 CREDIT");
    expect(describeCredit("2")).toBe("2 CREDIT");
    expect(describeCredit(null)).toBeNull();
    expect(describeCredit("-1")).toBeNull();
    expect(describeCredit("0.1e400")).toBeNull();
  });

  it("shows settled spend in CREDIT with its USD, a lower bound with unknown calls, and unknown when nothing settled", () => {
    expect(describeCreditSpend(cost("0.0074285", 1, 0))).toBe("spent 0.0074285 CREDIT (USD 0.0074285)");
    expect(describeCreditSpend(cost("0.0074285", 1, 2, "0.17216"))).toBe("at least 0.0074285 CREDIT, 2 calls unknown");
    expect(describeCreditSpend(cost(null, 0, 1, "0.17216"))).toBe("unknown, 1 call unknown");
    expect(describeCreditSpend(cost(null, 0, 2))).not.toMatch(/\b0 CREDIT/);
    expect(describeCreditSpend({ ...cost("0.0074285", 1, 0), settled_credit: "0.0074284" })).toBe("unknown");
  });

  it("shows the owner's shared budget with held calls as used, and a missing budget as not set", () => {
    expect(describeModelBudget(budget)).toBe(
      "available 1.8 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT; 0.17216 CREDIT held by 1 call of unknown cost");
    expect(describeModelBudget({ ...budget, held_credit: "0", held_calls: 0, available_credit: "1.97216" })).toBe(
      "available 1.97216 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT");
    expect(describeModelBudget({ ...budget, held_credit: "0.34432", held_calls: 2, available_credit: "1.62784" })).toBe(
      "available 1.62784 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT; 0.34432 CREDIT held by 2 calls of unknown cost");
    expect(describeModelBudget(null)).toBe("budget not set");
    expect(describeModelBudget({ ...budget, available_credit: "not-a-number" })).toBe("unknown");
    expect(describeModelBudget({ ...budget, held_calls: 1.5 })).toBe("unknown");
    expect(describeModelBudget({ unit: "CREDIT", state: "UNKNOWN" })).toBe("unknown"); // could not be read: not 0, not "not set"
  });

  it("shows the configured limits before the ledger's first use", () => {
    expect(describeModelBudget({ ...budget, settled_credit: "0", held_credit: "0", held_calls: 0, available_credit: "2" })).toBe(
      "available 2 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT");
  });

  it("shows 0 available and the overrun amount after a charge passes the cap", () => {
    const over = { ...budget, settled_credit: "2.05", held_credit: "0", held_calls: 0, available_credit: "0", over_credit: "0.05" };
    expect(describeModelBudget(over)).toBe(
      "0 available, over by 0.05 CREDIT; cap 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT");
    expect(describeModelBudget({ ...over, held_credit: "0.17216", held_calls: 1 })).toBe(
      "0 available, over by 0.05 CREDIT; cap 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT; 0.17216 CREDIT held by 1 call of unknown cost");
    expect(describeModelBudget({ ...over, over_credit: "not-a-number" })).toBe("unknown");
  });
});

describe("CREDIT on the attempts list", () => {
  it("renders an all-unknown study as unknown, never as 0 CREDIT", () => {
    render(<InterpretationAttempts attempts={[attempt("a1", 1, heldUnknown)]} modelCost={cost(null, 0, 1, "0.17216")}
      modelBudget={budget} lateResults={[]} open />);
    expect(screen.getByTestId("model-credit")).toHaveTextContent("Model spend: unknown, 1 call unknown");
    expect(screen.getByTestId("model-budget")).toHaveTextContent(
      "Model budget: available 1.8 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT; 0.17216 CREDIT held by 1 call of unknown cost");
    expect(document.body.textContent).not.toMatch(/\b0 CREDIT/);
  });

  it("renders a mixed study as a lower bound and a missing budget as not set", () => {
    render(<InterpretationAttempts attempts={[attempt("a1", 1, settled), attempt("a2", 2, heldUnknown)]}
      modelCost={cost("0.0074285", 1, 1, "0.17216")} modelBudget={null} lateResults={[]} open />);
    expect(screen.getByTestId("model-credit")).toHaveTextContent("Model spend: at least 0.0074285 CREDIT, 1 call unknown");
    expect(screen.getByTestId("model-budget")).toHaveTextContent("Model budget: budget not set");
    expect(screen.getByTestId("model-budget")).not.toHaveTextContent(/\b0 CREDIT/);
  });

  it("passes the bundle's budget through the saved request page", async () => {
    mocks.get.mockResolvedValue({
      interpreter: { kind: "HERMES_LIVE_RELEASE", id: "release-1", notice: "" },
      intake: { record_id: "intake-1", created_at: "2026-10-10T08:00:00Z", content: { original_request: "Buy when up", restrictions: [], input_class: "CONCRETE_THESIS", requested_job: "CREATE_STRATEGY" } },
      interpretations: [], clarifications: [], publications: [], drafts: [], revisions: [], outcomes: [], late_results: [],
      attempts: [attempt("a1", 1, settled)], model_cost: cost("0.0074285", 1, 0), model_budget: budget,
      head: { interpretation_revision_id: null, outcome: null, questions: [], draft_id: null, strategy_id: null,
        retry: { allowed: false, retry_of: null, reason: "nothing_to_retry" }, reply: null },
    });
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByTestId("model-credit")).toHaveTextContent("Model spend: spent 0.0074285 CREDIT (USD 0.0074285)");
    expect(screen.getByTestId("model-budget")).toHaveTextContent("Model budget: available 1.8 of 2 CREDIT");
  });

  it("shows the budget on a saved request with no attempts, and no cost lines", () => {
    render(<InterpretationAttempts attempts={[]} modelCost={cost(null, 0, 0)} modelBudget={{ ...budget, held_credit: "0", held_calls: 0, available_credit: "2" }} lateResults={[]} open={false} />);
    expect(screen.getByTestId("model-budget")).toHaveTextContent(
      "Model budget: available 2 of 2 CREDIT, shared by all your studies and limited by the global ceiling of 2 CREDIT");
    expect(screen.queryByTestId("model-credit")).toBeNull();
    expect(screen.queryByTestId("attempts")).toBeNull();
  });

  it("shows nothing with no attempts when the application reports no model cost", () => {
    const { container } = render(<InterpretationAttempts attempts={[]} lateResults={[]} open={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});

const routed = (route: string | null): Attempt => {
  const base = attempt("a-route", 1, settled);
  return { ...base, identity: { ...base.identity, route } };
};
const routeLine = () => screen.queryByText("Route")?.nextElementSibling?.textContent ?? null;

describe("the route on a saved attempt line", () => {
  it("names each saved route in plain words", () => {
    expect(describeRoute("orbio-openrouter-managed")).toBe("via Orbio");
    expect(describeRoute("openrouter-openai-standard")).toBe("via OpenRouter");
  });

  it("does not guess for a route with no saved value or no plain name", () => {
    expect(describeRoute(null)).toBeNull();
    expect(describeRoute("relay")).toBeNull();
  });

  it.each([["orbio-openrouter-managed", "via Orbio"], ["openrouter-openai-standard", "via OpenRouter"]])(
    "shows the attempt's own route %s", (route, words) => {
      render(<InterpretationAttempts attempts={[routed(route)]} lateResults={[]} open />);
      expect(routeLine()).toBe(words);
    });

  it.each([[null], ["relay"]])("shows no route line for %s", (route) => {
    render(<InterpretationAttempts attempts={[routed(route)]} lateResults={[]} open />);
    expect(screen.queryByText("Route")).toBeNull();
  });
});

const ORBIO = "orbio-openrouter-managed";
const OPENROUTER = "openrouter-openai-standard";
const attemptsOn = (...routes: (string | null)[]): Attempt[] => routes.map((route, index) => {
  const base = attempt(`a${index + 1}`, index + 1, settled);
  return { ...base, identity: { ...base.identity, route } };
});
const routeSummary = () => screen.queryByTestId("model-route-summary");

describe("the route summary near the study total", () => {
  it("says the model calls ran through Orbio when every attempt saved that route", () => {
    expect(describeRouteSummary(attemptsOn(ORBIO))).toBe("Model calls ran through Orbio");
    expect(describeRouteSummary(attemptsOn(ORBIO, ORBIO, ORBIO))).toBe("Model calls ran through Orbio");
  });

  it("counts the Orbio attempts when other attempts used another route", () => {
    expect(describeRouteSummary(attemptsOn(ORBIO, OPENROUTER))).toBe("1 of 2 model calls ran through Orbio");
    expect(describeRouteSummary(attemptsOn(ORBIO, ORBIO, "relay"))).toBe("2 of 3 model calls ran through Orbio");
  });

  it("never treats a missing route as Orbio", () => {
    expect(describeRouteSummary(attemptsOn(ORBIO, null))).toBe("1 of 2 model calls ran through Orbio");
    expect(describeRouteSummary(attemptsOn(null, ORBIO, OPENROUTER, null))).toBe("1 of 4 model calls ran through Orbio");
  });

  it("counts failed and unknown attempts, because they were sent on that route", () => {
    const [sent, failed, unknownOutcome] = attemptsOn(ORBIO, ORBIO, OPENROUTER);
    const attempts: Attempt[] = [sent, { ...failed, status: "PROVIDER_FAILED" }, { ...unknownOutcome, status: "UNKNOWN" }];
    expect(describeRouteSummary(attempts)).toBe("2 of 3 model calls ran through Orbio");
  });

  it.each([[[OPENROUTER]], [[OPENROUTER, OPENROUTER]], [[null]], [["relay", null]], [[]]])(
    "gives nothing when no attempt saved the Orbio route: %j", (routes) => {
      expect(describeRouteSummary(attemptsOn(...routes))).toBeNull();
    });

  it("sits directly after the cost lines, outside the closed attempts section", () => {
    render(<InterpretationAttempts attempts={attemptsOn(ORBIO, ORBIO)} modelCost={cost("0.014857", 2, 0)} modelBudget={budget}
      lateResults={[]} open={false} />);
    const line = screen.getByTestId("model-route-summary");
    expect(line).toHaveTextContent(/^Model calls ran through Orbio$/);
    expect(screen.getByTestId("attempts")).not.toHaveAttribute("open");
    expect(line.closest("details")).toBeNull();
    expect(screen.getByTestId("model-credit").nextElementSibling).toBe(line);
    expect(line.nextElementSibling).toBe(screen.getByTestId("model-budget"));
  });

  it("shows the count from a mixed list with a missing route", () => {
    render(<InterpretationAttempts attempts={attemptsOn(ORBIO, OPENROUTER, null)} modelCost={cost("0.02", 3, 0)} lateResults={[]} open={false} />);
    expect(routeSummary()).toHaveTextContent(/^1 of 3 model calls ran through Orbio$/);
  });

  it("does not need a model cost, because the saved route is enough", () => {
    render(<InterpretationAttempts attempts={attemptsOn(ORBIO)} lateResults={[]} open={false} />);
    expect(screen.queryByTestId("model-cost-total")).toBeNull();
    expect(routeSummary()).toHaveTextContent(/^Model calls ran through Orbio$/);
  });

  it("shows no line and no provider name for an OpenRouter study", () => {
    render(<InterpretationAttempts attempts={attemptsOn(OPENROUTER, OPENROUTER)} modelCost={cost("0.02", 2, 0)} lateResults={[]} open={false} />);
    expect(routeSummary()).toBeNull();
    expect(document.body.textContent).not.toMatch(/Orbio/);
    expect(screen.getByTestId("model-credit").nextElementSibling).toBe(screen.getByTestId("model-budget"));
  });

  it("shows no line for a study with no attempts", () => {
    render(<InterpretationAttempts attempts={[]} modelCost={cost(null, 0, 0)} modelBudget={budget} lateResults={[]} open={false} />);
    expect(routeSummary()).toBeNull();
  });
});
