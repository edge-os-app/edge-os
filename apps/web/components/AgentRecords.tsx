"use client";

import { useEffect, useState } from "react";
import { agentContextApi, formatAmount, type AccountViewRecord, type AgentContextRecord } from "../lib/account-views";
import { AgentContext } from "./AgentContext";

export function AgentRecords({ records }: { records: AccountViewRecord[] }) {
  const agents = records.filter((record) => record.content.record_kind === "AGENT");
  const [selected, setSelected] = useState<string | null>(null);
  const [context, setContext] = useState<AgentContextRecord | null>(null);
  const [contextError, setContextError] = useState("");
  const [refresh, setRefresh] = useState(0);

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

  if (!agents.length) return <p className="muted">No saved agent records.</p>;
  return (
    <div className="stack">
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
          <p><strong>Worker state.</strong> {content.status} · {content.health} · authored fixture</p>
          <p><strong>Wallet balance.</strong> {content.wallet_balance ? `${formatAmount(content.wallet_balance)} ${content.wallet_balance.asset_id}` : "Unknown"}</p>
          <p><strong>Available.</strong> {content.available_balance ? `${formatAmount(content.available_balance)} ${content.available_balance.asset_id}` : "Unknown"}</p>
          <p><strong>Reserved.</strong> {content.reserved_amount ? `${formatAmount(content.reserved_amount)} ${content.reserved_amount.asset_id}` : "Unknown"}</p>
          <p><strong>Remaining authority.</strong> {content.remaining_authority ? `${formatAmount(content.remaining_authority)} ${content.remaining_authority.asset_id}` : "Unknown"}</p>
          <p><strong>Network gas.</strong> {content.native_gas ? `${formatAmount(content.native_gas)} ${content.native_gas.asset_id}` : "Unknown"}</p>
          <p><strong>Permission.</strong> {content.permission_state ?? "Unknown"}. Account summaries do not pool balances or permission.</p>
          <p><strong>Updated.</strong> <time dateTime={content.updated_at}>{content.updated_at}</time></p>
          <button className="btn btn-secondary" style={{ minHeight: 44 }} type="button" onClick={() => setSelected(content.agent_id)}>
            Inspect agent context
          </button>
          {selected === content.agent_id && (
            context ? <AgentContext record={context} onChange={setContext} onClose={() => setSelected(null)} />
              : <div role="status" aria-live="polite">{contextError || "Loading agent context…"}{contextError && <button className="btn btn-ghost" type="button" style={{ minHeight: 44 }} onClick={() => setRefresh((value) => value + 1)}>Try again</button>}</div>
          )}
          <h3>Permission approval history · synthetic records</h3>
          {!permissions.length && <p>No saved permission approval snapshots.</p>}
          <ul>{permissions.map((snapshot) => {
            const item = snapshot.content;
            return <li id={`record-${snapshot.record_id}`} key={snapshot.record_id}>
              <details>
                <summary style={{ minHeight: 44, cursor: "pointer" }}>
                  {item.approval_id} · {item.status} · {item.activation_state}
                </summary>
                <dl>
                  <dt>Owner / agent / wallet / network</dt><dd>{snapshot.owner_id} · {item.agent_id} · {item.wallet_id} · {item.network_id}</dd>
                  <dt>Strategy revision / mandate</dt><dd>{item.strategy_revision} · {item.mandate_id}</dd>
                  <dt>Predecessor / successor approval</dt><dd>{item.predecessor_approval_id ?? "none"} · {item.successor_approval_id ?? "none"}</dd>
                  <dt>Signer / policy binding</dt><dd>{item.signer_binding} · {item.policy_binding}</dd>
                  <dt>Requested / checked</dt><dd>{item.requested_at} · {item.checked_at}</dd>
                  <dt>Approved / applied</dt><dd>{item.approved_at ?? "not approved"} · {item.applied_at ?? "not applied"}</dd>
                  <dt>Failed / cancelled</dt><dd>{item.failed_at ?? "none"} · {item.cancelled_at ?? "none"}</dd>
                  <dt>Terms hash</dt><dd>{item.terms_hash}</dd>
                  <dt>Adopted capital</dt><dd>{item.terms?.adopted_capital.map((amount) => `${formatAmount(amount)} ${amount.asset_id}`).join("; ")}</dd>
                  <dt>Supported assets / routes</dt><dd>{item.terms?.supported_assets.join(", ")} · {item.terms?.supported_routes.join(", ")}</dd>
                  <dt>Actions / expiry</dt><dd>{item.terms?.actions.join(", ")} · {item.terms?.expiry}</dd>
                  <dt>Limits</dt><dd>{item.terms?.limits.map((limit) => `${limit.name}: ${formatAmount(limit.amount)} ${limit.amount.asset_id}`).join("; ")}</dd>
                  <dt>Stop effects</dt><dd>{item.terms?.stop_effects.join(", ")}</dd>
                </dl>
              </details>
            </li>;
          })}</ul>
          <h3>Monitoring · synthetic fixture</h3>
          {!monitoring.length && <p>No saved monitoring records.</p>}
          <ul>{monitoring.map((item) => (
            <li id={`record-${item.record_id}`} key={item.record_id}>
              <strong>{item.content.status}</strong> · {item.content.health ?? "health unknown"}
              {` · ${item.content.evaluation_attempts ?? "Unknown"} attempts / ${item.content.evaluation_completions ?? "Unknown"} completions`}
              {item.content.input_updated_at && <> · inputs updated <time dateTime={item.content.input_updated_at}>{item.content.input_updated_at}</time></>}
              {` · record updated ${item.content.updated_at}`}
              {item.content.next_work && <p>Next work: {item.content.next_work}</p>}
              {item.content.blocking_reason && <p>Blocked: {item.content.blocking_reason}</p>}
              <p>Pending reconciliation: {item.content.pending_reconciliation == null ? "Unknown" : item.content.pending_reconciliation ? "Yes" : "No"}</p>
            </li>
          ))}</ul>
        </section>
      })}
    </div>
  );
}
