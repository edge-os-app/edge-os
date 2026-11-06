import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InterpretationAttempts } from "../components/InterpretationAttempts";
import { QuestionForm } from "../components/QuestionForm";
import { RequestPage } from "../components/RequestPage";
import { describeLatency, describeParse, describeUsage, sourceQuote, systemFailure } from "../lib/interpretation";
import type { Attempt, Question } from "../lib/types";

const mocks = vi.hoisted(() => ({ get: vi.fn(), retry: vi.fn(), answer: vi.fn(), revision: vi.fn(), investigations: vi.fn(), investigationProposal: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { constructor(public status = 503, public code = "x", public detail = "Unavailable") { super(detail); } },
  api: {
    get: (...a: unknown[]) => mocks.get(...a), retryInterpretation: (...a: unknown[]) => mocks.retry(...a),
    answer: (...a: unknown[]) => mocks.answer(...a), revision: (...a: unknown[]) => mocks.revision(...a),
    investigations: (...a: unknown[]) => mocks.investigations(...a), investigationProposal: (...a: unknown[]) => mocks.investigationProposal(...a),
    historySources: async () => ({ label: "", mode: "recorded", sources: [] }),
  },
}));

const choice: Question = { question_id: "choose-entry", kind: "CHOICE", field_name: "entry", text: "What should count as a rise for the entry rule?",
  options: [{ id: "a", label: "Up 1% over 15 minutes" }] };
const text: Question = { question_id: "ask-sizing", kind: "TEXT", field_name: "sizing", text: "What should the sizing be?", options: [] };
const adopt: Question = { question_id: "adopt-suggested-settings", kind: "ADOPT", text: "Review the suggested settings.", options: [{ id: "adopt", label: "Adopt" }],
  items: [{ field_name: "sizing", label: "Sizing", summary: "{}", origin: "AGENT_PROPOSED", question: "q?",
    value: { kind: "FIXED_QUOTE_AMOUNT", amount: "100", unit: "QUOTE:0x22" } }] };

describe("answering in your own words", () => {
  it("offers words beside a listed choice and sends them exactly as typed", async () => {
    const onReply = vi.fn(); const user = userEvent.setup();
    render(<QuestionForm questions={[choice]} busy={false} idPrefix="t" onAnswer={vi.fn()} onReply={onReply} />);
    const send = screen.getByRole("button", { name: /^Send my words/ });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /^Or say it in your own words/ }), "Up more than 2%");
    await user.click(send);
    expect(onReply).toHaveBeenCalledWith("choose-entry", "Up more than 2%", expect.any(HTMLFormElement));
  });

  it("asks a words-only question as a labelled text box, and hides it when the interpreter cannot read words", () => {
    const { rerender } = render(<QuestionForm questions={[text]} busy={false} idPrefix="t" onAnswer={vi.fn()} onReply={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "What should the sizing be?" })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    rerender(<QuestionForm questions={[choice, text]} busy={false} idPrefix="t" onAnswer={vi.fn()} />);
    expect(screen.queryByRole("textbox")).toBeNull(); // the fixture interpreter reads listed choices only
    expect(screen.getByRole("button", { name: "Save my answer" })).toBeInTheDocument();
  });

  it("gives each question's words box its own name, so two questions are never confused", () => {
    const exit: Question = { ...choice, question_id: "choose-exit", field_name: "exit", text: "When should the position be closed?" };
    render(<QuestionForm questions={[choice, exit]} busy={false} idPrefix="t" onAnswer={vi.fn()} onReply={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "Or say it in your own words. What should count as a rise for the entry rule?" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Or say it in your own words. When should the position be closed?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send my words. When should the position be closed?" })).toBeInTheDocument();
  });

  it("never offers words for the adoption review, and shows each suggestion in plain words", () => {
    render(<QuestionForm questions={[adopt]} busy={false} idPrefix="t" onAnswer={vi.fn()} onReply={vi.fn()} />);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("row", { name: /Sizing.*Fixed 100 quote units per entry.*Suggested/ })).toBeInTheDocument();
  });

  it("ignores a second send while one is in flight", async () => {
    const onReply = vi.fn(); const user = userEvent.setup();
    render(<QuestionForm questions={[choice]} busy idPrefix="t" onAnswer={vi.fn()} onReply={onReply} />);
    await user.type(screen.getByRole("textbox"), "words{Enter}");
    await user.click(screen.getByRole("button", { name: "Working…" }));
    expect(onReply).not.toHaveBeenCalled();
  });
});

const attempt = (over: Partial<Attempt>): Attempt => ({
  attempt_id: "a1", sequence: 1, retry_of: null, purpose: "INTERPRET", status: "COMPLETED", completion: "COMPLETE",
  started_at: "2026-10-10T08:00:00Z", finished_at: "2026-10-10T08:00:02Z", latency_ms: 2500,
  usage: { source: "PROVIDER_REPORTED", input_tokens: 1423, output_tokens: 611, total_tokens: 2034 }, request_count: 1,
  response_sha256: "a".repeat(64), parse_result: "ACCEPTED", error_class: null, revision_id: "r1",
  spend: { state: "SETTLED", charge_usd: "0.0074285" },
  identity: { prompt_version: "p05-interpretation/4", system_prompt_sha256: "b".repeat(64), task_sha256: "c".repeat(64),
    response_shape_sha256: "d".repeat(64), manifest_sha256: "e".repeat(64), config_sha256: "f".repeat(64),
    runtime_label: "LOCAL_FAKE_PROVIDER", model: "local-fake/p05-interpretation", route: "local-fake-provider",
    hermes_commit: "54bc5e509c985f37265c3d416bd2c64b10fc77ba", answer_ref: null, previous_revision_id: null }, ...over,
});

describe("interpreter attempts", () => {
  it("lists every attempt, keeps unknown usage unknown, and names a retry's parent", () => {
    const failed = attempt({ attempt_id: "a1", status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null,
      usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null }, error_class: "ProviderHTTPError", latency_ms: null,
      spend: { state: "UNKNOWN", charge_usd: "0.054848" } });
    const retry = attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1" });
    render(<InterpretationAttempts attempts={[failed, retry]} lateResults={[]} open currentRevisionId="r1" />);
    const [first, second] = screen.getAllByRole("listitem");
    expect(within(first).getByRole("heading", { name: "Read #1: First read" })).toBeInTheDocument();
    expect(within(first).getByText("Provider failed")).toBeInTheDocument(); // the raw class stays in Details
    expect(within(first).getByText(/error ProviderHTTPError/).closest("details")).not.toBeNull();
    expect(within(first).getAllByText("Unknown")).toHaveLength(3); // tokens, time and model cost
    expect(within(second).getByRole("heading", { name: "Read #2: First read, retry of #1" })).toBeInTheDocument();
    expect(within(second).getByText("1,423 in, 611 out")).toBeInTheDocument();
    expect(within(second).getByText("2.5 s")).toBeInTheDocument();
    expect(within(second).getByText("Accepted. Used for the current meaning")).toBeInTheDocument();
  });

  it("says a late result is evidence only", () => {
    render(<InterpretationAttempts attempts={[attempt({ status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })]}
      lateResults={[{ observation_id: "o1", attempt_id: "a1", observed_at: "2026-10-10T09:00:00Z", status: "COMPLETED", response_sha256: "a".repeat(64),
        authoritative: false, usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } }]} open />);
    expect(screen.getByTestId("late-result")).toHaveTextContent("A result arrived after read #1 was closed. It is kept as evidence and was not used.");
  });

  it("describes values without turning unknown into zero", () => {
    expect(describeUsage({ source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null })).toBe("Unknown");
    expect(describeLatency(0)).toBe("0 ms");
    expect(describeLatency(null)).toBe("Unknown");
    expect(describeParse("REJECTED:multiple_objects")).toBe("Rejected: multiple objects");
    expect(describeParse("NOT_PARSED")).toBe("No answer to read");
    expect(describeParse(null)).toBe("No result saved");
  });

  it("finds the exact words a source points at and refuses a reference that does not fit", () => {
    const request = "Buy when the 15-minute price return is above 1%, and exit when negative.";
    expect(sourceQuote("intake:original_request#c0-47", request)).toBe("Buy when the 15-minute price return is above 1%");
    expect(sourceQuote("reply:11111111-1111-4111-8111-111111111111#c0-10", request)).toBeNull();
    expect(sourceQuote("intake:original_request#c0-9999", request)).toBeNull();
    expect(systemFailure([{ code: "missing_capability", path: "/", detail: "" }])).toBeNull();
    expect(systemFailure([{ code: "interpreter_unavailable", path: "/", detail: "" }])).toBe("UNAVAILABLE");
  });

  it("counts the stored offsets in characters, so an emoji before or inside a passage does not shift the quote", () => {
    const original = "🚀 Buy when the 15-minute price return is above 1%";
    // the API stores code point offsets: the emoji is one character, the quote starts at 2 and ends at 49
    expect(sourceQuote("intake:original_request#c2-49", original)).toBe("Buy when the 15-minute price return is above 1%");
    const inside = "Buy 🚀 when above 1%";
    expect(sourceQuote("intake:original_request#c0-19", inside)).toBe("Buy 🚀 when above 1%");
    expect(sourceQuote("intake:original_request#c0-20", inside)).toBeNull();
  });
});

const baseBundle = (outcome: string, finding: { code: string; detail: string }, retry: object, attempts: Attempt[], reply: object | null = null) => ({
  interpreter: { kind: "HERMES_LOCAL_FAKE_PROVIDER", id: "p05-interpretation/4", notice: "Actual pinned Hermes ran against a local fake provider." },
  intake: { record_id: "intake-1", created_at: "2026-10-10T08:00:00Z", content: { original_request: "Buy when up", restrictions: [], input_class: "CONCRETE_THESIS", requested_job: "CREATE_STRATEGY" } },
  interpretations: [], clarifications: [], publications: [], drafts: [], revisions: [], attempts, late_results: [],
  outcomes: [{ interpretation_revision_id: null, record: { record_id: "o1", operation_id: attempts[attempts.length - 1]?.attempt_id ?? "none", content: { outcome, stage: "INTERPRETATION", code: "validation_error", retry: "SAFE_SAME_KEY", findings: [{ path: "/", ...finding }] } } }],
  head: { interpretation_revision_id: null, outcome, questions: [], draft_id: null, strategy_id: null, retry, reply },
});

const failedAttempt = attempt({ status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null,
  usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } });

beforeEach(() => {
  mocks.get.mockReset(); mocks.retry.mockReset(); mocks.answer.mockReset(); mocks.revision.mockReset();
  mocks.investigations.mockReset().mockReturnValue(new Promise(() => {})); mocks.investigationProposal.mockReset().mockReturnValue(new Promise(() => {}));
});

describe("system failures on the request page", () => {
  it("says a provider failure is a system failure, never a verdict on the idea, and retries only on request", async () => {
    const failed = baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "The model provider did not return a result." },
      { allowed: true, retry_of: "a1", reason: null }, [failedAttempt]);
    mocks.get.mockResolvedValue(failed);
    mocks.retry.mockResolvedValue(baseBundle("UNRESOLVED", { code: "missing_dependency", detail: "No research run exists." },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [failedAttempt, attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1" })]));
    const user = userEvent.setup();
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "The research agent did not answer" })).toBeInTheDocument();
    expect(screen.queryByText("Could not be interpreted")).toBeNull();
    expect(screen.getByText(/This is not a verdict on your idea/)).toBeInTheDocument();
    expect(mocks.retry).not.toHaveBeenCalled(); // nothing is retried until the user asks
    await user.click(screen.getByRole("button", { name: "Try the research agent again" }));
    expect(mocks.retry).toHaveBeenCalledWith("intake-1", "a1");
    expect(await screen.findByRole("heading", { name: "Unresolved: nothing was tested" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2); // both attempts stay listed
  });

  it("gives one plain message and no retry for an unknown outcome", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "interpreter_outcome_unknown", detail: "It is not known whether the provider finished." },
      { allowed: false, retry_of: null, reason: "outcome_uncertain" }, [attempt({ status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "We did not get an answer we can show you" })).toBeInTheDocument();
    expect(screen.getByText("Your request is saved. You may be charged for this read.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try the research agent again" })).toBeNull();
    expect(screen.queryByTestId("retry-blocked")).toBeNull();
    expect(screen.queryByTestId("failure-detail")).toBeNull();
    expect(screen.queryByText(/It is not known|may or may not|No strategy was created/)).toBeNull();
  });

  const kept = (overrides: Partial<Attempt>) => attempt({ error_class: "RelayCostUnverified", request_count: 1,
    spend: { state: "UNKNOWN", charge_usd: "0.17216" }, identity: { ...attempt({}).identity, route: "orbio-list-price" }, ...overrides });

  it("shows a kept answer as ready, its cost as unknown and its Orbio route", async () => {
    mocks.get.mockResolvedValue({ ...baseBundle("UNRESOLVED", { code: "x", detail: "Nothing was tested." },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [kept({})]),
    model_cost: { settled_usd: null, settled_calls: 0, unknown_calls: 1, unit: "CREDIT", settled_credit: null, held_credit: "0.17216" } });
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByTestId("cost-not-confirmed")).toHaveTextContent(/^Answer ready\. Cost not confirmed yet\.$/);
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.getByText("Finished")).toBeInTheDocument();
    expect(screen.getByText(/error RelayCostUnverified/).closest("details")).not.toBeNull();
    expect(screen.queryByText(/\$0\b|0 CREDIT/)).toBeNull();
  });

  it("gives a reply it could not use the plain words and no retry when its cost is open", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "interpreter_outcome_unknown", detail: "Saved words." },
      { allowed: false, retry_of: null, reason: "outcome_uncertain" },
      [kept({ status: "UNKNOWN", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    await screen.findByRole("heading", { name: "We did not get an answer we can show you" });
    expect(screen.getByText("Your request is saved. You may be charged for this read.")).toBeInTheDocument();
    expect(screen.queryByTestId("cost-not-confirmed")).toBeNull();
    expect(screen.queryByRole("button", { name: "Try the research agent again" })).toBeNull();
  });

  it("does not call an answer ready before it is saved", async () => {
    mocks.get.mockResolvedValue(baseBundle("UNRESOLVED", { code: "x", detail: "Nothing was tested." },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [kept({ revision_id: null })]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    await screen.findByTestId("outcome");
    expect(screen.queryByTestId("cost-not-confirmed")).toBeNull();
  });

  it("explains a reply the ledger refused in one plain sentence, with no retry and no raw class in the main text", async () => {
    mocks.get.mockResolvedValue(baseBundle("UNRESOLVED", { code: "x", detail: "Nothing was tested." }, { allowed: true, retry_of: "a2", reason: null }, [
      kept({}), attempt({ attempt_id: "a2", sequence: 2, status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null,
        error_class: "SpendScopeBlocked", request_count: 0 })],
    { state: "FAILED", reason_code: "cost_not_confirmed", attempt_id: "a2" }));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    const section = await screen.findByTestId("reply-state");
    expect(section).toHaveTextContent("You can't reply to this request yet, because its cost is not confirmed. Start a new request to continue.");
    expect(section).not.toHaveTextContent("SpendScopeBlocked");
    expect(screen.queryByRole("button", { name: "Try this reply again" })).toBeNull();
  });

  it("gives an uncertain reply the same plain words", async () => {
    mocks.get.mockResolvedValue(baseBundle("UNRESOLVED", { code: "x", detail: "Nothing was tested." }, { allowed: false, retry_of: null, reason: "outcome_uncertain" },
      [attempt({ status: "UNKNOWN", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })],
      { state: "UNCERTAIN", reason_code: null, attempt_id: "a1" }));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    const section = await screen.findByTestId("reply-state");
    expect(section).toHaveTextContent("We did not get an answer we can show you");
    expect(section).toHaveTextContent("You may be charged for this read.");
    expect(section).not.toHaveTextContent("may or may not");
  });

  it("names malformed model output separately from a provider failure", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "malformed_model_output", detail: "The model's answer could not be used (reason: multiple_objects)." },
      { allowed: true, retry_of: "a1", reason: null }, [attempt({ parse_result: "REJECTED:multiple_objects", revision_id: null })]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "The research agent's answer was not usable" })).toBeInTheDocument();
    expect(screen.getByTestId("failure-detail")).toHaveTextContent("multiple_objects");
    expect(screen.getByText("Rejected: multiple objects")).toBeInTheDocument(); // in the attempt list
  });

  it("keeps the saved meaning and the questions when a reply was rejected", async () => {
    const bundle = baseBundle("NEEDS_CLARIFICATION", { code: "missing_field", detail: "What should the entry rule be?" },
      { allowed: true, retry_of: "a2", reason: null }, [attempt({}), attempt({ attempt_id: "a2", sequence: 2, purpose: "FOLLOW_UP", revision_id: null, parse_result: "REJECTED:silent_overwrite" })],
      { state: "REJECTED", reason_code: "silent_overwrite", attempt_id: "a2" });
    bundle.head.interpretation_revision_id = "rev-1" as never;
    bundle.head.questions = [choice] as never;
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Your last reply could not be used" })).toBeInTheDocument();
    expect(screen.getByText(/Your saved meaning did not change/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Or say it in your own words/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try this reply again" })).toBeInTheDocument();
  });

  it("tells the user a reply that matched the saved meaning changed nothing", async () => {
    const bundle = baseBundle("NEEDS_CLARIFICATION", { code: "missing_field", detail: "What should the entry rule be?" },
      { allowed: true, retry_of: "a2", reason: null }, [attempt({}), attempt({ attempt_id: "a2", sequence: 2, purpose: "FOLLOW_UP", revision_id: null, parse_result: "REJECTED:reply_changed_nothing" })],
      { state: "REJECTED", reason_code: "reply_changed_nothing", attempt_id: "a2" });
    bundle.head.interpretation_revision_id = "rev-1" as never;
    bundle.head.questions = [choice] as never;
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByText(/matched what is already saved, so nothing changed/)).toBeInTheDocument();
  });

  it("does not say 'You said' for a field the user has not stated", async () => {
    const bundle = baseBundle("NEEDS_CLARIFICATION", { code: "missing_field", detail: "What should the exit be?" },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({})]);
    bundle.head.interpretation_revision_id = "rev-1" as never;
    (bundle as { interpretations: unknown[] }).interpretations = [{ content: { interpretation_revision_id: "rev-1", field_evidence: [
      { field_name: "exit", state: "MISSING", origin: "USER_STATED", source_ref: "intake:original_request", interpretation_revision: "rev-1", evidence_status: "UNKNOWN" }] } }];
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    const row = (await screen.findAllByRole("row")).find((r) => r.textContent?.includes("Exit rule"));
    expect(row).toHaveTextContent("Not stated yet");
    expect(row).not.toHaveTextContent("You said");
  });

  it("keeps one status region on the page so a change is announced", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "x" },
      { allowed: true, retry_of: "a1", reason: null }, [failedAttempt]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    await screen.findByRole("heading", { name: "The research agent did not answer" });
    expect(screen.getByTestId("working")).toHaveAttribute("role", "status");
    expect(screen.getByTestId("working")).toBeEmptyDOMElement();
  });

  it("says an accepted reply that is not saved yet was read, and does not call it a failure", async () => {
    const bundle = baseBundle("NEEDS_CLARIFICATION", { code: "missing_field", detail: "What should the entry rule be?" },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({}), attempt({ attempt_id: "a2", sequence: 2, purpose: "FOLLOW_UP", revision_id: null })],
      { state: "PENDING_SAVE", reason_code: null, attempt_id: "a2" });
    bundle.head.interpretation_revision_id = "rev-1" as never;
    bundle.head.questions = [choice] as never;
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Your last reply was read but is not saved yet" })).toBeInTheDocument();
    expect(screen.queryByText(/system failure/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Try this reply again" })).toBeNull();
  });

  it("does not mark the status region busy, so its announcement is not held back", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "x" },
      { allowed: true, retry_of: "a1", reason: null }, [failedAttempt]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    await screen.findByRole("heading", { name: "The research agent did not answer" });
    expect(screen.getByTestId("working")).not.toHaveAttribute("aria-busy");
  });

  it("offers a way forward for a request that was saved but never reached an attempt, and calls it neither a failure nor a verdict", async () => {
    const saved = baseBundle("INVALID_INPUT", { code: "x", detail: "y" }, { allowed: true, retry_of: null, reason: null }, []);
    saved.outcomes = [] as never;
    saved.head.outcome = null as never;
    mocks.get.mockResolvedValue(saved);
    mocks.retry.mockResolvedValue(baseBundle("UNRESOLVED", { code: "missing_dependency", detail: "No research run exists." },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({})]));
    const user = userEvent.setup();
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Saved, not read yet" })).toBeInTheDocument();
    expect(screen.queryByText("Could not be interpreted")).toBeNull();
    expect(screen.queryByText(/could not be interpreted|not a verdict on your idea/i)).toBeNull();
    expect(mocks.retry).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Read my request now" }));
    expect(mocks.retry).toHaveBeenCalledWith("intake-1", null);
  });
});

describe("a first request with no saved outcome and no revision", () => {
  const noOutcome = (attempts: Attempt[], retry: object) => {
    const bundle = baseBundle("INVALID_INPUT", { code: "x", detail: "y" }, retry, attempts);
    bundle.outcomes = [] as never;
    bundle.head.outcome = null as never;
    return bundle;
  };
  const show = async (bundle: unknown) => {
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    return screen.findByTestId("outcome");
  };
  const wrongClaims = () => {
    expect(screen.queryByText("Could not be interpreted")).toBeNull();
    expect(screen.queryByText(/No strategy was created/)).toBeNull();
  };

  it("says an attempt that has not finished may be running or stopped, and claims nothing about current activity", async () => {
    const section = await show(noOutcome([attempt({ status: "STARTED", completion: "UNKNOWN", finished_at: null, latency_ms: null, parse_result: null, revision_id: null,
      usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } })], { allowed: false, retry_of: null, reason: "attempt_in_flight" }));
    expect(section).toHaveAttribute("data-reading", "RUNNING_OR_STOPPED");
    expect(screen.getByRole("heading", { name: "A research-agent read has not finished" })).toBeInTheDocument();
    expect(screen.getByTestId("reading-state")).toHaveTextContent("may still be running, or it may have stopped");
    expect(screen.getByTestId("reading-state")).not.toHaveTextContent(/is reading|is running now|working now/i);
    expect(screen.getByTestId("retry-blocked")).toHaveTextContent("may still be running");
    expect(screen.getByTestId("retry-blocked")).not.toHaveTextContent(/is still running|Wait for it/);
    expect(screen.queryByRole("button", { name: /Try the research agent again|Read my request now/ })).toBeNull();
    wrongClaims();
  });

  it("says an accepted answer was read and is waiting to be saved, and does not call it a failure", async () => {
    const section = await show(noOutcome([attempt({ revision_id: null })], { allowed: false, retry_of: null, reason: "nothing_to_retry" }));
    expect(section).toHaveAttribute("data-reading", "READ_NOT_SAVED");
    expect(screen.getByRole("heading", { name: "Your request was read, and the answer is not saved yet" })).toBeInTheDocument();
    expect(screen.getByTestId("reading-state")).toHaveTextContent("answer was accepted");
    expect(screen.queryByText(/system failure|did not answer|not usable/)).toBeNull();
    wrongClaims();
  });

  it("offers the retry button for a settled provider failure whose outcome was not saved", async () => {
    mocks.retry.mockResolvedValue(baseBundle("UNRESOLVED", { code: "m", detail: "n" }, { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({})]));
    const user = userEvent.setup();
    const section = await show(noOutcome([failedAttempt], { allowed: true, retry_of: "a1", reason: null }));
    expect(section).toHaveAttribute("data-reading", "FAILED");
    expect(screen.getByRole("heading", { name: "The research agent did not answer" })).toBeInTheDocument();
    expect(mocks.retry).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Try the research agent again" }));
    expect(mocks.retry).toHaveBeenCalledWith("intake-1", "a1");
    wrongClaims();
  });

  it("names a rejected answer with its reason and offers the retry button", async () => {
    await show(noOutcome([attempt({ parse_result: "REJECTED:multiple_objects", revision_id: null })], { allowed: true, retry_of: "a1", reason: null }));
    expect(screen.getByRole("heading", { name: "The research agent's answer was not usable" })).toBeInTheDocument();
    expect(screen.getByTestId("reading-state")).toHaveTextContent("Reason: multiple objects");
    expect(screen.getByRole("button", { name: "Try the research agent again" })).toBeInTheDocument();
  });

  it.each(["TIMED_OUT", "UNKNOWN", "INTERRUPTED"] as const)("gives one plain message for %s and offers no retry", async (status) => {
    const section = await show(noOutcome([attempt({ status, completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })],
      { allowed: false, retry_of: null, reason: "outcome_uncertain" }));
    expect(section).toHaveAttribute("data-reading", "UNCERTAIN");
    expect(screen.getByRole("heading", { name: "We did not get an answer we can show you" })).toBeInTheDocument();
    expect(screen.getByTestId("reading-state")).toHaveTextContent(/^Your request is saved\. You may be charged for this read\.$/);
    expect(screen.queryByTestId("retry-blocked")).toBeNull();
    expect(screen.queryByRole("button", { name: /Try the research agent again|Read my request now/ })).toBeNull();
    wrongClaims();
  });

  it("looks at the saved record again without starting an attempt, and shows what is saved by then", async () => {
    const user = userEvent.setup();
    const stuck = noOutcome([attempt({ revision_id: null })], { allowed: false, retry_of: null, reason: "nothing_to_retry" });
    mocks.get.mockResolvedValueOnce(stuck).mockResolvedValueOnce(baseBundle("UNRESOLVED", { code: "m", detail: "n" },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({})]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Check the saved request again" }));
    expect(await screen.findByRole("heading", { name: "Unresolved: nothing was tested" })).toBeInTheDocument();
    expect(mocks.retry).not.toHaveBeenCalled();
    expect(mocks.answer).not.toHaveBeenCalled();
    expect(mocks.get).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("heading", { name: "Unresolved: nothing was tested" })).toHaveFocus(); // focus follows the new state
  });

  it("moves focus to the state heading after 'Read my request now' and says it is starting, not retrying", async () => {
    const user = userEvent.setup();
    mocks.get.mockResolvedValue(noOutcome([], { allowed: true, retry_of: null, reason: null }));
    let finish: (value: unknown) => void = () => {};
    mocks.retry.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Read my request now" }));
    expect(await screen.findByTestId("working")).toHaveTextContent("Starting the research agent");
    expect(screen.getByTestId("working")).not.toHaveTextContent("Trying the research agent again");
    finish(baseBundle("UNRESOLVED", { code: "m", detail: "n" }, { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({})]));
    expect(await screen.findByRole("heading", { name: "Unresolved: nothing was tested" })).toHaveFocus();
  });

  it("does not offer the investigation plan beside a request the interpreter has not read or failed to read", async () => {
    const bundle = noOutcome([failedAttempt], { allowed: true, retry_of: "a1", reason: null });
    bundle.intake.content.requested_job = "INVESTIGATE_EFFECT" as never;
    await show(bundle);
    expect(screen.queryByText("Investigation plan")).toBeNull();
    expect(mocks.investigations).not.toHaveBeenCalled();
  });

  it("does offer the investigation plan once the request has an interpretation (positive control)", async () => {
    const bundle = baseBundle("UNRESOLVED", { code: "m", detail: "n" }, { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [attempt({})]);
    bundle.intake.content.requested_job = "INVESTIGATE_EFFECT" as never;
    bundle.head.interpretation_revision_id = "rev-1" as never;
    (bundle as { interpretations: unknown[] }).interpretations = [{ record_id: "r1", content: { interpretation_revision_id: "rev-1", field_evidence: [] } }];
    await show(bundle);
    expect(await screen.findByText("Investigation plan")).toBeInTheDocument();
    expect(mocks.investigations).toHaveBeenCalled();
  });

  it("draws the state in the neutral grey style, not as an error and not as a prompt for an answer", async () => {
    const section = await show(noOutcome([], { allowed: true, retry_of: null, reason: null }));
    expect(section.className).toMatch(/\bstop\b/);
    expect(section.className).not.toMatch(/err|ok/);
  });

  it("leaves a request that has a saved outcome untouched", async () => {
    const section = await show(baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "x" }, { allowed: true, retry_of: "a1", reason: null }, [failedAttempt]));
    expect(section).not.toHaveAttribute("data-reading");
    expect(section).toHaveAttribute("data-outcome", "INVALID_INPUT");
  });

  it("words the request from the LATEST attempt when an earlier attempt has its own outcome: failed, then unknown", async () => {
    const first = attempt({ attempt_id: "a1", status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null,
      usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } });
    const second = attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1", status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null });
    const bundle = baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "The model provider did not return a result." },
      { allowed: false, retry_of: null, reason: "outcome_uncertain" }, [first, second]);
    bundle.outcomes[0].record.operation_id = "a1"; // only attempt 1 has an outcome
    const section = await show(bundle);
    expect(section).toHaveAttribute("data-reading", "UNCERTAIN");
    expect(screen.getByRole("heading", { name: "We did not get an answer we can show you" })).toBeInTheDocument();
    expect(screen.queryByText("The research agent did not answer")).toBeNull();
    expect(screen.queryByText(/did not return a result|You can try again/)).toBeNull();
    expect(screen.queryByTestId("retry-blocked")).toBeNull();
  });

  it("says the latest attempt was read and is not saved when an earlier attempt failed: failed, then accepted but unsaved", async () => {
    const first = attempt({ attempt_id: "a1", status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null });
    const second = attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1", revision_id: null });
    const bundle = baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "The model provider did not return a result." },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [first, second]);
    bundle.outcomes[0].record.operation_id = "a1";
    const section = await show(bundle);
    expect(section).toHaveAttribute("data-reading", "READ_NOT_SAVED");
    expect(screen.queryByText(/system failure|did not return a result|A retry is not available/)).toBeNull();
  });

  it("does not claim an earlier failure describes a retry that has started: failed, then started", async () => {
    const first = attempt({ attempt_id: "a1", status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null });
    const second = attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1", status: "STARTED", completion: "UNKNOWN", finished_at: null, parse_result: null, revision_id: null });
    const bundle = baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "x" }, { allowed: false, retry_of: null, reason: "attempt_in_flight" }, [first, second]);
    bundle.outcomes[0].record.operation_id = "a1";
    const section = await show(bundle);
    expect(section).toHaveAttribute("data-reading", "RUNNING_OR_STOPPED");
    expect(screen.queryByText("The research agent did not answer")).toBeNull();
  });

  it("keeps the outcome of the latest attempt when that attempt has one: failed, then failed again", async () => {
    const first = attempt({ attempt_id: "a1", status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null });
    const second = attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1", parse_result: "REJECTED:multiple_objects", revision_id: null });
    const bundle = baseBundle("INVALID_INPUT", { code: "malformed_model_output", detail: "The model's answer could not be used (reason: multiple_objects)." },
      { allowed: true, retry_of: "a2", reason: null }, [first, second]);
    bundle.outcomes = [
      { interpretation_revision_id: null, record: { record_id: "o1", operation_id: "a1", content: { outcome: "INVALID_INPUT", stage: "INTERPRETATION", code: "validation_error", retry: "SAFE_SAME_KEY", findings: [{ path: "/", code: "interpreter_unavailable", detail: "provider" }] } } },
      bundle.outcomes[0]] as never;
    bundle.outcomes[1].record.operation_id = "a2";
    const section = await show(bundle);
    expect(section).not.toHaveAttribute("data-reading");
    expect(screen.getByRole("heading", { name: "The research agent's answer was not usable" })).toBeInTheDocument();
    expect(screen.getByTestId("failure-detail")).toHaveTextContent("multiple_objects");
  });

  it("does not label an attempt with no saved result as running", () => {
    render(<InterpretationAttempts attempts={[attempt({ status: "STARTED", completion: "UNKNOWN", finished_at: null, parse_result: null, revision_id: null })]} lateResults={[]} open />);
    expect(screen.queryByText("Running")).toBeNull();
    expect(screen.getByText("Started, no result saved")).toBeInTheDocument();
  });

  it("says a reply attempt with no saved result may be running or stopped, and makes no claim of activity", async () => {
    const bundle = baseBundle("NEEDS_CLARIFICATION", { code: "missing_field", detail: "What should the entry rule be?" },
      { allowed: false, retry_of: null, reason: "attempt_in_flight" }, [attempt({}), attempt({ attempt_id: "a2", sequence: 2, purpose: "FOLLOW_UP", status: "STARTED", completion: "UNKNOWN", finished_at: null, parse_result: null, revision_id: null })],
      { state: "UNFINISHED", reason_code: null, attempt_id: "a2" });
    bundle.head.interpretation_revision_id = "rev-1" as never;
    bundle.head.questions = [choice] as never;
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Your last reply has no saved result" })).toBeInTheDocument();
    expect(screen.getByText(/may still be running, or it may have stopped/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try this reply again" })).toBeNull();
    expect(screen.queryByText(/system failure|was not read/)).toBeNull();
  });

  it("says an attempt used for an earlier meaning was used for an earlier meaning", () => {
    render(<InterpretationAttempts attempts={[attempt({ revision_id: "rev-old" })]} lateResults={[]} open currentRevisionId="rev-new" />);
    expect(screen.getByText("Accepted. Used for an earlier meaning")).toBeInTheDocument();
    expect(screen.queryByText(/current meaning/)).toBeNull();
  });

  it("never invites a choice that does not exist, and says investigation for an investigation", async () => {
    const bundle = baseBundle("NEEDS_CLARIFICATION", { code: "missing_field", detail: "Adopt the suggested market?" },
      { allowed: true, retry_of: "a2", reason: null }, [attempt({}), attempt({ attempt_id: "a2", sequence: 2, purpose: "FOLLOW_UP", revision_id: null, parse_result: "REJECTED:reply_changed_nothing" })],
      { state: "REJECTED", reason_code: "reply_changed_nothing", attempt_id: "a2" });
    bundle.intake.content.requested_job = "INVESTIGATE_EFFECT" as never;
    bundle.head.interpretation_revision_id = "rev-1" as never;
    bundle.head.questions = [adopt] as never;
    (bundle as { interpretations: unknown[] }).interpretations = [{ record_id: "r1", content: { interpretation_revision_id: "rev-1", field_evidence: [] } }];
    mocks.get.mockResolvedValue(bundle);
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByText(/before the investigation can be reviewed/)).toBeInTheDocument();
    expect(screen.queryByText(/choose an option/)).toBeNull();
    expect(screen.getAllByText(/answer one of the questions/).length).toBeGreaterThanOrEqual(1);
  });
});
