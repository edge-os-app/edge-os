"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { EffectRunBody, EffectRunResult, InvestigationSaveResult } from "../lib/types";

const FIXTURE_START = "2026-01-01T00:00:00Z";

function operationKeys(prefix: string) {
  return { operation_id: crypto.randomUUID(), idempotency_key: `${prefix}-${crypto.randomUUID()}` };
}

function failure(error: unknown): string {
  return error instanceof ApiError ? error.detail : "The saved effect report could not be loaded.";
}

function exampleBody(saved: InvestigationSaveResult): EffectRunBody {
  const plan = saved.declaration.content.configuration.evaluation_plan;
  const quoteUnit = "QUOTE:0x2222222222222222222222222222222222222222";
  const price = { op: "gt", args: [{ op: "price" }, { op: "constant", value: "99", unit: "PRICE" }] };
  return {
    ...operationKeys("p09-run"), fixture_id: "synthetic-effect-comparison/1", adoption: "ADOPT",
    schedule: { version: "p09.decision-clock/1", start: FIXTURE_START,
      end: "2026-01-01T00:20:00Z", interval_seconds: 300 },
    bindings: plan.map((item, index) => ({
      evaluation_id: item.evaluation_id, trial_id: item.trial_id, variant_id: item.variant_id,
      price_expression: price,
      volume_expression: { op: "gt", args: [{ op: "quote_volume" },
        { op: "constant", value: index === 0 ? "4" : "6", unit: quoteUnit }] },
      essential_inputs: ["price", "quote_volume"],
    })),
    incremental_volume_declared: true,
  };
}

export function EffectComparisonPanel({ intakeId, saved }: { intakeId: string; saved: InvestigationSaveResult }) {
  const [runs, setRuns] = useState<EffectRunResult[]>([]);
  const [body, setBody] = useState<EffectRunBody | null>(null);
  const [selected, setSelected] = useState<EffectRunResult | null>(null);
  const [adopted, setAdopted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = async () => {
    const response = await api.effectRuns(intakeId);
    const matching = response.runs.filter((item) => item.run.p08_declaration_id === saved.declaration.record_id);
    setRuns(matching);
    const latest = matching[matching.length - 1] ?? null;
    setSelected((current) => current
      ? matching.find((item) => item.run.record_id === current.run.record_id) ?? latest
      : latest);
  };

  useEffect(() => {
    let current = true;
    api.effectRuns(intakeId).then((response) => {
      if (!current) return;
      const matching = response.runs.filter((item) => item.run.p08_declaration_id === saved.declaration.record_id);
      setRuns(matching); setSelected(matching[matching.length - 1] ?? null);
    }).catch((cause: unknown) => { if (current) setError(failure(cause)); })
      .finally(() => { if (current) setLoaded(true); });
    return () => { current = false; };
  }, [intakeId, saved.declaration.record_id]);

  const adopt = async () => {
    if (!body || !adopted || busy) return;
    setBusy(true); setError("");
    try {
      const result = await api.adoptEffectRun(intakeId, saved.declaration.record_id, body);
      setSelected(result); setBody(null); setAdopted(false); await refresh();
    } catch (cause) { setError(failure(cause)); }
    finally { setBusy(false); }
  };

  const evaluate = async () => {
    if (!selected || selected.report || busy) return;
    setBusy(true); setError("");
    try {
      const result = await api.executeEffectRun(intakeId, selected.run.record_id, operationKeys("p09-attempt"));
      setSelected(result); await refresh();
    } catch (cause) {
      setError(failure(cause));
      try { await refresh(); } catch { /* keep the original error visible and allow a retry */ }
    } finally { setBusy(false); }
  };

  const reopen = async (runId: string) => {
    setBusy(true); setError("");
    try { setSelected(await api.effectRun(intakeId, runId)); }
    catch (cause) { setError(failure(cause)); }
    finally { setBusy(false); }
  };

  const configuration = saved.declaration.content.configuration;
  const protectedPlan = configuration.partitions.some((partition) => partition.role !== "DESCRIPTIVE");
  const result = selected?.report?.content.result;

  return (
    <section className="stack effect-comparison" aria-labelledby="effect-comparison-title" data-testid="effect-comparison">
      <div>
        <h3 id="effect-comparison-title">Descriptive comparison</h3>
        <p className="muted">Saving the P08 declaration did not read outcomes. This path uses an authored synthetic fixture only. Real-data mode is unavailable while P07 history remains unresolved.</p>
      </div>
      {error ? <p className="status err" role="alert">{error}</p> : null}
      {!loaded ? <p role="status" aria-busy="true">Loading saved comparison runs.</p> : null}
      {protectedPlan ? <p className="status stop" role="status">This declaration includes a protected partition. The synthetic descriptive profile does not access training, validation, or holdout rows.</p> : null}
      {runs.length ? <div className="stack" aria-label="Saved comparison runs">
        <h4>Saved P09 run declarations</h4>
        {runs.map((item) => <div className="card" key={item.run.record_id}>
          <span className="mono">{item.run.record_id}</span>
          <span className="muted">P08 declaration {item.run.p08_declaration_id}</span>
          <button className="btn btn-secondary" type="button" onClick={() => void reopen(item.run.record_id)} disabled={busy}>
            Reopen exact run and report
          </button>
        </div>)}
      </div> : null}

      {!selected && !body && !protectedPlan ? <button className="btn btn-secondary" type="button"
        onClick={() => { setError(""); setBody(exampleBody(saved)); setAdopted(false); }}>
        Load explicit synthetic example
      </button> : null}

      {body ? <div className="stack">
        <p className="status stop" role="note">This visible example was authored for the synthetic fixture. It is a new P09 run declaration, not an inference from P08 hypothesis text. Saving it does not read outcomes.</p>
        <dl className="kv">
          <dt>Fixture</dt><dd>{body.fixture_id} · logic only</dd>
          <dt>Decision schedule</dt><dd>{body.schedule.start} to {body.schedule.end} · every {body.schedule.interval_seconds} seconds; two authored feature buckets and two intentionally unavailable buckets</dd>
          <dt>P08 declaration</dt><dd className="mono">{saved.declaration.record_id}</dd>
          <dt>Primary contrast</dt><dd>Both authored variants split at 00:00 and 00:05: quote volume 3 yields −0.1; quote volume 8 yields +0.1 over the 15-minute outcome horizon. The 00:10 and 00:15 buckets are absent and remain unavailable. Expected synthetic contrast: +0.2.</dd>
          <dt>Incremental volume</dt><dd>Predeclared price-only versus quote-volume-only mapping, with price fixed at TRUE.</dd>
        </dl>
        <div className="table-scroll">
          <table className="records">
            <caption>Exact P08 identities and explicitly authored P06 fixture bindings</caption>
            <thead><tr><th>Evaluation</th><th>Trial</th><th>Variant</th><th>Price rule</th><th>Quote-volume rule</th><th>Essential inputs</th></tr></thead>
            <tbody>{body.bindings.map((binding) => <tr key={binding.evaluation_id}>
              <td className="mono">{binding.evaluation_id}</td><td className="mono">{binding.trial_id}</td><td>{binding.variant_id}</td>
              <td><code>price &gt; 99 PRICE</code></td>
              <td><code>quote_volume &gt; {(binding.volume_expression as { args?: { value?: string }[] }).args?.[1]?.value} QUOTE</code></td>
              <td>price, quote_volume</td>
            </tr>)}</tbody>
          </table>
        </div>
        <details><summary>Review complete P09 run configuration</summary><pre className="records-json">{JSON.stringify(body, null, 2)}</pre></details>
        <label className="choice"><input type="checkbox" checked={adopted} onChange={(event) => setAdopted(event.target.checked)} />
          <span>I reviewed these exact P08 identities, P06 rules, essential-input mapping, fixture, decision schedule, and separate volume contrast. Adopt this immutable P09 run before any outcome access.</span>
        </label>
        <div className="btn-row">
          <button className="btn btn-primary" type="button" onClick={() => void adopt()} disabled={!adopted || busy}>
            {busy ? "Saving run declaration…" : "Adopt synthetic run declaration"}
          </button>
          <button className="btn btn-secondary" type="button" onClick={() => { setBody(null); setAdopted(false); }} disabled={busy}>Cancel</button>
        </div>
      </div> : null}

      {selected ? <div className="stack" data-testid="effect-run-selected">
        <p className="mono">P09 run {selected.run.record_id}</p>
        <p className="status" role="status">P09 outcome access: {selected.events.some((event) => event.content.outcome_accessed === true)
          ? `recorded at event sequence ${selected.events.find((event) => event.content.kind === "OUTCOME_ACCESS_STARTED")?.sequence ?? "unknown"}`
          : "not recorded"}. P08 declaration-time labels remain a separate snapshot.</p>
        {!selected.report ? <>
        <p className="status stop" role="status">Run declaration saved. No report exists yet. Review the attempt and outcome-access history, then evaluate the named synthetic fixture as a separate action.</p>
          <details><summary>Run declaration and append-only attempt history</summary><pre className="records-json">{JSON.stringify({ content: selected.run.content, events: selected.events }, null, 2)}</pre></details>
          <button className="btn btn-primary" type="button" onClick={() => void evaluate()} disabled={busy}>
            {busy ? "Evaluating synthetic fixture…" : selected.events.some((event) => event.content.kind === "ATTEMPT_FAILED") ? "Retry synthetic evaluation" : "Evaluate synthetic fixture"}
          </button>
        </> : <div className="status ok" data-testid="effect-report-saved">
          <h4>Saved descriptive report · UNRESOLVED</h4>
          <p>{selected.report.content.fixture_qualification}. This is synthetic logic evidence only, not a real study or a support claim.</p>
          <dl className="kv">
            <dt>Report ID</dt><dd className="mono">{selected.report.record_id}</dd>
            <dt>P08 declaration</dt><dd className="mono">{selected.report.content.p08_declaration_id}</dd>
            <dt>Fixture SHA-256</dt><dd className="mono">{selected.report.content.fixture_sha256}</dd>
            <dt>Profile SHA-256</dt><dd className="mono">{selected.report.content.profile_sha256}</dd>
            <dt>Opportunity count</dt><dd>{result.opportunity_count}</dd>
            <dt>Excluded</dt><dd>{result.excluded_count}</dd>
            <dt>Missing outcome</dt><dd>{result.missing_outcome_count}</dd>
            <dt>Statistical status</dt><dd>{result.statistical_status} · {result.statistical_reasons.join(", ")}</dd>
          </dl>
          {result.variants.map((variant: {
            evaluation_id: string; variant_id: string;
            general_comparison: { triggered: { mean: string | null }; control: { mean: string | null };
              triggered_minus_control_mean: string | null };
            incremental_volume_comparison: { status: string; triggered_minus_control_mean: string | null };
          }) => <section className="stack" key={variant.evaluation_id}>
            <h5>{variant.variant_id} · evaluation {variant.evaluation_id}</h5>
            <p>Triggered mean: {variant.general_comparison.triggered.mean ?? "unavailable"}; qualified FALSE-control mean: {variant.general_comparison.control.mean ?? "unavailable"}; triggered minus control: {variant.general_comparison.triggered_minus_control_mean ?? "unavailable"}.</p>
            <p>Incremental volume: {variant.incremental_volume_comparison.status}; contrast: {variant.incremental_volume_comparison.triggered_minus_control_mean ?? "unavailable"}.</p>
            <details><summary>Every opportunity, exclusion, reference and diagnostic</summary><pre className="records-json">{JSON.stringify(variant, null, 2)}</pre></details>
          </section>)}
          <p>{selected.report.content.next_action}</p>
          <details><summary>Exact saved report and access order</summary><pre className="records-json">{JSON.stringify(selected.report.content, null, 2)}</pre></details>
          <button className="btn btn-secondary" type="button" onClick={() => void reopen(selected.run.record_id)} disabled={busy}>Reopen saved report without rerunning</button>
        </div>}
      </div> : null}
    </section>
  );
}
