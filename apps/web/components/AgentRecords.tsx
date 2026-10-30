"use client";

import { useEffect, useState } from "react";
import { agentContextApi, formatAmount, type AccountViewRecord, type AgentContextRecord } from "../lib/account-views";
import { PERMISSION_STATE, RECORD_STATUS, plain } from "../lib/labels";
import { Details } from "./Details";
import { AgentContext } from "./AgentContext";
import { WalletSetup } from "./WalletSetup";
import { plural } from "../lib/plural";

export function AgentRecords({ records, sourceRecordId }: { records: AccountViewRecord[]; sourceRecordId?: string }) {
  const agents = records.filter((record) => record.content.record_kind === "AGENT");
  const unmatchedSource = records.find((record) => record.record_id === sourceRecordId
    && (record.content.record_kind === "MONITORING" || record.content.record_kind === "PERMISSION_SNAPSHOT"));
  const sourceHasMatchingAgent = unmatchedSource && agents.some((record) => record.owner_id === unmatchedSource.owner_id
    && record.content.agent_id === unmatchedSource.content.agent_id
    && record.content.wallet_id === unmatchedSource.content.wallet_id
    && record.content.network_id === unmatchedSource.content.network_id);
  const [selected, setSelected] = useState<string | null>(null);
  const [context, setContext] = useState<AgentContextRecord | null>(null);
  const [contextError, setContextError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [setupAgent, setSetupAgent] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) return;
    let current = true;
    setContext(null);
    setContextError("");
    agentContextApi.get(selected).then((next) => {
      if (current) setContext(next);
    }).catch(() => {
      if (current) setContextError("Agent context could not be loaded. Try again.");
    });
    return () => { current = false; };
  }, [selected, refresh]);

  if (!agents.length && !unmatchedSource) return <p className="muted">No saved agent records.</p>;
  return (
    <div className="stack">
      {unmatchedSource && !sourceHasMatchingAgent && <section className="panel" id={`record-${unmatchedSource.record_id}`} aria-label="Exact agent source">
        <h2>Exact saved {unmatchedSource.content.record_kind === "MONITORING" ? "monitoring" : "permission"} source</h2>
        <p>The related agent summary is unavailable. This exact saved record is shown without inferring a relationship or current permission.</p>
        <dl className="kv" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr)" }}>
          <dt>Owner, agent, wallet and network</dt><dd>{unmatchedSource.owner_id} · {unmatchedSource.content.agent_id} · {unmatchedSource.content.wallet_id} · {unmatchedSource.content.network_id}</dd>
          <dt>Saved version and permission</dt><dd>{unmatchedSource.content.strategy_revision ?? "Not recorded"} · {unmatchedSource.content.mandate_id ?? "Not recorded"}</dd>
          <dt>Status and updated</dt><dd>{plain(RECORD_STATUS, unmatchedSource.content.status, "Unknown")} · {unmatchedSource.content.updated_at}</dd>
          {unmatchedSource.content.record_kind === "MONITORING" && <>
            <dt>Health / evaluations</dt><dd>{unmatchedSource.content.health ?? "Unknown"} · {unmatchedSource.content.evaluation_attempts ?? "Unknown"} attempts / {unmatchedSource.content.evaluation_completions ?? "Unknown"} completions</dd>
            <dt>Inputs / next work</dt><dd>{unmatchedSource.content.input_updated_at ?? "Input time not recorded"} · {unmatchedSource.content.next_work ?? "Not recorded"}</dd>
            <dt>Block / reconciliation</dt><dd>{unmatchedSource.content.blocking_reason ?? "No block recorded"} · {unmatchedSource.content.pending_reconciliation == null ? "Unknown" : unmatchedSource.content.pending_reconciliation ? "Yes" : "No"}</dd>
          </>}
          {unmatchedSource.content.record_kind === "PERMISSION_SNAPSHOT" && <>
            <dt>Approval / activation</dt><dd>{unmatchedSource.content.approval_id} · {unmatchedSource.content.activation_state}</dd>
            <dt>Predecessor / successor</dt><dd>{unmatchedSource.content.predecessor_approval_id ?? "No predecessor recorded"} · {unmatchedSource.content.successor_approval_id ?? "No successor recorded"}</dd>
            <dt>Signer and policy</dt><dd>{unmatchedSource.content.signer_binding ?? "Not recorded"} · {unmatchedSource.content.policy_binding ?? "Not recorded"}</dd>
            <dt>Requested / checked</dt><dd>{unmatchedSource.content.requested_at ?? "Not recorded"} · {unmatchedSource.content.checked_at ?? "Not recorded"}</dd>
            <dt>Approved and applied</dt><dd>{unmatchedSource.content.approved_at ?? "No owner approval recorded"} · {unmatchedSource.content.applied_at ?? "Not applied / not recorded"}</dd>
            <dt>Failed and cancelled</dt><dd>{unmatchedSource.content.failed_at ?? "No failure recorded"} · {unmatchedSource.content.cancelled_at ?? "No cancellation recorded"}</dd>
            <dt>Terms hash</dt><dd>{unmatchedSource.content.terms_hash}</dd>
            <dt>Adopted capital</dt><dd>{unmatchedSource.content.terms?.adopted_capital.map((amount) => `${formatAmount(amount)} ${amount.asset_id}`).join("; ") ?? "Not recorded"}</dd>
            <dt>Supported assets and routes</dt><dd>{unmatchedSource.content.terms?.supported_assets.join(", ") ?? "Not recorded"} · {unmatchedSource.content.terms?.supported_routes.join(", ") ?? "Not recorded"}</dd>
            <dt>Actions and expiry</dt><dd>{unmatchedSource.content.terms?.actions.join(", ") ?? "Not recorded"} · {unmatchedSource.content.terms?.expiry ?? "Not recorded"}</dd>
            <dt>Limits and stop effects</dt><dd>{unmatchedSource.content.terms?.limits.map((limit) => `${limit.name}: ${formatAmount(limit.amount)} ${limit.amount.asset_id}`).join("; ") ?? "Not recorded"} · {unmatchedSource.content.terms?.stop_effects.join(", ") ?? "Not recorded"}</dd>
          </>}
        </dl>
        <Details summary="Details"><p className="mono">status {unmatchedSource.content.status} · permission {unmatchedSource.content.permission_state ?? "none"}</p></Details>
        <p>Record ID: <code>{unmatchedSource.record_id}</code></p>
      </section>}
      {agents.map(({ record_id, owner_id, content }) => {
        const monitoring = records.filter((record) => record.owner_id === owner_id
          && record.content.record_kind === "MONITORING"
          && record.content.agent_id === content.agent_id
          && record.content.wallet_id === content.wallet_id
          && record.content.network_id === content.network_id);
        const permissions = records.filter((record) => record.owner_id === owner_id
          && record.content.record_kind === "PERMISSION_SNAPSHOT"
          && record.content.agent_id === content.agent_id
          && record.content.wallet_id === content.wallet_id
          && record.content.network_id === content.network_id);
        return <section className="panel" id={`record-${record_id}`} key={record_id}>
          <h2>{content.agent_id}</h2>
          <p><strong>Wallet.</strong> {content.wallet_id} · {content.network_id}</p>
          <p><strong>Agent state.</strong> {plain(RECORD_STATUS, content.status, "Unknown")} · {content.health ? "health recorded" : "health unknown"} · example record</p>
          <p><strong>Wallet balance.</strong> {content.wallet_balance ? `${formatAmount(content.wallet_balance)} ${content.wallet_balance.asset_id}` : "Unknown"}</p>
          <p><strong>Available.</strong> {content.available_balance ? `${formatAmount(content.available_balance)} ${content.available_balance.asset_id}` : "Unknown"}</p>
          <p><strong>Reserved.</strong> {content.reserved_amount ? `${formatAmount(content.reserved_amount)} ${content.reserved_amount.asset_id}` : "Unknown"}</p>
          <p><strong>Remaining authority.</strong> {content.remaining_authority ? `${formatAmount(content.remaining_authority)} ${content.remaining_authority.asset_id}` : "Unknown"}</p>
          <p><strong>Network gas.</strong> {content.native_gas ? `${formatAmount(content.native_gas)} ${content.native_gas.asset_id}` : "Unknown"}</p>
          <p><strong>Permission.</strong> {plain(PERMISSION_STATE, content.permission_state, "Unknown")}. Account summaries do not pool balances or permission.</p>
          <p><strong>Updated.</strong> <time dateTime={content.updated_at}>{content.updated_at}</time></p>
          <Details summary="Details"><p className="mono">status {content.status} · health {content.health ?? "none"} · permission {content.permission_state ?? "none"}</p></Details>
          <div className="btn-row">
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => setSelected(content.agent_id)}>
              Inspect agent context
            </button>
            <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button"
              onClick={() => setSetupAgent((value) => value === content.agent_id ? null : content.agent_id)}>
              {setupAgent === content.agent_id ? "Hide wallet setup" : "Wallet setup"}
            </button>
          </div>
          {selected === content.agent_id && (
            context ? <AgentContext record={context} onChange={setContext} onClose={() => setSelected(null)} />
              : <div role="status" aria-live="polite">{contextError || "Loading agent context…"}{contextError && <button className="btn btn-ghost" type="button" style={{ minHeight: 44 }} onClick={() => setRefresh((value) => value + 1)}>Try again</button>}</div>
          )}
          {setupAgent === content.agent_id && <WalletSetup agentId={content.agent_id} onClose={() => setSetupAgent(null)} />}
          <h3>Permission approval history · example records</h3>
          <p>Each snapshot records history at its own time. It does not prove current permission. A change marked active was active when applied; the agent summary above shows the current saved permission state.</p>
          {!permissions.length && <p>No saved permission approval snapshots.</p>}
          <ul>{permissions.map((snapshot) => {
            const item = snapshot.content;
            return <li id={`record-${snapshot.record_id}`} key={snapshot.record_id}>
              <details>
                <summary style={{ minHeight: 44, cursor: "pointer" }}>
                  {item.status.replaceAll("_", " ").toLowerCase()} · {item.status === "CHANGE_APPLIED" ? "active when applied" : (item.activation_state ?? "state unknown").replaceAll("_", " ").toLowerCase()}
                </summary>
                <dl className="kv" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr)" }}>
                  <dt>Approval ID</dt><dd className="mono">{item.approval_id}</dd>
                  <dt>Saved status codes</dt><dd className="mono">{item.status} · {item.activation_state ?? "none"}</dd>
                  <dt>Owner, agent, wallet and network</dt><dd>{snapshot.owner_id} · {item.agent_id} · {item.wallet_id} · {item.network_id}</dd>
                  <dt>Saved version and permission</dt><dd>{item.strategy_revision} · {item.mandate_id}</dd>
                  <dt>Earlier and later approval</dt><dd>{item.predecessor_approval_id ?? (item.status === "FAILED" || item.status === "CANCELLED" ? "No earlier approval (initial attempt)" : "No predecessor recorded")} · {item.successor_approval_id ?? "No successor recorded"}</dd>
                  <dt>Signer and policy</dt><dd>{item.signer_binding} · {item.policy_binding}</dd>
                  <dt>Requested and checked</dt><dd>{item.requested_at ?? "Not recorded"} · {item.checked_at ?? (item.status === "CHANGE_PENDING" ? "Not yet checked" : item.status === "CANCELLED" ? "Not checked before cancellation" : "Not recorded")}</dd>
                  <dt>Approved and applied</dt><dd>{item.approved_at ?? "No owner approval recorded"} · {item.applied_at ?? (item.activation_state === "NEVER_ACTIVE" ? "Not applied (never active)" : "Not recorded")}</dd>
                  <dt>Failed and cancelled</dt><dd>{item.failed_at ?? "No failure recorded"} · {item.cancelled_at ?? "No cancellation recorded"}</dd>
                  <dt>Terms hash</dt><dd>{item.terms_hash}</dd>
                  <dt>Adopted capital</dt><dd>{item.terms?.adopted_capital.map((amount) => `${formatAmount(amount)} ${amount.asset_id}`).join("; ")}</dd>
                  <dt>Supported assets and routes</dt><dd>{item.terms?.supported_assets.join(", ")} · {item.terms?.supported_routes.join(", ")}</dd>
                  <dt>Actions and expiry</dt><dd>{item.terms?.actions.join(", ")} · {item.terms?.expiry}</dd>
                  <dt>Limits</dt><dd>{item.terms?.limits.map((limit) => `${limit.name}: ${formatAmount(limit.amount)} ${limit.amount.asset_id}`).join("; ")}</dd>
                  <dt>Stop effects</dt><dd>{item.terms?.stop_effects.join(", ")}</dd>
                </dl>
              </details>
            </li>;
          })}</ul>
          <h3>Monitoring · example data</h3>
          {!monitoring.length && <p>No saved monitoring records.</p>}
          <ul>{monitoring.map((item) => (
            <li id={`record-${item.record_id}`} key={item.record_id}>
              <strong>{plain(RECORD_STATUS, item.content.status, "Unknown")}</strong> · {item.content.health ? "health recorded" : "health unknown"}
              {` · ${plural(item.content.evaluation_attempts ?? 0, "attempt")}, ${item.content.evaluation_completions ?? 0} completed`}
              {item.content.input_updated_at && <> · inputs updated <time dateTime={item.content.input_updated_at}>{item.content.input_updated_at}</time></>}
              {` · record updated ${item.content.updated_at}`}
              {item.content.next_work && <p style={{ overflowWrap: "anywhere" }}>Next work: {item.content.next_work}</p>}
              {item.content.blocking_reason && <p style={{ overflowWrap: "anywhere" }}>Blocked: {item.content.blocking_reason}</p>}
              <p>Pending reconciliation: {item.content.pending_reconciliation == null ? "Unknown" : item.content.pending_reconciliation ? "Yes" : "No"}</p>
              <Details summary="Details"><p className="mono">status {item.content.status} · health {item.content.health ?? "none"} · pending {String(item.content.pending_reconciliation)}</p></Details>
            </li>
          ))}</ul>
        </section>
      })}
    </div>
  );
}
