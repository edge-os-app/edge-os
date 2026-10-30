"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { payloadBindingText, payloadBindingUsable } from "../lib/types";
import type { DatasetSummary, MarketAdoptionBody } from "../lib/api";
import { Details } from "./Details";
import { EVIDENCE_CLASS, plain } from "../lib/labels";

interface Props {
  intakeId: string;
  interpretationRevisionId: string;
  parentRevisionId: string | null;
  currentQuoteUnit: string;
  /** Reloads the saved request. Resolves to the reloaded head draft ID, or null when the read-back failed. */
  reload(): Promise<string | null>;
}

const AMOUNT = /^(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$/;
const SIGNED = /^-?(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$/;

function describe(node: unknown): string {
  const item = node as { op?: string; args?: unknown[]; value?: unknown; lookback_buckets?: number; unit?: string };
  if (!item || typeof item !== "object") return String(node);
  if (item.op === "constant") return `${String(item.value)}${item.unit && item.unit !== "DIMENSIONLESS" ? ` ${item.unit}` : ""}`;
  if (item.op === "price_return") return `${item.lookback_buckets}-bucket price return`;
  if (item.op === "quote_volume") return "quote volume";
  if (item.op === "price") return "price";
  const symbol: Record<string, string> = { gt: ">", lt: "<", gte: "≥", lte: "≤", and: "and", or: "or" };
  if (item.args && item.op && symbol[item.op]) return item.args.map(describe).join(` ${symbol[item.op]} `);
  return JSON.stringify(node);
}

function failure(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

const KNOWN_SYNTHETIC_EVIDENCE = new Set([
  "SYNTHETIC_FIXTURE", "RECORDED_RESPONSE", "RECORDED_NATIVE_RESPONSE",
  "AUTHORED_HTTP_RESPONSE", "RELEASE_STAND_IN_RESPONSE",
]);

// Only PROVIDER_ACTUAL is observed provider history; known recorded/authored classes stay synthetic; anything else
// is shown literally and claimed as neither.
function provenance(item: DatasetSummary): string {
  if (item.evidence_class === "PROVIDER_ACTUAL") return "Saved provider history. This is observed provider data.";
  return KNOWN_SYNTHETIC_EVIDENCE.has(item.evidence_class)
    ? "Synthetic recorded responses, not observed market history."
    : `${item.evidence_class} is an unrecognized evidence class; this view claims neither observed history nor synthetic prices.`;
}

/** Adopt one saved QUALIFIED recorded-history market for a NEW draft. Nothing earlier is changed or published. */
export function MarketAdoption({ intakeId, interpretationRevisionId, parentRevisionId, currentQuoteUnit, reload }: Props) {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [amount, setAmount] = useState("");
  const [notional, setNotional] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [ruleId, setRuleId] = useState("");
  const [exitLookback, setExitLookback] = useState("");
  const [exitThreshold, setExitThreshold] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [pending, setPending] = useState<MarketAdoptionBody | null>(null);

  const load = async () => {
    setLoadError("");
    try { setDatasets((await api.historyDatasets()).datasets); }
    catch (cause) { setLoadError(failure(cause, "Your saved data could not be loaded.")); }
  };
  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // A required payload binding that does not PASS blocks the market even when the saved verdict is QUALIFIED.
  const qualified = (datasets ?? []).filter((item) => item.binding_state === "QUALIFIED_BINDING"
    && item.verdict.overall === "QUALIFIED" && item.hashes_verified.content_sha256 && item.hashes_verified.raw_evidence_sha256
    && payloadBindingUsable(item.payload_binding));
  const others = (datasets ?? []).filter((item) => !qualified.includes(item));
  const chosen = qualified.find((item) => item.dataset_id === datasetId) ?? null;
  const binding = (chosen?.market_binding ?? {}) as Record<string, string | number | null | string[]>;
  const amountsValid = AMOUNT.test(amount) && AMOUNT.test(notional);
  const rule = chosen?.declared_rules.find((item) => item.evaluation_id === ruleId) ?? null;
  const exitValid = /^[1-9][0-9]?$/.test(exitLookback) && SIGNED.test(exitThreshold);
  const ready = amountsValid && rule !== null && exitValid;

  const submit = async (body: MarketAdoptionBody) => {
    setBusy(true); setError(""); setSaved(""); setPending(body);
    try {
      const result = await api.adoptMarket(intakeId, body);
      const shown = await reload();
      if (shown === result.adoption.draft_id) {
        setPending(null);
        setSaved(`New draft ${result.adoption.draft_id} uses the recorded market. Review its rules, then save it as a new version.`);
      } else {
        setError("The adoption was saved, but the request could not be read back. Reload the page before you save a version.");
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 0) {
        setError("We could not confirm the adoption. Retry uses the same request and key, so it cannot adopt twice.");
      } else {
        setPending(null);
        if (cause instanceof ApiError && cause.code === "parent_revision_conflict") await reload();
        setError(failure(cause, "The market was not adopted."));
      }
    } finally { setBusy(false); }
  };

  const adopt = () => {
    if (busy || !chosen || !confirmed || !ready || !rule || !chosen.quote_unit) return;
    void submit({ idempotency_key: `ui-market-${crypto.randomUUID()}`, expected_interpretation_revision_id: interpretationRevisionId,
      expected_parent_revision_id: parentRevisionId, dataset_id: chosen.dataset_id, adoption: "ADOPT_DATASET_MARKET",
      quote_unit: chosen.quote_unit, evaluation_id: rule.evaluation_id,
      exit_rule: { op: "lt", args: [{ op: "price_return", lookback_buckets: Number(exitLookback) },
        { op: "constant", value: exitThreshold, unit: "DIMENSIONLESS" }] },
      sizing_amount: amount, max_quote_notional: notional });
  };

  return (
    <section className="panel stack" aria-labelledby="market-adoption-title" data-testid="market-adoption"
      style={{ overflowWrap: "anywhere" }}>
      <h2 id="market-adoption-title">Use a saved market (optional)</h2>
      <p className="muted">This makes a new draft on a saved market. Earlier drafts and saved versions stay unchanged. The saved data&rsquo;s own label decides the source note below. Trading stays unapproved and no trading permission is granted.</p>
      {loadError ? <div className="status err" role="alert"><p>{loadError}</p>
        <button className="btn btn-secondary" type="button" onClick={() => void load()}>Retry loading saved data</button></div> : null}
      {datasets === null && !loadError ? <p role="status" aria-busy="true" className="muted">Loading your saved data.</p> : null}
      {datasets !== null && qualified.length === 0 ? <p className="status stop">No saved data is ready to use. Run a history investigation first.</p> : null}
      {others.length ? (
        <details>
          <summary>Saved data that cannot supply a market ({others.length})</summary>
          <ul>{others.map((item) => <li key={item.dataset_id}><span className="mono">{item.dataset_id}</span>: {item.source_id}, {item.verdict.overall}, {item.binding_state}{item.unavailable_states.length ? ` (${item.unavailable_states.join(", ")})` : ""}
            {payloadBindingUsable(item.payload_binding) ? null : <span data-testid="market-adoption-binding-blocked"> {payloadBindingText(item.payload_binding)}</span>}</li>)}</ul>
        </details>
      ) : null}
      {qualified.length ? (
        <div className="field">
          <label htmlFor="market-dataset">Saved data</label>
          <select id="market-dataset" className="input" value={datasetId} onChange={(event) => { setDatasetId(event.target.value); setRuleId(""); setConfirmed(false); }}>
            <option value="">Choose a qualified dataset</option>
            {qualified.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.source_id} · {item.dataset_id.slice(0, 8)}</option>)}
          </select>
        </div>
      ) : null}
      {chosen ? (
        <div className="stack" data-testid="market-adoption-review">
          <dl className="kv">
            <dt>Saved data</dt><dd className="mono">{chosen.dataset_id}</dd>
            <dt>Source</dt><dd>{plain(EVIDENCE_CLASS, chosen.evidence_class, "unknown data label")}</dd>
            <dt>Result</dt><dd>{chosen.verdict.overall === "QUALIFIED" ? "Qualified" : "Not qualified"}; window {chosen.window_start} to {chosen.window_end}</dd>
            <dt>Network</dt><dd>MONAD, chain {String(binding.chain_id)}</dd>
            <dt>Pool</dt><dd className="mono">{String(binding.pool_address)}</dd>
            <dt>Base asset</dt><dd className="mono">{String(binding.base_asset)} ({String(binding.base_decimals)} decimals)</dd>
            <dt>Quote asset</dt><dd className="mono">{String(binding.quote_asset)} ({String(binding.quote_decimals)} decimals)</dd>
            <dt>Market direction</dt><dd>{String(binding.orientation)}</dd>
            <dt>Format versions</dt><dd>{String(binding.event_schema_version)}; {String(binding.amount_conversion_version)}; {String(binding.data_route)}</dd>
            <dt>Evidence check</dt><dd>{plain(EVIDENCE_CLASS, String(binding.evidence_class), "unknown data label")}</dd>
            <dt>Delivery check</dt><dd data-testid="market-adoption-binding">The saved data {chosen.payload_binding?.status === "PASS" ? "matches the recorded delivery. It does not prove where the data came from." : "does not match the recorded delivery. Do not use it as a market."}</dd>
            <dt>Quote unit</dt><dd className="mono">{chosen.quote_unit}</dd>
          </dl>
          <Details summary="Details"><dl className="kv">
            <dt>Saved data ID</dt><dd className="mono">{chosen.dataset_id}</dd>
            <dt>Source ID</dt><dd className="mono">{chosen.source_id}</dd>
            <dt>Data label</dt><dd className="mono">{chosen.evidence_class}</dd>
            <dt>Route</dt><dd className="mono">{String(binding.data_route)}</dd>
            <dt>Qualification</dt><dd className="mono">{String(binding.qualification)}</dd>
            <dt>Format versions</dt><dd className="mono">{String(binding.event_schema_version)}; {String(binding.amount_conversion_version)}</dd>
            <dt>Delivery check</dt><dd className="mono">{payloadBindingText(chosen.payload_binding)}</dd>
          </dl></Details>
          <p className="muted" data-testid="market-adoption-provenance">{provenance(chosen)}</p>
          <div className="field">
            <label htmlFor="market-rule">Entry rule (one you saved for this data)</label>
            <select id="market-rule" className="input" value={ruleId} onChange={(event) => { setRuleId(event.target.value); setConfirmed(false); }}>
              <option value="">Choose a saved rule</option>
              {chosen.declared_rules.map((item) => <option key={item.evaluation_id} value={item.evaluation_id}>{item.variant_id}: {describe(item.price_expression)} and {describe(item.volume_expression)}</option>)}
            </select>
          </div>
          <p className="muted">The draft's entry becomes exactly this saved rule. Worked-example rules are refused.</p>
          <fieldset className="stack">
            <legend>Exit rule in your own words: exit when the price return is below a threshold</legend>
            <label className="field">Exit lookback (five-minute periods)
              <input className="input" inputMode="numeric" value={exitLookback} onChange={(event) => { setExitLookback(event.target.value.trim()); setConfirmed(false); }} />
            </label>
            <label className="field">Exit threshold (fraction, for example -0.001)
              <input className="input" value={exitThreshold} onChange={(event) => { setExitThreshold(event.target.value.trim()); setConfirmed(false); }} />
            </label>
          </fieldset>
          <p className="status stop">The current draft uses {currentQuoteUnit}. Amounts are not converted. Enter both amounts again in {chosen.quote_unit}.</p>
          <div className="field">
            <label htmlFor="market-amount">Trade size in the new quote unit</label>
            <input id="market-amount" className="input" inputMode="decimal" value={amount} onChange={(event) => { setAmount(event.target.value.trim()); setConfirmed(false); }} />
          </div>
          <div className="field">
            <label htmlFor="market-notional">Largest position value in the new quote unit</label>
            <input id="market-notional" className="input" inputMode="decimal" value={notional} onChange={(event) => { setNotional(event.target.value.trim()); setConfirmed(false); }} />
          </div>
          {(amount || notional) && !amountsValid ? <p className="status err">Use plain decimal amounts, for example 50 or 12.5.</p> : null}
          <label className="choice">
            <input type="checkbox" checked={confirmed} disabled={!ready} onChange={(event) => setConfirmed(event.target.checked)} />
            I adopt this market, this entry rule, this exit rule and these amounts in {chosen.quote_unit}
          </label>
          <button className="btn btn-primary" type="button" onClick={adopt} disabled={!confirmed || !ready} aria-disabled={busy || undefined}>
            {busy ? "Adopting…" : "Adopt this market for a new draft"}
          </button>
        </div>
      ) : null}
      {pending && !busy && error ? <button className="btn btn-secondary" type="button" onClick={() => void submit(pending)}>Retry the same adoption</button> : null}
      {error ? <p className="status err" role="alert">{error}</p> : null}
      {saved ? <p className="status ok" role="status">{saved}</p> : null}
    </section>
  );
}
