import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SpotReplayPanel } from "../components/SpotReplayPanel";
import type { SpotReplayRecord } from "../lib/types";

const mocks = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { detail = "Unavailable"; },
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
    render(<SpotReplayPanel strategy={{ strategy_id: "strategy-1", data_inputs: ["price"],
      cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" } } as never}
      strategyId="strategy-1" strategyRevisionId="22222222-2222-4222-8222-222222222222" />);

    expect(screen.getByText(/authored synthetic fixture/)).toBeInTheDocument();
    expect(screen.getByText(/Fills are assumptions/)).toBeInTheDocument();
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
  });
});
