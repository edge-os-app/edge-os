import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentHealthConversation, AgentHealthPanel } from "../components/AgentHealthConversation";
import { Conversation } from "../components/Conversation";
import { ApiError, type AgentHealth, type HealthExplanation } from "../lib/api";

const mocks = vi.hoisted(() => ({ read: vi.fn(), explain: vi.fn() }));
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, agentHealth: { read: (...a: unknown[]) => mocks.read(...a), explain: (...a: unknown[]) => mocks.explain(...a) } };
});

const unknown = (reason: string) => ({ state: "UNKNOWN" as const, reason });
const known = <T,>(value: T, source = "producer") => ({ state: "KNOWN" as const, value, source });

function snapshot(over: Partial<AgentHealth> = {}): AgentHealth {
  return {
    schema_version: "edge-os.agent-health-projection/1", record_type: "AgentHealthProjection", evidence_class: "SERVICE_PROJECTION",
    record_id: "health:o:agent-a:w:monad-testnet:dep-1", notice: "Read-only service projection.", provider_mode: "fixture",
    read_at: "2026-10-13T09:07:30Z", as_of_meaning: "newest stored write",
    as_of: { table: "execution_local.execution_queue", id: "q-1", field: "updated_at", time: "2026-10-13T09:06:12Z" },
    snapshot_digest: "sha256:first",
    scope: { owner_id: "o", agent_id: "agent-a", wallet_id: "w", network_id: "monad-testnet", deployment_id: "dep-1" },
    deployment: { deployment_id: "dep-1", state: "ACTIVE", end_reason: null, activated_at: "2026-10-13T09:01:00Z", ended_at: null },
    identity: { saved_deployment: { execution_revision_id: "rev-1" }, current_resolution: known({ execution_revision_id: "rev-1" }),
      changed: known(false) },
    producer: { next_due_slot: known("2026-10-13T09:10:00Z"), producer_silent: known(false), last_tick_at: known("2026-10-13T09:06:00Z"),
      cursor_slot: known("2026-10-13T09:05:00Z"), missed_slots: known(0) },
    wait_reason: known(null),
    window: { occurrences_shown: 1, limit: 20 },
    occurrences: [],
    last_evaluation: known({ job_id: "job-1", decision_slot: "2026-10-13T09:05:00Z", job_state: "COMPLETED",
      evaluation: { outcome: "SIGNAL", reason: null, inputs_observed_at: known("2026-10-13T09:05:00Z"),
        inputs_collected_at: unknown("INPUT_COLLECTION_TIME_NOT_SAVED"), evaluated_at: known("2026-10-13T09:06:10Z"),
        evidence_class: "SYNTHETIC_FIXTURE" } }),
    last_trade_attempt: known({ job_id: "job-1", decision_slot: "2026-10-13T09:05:00Z", action_id: "act-1",
      job_outcome: "SUBMITTED_CONFIRMED", submission: { attempt_id: "att", state: "TERMINAL", outcome: "CONFIRMED",
        started_at: known("2026-10-13T09:06:11Z"), completed_at: known("2026-10-13T09:06:12Z") } }),
    pending_reconciliation: {
      canonical: { rule: "PRODUCER_UNSETTLED_QUEUE", queue_states: ["CLAIMED"], source: "producer", action_ids: ["act-9"] },
      warnings: [{ kind: "ACCOUNT_RECOVERY_OPEN_OR_UNKNOWN", source: "recovery", action_ids: ["act-9"] },
        { kind: "MONITORING_SUBMITTED_UNKNOWN", source: "jobs", pending: true }] },
    controls: { stops: [{ stop_id: "s1", mode: "STOP_NEW_ENTRIES", scope: "AGENT_WALLET_NETWORK", position_id: null,
      created_at: "2026-10-13T09:07:00Z" }], removals: [], control_state_basis: unknown("PRODUCER_INPUT_MISSING") },
    residual_inventory: [{ position_id: "pos-1", asset_id: "monad-testnet/0x11", quantity: { asset_id: "monad-testnet/0x11",
      raw: "50000000000000000000", decimals: 18 }, position_state: "OPEN", updated_at: "2026-10-13T09:06:12Z" }],
    unknown_inputs: [{ field: "native_gas_aggregate", state: "UNKNOWN", reason: "PRODUCER_INPUT_MISSING: only per-receipt gas" }],
    record_refs: [],
    ...over,
  };
}

function reply(snap: AgentHealth, text: string, topic = "last"): HealthExplanation {
  return { schema_version: "edge-os.agent-health-explanation/1", question: "q", topic, record_id: snap.record_id,
    snapshot_digest: snap.snapshot_digest, as_of: snap.as_of, read_at: snap.read_at, answer: [{ text, fields: ["last_evaluation"] }],
    notice: "Read-only answer from saved records.", snapshot: snap };
}

beforeEach(() => { vi.resetAllMocks(); });

describe("direct agent health", () => {
  it("shows dated, sourced facts and keeps each unknown explicit", async () => {
    mocks.read.mockResolvedValue(snapshot());
    render(<AgentHealthPanel agentId="agent-a" />);
    const panel = await screen.findByRole("region", { name: "Agent health" });
    const facts = within(panel);
    expect(await facts.findByTestId("health-as-of")).toHaveTextContent(
      "2026-10-13T09:06:12Z (execution_local.execution_queue q-1 updated_at)");
    expect(facts.getByTestId("health-read-at")).toHaveTextContent("2026-10-13T09:07:30Z");
    expect(facts.getByTestId("health-next")).toHaveTextContent("2026-10-13T09:10:00Z");
    expect(facts.getByTestId("health-last-evaluation")).toHaveTextContent("SIGNAL");
    expect(facts.getByTestId("health-last-evaluation")).toHaveTextContent("collected Unknown (INPUT_COLLECTION_TIME_NOT_SAVED)");
    expect(facts.getByTestId("health-last-attempt")).toHaveTextContent("act-1");
    expect(facts.getByTestId("health-pending")).toHaveTextContent("act-9");
    expect(facts.getByTestId("health-warnings")).toHaveTextContent("ACCOUNT_RECOVERY_OPEN_OR_UNKNOWN");
    expect(facts.getByTestId("health-controls")).toHaveTextContent("STOP_NEW_ENTRIES");
    expect(facts.getByTestId("health-inventory")).toHaveTextContent("50000000000000000000");
    expect(facts.getByTestId("health-unknowns")).toHaveTextContent("native_gas_aggregate");
    expect(facts.getByTestId("health-digest")).toHaveTextContent("sha256:first");
    expect(mocks.read).toHaveBeenCalledWith("agent-a");
  });

  it("says when no deployment exists instead of inventing next work", async () => {
    mocks.read.mockResolvedValue(snapshot({ deployment: null, as_of: null,
      producer: { next_due_slot: unknown("NO_DEPLOYMENT"), producer_silent: unknown("NO_DEPLOYMENT"),
        last_tick_at: unknown("NO_DEPLOYMENT"), cursor_slot: unknown("NO_DEPLOYMENT"), missed_slots: unknown("NO_DEPLOYMENT") },
      wait_reason: unknown("NO_DEPLOYMENT") }));
    render(<AgentHealthPanel agentId="agent-a" />);
    expect(await screen.findByTestId("health-next")).toHaveTextContent("Unknown (NO_DEPLOYMENT)");
    expect(screen.getByTestId("health-as-of")).toHaveTextContent("No stored write");
  });

  it("keeps the panel usable when the read fails", async () => {
    mocks.read.mockRejectedValueOnce(new ApiError(404, "not_found", "No agent wallet."));
    render(<AgentHealthPanel agentId="agent-a" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No agent wallet.");
  });
});

describe("read-only agent health conversation", () => {
  it("answers from the same dated snapshot and keeps each saved reply's original date", async () => {
    const first = snapshot();
    const second = snapshot({ read_at: "2026-10-13T09:12:30Z", snapshot_digest: "sha256:second",
      as_of: { table: "execution_local.execution_evaluation_jobs", id: "job-2", field: "updated_at", time: "2026-10-13T09:11:00Z" } });
    mocks.explain.mockResolvedValueOnce(reply(first, "Last saved evaluation: slot 09:05, outcome SIGNAL."))
      .mockResolvedValueOnce(reply(second, "Next due slot from the producer: 2026-10-13T09:15:00Z.", "next"));
    render(<AgentHealthConversation agentId="agent-a" />);
    await userEvent.click(screen.getByRole("button", { name: "What did it last do?" }));
    const log = screen.getByRole("log", { name: "Health conversation" });
    expect(await within(log).findByText("Last saved evaluation: slot 09:05, outcome SIGNAL.")).toBeDefined();
    await userEvent.type(screen.getByLabelText("Ask about this agent's health"), "what is next?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await within(log).findByText("Next due slot from the producer: 2026-10-13T09:15:00Z.")).toBeDefined();
    const replies = within(log).getAllByTestId("health-reply");
    expect(replies).toHaveLength(2);
    expect(replies[0]).toHaveTextContent("Read 2026-10-13T09:07:30Z");
    expect(replies[0]).toHaveTextContent("sha256:first");
    expect(replies[1]).toHaveTextContent("Read 2026-10-13T09:12:30Z");
    expect(replies[1]).toHaveTextContent("2026-10-13T09:11:00Z (execution_local.execution_evaluation_jobs job-2 updated_at)");
    expect(mocks.explain.mock.calls).toEqual([["agent-a", "What did it last do?"], ["agent-a", "what is next?"]]);
  });

  it("offers no financial control and keeps earlier replies when a question fails", async () => {
    mocks.explain.mockResolvedValueOnce(reply(snapshot(), "Wait reason none."))
      .mockRejectedValueOnce(new ApiError(0, "network_error", "The service could not be reached."));
    render(<AgentHealthConversation agentId="agent-a" />);
    await userEvent.click(screen.getByRole("button", { name: "Why is it waiting?" }));
    expect(await screen.findByText("Wait reason none.")).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Is anything pending?" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The service could not be reached.");
    expect(screen.getByText("Wait reason none.")).toBeDefined();
    // Only the read-only questions and Ask exist: no control can start, stop, end, remove or sell anything.
    const names = screen.getAllByRole("button").map((b) => b.textContent ?? "");
    expect(names).toEqual(["What did it last do?", "What is next?", "Why is it waiting?", "Is anything pending?",
      "Was it stopped or removed?", "What inventory is left?", "Did the revision change?", "What is unknown?", "Ask"]);
  });

  it("keeps text typed while an earlier question is answered", async () => {
    let finish: (value: HealthExplanation) => void = () => {};
    mocks.explain.mockReturnValueOnce(new Promise<HealthExplanation>((resolve) => { finish = resolve; }));
    render(<AgentHealthConversation agentId="agent-a" />);
    await userEvent.click(screen.getByRole("button", { name: "What is next?" }));
    await userEvent.type(screen.getByLabelText("Ask about this agent's health"), "what is left?");
    finish(reply(snapshot(), "Next due slot from the producer: 2026-10-13T09:10:00Z.", "next"));
    expect(await screen.findByText("Next due slot from the producer: 2026-10-13T09:10:00Z.")).toBeDefined();
    expect(screen.getByLabelText("Ask about this agent's health")).toHaveValue("what is left?");
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("is the conversation's dedicated agent branch; Research keeps its own panel", async () => {
    const { unmount } = render(<Conversation context={null} idPrefix="side" agentId="agent-a" />);
    expect(screen.getByRole("button", { name: "What did it last do?" })).toBeDefined();
    expect(screen.getByText(/agent-a/)).toBeDefined();
    unmount();
    render(<Conversation context={null} idPrefix="side" />);
    expect(screen.getByText(/Open a request to see its questions here/)).toBeDefined();
    expect(screen.queryByRole("button", { name: "What did it last do?" })).toBeNull();
  });
});
