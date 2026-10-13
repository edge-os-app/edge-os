"use client";

import { useCallback, useEffect, useState } from "react";
import { getAccountView, loadAccountViews, type AccountViewRecord, type PositionFilters } from "../lib/account-views";
import { AgentActions } from "./AgentActions";
import { AgentAuthority } from "./AgentAuthority";
import { AgentFunding } from "./AgentFunding";
import { AgentRecords } from "./AgentRecords";
import { AgentRecurring } from "./AgentRecurring";
import { FundRecords } from "./FundRecords";
import { PositionRecords } from "./PositionRecords";
import { ServiceAccountState } from "./ServiceAccountState";

export type AccountViewName = "Agents" | "Positions" | "Funds";

function mergeAccountRecords(...groups: AccountViewRecord[][]): AccountViewRecord[] {
  const byId = new Map<string, AccountViewRecord>();
  for (const record of groups.flat()) if (!byId.has(record.record_id)) byId.set(record.record_id, record);
  return [...byId.values()];
}

function relatedQueries(source: AccountViewRecord): PositionFilters[] {
  const item = source.content;
  switch (item.record_kind) {
    case "ACTION":
      return item.position_id ? [{ record_kind: "POSITION", agent_id: item.agent_id, wallet_id: item.wallet_id ?? undefined,
        network_id: item.network_id ?? undefined, asset_id: item.asset_id ?? undefined,
        position_id: item.position_id, strategy_revision: item.strategy_revision ?? undefined }]
        : item.flow_id ? [{ record_kind: "CAPITAL_FLOW", agent_id: item.agent_id, wallet_id: item.wallet_id ?? undefined,
          network_id: item.network_id ?? undefined, flow_id: item.flow_id }] : [];
    case "POSITION":
      return [{ record_kind: "ACTION", agent_id: item.agent_id, wallet_id: item.wallet_id ?? undefined,
        network_id: item.network_id ?? undefined, asset_id: item.asset_id ?? undefined,
        position_id: item.position_id ?? undefined, strategy_revision: item.strategy_revision ?? undefined }];
    case "CAPITAL_FLOW":
      return [{ record_kind: "ACTION", agent_id: item.agent_id, wallet_id: item.wallet_id ?? undefined,
        network_id: item.network_id ?? undefined, flow_id: item.flow_id ?? undefined }];
    case "EDGE_EVIDENCE":
      return [{ record_kind: "POSITION", agent_id: item.agent_id, strategy_revision: item.strategy_revision ?? undefined }];
    case "AGENT":
    case "MONITORING":
    case "PERMISSION_SNAPSHOT":
      return ["AGENT", "MONITORING", "PERMISSION_SNAPSHOT"].filter((kind) => kind !== item.record_kind)
        .map((kind) => ({ record_kind: kind as PositionFilters["record_kind"], agent_id: item.agent_id, wallet_id: item.wallet_id ?? undefined,
          network_id: item.network_id ?? undefined }));
  }
}

function relatedRecordMatches(source: AccountViewRecord, candidate: AccountViewRecord): boolean {
  if (candidate.owner_id !== source.owner_id) return false;
  const item = source.content;
  const row = candidate.content;
  if (item.record_kind === "ACTION" && item.position_id && row.record_kind === "POSITION") return row.agent_id === item.agent_id
    && row.wallet_id === item.wallet_id && row.network_id === item.network_id && row.asset_id === item.asset_id
    && row.position_id === item.position_id && row.strategy_revision === item.strategy_revision
    && row.mandate_id === item.mandate_id;
  if (item.record_kind === "POSITION" && row.record_kind === "ACTION") return row.agent_id === item.agent_id
    && row.wallet_id === item.wallet_id && row.network_id === item.network_id && row.asset_id === item.asset_id
    && row.position_id === item.position_id && row.strategy_revision === item.strategy_revision
    && row.mandate_id === item.mandate_id;
  if (item.record_kind === "CAPITAL_FLOW" && row.record_kind === "ACTION") return row.agent_id === item.agent_id
    && row.wallet_id === item.wallet_id && row.network_id === item.network_id && row.position_id == null
    && row.flow_id === item.flow_id;
  if (item.record_kind === "ACTION" && !item.position_id && row.record_kind === "CAPITAL_FLOW") return row.agent_id === item.agent_id
    && row.wallet_id === item.wallet_id && row.network_id === item.network_id && row.flow_id === item.flow_id;
  if (item.record_kind === "EDGE_EVIDENCE" && row.record_kind === "POSITION") return row.agent_id === item.agent_id
    && row.strategy_revision === item.strategy_revision;
  return row.agent_id === item.agent_id && row.wallet_id === item.wallet_id && row.network_id === item.network_id;
}

const AGENT_ID = /^[A-Za-z0-9_-]{1,64}$/;

/** One confirmed agent's saved services: authority on Agents, funding on Funds, actions on Positions. */
function ConnectedAgent({ view, agentId }: { view: AccountViewName; agentId?: string }) {
  const [draft, setDraft] = useState(agentId ?? "");
  const [selected, setSelected] = useState(agentId ?? "");
  useEffect(() => { setDraft(agentId ?? ""); setSelected(agentId ?? ""); }, [agentId]);
  const open = () => {
    if (!AGENT_ID.test(draft)) return;
    setSelected(draft);
    window.location.hash = `#/${view.toLowerCase()}?agent=${encodeURIComponent(draft)}`;
  };
  return (
    <section className="stack" aria-label="Connected agent">
      <form className="btn-row" onSubmit={(event) => { event.preventDefault(); open(); }}>
        <label htmlFor="connected-agent">Agent ID</label>
        <input id="connected-agent" className="input" value={draft} maxLength={64} style={{ minHeight: 44 }}
          aria-invalid={draft !== "" && !AGENT_ID.test(draft)} onChange={(event) => setDraft(event.target.value)} />
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="submit" disabled={!AGENT_ID.test(draft)}>Open agent</button>
      </form>
      {selected && view === "Agents" && <AgentAuthority key={selected} agentId={selected} />}
      {selected && view === "Funds" && <AgentFunding key={selected} agentId={selected} />}
      {selected && view === "Positions" && <AgentRecurring key={`recurring-${selected}`} agentId={selected} />}
      {selected && view === "Positions" && <AgentActions key={selected} agentId={selected} />}
      {selected && <ServiceAccountState key={`${view}-${selected}`} agentId={selected} />}
    </section>
  );
}

export function AccountViews({ initialView = "Agents", sourceRecordId, agentId }: { initialView?: AccountViewName; sourceRecordId?: string; agentId?: string }) {
  const [view, setView] = useState<AccountViewName>(initialView);
  const [records, setRecords] = useState<AccountViewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [moreError, setMoreError] = useState("");
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [relatedIncomplete, setRelatedIncomplete] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMoreError("");
    setRecords([]);
    setNextOffset(null);
    setRelatedIncomplete(false);
    try {
      const page = await loadAccountViews();
      let nextRecords = page.records;
      let source = sourceRecordId ? nextRecords.find((record) => record.record_id === sourceRecordId) : undefined;
      if (sourceRecordId && !source) {
        source = await getAccountView(sourceRecordId);
        nextRecords = mergeAccountRecords(nextRecords, [source]);
      }
      if (source) {
        const resolvedSource = source;
        const queries = relatedQueries(resolvedSource);
        const relatedResults = await Promise.all(queries.map(async (filters) => {
          try { return await loadAccountViews(filters); } catch { return null; }
        }));
        const relatedPages = relatedResults.filter((related) => related !== null);
        const exactRelated = relatedPages.flatMap((related) => related.records)
          .filter((record) => relatedRecordMatches(resolvedSource, record));
        nextRecords = mergeAccountRecords(nextRecords, exactRelated);
        setRelatedIncomplete(relatedResults.some((related) => related === null)
          || relatedPages.some((related) => related.next_offset != null));
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
    const targetView = kind === "AGENT" || kind === "MONITORING" || kind === "PERMISSION_SNAPSHOT" ? "Agents"
      : kind === "CAPITAL_FLOW" || (kind === "ACTION" && !source.content.position_id) ? "Funds" : "Positions";
    setView(targetView);
  }, [sourceRecordId, records]);

  useEffect(() => {
    if (!sourceRecordId || !records.length) return;
    const source = records.find((record) => record.record_id === sourceRecordId);
    if (!source) return;
    const kind = source.content.record_kind;
    const targetView = kind === "AGENT" || kind === "MONITORING" || kind === "PERMISSION_SNAPSHOT" ? "Agents"
      : kind === "CAPITAL_FLOW" || (kind === "ACTION" && !source.content.position_id) ? "Funds" : "Positions";
    if (view !== targetView) return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(`record-${sourceRecordId}`);
      target?.closest("details")?.setAttribute("open", "");
      target?.scrollIntoView?.({ block: "center" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [sourceRecordId, records, view]);

  const loadMore = async () => {
    if (nextOffset == null || loadingMore) return;
    setLoadingMore(true);
    setMoreError("");
    try {
      const page = await loadAccountViews({}, nextOffset);
      setRecords((current) => mergeAccountRecords(current, page.records));
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
      <ConnectedAgent view={view} agentId={agentId} />
      <h2>Authored account records</h2>
      {loading && <p role="status" aria-live="polite">Loading saved account records…</p>}
      {!loading && error && <section className="panel" role="alert">
        <p>{error} Existing records remain unchanged.</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => setAttempt((value) => value + 1)}>Try again</button>
      </section>}
      {!loading && !error && view === "Agents" && <AgentRecords records={records} sourceRecordId={sourceRecordId} />}
      {!loading && !error && view === "Positions" && <PositionRecords records={records} sourceRecordId={sourceRecordId} />}
      {!loading && !error && view === "Funds" && <FundRecords records={records} />}
      {!loading && !error && relatedIncomplete && <p role="status" aria-live="polite">Related history exceeds this bounded page. The exact saved source remains visible; load more records to inspect additional rows.</p>}
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
