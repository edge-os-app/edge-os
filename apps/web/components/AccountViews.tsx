"use client";

import { useCallback, useEffect, useState } from "react";
import { getAccountView, loadAccountViews, type AccountViewRecord } from "../lib/account-views";
import { AgentRecords } from "./AgentRecords";
import { FundRecords } from "./FundRecords";
import { PositionRecords } from "./PositionRecords";

export type AccountViewName = "Agents" | "Positions" | "Funds";

export function AccountViews({ initialView = "Agents", sourceRecordId }: { initialView?: AccountViewName; sourceRecordId?: string }) {
  const [view, setView] = useState<AccountViewName>(initialView);
  const [records, setRecords] = useState<AccountViewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [moreError, setMoreError] = useState("");
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMoreError("");
    setRecords([]);
    setNextOffset(null);
    try {
      const page = await loadAccountViews();
      let nextRecords = page.records;
      if (sourceRecordId && !nextRecords.some((record) => record.record_id === sourceRecordId)) {
        const source = await getAccountView(sourceRecordId);
        nextRecords = [...nextRecords, source];
      }
      setRecords(nextRecords);
      setNextOffset(page.next_offset);
    } catch {
      setError("Account records could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [sourceRecordId]);

  useEffect(() => {
    if (!sourceRecordId || !records.length) return;
    const source = records.find((record) => record.record_id === sourceRecordId);
    if (!source) return;
    const kind = source.content.record_kind;
    setView(kind === "AGENT" || kind === "MONITORING" || kind === "PERMISSION_SNAPSHOT" ? "Agents"
      : kind === "CAPITAL_FLOW" || (kind === "ACTION" && !source.content.position_id) ? "Funds" : "Positions");
    const timer = window.setTimeout(() => {
      const target = document.getElementById(`record-${sourceRecordId}`);
      target?.closest("details")?.setAttribute("open", "");
      target?.scrollIntoView?.({ block: "center" });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [sourceRecordId, records]);

  const loadMore = async () => {
    if (nextOffset == null || loadingMore) return;
    setLoadingMore(true);
    setMoreError("");
    try {
      const page = await loadAccountViews({}, nextOffset);
      setRecords((current) => [...current, ...page.records]);
      setNextOffset(page.next_offset);
    } catch {
      setMoreError("More account records could not be loaded. Existing records remain unchanged.");
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => { void load(); }, [load, attempt]);

  return (
    <div className="stack">
      <h1>Account</h1>
      <p className="muted">Authored synthetic records. They do not show live wallets, balances, worker health, marks, or receipts.</p>
      <div aria-label="Account views" role="group" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {(["Agents", "Positions", "Funds"] as const).map((name) => (
          <button key={name} className={view === name ? "btn btn-primary" : "btn btn-secondary"}
            style={{ minHeight: 44, backgroundColor: view === name ? "var(--color-accent-800)" : "var(--color-neutral-100)",
              color: view === name ? "var(--color-neutral-100)" : "var(--color-text)" }}
            type="button" aria-pressed={view === name}
            onClick={() => setView(name)}>{name}</button>
        ))}
      </div>
      {loading && <p role="status" aria-live="polite">Loading saved account records…</p>}
      {!loading && error && <section className="panel" role="alert">
        <p>{error} Existing records remain unchanged.</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => setAttempt((value) => value + 1)}>Try again</button>
      </section>}
      {!loading && !error && view === "Agents" && <AgentRecords records={records} />}
      {!loading && !error && view === "Positions" && <PositionRecords records={records} />}
      {!loading && !error && view === "Funds" && <FundRecords records={records} />}
      {!loading && !error && <p className="muted">Account summaries do not pool wallet balances or permission. Account value, percent return, and drawdown are unavailable.</p>}
      {!loading && !error && nextOffset != null && <div>
        {moreError && <p role="alert">{moreError}</p>}
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          {loadingMore ? "Loading more…" : "Load more records"}
        </button>
      </div>}
    </div>
  );
}
