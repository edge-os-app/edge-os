"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { loadServiceProjection, type ServiceProjectionPage, type ServiceProjectionRecord } from "../lib/account-views";
import { formatRaw } from "../lib/financial";

const KIND_LABEL: Record<string, string> = { AGENT: "Agent", CAPITAL_FLOW: "Deposit or withdrawal", POSITION: "Position",
  ACTION: "Action", MONITORING: "Evaluations" };

function amount(value: { raw: string; decimals: number; asset_id: string } | null | undefined): string {
  return value ? `${formatRaw(value.raw, value.decimals)} ${value.asset_id}` : "—";
}

function detail(record: ServiceProjectionRecord): string {
  const item = record.content;
  switch (item.record_kind) {
    case "CAPITAL_FLOW":
      return `${item.flow_kind}: ${amount(item.quantity)}${item.reason ? `. ${item.reason}` : ""} Not a trading result.`;
    case "POSITION":
      return `Held ${amount(item.quantity)}; cost basis ${item.basis?.state === "KNOWN" ? amount(item.basis.amount) : "unknown"}; `
        + `realized ${item.realized_result?.state === "KNOWN" ? amount(item.realized_result.amount) : "unknown"}; `
        + "unrealized result and mark unknown (no observed mark).";
    case "ACTION":
      return `${item.action_id}${item.pending_reconciliation ? " · reconciliation pending" : ""}`;
    case "MONITORING":
      return `${item.evaluation_completions} of ${item.evaluation_attempts} evaluations finished`
        + `${item.pending_reconciliation ? " · reconcile the original action before another evaluation" : ""}`;
    default:
      return `${item.wallet_id ?? ""} · ${item.permission_state ?? ""}`;
  }
}

/** The selected agent's saved connected-service state, read only. Unknown values stay unknown. */
export function ServiceAccountState({ agentId }: { agentId: string }) {
  const [page, setPage] = useState<ServiceProjectionPage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setPage(await loadServiceProjection(agentId)); }
    catch (cause) { setError(cause instanceof ApiError ? cause.detail : "The saved connected state could not be loaded."); }
    finally { setLoading(false); }
  }, [agentId]);
  useEffect(() => { void load(); }, [load]);

  return (
    <section className="panel" aria-label="Saved connected state" data-testid="service-account-state" style={{ overflowWrap: "anywhere" }}>
      <h2>Saved connected state</h2>
      {loading && <p role="status" className="muted">Loading the saved connected state…</p>}
      {error && <div role="alert"><p>{error}</p>
        <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Try again</button></div>}
      {page && !loading && <>
        <p className="muted">{page.notice} {page.ports === "FIXTURE" ? "Ports: authored local fixtures." : "Ports: unavailable."}</p>
        <div className="btn-row">
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => void load()}>Refresh saved state</button>
          <span className="muted">This panel reads the saved state when it opens. Refresh it after a change above.</span>
        </div>
        {page.records.length === 0 ? <p>No connected-service state is saved for this agent.</p> : (
          <ul className="stack" aria-label="Projected records">
            {page.records.map((record) => (
              <li key={record.record_id} className="card" data-kind={record.content.record_kind}>
                <strong>{KIND_LABEL[record.content.record_kind] ?? record.content.record_kind}: {record.content.status}</strong>
                <span>{detail(record)}</span>
                <span className="muted mono">from {record.source.table}</span>
              </li>
            ))}
          </ul>
        )}
      </>}
    </section>
  );
}
