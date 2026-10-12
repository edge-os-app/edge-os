"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { financial, formatRaw, heldKey, releaseKey, type ActionDetail, type AgentActions as AgentActionsView,
  type Removal, type Stop } from "../lib/financial";

const JOB_COPY: Record<string, string> = {
  QUEUED: "Saved. Waiting for the bounded worker to evaluate it.",
  DECIDED: "Decision saved. Waiting to admit the one action it allows.",
  ENQUEUED: "Admitted. Waiting for submission checks.",
  SUBMITTED: "The original action's outcome is not settled. Reconcile it before anything new runs for this wallet.",
  COMPLETED: "Finished.",
  UNAVAILABLE: "Unavailable. Nothing was submitted.",
};

const UNSETTLED = new Set(["SUBMITTED_UNKNOWN", "CLAIMED", "BREACHED", "RECONCILE_MISMATCH"]);

/** Bounded evaluations, the original action's lineage and recovery, and the owner's stop and removal controls. */
export function AgentActions({ agentId }: { agentId: string }) {
  const [view, setView] = useState<AgentActionsView | null>(null);
  const [stops, setStops] = useState<Stop[]>([]);
  const [removals, setRemovals] = useState<Removal[]>([]);
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [phase, setPhase] = useState<"loading" | "loaded" | "missing" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const [saved, savedStops, savedRemovals] = await Promise.all([
        financial.actions(agentId), financial.stops(agentId), financial.removals(agentId)]);
      if (current !== seq.current) return;
      setView(saved); setStops(savedStops.stops); setRemovals(savedRemovals.removals);
      setPhase("loaded"); setUncertain(false); setError("");
    } catch (failure) {
      if (current !== seq.current) return;
      if (failure instanceof ApiError && failure.status === 404) setPhase("missing");
      else { setPhase("error"); setError(failure instanceof ApiError ? failure.detail : "Saved actions could not be loaded."); }
    }
  }, [agentId]);

  useEffect(() => { setPhase("loading"); void load(); }, [load]);

  const openAction = useCallback(async (actionId: string) => {
    try { setDetail(await financial.action(actionId)); }
    catch { setError("The saved action could not be loaded."); }
  }, []);

  const write = async (action: () => Promise<unknown>, done: string, after?: () => void) => {
    if (busy || uncertain) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await action();
      after?.();
      setNotice(done);
      await load();
      if (detail) await openAction(detail.action_id);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 500) setError(failure.detail);
      else if (failure instanceof ApiError && failure.status === 503) setError(failure.detail);
      else { setUncertain(true); setError("The outcome is not confirmed. Check the saved actions before repeating it."); }
    } finally { setBusy(false); }
  };

  const latestRemoval = removals[removals.length - 1];
  const blocked = busy || uncertain;
  return (
    <section className="panel" aria-label="Agent actions">
      <h2>Bounded actions</h2>
      {phase === "loading" && <p role="status" className="muted">Loading saved actions…</p>}
      {phase === "missing" && <p>No confirmed wallet is saved for this agent. Set up the agent wallet first.</p>}
      {phase === "error" && <div role="alert"><p>{error}</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Try again</button></div>}
      {view && <>
        <p className="muted" data-testid="actions-mode">{view.provider_mode === "fixture"
          ? "Authored fixture market, quotes, transport and receipts. No transaction is signed or sent."
          : "No qualified execution route exists in this build. Evaluations end unavailable and nothing is submitted."}</p>
        <p>Each run evaluates the saved rules once for the current five-minute slot. It is not continuous trading.</p>
        {error ? <p role="alert" className="status err">{error}</p> : null}
        {notice ? <p role="status" className="status">{notice}</p> : null}
        {uncertain && <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Check saved actions</button>
          <span className="muted">The last request is unconfirmed. New requests stay paused until this read succeeds.</span>
        </div>}
        {view.blocking_reason && <p className="status err" data-testid="actions-blocking">Blocked: {view.blocking_reason}</p>}
        <div className="btn-row">
          <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={blocked}
            onClick={() => void write(() => financial.schedule(agentId, heldKey("evaluation", agentId)),
              "Evaluation saved. The bounded worker runs it from saved state.", () => releaseKey("evaluation", agentId))}>
            {busy ? "Saving…" : "Run one bounded evaluation"}
          </button>
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy} onClick={() => void load()}>Refresh</button>
        </div>

        <h3>Evaluations</h3>
        {!view.jobs.length && <p className="muted">No evaluations yet.</p>}
        <ul data-testid="actions-jobs">{[...view.jobs].reverse().map((job) => <li key={job.job_id}>
          <strong>{job.state}</strong>{job.outcome ? ` · ${job.outcome}` : ""}{job.reason ? ` · ${job.reason}` : ""} · slot <time dateTime={job.decision_slot}>{job.decision_slot}</time>
          <p className="muted">{JOB_COPY[job.state] ?? job.state}</p>
          {job.action_id && <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button"
            onClick={() => void openAction(job.action_id!)}>Open action {job.action_id}</button>}
        </li>)}</ul>

        {view.positions.length > 0 && <>
          <h3>Positions</h3>
          <ul data-testid="actions-positions">{view.positions.map((position) => <li key={position.position_id}>
            <span className="mono">{position.position_id}</span>: {formatRaw(position.inventory_raw, position.decimals)} base units held (residual inventory stays yours after a stop or removal)
          </li>)}</ul>
        </>}

        {detail && <ActionLineage detail={detail} busy={blocked}
          onReconcile={() => void write(() => financial.reconcileAction(detail.action_id),
            "Reconciliation read the original action's receipt. No new action was created.")} />}

        <h3>Stop</h3>
        <p className="muted">A stop denies new work for this wallet. It does not sell, withdraw or cancel an action already sent.</p>
        <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={blocked}
            onClick={() => void write(() => financial.stop(agentId, "STOP_NEW_ENTRIES"), "New entries are stopped.")}>Stop new entries</button>
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={blocked}
            onClick={() => void write(() => financial.stop(agentId, "HALT_ALL_SWAPS"), "All swaps are halted.")}>Halt all swaps</button>
        </div>
        <ul data-testid="actions-stops">{stops.map((stop) => <li key={stop.stop_id}>{stop.mode} · {stop.scope} · <time dateTime={stop.created_at}>{stop.created_at}</time></li>)}</ul>

        <h3>Remove agent</h3>
        <p className="muted">Removal withdraws the agent's signer. A requested removal denies new submissions at once. You keep access to the wallet and its holdings.</p>
        {!latestRemoval ? <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={blocked}
          onClick={() => void write(() => financial.requestRemoval(agentId, heldKey("removal", agentId), "Owner removed the agent"),
            "Removal requested. New submissions are denied.")}>Request removal</button>
          : <div data-testid="actions-removal">
              <p>Removal {latestRemoval.state}{latestRemoval.evidenced_signer ? ` · signer ${latestRemoval.evidenced_signer}` : ""}</p>
              {latestRemoval.state !== "CONFIRMED" && <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button"
                disabled={blocked} onClick={() => void write(() => financial.reconcileRemoval(agentId), "Removal status checked.")}>
                Check removal status</button>}
            </div>}
      </>}
    </section>
  );
}

function ActionLineage({ detail, busy, onReconcile }: { detail: ActionDetail; busy: boolean; onReconcile: () => void }) {
  const references = detail.attempts[0]?.content.original_references;
  const unsettled = detail.queue ? UNSETTLED.has(detail.queue.state) : false;
  return (
    <div data-testid="action-lineage">
      <h3>Action {detail.action_id}</h3>
      <dl className="kv">
        <dt>Operation</dt><dd>{detail.operation}</dd>
        <dt>Decision</dt><dd>{detail.decision.status} at <time dateTime={detail.decision.decision_at}>{detail.decision.decision_at}</time></dd>
        <dt>Execution revision</dt><dd className="mono">{detail.revision_id}</dd>
        <dt>Consent (mandate)</dt><dd className="mono">{detail.mandate_id}</dd>
        <dt>Quantity</dt><dd>{formatRaw(detail.payload.quantity.raw, detail.payload.quantity.decimals)} <span className="mono">{detail.payload.quantity.asset_id}</span></dd>
        {detail.payload.input.quote_input && <><dt>Trading input</dt>
          <dd>{formatRaw(detail.payload.input.quote_input.raw, detail.payload.input.quote_input.decimals)} <span className="mono">{detail.payload.input.quote_input.asset_id}</span></dd></>}
        <dt>Admission</dt><dd>{detail.admission.map((item) => `${item.status}${item.reason ? ` (${item.reason})` : ""}`).join("; ")}</dd>
        <dt>Queue</dt><dd data-testid="action-queue-state">{detail.queue ? `${detail.queue.state}${detail.queue.blocking_reason ? ` (${detail.queue.blocking_reason})` : ""}` : "None"}</dd>
        <dt>Receipts</dt><dd data-testid="action-receipts">{detail.receipts.length ? detail.receipts.map((r) => `${r.outcome}${r.breach ? " (breach)" : ""}`).join(" → ") : "None yet"}</dd>
        <dt>Recovery</dt><dd>{detail.recovery ? detail.recovery.state : "Not opened"}</dd>
        <dt>Transaction hash</dt><dd className="mono">{references?.transaction_hash ?? `None (${references?.absent_reason ?? "not recorded"})`}</dd>
      </dl>
      <h4>Reservations</h4>
      <ul>{detail.reservations.map((item, index) => <li key={index}>{item.scope} · {formatRaw(item.raw, item.decimals)} <span className="mono">{item.asset_id}</span> · {item.state}</li>)}</ul>
      {unsettled && <div className="btn-row">
        <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={busy} onClick={onReconcile}>Reconcile original action</button>
        <span className="muted">Reads the original action's receipt. It never sends a replacement.</span>
      </div>}
    </div>
  );
}
