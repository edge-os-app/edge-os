"use client";

import { useState } from "react";
import { ApiError } from "../lib/api";
import { agentContextApi, resolveContextSource, type AgentContextRecord, type ContextEntry } from "../lib/account-views";

type ContextIntent =
  | { kind: "CORRECT"; expectedVersion: number; contextId: string; replacement: string }
  | { kind: "ADOPT"; expectedVersion: number; contextId: string }
  | { kind: "DISABLE"; expectedVersion: number }
  | { kind: "CLEAR"; expectedVersion: number };

function intentIsPresent(intent: ContextIntent, saved: AgentContextRecord): boolean {
  if (saved.memory_version <= intent.expectedVersion) return false;
  if (intent.kind === "DISABLE") return saved.state === "DISABLED";
  if (intent.kind === "CLEAR") return saved.state === "CLEARED";
  const entry = saved.entries.find((item) => item.context_id === intent.contextId);
  if (intent.kind === "ADOPT") return entry?.status === "ADOPTED";
  return entry?.kind === "CORRECTION" && entry.text === intent.replacement;
}

export function AgentContext({
  record,
  onChange,
  onClose,
}: {
  record: AgentContextRecord;
  onChange: (record: AgentContextRecord) => void;
  onClose: () => void;
}) {
  const [editing, setEditing] = useState<ContextEntry | null>(null);
  const [replacement, setReplacement] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [pendingIntent, setPendingIntent] = useState<ContextIntent | null>(null);
  const [notice, setNotice] = useState("");

  async function openSource(sourceId: string) {
    setSourceError("");
    try {
      const source = await resolveContextSource(sourceId);
      if (source.destination_type === "UNSUPPORTED" || !source.destination_record_id) {
        setSourceError(`This saved source type (${source.source_record_type}) has no supported detail view. Your context is unchanged.`);
        return;
      }
      if (source.destination_type === "RESEARCH") {
        window.location.hash = `#/research/${encodeURIComponent(source.destination_record_id)}?source=${encodeURIComponent(source.source_record_id)}`;
      } else {
        window.location.hash = `#/agents?record=${encodeURIComponent(source.destination_record_id)}`;
      }
    } catch {
      setSourceError("This source could not be verified or opened. Your saved context is unchanged. Try again.");
    }
  }

  async function save(intent: ContextIntent, action: () => Promise<AgentContextRecord>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      onChange(await action());
      setPendingIntent(null);
      setEditing(null);
      setConfirmClear(false);
    } catch (failure) {
      setPendingIntent(intent);
      if (!(failure instanceof ApiError) || failure.status === 0 || failure.status >= 500 || failure.code === "RECONCILE") {
        setError("The save outcome is not confirmed. Your intent is held; check saved context before another change.");
      } else if (failure.status === 409) {
        setError("Context changed before this save. Your draft is preserved; check saved context before another change.");
      } else {
        setError("The save was rejected. Your draft is still here; check the current saved version before another change.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function reconcile() {
    if (!pendingIntent) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await agentContextApi.get(record.agent_id);
      const applied = intentIsPresent(pendingIntent, saved);
      onChange(saved);
      setPendingIntent(null);
      if (applied) {
        setEditing(null);
        setConfirmClear(false);
        setNotice(`Saved context version ${saved.memory_version} contains the requested change. No repeat was sent.`);
      } else {
        setNotice(`Saved context version ${saved.memory_version} was checked. The pending change was not confirmed; review this version before choosing another action.`);
      }
    } catch {
      setError("Saved context could not be checked. The outcome remains uncertain; your draft and intent are still held.");
    } finally {
      setBusy(false);
    }
  }

  function edit(entry: ContextEntry) {
    setEditing(entry);
    setReplacement(entry.text);
  }

  return (
    <section className="panel" aria-label={`${record.agent_id} context`}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h3>Agent context · version {record.memory_version}</h3>
        <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" onClick={onClose}>Close context</button>
      </div>
      <p><strong>State.</strong> {record.state}. Suggestions need your approval before a task can use them.</p>
      <p className="muted">Context cannot change strategy rules, permission, balances, positions, reservations, or pending actions. Clearing it does not remove financial history.</p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {sourceError && <p role="alert">{sourceError}</p>}
      {pendingIntent && <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
        onClick={() => void reconcile()}>{busy ? "Checking saved context…" : "Check saved context"}</button>}
      {!record.entries.length && <p>No saved context entries.</p>}
      <ul>
        {record.entries.map((entry) => (
          <li key={entry.context_id}>
            <p><strong>{entry.status === "SUGGESTED" ? "Suggested lesson" : entry.kind}</strong> · {entry.status}</p>
            <p>{entry.text}</p>
            {entry.source_refs.map((source) => <button key={source} className="btn btn-ghost"
              style={{ minHeight: 44 }} type="button" onClick={() => void openSource(source)}>Open source record</button>)}
            {entry.status === "SUGGESTED" ? (
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy || Boolean(pendingIntent)}
                onClick={() => void save({ kind: "ADOPT", expectedVersion: record.memory_version, contextId: entry.context_id },
                  () => agentContextApi.adopt(record.agent_id, record.memory_version, entry.context_id))}>
                Adopt suggestion
              </button>
            ) : (
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy || Boolean(pendingIntent)}
                onClick={() => edit(entry)}>Correct context</button>
            )}
            {editing?.context_id === entry.context_id && (
              <form onSubmit={(event) => {
                event.preventDefault();
                void save({ kind: "CORRECT", expectedVersion: record.memory_version, contextId: entry.context_id, replacement },
                  () => agentContextApi.correct(record.agent_id, record.memory_version, entry.context_id, replacement));
              }}>
                <label htmlFor="context-correction">Corrected context</label>
                <textarea id="context-correction" className="input" rows={3} value={replacement}
                  onChange={(event) => setReplacement(event.target.value)} required maxLength={2000} />
                <button className="btn btn-primary" style={{ minHeight: 44 }} type="submit" disabled={busy || Boolean(pendingIntent) || !replacement.trim()}>
                  Save correction
                </button>
                <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" disabled={busy} onClick={() => setEditing(null)}>
                  Cancel correction
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
      {record.state === "ACTIVE" && (
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy || Boolean(pendingIntent)}
          onClick={() => void save({ kind: "DISABLE", expectedVersion: record.memory_version },
            () => agentContextApi.disable(record.agent_id, record.memory_version))}>
          Disable future context
        </button>
      )}
      {record.state !== "CLEARED" && !confirmClear && (
        <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" disabled={busy}
          onClick={() => setConfirmClear(true)}>Clear context</button>
      )}
      {confirmClear && (
        <div role="group" aria-label="Confirm clear context">
          <p>Clear saved context for future tasks? Financial history, reservations, pending actions, and permission stay unchanged.</p>
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy || Boolean(pendingIntent)}
            onClick={() => void save({ kind: "CLEAR", expectedVersion: record.memory_version },
              () => agentContextApi.clear(record.agent_id, record.memory_version))}>Confirm clear</button>
          <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" disabled={busy}
            onClick={() => setConfirmClear(false)}>Keep context</button>
        </div>
      )}
    </section>
  );
}
