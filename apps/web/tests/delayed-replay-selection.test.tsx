// The explicit delayed-profile control and the labels of a saved delayed replay.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { ReplayResult } from "../components/ReplayResult";
import { SpotReplayPanel } from "../components/SpotReplayPanel";
import type { SpotReplayRecord } from "../lib/types";

const mocks = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn(), datasets: vi.fn() }));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error {
    constructor(public status: number, public code: string, public detail: string) { super(detail); }
  },
  api: {
    createSpotReplay: (...args: unknown[]) => mocks.create(...args),
    spotReplay: (...args: unknown[]) => mocks.get(...args),
    historyDatasets: (...args: unknown[]) => mocks.datasets(...args),
  },
}));

const DEFAULT = "p12.spot-replay/1";
const DELAYED = "edge-os.delayed-history-replay/1";
const DELAYED_LABEL = "Delayed hypothetical replay (300 s decision delay)";
const FILL_LABEL = "Hypothetical stale historical close";

const strategy = {
  strategy_id: "strategy-1", data_inputs: ["price"], sizing: { amount: "100", unit: "QUOTE:WMON" },
  warmup_buckets: 2, cost_assumptions: { source_ref: "saved-cost-profile", fee_rate: "0.001", slippage_rate: "0" },
} as never;

function delayedRecord(): SpotReplayRecord {
  return {
    schema_version: "p13.spot-replay-run/1", record_type: "SpotReplayRun",
    replay_id: "11111111-1111-4111-8111-111111111111", created_at: "2026-10-01T12:35:00Z",
    content_sha256: "a".repeat(64),
    content: {
      owner_id: "00000000-0000-4000-8000-000000000001",
      strategy_revision_id: "22222222-2222-4222-8222-222222222222", dataset_fixture_id: "p13.wc01/1",
      run_configuration_id: "delayed-config",
      inputs: {
        profile_version: DEFAULT, timing_profile: DELAYED,
        timing_policy: { schema_version: DELAYED, decision_delay_seconds: 300,
          fill_rule: "NEXT_BUCKET_DELAYED_CLOSE", fill_label: FILL_LABEL },
        strategy_revision_id: "22222222-2222-4222-8222-222222222222", strategy_id: "strategy-1",
        strategy_sha256: "c".repeat(64), run_configuration_id: "delayed-config", dataset_fixture_id: "p13.wc01/1",
        dataset_revision_id: "dataset-1", dataset_qualification: "QUALIFIED", evidence_class: "SYNTHETIC_FIXTURE",
        window_start: "2026-10-01T12:05:00Z", window_end: "2026-10-01T12:35:00Z",
        initial_cash_quote: "1000", initial_base_amount: "0", initial_basis_quote: "0",
        strategy: { sizing: { amount: "100", unit: "QUOTE:WMON" }, warmup_buckets: 2,
          cost_assumptions: { fee_rate: "0.001", slippage_rate: "0", source_ref: "saved-cost-profile" } },
        essential_evidence: { fields: {
          entry: { state: "BOUND", essential_dependencies: [] },
          exit: { state: "BOUND", essential_dependencies: [] },
        } },
      },
      result: {
        status: "COMPLETE", evidence_class: "SYNTHETIC_FIXTURE", repeatability_id: "b".repeat(64),
        samples: [{ at: "2026-10-01T12:05:00Z", cash_quote: "1000", base_amount: "0",
          account_value_quote: "1000", timing_profile: DELAYED }],
        events: [
          { kind: "ORDER", status: "BUY_FILLED", at: "2026-10-01T12:10:00Z", fill_label: FILL_LABEL,
            timing_profile: DELAYED },
          { kind: "ORDER", status: "FILL_UNAVAILABLE", at: "2026-10-01T12:15:00Z", fill_label: FILL_LABEL,
            timing_profile: DELAYED },
          { kind: "ORDER", status: "NO_NEXT_BUCKET", at: "2026-10-01T12:30:00Z", timing_profile: DELAYED },
        ],
        trades: [],
        metrics: { gain_loss_quote: "0", completed_trade_pairs: 0, largest_drawdown_quote: "0" },
        metric_statuses: { gain_loss_quote: "AVAILABLE", completed_trade_pairs: "AVAILABLE",
          largest_drawdown_quote: "AVAILABLE" },
        metric_reasons: {}, open_position: null,
      },
      notice: "Synthetic replay only. Assumed fills. No trading permission is granted.",
    },
  } as unknown as SpotReplayRecord;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.create.mockResolvedValue(delayedRecord());
  mocks.get.mockResolvedValue(delayedRecord());
  mocks.datasets.mockResolvedValue({ datasets: [] });
});

function panel() {
  return render(<SpotReplayPanel strategy={strategy} strategyId="strategy-1"
    strategyRevisionId="22222222-2222-4222-8222-222222222222" />);
}

async function reviewAndSave(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("checkbox", { name: "I reviewed the entry dependency set" }));
  await user.click(screen.getByRole("checkbox", { name: "I reviewed the exit dependency set" }));
  await user.click(screen.getByRole("button", { name: "Save synthetic replay" }));
}

describe("delayed replay selection", () => {
  it("selects the default profile and sends the delayed choice only when chosen", async () => {
    const user = userEvent.setup();
    panel();
    const control = screen.getByLabelText("Timing profile");
    expect(control).toHaveValue(DEFAULT);
    expect(control).toHaveClass("input");
    expect(screen.getByRole("option", { name: DELAYED_LABEL })).toBeInTheDocument();
    expect(screen.queryByTestId("spot-replay-delayed-note")).toBeNull();

    await user.selectOptions(control, DELAYED);

    expect(screen.getByTestId("spot-replay-delayed-note")).toBeInTheDocument();
    await reviewAndSave(user);

    await screen.findByTestId("spot-replay-result");
    expect(mocks.create.mock.calls[0][0].timing_profile).toBe(DELAYED);
  });

  it("keeps the default request free of a timing profile", async () => {
    const user = userEvent.setup();
    panel();
    await reviewAndSave(user);

    await screen.findByTestId("spot-replay-result");
    expect("timing_profile" in mocks.create.mock.calls[0][0]).toBe(false);
    expect(mocks.create.mock.calls[0][0].window_start).toBe("2026-10-01T12:05:00Z");
  });

  it("starts the fixture window one bucket later for the delayed profile", async () => {
    const user = userEvent.setup();
    panel();
    await user.selectOptions(screen.getByLabelText("Timing profile"), DELAYED);
    await reviewAndSave(user);

    await screen.findByTestId("spot-replay-result");
    expect(mocks.create.mock.calls[0][0].window_start).toBe("2026-10-01T12:10:00Z");
    expect(mocks.create.mock.calls[0][0].window_end).toBe("2026-10-01T12:35:00Z");
  });

  it("disables the profile control while a save is in flight", async () => {
    const user = userEvent.setup();
    let finish: (record: SpotReplayRecord) => void = () => {};
    mocks.create.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    panel();
    const control = screen.getByLabelText("Timing profile");
    await user.selectOptions(control, DELAYED);
    await reviewAndSave(user);

    expect(screen.getByRole("button", { name: "Saving replay…" })).toBeInTheDocument();
    expect(screen.getByLabelText("Timing profile")).toBeDisabled();
    finish(delayedRecord());
    await waitFor(() => expect(screen.getByLabelText("Timing profile")).not.toBeDisabled());
  });

  it("shows the API refusal and keeps the chosen profile and form", async () => {
    const user = userEvent.setup();
    mocks.create.mockRejectedValueOnce(new ApiError(422, "INVALID_INPUT", "Use a recognized replay timing profile."));
    panel();
    const control = screen.getByLabelText("Timing profile");
    await user.selectOptions(control, DELAYED);
    await reviewAndSave(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Use a recognized replay timing profile.");
    expect(screen.getByLabelText("Timing profile")).toHaveValue(DELAYED);
    expect(screen.getByRole("button", { name: "Save synthetic replay" })).toBeInTheDocument();
    expect(screen.queryByTestId("spot-replay-result")).toBeNull();
  });
});

describe("a saved delayed replay", () => {
  it("labels the delayed run, its profile and each hypothetical fill", () => {
    render(<ReplayResult replay={delayedRecord()} />);

    expect(screen.getByRole("heading", { name: "Saved replay: complete" })).toBeInTheDocument();
    expect(screen.getByText(DELAYED_LABEL)).toBeInTheDocument();
    expect(screen.getByTestId("spot-replay-timing-profile")).toHaveTextContent(DELAYED);
    const events = screen.getByTestId("spot-replay-order-events");
    expect(events).toHaveTextContent("FILL_UNAVAILABLE");
    expect(events).toHaveTextContent("NO_NEXT_BUCKET");
    expect(events).toHaveTextContent(FILL_LABEL);
    expect(events).toHaveTextContent(/not a failed replay/i);
    expect(screen.getByText("SYNTHETIC_FIXTURE. This is an authored fixture, not observed market history."))
      .toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(/executable|\blive\b|real fill/i);
  });

  it("keeps a default saved replay free of the delayed label", () => {
    const saved = delayedRecord();
    const inputs = saved.content.inputs as unknown as Record<string, unknown>;
    delete inputs.timing_profile;
    delete inputs.timing_policy;
    saved.content.result.events = [];
    saved.content.result.trades = [];

    render(<ReplayResult replay={saved} />);

    expect(screen.queryByText(DELAYED_LABEL)).toBeNull();
    expect(screen.getByTestId("spot-replay-timing-profile")).toHaveTextContent(DEFAULT);
    expect(screen.queryByTestId("spot-replay-order-events")).toBeNull();
  });
});
