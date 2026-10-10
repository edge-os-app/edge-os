"use client";

import { useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { SpotReplayBody, SpotReplayDependency, SpotReplayRecord, Strategy } from "../lib/types";
import { ReplayResult } from "./ReplayResult";

type FieldName = "entry" | "exit";
type Series = SpotReplayDependency["series"];
type Dependencies = Record<FieldName, SpotReplayDependency[]>;

interface Props { strategy: Strategy; strategyId: string; strategyRevisionId: string }

function emptyDependencies(): Dependencies { return { entry: [], exit: [] }; }

function makeBody(strategyId: string, revisionId: string, dependencies: Dependencies): SpotReplayBody {
  return {
    idempotency_key: `p13-${crypto.randomUUID()}`,
    strategy_id: strategyId,
    strategy_revision_id: revisionId,
    dataset_fixture_id: "p13.wc01/1",
    run_configuration_id: `p13-config-${crypto.randomUUID()}`,
    window_start: "2026-10-01T12:05:00Z",
    window_end: "2026-10-01T12:35:00Z",
    initial_cash_quote: "1000",
    initial_base_amount: "0",
    initial_basis_quote: "0",
    essential_fields: {
      entry: { state: "BOUND", essential_dependencies: dependencies.entry },
      exit: { state: "BOUND", essential_dependencies: dependencies.exit },
    },
  };
}

export function SpotReplayPanel({ strategy, strategyId, strategyRevisionId }: Props) {
  const availableSeries = useMemo(() => strategy.data_inputs.filter(
    (series): series is Series => series === "price" || series === "quote_volume"), [strategy.data_inputs]);
  const [dependencies, setDependencies] = useState<Dependencies>(emptyDependencies);
  const [reviewed, setReviewed] = useState<Record<FieldName, boolean>>({ entry: false, exit: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [record, setRecord] = useState<SpotReplayRecord | null>(null);
  const [replayId, setReplayId] = useState("");
  const [loadNotice, setLoadNotice] = useState("");
  const [pendingBody, setPendingBody] = useState<SpotReplayBody | null>(null);

  const updateDependency = (field: FieldName, index: number, changes: Partial<SpotReplayDependency>) => {
    setDependencies((current) => ({ ...current, [field]: current[field].map((dependency, position) =>
      position === index ? { ...dependency, ...changes } : dependency) }));
  };

  const addDependency = (field: FieldName) => {
    const series = availableSeries[0];
    if (!series) return;
    setDependencies((current) => ({ ...current, [field]: [...current[field], { series, offset_buckets: 0 }] }));
  };

  const removeDependency = (field: FieldName, index: number) => {
    setDependencies((current) => ({ ...current, [field]: current[field].filter((_, position) => position !== index) }));
  };

  const save = async () => {
    if (busy || !reviewed.entry || !reviewed.exit) return;
    setBusy(true); setError(""); setLoadNotice("");
    const body = pendingBody ?? makeBody(strategyId, strategyRevisionId, dependencies);
    setPendingBody(body);
    try {
      const saved = await api.createSpotReplay(body);
      setRecord(saved); setReplayId(saved.replay_id); setPendingBody(null);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setPendingBody(null);
        setError(`${cause.detail} This request was rejected before it was saved. Correct the editable settings and submit again.`);
      } else {
        setError(cause instanceof ApiError ? cause.detail : "The replay may have saved. Retry with the same key or load its saved ID.");
      }
    } finally { setBusy(false); }
  };

  const load = async () => {
    if (!replayId.trim() || busy) return;
    setBusy(true); setError(""); setLoadNotice("");
    try {
      const saved = await api.spotReplay(replayId.trim());
      setRecord(saved); setReplayId(saved.replay_id);
      setLoadNotice("Loaded the exact saved result. The replay did not run again.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "The saved replay could not be loaded. Check the ID and retry.");
    } finally { setBusy(false); }
  };

  return (
    <section className="panel spot-replay" aria-labelledby="spot-replay-title" data-testid="spot-replay">
      <h2 id="spot-replay-title">Test the saved strategy on synthetic prices</h2>
      <p className="muted">The authored synthetic fixture covers 12:05 to 12:35 UTC, with three earlier buckets for warm-up. Fills are assumptions. The replay uses saved fee and slippage rates, and omits gas, spread, extra impact, and capacity. Review each essential input set before saving.</p>
      <h3>New run settings (editable)</h3>
      <dl className="kv">
        <dt>Fixture</dt><dd className="mono">p13.wc01/1 · synthetic only</dd>
        <dt>Window</dt><dd>2026-10-01 12:05 to 12:35 UTC</dd>
        <dt>Starting capital (quote)</dt><dd>1000. This fixed amount will be used for a new run.</dd>
        <dt>Starting base amount</dt><dd>0</dd>
        <dt>Starting cost basis</dt><dd>0</dd>
        <dt>Trade size</dt><dd>{strategy.sizing.amount} {strategy.sizing.unit}</dd>
        <dt>Warm-up</dt><dd>{strategy.warmup_buckets} scheduled buckets</dd>
        <dt>Saved cost source</dt><dd>{strategy.cost_assumptions.source_ref}; fee {strategy.cost_assumptions.fee_rate}; slippage {strategy.cost_assumptions.slippage_rate}</dd>
        <dt>Execution effects</dt><dd>Gas, spread, extra impact, and capacity are not modeled.</dd>
      </dl>

      {(["entry", "exit"] as const).map((field) => (
        <fieldset className="spot-replay-field" key={field}>
          <legend>{field === "entry" ? "Entry" : "Exit"} essential dependencies</legend>
          <p className="muted">Bind the complete saved dependency set. Offsets count scheduled five-minute buckets. Do not guess.</p>
          {dependencies[field].map((dependency, index) => (
            <div className="spot-replay-dependency" key={`${field}-${index}`}>
              <label className="field">Series
                <select className="input" aria-label={`${field} dependency series ${index + 1}`} value={dependency.series}
                  onChange={(event) => updateDependency(field, index, { series: event.target.value as Series })}>
                  {availableSeries.map((series) => <option key={series} value={series}>{series}</option>)}
                </select>
              </label>
              <label className="field">Scheduled offset
                <input className="input" aria-label={`${field} dependency offset ${index + 1}`} type="number" step="1" max="0"
                  value={dependency.offset_buckets} onChange={(event) => updateDependency(field, index,
                    { offset_buckets: Number(event.target.value) })} />
              </label>
              <button className="btn btn-secondary" type="button" onClick={() => removeDependency(field, index)}
                aria-label={`Remove ${field} dependency ${index + 1}`}>Remove</button>
            </div>
          ))}
          <div className="btn-row">
            <button className="btn btn-secondary" type="button" onClick={() => addDependency(field)}
              disabled={availableSeries.length === 0}>Add {field} dependency</button>
            <label className="choice">
              <input type="checkbox" checked={reviewed[field]} onChange={(event) =>
                setReviewed((current) => ({ ...current, [field]: event.target.checked }))} />
              I reviewed the {field} dependency set
            </label>
          </div>
        </fieldset>
      ))}

      <button className="btn btn-primary" type="button" onClick={save} aria-disabled={busy || undefined}
        disabled={!reviewed.entry || !reviewed.exit}>
        {busy ? "Saving replay…" : pendingBody ? "Retry same replay" : "Save synthetic replay"}
      </button>
      {pendingBody ? <p role="status" className="muted">This attempt has an uncertain outcome. Retry uses its original inputs and key; edits above apply only to a new attempt.</p> : null}
      {error ? <p role="alert" className="status err">{error}</p> : null}
      {loadNotice ? <p role="status" className="status ok">{loadNotice}</p> : null}

      <div className="field">
        <label htmlFor="spot-replay-load-id">Saved replay ID</label>
        <input className="input mono" id="spot-replay-load-id" value={replayId} onChange={(event) => setReplayId(event.target.value)} />
        <button className="btn btn-secondary" type="button" onClick={load} disabled={!replayId.trim() || busy}>
          {busy ? "Loading replay…" : "Load saved replay"}
        </button>
      </div>

      {record ? <ReplayResult replay={record} /> : <p className="muted">No replay is saved for this revision yet.</p>}
    </section>
  );
}
