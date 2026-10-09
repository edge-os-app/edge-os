"use client";

import { useCallback, useEffect, useState } from "react";
import { loadAccountViews, type AccountViewRecord } from "../lib/account-views";
import { AgentRecords } from "./AgentRecords";
import { FundRecords } from "./FundRecords";
import { PositionRecords } from "./PositionRecords";

type View = "Agents" | "Positions" | "Funds";

export function AccountViews({ initialView = "Agents" }: { initialView?: View }) {
  const [view, setView] = useState<View>(initialView);
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
      setRecords(page.records);
      setNextOffset(page.next_offset);
    } catch {
      setError("Account records could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

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
      <nav aria-label="Account views" role="tablist" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {(["Agents", "Positions", "Funds"] as const).map((name) => (
          <button key={name} className={view === name ? "btn btn-primary" : "btn btn-secondary"}
            style={{ minHeight: 44 }} type="button" role="tab" aria-selected={view === name}
            onClick={() => setView(name)}>{name}</button>
        ))}
      </nav>
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
