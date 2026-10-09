import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvestigationReview } from "../components/InvestigationReview";

const mocks = vi.hoisted(() => ({ proposal: vi.fn(), list: vi.fn(), save: vi.fn(), get: vi.fn(),
  ApiError: class extends Error { status = 503; detail = "Unavailable"; code = "service_unavailable"; } }));
vi.mock("../lib/api", () => ({
  ApiError: mocks.ApiError,
  api: {
    investigationProposal: (...args: unknown[]) => mocks.proposal(...args),
    investigations: (...args: unknown[]) => mocks.list(...args),
    saveInvestigation: (...args: unknown[]) => mocks.save(...args),
    investigation: (...args: unknown[]) => mocks.get(...args),
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
  window.sessionStorage.clear();
  vi.clearAllMocks();
  mocks.proposal.mockResolvedValue(proposal);
  mocks.list.mockResolvedValue({ declarations: [], access_history: [] });
  mocks.save.mockResolvedValue(saved);
  mocks.get.mockResolvedValue(saved);
});

describe("investigation declaration adoption", () => {
  it("requires explicit adoption, saves the whole bounded declaration, and reopens the exact record", async () => {
    render(<InvestigationReview intakeId="intake-1" interpretationRevisionId={null} />);
    expect(await screen.findByLabelText("I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Adopt and save declaration" });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
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
    await user.click(screen.getByRole("checkbox"));
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
        await user.click(screen.getByRole("checkbox"));
        await user.click(screen.getByRole("button", { name: "Adopt and save declaration" }));
        await screen.findByText(/unsaved edits remain in place/);
        expect(screen.getByRole("checkbox")).not.toBeChecked();
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

      expect(screen.getByRole("checkbox")).not.toBeChecked();
      await user.click(screen.getByRole("checkbox"));
      await user.click(screen.getByRole("button", { name: "Adopt and save declaration" }));
      await screen.findByRole("heading", { name: "Declaration saved" });
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
