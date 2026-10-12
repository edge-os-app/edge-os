"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { financial, formatRaw, heldKey, peekKey, releaseKey, type FundingView } from "../lib/financial";

const MODE_COPY: Record<string, string> = {
  fixture: "Authored local fixture ports. Deposits and holdings here are not a wallet, a transfer or chain evidence.",
  unavailable: "Real deposit and holdings observation is unavailable in this build. Reviewed deposits stay pending and nothing is credited.",
};

/** Funding for one confirmed agent wallet: declared assets, reviewed deposits, credited deposits and current holdings. */
export function AgentFunding({ agentId }: { agentId: string }) {
  const [view, setView] = useState<FundingView | null>(null);
  const [phase, setPhase] = useState<"loading" | "loaded" | "missing" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [assetClass, setAssetClass] = useState<"TRADING" | "NATIVE_GAS">("TRADING");
  const [raw, setRaw] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const saved = await financial.funding(agentId);
      if (current !== seq.current) return false;
      // A reference the server already saved (for example after a lost reply) is released, so the next
      // reviewed deposit uses a fresh reference instead of colliding with the saved one.
      for (const kind of ["TRADING", "NATIVE_GAS"]) {
        const held = peekKey(`deposit-${kind}`, agentId);
        if (held && saved.flows.some((flow) => flow.reference === held)) releaseKey(`deposit-${kind}`, agentId);
      }
      setView(saved); setPhase("loaded"); setUncertain(false); setError("");
      return true;
    } catch (failure) {
      if (current !== seq.current) return false;
      if (failure instanceof ApiError && failure.status === 404) { setView(null); setPhase("missing"); }
      else { setPhase("error"); setError(failure instanceof ApiError ? failure.detail : "Funding could not be loaded."); }
      return false;
    }
  }, [agentId]);

  useEffect(() => { setPhase("loading"); void load(); }, [load]);

  /** A write. A lost reply leaves the outcome unknown: read the saved funding before offering another write. */
  const write = async (action: () => Promise<unknown>, after?: () => void, onRefused?: () => void) => {
    if (busy || uncertain) return;
    setBusy(true); setError("");
    try {
      await action();
      after?.();
      if (!(await load())) {
        // Saved, but not read back: keep every write blocked until a read shows the current saved state.
        setUncertain(true); setPhase("loaded"); // keep the last saved view on screen, clearly marked unconfirmed
        setError("The change was saved, but the current funding could not be read. Check the saved funding before you continue.");
      }
    } catch (failure) {
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 500) {
        setError(failure.detail);
        onRefused?.();
      } else {
        setUncertain(true);
        setError("The outcome is not confirmed. Check the saved funding before repeating the change.");
      }
    } finally { setBusy(false); }
  };

  const decimals = assetClass === "TRADING" ? view?.declaration?.trading_asset.decimals : view?.declaration?.gas_asset.decimals;
  const validRaw = /^(0|[1-9][0-9]*)$/.test(raw) && raw.length <= 78;

  return (
    <section className="panel" aria-label="Agent funding" style={{ overflowWrap: "anywhere" }}>
      <h2>Funding</h2>
      {phase === "loading" && <p role="status" className="muted">Loading saved funding…</p>}
      {phase === "missing" && <p>No confirmed wallet is saved for this agent. Set up the agent wallet first.</p>}
      {phase === "error" && <div role="alert"><p>{error}</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Try again</button></div>}
      {view && <>
        <p className="muted" data-testid="funding-mode">{MODE_COPY[view.provider_mode] ?? view.provider_mode}</p>
        <p>Deposits are capital flows, not trading results. Credited deposits are history; current holdings are observed separately and change after swaps and gas.</p>
        <dl className="kv">
          <dt>Agent wallet</dt><dd className="mono">{view.wallet_id}</dd>
          <dt>Network</dt><dd>{view.network_id}</dd>
        </dl>
        {error ? <p role="alert" className="status err">{error}</p> : null}
        {uncertain && <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
            onClick={() => void load()}>Check saved funding</button>
          <span className="muted">The last change is unconfirmed. New changes stay paused until this read succeeds.</span>
        </div>}

        {!view.declaration ? (
          <div>
            <h3>Declare funded assets</h3>
            <p>The trading asset is the saved revision's quote token. Native MON is gas only and is never trading capital.</p>
            <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={busy || uncertain}
              onClick={() => void write(() => financial.declare(agentId))}>{busy ? "Saving…" : "Declare trading and gas assets"}</button>
          </div>
        ) : (
          <>
            <h3>Declared assets</h3>
            <dl className="kv">
              <dt>Trading capital</dt><dd className="mono">{view.declaration.trading_asset.asset_id} ({view.declaration.trading_asset.decimals} decimals)</dd>
              <dt>Native gas</dt><dd className="mono">{view.declaration.gas_asset.asset_id} ({view.declaration.gas_asset.decimals} decimals)</dd>
            </dl>
            <h3>Review a deposit</h3>
            <p className="muted">A reviewed deposit records what you intend to send. It is not a sent or credited transfer.</p>
            <label htmlFor={`deposit-class-${agentId}`}>Asset</label>
            <select id={`deposit-class-${agentId}`} className="input" style={{ minHeight: 44 }} value={assetClass}
              onChange={(event) => setAssetClass(event.target.value as "TRADING" | "NATIVE_GAS")}>
              <option value="TRADING">Trading capital</option>
              <option value="NATIVE_GAS">Native MON gas</option>
            </select>
            <label htmlFor={`deposit-raw-${agentId}`}>Amount in base units ({decimals ?? "?"} decimals)</label>
            <input id={`deposit-raw-${agentId}`} className="input" inputMode="numeric" style={{ minHeight: 44 }} value={raw}
              aria-invalid={raw !== "" && !validRaw} onChange={(event) => setRaw(event.target.value.trim())} />
            {raw !== "" && validRaw && decimals !== undefined && <p className="muted">That is {formatRaw(raw, decimals)} units.</p>}
            {raw !== "" && !validRaw && <p className="status err">Use whole base units without signs, spaces or leading zeros.</p>}
            <div className="btn-row">
              <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={busy || uncertain || !validRaw}
                onClick={() => void write(() => financial.prepareDeposit(agentId, {
                  asset_class: assetClass, raw, reference: heldKey(`deposit-${assetClass}`, agentId) }),
                () => { releaseKey(`deposit-${assetClass}`, agentId); setRaw(""); },
                () => releaseKey(`deposit-${assetClass}`, agentId))}>
                {busy ? "Saving…" : "Save reviewed deposit"}
              </button>
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy || uncertain}
                onClick={() => void write(() => financial.reconcileDeposits(agentId))}>Check deposits</button>
            </div>
          </>
        )}

        <h3>Deposits</h3>
        {!view.flows.length && <p className="muted">No reviewed deposits.</p>}
        <ul data-testid="funding-flows">{view.flows.map((flow) => <li key={flow.flow_id}>
          {flow.state} · {formatRaw(flow.asset.raw, flow.asset.decimals)} <span className="mono">{flow.asset.asset_id}</span> · reference {flow.reference}
          {flow.transaction_reference && <> · observed event <span className="mono">{flow.transaction_reference}</span></>}
        </li>)}</ul>
        {view.deposit_balances.length > 0 && <dl className="kv" data-testid="funding-credited">
          {view.deposit_balances.map((balance) => <Fragment key={balance.asset_id}>
            <dt>{balance.asset_class === "TRADING" ? "Credited trading deposits" : balance.asset_class === "NATIVE_GAS" ? "Credited gas deposits" : balance.asset_class}</dt>
            <dd>{formatRaw(balance.credited_deposits.raw, balance.credited_deposits.decimals)} credited · {formatRaw(balance.pending_deposits.raw, balance.pending_deposits.decimals)} pending</dd>
          </Fragment>)}
        </dl>}

        <h3>Current holdings</h3>
        {view.current_holdings.state === "UNAVAILABLE"
          ? <p data-testid="funding-holdings">Current holdings are unavailable{view.current_holdings.reason && view.current_holdings.reason !== "HOLDINGS_UNAVAILABLE" ? ` (${view.current_holdings.reason})` : ""}. No balance is shown or assumed.</p>
          : <>{view.current_holdings.observed_at && <p className="muted" data-testid="funding-holdings-observation">
              Observed <time dateTime={view.current_holdings.observed_at}>{view.current_holdings.observed_at}</time>
              {view.current_holdings.block_number != null && ` at block ${view.current_holdings.block_number}`}
              {view.current_holdings.finality && ` (${view.current_holdings.finality})`}
              {view.current_holdings.wallet_address && <> for <span className="mono">{view.current_holdings.wallet_address}</span></>}
              {view.current_holdings.source && ` · ${view.current_holdings.source}`}</p>}
            <dl className="kv" data-testid="funding-holdings">{view.current_holdings.assets.map((asset) => <Fragment key={asset.asset_id}>
              <dt>{asset.asset_id === view.declaration?.trading_asset.asset_id ? "Trading asset"
                : asset.asset_id === view.declaration?.gas_asset.asset_id ? "Native gas" : "Acquired asset"}</dt>
              <dd>{formatRaw(asset.raw, asset.decimals)} <span className="mono">{asset.asset_id}</span> ({view.current_holdings.evidence_class})</dd>
            </Fragment>)}</dl></>}
        {view.allowances.length > 0 && <>
          <h3>Authority used</h3>
          <ul>{view.allowances.map((item) => <li key={item.asset_id}>
            <span className="mono">{item.asset_id}</span>: approved {formatRaw(item.approved_raw, item.decimals)}, consumed {formatRaw(item.consumed_raw, item.decimals)}, reserved {formatRaw(item.reserved_raw, item.decimals)}
          </li>)}</ul>
        </>}
      </>}
    </section>
  );
}
