import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import type { ActionDetail, AgentActions as AgentActionsView, ConsentState, FundingView } from "../lib/financial";
import { AgentActions } from "../components/AgentActions";
import { AgentAuthority } from "../components/AgentAuthority";
import { AgentFunding } from "../components/AgentFunding";
import { formatRaw } from "../lib/financial";

const mocks = vi.hoisted(() => ({
  funding: vi.fn(), declare: vi.fn(), prepareDeposit: vi.fn(), reconcileDeposits: vi.fn(),
  consent: vi.fn(), review: vi.fn(), adopt: vi.fn(),
  actions: vi.fn(), schedule: vi.fn(), action: vi.fn(), reconcileAction: vi.fn(),
  stops: vi.fn(), stop: vi.fn(), removals: vi.fn(), requestRemoval: vi.fn(), reconcileRemoval: vi.fn(),
}));
vi.mock("../lib/financial", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/financial")>();
  const wrapped = Object.fromEntries(Object.keys(mocks).map((name) =>
    [name, (...args: unknown[]) => (mocks as Record<string, (...a: unknown[]) => unknown>)[name](...args)]));
  return { ...original, financial: wrapped };
});

const QUOTE = { asset_id: "monad-testnet:10143/0x2222222222222222222222222222222222222222", decimals: 6 };
const BASE = { asset_id: "monad-testnet:10143/0x1111111111111111111111111111111111111111", decimals: 18 };
const GAS = { asset_id: "monad-testnet:10143/native", decimals: 18 };

function funding(over: Partial<FundingView> = {}): FundingView {
  return { agent_id: "agent-a", wallet_id: "fixture:o:agent-a", network_id: 10143, provider_mode: "fixture",
    declaration: { trading_asset: { ...QUOTE, raw: "0" }, gas_asset: { ...GAS, raw: "0" } }, flows: [],
    deposit_balances: [{ asset_class: "TRADING", asset_id: QUOTE.asset_id, credited_deposits: { ...QUOTE, raw: "1000000000" },
      pending_deposits: { ...QUOTE, raw: "0" } }],
    current_holdings: { state: "OBSERVED", evidence_class: "SYNTHETIC_FIXTURE", assets: [{ ...QUOTE, raw: "900000000" }] },
    allowances: [], ...over };
}

function consent(over: Partial<ConsentState> = {}): ConsentState {
  return { agent_id: "agent-a", adoptions: [], reviews: [], activation: { state: "UNAVAILABLE", reason: "CONSENT_NOT_ADOPTED", evidence_class: null },
    assets: { quote: QUOTE, base: BASE, gas: GAS },
    identity: { publication_revision_id: "11111111-1111-4111-8111-111111111111", execution_revision_id: "s:abc",
      wallet_id: "fixture:o:agent-a", network_id: "monad-testnet:10143" }, ...over };
}

function actions(over: Partial<AgentActionsView> = {}): AgentActionsView {
  return { agent_id: "agent-a", provider_mode: "fixture", identity: {}, jobs: [], decisions: [], queue: [], positions: [],
    blocking_reason: null, ...over };
}

function detail(over: Partial<ActionDetail> = {}): ActionDetail {
  return { action_id: "p23:d:ENTRY", agent_id: "agent-a", wallet_id: "w", network_id: "monad-testnet:10143", operation: "ENTRY",
    revision_id: "s:abc", mandate_id: "m-1", policy_binding: "sha256:p", payload_hash: "sha256:h",
    payload: { quantity: { ...BASE, raw: "50000000000000000000" }, input: { quote_input: { ...QUOTE, raw: "100000000" }, expected_quote: null } },
    decision: { decision_id: "d", decision_at: "2026-10-12T01:05:00Z", status: "SIGNAL", operation: "ENTRY", reasons: [] },
    queue: { queue_id: "q", action_id: "p23:d:ENTRY", operation: "ENTRY", position_id: "p", state: "SUBMITTED_UNKNOWN", blocking_reason: "SUBMISSION_UNKNOWN" },
    admission: [{ status: "SUBMISSION_UNKNOWN", reason: null }], reservations: [{ scope: "CAPITAL", asset_id: QUOTE.asset_id, decimals: 6, raw: "100000000", state: "RESERVED" }],
    receipts: [{ outcome: "SUBMISSION_UNKNOWN", breach: false, created_at: "2026-10-12T01:05:01Z", content: {} }],
    attempts: [{ attempt_id: "a", state: "TERMINAL", outcome: "SUBMISSION_POSSIBLE", detail: null,
      content: { original_references: { transaction_hash: null, absent_reason: "FIXTURE_TRANSPORT_SIGNS_NOTHING" } } }],
    recovery: null, ...over };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.stops.mockResolvedValue({ stops: [] });
  mocks.removals.mockResolvedValue({ removals: [] });
});

describe("amounts", () => {
  it("formats exact base units without floating point", () => {
    expect(formatRaw("100000000", 6)).toBe("100");
    expect(formatRaw("50000000000000000000", 18)).toBe("50");
    expect(formatRaw("1", 18)).toBe("0.000000000000000001");
    expect(formatRaw("123456789", 0)).toBe("123456789");
  });
});

describe("agent funding", () => {
  it("keeps credited deposits separate from current holdings and labels fixture evidence", async () => {
    mocks.funding.mockResolvedValue(funding());
    render(<AgentFunding agentId="agent-a" />);
    expect(await screen.findByTestId("funding-mode")).toHaveTextContent(/not a wallet, a transfer or chain evidence/);
    expect(screen.getByTestId("funding-credited")).toHaveTextContent("1000 credited");
    expect(screen.getByTestId("funding-holdings")).toHaveTextContent("Trading asset900 monad-testnet:10143/0x2222");
    expect(screen.getByTestId("funding-holdings")).toHaveTextContent("(SYNTHETIC_FIXTURE)");
  });

  it("shows unavailable holdings without inventing a balance", async () => {
    mocks.funding.mockResolvedValue(funding({ provider_mode: "unavailable",
      current_holdings: { state: "UNAVAILABLE", evidence_class: null, assets: [] } }));
    render(<AgentFunding agentId="agent-a" />);
    expect(await screen.findByTestId("funding-holdings")).toHaveTextContent("No balance is shown or assumed");
  });

  it("refuses a malformed amount and holds the reference across a lost reply", async () => {
    mocks.funding.mockResolvedValue(funding());
    mocks.prepareDeposit.mockRejectedValueOnce(new ApiError(0, "network_error", "unreachable"));
    render(<AgentFunding agentId="agent-a" />);
    const amount = await screen.findByLabelText(/Amount in base units/);
    await userEvent.type(amount, "007");
    expect(screen.getByRole("button", { name: "Save reviewed deposit" })).toBeDisabled();
    await userEvent.clear(amount);
    await userEvent.type(amount, "5");
    await userEvent.click(screen.getByRole("button", { name: "Save reviewed deposit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not confirmed");
    expect(screen.getByRole("button", { name: "Save reviewed deposit" })).toBeDisabled();
    const firstKey = mocks.prepareDeposit.mock.calls[0][1].reference;
    await userEvent.click(screen.getByRole("button", { name: "Check saved funding" }));
    mocks.prepareDeposit.mockResolvedValueOnce({});
    await waitFor(() => expect(screen.getByRole("button", { name: "Save reviewed deposit" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Save reviewed deposit" }));
    await waitFor(() => expect(mocks.prepareDeposit).toHaveBeenCalledTimes(2));
    expect(mocks.prepareDeposit.mock.calls[1][1].reference).toBe(firstKey);
  });

  it("reports a missing agent wallet and an expired session as errors", async () => {
    mocks.funding.mockRejectedValueOnce(new ApiError(404, "not_found", "missing"));
    const { unmount } = render(<AgentFunding agentId="agent-a" />);
    expect(await screen.findByText(/No confirmed wallet/)).toBeInTheDocument();
    unmount();
    mocks.funding.mockRejectedValueOnce(new ApiError(401, "auth_expired", "The access token expired."));
    render(<AgentFunding agentId="agent-a" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The access token expired.");
  });
});

describe("agent authority", () => {
  it("reviews exact terms, then adopts them as inactive and shows the activation verdict", async () => {
    mocks.consent.mockResolvedValueOnce(consent());
    const review = { review_id: "r-1", review_hash: "sha256:" + "a".repeat(64), status: "INACTIVE",
      content: { terms: { terms_version: "connected-spot/1", operating_purpose: "TRIAL", trial_objective: "x",
        allocation: [{ ...QUOTE, raw: "500000000" }], allowances: [{ name: "quote_input", amount: { ...QUOTE, raw: "500000000" } }],
        attempt_budget: 5, gas_budget: { ...GAS, raw: "1" }, expiry: "2030-01-01T00:00:00Z", supported_actions: ["ENTRY", "EXIT"],
        supported_assets: [], supported_routes: [], route: { adapter: "KURU_FLOW_FIXED_INPUT" },
        evidence: { status: "HYPOTHESIS", source: "s" }, stop_effects: ["stop"] } } };
    mocks.review.mockResolvedValue(review);
    mocks.consent.mockResolvedValueOnce(consent({ reviews: [review as never] }));
    render(<AgentAuthority agentId="agent-a" />);
    expect(await screen.findByTestId("activation-state")).toHaveTextContent("Adopt exact reviewed terms first");
    await userEvent.click(screen.getByRole("button", { name: "Review exact terms" }));
    const summary = await screen.findByTestId("consent-review");
    expect(summary).toHaveTextContent("Allocation500 monad-testnet:10143/0x2222");
    const terms = mocks.review.mock.calls[0][1];
    expect(terms.allowances.map((item: { name: string }) => item.name)).toEqual(["quote_input", "base_inventory", "per_action_gas", "per_exit_gas"]);
    expect(terms.allocation[0].asset_id).toBe(QUOTE.asset_id);
    mocks.adopt.mockResolvedValue({});
    mocks.consent.mockResolvedValueOnce(consent({ reviews: [review as never], adoptions: [{ adoption_id: "m-1", review_id: "r-1",
      review_hash: review.review_hash, consent_hash: "sha256:c", status: "INACTIVE", content: {}, created_at: "t" }],
      activation: { state: "FIXTURE_QUALIFIED", reason: null, evidence_class: "SYNTHETIC_FIXTURE_QUALIFICATION" } }));
    await userEvent.click(screen.getByRole("button", { name: "Adopt these exact terms (inactive)" }));
    expect(await screen.findByTestId("consent-adopted")).toHaveTextContent("status INACTIVE");
    expect(mocks.adopt).toHaveBeenCalledWith("agent-a", "r-1", review.review_hash);
    expect(screen.getByTestId("activation-state")).toHaveTextContent("not live authority");
  });

  it("explains why no action can run when the build has no qualified route", async () => {
    mocks.consent.mockResolvedValue(consent({ activation: { state: "UNAVAILABLE", reason: "ACTIVATION_UNAVAILABLE", evidence_class: null } }));
    render(<AgentAuthority agentId="agent-a" />);
    expect(await screen.findByTestId("activation-state")).toHaveTextContent("No qualified execution route");
  });
});

describe("agent actions", () => {
  it("saves one evaluation with a held key and shows the unknown outcome without success", async () => {
    mocks.actions.mockResolvedValue(actions({ jobs: [{ job_id: "j", agent_id: "agent-a", request_key: "k", decision_slot: "2026-10-12T01:05:00Z",
      state: "SUBMITTED", publication_revision_id: "r", execution_revision_id: "s:abc", consent_adoption_id: "m-1",
      decision_id: "d", action_id: "p23:d:ENTRY", outcome: "SUBMITTED_UNKNOWN", reason: "SUBMISSION_UNKNOWN", runs: 1,
      created_at: "t", updated_at: "t" }], blocking_reason: "SUBMISSION_UNKNOWN" }));
    mocks.action.mockResolvedValue(detail());
    render(<AgentActions agentId="agent-a" />);
    expect(await screen.findByTestId("actions-blocking")).toHaveTextContent("SUBMISSION_UNKNOWN");
    expect(screen.getByTestId("actions-jobs")).toHaveTextContent("Reconcile it before anything new runs");
    await userEvent.click(screen.getByRole("button", { name: /Open action/ }));
    const lineage = await screen.findByTestId("action-lineage");
    expect(within(lineage).getByTestId("action-receipts")).toHaveTextContent("SUBMISSION_UNKNOWN");
    expect(lineage).not.toHaveTextContent("CONFIRMED");
    expect(lineage).toHaveTextContent("FIXTURE_TRANSPORT_SIGNS_NOTHING");
    mocks.reconcileAction.mockResolvedValue({ receipt_outcome: "CONFIRMED", case_state: "CONFIRMED", decision_status: "CONFIRMED" });
    mocks.action.mockResolvedValue(detail({ queue: { ...detail().queue!, state: "SUBMITTED_CONFIRMED", blocking_reason: null },
      receipts: [...detail().receipts, { outcome: "CONFIRMED", breach: false, created_at: "t", content: {} }] }));
    await userEvent.click(screen.getByRole("button", { name: "Reconcile original action" }));
    await waitFor(() => expect(screen.getByTestId("action-receipts")).toHaveTextContent("SUBMISSION_UNKNOWN → CONFIRMED"));
    expect(mocks.schedule).not.toHaveBeenCalled();
  });

  it("offers stop and removal without liquidation or withdrawal and keeps the position visible", async () => {
    mocks.actions.mockResolvedValue(actions({ positions: [{ position_id: "agent-a:s:abc", asset_id: BASE.asset_id, decimals: 18,
      inventory_raw: "50000000000000000000", quote_asset_id: QUOTE.asset_id }] }));
    mocks.stop.mockResolvedValue({});
    mocks.requestRemoval.mockResolvedValue({});
    render(<AgentActions agentId="agent-a" />);
    expect(await screen.findByTestId("actions-positions")).toHaveTextContent("50 base units held");
    expect(screen.queryByRole("button", { name: /sell|liquidat|withdraw/i })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Halt all swaps" }));
    expect(mocks.stop).toHaveBeenCalledWith("agent-a", "HALT_ALL_SWAPS");
    mocks.removals.mockResolvedValue({ removals: [{ request_id: "x", state: "REQUESTED", reason: "OWNER_REQUESTED",
      requested_at: "t", updated_at: "t", evidenced_signer: null }] });
    await userEvent.click(await screen.findByRole("button", { name: "Request removal" }));
    expect(await screen.findByTestId("actions-removal")).toHaveTextContent("Removal REQUESTED");
    expect(screen.getByTestId("actions-positions")).toHaveTextContent("50 base units held");
  });

  it("pauses new requests after a lost reply until the saved actions are read", async () => {
    mocks.actions.mockResolvedValue(actions());
    mocks.schedule.mockRejectedValueOnce(new ApiError(0, "timeout", "late"));
    render(<AgentActions agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "Run one bounded evaluation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not confirmed");
    expect(screen.getByRole("button", { name: "Run one bounded evaluation" })).toBeDisabled();
    const key = mocks.schedule.mock.calls[0][1];
    await userEvent.click(screen.getByRole("button", { name: "Check saved actions" }));
    mocks.schedule.mockResolvedValueOnce({});
    await waitFor(() => expect(screen.getByRole("button", { name: "Run one bounded evaluation" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Run one bounded evaluation" }));
    await waitFor(() => expect(mocks.schedule).toHaveBeenCalledTimes(2));
    expect(mocks.schedule.mock.calls[1][1]).toBe(key);
  });
});

describe("deposit reference recovery", () => {
  it("releases a held reference once the saved flows show it, so a new deposit gets a fresh reference", async () => {
    window.sessionStorage.clear();
    mocks.funding.mockResolvedValueOnce(funding());
    mocks.prepareDeposit.mockRejectedValueOnce(new ApiError(0, "network_error", "unreachable"));
    render(<AgentFunding agentId="agent-r" />);
    await userEvent.type(await screen.findByLabelText(/Amount in base units/), "5");
    await userEvent.click(screen.getByRole("button", { name: "Save reviewed deposit" }));
    await screen.findByRole("button", { name: "Check saved funding" });
    const saved = mocks.prepareDeposit.mock.calls[0][1].reference;
    mocks.funding.mockResolvedValue(funding({ flows: [{ flow_id: "f", agent_id: "agent-r", wallet_id: "w", network_id: 10143,
      kind: "DEPOSIT", asset: { ...QUOTE, raw: "5" }, transport: "t", recipient: null, state: "PENDING", reference: saved,
      transaction_reference: null, reason: null, created_at: "t", updated_at: "t" }] }));
    await userEvent.click(screen.getByRole("button", { name: "Check saved funding" }));
    await waitFor(() => expect(screen.getByTestId("funding-flows")).toHaveTextContent(saved));
    mocks.prepareDeposit.mockResolvedValueOnce({});
    await userEvent.type(screen.getByLabelText(/Amount in base units/), "7");
    await userEvent.click(screen.getByRole("button", { name: "Save reviewed deposit" }));
    await waitFor(() => expect(mocks.prepareDeposit).toHaveBeenCalledTimes(2));
    expect(mocks.prepareDeposit.mock.calls[1][1].reference).not.toBe(saved);
  });
});

describe("committed change with a failed read-back (F2)", () => {
  it("actions: no success notice and every write blocked until a read succeeds", async () => {
    mocks.actions.mockResolvedValueOnce(actions()).mockRejectedValueOnce(new ApiError(503, "service_unavailable", "down"))
      .mockResolvedValue(actions());
    mocks.schedule.mockResolvedValueOnce({ job_id: "j" });
    render(<AgentActions agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "Run one bounded evaluation" }));
    expect(await screen.findByText(/was saved, but the current actions could not be read/)).toBeInTheDocument();
    expect(screen.queryByText(/Evaluation saved/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Run one bounded evaluation" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Halt all swaps" })).toBeDisabled();
    expect(mocks.schedule).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Check saved actions" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Run one bounded evaluation" })).toBeEnabled());
    expect(mocks.schedule).toHaveBeenCalledTimes(1); // nothing was repeated automatically
  });

  it("funding: a saved deposit whose read-back fails keeps changes paused", async () => {
    mocks.funding.mockResolvedValueOnce(funding()).mockRejectedValueOnce(new ApiError(503, "service_unavailable", "down"))
      .mockResolvedValue(funding());
    mocks.reconcileDeposits.mockResolvedValueOnce({});
    render(<AgentFunding agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "Check deposits" }));
    expect(await screen.findByText(/was saved, but the current funding could not be read/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check deposits" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Check saved funding" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Check deposits" })).toBeEnabled());
    expect(mocks.reconcileDeposits).toHaveBeenCalledTimes(1);
  });

  it("authority: a saved review whose read-back fails keeps adoption paused", async () => {
    mocks.consent.mockResolvedValueOnce(consent()).mockRejectedValueOnce(new ApiError(503, "service_unavailable", "down"))
      .mockResolvedValue(consent());
    mocks.review.mockResolvedValueOnce({ review_id: "r-2", review_hash: "sha256:" + "b".repeat(64), status: "INACTIVE",
      content: { terms: { terms_version: "connected-spot/1", operating_purpose: "TRIAL", trial_objective: "x",
        allocation: [{ ...QUOTE, raw: "500000000" }], allowances: [{ name: "quote_input", amount: { ...QUOTE, raw: "500000000" } }],
        attempt_budget: 5, gas_budget: { ...GAS, raw: "1" }, expiry: "2030-01-01T00:00:00Z", supported_actions: ["ENTRY", "EXIT"],
        supported_assets: [], supported_routes: [], route: { adapter: "KURU_FLOW_FIXED_INPUT" },
        evidence: { status: "HYPOTHESIS", source: "s" }, stop_effects: ["stop"] } } });
    render(<AgentAuthority agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: /Review exact terms/ }));
    expect(await screen.findByText(/was saved, but the current consent could not be read/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adopt these exact terms (inactive)" })).toBeDisabled();
    expect(mocks.adopt).not.toHaveBeenCalled();
  });
});

describe("original transaction and observed holdings (ORIGINAL-LOCAL)", () => {
  const ORIGINAL = { stage: "BROADCAST_RETURNED", reason: "BROADCAST_RETURNED", evidence_class: "AUTHORED_RECORDING",
    chain_id: 143, wallet_address: "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23", candidate_hash: "sha256:" + "a".repeat(64),
    transaction_hash: "0x7067b4c886f172b32b1c2839bcd70a45186817e3ade5648bb34fc0d6ea7aa28d", nonce: 0,
    fee_envelope: { gas_limit: 300000, max_fee_per_gas: 3000000000, max_priority_fee_per_gas: 1000000000 },
    signing_request_id: "attempt-1", signed_bytes_sha256: "sha256:" + "b".repeat(64), signed_bytes_length: 300,
    broadcast_returned: "0x7067b4c886f172b32b1c2839bcd70a45186817e3ade5648bb34fc0d6ea7aa28d",
    stages: [{ stage: "PREPARED", at: "t" }, { stage: "BROADCAST_RETURNED", at: "t" }] };

  it("shows the saved original identities and an unknown effect, never a success or a live claim", async () => {
    mocks.actions.mockResolvedValue(actions({ jobs: [{ job_id: "j", agent_id: "agent-a", request_key: "k",
      decision_slot: "2026-10-12T01:05:00Z", state: "SUBMITTED", publication_revision_id: "r", execution_revision_id: "s:abc",
      consent_adoption_id: "m-1", decision_id: "d", action_id: "p23:d:ENTRY", outcome: "SUBMITTED_UNKNOWN",
      reason: "BROADCAST_RETURNED", runs: 1, created_at: "t", updated_at: "t" }], blocking_reason: "SUBMISSION_UNKNOWN" }));
    const base = detail();
    mocks.action.mockResolvedValue(detail({ attempts: [{ ...base.attempts[0],
      content: { original_references: base.attempts[0].content.original_references, original_transaction: ORIGINAL } }] }));
    render(<AgentActions agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: /Open action/ }));
    const original = await screen.findByTestId("action-original");
    expect(within(original).getByTestId("action-original-hash")).toHaveTextContent(ORIGINAL.transaction_hash);
    expect(within(original).getByTestId("action-original-stage")).toHaveTextContent("Its effect is unknown until its own receipt is reconciled");
    expect(original).toHaveTextContent("not a live provider or chain");
    expect(original).not.toHaveTextContent("CONFIRMED");
    expect(screen.getByRole("button", { name: "Reconcile original action" })).toBeEnabled();
  });

  it("says an explicit signer refusal signed and sent nothing, and an unusable reply keeps the amounts held", async () => {
    mocks.actions.mockResolvedValue(actions({ jobs: [{ job_id: "j", agent_id: "agent-a", request_key: "k",
      decision_slot: "2026-10-12T01:05:00Z", state: "COMPLETED", publication_revision_id: "r", execution_revision_id: "s:abc",
      consent_adoption_id: "m-1", decision_id: "d", action_id: "p23:d:ENTRY", outcome: "DENIED_UNSENT",
      reason: "SIGNER_REFUSED", runs: 1, created_at: "t", updated_at: "t" }] }));
    const base = detail();
    const refused = { ...ORIGINAL, stage: "REFUSED_UNSENT", reason: "SIGNER_REFUSED", transaction_hash: undefined };
    mocks.action.mockResolvedValue(detail({ attempts: [{ ...base.attempts[0], content: { original_transaction: refused } }] }));
    const { unmount } = render(<AgentActions agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: /Open action/ }));
    expect(await screen.findByTestId("action-original-stage")).toHaveTextContent("The signer refused. Nothing was signed or sent.");
    unmount();
    const unusable = { ...ORIGINAL, stage: "SIGNED_RESPONSE_REJECTED", reason: "SIGNED_RESPONSE_REJECTED",
      reasons: ["SIGNER_REPLY_UNRECOGNIZED"], transaction_hash: undefined };
    mocks.action.mockResolvedValue(detail({ attempts: [{ ...base.attempts[0], content: { original_transaction: unusable } }] }));
    render(<AgentActions agentId="agent-a" />);
    await userEvent.click(await screen.findByRole("button", { name: /Open action/ }));
    expect(await screen.findByTestId("action-original-stage")).toHaveTextContent("Nothing was sent; the reserved amounts stay held.");
    expect(screen.getByTestId("action-original-hash")).toHaveTextContent("None saved");
  });

  it("shows the observation identity of current holdings and names a stale observation as unavailable", async () => {
    mocks.funding.mockResolvedValue(funding({ current_holdings: { state: "OBSERVED", evidence_class: "AUTHORED_RECORDING",
      assets: [{ ...QUOTE, raw: "1000000000" }], source: "recorded-holdings/1", finality: "FINALIZED",
      observed_at: "2026-10-12T16:00:00+00:00", wallet_address: "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23",
      chain_id: 143, block_number: 2000000, missing: [] } }));
    const { unmount } = render(<AgentFunding agentId="agent-a" />);
    expect(await screen.findByTestId("funding-holdings-observation")).toHaveTextContent(
      "Observed 2026-10-12T16:00:00+00:00 at block 2000000 (FINALIZED) for 0x2c7536E3605D9C16a7a3D7b1898e529396a65c23 · recorded-holdings/1");
    unmount();
    mocks.funding.mockResolvedValue(funding({ current_holdings: { state: "UNAVAILABLE", reason: "HOLDINGS_STALE",
      evidence_class: "AUTHORED_RECORDING", assets: [] } }));
    render(<AgentFunding agentId="agent-a" />);
    expect(await screen.findByTestId("funding-holdings")).toHaveTextContent(
      "Current holdings are unavailable (HOLDINGS_STALE). No balance is shown or assumed.");
  });
});
