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
  it("reopens the saved report with the exact question, findings, gaps and an authored label", async () => {
    mocks.list.mockResolvedValue({ jobs: [job()] });
    mocks.open.mockResolvedValue(record);
    render(<ResearchNansenReport intakeId="intake-1" />);
    expect(screen.getByTestId("nansen-label")).toHaveTextContent("Not provider data");
    expect(await screen.findByTestId("nansen-job-answer")).toHaveTextContent("Answer: PARTIAL · requests KNOWN 2 · credits KNOWN 6");
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
    await userEvent.type(screen.getByLabelText("Token contract address"), "0xd8e004acba279417c04c0633cb5a21ceca207777");
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
