import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvestigationReview } from "../components/InvestigationReview";

const mocks = vi.hoisted(() => ({ proposal: vi.fn(), list: vi.fn(), save: vi.fn(), get: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { status = 503; detail = "Unavailable"; },
  api: {
    investigationProposal: (...args: unknown[]) => mocks.proposal(...args),
    investigations: (...args: unknown[]) => mocks.list(...args),
    saveInvestigation: (...args: unknown[]) => mocks.save(...args),
    investigation: (...args: unknown[]) => mocks.get(...args),
  },
}));

const proposal = {
  schema_version: "p08.investigation-declaration/1",
  proposal_version: "p08-bounded-review/1",
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
    direction: "DESCRIPTIVE", horizons: ["15 minutes"], sources: ["fixture-unqualified-pool/1"],
    candidate_limit: 2, parameter_limit: 4,
    compute_limit: { max_evaluations: 2, max_runtime_seconds: 60, max_cost_usd: "0" },
    period: { start: "2026-01-01T00:00:00+00:00", end: "2026-01-03T00:00:00+00:00" },
    partitions: [{ partition_id: "descriptive", role: "DESCRIPTIVE" }], permitted_access: ["FIXTURE_ONLY"],
    stopping_rule: "Stop after two comparisons.", budget_version: "p08-research-budget/1",
    optional_tools: { creator_history: "UNAVAILABLE", wallet_pnl: "UNAVAILABLE", social_signals: "UNAVAILABLE" },
  },
  adopted_fields: [], field_origins: {}, trial_ids: ["22222222-2222-4222-8222-222222222222"],
  evaluation_ids: ["33333333-3333-4333-8333-333333333333"],
  notice: "Fixture-only proposal. No study runs.",
};

const saved = {
  declaration: {
    schema_version: "p08.investigation-declaration/1", record_type: "InvestigationDeclaration",
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
  vi.clearAllMocks();
  mocks.proposal.mockResolvedValue(proposal);
  mocks.list.mockResolvedValue({ declarations: [], access_history: [] });
  mocks.save.mockResolvedValue(saved);
  mocks.get.mockResolvedValue(saved);
});

describe("investigation declaration adoption", () => {
  it("requires explicit adoption, saves the whole bounded declaration, and reopens the exact record", async () => {
    render(<InvestigationReview intakeId="intake-1" />);
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
    render(<InvestigationReview intakeId="intake-1" />);
    expect(await screen.findByTestId("investigation-saved")).toHaveTextContent(saved.declaration.record_id);
    expect(screen.queryByLabelText(/I reviewed the hypothesis and every required setting/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reopen saved declaration" }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith("intake-1", saved.declaration.record_id));
  });
});
