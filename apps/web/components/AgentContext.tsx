"use client";

import { useState } from "react";
import { agentContextApi, type AgentContextRecord, type ContextEntry } from "../lib/account-views";

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

  async function save(action: () => Promise<AgentContextRecord>) {
    setBusy(true);
    setError("");
    try {
      onChange(await action());
      setEditing(null);
      setConfirmClear(false);
    } catch {
      setError("Context was not updated. Reload it and check the current version.");
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
      {!record.entries.length && <p>No saved context entries.</p>}
      <ul>
        {record.entries.map((entry) => (
          <li key={entry.context_id}>
            <p><strong>{entry.status === "SUGGESTED" ? "Suggested lesson" : entry.kind}</strong> · {entry.status}</p>
            <p>{entry.text}</p>
            {entry.source_refs.map((source) => <a key={source} href={`#record-${encodeURIComponent(source)}`}>Open source record</a>)}
            {entry.status === "SUGGESTED" ? (
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
                onClick={() => void save(() => agentContextApi.adopt(record.agent_id, record.memory_version, entry.context_id))}>
                Adopt suggestion
              </button>
            ) : (
              <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
                onClick={() => edit(entry)}>Correct context</button>
            )}
            {editing?.context_id === entry.context_id && (
              <form onSubmit={(event) => {
                event.preventDefault();
                void save(() => agentContextApi.correct(record.agent_id, record.memory_version, entry.context_id, replacement));
              }}>
                <label htmlFor="context-correction">Corrected context</label>
                <textarea id="context-correction" className="input" rows={3} value={replacement}
                  onChange={(event) => setReplacement(event.target.value)} required maxLength={2000} />
                <button className="btn btn-primary" style={{ minHeight: 44 }} type="submit" disabled={busy || !replacement.trim()}>
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
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
          onClick={() => void save(() => agentContextApi.disable(record.agent_id, record.memory_version))}>
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
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={busy}
            onClick={() => void save(() => agentContextApi.clear(record.agent_id, record.memory_version))}>Confirm clear</button>
          <button className="btn btn-ghost" style={{ minHeight: 44 }} type="button" disabled={busy}
            onClick={() => setConfirmClear(false)}>Keep context</button>
        </div>
      )}
    </section>
  );
}
