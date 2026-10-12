import type { SpotReplayRecord } from "../lib/types";
import { ReplayBalanceChart } from "./ReplayBalanceChart";

interface Props { replay: SpotReplayRecord }

function displayUtc(value: string): string {
  const normalized = new Date(value);
  if (Number.isNaN(normalized.valueOf())) return value;
  const iso = normalized.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)} UTC`;
}

export function ReplayResult({ replay }: Props) {
  const result = replay.content.result;
  const inputs = replay.content.inputs;
  const history = (inputs as { history_input?: { dataset_id: string; source_id: string; content_label: string;
    declaration_id: string; job_id: string; dataset_market_binding_id: string | null; strategy_market_binding_id: string;
    fill_label: string; dataset_content_sha256: string } }).history_input ?? null;
  const dependencies = (field: "entry" | "exit") => inputs.essential_evidence.fields[field];
  const bindingSummary = (field: "entry" | "exit") => {
    const binding = dependencies(field);
    if (binding.essential_dependencies === undefined) return `${binding.state}: dependency list not supplied`;
    if (binding.essential_dependencies === null) return `${binding.state}: dependency list is null`;
    return `${binding.state}: ${binding.essential_dependencies.map(({ series, offset_buckets }) => `${series}@${offset_buckets}`).join(", ") || "no additional dependencies"}`;
  };
  const summaryMetric = (name: "gain_loss_quote" | "completed_trade_pairs" | "largest_drawdown_quote", unit: string) => {
    const value = result.metrics[name];
    const status = result.metric_statuses[name] ?? "UNAVAILABLE";
    const reasons = result.metric_reasons[name] ?? [];
    if (status !== "AVAILABLE" || value === null || value === undefined) {
      return `Unavailable${reasons.length ? `: ${reasons.join(", ")}` : ""}`;
    }
    const resolvedUnit = name === "completed_trade_pairs"
      ? Number(value) === 1 ? "completed trade pair" : "completed trade pairs"
      : unit;
    return `${String(value)}${resolvedUnit ? ` ${resolvedUnit}` : ""}`;
  };
  return (
    <section className={`status ${result.status === "COMPLETE" ? "ok" : "stop"}`} data-testid="spot-replay-result"
      aria-labelledby="spot-replay-result-title">
      <h3 id="spot-replay-result-title">Saved replay: {result.status === "COMPLETE" ? "complete" : "unavailable"}</h3>
      {result.reason ? <p role="alert">{result.reason.code} at {result.reason.path}: {result.reason.detail}</p> : null}
      <section className="spot-replay-summary" aria-labelledby="spot-replay-summary-title">
        <h4 id="spot-replay-summary-title">Simulated replay summary</h4>
        <dl className="kv">
          <dt>Simulated gain/loss</dt><dd>{summaryMetric("gain_loss_quote", "quote")}</dd>
          <dt>Completed trade pairs</dt><dd>{summaryMetric("completed_trade_pairs", "completed trade pairs")}</dd>
          <dt>Largest drawdown</dt><dd>{summaryMetric("largest_drawdown_quote", "quote")}</dd>
        </dl>
      </section>
      <ReplayBalanceChart samples={result.samples} />
      <dl className="kv">
        <dt>Replay ID</dt><dd className="mono" data-testid="spot-replay-id">{replay.replay_id}</dd>
        <dt>Saved hash</dt><dd className="mono">{replay.content_sha256}</dd>
        <dt>Evidence</dt><dd>{history
          ? `${result.evidence_class}. Simulated fills on saved recorded-history dataset ${history.dataset_id} (${history.source_id}, ${history.content_label}). Not observed market history.`
          : `${result.evidence_class}. This is an authored fixture, not observed market history.`}</dd>
        <dt>Repeatability</dt><dd className="mono">{result.repeatability_id ?? "Unavailable before replay"}</dd>
      </dl>
      {history ? (
        <section aria-labelledby="spot-replay-lineage-title" data-testid="spot-replay-history-lineage"
          style={{ overflowWrap: "anywhere" }}>
          <h4 id="spot-replay-lineage-title">Recorded-history lineage ({history.fill_label})</h4>
          <dl className="kv">
            <dt>Dataset</dt><dd className="mono">{history.dataset_id}</dd>
            <dt>Dataset hash</dt><dd className="mono">{history.dataset_content_sha256}</dd>
            <dt>Declaration</dt><dd className="mono">{history.declaration_id}</dd>
            <dt>Investigation job</dt><dd className="mono">{history.job_id}</dd>
            <dt>Dataset market</dt><dd className="mono">{history.dataset_market_binding_id ?? "Unavailable: dataset not qualified"}</dd>
            <dt>Revision market</dt><dd className="mono">{history.strategy_market_binding_id}</dd>
          </dl>
        </section>
      ) : null}
      <section aria-labelledby="spot-replay-saved-inputs-title" data-testid="spot-replay-saved-inputs">
        <h4 id="spot-replay-saved-inputs-title">Exact saved run settings</h4>
        <dl className="kv">
          <dt>Profile</dt><dd>{inputs.profile_version}</dd>
          <dt>Strategy revision</dt><dd className="mono">{inputs.strategy_revision_id}</dd>
          <dt>Run configuration</dt><dd className="mono">{inputs.run_configuration_id}</dd>
          <dt>Fixture and dataset</dt><dd>{inputs.dataset_fixture_id} · {inputs.dataset_revision_id}</dd>
          <dt>Evidence</dt><dd>{inputs.evidence_class} · {inputs.dataset_qualification}</dd>
          <dt>Window</dt><dd>{displayUtc(inputs.window_start)} to {displayUtc(inputs.window_end)}</dd>
          <dt>Starting balances</dt><dd>{inputs.initial_cash_quote} quote cash · {inputs.initial_base_amount} base · {inputs.initial_basis_quote} quote basis</dd>
          <dt>Trade size</dt><dd>{inputs.strategy.sizing.amount} {inputs.strategy.sizing.unit}</dd>
          <dt>Warm-up</dt><dd>{inputs.strategy.warmup_buckets} scheduled buckets</dd>
          <dt>Saved costs</dt><dd>{inputs.strategy.cost_assumptions.source_ref} · fee {inputs.strategy.cost_assumptions.fee_rate} · slippage {inputs.strategy.cost_assumptions.slippage_rate}</dd>
          <dt>Entry binding</dt><dd>{bindingSummary("entry")}</dd>
          <dt>Exit binding</dt><dd>{bindingSummary("exit")}</dd>
        </dl>
      </section>
      <div className="table-scroll">
        <table className="records" aria-label="Quote-denominated replay metrics">
          <thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">Status and reasons</th></tr></thead>
          <tbody>{Object.entries(result.metric_statuses).map(([name, status]) => (
            <tr key={name}>
              <th scope="row">{name.replaceAll("_", " ")}</th>
              <td>{result.metrics[name] === null || result.metrics[name] === undefined ? "Unavailable" : String(result.metrics[name])}</td>
              <td>{status}{result.metric_reasons[name]?.length ? `: ${result.metric_reasons[name].join(", ")}` : ""}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <details>
        <summary>Saved events, trades, and samples</summary>
        <pre className="spot-replay-json">{JSON.stringify({ events: result.events, trades: result.trades,
          samples: result.samples, open_position: result.open_position }, null, 2)}</pre>
      </details>
      <p>{replay.content.notice}</p>
    </section>
  );
}
