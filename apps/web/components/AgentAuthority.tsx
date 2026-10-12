"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { financial, formatRaw, type ConsentReview, type ConsentState, type ReviewedTerms } from "../lib/financial";

const ACTIVATION_COPY: Record<string, string> = {
  ACTIVATION_UNAVAILABLE: "No qualified execution route exists in this build. The adopted consent stays inactive and no action can run.",
  CONSENT_NOT_ADOPTED: "Adopt exact reviewed terms first. Nothing runs without them.",
  CONSENT_EXPIRED: "The adopted terms expired. No action can run until new terms are reviewed and adopted.",
  TERMS_VERSION_UNSUPPORTED: "These terms use a version the bounded action path does not support.",
  TERMS_INCOMPLETE: "A required limit is missing, so no action can run.",
  TERMS_ASSET_MISMATCH: "A limit names an asset outside this revision's market, so no action can run.",
  AGENT_NOT_READY: "The agent has no confirmed wallet bound to an exact saved revision.",
};

const LIMITS = [
  { key: "allocation", label: "Allocated trading capital", asset: "quote", fallback: "500000000" },
  { key: "quote_input", label: "Cumulative trading input", asset: "quote", fallback: "500000000" },
  { key: "base_inventory", label: "Cumulative acquired inventory", asset: "base", fallback: "1000000000000000000000" },
  { key: "gas_budget", label: "Total native gas", asset: "gas", fallback: "100000000000000000" },
  { key: "per_action_gas", label: "Gas per entry", asset: "gas", fallback: "1000000000000000" },
  { key: "per_exit_gas", label: "Gas per exit", asset: "gas", fallback: "1000000000000000" },
] as const;

type LimitKey = (typeof LIMITS)[number]["key"];

function defaultExpiry(): string {
  const date = new Date(Date.now() + 7 * 24 * 3600 * 1000);
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** Exact review and INACTIVE adoption of bounded terms for one agent, and the server's activation verdict. */
export function AgentAuthority({ agentId }: { agentId: string }) {
  const [state, setState] = useState<ConsentState | null>(null);
  const [phase, setPhase] = useState<"loading" | "loaded" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [limits, setLimits] = useState<Record<LimitKey, string>>(
    Object.fromEntries(LIMITS.map((item) => [item.key, item.fallback])) as Record<LimitKey, string>);
  const [attempts, setAttempts] = useState("5");
  const [expiry, setExpiry] = useState(defaultExpiry);
  const [review, setReview] = useState<ConsentReview | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const saved = await financial.consent(agentId);
      if (current !== seq.current) return;
      setState(saved); setPhase("loaded"); setUncertain(false); setError("");
    } catch (failure) {
      if (current !== seq.current) return;
      setPhase("error"); setError(failure instanceof ApiError ? failure.detail : "Saved consent could not be loaded.");
    }
  }, [agentId]);

  useEffect(() => { setPhase("loading"); void load(); }, [load]);

  const assets = state?.assets;
  const valid = LIMITS.every((item) => /^(0|[1-9][0-9]*)$/.test(limits[item.key])) && /^\d{1,7}$/.test(attempts)
    && !Number.isNaN(Date.parse(expiry));

  const terms = (): ReviewedTerms | null => {
    if (!assets) return null;
    const amount = (asset: "quote" | "base" | "gas", raw: string) => ({ ...assets[asset], raw });
    const named = (key: LimitKey) => LIMITS.find((item) => item.key === key)!;
    return {
      terms_version: "connected-spot/1", operating_purpose: "TRIAL",
      trial_objective: "Observe one bounded action through the application.",
      allocation: [amount("quote", limits.allocation)],
      allowances: (["quote_input", "base_inventory", "per_action_gas", "per_exit_gas"] as const)
        .map((key) => ({ name: key, amount: amount(named(key).asset, limits[key]) })),
      attempt_budget: Number(attempts), gas_budget: amount("gas", limits.gas_budget), expiry,
      supported_actions: ["ENTRY", "EXIT"], supported_assets: [assets.quote.asset_id, assets.base.asset_id],
      supported_routes: ["KURU_FLOW_FIXED_INPUT"], route: { adapter: "KURU_FLOW_FIXED_INPUT" },
      evidence: { status: "HYPOTHESIS", source: "saved-research" },
      stop_effects: ["STOP_NEW_ENTRIES denies new entries and keeps approved exits",
        "HALT_ALL_SWAPS denies every swap; pending actions and holdings stay"],
    };
  };

  const write = async (action: () => Promise<unknown>) => {
    if (busy || uncertain) return;
    setBusy(true); setError("");
    try { await action(); await load(); }
    catch (failure) {
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 500) setError(failure.detail);
      else { setUncertain(true); setError("The outcome is not confirmed. Check the saved consent before repeating it."); }
    } finally { setBusy(false); }
  };

  const activation = state?.activation;
  const shown = review ?? state?.reviews[0] ?? null;
  return (
    <section className="panel" aria-label="Agent authority">
      <h2>Bounded authority</h2>
      {phase === "loading" && <p role="status" className="muted">Loading saved consent…</p>}
      {phase === "error" && <div role="alert"><p>{error}</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Try again</button></div>}
      {state && <>
        <p>Adopting terms saves an <strong>inactive</strong> consent. It never signs, moves funds or grants wallet permission by itself.</p>
        <p data-testid="activation-state" role="status">
          {activation?.state === "FIXTURE_QUALIFIED"
            ? `Fixture qualification (${activation.evidence_class}). Bounded fixture actions can run under these exact terms; this is not live authority.`
            : ACTIVATION_COPY[activation?.reason ?? ""] ?? `Unavailable: ${activation?.reason}`}
        </p>
        {error ? <p role="alert" className="status err">{error}</p> : null}
        {uncertain && <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Check saved consent</button>
        </div>}
        {state.identity && <dl className="kv">
          <dt>Saved revision</dt><dd className="mono">{state.identity.publication_revision_id}</dd>
          <dt>Execution identity</dt><dd className="mono">{state.identity.execution_revision_id}</dd>
          <dt>Wallet</dt><dd className="mono">{state.identity.wallet_id}</dd>
          <dt>Network</dt><dd>{state.identity.network_id}</dd>
        </dl>}

        {state.adoptions.length === 0 && !shown && assets && <fieldset style={{ border: 0, padding: 0 }}>
          <legend><h3 style={{ margin: 0 }}>Terms to review</h3></legend>
          <p className="muted">Whole base units. Unlike assets are never added together.</p>
          {LIMITS.map((item) => <div key={item.key}>
            <label htmlFor={`limit-${item.key}-${agentId}`}>{item.label} ({assets[item.asset].decimals} decimals)</label>
            <input id={`limit-${item.key}-${agentId}`} className="input" inputMode="numeric" style={{ minHeight: 44 }}
              value={limits[item.key]} onChange={(event) => setLimits({ ...limits, [item.key]: event.target.value.trim() })} />
            <span className="muted">{/^\d+$/.test(limits[item.key]) ? formatRaw(limits[item.key], assets[item.asset].decimals) : ""}</span>
          </div>)}
          <label htmlFor={`limit-attempts-${agentId}`}>Economic attempts</label>
          <input id={`limit-attempts-${agentId}`} className="input" inputMode="numeric" style={{ minHeight: 44 }} value={attempts}
            onChange={(event) => setAttempts(event.target.value.trim())} />
          <label htmlFor={`limit-expiry-${agentId}`}>Expiry (UTC)</label>
          <input id={`limit-expiry-${agentId}`} className="input" style={{ minHeight: 44 }} value={expiry}
            onChange={(event) => setExpiry(event.target.value.trim())} />
          <div className="btn-row">
            <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={!valid || busy || uncertain}
              onClick={() => void write(async () => { const t = terms(); if (t) setReview(await financial.review(agentId, t)); })}>
              {busy ? "Saving…" : "Review exact terms"}
            </button>
          </div>
        </fieldset>}

        {shown && <ReviewSummary review={shown} />}
        {shown && state.adoptions.length === 0 && <div className="btn-row">
          <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={busy || uncertain}
            onClick={() => void write(() => financial.adopt(agentId, shown.review_id, shown.review_hash))}>
            {busy ? "Adopting…" : "Adopt these exact terms (inactive)"}
          </button>
        </div>}
        {state.adoptions.map((adoption) => <p key={adoption.adoption_id} data-testid="consent-adopted">
          Adopted, status {adoption.status} · consent <span className="mono">{adoption.consent_hash}</span>
        </p>)}
      </>}
    </section>
  );
}

function ReviewSummary({ review }: { review: ConsentReview }) {
  const terms = review.content.terms;
  return (
    <div data-testid="consent-review">
      <h3>Reviewed terms</h3>
      <dl className="kv">
        <dt>Review hash</dt><dd className="mono">{review.review_hash}</dd>
        <dt>Purpose</dt><dd>{terms.operating_purpose}{terms.trial_objective ? ` — ${terms.trial_objective}` : ""}</dd>
        {terms.allocation.map((amount) => <div key={`alloc-${amount.asset_id}`}><dt>Allocation</dt>
          <dd>{formatRaw(amount.raw, amount.decimals)} <span className="mono">{amount.asset_id}</span></dd></div>)}
        {terms.allowances.map((term) => <div key={term.name}><dt>{term.name}</dt>
          <dd>{formatRaw(term.amount.raw, term.amount.decimals)} <span className="mono">{term.amount.asset_id}</span></dd></div>)}
        {terms.gas_budget && <><dt>Gas budget</dt><dd>{formatRaw(terms.gas_budget.raw, terms.gas_budget.decimals)} MON</dd></>}
        <dt>Attempts</dt><dd>{terms.attempt_budget}</dd>
        <dt>Expiry</dt><dd><time dateTime={terms.expiry}>{terms.expiry}</time></dd>
        <dt>Actions</dt><dd>{terms.supported_actions.join(", ")}</dd>
        <dt>Route</dt><dd>{terms.route.adapter} (unqualified)</dd>
        <dt>Evidence</dt><dd>{terms.evidence.status}</dd>
        <dt>Stop effects</dt><dd>{terms.stop_effects.join("; ")}</dd>
      </dl>
      {review.content.unknowns && review.content.unknowns.length > 0 &&
        <p className="muted">Unknown at review: {review.content.unknowns.join(", ")}</p>}
    </div>
  );
}
