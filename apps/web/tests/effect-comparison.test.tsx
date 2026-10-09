import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EffectComparisonPanel } from "../components/EffectComparisonPanel";
import type { EffectRunResult, InvestigationSaveResult } from "../lib/types";

const mocks = vi.hoisted(() => ({ effectRuns: vi.fn(), adopt: vi.fn(), execute: vi.fn(), reopen: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { detail = "Unavailable"; },
  api: {
    effectRuns: (...args: unknown[]) => mocks.effectRuns(...args),
    adoptEffectRun: (...args: unknown[]) => mocks.adopt(...args),
    executeEffectRun: (...args: unknown[]) => mocks.execute(...args),
    effectRun: (...args: unknown[]) => mocks.reopen(...args),
  },
}));

const saved = {
  declaration: {
    schema_version: "p08.investigation-declaration/2", record_type: "InvestigationDeclaration",
    record_id: "11111111-1111-4111-8111-111111111111", owner_id: "owner-a",
    operation_id: "22222222-2222-4222-8222-222222222222", created_at: "2026-01-01T00:00:00Z",
    content: { configuration: {
      period: { start: "2026-01-01T00:00:00Z", end: "2026-01-03T00:00:00Z" },
      partitions: [{ partition_id: "descriptive", role: "DESCRIPTIVE", start: "2026-01-01T00:00:00Z", end: "2026-01-03T00:00:00Z" }],
      evaluation_plan: [
        { evaluation_id: "33333333-3333-4333-8333-333333333333", trial_id: "44444444-4444-4444-8444-444444444444", variant_id: "primary", horizon: { value: 15, unit: "MINUTES" }, partition_ids: ["descriptive"] },
        { evaluation_id: "55555555-5555-4555-8555-555555555555", trial_id: "44444444-4444-4444-8444-444444444444", variant_id: "comparison", horizon: { value: 15, unit: "MINUTES" }, partition_ids: ["descriptive"] },
      ],
    } },
  },
  access_history: [], study_started: false, idempotent_replay: false,
} as unknown as InvestigationSaveResult;

function run(report: EffectRunResult["report"] = null): EffectRunResult {
  return { run: { schema_version: "p09.effect-run-declaration/1", record_type: "EffectRunDeclaration",
    record_id: "66666666-6666-4666-8666-666666666666", owner_id: "owner-a",
    p08_declaration_id: saved.declaration.record_id, created_at: "2026-01-01T00:00:00Z", content: {} },
    events: [], report };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.effectRuns.mockResolvedValue({ runs: [] });
  mocks.adopt.mockResolvedValue(run());
  mocks.execute.mockResolvedValue(run({
    schema_version: "p09.effect-report/1", record_type: "EffectReport", record_id: "77777777-7777-4777-8777-777777777777",
    owner_id: "owner-a", created_at: "2026-01-01T00:01:00Z",
    content: { fixture_qualification: "SYNTHETIC_FIXTURE_QUALIFIED_FOR_LOGIC_ONLY", fixture_sha256: "a".repeat(64),
      profile_sha256: "b".repeat(64), p08_declaration_id: saved.declaration.record_id,
      next_action: "Qualify the research-data history before interpreting a real-data claim.",
      result: { status: "UNRESOLVED", statistical_status: "UNRESOLVED", statistical_reasons: ["STAT_Q01_PROFILE_NOT_QUALIFIED"],
        opportunity_count: 4, excluded_count: 0, missing_outcome_count: 0,
        variants: [{ evaluation_id: "33333333-3333-4333-8333-333333333333", variant_id: "primary",
          general_comparison: { triggered: { mean: "0" }, control: { mean: null }, triggered_minus_control_mean: null },
          incremental_volume_comparison: { status: "DESCRIPTIVE_ONLY", triggered_minus_control_mean: null } }],
      },
    },
  }));
  mocks.reopen.mockImplementation(async () => run(mocks.execute.mock.results[0]?.value?.report ?? null));
});

describe("P09 effect comparison", () => {
  it("shows exact adopted IDs and rules, saves before evaluation, then reopens the stored report", async () => {
    const user = userEvent.setup();
    render(<EffectComparisonPanel intakeId="request-1" saved={saved} />);
    await user.click(await screen.findByRole("button", { name: "Load explicit synthetic example" }));
    expect(screen.getByText(saved.declaration.record_id)).toBeInTheDocument();
    expect(screen.getByText("33333333-3333-4333-8333-333333333333")).toBeInTheDocument();
    expect(screen.getByText(/This visible example was authored/)).toBeInTheDocument();
    expect(screen.getByText(/one immutable P06 rule mapping across P09 runs/)).toBeInTheDocument();
    expect(screen.getByText(/four opportunities per evaluation/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adopt synthetic run declaration" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    mocks.effectRuns.mockResolvedValue({ runs: [run()] });
    await user.click(screen.getByRole("button", { name: "Adopt synthetic run declaration" }));
    await screen.findByText(/Run declaration saved/);
    expect(mocks.adopt).toHaveBeenCalledOnce();
    expect(mocks.execute).not.toHaveBeenCalled();
    const [, declarationId, body] = mocks.adopt.mock.calls[0];
    expect(declarationId).toBe(saved.declaration.record_id);
    expect(body.bindings.map((binding: { evaluation_id: string }) => binding.evaluation_id)).toEqual(
      saved.declaration.content.configuration.evaluation_plan.map((item) => item.evaluation_id));

    mocks.effectRuns.mockImplementation(async () => ({ runs: [await mocks.execute.mock.results[0]?.value ?? run()] }));
    await user.click(screen.getByRole("button", { name: "Evaluate synthetic fixture" }));
    expect(await screen.findByTestId("effect-report-saved")).toHaveTextContent("UNRESOLVED");
    expect(screen.getAllByText(/STAT_Q01_PROFILE_NOT_QUALIFIED/).length).toBeGreaterThan(0);
    expect(mocks.execute).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Reopen saved report without rerunning" }));
    await waitFor(() => expect(mocks.reopen).toHaveBeenCalledWith("request-1", "66666666-6666-4666-8666-666666666666"));
    expect(mocks.execute).toHaveBeenCalledOnce();
  });

  it("does not offer the synthetic route for a protected P08 partition", async () => {
    const protectedSaved = structuredClone(saved);
    protectedSaved.declaration.content.configuration.partitions[0].role = "HOLDOUT";
    render(<EffectComparisonPanel intakeId="request-1" saved={protectedSaved} />);
    expect(await screen.findByText(/does not access training, validation, or holdout rows/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load explicit synthetic example" })).toBeNull();
  });

  it("refreshes the selected run from durable failed-attempt history after a lost response", async () => {
    const failedRun = run();
    failedRun.events = [{ event_id: "event-1", sequence: 1, created_at: "2026-01-01T00:01:00Z",
      content: { kind: "ATTEMPT_STARTED" } },
    { event_id: "event-2", sequence: 2, created_at: "2026-01-01T00:02:00Z",
      content: { kind: "ATTEMPT_FAILED", outcome_accessed: true } }];
    mocks.effectRuns.mockResolvedValueOnce({ runs: [run()] }).mockResolvedValueOnce({ runs: [failedRun] });
    mocks.execute.mockRejectedValueOnce(new Error("response lost after server commit"));
    const user = userEvent.setup();
    render(<EffectComparisonPanel intakeId="request-1" saved={saved} />);
    await screen.findByRole("button", { name: "Evaluate synthetic fixture" });
    await user.click(screen.getByRole("button", { name: "Evaluate synthetic fixture" }));
    expect(await screen.findByRole("button", { name: "Retry synthetic evaluation" })).toBeInTheDocument();
    expect(screen.getByText(/P09 outcome access: recorded at event sequence/)).toBeInTheDocument();
    await user.click(screen.getByText("Run declaration and append-only attempt history"));
    expect(screen.getByText(/OUTCOME_ACCESS_STARTED|outcome_accessed/)).toBeInTheDocument();
  });
});
