"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
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
  const preparedBinding = useRef<string | null>(null);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const saved = await financial.consent(agentId);
      if (current !== seq.current) return false;
      if (saved.controlled_action && preparedBinding.current !== saved.controlled_action.binding_sha256) {
        const action = saved.controlled_action;
        preparedBinding.current = action.binding_sha256;
        setLimits((previous) => ({ ...previous, allocation: action.input.raw, quote_input: action.input.raw,
          per_action_gas: action.gas.budget_raw }));
        setExpiry(action.expires_at); setAttempts("2");
      }
      setState(saved); setPhase("loaded"); setUncertain(false); setError("");
      return true;
    } catch (failure) {
      if (current !== seq.current) return false;
      setPhase("error"); setError(failure instanceof ApiError ? failure.detail : "Saved consent could not be loaded.");
      return false;
    }
  }, [agentId]);

  useEffect(() => { setPhase("loading"); void load(); }, [load]);

  const assets = state?.assets;
  const controlledMode = state?.provider_mode === "controlled";
  const controlled = controlledMode ? state?.controlled_action : null;
  const valid = LIMITS.every((item) => /^(0|[1-9][0-9]*)$/.test(limits[item.key])) && /^\d{1,7}$/.test(attempts)
    && !Number.isNaN(Date.parse(expiry)) && (!controlledMode || Boolean(controlled));

  const terms = (): ReviewedTerms | null => {
    if (!assets) return null;
    const amount = (asset: "quote" | "base" | "gas", raw: string) => ({ ...assets[asset], raw });
    const named = (key: LimitKey) => LIMITS.find((item) => item.key === key)!;
    return {
      terms_version: controlled ? "connected-one-action/1" : "connected-spot/1", operating_purpose: "TRIAL",
      trial_objective: "Observe one bounded action through the application.",
      allocation: [amount("quote", limits.allocation)],
      allowances: (["quote_input", "base_inventory", "per_action_gas", "per_exit_gas"] as const)
        .map((key) => ({ name: key, amount: amount(named(key).asset, limits[key]) })),
      attempt_budget: Number(attempts), gas_budget: amount("gas", limits.gas_budget), expiry,
      supported_actions: controlled ? ["ENTRY"] : ["ENTRY", "EXIT"], supported_assets: [assets.quote.asset_id, assets.base.asset_id],
      supported_routes: ["KURU_FLOW_FIXED_INPUT"], route: controlled
        ? { adapter: "KURU_FLOW_FIXED_INPUT", identity_state: "KNOWN", identity: controlled.entrypoint }
        : { adapter: "KURU_FLOW_FIXED_INPUT" },
      ...(controlled ? { signer: controlled.signer_id, policy: { policy_id: controlled.policy_id,
        status: "UNQUALIFIED" as const, content_sha256: controlled.policy_content_sha256 } } : {}),
      evidence: { status: "HYPOTHESIS", source: "saved-research" },
      stop_effects: [controlled ? "STOP_NEW_ENTRIES denies the controlled entry; held funds stay"
        : "STOP_NEW_ENTRIES denies new entries and keeps approved exits",
        "HALT_ALL_SWAPS denies every swap; pending actions and holdings stay"],
    };
  };

  const write = async (action: () => Promise<unknown>) => {
    if (busy || uncertain) return;
    setBusy(true); setError("");
    try {
      await action();
      if (!(await load())) {
        // Saved, but not read back: keep every write blocked until a read shows the current saved state.
        setUncertain(true); setPhase("loaded"); // keep the last saved view on screen, clearly marked unconfirmed
        setError("The change was saved, but the current consent could not be read. Check the saved consent before you continue.");
      }
    }
    catch (failure) {
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 500) setError(failure.detail);
      else { setUncertain(true); setError("The outcome is not confirmed. Check the saved consent before repeating it."); }
    } finally { setBusy(false); }
  };

  const activation = state?.activation;
  const shown = review ?? state?.reviews[0] ?? null;
  return (
    <section className="panel" aria-label="Agent authority" style={{ overflowWrap: "anywhere" }}>
      <h2>Bounded authority</h2>
      {phase === "loading" && <p role="status" className="muted">Loading saved consent…</p>}
      {phase === "error" && <div role="alert"><p>{error}</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Try again</button></div>}
      {state && <>
        <p>Adopting terms saves an <strong>inactive</strong> consent. It never signs, moves funds or grants wallet permission by itself.</p>
        <p data-testid="activation-state" role="status">
          {activation?.state === "FIXTURE_QUALIFIED"
            ? `Fixture qualification (${activation.evidence_class}). Bounded fixture actions can run under these exact terms; this is not live authority.`
            : activation?.state === "CONTROLLED_QUALIFIED"
            ? `One controlled action is qualified (${activation.evidence_class}) under its exact release. Exit and recurring execution are unavailable.`
            : ACTIVATION_COPY[activation?.reason ?? ""] ?? `Unavailable: ${activation?.reason}`}
        </p>
        {controlledMode && !controlled && <p>No prepared controlled action is available. Exact terms cannot be reviewed yet.</p>}
        {controlled && <div data-testid="controlled-action-terms">
          <h3>One controlled entry</h3>
          <p>These are prepared terms. The activation status above determines whether they can run.</p>
          <dl className="kv">
            <dt>Input, raw</dt><dd>{controlled.input.raw} <span className="mono">{controlled.input.asset_id}</span></dd>
            <dt>Minimum output, raw</dt><dd>{controlled.minimum_output.raw} <span className="mono">{controlled.minimum_output.asset_id}</span></dd>
            <dt>Recipient</dt><dd className="mono">{controlled.recipient}</dd>
            <dt>Route</dt><dd className="mono">{controlled.entrypoint} · {controlled.method}</dd>
            <dt>Allowance, raw</dt><dd>{controlled.allowance_raw}</dd>
            <dt>Gas limits</dt><dd>{controlled.gas.gas_limit} gas · maximum {controlled.gas.max_fee_per_gas} wei per gas · priority {controlled.gas.max_priority_fee_per_gas} wei per gas · budget {controlled.gas.budget_raw} wei</dd>
            <dt>Fees</dt><dd>{controlled.fees.fee_bps} basis points; referral {controlled.fees.referrer_fee_bps} basis points; input-token fee: {controlled.fees.is_in_token_fee ? "yes" : "no"}</dd>
            <dt>Fee collector</dt><dd className="mono">{controlled.fees.fee_collector_address}</dd>
            <dt>Referrer</dt><dd className="mono">{controlled.fees.referrer_address}</dd>
            <dt>Expiry</dt><dd><time dateTime={controlled.expires_at}>{controlled.expires_at}</time></dd>
            <dt>Signer and policy</dt><dd className="mono">{controlled.signer_id} · {controlled.policy_id} · {controlled.policy_content_sha256}</dd>
            <dt>Release and evidence</dt><dd className="mono">{controlled.release_id} · {controlled.release_sha256} · {controlled.evidence_class}</dd>
          </dl>
          <div data-testid="release-limits">
            <h4>Release limits</h4>
            <dl className="kv">
              <dt>Fixed input</dt><dd>{formatRaw(controlled.input.raw, controlled.input.decimals)} <span className="mono">{controlled.input.asset_id}</span></dd>
              <dt>Minimum output</dt><dd>{formatRaw(controlled.minimum_output.raw, controlled.minimum_output.decimals)} <span className="mono">{controlled.minimum_output.asset_id}</span></dd>
              <dt>USD ceiling including gas</dt><dd>Not available</dd>
            </dl>
            <p className="muted">The server does not report a USD ceiling, so none is shown. No value is calculated in the browser.</p>
          </div>
          <p>Exit and recurring execution are unavailable. The exit gas and attempt reservations remain as protection for held inventory.</p>
        </div>}
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

        {state.adoptions.length === 0 && !shown && assets && <fieldset style={{ border: 0, padding: 0, minWidth: 0 }}>
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
        {terms.allocation.map((amount) => <Fragment key={`alloc-${amount.asset_id}`}><dt>Allocation</dt>
          <dd>{formatRaw(amount.raw, amount.decimals)} <span className="mono">{amount.asset_id}</span></dd></Fragment>)}
        {terms.allowances.map((term) => <Fragment key={term.name}><dt>{term.name}</dt>
          <dd>{formatRaw(term.amount.raw, term.amount.decimals)} <span className="mono">{term.amount.asset_id}</span></dd></Fragment>)}
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
