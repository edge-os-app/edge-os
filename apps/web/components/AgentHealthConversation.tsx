"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { agentHealth, ApiError, type AgentHealth, type HealthExplanation, type HealthField, type HealthSourceRef } from "../lib/api";

/** P31 LOCAL. The direct view and the conversation read one dated, read-only health snapshot of the newest deployment. */

const QUESTIONS = ["What did it last do?", "What is next?", "Why is it waiting?", "Is anything pending?",
  "Was it stopped or removed?", "What inventory is left?", "Did the revision change?", "What is unknown?"];

function show(field: HealthField | undefined): string {
  if (!field) return "Unknown";
  if (field.state === "UNKNOWN") return `Unknown (${field.reason})`;
  return field.value === null ? "None" : String(field.value);
}

function sourceText(ref: HealthSourceRef | null): string {
  return ref ? `${ref.time} (${ref.table} ${ref.id} ${ref.field})` : "No stored write";
}

function failureText(failure: unknown, fallback: string): string {
  return failure instanceof ApiError ? failure.detail : fallback;
}

function Facts({ health }: { health: AgentHealth }) {
  const evaluation = health.last_evaluation;
  const attempt = health.last_trade_attempt;
  const canonical = health.pending_reconciliation.canonical;
  const [recovery, monitoring] = health.pending_reconciliation.warnings;
  const wait = health.wait_reason;
  return (
    <dl className="kv">
      <dt>Stored as of</dt><dd data-testid="health-as-of">{sourceText(health.as_of)}</dd>
      <dt>Read at</dt><dd data-testid="health-read-at">{health.read_at} (silence and wait are values at this time)</dd>
      <dt>Recurring operation</dt>
      <dd>{health.deployment ? `${health.deployment.state}${health.deployment.end_reason ? ` (${health.deployment.end_reason}, ${health.deployment.ended_at})` : ""}` : "No deployment saved"}</dd>
      <dt>Last evaluation</dt>
      <dd data-testid="health-last-evaluation">{evaluation.state === "KNOWN" && evaluation.value.evaluation
        ? `Slot ${evaluation.value.decision_slot}: ${evaluation.value.evaluation.outcome}${evaluation.value.evaluation.reason ? ` (${evaluation.value.evaluation.reason})` : ""}; inputs observed ${show(evaluation.value.evaluation.inputs_observed_at)}, collected ${show(evaluation.value.evaluation.inputs_collected_at)}, evaluated ${show(evaluation.value.evaluation.evaluated_at)}. An evaluation is not a trade.`
        : show(evaluation)}</dd>
      <dt>Last trade attempt</dt>
      <dd data-testid="health-last-attempt">{attempt.state === "KNOWN" && attempt.value.submission
        ? `Action ${attempt.value.action_id}: ${attempt.value.submission.state}${attempt.value.submission.outcome ? ` ${attempt.value.submission.outcome}` : ""}, started ${show(attempt.value.submission.started_at)}, completed ${show(attempt.value.submission.completed_at)}`
        : show(attempt)}</dd>
      <dt>Next due slot</dt><dd data-testid="health-next">{show(health.producer.next_due_slot)}</dd>
      <dt>Last scheduler pass</dt><dd>{show(health.producer.last_tick_at)}</dd>
      <dt>Wait reason</dt><dd data-testid="health-wait">{wait.state === "KNOWN" && wait.value === null ? "None" : show(wait)}</dd>
      <dt>Pending reconciliation</dt>
      <dd data-testid="health-pending">{"action_ids" in canonical ? (canonical.action_ids.join(", ") || "None") + " (producer unsettled queue)" : `Unknown (${canonical.reason})`}</dd>
      <dt>Separate warnings</dt>
      <dd data-testid="health-warnings">{`${recovery.kind}: ${recovery.action_ids.join(", ") || "none"}; ${monitoring.kind}: ${monitoring.pending ? "present" : "not present"}`}</dd>
      <dt>Stops and removal</dt>
      <dd data-testid="health-controls">{[...health.controls.stops.map((s) => `${s.mode} on ${s.scope} since ${s.created_at}`),
        ...health.controls.removals.map((r) => `Removal ${r.state} (requested ${r.requested_at}, updated ${r.updated_at})`)].join("; ") || "None"}</dd>
      <dt>Residual inventory</dt>
      <dd data-testid="health-inventory">{health.residual_inventory.map((p) => `${p.position_id} ${p.position_state}: ${p.quantity.raw} raw ${p.quantity.asset_id}, last saved ${show(p.updated_at)}`).join("; ") || "No saved position"}</dd>
      <dt>Revision changed</dt><dd>{show(health.identity.changed)}</dd>
      <dt>Unknown inputs</dt>
      <dd data-testid="health-unknowns">{health.unknown_inputs.map((u) => `${u.field}: ${u.reason}`).join("; ")}</dd>
      <dt>Snapshot</dt><dd className="mono" data-testid="health-digest">{health.snapshot_digest}</dd>
    </dl>
  );
}

/** Direct view: the dated read-only health snapshot. It has no controls; stop, removal and end stay in their panels. */
export function AgentHealthPanel({ agentId }: { agentId: string }) {
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const load = useCallback(async () => {
    const current = (seq.current += 1);
    setLoading(true); setError("");
    try {
      const saved = await agentHealth.read(agentId);
      if (current === seq.current) setHealth(saved);
    } catch (failure) {
      if (current === seq.current) setError(failureText(failure, "Agent health could not be read."));
    } finally {
      if (current === seq.current) setLoading(false);
    }
  }, [agentId]);
  useEffect(() => { void load(); }, [load]);
  return (
    <section className="panel" aria-label="Agent health" style={{ overflowWrap: "anywhere" }}>
      <h2>Agent health</h2>
      {loading && !health && <p role="status" className="muted">Reading agent health…</p>}
      {error && <p role="alert" className="status err">{error}</p>}
      {health && <>
        <p className="muted">{health.notice}</p>
        <Facts health={health} />
      </>}
      <div className="btn-row">
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={loading} onClick={() => void load()}>Read again</button>
      </div>
    </section>
  );
}

type Reply = { question: string; explanation: HealthExplanation };

/** Read-only conversation about one agent's health. Each reply keeps the date of the snapshot it read. */
export function AgentHealthConversation({ agentId }: { agentId: string }) {
  const [replies, setReplies] = useState<Reply[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // The side panel and the sheet both render this conversation, so each copy needs its own field id.
  const fieldId = useId();
  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true); setError("");
    try {
      const explanation = await agentHealth.explain(agentId, text.slice(0, 500));
      setReplies((current) => [...current, { question: text, explanation }]);
      // Clear the field only when it still holds this question; text typed while it was answered stays.
      setDraft((current) => (current.trim() === text ? "" : current));
    } catch (failure) {
      setError(failureText(failure, "The question could not be answered. Earlier answers stay as they were."));
    } finally { setBusy(false); }
  };
  return (
    <>
      <div className="convo-about">
        <span className="eyebrow">About this agent</span>
        <p style={{ margin: "4px 0 0" }}><strong>{agentId}</strong><br />
          <span className="muted">Health of the newest recurring deployment</span></p>
      </div>
      <p className="muted" style={{ margin: 0 }}>Answers come only from saved records. Asking changes nothing, calls no provider and grants no
        permission. Stop, removal and end stay on the direct page.</p>
      <div className="btn-row" role="group" aria-label="Suggested questions">
        {QUESTIONS.map((question) => (
          <button key={question} className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
            onClick={() => void ask(question)}>{question}</button>
        ))}
      </div>
      <form className="stack" style={{ gap: 8 }} onSubmit={(event) => { event.preventDefault(); void ask(draft); }}>
        <label htmlFor={fieldId}>Ask about this agent's health</label>
        <input id={fieldId} className="input" value={draft} maxLength={500} style={{ minHeight: 44 }}
          onChange={(event) => setDraft(event.target.value)} />
        <div className="btn-row">
          <button className="btn btn-primary" style={{ minHeight: 44 }} type="submit" disabled={busy || !draft.trim()}>Ask</button>
        </div>
      </form>
      {error && <p role="alert" className="status err">{error}</p>}
      <div className="stack" role="log" aria-label="Health conversation" style={{ overflowWrap: "anywhere" }}>
        {replies.length === 0 && <p className="muted">No question asked yet.</p>}
        {replies.map(({ question, explanation }, index) => (
          <div key={`${explanation.read_at}-${index}`} className="stack" style={{ gap: 8 }} data-testid="health-reply"
            data-digest={explanation.snapshot_digest}>
            <div className="msg user"><span className="who">You asked</span>{question}</div>
            <div className="msg system"><span className="who">Saved records</span>
              {explanation.answer.map((line, row) => <p key={row} style={{ margin: "0 0 6px" }}>{line.text}</p>)}
              <p className="muted" style={{ margin: 0 }}>Read {explanation.read_at}. Stored as of {sourceText(explanation.as_of)}.
                Snapshot <span className="mono">{explanation.snapshot_digest}</span>.</p>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
