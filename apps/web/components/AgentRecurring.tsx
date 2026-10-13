"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { financial, heldKey, releaseKey, type ConsentState, type RecurringProjection } from "../lib/financial";

const WAIT_COPY: Record<string, string> = {
  WAITING_RECONCILIATION: "Waiting: an earlier action's outcome is unknown. Its receipt is read before anything new runs for this wallet.",
  PRODUCER_NOT_SEEN: "Waiting: no scheduler pass was recorded in the last two slots. Nothing runs until one is.",
};

const END_COPY: Record<string, string> = {
  OWNER_ENDED: "You ended recurring operation.",
  CONSENT_EXPIRED: "The adopted terms expired.",
  CONSENT_CHANGED: "The adopted terms changed.",
  IDENTITY_CHANGED: "The agent's wallet or saved revision changed.",
  REMOVAL_REQUESTED: "Agent removal was requested.",
  ACTIVATION_UNAVAILABLE: "No qualified execution route exists in this build.",
};

function waitText(reason: string): string {
  if (reason.startsWith("ENDED:")) {
    const why = reason.slice(6);
    return `Ended: ${END_COPY[why] ?? why}`;
  }
  if (reason.startsWith("STOPPED:")) return `Stopped: ${reason.slice(8).replaceAll("_", " ").toLowerCase()} denies matching work.`;
  if (reason.startsWith("REMOVAL:")) return "Removal denies every new submission for this wallet.";
  return WAIT_COPY[reason] ?? reason;
}

/** Recurring operation for one agent: the explicit authorization and the durable scheduler record. */
export function AgentRecurring({ agentId }: { agentId: string }) {
  const [view, setView] = useState<RecurringProjection | null>(null);
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [phase, setPhase] = useState<"loading" | "loaded" | "missing" | "error">("loading");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const [saved, savedConsent] = await Promise.all([financial.deployment(agentId), financial.consent(agentId)]);
      if (current !== seq.current) return false;
      setView(saved); setConsent(savedConsent); setPhase("loaded"); setUncertain(false); setError("");
      return true;
    } catch (failure) {
      if (current !== seq.current) return false;
      if (failure instanceof ApiError && failure.status === 404) setPhase("missing");
      else { setPhase("error"); setError(failure instanceof ApiError ? failure.detail : "Recurring operation could not be loaded."); }
      return false;
    }
  }, [agentId]);

  useEffect(() => { setPhase("loading"); void load(); }, [load]);

  const write = async (action: () => Promise<unknown>, done: string, after?: () => void) => {
    if (busy || uncertain) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await action();
      after?.();
      if (!(await load())) {
        setUncertain(true); setPhase("loaded");
        setError("The change was saved, but recurring operation could not be read. Check it before you continue.");
        return;
      }
      setNotice(done);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status >= 400 && failure.status < 600 && failure.status !== 502 && failure.status !== 504) {
        setError(failure.detail);
      } else { setUncertain(true); setError("The outcome is not confirmed. Check recurring operation before repeating it."); }
    } finally { setBusy(false); }
  };

  const adoption = consent?.adoptions[consent.adoptions.length - 1];
  const qualified = consent?.activation.state === "FIXTURE_QUALIFIED";
  const deployment = view?.deployment ?? null;
  const producer = view?.producer;
  return (
    <section className="panel" aria-label="Recurring operation" style={{ overflowWrap: "anywhere" }}>
      <h2>Recurring operation</h2>
      {phase === "loading" && <p role="status" className="muted">Loading recurring operation…</p>}
      {phase === "missing" && <p>No confirmed wallet is saved for this agent. Set up the agent wallet first.</p>}
      {phase === "error" && <div role="alert"><p>{error}</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Try again</button></div>}
      {phase === "loaded" && <>
        <p className="muted">The scheduler evaluates the saved rules once per five-minute slot while you are away, and the worker
          runs only actions your adopted terms permit. Authored fixture data only: no transaction is signed or sent, and this is
          not live trading.</p>
        {error ? <p role="alert" className="status err">{error}</p> : null}
        {notice ? <p role="status" className="status">{notice}</p> : null}
        {uncertain && <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Check recurring operation</button>
          <span className="muted">The last request is unconfirmed. New requests stay paused until this read succeeds.</span>
        </div>}

        {!deployment && (!adoption ? <p data-testid="recurring-needs-terms">Adopt bounded terms for this agent first.</p>
          : !qualified ? <p data-testid="recurring-unavailable">Recurring operation is unavailable: {consent?.activation.reason ?? "no qualification"}.</p>
          : <div data-testid="recurring-activate">
              <p>Terms <span className="mono">{adoption.consent_hash}</span> (adopted <time dateTime={adoption.created_at}>{adoption.created_at}</time>).
                Their cumulative limits, expiry and stops apply to every slot; starting again never resets them.</p>
              <label className="choice"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />{" "}
                <span>I authorize repeated evaluations and the permitted actions under these exact terms while I am away.</span></label>
              <div className="btn-row">
                <button className="btn btn-primary" style={{ minHeight: 44 }} type="button" disabled={!confirmed || busy || uncertain}
                  onClick={() => void write(() => financial.activateDeployment(agentId, heldKey("deployment", agentId), adoption.consent_hash),
                    "Recurring operation started. The scheduler saves each slot's evaluation.", () => releaseKey("deployment", agentId))}>
                  {busy ? "Saving…" : "Start recurring operation"}</button>
              </div>
            </div>)}

        {deployment && <div data-testid="recurring-deployment" data-state={deployment.state}>
          <p data-testid="recurring-wait" role="status">{view?.wait_reason ? waitText(view.wait_reason)
            : `Active. Next slot ${producer?.next_due_slot ?? "not scheduled"}.`}</p>
          <dl className="kv">
            <dt>State</dt><dd>{deployment.state}{deployment.end_reason ? ` (${deployment.end_reason})` : ""}</dd>
            <dt>Started</dt><dd><time dateTime={deployment.activated_at}>{deployment.activated_at}</time></dd>
            <dt>Terms</dt><dd className="mono">{deployment.identity.consent_hash}</dd>
            <dt>Execution revision</dt><dd className="mono">{deployment.identity.execution_revision_id}</dd>
            <dt>Last scheduler pass</dt><dd data-testid="recurring-last-tick">{producer?.last_tick_at ?? "None yet"}</dd>
            <dt>Last saved slot</dt><dd>{producer?.cursor_slot ?? "None yet"}</dd>
            <dt>Next due slot</dt><dd data-testid="recurring-next">{producer?.next_due_slot ?? `None${producer?.no_next_reason ? ` (${producer.no_next_reason})` : ""}`}</dd>
            <dt>Missed slots</dt><dd data-testid="recurring-missed">{producer?.missed_slots ?? 0}{producer?.missed_intervals.length
              ? ` · latest ${producer.missed_intervals[producer.missed_intervals.length - 1].from} to ${producer.missed_intervals[producer.missed_intervals.length - 1].to}, not replayed` : ""}</dd>
            <dt>Pending reconciliation</dt><dd data-testid="recurring-pending">{view?.pending_reconciliation?.length ? view.pending_reconciliation.join(", ") : "None"}</dd>
          </dl>
          <h3>Saved slots</h3>
          {!view?.occurrences?.length && <p className="muted">No slot evaluated yet.</p>}
          <ul data-testid="recurring-occurrences">{(view?.occurrences ?? []).map((item) => <li key={item.job_id}>
            <strong>{item.decision_slot}</strong> · {item.evaluation ? `${item.evaluation.outcome}${item.evaluation.reason ? ` (${item.evaluation.reason})` : ""}` : "Not evaluated yet"}
            {item.outcome ? ` · ${item.outcome}` : ""}{item.reason ? ` · ${item.reason}` : ""}
            <p className="muted">
              {item.evaluation ? `Inputs observed ${item.evaluation.inputs_observed_at ?? "unknown"}, collected ${item.evaluation.inputs_collected_at ?? "unknown"}, evaluated ${item.evaluation.evaluated_at} (${item.evaluation.evidence_class ?? "no evidence class"}). ` : ""}
              {item.submission ? `Submission ${item.submission.state}${item.submission.outcome ? ` ${item.submission.outcome}` : ""}, started ${item.submission.started_at}${item.submission.completed_at ? `, completed ${item.submission.completed_at}` : ", not completed"}.` : "No submission."}
            </p>
          </li>)}</ul>
          {deployment.state === "ACTIVE" && <div className="btn-row">
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy || uncertain}
              onClick={() => void write(() => financial.endDeployment(agentId), "Recurring operation ended. Sent actions and held amounts stay as saved.")}>
              End recurring operation</button>
            <span className="muted">Ending does not sell, cancel a sent action or release unknown liability.</span>
          </div>}
          <div className="btn-row">
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy} onClick={() => void load()}>Refresh</button>
          </div>
        </div>}
      </>}
    </section>
  );
}
