import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InterpretationAttempts } from "../components/InterpretationAttempts";
import { QuestionForm } from "../components/QuestionForm";
import { RequestPage } from "../components/RequestPage";
import { describeLatency, describeParse, describeUsage, sourceQuote, systemFailure } from "../lib/interpretation";
import type { Attempt, Question } from "../lib/types";

const mocks = vi.hoisted(() => ({ get: vi.fn(), retry: vi.fn(), answer: vi.fn(), revision: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { constructor(public status = 503, public code = "x", public detail = "Unavailable") { super(detail); } },
  api: {
    get: (...a: unknown[]) => mocks.get(...a), retryInterpretation: (...a: unknown[]) => mocks.retry(...a),
    answer: (...a: unknown[]) => mocks.answer(...a), revision: (...a: unknown[]) => mocks.revision(...a),
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
  identity: { prompt_version: "p05-interpretation/1", system_prompt_sha256: "b".repeat(64), task_sha256: "c".repeat(64),
    response_shape_sha256: "d".repeat(64), manifest_sha256: "e".repeat(64), config_sha256: "f".repeat(64),
    runtime_label: "LOCAL_FAKE_PROVIDER", model: "local-fake/p05-interpretation", route: "local-fake-provider",
    hermes_commit: "54bc5e509c985f37265c3d416bd2c64b10fc77ba", answer_ref: null, previous_revision_id: null }, ...over,
});

describe("interpreter attempts", () => {
  it("lists every attempt, keeps unknown usage unknown, and names a retry's parent", () => {
    const failed = attempt({ attempt_id: "a1", status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null,
      usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null }, error_class: "ProviderHTTPError", latency_ms: null });
    const retry = attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1" });
    render(<InterpretationAttempts attempts={[failed, retry]} lateResults={[]} open />);
    const [first, second] = screen.getAllByRole("listitem");
    expect(within(first).getByRole("heading", { name: "Attempt #1: First reading" })).toBeInTheDocument();
    expect(within(first).getByText("Provider failed (ProviderHTTPError)")).toBeInTheDocument();
    expect(within(first).getAllByText("Unknown")).toHaveLength(2); // tokens and time
    expect(within(second).getByRole("heading", { name: "Attempt #2: First reading, retry of #1" })).toBeInTheDocument();
    expect(within(second).getByText("1,423 in, 611 out")).toBeInTheDocument();
    expect(within(second).getByText("2.5 s")).toBeInTheDocument();
    expect(within(second).getByText("Accepted. Used for the current meaning")).toBeInTheDocument();
  });

  it("says a late result is evidence only", () => {
    render(<InterpretationAttempts attempts={[attempt({ status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })]}
      lateResults={[{ observation_id: "o1", attempt_id: "a1", observed_at: "2026-10-10T09:00:00Z", status: "COMPLETED", response_sha256: "a".repeat(64),
        authoritative: false, usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } }]} open />);
    expect(screen.getByTestId("late-result")).toHaveTextContent("A result arrived after attempt #1 was closed. It is kept as evidence and was not used.");
  });

  it("describes values without turning unknown into zero", () => {
    expect(describeUsage({ source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null })).toBe("Unknown");
    expect(describeLatency(0)).toBe("0 ms");
    expect(describeLatency(null)).toBe("Unknown");
    expect(describeParse("REJECTED:multiple_objects")).toBe("Rejected: multiple objects");
    expect(describeParse("NOT_PARSED")).toBe("No answer to read");
  });

  it("finds the exact words a source points at and refuses a reference that does not fit", () => {
    const request = "Buy when the 15-minute price return is above 1%, and exit when negative.";
    expect(sourceQuote("intake:original_request#c0-47", request)).toBe("Buy when the 15-minute price return is above 1%");
    expect(sourceQuote("reply:11111111-1111-4111-8111-111111111111#c0-10", request)).toBeNull();
    expect(sourceQuote("intake:original_request#c0-9999", request)).toBeNull();
    expect(systemFailure([{ code: "missing_capability", path: "/", detail: "" }])).toBeNull();
    expect(systemFailure([{ code: "interpreter_unavailable", path: "/", detail: "" }])).toBe("UNAVAILABLE");
  });
});

const baseBundle = (outcome: string, finding: { code: string; detail: string }, retry: object, attempts: Attempt[], reply: object | null = null) => ({
  interpreter: { kind: "HERMES_LOCAL_FAKE_PROVIDER", id: "p05-interpretation/1", notice: "Actual pinned Hermes ran against a local fake provider." },
  intake: { record_id: "intake-1", created_at: "2026-10-10T08:00:00Z", content: { original_request: "Buy when up", restrictions: [], input_class: "CONCRETE_THESIS", requested_job: "CREATE_STRATEGY" } },
  interpretations: [], clarifications: [], publications: [], drafts: [], revisions: [], attempts, late_results: [],
  outcomes: [{ interpretation_revision_id: null, record: { record_id: "o1", content: { outcome, stage: "INTERPRETATION", code: "validation_error", retry: "SAFE_SAME_KEY", findings: [{ path: "/", ...finding }] } } }],
  head: { interpretation_revision_id: null, outcome, questions: [], draft_id: null, strategy_id: null, retry, reply },
});

const failedAttempt = attempt({ status: "PROVIDER_FAILED", completion: "NONE", parse_result: "NOT_PARSED", revision_id: null,
  usage: { source: "UNKNOWN", input_tokens: null, output_tokens: null, total_tokens: null } });

beforeEach(() => { mocks.get.mockReset(); mocks.retry.mockReset(); mocks.answer.mockReset(); mocks.revision.mockReset(); });

describe("system failures on the request page", () => {
  it("says a provider failure is a system failure, never a verdict on the idea, and retries only on request", async () => {
    const failed = baseBundle("INVALID_INPUT", { code: "interpreter_unavailable", detail: "The model provider did not return a result." },
      { allowed: true, retry_of: "a1", reason: null }, [failedAttempt]);
    mocks.get.mockResolvedValue(failed);
    mocks.retry.mockResolvedValue(baseBundle("UNRESOLVED", { code: "missing_dependency", detail: "No research run exists." },
      { allowed: false, retry_of: null, reason: "nothing_to_retry" }, [failedAttempt, attempt({ attempt_id: "a2", sequence: 2, retry_of: "a1" })]));
    const user = userEvent.setup();
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "The interpreter did not answer" })).toBeInTheDocument();
    expect(screen.queryByText("Could not be interpreted")).toBeNull();
    expect(screen.getByText(/This is not a verdict on your idea/)).toBeInTheDocument();
    expect(mocks.retry).not.toHaveBeenCalled(); // nothing is retried until the user asks
    await user.click(screen.getByRole("button", { name: "Try the interpreter again" }));
    expect(mocks.retry).toHaveBeenCalledWith("intake-1", "a1");
    expect(await screen.findByRole("heading", { name: "Unresolved: nothing was tested" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2); // both attempts stay listed
  });

  it("offers no retry for an unknown outcome and explains why", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "interpreter_outcome_unknown", detail: "It is not known whether the provider finished." },
      { allowed: false, retry_of: null, reason: "outcome_uncertain" }, [attempt({ status: "TIMED_OUT", completion: "UNKNOWN", parse_result: "NOT_PARSED", revision_id: null })]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "We do not know if the interpreter finished" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try the interpreter again" })).toBeNull();
    expect(screen.getByTestId("retry-blocked")).toHaveTextContent("Nothing was replayed.");
  });

  it("names malformed model output separately from a provider failure", async () => {
    mocks.get.mockResolvedValue(baseBundle("INVALID_INPUT", { code: "malformed_model_output", detail: "The model's answer could not be used (reason: multiple_objects)." },
      { allowed: true, retry_of: "a1", reason: null }, [attempt({ parse_result: "REJECTED:multiple_objects", revision_id: null })]));
    render(<RequestPage id="intake-1" go={vi.fn()} setContext={vi.fn()} openConversation={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "The interpreter's answer was not usable" })).toBeInTheDocument();
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
});
