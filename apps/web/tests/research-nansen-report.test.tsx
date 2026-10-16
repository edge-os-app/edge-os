import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchNansenReport } from "../components/ResearchNansenReport";

const mocks = vi.hoisted(() => ({ list: vi.fn(), start: vi.fn(), open: vi.fn(),
  ApiError: class extends Error { status = 422; detail = "The window start must be before its end."; code = "WINDOW_INVALID"; } }));
vi.mock("../lib/api", () => ({
  ApiError: mocks.ApiError,
  api: {
    nansenReports: (...args: unknown[]) => mocks.list(...args),
    startNansenReport: (...args: unknown[]) => mocks.start(...args),
    nansenReport: (...args: unknown[]) => mocks.open(...args),
  },
}));

const QUESTION = "Which holder records does MOE return, and who is buying MOE?";

function job(over: Record<string, unknown> = {}) {
  return { job_id: "job-1", kind: "NANSEN_REPORT", state: "REPORTED", terminal_reason: "partial", declaration_id: "r",
    request_key: "k", operation_id: "o", budget: {}, deadline_at: "t", cancel_requested_at: null, created_at: "t",
    events: [], dataset: null, report: null,
    nansen_report: { report_id: "report-1", content_sha256: "a".repeat(64), answer_state: "PARTIAL", question: QUESTION,
      token_symbol: "MOE", evidence_class: "AUTHORED_FIXTURE", outcomes: [],
      settlement: { provider_requests: { state: "KNOWN", measured: 2, lost: 0 },
        nansen_credits: { state: "KNOWN", measured: 6, deducted: "6", reserved_by_package: "6" } } },
    ...over };
}

const record = {
  report_id: "report-1", job_id: "job-1", content_sha256: "a".repeat(64), created_at: "t",
  hashes_verified: { content_sha256: true, request_sha256: true, evidence_sha256: true, report_sha256: true, report_binds_request: true },
  content: {
    evidence_class: "AUTHORED_FIXTURE", transport_label: "AUTHORED_NANSEN_TRANSPORT", request_sha256: "r", report_sha256: "p",
    notice: "Authored Nansen-shaped responses replayed locally. Not provider data, not a market fact and not bounty evidence.",
    settlement: job().nansen_report.settlement, outcomes: [],
    report: { question: QUESTION, token_address: "0xd8e004acba279417c04c0633cb5a21ceca207777", token_symbol: "MOE",
      answer_state: "PARTIAL", window: { start_utc: "2026-10-06T09:44:14Z", end_utc: "2026-10-07T09:44:14Z" },
      findings: [{ code: "HOLDER_INVENTORY", verdict: "SUPPORTED", statement: "3 address records returned in the requested provider order (token_amount descending).", source_refs: ["s1"], limitations: [] },
        { code: "BUYING", verdict: "UNRESOLVED", statement: "Flows and transfers do not evidence a purchase.", source_refs: [], limitations: [] }],
      limitations: [{ claim: "buying", missing_dependency: "trade-level evidence" }], unknowns: ["holder supply denominator"],
      coverage: { attempts: 2, pages: 2, holder_rows: 3, flow_buckets: 24, expected_buckets: 24, missing_buckets: 0,
        incomplete_buckets: 0, complete_seconds: 86400, pagination_is_last_page: true, stop_reason: null },
      source_hashes: ["h1", "h2"] } },
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue({ jobs: [] });
});

describe("Nansen token report", () => {
  it("says when the server cannot run reports and shows a released refusal honestly", async () => {
    mocks.list.mockResolvedValue({ available: false, jobs: [job({ state: "UNAVAILABLE", terminal_reason: "nansen_research_unavailable", nansen_report: null })] });
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-unavailable")).toHaveTextContent("This server cannot run Nansen reports.");
    expect(screen.getByTestId("nansen-job")).toHaveTextContent("Nothing was sent; the reserved amounts were released.");
    expect(screen.getByTestId("nansen-job")).not.toHaveTextContent("stay held");
    expect(screen.getByRole("button", { name: "Save and reserve this report" })).toBeDisabled();
  });

  it("reopens the saved report with the exact question, findings, gaps and an authored label", async () => {
    mocks.list.mockResolvedValue({ jobs: [job()] });
    mocks.open.mockResolvedValue(record);
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-job-answer")).toHaveTextContent("Answer: PARTIAL · requests KNOWN 2 · credits KNOWN 6");
    expect(screen.getByTestId("nansen-label")).toHaveTextContent("Not provider data");
    await userEvent.click(screen.getByRole("button", { name: "Open saved report" }));
    const view = await screen.findByTestId("nansen-report-view");
    expect(within(view).getByTestId("nansen-question")).toHaveTextContent(QUESTION);
    expect(within(view).getByTestId("nansen-findings")).toHaveTextContent("Unresolved · Flows and transfers do not evidence a purchase.");
    expect(within(view).getByTestId("nansen-limitations")).toHaveTextContent("buying: needs trade-level evidence");
    expect(within(view).getByTestId("nansen-coverage")).toHaveTextContent("3 holder address records (not people, not amounts)");
    expect(within(view).getByTestId("nansen-hashes")).toHaveTextContent("Saved hashes recomputed and matched.");
    expect(mocks.open).toHaveBeenCalledWith("report-1");
  });

  it("shows held credits honestly when the charge is unknown", async () => {
    mocks.list.mockResolvedValue({ jobs: [job({ nansen_report: { ...job().nansen_report, settlement: {
      provider_requests: { state: "UNKNOWN", measured: 0, lost: 1 },
      nansen_credits: { state: "UNKNOWN", measured: 0, deducted: null, reserved_by_package: "6" } } } })] });
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-job-answer")).toHaveTextContent("credits UNKNOWN (reserved amount held)");
  });

  it("starts one keyed report with the exact fields and shows a refusal with its code", async () => {
    mocks.start.mockRejectedValueOnce(new mocks.ApiError("refused"));
    render(<ResearchNansenReport intakeId="intake-1" />);
    await userEvent.type(await screen.findByLabelText("Token contract address"), "0xd8e004acba279417c04c0633cb5a21ceca207777");
    await userEvent.type(screen.getByLabelText("Token symbol"), "MOE");
    await userEvent.click(screen.getByLabelText("Basic flow records"));
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The window start must be before its end. (WINDOW_INVALID)");
    const [intakeId, body] = mocks.start.mock.calls[0];
    expect(intakeId).toBe("intake-1");
    expect(body).toMatchObject({ token_address: "0xd8e004acba279417c04c0633cb5a21ceca207777", token_symbol: "MOE",
      operations: ["holders"], limits: { max_requests: 4, max_pages: 2, max_bytes: 200000, max_credits: "12", per_page: 100 } });
    expect(Object.keys(body).sort()).toEqual(["compute_seconds", "deadline_seconds", "limits", "operation_id", "operations",
      "request_key", "token_address", "token_symbol", "window"]);
    mocks.start.mockResolvedValueOnce(job({ state: "RESERVED", nansen_report: null }));
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledTimes(2));
    expect(mocks.start.mock.calls[1][1].request_key).toBe(body.request_key);  // an uncertain retry reuses the key
  });
});

// SYNTHETIC fixtures in the server's release and record shapes. They represent response classes only; they are not
// provider replies, not collected data and not sponsor proof.
const FLOWS_ONLY = {
  token_address: "0x1111111111111111111111111111111111111111", token_symbol: "FLW",
  window: { start_utc: "2026-10-08T00:00:00Z", end_utc: "2026-10-09T00:00:00Z" }, operations: ["flows"],
  holder_query: { label_type: "all_holders", aggregate_by_entity: false, order_field: "token_amount", value_usd_min: null },
  flow_query: { label: "smart_money" },
  limits: { max_requests: 3, max_pages: 1, max_bytes: 90000, max_credits: "2.5", per_page: 50 },
  deadline_seconds: 240, compute_seconds: 12,
};

function release(over: Record<string, unknown> = {}, request: Record<string, unknown> = {}) {
  return { release_id: "nansen-flows-1", sha256: "c".repeat(64), kind: "ACTUAL", evidence_class: "PROVIDER_ACTUAL",
    request: { ...FLOWS_ONLY, ...request }, ...over };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("Nansen report under an operating release", () => {
  it("posts the whole fixed flows-only request without authored defaults and offers no field to change it", async () => {
    mocks.list.mockResolvedValue({ available: true, jobs: [], operating_release: release() });
    mocks.start.mockResolvedValueOnce(job({ state: "RESERVED", nansen_report: null }));
    render(<ResearchNansenReport intakeId="intake-1" />);
    const fixed = await screen.findByTestId("nansen-release-request");
    expect(fixed).toHaveTextContent("FLW");
    expect(fixed).toHaveTextContent("up to 3 provider requests");
    expect(fixed).toHaveTextContent("2.5 credits");
    expect(fixed).toHaveTextContent("smart_money");
    expect(screen.queryByLabelText("Token contract address")).toBeNull();
    expect(screen.queryByLabelText("Credit limit for this report")).toBeNull();
    const label = screen.getByTestId("nansen-label");
    expect(label).toHaveTextContent("configured for actual Nansen collection");
    expect(label).not.toHaveTextContent(/collected from Nansen|passed|verified/i);
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledTimes(1));
    const [intakeId, body] = mocks.start.mock.calls[0];
    expect(intakeId).toBe("intake-1");
    expect(body).toEqual({ operation_id: expect.any(String), request_key: expect.any(String), ...FLOWS_ONLY });
  });

  it("posts a holder-only stand-in release and labels it as not provider data", async () => {
    const holders = { operations: ["holders"], holder_query: { label_type: "all_holders", aggregate_by_entity: true,
      order_field: "token_amount", value_usd_min: 1000 } };
    mocks.list.mockResolvedValue({ jobs: [], operating_release: release({ kind: "STAND_IN", evidence_class: "RELEASE_STAND_IN_RESPONSE" }, holders) });
    mocks.start.mockResolvedValueOnce(job({ state: "RESERVED", nansen_report: null }));
    render(<ResearchNansenReport intakeId="intake-1" />);
    await screen.findByTestId("nansen-release-request");
    expect(screen.getByTestId("nansen-label")).toHaveTextContent("Stand-in");
    expect(screen.getByTestId("nansen-label")).toHaveTextContent("Not provider data");
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledTimes(1));
    expect(mocks.start.mock.calls[0][1]).toEqual({ operation_id: expect.any(String), request_key: expect.any(String), ...FLOWS_ONLY, ...holders });
  });

  it.each([
    ["null", null],
    ["missing its request", release({ request: undefined })],
    ["of an unknown evidence class", release({ evidence_class: "PROVIDER_MAYBE" })],
    ["with conflicting limits", release({}, { limits: { max_requests: "3", max_pages: 1, max_bytes: 90000, max_credits: "2.5", per_page: 50 } })],
  ])("blocks a new request when the release is %s, but saved reports still open", async (_name, operating_release) => {
    mocks.list.mockResolvedValue({ available: true, jobs: [job()], operating_release });
    mocks.open.mockResolvedValue(record);
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-release-blocked")).toHaveTextContent("The operating release could not be read");
    expect(screen.getByRole("button", { name: "Save and reserve this report" })).toBeDisabled();
    expect(screen.queryByLabelText("Token contract address")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Open saved report" }));
    expect(await screen.findByTestId("nansen-report-view")).toBeInTheDocument();
    expect(mocks.start).not.toHaveBeenCalled();
  });

  it("blocks a valid release when the server says it is unavailable", async () => {
    mocks.list.mockResolvedValue({ available: false, jobs: [], operating_release: release() });
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save and reserve this report" })).toBeDisabled();
  });

  it("posts the release from the latest refresh, never the previous one", async () => {
    const changed = release({ release_id: "nansen-flows-2", sha256: "d".repeat(64) },
      { limits: { max_requests: 2, max_pages: 1, max_bytes: 70000, max_credits: "1", per_page: 40 } });
    mocks.list.mockResolvedValueOnce({ jobs: [], operating_release: release() }).mockResolvedValue({ jobs: [], operating_release: changed });
    mocks.start.mockResolvedValue(job({ state: "RESERVED", nansen_report: null }));
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-release-request")).toHaveTextContent("nansen-flows-1");
    await userEvent.click(screen.getByRole("button", { name: "Refresh reports" }));
    await waitFor(() => expect(screen.getByTestId("nansen-release-request")).toHaveTextContent("nansen-flows-2"));
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledTimes(1));
    expect(mocks.start.mock.calls[0][1].limits).toEqual({ max_requests: 2, max_pages: 1, max_bytes: 70000, max_credits: "1", per_page: 40 });
  });

  it("ignores an older listing that returns late and waits for the new intake's release", async () => {
    const late = deferred<unknown>();
    const second = deferred<unknown>();
    mocks.list.mockReturnValueOnce(late.promise).mockReturnValueOnce(second.promise);
    mocks.start.mockResolvedValue(job({ state: "RESERVED", nansen_report: null }));
    const view = render(<ResearchNansenReport intakeId="intake-1" />);
    view.rerender(<ResearchNansenReport intakeId="intake-2" />);
    expect(screen.getByRole("button", { name: "Save and reserve this report" })).toBeDisabled();
    second.resolve({ jobs: [], operating_release: release({ release_id: "nansen-flows-2", sha256: "d".repeat(64) }, { token_symbol: "TWO" }) });
    await waitFor(() => expect(screen.getByTestId("nansen-release-request")).toHaveTextContent("nansen-flows-2"));
    late.resolve({ jobs: [], operating_release: release({}, { token_symbol: "OLD" }) });
    await new Promise((done) => setTimeout(done, 0));
    expect(screen.getByTestId("nansen-release-request")).toHaveTextContent("TWO");
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledTimes(1));
    expect(mocks.start.mock.calls[0][0]).toBe("intake-2");
    expect(mocks.start.mock.calls[0][1].token_symbol).toBe("TWO");
  });

  it("reuses the keys after an unconfirmed request and never resubmits by itself", async () => {
    mocks.list.mockResolvedValue({ jobs: [], operating_release: release() });
    mocks.start.mockRejectedValueOnce(new Error("network"));
    render(<ResearchNansenReport intakeId="intake-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Save and reserve this report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Check saved reports before trying again.");
    expect(mocks.start).toHaveBeenCalledTimes(1);
    mocks.start.mockResolvedValueOnce(job({ state: "RESERVED", nansen_report: null }));
    await userEvent.click(screen.getByRole("button", { name: "Save and reserve this report" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledTimes(2));
    expect(mocks.start.mock.calls[1][1].request_key).toBe(mocks.start.mock.calls[0][1].request_key);
    expect(mocks.start.mock.calls[1][1].operation_id).toBe(mocks.start.mock.calls[0][1].operation_id);
  });
});

describe("saved Nansen report labels", () => {
  const ACTUAL_NOTICE = "Nansen provider responses under an approved operating release. Address counts are returned records.";
  const actual = { ...record, hashes_verified: { ...record.hashes_verified, evidence_sha256: false },
    content: { ...record.content, evidence_class: "PROVIDER_ACTUAL", transport_label: "PROVIDER_NANSEN_TRANSPORT", notice: ACTUAL_NOTICE,
      settlement: { provider_requests: { state: "UNKNOWN", measured: 1, lost: 1 },
        nansen_credits: { state: "UNKNOWN", measured: 0, deducted: null, reserved_by_package: "2.5" } },
      report: { ...record.content.report, coverage: { ...record.content.report.coverage, missing_buckets: 3, incomplete_buckets: 1 } } } };

  it("attributes a saved actual report to Nansen with its notice, gaps, sources and failed hash", async () => {
    mocks.list.mockResolvedValue({ jobs: [job({ nansen_report: { ...job().nansen_report, evidence_class: "PROVIDER_ACTUAL" } })] });
    mocks.open.mockResolvedValue(actual);
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(await screen.findByTestId("nansen-job-evidence")).toHaveTextContent("Nansen provider data");
    await userEvent.click(screen.getByRole("button", { name: "Open saved report" }));
    const view = await screen.findByTestId("nansen-report-view");
    const evidence = within(view).getByTestId("nansen-evidence");
    expect(evidence).toHaveTextContent("Data from Nansen");
    expect(evidence).toHaveTextContent("not full ownership");
    expect(within(evidence).getByRole("link", { name: "Nansen" })).toHaveAttribute("href", "https://www.nansen.ai");
    expect(within(evidence).getByRole("link", { name: "Nansen API documentation" })).toHaveAttribute("href", "https://docs.nansen.ai");
    expect(view).toHaveTextContent(ACTUAL_NOTICE);
    expect(within(view).getByTestId("nansen-coverage")).toHaveTextContent("partial coverage");
    expect(within(view).getByTestId("nansen-settlement")).toHaveTextContent("credits UNKNOWN (reserved amount held)");
    expect(within(view).getByTestId("nansen-sources")).toHaveTextContent("2 saved provider response hashes");
    expect(within(view).getByTestId("nansen-hashes")).toHaveTextContent("A saved hash did not match. Do not rely on this report.");
  });

  it.each([
    ["RELEASE_STAND_IN_RESPONSE", "Stand-in responses. Not provider data."],
    ["AUTHORED_FIXTURE", "Authored responses replayed on this server. Not provider data."],
    ["SOMETHING_ELSE", "Unrecognized evidence class SOMETHING_ELSE. Do not treat this report as provider data."],
  ])("labels a saved %s report without Nansen attribution", async (evidenceClass, copy) => {
    mocks.list.mockResolvedValue({ jobs: [job()] });
    mocks.open.mockResolvedValue({ ...record, content: { ...record.content, evidence_class: evidenceClass } });
    render(<ResearchNansenReport intakeId="intake-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Open saved report" }));
    const evidence = await screen.findByTestId("nansen-evidence");
    expect(evidence).toHaveTextContent(copy);
    expect(within(evidence).queryByRole("link")).toBeNull();
    expect(screen.getByTestId("nansen-report-view")).toHaveTextContent(record.content.notice);
  });
});
