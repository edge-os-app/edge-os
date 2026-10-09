import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { SpotReplayPanel } from "../components/SpotReplayPanel";
import type { SpotReplayRecord } from "../lib/types";

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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.create.mockResolvedValue(replay);
  mocks.get.mockResolvedValue(replay);
});

describe("P13 spot replay", () => {
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
});
