import type { SpotReplayRecord } from "../lib/types";

interface Props { replay: SpotReplayRecord }

export function ReplayResult({ replay }: Props) {
  const result = replay.content.result;
  return (
    <section className={`status ${result.status === "COMPLETE" ? "ok" : "stop"}`} data-testid="spot-replay-result"
      aria-labelledby="spot-replay-result-title">
      <h3 id="spot-replay-result-title">Saved replay: {result.status === "COMPLETE" ? "complete" : "unavailable"}</h3>
      <dl className="kv">
        <dt>Replay ID</dt><dd className="mono" data-testid="spot-replay-id">{replay.replay_id}</dd>
        <dt>Saved hash</dt><dd className="mono">{replay.content_sha256}</dd>
        <dt>Evidence</dt><dd>{result.evidence_class}. This is an authored fixture, not observed market history.</dd>
        <dt>Repeatability</dt><dd className="mono">{result.repeatability_id ?? "Unavailable before replay"}</dd>
      </dl>
      {result.reason ? <p role="alert">{result.reason.code} at {result.reason.path}: {result.reason.detail}</p> : null}
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
