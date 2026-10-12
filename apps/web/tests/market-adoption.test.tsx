import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MarketAdoption } from "../components/MarketAdoption";

const mocks = vi.hoisted(() => ({
  datasets: vi.fn(), adopt: vi.fn(),
  ApiError: class extends Error {
    constructor(public status: number, public code: string, public detail: string) { super(code); }
  },
}));
vi.mock("../lib/api", () => ({
  ApiError: mocks.ApiError,
  api: {
    historyDatasets: (...args: unknown[]) => mocks.datasets(...args),
    adoptMarket: (...args: unknown[]) => mocks.adopt(...args),
  },
}));

const QUOTE = "QUOTE:0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const qualified = {
  dataset_id: "d0000000-0000-4000-8000-000000000001", created_at: "2026-10-12T00:00:00Z", content_sha256: "a".repeat(64),
  hashes_verified: { content_sha256: true, raw_evidence_sha256: true }, quote_unit: QUOTE,
  source_id: "recorded-syn-qualified/1", evidence_class: "RECORDED_RESPONSE", content_label: "SYNTHETIC_FIXTURE",
  profile_evidence_class: "SYNTHETIC_FIXTURE", status: "COMPLETE", verdict: { overall: "QUALIFIED" },
  binding_state: "QUALIFIED_BINDING", unavailable_states: [], market_binding_id: "b".repeat(64),
  market_binding: { chain_id: 999001, pool_address: "0xaaaa", base_asset: "0xcccc", quote_asset: "0xbbbb",
    base_decimals: 18, quote_decimals: 6, orientation: "QUOTE_PER_BASE", event_schema_version: "uniswap-v2-swap/1",
    amount_conversion_version: "v2/1", data_route: "ENVIO_QUICKNODE_CORROBORATED", evidence_class: "SYNTHETIC_FIXTURE",
    qualification: "UNQUALIFIED" },
  window_start: "2026-09-25T10:00:00Z", window_end: "2026-09-25T12:00:00Z", declaration_id: "decl-1", job_id: "job-1",
  declared_rules: [{ evaluation_id: "e0000000-0000-4000-8000-000000000001", variant_id: "rule-1",
    price_expression: { op: "gt", args: [{ op: "price_return", lookback_buckets: 1 }, { op: "constant", value: "0", unit: "DIMENSIONLESS" }] },
    volume_expression: { op: "gt", args: [{ op: "quote_volume" }, { op: "constant", value: "100", unit: QUOTE }] } }],
};
const limited = { ...qualified, dataset_id: "d0000000-0000-4000-8000-000000000002", verdict: { overall: "LIMITED" },
  binding_state: "UNAVAILABLE_LIMITED_DATA", unavailable_states: ["PARTIAL_COVERAGE"], market_binding: null, quote_unit: null,
  source_id: "recorded-syn-provider-failure/1" };

function renderAdoption(reload = vi.fn(async (): Promise<string | null> => "draft-new")) {
  render(<MarketAdoption intakeId="intake-1" interpretationRevisionId="rev-1" parentRevisionId="revision-1"
    currentQuoteUnit="QUOTE:0x2222222222222222222222222222222222222222" reload={reload} />);
  return reload;
}

async function review(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(await screen.findByLabelText("Saved dataset"), qualified.dataset_id);
  await user.type(screen.getByLabelText("Trade size in the new quote unit"), "50");
  await user.type(screen.getByLabelText("Largest position value in the new quote unit"), "50");
  await user.selectOptions(screen.getByLabelText("Entry rule (one you declared for this dataset)"), "e0000000-0000-4000-8000-000000000001");
  await user.type(screen.getByLabelText("Exit lookback (buckets)"), "2");
  await user.type(screen.getByLabelText("Exit threshold (fraction, for example -0.001)"), "-0.001");
  await user.click(screen.getByRole("checkbox"));
}

beforeEach(() => {
  mocks.datasets.mockReset().mockResolvedValue({ datasets: [qualified, limited] });
  mocks.adopt.mockReset();
});

describe("recorded market adoption", () => {
  it("shows the exact market and keeps unqualified datasets out of the choices", async () => {
    const user = userEvent.setup();
    renderAdoption();
    await user.selectOptions(await screen.findByLabelText("Saved dataset"), qualified.dataset_id);
    expect(screen.getByTestId("market-adoption-review")).toHaveTextContent("0xaaaa");
    expect(screen.getByTestId("market-adoption-review")).toHaveTextContent(QUOTE);
    expect(screen.getByTestId("market-adoption-review")).toHaveTextContent("route qualification UNQUALIFIED");
    expect(screen.queryByRole("option", { name: /provider-failure/ })).toBeNull();
    expect(screen.getByText(/cannot supply a market/)).toBeInTheDocument();
  });

  it("never carries the old amount: both amounts start empty and adoption stays disabled", async () => {
    const user = userEvent.setup();
    renderAdoption();
    await user.selectOptions(await screen.findByLabelText("Saved dataset"), qualified.dataset_id);
    expect(screen.getByLabelText("Trade size in the new quote unit")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Adopt this market for a new draft" })).toBeDisabled();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    await user.type(screen.getByLabelText("Trade size in the new quote unit"), "50");
    await user.type(screen.getByLabelText("Largest position value in the new quote unit"), "50");
    expect(screen.getByRole("checkbox")).toBeDisabled(); // still needs a declared entry rule and an own exit rule
  });

  it("adopts with the exact confirmed body and shows success only after the read-back shows the new draft", async () => {
    const user = userEvent.setup();
    mocks.adopt.mockResolvedValue({ adoption: { draft_id: "draft-new" }, replayed: false, bundle: {} });
    const reload = renderAdoption();
    await review(user);
    await user.click(screen.getByRole("button", { name: "Adopt this market for a new draft" }));
    expect(await screen.findByText(/New draft draft-new uses the recorded market/)).toBeInTheDocument();
    const body = mocks.adopt.mock.calls[0][1];
    expect(body).toMatchObject({ expected_interpretation_revision_id: "rev-1", expected_parent_revision_id: "revision-1",
      dataset_id: qualified.dataset_id, adoption: "ADOPT_DATASET_MARKET", quote_unit: QUOTE, sizing_amount: "50",
      max_quote_notional: "50", evaluation_id: "e0000000-0000-4000-8000-000000000001",
      exit_rule: { op: "lt", args: [{ op: "price_return", lookback_buckets: 2 }, { op: "constant", value: "-0.001", unit: "DIMENSIONLESS" }] } });
    expect(Object.keys(body).sort()).toEqual(["adoption", "dataset_id", "evaluation_id", "exit_rule",
      "expected_interpretation_revision_id", "expected_parent_revision_id", "idempotency_key", "max_quote_notional",
      "quote_unit", "sizing_amount"]);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("does not claim success when the read-back fails", async () => {
    const user = userEvent.setup();
    mocks.adopt.mockResolvedValue({ adoption: { draft_id: "draft-new" }, replayed: false, bundle: {} });
    renderAdoption(vi.fn(async (): Promise<string | null> => null));
    await review(user);
    await user.click(screen.getByRole("button", { name: "Adopt this market for a new draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be read back");
    expect(screen.queryByText(/uses the recorded market/)).toBeNull();
  });

  it("retries an uncertain adoption with the same request and key", async () => {
    const user = userEvent.setup();
    mocks.adopt.mockRejectedValueOnce(new mocks.ApiError(0, "network_error", "unreachable"))
      .mockResolvedValueOnce({ adoption: { draft_id: "draft-new" }, replayed: true, bundle: {} });
    renderAdoption();
    await review(user);
    await user.click(screen.getByRole("button", { name: "Adopt this market for a new draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("same request and key");
    await user.click(screen.getByRole("button", { name: "Retry the same adoption" }));
    await screen.findByText(/uses the recorded market/);
    expect(mocks.adopt.mock.calls[1][1]).toEqual(mocks.adopt.mock.calls[0][1]);
  });

  it("shows a refusal and reloads on a stale revision", async () => {
    const user = userEvent.setup();
    mocks.adopt.mockRejectedValue(new mocks.ApiError(409, "parent_revision_conflict", "The request changed."));
    const reload = renderAdoption();
    await review(user);
    await user.click(screen.getByRole("button", { name: "Adopt this market for a new draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The request changed.");
    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Retry the same adoption" })).toBeNull();
  });

  it("explains when no qualified dataset exists", async () => {
    mocks.datasets.mockResolvedValue({ datasets: [limited] });
    renderAdoption();
    expect(await screen.findByText(/No qualified recorded dataset is saved/)).toBeInTheDocument();
  });
});
