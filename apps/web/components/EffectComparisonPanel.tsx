"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { EffectRunBody, EffectRunResult, InvestigationSaveResult } from "../lib/types";
import { Details } from "./Details";
import { plural } from "../lib/plural";

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
        <p className="muted">Saving the earlier rule did not read results. This comparison uses example data only. Real data is unavailable here.</p>
      </div>
      {error ? <p className="status err" role="alert">{error}</p> : null}
      {!loaded ? <p role="status" aria-busy="true">Loading saved comparisons.</p> : null}
      {protectedPlan ? <p className="status stop" role="status">This rule includes a protected time period. The example comparison does not read training, validation or holdout rows.</p> : null}
      {runs.length ? <div className="stack" aria-label="Saved comparison runs">
        <h4>Saved comparisons</h4>
        {runs.map((item) => <div className="card" key={item.run.record_id}>
          <span className="mono">{item.run.record_id}</span>
          <span className="muted">Earlier rule {item.run.p08_declaration_id.slice(0, 8)}</span>
          <button className="btn btn-secondary" type="button" onClick={() => void reopen(item.run.record_id)} disabled={busy}>
            Reopen the saved comparison and report
          </button>
        </div>)}
      </div> : null}

      {!selected && !body && !protectedPlan ? <button className="btn btn-secondary" type="button"
        onClick={() => { setError(""); setBody(exampleBody(saved)); setAdopted(false); }}>
        Load the example comparison
      </button> : null}

      {body ? <div className="stack">
        <p className="status stop" role="note">This example was written for the local example data. It is a new comparison, not a guess taken from the hypothesis text. Each planned test keeps one fixed rule across comparisons. Saving it does not read results.</p>
        <dl className="kv">
          <dt>Example data</dt><dd>logic only</dd>
          <dt>Schedule</dt><dd>{body.schedule.start} to {body.schedule.end} · every {body.schedule.interval_seconds} seconds; four opportunities per evaluation, with two authored feature buckets and two intentionally unavailable buckets</dd>
          <dt>Earlier rule</dt><dd className="mono">{saved.declaration.record_id.slice(0, 8)}</dd>
          <dt>Primary contrast</dt><dd>Both example variants split at 00:00 and 00:05: quote volume 3 yields −0.1; quote volume 8 yields +0.1 over the 15-minute outcome horizon. The 00:10 and 00:15 periods are absent and remain unavailable. Expected example difference: +0.2.</dd>
          <dt>Extra volume</dt><dd>Predeclared price-only versus quote-volume-only mapping, with price fixed at TRUE.</dd>
        </dl>
        <div className="table-scroll">
          <table className="records">
            <caption>Exact planned tests and example rules</caption>
            <thead><tr><th>Test</th><th>Trial</th><th>Variant</th><th>Price rule</th><th>Quote-volume rule</th><th>Required inputs</th></tr></thead>
            <tbody>{body.bindings.map((binding) => <tr key={binding.evaluation_id}>
              <td className="mono">{binding.evaluation_id}</td><td className="mono">{binding.trial_id}</td><td>{binding.variant_id}</td>
              <td><code>price &gt; 99 PRICE</code></td>
              <td><code>quote_volume &gt; {(binding.volume_expression as { args?: { value?: string }[] }).args?.[1]?.value} QUOTE</code></td>
              <td>price, quote_volume</td>
            </tr>)}</tbody>
          </table>
        </div>
        <Details summary="Details"><p className="mono">Earlier rule {saved.declaration.record_id}</p><pre className="records-json">{JSON.stringify(body, null, 2)}</pre></Details>
        <label className="choice"><input type="checkbox" checked={adopted} onChange={(event) => setAdopted(event.target.checked)} />
          <span>I reviewed these tests, rules, required inputs, example data and schedule. Adopt this comparison before any result is read.</span>
        </label>
        <div className="btn-row">
          <button className="btn btn-primary" type="button" onClick={() => void adopt()} disabled={!adopted || busy}>
            {busy ? "Saving comparison…" : "Adopt example comparison"}
          </button>
          <button className="btn btn-secondary" type="button" onClick={() => { setBody(null); setAdopted(false); }} disabled={busy}>Cancel</button>
        </div>
      </div> : null}

      {selected ? <div className="stack" data-testid="effect-run-selected">
        <p className="mono">Comparison {selected.run.record_id.slice(0, 8)}</p>
        <p className="status" role="status">Result access: {selected.events.some((event) => event.content.outcome_accessed === true)
          ? `recorded at step ${selected.events.find((event) => event.content.kind === "OUTCOME_ACCESS_STARTED")?.sequence ?? "unknown"}`
          : "not recorded"}. The earlier rule's labels remain a separate snapshot.</p>
        {!selected.report ? <>
        <p className="status stop" role="status">Comparison saved. No report yet. Review the attempts and result access, then evaluate the example data as a separate action.</p>
          <details><summary>Comparison and attempt history</summary><pre className="records-json">{JSON.stringify({ content: selected.run.content, events: selected.events }, null, 2)}</pre></details>
          <button className="btn btn-primary" type="button" onClick={() => void evaluate()} disabled={busy}>
            {busy ? "Evaluating example data…" : selected.events.some((event) => event.content.kind === "ATTEMPT_FAILED") ? "Retry example evaluation" : "Evaluate example data"}
          </button>
        </> : <div className="status ok" data-testid="effect-report-saved">
          <h4>Saved descriptive report · unresolved</h4>
          <p>{selected.report.content.fixture_qualification}. This is example logic only, not a real study or a support claim.</p>
          <dl className="kv">
            <dt>Report ID</dt><dd className="mono">{selected.report.record_id}</dd>
            <dt>Earlier rule</dt><dd className="mono">{selected.report.content.p08_declaration_id.slice(0, 8)}</dd>
            <dt>Example data hash</dt><dd className="mono">{selected.report.content.fixture_sha256}</dd>
            <dt>Profile hash</dt><dd className="mono">{selected.report.content.profile_sha256}</dd>
            <dt>Chances found</dt><dd>{result.opportunity_count}</dd>
            <dt>Excluded</dt><dd>{result.excluded_count}</dd>
            <dt>Missing result</dt><dd>{result.missing_outcome_count}</dd>
            <dt>Statistical status</dt><dd>{result.statistical_status} · {result.statistical_reasons.join(", ")}</dd>
          </dl>
          {result.variants.map((variant: {
            evaluation_id: string; variant_id: string;
            general_comparison: { triggered: { mean: string | null }; control: { mean: string | null };
              triggered_minus_control_mean: string | null };
            incremental_volume_comparison: { status: string; triggered_minus_control_mean: string | null };
          }) => <section className="stack" key={variant.evaluation_id}>
            <h5>{variant.variant_id} · evaluation {variant.evaluation_id}</h5>
            <p>Mean when the rule fired: {variant.general_comparison.triggered.mean ?? "unavailable"}; Mean when it did not fire: {variant.general_comparison.control.mean ?? "unavailable"}; difference: {variant.general_comparison.triggered_minus_control_mean ?? "unavailable"}.</p>
            <p>Extra volume: {variant.incremental_volume_comparison.status}; contrast: {variant.incremental_volume_comparison.triggered_minus_control_mean ?? "unavailable"}.</p>
            <details><summary>Every chance, exclusion and reference</summary><pre className="records-json">{JSON.stringify(variant, null, 2)}</pre></details>
          </section>)}
          <p>{selected.report.content.next_action}</p>
          <details><summary>Exact saved report and order of access</summary><pre className="records-json">{JSON.stringify(selected.report.content, null, 2)}</pre></details>
          <button className="btn btn-secondary" type="button" onClick={() => void reopen(selected.run.record_id)} disabled={busy}>Reopen saved report without rerunning</button>
        </div>}
      </div> : null}
    </section>
  );
}
