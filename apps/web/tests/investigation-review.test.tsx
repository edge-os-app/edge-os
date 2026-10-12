import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvestigationReview } from "../components/InvestigationReview";

const mocks = vi.hoisted(() => ({ proposal: vi.fn(), list: vi.fn(), save: vi.fn(), get: vi.fn(),
  historySources: vi.fn(), historyList: vi.fn(), historySave: vi.fn(), jobs: vi.fn(), startJob: vi.fn(),
  cancelJob: vi.fn(), budget: vi.fn(), nansenReports: vi.fn(), startNansen: vi.fn(), nansenReport: vi.fn(),
  effectRuns: vi.fn(), adoptEffectRun: vi.fn(), executeEffectRun: vi.fn(), getEffectRun: vi.fn(),
  ApiError: class extends Error { status = 503; detail = "Unavailable"; code = "service_unavailable"; } }));
vi.mock("../lib/api", () => ({
  ApiError: mocks.ApiError,
  api: {
    investigationProposal: (...args: unknown[]) => mocks.proposal(...args),
    investigations: (...args: unknown[]) => mocks.list(...args),
    saveInvestigation: (...args: unknown[]) => mocks.save(...args),
    investigation: (...args: unknown[]) => mocks.get(...args),
    effectRuns: (...args: unknown[]) => mocks.effectRuns(...args),
    adoptEffectRun: (...args: unknown[]) => mocks.adoptEffectRun(...args),
    executeEffectRun: (...args: unknown[]) => mocks.executeEffectRun(...args),
    effectRun: (...args: unknown[]) => mocks.getEffectRun(...args),
    // The recorded-history section below the plan. Its default state is empty.
    historySources: (...args: unknown[]) => mocks.historySources(...args),
    historyInvestigations: (...args: unknown[]) => mocks.historyList(...args),
    saveHistoryInvestigation: (...args: unknown[]) => mocks.historySave(...args),
    investigationJobs: (...args: unknown[]) => mocks.jobs(...args),
    startInvestigationJob: (...args: unknown[]) => mocks.startJob(...args),
    cancelInvestigationJob: (...args: unknown[]) => mocks.cancelJob(...args),
    get: async () => ({ intake: { content: { original_request: "test request" } } }),
    researchBudget: (...args: unknown[]) => mocks.budget(...args),
    // The Nansen report section below the history section. Its default state is empty.
    nansenReports: (...args: unknown[]) => mocks.nansenReports(...args),
    startNansenReport: (...args: unknown[]) => mocks.startNansen(...args),
    nansenReport: (...args: unknown[]) => mocks.nansenReport(...args),
  },
}));

const proposal = {
  schema_version: "p08.investigation-declaration/2",
  proposal_version: "p08-bounded-review/2",
  interpretation_revision_id: null,
  request_record_id: "intake-1",
  edge_spec: {
    edge_id: "11111111-1111-4111-8111-111111111111", version: 1, parent_declaration_id: null,
    hypothesis: "Describe the comparison only.",
    claim: { status: "DESCRIPTIVE_ONLY", text: "Describe only. No predictive claim is declared." },
    falsification: { status: "DESCRIPTIVE_ONLY", criteria: "No outcome claim is evaluated." },
    alternatives: ["Selection may explain the pattern."], unknowns: ["Participant incentives are unverified."],
  },
  configuration: {
    question: "Something nobody scripted.",
    pool_binding: { profile_id: "fixture-unqualified-pool/1", qualification: "UNQUALIFIED_FIXTURE", limitations: ["Synthetic fixture only."] },
    variants: [{ variant_id: "primary", hypothesis: "Primary group" }, { variant_id: "comparison", hypothesis: "Comparison group" }],
    direction: "DESCRIPTIVE", horizons: [{ value: 15, unit: "MINUTES" }], sources: ["fixture-unqualified-pool/1"],
    candidate_limit: 2, parameter_limit: 4,
    compute_limit: { max_evaluations: 2, max_runtime_seconds: 60, max_cost_usd: "0" },
    period: { start: "2026-01-01T00:00:00+00:00", end: "2026-01-03T00:00:00+00:00" },
    partitions: [{ partition_id: "descriptive", role: "DESCRIPTIVE", start: "2026-01-01T00:00:00Z", end: "2026-01-03T00:00:00Z" }], permitted_access: ["FIXTURE_ONLY"],
    stopping_rule: "Stop after two comparisons.", evaluation_plan: [
      { evaluation_id: "33333333-3333-4333-8333-333333333333", trial_id: "22222222-2222-4222-8222-222222222222",
        variant_id: "primary", horizon: { value: 15, unit: "MINUTES" }, partition_ids: ["descriptive"] },
    ], budget_version: "p08-research-budget/2",
    optional_tools: { creator_history: "UNAVAILABLE", wallet_pnl: "UNAVAILABLE", social_signals: "UNAVAILABLE" },
  },
  adopted_fields: [], field_origins: {}, trial_ids: ["22222222-2222-4222-8222-222222222222"],
  evaluation_ids: ["33333333-3333-4333-8333-333333333333"],
  notice: "Fixture-only proposal. No study runs.",
};

function proposalWithIds(source: typeof proposal, revision: string, trialId: string, evaluationId: string) {
  return {
    ...source,
    interpretation_revision_id: revision,
    trial_ids: [trialId],
    evaluation_ids: [evaluationId],
    configuration: {
      ...source.configuration,
      evaluation_plan: source.configuration.evaluation_plan.map((row) => ({
        ...row, trial_id: trialId, evaluation_id: evaluationId,
      })),
    },
  };
}

const saved = {
  declaration: {
  schema_version: "p08.investigation-declaration/2", record_type: "InvestigationDeclaration",
    record_id: "44444444-4444-4444-8444-444444444444", owner_id: "owner-a",
    operation_id: "55555555-5555-4555-8555-555555555555", created_at: "2026-01-03T00:00:00Z",
    content: {
      original_request: proposal.configuration.question, restrictions: [], input_class: "BOUNDED_NO_THESIS",
      requested_job: "INVESTIGATE_EFFECT", interpretation_revision_id: null, edge_spec: proposal.edge_spec,
      configuration: proposal.configuration, adopted_fields: [], field_origins: {}, trial_ids: [], evaluation_ids: [],
      declaration_state: "PRE_OUTCOME_DECLARED", outcome_labels_read: false,
    },
  },
  access_history: [{ event_id: "id", declaration_id: "id", created_at: "2026-01-03T00:00:00Z",
    schema_version: "p08.investigation-access/1", event: "DECLARATION_SAVED", outcome_labels_read: false,
    provider_queries: 0, study_started: false }], study_started: false, idempotent_replay: false,
};

beforeEach(() => {
  mocks.historySources.mockReset().mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [] });
  mocks.historyList.mockReset().mockResolvedValue({ declarations: [] });
  mocks.nansenReports.mockReset().mockResolvedValue({ jobs: [] });
  mocks.startNansen.mockReset(); mocks.nansenReport.mockReset();
  mocks.historySave.mockReset(); mocks.startJob.mockReset(); mocks.cancelJob.mockReset();
  mocks.jobs.mockReset().mockResolvedValue({ jobs: [] });
  mocks.budget.mockReset().mockResolvedValue(null);
  window.sessionStorage.clear();
  vi.clearAllMocks();
  mocks.proposal.mockResolvedValue(proposal);
  mocks.list.mockResolvedValue({ declarations: [], access_history: [] });
  mocks.save.mockResolvedValue(saved);
  mocks.get.mockResolvedValue(saved);
  mocks.effectRuns.mockResolvedValue({ runs: [] });
  mocks.adoptEffectRun.mockResolvedValue({ run: {}, events: [], report: null });
  mocks.executeEffectRun.mockResolvedValue({ run: {}, events: [], report: null });
  mocks.getEffectRun.mockResolvedValue({ run: {}, events: [], report: null });
});

describe("investigation declaration adoption", () => {
  it("requires explicit adoption, saves the whole bounded declaration, and reopens the exact record", async () => {
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    expect(await screen.findByLabelText("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Adopt and save declaration" });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /fixture-only declaration/ }));
    fireEvent.click(save);
    await screen.findByText("Declaration saved");
    expect(mocks.save).toHaveBeenCalledOnce();
    const [, body] = mocks.save.mock.calls[0];
    expect(body.expected_interpretation_revision_id).toBeNull();
    expect(body.edge_spec.unknowns).toContain("Participant incentives are unverified.");
    expect(body.configuration.compute_limit.max_cost_usd).toBe("0");
    expect(body.configuration.permitted_access).toEqual(["FIXTURE_ONLY"]);
      expect(body.adopted_fields).toContain("edge_spec");
    expect(body.field_origins.edge_spec.adoption).toBe("ADOPTED");
    expect(screen.getByTestId("investigation-saved")).toHaveTextContent("No study started");
    fireEvent.click(screen.getByRole("button", { name: "Reopen saved declaration" }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith("intake-1", saved.declaration.record_id));
    expect(screen.getByTestId("investigation-saved")).toHaveTextContent(saved.declaration.record_id);
  });

  it("reopens only the saved declaration on a fresh page load", async () => {
    mocks.list.mockResolvedValue({ declarations: [saved.declaration], access_history: saved.access_history });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    expect(await screen.findByTestId("investigation-saved")).toHaveTextContent(saved.declaration.record_id);
    expect(screen.queryByLabelText(/I reviewed the hypothesis and every required setting/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reopen saved declaration" }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith("intake-1", saved.declaration.record_id));
  });

  it("keeps the saved declaration visible when proposal generation fails and retries only the proposal", async () => {
    mocks.list.mockResolvedValue({ declarations: [saved.declaration], access_history: saved.access_history });
    mocks.proposal.mockRejectedValueOnce(new mocks.ApiError("proposal unavailable"));
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    expect(await screen.findByTestId("investigation-saved")).toHaveTextContent(saved.declaration.record_id);
    await userEvent.click(await screen.findByRole("button", { name: "Retry proposal" }));
    await waitFor(() => expect(mocks.proposal).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("investigation-saved")).toHaveTextContent(saved.declaration.record_id);
    expect(screen.getByRole("button", { name: "Reopen saved declaration" })).toBeInTheDocument();
  });

  it("offers an in-place retry when no saved declaration exists and proposal loading fails", async () => {
    mocks.proposal.mockRejectedValueOnce(new mocks.ApiError("proposal unavailable"));
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Retry proposal" }));
    expect(await screen.findByRole("textbox", { name: "Hypothesis or descriptive question" })).toBeInTheDocument();
    expect(mocks.list).toHaveBeenCalledOnce();
  });

  it("keeps claim, falsification, direction, and partition controls semantically aligned", async () => {
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    const claim = await screen.findByLabelText("Claim status");
    fireEvent.change(claim, { target: { value: "HYPOTHESIS" } });
    expect(screen.getByLabelText("Expected direction")).toHaveValue("OUTPERFORM");
    expect(screen.queryByRole("option", { name: "Descriptive, no prediction" })).toBeNull();
    expect(screen.getByRole("option", { name: "Primary group outperforms comparison" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Primary group underperforms comparison" })).toBeInTheDocument();
    expect(screen.getByText(/TRAINING · training/)).toBeInTheDocument();
    expect(screen.getByText(/VALIDATION · validation/)).toBeInTheDocument();
    expect(screen.getByText(/HOLDOUT · holdout/)).toBeInTheDocument();
    fireEvent.change(claim, { target: { value: "DESCRIPTIVE_ONLY" } });
    expect(screen.getByLabelText("Expected direction")).toHaveValue("DESCRIPTIVE");
    expect(screen.queryByText(/HOLDOUT · holdout/)).toBeNull();
    expect(screen.getByLabelText("Expected direction").querySelectorAll("option")).toHaveLength(1);
    expect(screen.getByRole("option", { name: "Descriptive, no prediction" })).toBeInTheDocument();
    expect(screen.getByLabelText("Outcome horizon (positive integer)")).toHaveValue(15);
  });

  it("retries a failed save with only the strict request keys and focuses the saved result after keyboard activation", async () => {
    const user = userEvent.setup();
    mocks.save.mockRejectedValueOnce(new Error("temporary network failure")).mockResolvedValue(saved);
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByLabelText("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.");
    await user.click(screen.getByRole("checkbox", { name: /fixture-only declaration/ }));
    const saveButton = screen.getByRole("button", { name: "Adopt and save declaration" });
    saveButton.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("alert");
    saveButton.focus();
    await user.keyboard("{Enter}");
    const heading = await screen.findByRole("heading", { name: "Declaration saved" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(mocks.save).toHaveBeenCalledTimes(2);
    const firstBody = mocks.save.mock.calls[0][1];
    const retryBody = mocks.save.mock.calls[1][1];
    expect(retryBody).not.toHaveProperty("fingerprint");
    expect(Object.keys(retryBody).sort()).toEqual(["expected_interpretation_revision_id", "operation_id", "idempotency_key", "edge_spec", "configuration", "adopted_fields", "field_origins", "trial_ids", "evaluation_ids"].sort());
    expect(retryBody.operation_id).toBe(firstBody.operation_id);
    expect(retryBody.idempotency_key).toBe(firstBody.idempotency_key);
  });

  it("keeps replacement intent across repeated proposal failures and saves a fresh hypothesis", async () => {
    const user = userEvent.setup();
    const replacement = {
      ...proposalWithIds(proposal, "revision-new", "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
      edge_spec: { ...proposal.edge_spec, edge_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        hypothesis: "A separately reviewed descriptive question." },
    };
    mocks.proposal.mockReset().mockResolvedValueOnce(proposal)
      .mockRejectedValueOnce(new mocks.ApiError("replacement unavailable"))
      .mockRejectedValueOnce(new mocks.ApiError("replacement still unavailable"))
      .mockResolvedValueOnce(replacement);
    const replacementSaved = {
      ...saved,
      declaration: { ...saved.declaration, record_id: "66666666-6666-4666-8666-666666666666",
        content: { ...saved.declaration.content, edge_spec: replacement.edge_spec,
          configuration: replacement.configuration, trial_ids: replacement.trial_ids,
          evaluation_ids: replacement.evaluation_ids } },
    };
    mocks.save.mockReset().mockResolvedValueOnce(saved).mockResolvedValueOnce(replacementSaved);

    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await user.click(await screen.findByRole("checkbox", { name: /fixture-only declaration/ }));
    await user.click(screen.getByRole("button", { name: "Adopt and save declaration" }));
    await screen.findByRole("heading", { name: "Declaration saved" });
    await user.click(screen.getByRole("button", { name: "Review another hypothesis" }));

    expect(await screen.findByText(/A new hypothesis could not be prepared/)).toBeInTheDocument();
    expect(screen.getByText(/The saved declaration is unchanged/)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Retry new hypothesis" });
    await user.click(retry);
    await screen.findByText(/A new hypothesis could not be prepared\. Unavailable/);
    expect(screen.getByRole("button", { name: "Retry new hypothesis" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry new hypothesis" }));

    expect(await screen.findByLabelText("Hypothesis or descriptive question")).toHaveValue(
      "A separately reviewed descriptive question.");
    expect(screen.queryByText(/request interpretation changed/)).toBeNull();
    await user.click(screen.getByRole("checkbox", { name: /fixture-only declaration/ }));
    await user.click(screen.getByRole("button", { name: "Adopt and save declaration" }));
    await screen.findByRole("heading", { name: "Declaration saved" });

    expect(mocks.proposal).toHaveBeenCalledTimes(4);
    expect(mocks.save).toHaveBeenCalledTimes(2);
    const initialBody = mocks.save.mock.calls[0][1];
    const replacementBody = mocks.save.mock.calls[1][1];
    expect(replacementBody.edge_spec.edge_id).not.toBe(initialBody.edge_spec.edge_id);
    expect(replacementBody.trial_ids).toEqual(replacement.trial_ids);
    expect(replacementBody.evaluation_ids).toEqual(replacement.evaluation_ids);
    expect(replacementBody.configuration.evaluation_plan).toEqual(replacement.configuration.evaluation_plan);
    expect(replacementBody.expected_interpretation_revision_id).toBe("revision-new");
    expect(screen.getByTestId("investigation-saved")).toHaveTextContent(replacementSaved.declaration.record_id);
  });

  it.each(["stale save", "proposal retry", "clarifications on the same intake"] as const)(
    "keeps a retained draft's regenerated identities coherent after %s and saves it",
    async (refreshPath) => {
      const user = userEvent.setup();
      const original = proposalWithIds(proposal, "revision-1", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
      const regenerated = proposalWithIds(proposal, "revision-2", "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd");
      const regeneratedAgain = proposalWithIds(proposal, "revision-3", "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "ffffffff-ffff-4fff-8fff-ffffffffffff");
      mocks.proposal.mockReset();
      mocks.proposal.mockResolvedValueOnce(original);
      if (refreshPath === "stale save") {
        mocks.proposal.mockResolvedValueOnce(regenerated);
        mocks.save.mockRejectedValueOnce(Object.assign(new mocks.ApiError("stale"), { code: "interpretation_revision_conflict" }));
      } else if (refreshPath === "proposal retry") {
        mocks.proposal.mockRejectedValueOnce(new mocks.ApiError("proposal refresh unavailable"));
        mocks.proposal.mockResolvedValueOnce(regenerated);
      } else {
        mocks.proposal.mockResolvedValueOnce(regenerated).mockResolvedValueOnce(regeneratedAgain);
      }
      mocks.save.mockResolvedValue(saved);

      const { rerender } = render(<InvestigationReview intakeId="intake-1" interpretationRevisionId="revision-1" />);
      const stopping = await screen.findByLabelText("Stopping rule");
      await user.clear(stopping);
      await user.type(stopping, "Keep my reviewed edits across each current review.");

      if (refreshPath === "stale save") {
        await user.click(screen.getByRole("checkbox", { name: /fixture-only declaration/ }));
        await user.click(screen.getByRole("button", { name: "Adopt and save declaration" }));
        await screen.findByText(/unsaved edits remain in place/);
        expect(screen.getByRole("checkbox", { name: /fixture-only declaration/ })).not.toBeChecked();
        expect(stopping).toHaveValue("Keep my reviewed edits across each current review.");
      } else if (refreshPath === "proposal retry") {
        rerender(<InvestigationReview intakeId="intake-1" interpretationRevisionId="revision-2" />);
        await screen.findByText("Unavailable", { selector: "p" });
        await user.click(screen.getByRole("button", { name: "Retry proposal" }));
        await screen.findByText(/unsaved edits remain in place/);
        expect(stopping).toHaveValue("Keep my reviewed edits across each current review.");
      } else {
        rerender(<InvestigationReview intakeId="intake-1" interpretationRevisionId="revision-2" />);
        await waitFor(() => expect(mocks.proposal).toHaveBeenCalledTimes(2));
        rerender(<InvestigationReview intakeId="intake-1" interpretationRevisionId="revision-3" />);
        await waitFor(() => expect(mocks.proposal).toHaveBeenCalledTimes(3));
        expect(stopping).toHaveValue("Keep my reviewed edits across each current review.");
      }

      expect(screen.getByRole("checkbox", { name: /fixture-only declaration/ })).not.toBeChecked();
      await user.click(screen.getByRole("checkbox", { name: /fixture-only declaration/ }));
      await user.click(screen.getByRole("button", { name: "Adopt and save declaration" }));
      await screen.findByRole("heading", { name: "Declaration saved" });
      expect(screen.queryByText(/unsaved edits remain in place/)).toBeNull();
      const body = mocks.save.mock.calls.at(-1)?.[1];
      expect(body.expected_interpretation_revision_id).toBe(refreshPath === "clarifications on the same intake" ? "revision-3" : "revision-2");
      expect(body.configuration.stopping_rule).toBe("Keep my reviewed edits across each current review.");
      expect(body.trial_ids).toEqual(original.trial_ids);
      expect(body.evaluation_ids).toEqual(original.evaluation_ids);
      expect(body.configuration.evaluation_plan.map((row: { trial_id: string; evaluation_id: string }) =>
        [row.trial_id, row.evaluation_id])).toEqual([[original.trial_ids[0], original.evaluation_ids[0]]]);
      expect(body.trial_ids).not.toEqual(regenerated.trial_ids);
      expect(body.evaluation_ids).not.toEqual(regenerated.evaluation_ids);
      if (refreshPath === "stale save") expect(mocks.save).toHaveBeenCalledTimes(2);
      else expect(mocks.save).toHaveBeenCalledOnce();
    },
  );

});


const SOURCE = {
  source_id: "recorded-syn-qualified/1", title: "Synthetic recorded history (qualifies)", evidence_class: "RECORDED_RESPONSE",
  content_label: "SYNTHETIC_FIXTURE", profile_version: "p07.market_dataset_profile/1", profile_sha256: "f".repeat(64),
  market: { network: "MONAD", pool_address: "0xaaaa", base_asset: "0xcccc", quote_asset: "0xbbbb" },
  window: { start: "2026-09-25T10:00:00Z", end: "2026-09-25T12:00:00Z" }, history_provider: "ENVIO_HYPERSYNC",
  page_requests_recorded: 2, transport: null,
};
const DECLARATION = {
  declaration: { record_id: "hist-decl-1", schema_version: "p08.investigation-declaration/3", created_at: "2026-10-12T00:00:00Z",
    content: { schema_version: "p08.investigation-declaration/3", original_request: "test request",
      declaration_state: "PRE_OUTCOME_DECLARED", outcome_labels_read: false,
      edge_spec: { hypothesis: "Rises continue", claim: { status: "DESCRIPTIVE_ONLY", text: "Describe only." } },
      configuration: { source: { source_id: SOURCE.source_id, profile_sha256: SOURCE.profile_sha256, evidence_class: "RECORDED_RESPONSE" },
        market: SOURCE.market, window: SOURCE.window, direction: "DESCRIPTIVE",
        resource_bounds: { provider_requests: 2, compute_seconds: 30 }, evaluation_plan: [], partitions: [] },
      rule_map: { rules: [], binding_state: "PENDING_DATASET_QUALIFICATION", control: "UNTRIGGERED_DECISIONS" },
      frozen: { configuration_sha256: "c".repeat(64), rule_map_sha256: "r".repeat(64), source_profile_sha256: "f".repeat(64),
        frozen_at: "2026-10-12T00:00:00Z" } } },
  access_history: [{ event: "DECLARATION_SAVED", provider_queries: 0, outcome_labels_read: false }],
};
function job(state: string, extra: Record<string, unknown> = {}) {
  return { job_id: `job-${state}`, declaration_id: "hist-decl-1", request_key: "k", operation_id: "o", state,
    terminal_reason: null, budget: { reserved: { provider_requests: 2, compute_seconds: 30 } }, deadline_at: "",
    cancel_requested_at: null, created_at: "", events: [{ kind: "JOB_QUEUED", attempt_id: null, created_at: "", content: {} }],
    dataset: null, report: null, ...extra };
}

describe("recorded-history investigation", () => {
  async function openSaved(user: ReturnType<typeof userEvent.setup>) {
    mocks.historyList.mockResolvedValue({ declarations: [DECLARATION] });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await user.click(await screen.findByRole("button", { name: "Open this declaration" }));
    await screen.findByTestId("history-declaration");
  }

  it("requires the user's own hypothesis, rules and adoption, then saves a user-adopted rule map", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE] });
    mocks.historySave.mockResolvedValue(DECLARATION);
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByRole("option", { name: SOURCE.title }); // the catalog loads after the label renders
    await user.selectOptions(screen.getByLabelText("Recorded source"), SOURCE.source_id);
    const save = screen.getByRole("button", { name: "Save history declaration" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Your hypothesis in your own words"), "Rises continue");
    await user.type(screen.getByLabelText("Rule 1 lookback buckets"), "2");
    await user.type(screen.getByLabelText("Rule 1 return threshold"), "0.004");
    await user.type(screen.getByLabelText("Rule 1 volume threshold"), "100");
    expect(save).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /before any data is read/ }));
    await user.click(save);
    await screen.findByText(/Declaration saved before any collection/);
    const body = mocks.historySave.mock.calls[0][1];
    expect(body.configuration.source).toEqual({ source_id: SOURCE.source_id, profile_sha256: SOURCE.profile_sha256,
      evidence_class: "RECORDED_RESPONSE" });
    expect(body.configuration.question).toBe("test request");
    expect(body.configuration.rule_map.rules[0]).toMatchObject({ rule_source: "USER_ADOPTED",
      price_expression: { op: "gt", args: [{ op: "price_return", lookback_buckets: 2 },
        { op: "constant", value: "0.004", unit: "DIMENSIONLESS" }] } });
    expect(body.configuration.permitted_access).toEqual(["RECORDED_RESPONSE"]);
    expect(Object.values(body.field_origins).every((item) => (item as { adoption: string }).adoption === "ADOPTED")).toBe(true);
  });

  it("shows a waiting job and cancels it", async () => {
    const user = userEvent.setup();
    mocks.jobs.mockResolvedValueOnce({ jobs: [job("RESERVED")] }).mockResolvedValue({ jobs: [job("CANCELLED")] });
    mocks.cancelJob.mockResolvedValue(job("CANCELLED"));
    await openSaved(user);
    expect(await screen.findByText(/Waiting for the research worker/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel this job" }));
    expect(mocks.cancelJob).toHaveBeenCalledWith("job-RESERVED");
    expect(await screen.findByText(/^Cancelled\./)).toBeInTheDocument();
  });

  it("retries a failed job as a new job with a new request key", async () => {
    const user = userEvent.setup();
    mocks.jobs.mockResolvedValue({ jobs: [job("FAILED")] });
    mocks.startJob.mockResolvedValue(job("RESERVED"));
    await openSaved(user);
    await user.click(await screen.findByRole("button", { name: "Start investigation job" }));
    await user.click(await screen.findByRole("button", { name: "Retry as a new job" }));
    const [first, second] = mocks.startJob.mock.calls.map((call) => call[2].request_key);
    expect(first).toBeTruthy(); expect(second).toBeTruthy(); expect(second).not.toBe(first);
  });

  it("shows a budget denial and an uncertain start reuses the same request", async () => {
    const user = userEvent.setup();
    mocks.startJob.mockRejectedValueOnce(new mocks.ApiError("budget"))
      .mockRejectedValueOnce(Object.assign(new mocks.ApiError("net"), { status: 0, code: "network_error", detail: "x" }))
      .mockResolvedValueOnce(job("RESERVED"));
    await openSaved(user);
    await user.click(screen.getByRole("button", { name: "Start investigation job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
    await user.click(screen.getByRole("button", { name: "Start investigation job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not confirm the start");
    await user.click(screen.getByRole("button", { name: "Check again with the same start" }));
    await waitFor(() => expect(mocks.startJob).toHaveBeenCalledTimes(3));
    expect(mocks.startJob.mock.calls[2][2]).toEqual(mocks.startJob.mock.calls[1][2]);
  });

  it("shows a saved report honestly", async () => {
    const user = userEvent.setup();
    const report = { report_id: "rep-1", content_sha256: "s", stored_hash_matches_content: true, created_at: "",
      content: { outcome: "CONTRADICTORY", outcome_reasons: ["variant_contrasts_have_opposite_signs"], outcome_accessed: true,
        statistical_status: "UNRESOLVED", claims: { significance: "NOT_CLAIMED", capital_authority: "NONE" },
        variants: [{ evaluation_id: "e1", variant_id: "rule-1", outcome: "DESCRIBED", triggered_minus_control_mean: "0.01",
          triggered_observed: 4, control_observed: 5 }], contrary_findings: [],
        protected_evaluations: [], protected_partitions: [{ partition_id: "holdout", role: "HOLDOUT", state: "NOT_READ" }],
        dataset_id: "ds-1",
        source_id: SOURCE.source_id, evidence_class: "RECORDED_RESPONSE", content_label: "SYNTHETIC_FIXTURE",
        dataset_verdict: { overall: "QUALIFIED" }, rule_map_sha256: "r", hypothesis: "h", notice: "Descriptive only." } };
    mocks.jobs.mockResolvedValue({ jobs: [job("REPORTED", { report })] });
    await openSaved(user);
    expect(await screen.findByText("Saved report: CONTRADICTORY")).toBeInTheDocument();
    expect(screen.getByText(/significance NOT_CLAIMED/)).toBeInTheDocument();
    expect(screen.getByText(/Not read: HOLDOUT partition/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry as a new job" })).toBeNull();
  });
});


describe("native recorded source (SOURCE-LOCAL)", () => {
  const NATIVE = { ...SOURCE, source_id: "native-syn-qualified/1", title: "Native recording, full corroboration (qualifies)",
    evidence_class: "RECORDED_NATIVE_RESPONSE", market: { network: "MONAD", pool_address: "0xd1d1", base_asset: "0xd3d3", quote_asset: "0xd2d2" },
    transport: { history_provider: "ENVIO_HYPERSYNC", provider_version: "envio-hypersync/1", corroboration_provider: "QUICKNODE_JSON_RPC",
      corroboration_sample_size: 24, provider_requests_needed: 27 } };

  it("declares with the source's own class and reserves its pages, chain read and receipts", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE, NATIVE] });
    mocks.historySave.mockResolvedValue(DECLARATION);
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByRole("option", { name: NATIVE.title });
    await user.selectOptions(screen.getByLabelText("Recorded source"), NATIVE.source_id);
    expect(screen.getByTestId("history-source-transport")).toHaveTextContent("It needs 27 provider requests: 2 pages, one chain read and 24 receipts.");
    expect(screen.getByTestId("history-source-transport")).toHaveTextContent("against recorded responses only");
    // Switching to a bundle source and back resets the reservation to each source's own need (Review A N2).
    await user.selectOptions(screen.getByLabelText("Recorded source"), SOURCE.source_id);
    expect(screen.getByLabelText("Bound provider_requests")).toHaveValue("2");
    await user.selectOptions(screen.getByLabelText("Recorded source"), NATIVE.source_id);
    expect(screen.getByLabelText("Bound provider_requests")).toHaveValue("27");
    await user.type(screen.getByLabelText("Your hypothesis in your own words"), "Rises continue");
    await user.type(screen.getByLabelText("Rule 1 lookback buckets"), "2");
    await user.type(screen.getByLabelText("Rule 1 return threshold"), "0.004");
    await user.type(screen.getByLabelText("Rule 1 volume threshold"), "100");
    await user.click(screen.getByRole("checkbox", { name: /before any data is read/ }));
    await user.click(screen.getByRole("button", { name: "Save history declaration" }));
    await screen.findByText(/Declaration saved before any collection/);
    const body = mocks.historySave.mock.calls[0][1];
    expect(body.configuration.source.evidence_class).toBe("RECORDED_NATIVE_RESPONSE");
    expect(body.configuration.permitted_access).toEqual(["RECORDED_NATIVE_RESPONSE"]);
    expect(body.configuration.resource_bounds.provider_requests).toBe(27);
    expect(body.configuration.market.pool_address).toBe("0xd1d1");
  });

  it("shows computed transport facts apart from recorded declarations", async () => {
    const user = userEvent.setup();
    const dataset = { dataset_id: "ds-n", content_sha256: "s", hashes_verified: {}, summary: { source_id: NATIVE.source_id,
      status: "COMPLETE", stop_reason: "COMPLETE", verdict: { overall: "LIMITED" }, binding_state: "UNAVAILABLE_LIMITED_DATA",
      unavailable_states: ["VERDICT_LIMITED"], provider_requests: { ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 9 },
      provider_requests_state: "MEASURED_CLIENT_CALLS", evidence_class: "RECORDED_NATIVE_RESPONSE", content_label: "SYNTHETIC_FIXTURE" },
      transport: { envio_pages_framed: 2, client_calls: { ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 9 }, chain_id: 143, chain_network: "MONAD",
        corroboration: { class: "SAMPLED", sample_size: 8, population_size: 24, mismatches: 0 }, corroboration_reason: null,
        recorded_declarations: ["decimals", "pool_tokens"] } };
    mocks.jobs.mockResolvedValue({ jobs: [job("REPORTED", { dataset })] });
    mocks.historyList.mockResolvedValue({ declarations: [DECLARATION] });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await user.click(await screen.findByRole("button", { name: "Open this declaration" }));
    const facts = await screen.findByTestId("history-transport");
    expect(facts).toHaveTextContent("chain id checked against recorded responses: 143 (MONAD)");
    expect(facts).toHaveTextContent("receipt corroboration SAMPLED, 8 of 24 checked, 0 mismatches");
    expect(facts).toHaveTextContent("Recorded declarations, not read by the application: decimals, pool tokens.");
    expect(screen.getByText(/LIMITED, UNAVAILABLE_LIMITED_DATA/)).toBeInTheDocument();
  });

  it("labels facts from the P07 HTTP clients as authored responses and disables an unavailable source", async () => {
    const user = userEvent.setup();
    const HTTP = { ...NATIVE, source_id: "native-http-qualified/1", title: "Native recording through the HTTP clients",
      evidence_class: "AUTHORED_HTTP_RESPONSE", available: false,
      transport: { ...NATIVE.transport, clients: "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT" } };
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE, NATIVE, HTTP] });
    const dataset = { dataset_id: "ds-h", content_sha256: "s", hashes_verified: {}, summary: { source_id: HTTP.source_id,
      status: "COMPLETE", stop_reason: "COMPLETE", verdict: { overall: "QUALIFIED" }, binding_state: "BOUND",
      unavailable_states: [], provider_requests: { ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 25 },
      provider_requests_state: "MEASURED_CLIENT_CALLS", evidence_class: "AUTHORED_HTTP_RESPONSE", content_label: "SYNTHETIC_FIXTURE" },
      transport: { envio_pages_framed: 2, client_calls: { ENVIO_HYPERSYNC: 2, QUICKNODE_JSON_RPC: 25 }, chain_id: 143, chain_network: "MONAD",
        corroboration: { class: "COMPLETE", sample_size: 24, population_size: 24, mismatches: 0 }, corroboration_reason: null,
        recorded_declarations: ["decimals"], clients: "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT",
        client_classes: { ENVIO_HYPERSYNC: "HttpEnvioQueryClient", QUICKNODE_JSON_RPC: "HttpQuickNodeRpcClient" },
        transport_label: "AUTHORED_HTTP_TRANSPORT" } };
    mocks.jobs.mockResolvedValue({ jobs: [job("REPORTED", { dataset })] });
    mocks.historyList.mockResolvedValue({ declarations: [DECLARATION] });
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    const option = await screen.findByRole("option", { name: /HTTP clients \(not available on this server\)/ });
    expect(option).toBeDisabled();
    await user.click(await screen.findByRole("button", { name: "Open this declaration" }));
    const facts = await screen.findByTestId("history-transport");
    expect(facts).toHaveTextContent("Authored HTTP responses served on this server through the accepted P07 HTTP clients (HttpEnvioQueryClient, HttpQuickNodeRpcClient), no network. Not provider data:");
    expect(facts).not.toHaveTextContent("Native recording, replayed locally");
  });
});


describe("recorded-history declaration lost reply", () => {
  it("retries an unconfirmed save with the exact same body", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE] });
    mocks.historySave.mockRejectedValueOnce(Object.assign(new mocks.ApiError("net"), { status: 0, code: "timeout", detail: "x" }))
      .mockResolvedValueOnce(DECLARATION);
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByRole("option", { name: SOURCE.title }); // the catalog loads after the label renders
    await user.selectOptions(screen.getByLabelText("Recorded source"), SOURCE.source_id);
    await user.type(screen.getByLabelText("Your hypothesis in your own words"), "Rises continue");
    await user.type(screen.getByLabelText("Rule 1 lookback buckets"), "2");
    await user.type(screen.getByLabelText("Rule 1 return threshold"), "0.004");
    await user.type(screen.getByLabelText("Rule 1 volume threshold"), "100");
    await user.click(screen.getByRole("checkbox", { name: /before any data is read/ }));
    await user.click(screen.getByRole("button", { name: "Save history declaration" }));
    expect(await screen.findByText(/could not confirm the save/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save history declaration" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry the same declaration" }));
    await screen.findByText(/Declaration saved before any collection/);
    expect(mocks.historySave.mock.calls[1][1]).toEqual(mocks.historySave.mock.calls[0][1]);
  });

  it("keeps the unconfirmed body across a reload of the page", async () => {
    const user = userEvent.setup();
    mocks.historySources.mockResolvedValue({ label: "SYNTHETIC", mode: "recorded", sources: [SOURCE] });
    mocks.historySave.mockRejectedValueOnce(Object.assign(new mocks.ApiError("net"), { status: 0, code: "timeout", detail: "x" }))
      .mockResolvedValueOnce(DECLARATION);
    const first = render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await screen.findByRole("option", { name: SOURCE.title });
    await user.selectOptions(screen.getByLabelText("Recorded source"), SOURCE.source_id);
    await user.type(screen.getByLabelText("Your hypothesis in your own words"), "Rises continue");
    await user.type(screen.getByLabelText("Rule 1 lookback buckets"), "2");
    await user.type(screen.getByLabelText("Rule 1 return threshold"), "0.004");
    await user.type(screen.getByLabelText("Rule 1 volume threshold"), "100");
    await user.click(screen.getByRole("checkbox", { name: /before any data is read/ }));
    await user.click(screen.getByRole("button", { name: "Save history declaration" }));
    await screen.findByText(/could not confirm the save/);
    first.unmount();
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    await user.click(await screen.findByRole("button", { name: "Retry the same declaration" }));
    await screen.findByText(/Declaration saved before any collection/);
    expect(mocks.historySave.mock.calls[1][1]).toEqual(mocks.historySave.mock.calls[0][1]);
  });
});
