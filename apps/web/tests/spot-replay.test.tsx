import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { ReplayResult } from "../components/ReplayResult";
import { SpotReplayPanel } from "../components/SpotReplayPanel";
import type { SpotReplayRecord, SpotReplayDependency } from "../lib/types";

const mocks = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error {
    constructor(public status: number, public code: string, public detail: string) { super(detail); }
  },
  api: {
    createSpotReplay: (...args: unknown[]) => mocks.create(...args),
    spotReplay: (...args: unknown[]) => mocks.get(...args),
  },
}));

const replay = {
  schema_version: "p13.spot-replay-run/1", record_type: "SpotReplayRun",
  replay_id: "11111111-1111-4111-8111-111111111111", created_at: "2026-10-01T12:30:00Z",
  content_sha256: "a".repeat(64),
  content: {
    inputs: {
      profile_version: "p12.spot-replay/1", strategy_revision_id: "saved-revision-9", strategy_id: "strategy-1",
      strategy_sha256: "c".repeat(64), run_configuration_id: "saved-config-9", dataset_fixture_id: "p13.wc01/1",
      dataset_revision_id: "saved-dataset-9", dataset_qualification: "QUALIFIED", evidence_class: "SYNTHETIC_FIXTURE",
      window_start: "2026-10-01T12:05:00Z", window_end: "2026-10-01T12:25:00Z",
      initial_cash_quote: "1250", initial_base_amount: "0", initial_basis_quote: "0", fixture_limitation: "synthetic only",
      strategy: { sizing: { amount: "250", unit: "QUOTE:WMON" }, warmup_buckets: 3,
        cost_assumptions: { fee_rate: "0.002", slippage_rate: "0.001", source_ref: "saved-cost-source-9" } },
      essential_evidence: { fields: {
        entry: { state: "BOUND", essential_dependencies: [{ series: "price", offset_buckets: 0 }, { series: "price", offset_buckets: -3 }] },
        exit: { state: "BOUND", essential_dependencies: [{ series: "price", offset_buckets: 0 }, { series: "price", offset_buckets: -1 }] },
      } },
    },
    result: { status: "COMPLETE", evidence_class: "SYNTHETIC_FIXTURE", repeatability_id: "b".repeat(64),
      samples: [{ at: "2026-10-01T12:20:00Z", cash_quote: "1000", base_amount: "0", account_value_quote: "1000" }],
      events: [], trades: [], metrics: { gain_loss_quote: "0", completed_trade_pairs: 0, largest_drawdown_quote: "0" },
      metric_statuses: { gain_loss_quote: "AVAILABLE", completed_trade_pairs: "AVAILABLE", largest_drawdown_quote: "AVAILABLE" },
      metric_reasons: {}, open_position: null },
    notice: "Synthetic replay only. Assumed fills. No trading permission is granted.",
  },
} as unknown as SpotReplayRecord;

type SavedBinding = { state: "BOUND" | "UNBOUND"; essential_dependencies?: SpotReplayDependency[] | null };

function recordWithSavedBinding(field: "entry" | "exit", binding: SavedBinding): SpotReplayRecord {
  const saved = JSON.parse(JSON.stringify(replay)) as any;
  saved.replay_id = field === "entry" ? "33333333-3333-4333-8333-333333333333" : "44444444-4444-4444-8444-444444444444";
  saved.content.inputs.essential_evidence.fields[field] = binding;
  saved.content.result.status = "UNAVAILABLE";
  saved.content.result.reason = binding.state === "UNBOUND"
    ? { code: "UNRESOLVED_ESSENTIAL_EVIDENCE", path: `/essential_evidence/fields/${field}`, detail: "Bind entry and exit separately." }
    : { code: "INVALID_ESSENTIAL_BINDING", path: `/essential_evidence/fields/${field}/essential_dependencies`, detail: "Use a dependency list." };
  return saved as SpotReplayRecord;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.create.mockResolvedValue(replay);
  mocks.get.mockResolvedValue(replay);
});

describe("P13 spot replay", () => {
  it("leads a saved result with quote metrics and an accessible balance chart that preserves unavailable gaps", () => {
    const saved = JSON.parse(JSON.stringify(replay)) as any;
    saved.content.result.samples = [
      { at: "2026-10-01T12:05:00Z", cash_quote: "1000", base_amount: "0", account_value_quote: "1000" },
      { at: "2026-10-01T12:10:00Z", cash_quote: "1100", base_amount: "0", account_value_quote: "1100" },
      { at: "2026-10-01T12:15:00Z", cash_quote: "1100", base_amount: "5", account_value_quote: null, mark_reasons: ["LATE_INPUT"] },
      { at: "2026-10-01T12:20:00Z", cash_quote: "950", base_amount: "0", account_value_quote: "950" },
      { at: "2026-10-01T12:25:00Z", cash_quote: "900", base_amount: "0", account_value_quote: "900" },
    ];
    saved.content.result.metrics = {
      gain_loss_quote: "-100", completed_trade_pairs: 1, largest_drawdown_quote: "200",
    };
    render(<ReplayResult replay={saved as SpotReplayRecord} />);

    expect(screen.getByRole("heading", { name: "Simulated replay summary" })).toBeInTheDocument();
    expect(screen.getByText("-100 quote")).toBeInTheDocument();
    expect(screen.getByText("1 completed trade pair")).toBeInTheDocument();
    expect(screen.getByText("200 quote")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /account balance in quote over the replay window/i })).toBeInTheDocument();
    const sampleList = screen.getByRole("list", { name: "Saved account value samples" });
    expect(within(sampleList).getByText("2026-10-01 12:15:00 UTC")).toBeInTheDocument();
    expect(within(sampleList).getByText("Unavailable")).toBeInTheDocument();
    expect(within(sampleList).getByText("LATE_INPUT")).toBeInTheDocument();
    const chart = screen.getByRole("img", { name: /account balance in quote over the replay window/i });
    expect(chart.querySelectorAll("polyline")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Simulated replay summary" }).compareDocumentPosition(screen.getByTestId("spot-replay-saved-inputs")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows single, flat, open-position and all-missing samples without inventing a balance", () => {
    const onePoint = JSON.parse(JSON.stringify(replay)) as any;
    onePoint.content.result.open_position = { base_amount: "2", basis_quote: "400", last_mark_quote: "500" };
    onePoint.content.result.samples = [
      { at: "2026-10-01T12:25:00Z", cash_quote: "900", base_amount: "2", account_value_quote: "1000.000000000000000001" },
    ];
    const { unmount } = render(<ReplayResult replay={onePoint as SpotReplayRecord} />);
    const firstChart = screen.getByRole("img", { name: /account balance in quote over the replay window/i });
    expect(firstChart.querySelectorAll("circle")).toHaveLength(1);
    expect(firstChart.querySelectorAll("polyline")).toHaveLength(0);
    expect(screen.getByText("1000.000000000000000001 quote")).toBeInTheDocument();

    unmount();
    const flat = JSON.parse(JSON.stringify(replay)) as any;
    flat.content.result.samples = [
      { at: "2026-10-01T12:20:00Z", cash_quote: "1000", base_amount: "0", account_value_quote: "1000.00" },
      { at: "2026-10-01T12:25:00Z", cash_quote: "1000", base_amount: "0", account_value_quote: "1000.00" },
    ];
    const flatView = render(<ReplayResult replay={flat as SpotReplayRecord} />);
    const flatChart = screen.getByRole("img", { name: /account balance in quote over the replay window/i });
    expect(flatChart.querySelectorAll("polyline")).toHaveLength(1);
    expect(screen.getAllByText("1000.00 quote")).toHaveLength(2);

    flatView.unmount();
    const unavailable = JSON.parse(JSON.stringify(replay)) as any;
    unavailable.content.result.status = "UNAVAILABLE";
    unavailable.content.result.reason = { code: "MARK_UNAVAILABLE", path: "/samples/0", detail: "The saved quote mark is late." };
    unavailable.content.result.samples = [
      { at: "2026-10-01T12:20:00Z", cash_quote: "900", base_amount: "2", account_value_quote: null, mark_reasons: ["LATE_INPUT"] },
    ];
    unavailable.content.result.metrics = { gain_loss_quote: null, completed_trade_pairs: null, largest_drawdown_quote: null };
    unavailable.content.result.metric_statuses = {
      gain_loss_quote: "UNAVAILABLE", completed_trade_pairs: "UNAVAILABLE", largest_drawdown_quote: "UNAVAILABLE",
    };
    render(<ReplayResult replay={unavailable as SpotReplayRecord} />);
    const missingChart = screen.getByRole("img", { name: /account balance in quote over the replay window/i });
    expect(missingChart.querySelectorAll("circle, polyline")).toHaveLength(0);
    expect(screen.getByText("No saved account-balance value is available to plot.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Saved account value samples" })).toHaveTextContent("LATE_INPUT");
  });

  it.each([
    ["entry", { state: "UNBOUND" }, "UNBOUND: dependency list not supplied", "UNRESOLVED_ESSENTIAL_EVIDENCE"],
    ["exit", { state: "UNBOUND", essential_dependencies: null }, "UNBOUND: dependency list is null", "UNRESOLVED_ESSENTIAL_EVIDENCE"],
    ["entry", { state: "BOUND" }, "BOUND: dependency list not supplied", "INVALID_ESSENTIAL_BINDING"],
    ["exit", { state: "BOUND" }, "BOUND: dependency list not supplied", "INVALID_ESSENTIAL_BINDING"],
    ["entry", { state: "BOUND", essential_dependencies: null }, "BOUND: dependency list is null", "INVALID_ESSENTIAL_BINDING"],
    ["exit", { state: "BOUND", essential_dependencies: null }, "BOUND: dependency list is null", "INVALID_ESSENTIAL_BINDING"],
  ] as const)("loads unavailable %s binding with its %s list state intact", async (field, binding, expectedText, reasonCode) => {
    const saved = recordWithSavedBinding(field, binding);
    const user = userEvent.setup();
    mocks.get.mockResolvedValueOnce(saved);
    expect(() => render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 3,
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />)).not.toThrow();

    await user.type(screen.getByRole("textbox", { name: "Saved replay ID" }), saved.replay_id);
    await user.click(screen.getByRole("button", { name: "Load saved replay" }));

    expect(await screen.findByRole("heading", { name: "Saved replay: unavailable" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(reasonCode);
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent(expectedText);
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it.each(["entry", "exit"] as const)("keeps an explicitly empty BOUND %s list distinct from an omitted list", async (field) => {
    const saved = JSON.parse(JSON.stringify(replay)) as any;
    saved.content.inputs.essential_evidence.fields[field] = { state: "BOUND", essential_dependencies: [] };
    const user = userEvent.setup();
    mocks.get.mockResolvedValueOnce(saved as SpotReplayRecord);
    render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 3,
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />);

    await user.type(screen.getByRole("textbox", { name: "Saved replay ID" }), saved.replay_id);
    await user.click(screen.getByRole("button", { name: "Load saved replay" }));

    expect(await screen.findByTestId("spot-replay-saved-inputs")).toHaveTextContent("BOUND: no additional dependencies");
  });

  it("saves an explicitly reviewed fixture run and can load its exact saved result", async () => {
    const user = userEvent.setup();
    render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 3,
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />);

    expect(screen.getByText(/authored synthetic fixture/)).toBeInTheDocument();
    expect(screen.getByText(/Fills are assumptions/)).toBeInTheDocument();
    expect(screen.getByText("1000. This fixed amount will be used for a new run.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add entry dependency" }));
    await user.click(screen.getByRole("button", { name: "Add exit dependency" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the entry dependency set" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the exit dependency set" }));
    await user.click(screen.getByRole("button", { name: "Save synthetic replay" }));

    expect(await screen.findByTestId("spot-replay-result")).toHaveTextContent("complete");
    expect(mocks.create).toHaveBeenCalledOnce();
    const body = mocks.create.mock.calls[0][0];
    expect(body.strategy_revision_id).toBe("22222222-2222-4222-8222-222222222222");
    expect(body.dataset_fixture_id).toBe("p13.wc01/1");
    expect(body.essential_fields.entry.essential_dependencies).toEqual([{ series: "price", offset_buckets: 0 }]);
    expect(body.essential_fields.exit.essential_dependencies).toEqual([{ series: "price", offset_buckets: 0 }]);

    await user.clear(screen.getByRole("textbox", { name: "Saved replay ID" }));
    await user.type(screen.getByRole("textbox", { name: "Saved replay ID" }), replay.replay_id);
    await user.click(screen.getByRole("button", { name: "Load saved replay" }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(replay.replay_id));
    expect(mocks.create).toHaveBeenCalledOnce();
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("saved-config-9");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("saved-revision-9");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("1250");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("2026-10-01 12:05:00 UTC to 2026-10-01 12:25:00 UTC");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("250");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("saved-cost-source-9");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("price@0, price@-3");
    expect(screen.getByTestId("spot-replay-saved-inputs")).toHaveTextContent("price@0, price@-1");
    expect(screen.getByText("New run settings (editable)")).toBeInTheDocument();
    expect(mocks.create).toHaveBeenCalledOnce();
  });

  it("releases a body only after a definitive 422 so corrected input starts a new attempt", async () => {
    const user = userEvent.setup();
    mocks.create.mockRejectedValueOnce(new ApiError(422, "INVALID_INPUT", "Correct the entry offset."));
    render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 3,
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />);
    await user.click(screen.getByRole("button", { name: "Add entry dependency" }));
    const offset = screen.getByRole("spinbutton", { name: "entry dependency offset 1" });
    await user.clear(offset); await user.type(offset, "1");
    await user.click(screen.getByRole("button", { name: "Add exit dependency" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the entry dependency set" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the exit dependency set" }));
    await user.click(screen.getByRole("button", { name: "Save synthetic replay" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Correct the entry offset.");
    expect(screen.getByRole("button", { name: "Save synthetic replay" })).toBeInTheDocument();
    await user.clear(offset); await user.type(offset, "0");
    await user.click(screen.getByRole("button", { name: "Save synthetic replay" }));
    await screen.findByTestId("spot-replay-result");
    expect(mocks.create).toHaveBeenCalledTimes(2);
    expect(mocks.create.mock.calls[0][0].essential_fields.entry.essential_dependencies[0].offset_buckets).toBe(1);
    expect(mocks.create.mock.calls[1][0].essential_fields.entry.essential_dependencies[0].offset_buckets).toBe(0);
    expect(mocks.create.mock.calls[1][0].idempotency_key).not.toBe(mocks.create.mock.calls[0][0].idempotency_key);
  });

  it("keeps the exact same key and body after an uncertain response even if fields change", async () => {
    const user = userEvent.setup();
    mocks.create.mockRejectedValueOnce(new ApiError(0, "network_error", "The service could not be reached."));
    render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 3,
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />);
    await user.click(screen.getByRole("button", { name: "Add entry dependency" }));
    const offset = screen.getByRole("spinbutton", { name: "entry dependency offset 1" });
    await user.click(screen.getByRole("button", { name: "Add exit dependency" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the entry dependency set" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the exit dependency set" }));
    await user.click(screen.getByRole("button", { name: "Save synthetic replay" }));
    expect(await screen.findByRole("button", { name: "Retry same replay" })).toBeInTheDocument();
    await user.clear(offset); await user.type(offset, "-2");
    await user.click(screen.getByRole("button", { name: "Retry same replay" }));
    await screen.findByTestId("spot-replay-result");
    expect(mocks.create).toHaveBeenCalledTimes(2);
    expect(mocks.create.mock.calls[1][0]).toEqual(mocks.create.mock.calls[0][0]);
  });

  it("keeps an uncertain attempt when loading an unrelated saved replay, then retries the original body", async () => {
    const user = userEvent.setup();
    const unrelated = { ...replay, replay_id: "55555555-5555-4555-8555-555555555555" };
    const committed = { ...replay, replay_id: "66666666-6666-4666-8666-666666666666" };
    mocks.create.mockRejectedValueOnce(new Error("The response was lost."));
    mocks.create.mockResolvedValueOnce(committed);
    mocks.get.mockResolvedValueOnce(unrelated);
    render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 3,
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />);
    await user.click(screen.getByRole("button", { name: "Add entry dependency" }));
    await user.click(screen.getByRole("button", { name: "Add exit dependency" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the entry dependency set" }));
    await user.click(screen.getByRole("checkbox", { name: "I reviewed the exit dependency set" }));
    await user.click(screen.getByRole("button", { name: "Save synthetic replay" }));
    expect(await screen.findByRole("button", { name: "Retry same replay" })).toBeInTheDocument();
    const uncertainBody = mocks.create.mock.calls[0][0];

    await user.type(screen.getByRole("textbox", { name: "Saved replay ID" }), unrelated.replay_id);
    await user.click(screen.getByRole("button", { name: "Load saved replay" }));
    expect(await screen.findByTestId("spot-replay-id")).toHaveTextContent(unrelated.replay_id);
    expect(screen.queryByRole("button", { name: "Retry same replay" })).toBeInTheDocument();
    expect(screen.getByText(/uncertain outcome/)).toBeInTheDocument();
    expect(screen.getByText("Loaded the exact saved result. The replay did not run again.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry same replay" }));
    await waitFor(() => expect(screen.getByTestId("spot-replay-id")).toHaveTextContent(committed.replay_id));
    expect(mocks.get).toHaveBeenCalledWith(unrelated.replay_id);
    expect(mocks.create).toHaveBeenCalledTimes(2);
    expect(mocks.create.mock.calls[1][0]).toEqual(uncertainBody);
  });
});
