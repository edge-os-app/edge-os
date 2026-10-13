import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentRecurring } from "../components/AgentRecurring";

const mocks = vi.hoisted(() => ({ deployment: vi.fn(), consent: vi.fn(), activate: vi.fn(), end: vi.fn() }));
vi.mock("../lib/financial", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/financial")>();
  return { ...actual, financial: { ...actual.financial,
    deployment: (...args: unknown[]) => mocks.deployment(...args), consent: (...args: unknown[]) => mocks.consent(...args),
    activateDeployment: (...args: unknown[]) => mocks.activate(...args), endDeployment: (...args: unknown[]) => mocks.end(...args) } };
});

const HASH = "sha256:" + "a".repeat(64);
const consent = { agent_id: "agent-a", reviews: [], assets: null, identity: null,
  adoptions: [{ adoption_id: "adopt-1", review_id: "r", review_hash: "h", consent_hash: HASH, status: "INACTIVE", content: {},
    created_at: "2026-10-13T09:00:00Z" }],
  activation: { state: "FIXTURE_QUALIFIED", reason: null, evidence_class: "SYNTHETIC_FIXTURE" } };
const deployment = { deployment_id: "dep-1", state: "ACTIVE", end_reason: null, request_key: "k", activated_at: "2026-10-13T09:01:00Z",
  ended_at: null, identity: { agent_id: "agent-a", wallet_id: "w", network_id: "monad-testnet:10143", strategy_id: "s",
    publication_revision_id: "p", execution_revision_id: "rev", content_hash: "c", manifest_hash: "m",
    consent_adoption_id: "adopt-1", consent_hash: HASH } };
const occurrence = { job_id: "job-1", agent_id: "agent-a", request_key: "recurring:dep-1", decision_slot: "2026-10-13T09:05:00Z",
  state: "COMPLETED", publication_revision_id: "p", execution_revision_id: "rev", consent_adoption_id: "adopt-1", decision_id: "d",
  action_id: "act-1", outcome: "SUBMITTED_CONFIRMED", reason: null, runs: 1, created_at: "x", updated_at: "y", deployment_id: "dep-1",
  evaluation: { outcome: "SIGNAL", reason: null, decision_id: "d", inputs_observed_at: "2026-10-13T09:05:00Z",
    inputs_collected_at: "2026-10-13T09:05:00Z", evaluated_at: "2026-10-13T09:06:10Z", evidence_class: "SYNTHETIC_FIXTURE" },
  submission: { attempt_id: "att", state: "TERMINAL", outcome: "CONFIRMED", started_at: "2026-10-13T09:06:11Z",
    completed_at: "2026-10-13T09:06:12Z" } };

function projection(over: Record<string, unknown> = {}) {
  return { deployment, producer: { last_tick_at: "2026-10-13T09:06:00Z", cursor_slot: "2026-10-13T09:05:00Z", producer_silent: false,
    next_due_slot: "2026-10-13T09:10:00Z", no_next_reason: null, occurrences: 1, missed_slots: 3,
    missed_intervals: [{ from: "2026-10-13T08:50:00Z", to: "2026-10-13T09:00:00Z", count: 3, reason: "PRODUCER_ABSENT", recorded_at: "z" }] },
    occurrences: [occurrence], pending_reconciliation: [], stops: [], removal: [], wait_reason: null, ...over };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.consent.mockResolvedValue(consent);
});

describe("recurring operation", () => {
  it("starts only after explicit authorization, binding the exact adopted terms", async () => {
    mocks.deployment.mockResolvedValueOnce({ deployment: null }).mockResolvedValue(projection());
    mocks.activate.mockResolvedValue(deployment);
    render(<AgentRecurring agentId="agent-a" />);
    const start = await screen.findByRole("button", { name: "Start recurring operation" });
    expect(start).toBeDisabled();
    expect(screen.getByTestId("recurring-activate")).toHaveTextContent(HASH);
    await userEvent.click(screen.getByRole("checkbox", { name: /I authorize repeated evaluations/ }));
    await userEvent.click(start);
    const [agent, key, hash] = mocks.activate.mock.calls[0];
    expect([agent, hash]).toEqual(["agent-a", HASH]);
    expect(key).toMatch(/^ui-/);
    expect(await screen.findByText("Recurring operation started. The scheduler saves each slot's evaluation.")).toBeDefined();
    expect(await screen.findByTestId("recurring-deployment")).toHaveAttribute("data-state", "ACTIVE");
  });

  it("shows the durable scheduler record: next slot, missed slots, input and submission times", async () => {
    mocks.deployment.mockResolvedValue(projection());
    render(<AgentRecurring agentId="agent-a" />);
    expect(await screen.findByTestId("recurring-wait")).toHaveTextContent("Active. Next slot 2026-10-13T09:10:00Z.");
    expect(screen.getByTestId("recurring-missed")).toHaveTextContent("3 · latest 2026-10-13T08:50:00Z to 2026-10-13T09:00:00Z, not replayed");
    const slots = within(screen.getByTestId("recurring-occurrences"));
    expect(slots.getByText(/SIGNAL · SUBMITTED_CONFIRMED/)).toBeDefined();
    expect(screen.getByTestId("recurring-occurrences")).toHaveTextContent(
      "Inputs observed 2026-10-13T09:05:00Z, collected 2026-10-13T09:05:00Z, evaluated 2026-10-13T09:06:10Z (SYNTHETIC_FIXTURE).");
    expect(screen.getByTestId("recurring-occurrences")).toHaveTextContent("Submission TERMINAL CONFIRMED, started 2026-10-13T09:06:11Z, completed 2026-10-13T09:06:12Z.");
  });

  it.each([
    ["WAITING_RECONCILIATION", "Waiting: an earlier action's outcome is unknown."],
    ["PRODUCER_NOT_SEEN", "Waiting: no scheduler pass was recorded in the last two slots."],
    ["STOPPED:STOP_NEW_ENTRIES", "Stopped: stop new entries denies matching work."],
    ["ENDED:REMOVAL_REQUESTED", "Ended: Agent removal was requested."],
  ])("states the saved wait reason %s honestly", async (reason, text) => {
    mocks.deployment.mockResolvedValue(projection({ wait_reason: reason, pending_reconciliation: reason === "WAITING_RECONCILIATION" ? ["act-9"] : [] }));
    render(<AgentRecurring agentId="agent-a" />);
    expect(await screen.findByTestId("recurring-wait")).toHaveTextContent(text);
  });

  it("ends recurring operation without claiming anything was sold or cancelled", async () => {
    mocks.deployment.mockResolvedValueOnce(projection()).mockResolvedValue(projection({
      deployment: { ...deployment, state: "ENDED", end_reason: "OWNER_ENDED", ended_at: "t" }, wait_reason: "ENDED:OWNER_ENDED",
      producer: { ...projection().producer, next_due_slot: null, no_next_reason: "OWNER_ENDED" } }));
    mocks.end.mockResolvedValue({ ...deployment, state: "ENDED" });
    render(<AgentRecurring agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "End recurring operation" }));
    expect(mocks.end).toHaveBeenCalledWith("agent-a");
    expect(await screen.findByTestId("recurring-wait")).toHaveTextContent("Ended: You ended recurring operation.");
    expect(screen.getByTestId("recurring-next")).toHaveTextContent("None (OWNER_ENDED)");
    expect(screen.queryByRole("button", { name: "End recurring operation" })).toBeNull();
  });

  it("says a silent producer has no next slot and a job that ended unevaluated was not evaluated", async () => {
    mocks.deployment.mockResolvedValue(projection({ wait_reason: "PRODUCER_NOT_SEEN",
      producer: { ...projection().producer, producer_silent: true, next_due_slot: null, no_next_reason: "PRODUCER_NOT_SEEN" },
      occurrences: [{ ...occurrence, state: "COMPLETED", outcome: "DENIED", reason: "DEPLOYMENT_ENDED:OWNER_ENDED",
        action_id: null, evaluation: null, submission: null }] }));
    render(<AgentRecurring agentId="agent-a" />);
    expect(await screen.findByTestId("recurring-next")).toHaveTextContent("None (PRODUCER_NOT_SEEN)");
    expect(screen.getByTestId("recurring-occurrences")).toHaveTextContent("Ended without an evaluation · DENIED · DEPLOYMENT_ENDED:OWNER_ENDED");
  });

  it("refuses to offer activation when the terms are not qualified", async () => {
    mocks.deployment.mockResolvedValue({ deployment: null });
    mocks.consent.mockResolvedValue({ ...consent, activation: { state: "UNAVAILABLE", reason: "ACTIVATION_UNAVAILABLE", evidence_class: null } });
    render(<AgentRecurring agentId="agent-a" />);
    expect(await screen.findByTestId("recurring-unavailable")).toHaveTextContent("ACTIVATION_UNAVAILABLE");
    expect(screen.queryByRole("button", { name: "Start recurring operation" })).toBeNull();
  });
});
