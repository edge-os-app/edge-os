import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchHome } from "../components/ResearchHome";
import { listTag, readingOf, type ReadingFacts } from "../lib/interpretation";
import type { RequestSummary } from "../lib/types";

const mocks = vi.hoisted(() => ({ list: vi.fn(), interpreter: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { status = 503; detail = "Unavailable"; },
  api: { list: (...a: unknown[]) => mocks.list(...a), interpreter: (...a: unknown[]) => mocks.interpreter(...a) },
}));

const facts = (over: Partial<ReadingFacts>): ReadingFacts => ({
  has_interpretation: false, outcome_present: false, last_attempt: null, last_covered: false, retry_allowed: true, ...over });
const attempt = (status: string, parse_result: string | null, id = "a1") => ({ attempt_id: id, status: status as never, parse_result });
const row = (over: Partial<RequestSummary>): RequestSummary => ({
  intake_record_id: "i1", created_at: "2026-10-10T08:00:00Z", original_request: "Buy when up", requested_job: "CREATE_STRATEGY",
  input_class: "CONCRETE_THESIS", outcome: null, published: false, ...over });

describe("the saved-requests tag follows the latest attempt's stored facts", () => {
  // Literal expectations, written from the stored facts, not computed by the code under test.
  const cases: [string, Partial<RequestSummary>, string][] = [
    ["never read", { reading: facts({}) }, "Saved, not read yet"],
    ["attempt started, no result", { reading: facts({ last_attempt: attempt("STARTED", null) }) }, "Attempt not finished"],
    ["accepted, not saved", { reading: facts({ last_attempt: attempt("COMPLETED", "ACCEPTED") }) }, "Read, not saved yet"],
    ["provider failed, outcome saved", { outcome: "INVALID_INPUT", outcome_code: "interpreter_unavailable",
      reading: facts({ outcome_present: true, last_covered: true, last_attempt: attempt("PROVIDER_FAILED", "NOT_PARSED") }) }, "Interpreter did not answer"],
    ["rejected, outcome saved", { outcome: "INVALID_INPUT", outcome_code: "malformed_model_output",
      reading: facts({ outcome_present: true, last_covered: true, last_attempt: attempt("COMPLETED", "REJECTED:multiple_objects") }) }, "Answer not usable"],
    ["unknown, outcome saved", { outcome: "INVALID_INPUT", outcome_code: "interpreter_outcome_unknown",
      reading: facts({ outcome_present: true, last_covered: true, last_attempt: attempt("TIMED_OUT", "NOT_PARSED") }) }, "Outcome unknown"],
    ["failed, then retry started (older outcome)", { outcome: "INVALID_INPUT", outcome_code: "interpreter_unavailable",
      reading: facts({ outcome_present: true, last_covered: false, last_attempt: attempt("STARTED", null, "a2") }) }, "Attempt not finished"],
    ["failed, then accepted and not saved (older outcome)", { outcome: "INVALID_INPUT", outcome_code: "interpreter_unavailable",
      reading: facts({ outcome_present: true, last_covered: false, last_attempt: attempt("COMPLETED", "ACCEPTED", "a2") }) }, "Read, not saved yet"],
    ["failed, then unknown without an outcome (older outcome)", { outcome: "INVALID_INPUT", outcome_code: "interpreter_unavailable",
      reading: facts({ outcome_present: true, last_covered: false, retry_allowed: false, last_attempt: attempt("TIMED_OUT", "NOT_PARSED", "a2") }) }, "Outcome unknown"],
    ["failed, then accepted and saved", { outcome: "NEEDS_CLARIFICATION", reading: facts({ has_interpretation: true, outcome_present: true, last_covered: true,
      last_attempt: attempt("COMPLETED", "ACCEPTED", "a2") }) }, "Needs your answer"],
    ["fixture request with its own outcome", { outcome: "INVALID_INPUT", reading: facts({ outcome_present: true }) }, "Could not be interpreted"],
    ["fixture request, no reading facts", { outcome: "UNSUPPORTED" }, "Not supported yet"],
    ["published", { published: true, outcome: "COMPILED" }, "Saved"],
  ];
  it.each(cases)("%s", (_name, over, title) => {
    expect(listTag(row(over)).title).toBe(title);
  });

  it("never says 'Could not be interpreted' for any Hermes state", () => {
    for (const [, over] of cases.filter(([, o]) => o.reading && !(o.reading.outcome_present && !o.reading.last_attempt))) {
      expect(listTag(row(over)).title).not.toBe("Could not be interpreted");
    }
  });

  it("uses the same function as the request page, so an unread request reads the same", () => {
    expect(readingOf(facts({}))?.title).toBe("Saved, not read yet");
  });
});

describe("the saved-requests list on the page", () => {
  beforeEach(() => { mocks.list.mockReset(); mocks.interpreter.mockReset().mockResolvedValue({ interpreter: { kind: "HERMES_LOCAL_FAKE_PROVIDER", id: "x", notice: "n" }, samples: [] }); });

  it("draws one tag per request from its own facts, without the verdict wording", async () => {
    mocks.list.mockResolvedValue({ has_more: false, requests: [
      row({ intake_record_id: "i1", reading: facts({}) }),
      row({ intake_record_id: "i2", reading: facts({ last_attempt: attempt("COMPLETED", "ACCEPTED") }) }),
      row({ intake_record_id: "i3", outcome: "INVALID_INPUT", outcome_code: "interpreter_unavailable",
        reading: facts({ outcome_present: true, last_covered: true, last_attempt: attempt("PROVIDER_FAILED", "NOT_PARSED") }) })] });
    render(<ResearchHome userId="u" go={vi.fn()} consumeReturn={() => null} />);
    expect(await screen.findByText("Saved, not read yet")).toBeInTheDocument();
    expect(screen.getByText("Read, not saved yet")).toBeInTheDocument();
    expect(screen.getByText("Interpreter did not answer")).toBeInTheDocument();
    expect(screen.queryByText("Could not be interpreted")).toBeNull();
  });
});
