"use client";

import { useMemo, useState } from "react";
import { actionsForPosition, filterPositions, formatAmount, formatResult, formatValue, type AccountViewRecord } from "../lib/account-views";

export function PositionRecords({ records, sourceRecordId }: { records: AccountViewRecord[]; sourceRecordId?: string }) {
  const [agentId, setAgentId] = useState("");
  const [walletId, setWalletId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [strategyRevision, setStrategyRevision] = useState("");
  const positions = useMemo(() => filterPositions(records, {
    agent_id: agentId || undefined, wallet_id: walletId || undefined, asset_id: assetId || undefined,
    strategy_revision: strategyRevision || undefined,
  }), [records, agentId, walletId, assetId, strategyRevision]);
  const agents = [...new Set(records.filter((row) => row.content.record_kind === "POSITION").map((row) => row.content.agent_id))];
  const wallets = [...new Set(records.filter((row) => row.content.record_kind === "POSITION").map((row) => row.content.wallet_id).filter((value): value is string => Boolean(value)))];
  const assets = [...new Set(records.filter((row) => row.content.record_kind === "POSITION").map((row) => row.content.asset_id).filter((value): value is string => Boolean(value)))];
  const revisions = [...new Set(records.filter((row) => row.content.record_kind === "POSITION").map((row) => row.content.strategy_revision).filter((value): value is string => Boolean(value)))];
  const sourceAction = records.find((record) => record.record_id === sourceRecordId
    && record.content.record_kind === "ACTION" && record.content.position_id);
  const sourceActionPosition = sourceAction && records.find((row) => row.content.record_kind === "POSITION"
    && row.owner_id === sourceAction.owner_id && row.content.agent_id === sourceAction.content.agent_id
    && row.content.wallet_id === sourceAction.content.wallet_id && row.content.network_id === sourceAction.content.network_id
    && row.content.asset_id === sourceAction.content.asset_id && row.content.position_id === sourceAction.content.position_id
    && row.content.strategy_revision === sourceAction.content.strategy_revision
    && row.content.mandate_id === sourceAction.content.mandate_id);
  const unmatchedSourceAction = sourceAction && !sourceActionPosition ? sourceAction : undefined;
  const sourceEdge = records.find((record) => record.record_id === sourceRecordId && record.content.record_kind === "EDGE_EVIDENCE");
  const sourceEdgePosition = sourceEdge && positions.find((position) => position.owner_id === sourceEdge.owner_id
    && position.content.agent_id === sourceEdge.content.agent_id
    && position.content.strategy_revision === sourceEdge.content.strategy_revision);

  return (
    <div className="stack">
      <div className="panel" aria-label="Position filters" style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <label>Agent
          <select className="input" style={{ minHeight: 44 }} value={agentId} onChange={(event) => setAgentId(event.target.value)}>
            <option value="">All agents</option>{agents.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>Wallet
          <select className="input" style={{ minHeight: 44 }} value={walletId} onChange={(event) => setWalletId(event.target.value)}>
            <option value="">All wallets</option>{wallets.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>Asset
          <select className="input" style={{ minHeight: 44 }} value={assetId} onChange={(event) => setAssetId(event.target.value)}>
            <option value="">All assets</option>{assets.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>Strategy revision
          <select className="input" style={{ minHeight: 44 }} value={strategyRevision} onChange={(event) => setStrategyRevision(event.target.value)}>
            <option value="">All revisions</option>{revisions.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
      </div>
      {!positions.length && <p className="muted">No positions match these filters.</p>}
      {unmatchedSourceAction && <section className="panel" aria-label="Exact source action">
        <h2>Exact saved source action</h2>
        <p>The owner-matched parent position is unavailable. This saved action is shown without inferring or assigning a position relationship.</p>
        <ul><li id={`record-${unmatchedSourceAction.record_id}`}>
          {unmatchedSourceAction.content.action_id} · {unmatchedSourceAction.content.status} · {unmatchedSourceAction.content.updated_at}
          {unmatchedSourceAction.content.reason && <p>{unmatchedSourceAction.content.reason}</p>}
        </li></ul>
      </section>}
      {sourceEdge && !sourceEdgePosition && <section className="panel" id={`record-${sourceEdge.record_id}`} aria-label="Exact edge evidence source">
        <h2>Exact saved revision evidence</h2>
        <p>No matching position is available in the bounded account page. This saved evidence is shown without assigning it to a position.</p>
        <p>{sourceEdge.content.agent_id} · {sourceEdge.content.strategy_revision} · {sourceEdge.content.edge_revision} · {sourceEdge.content.edge_evidence_status ?? sourceEdge.content.status} · {sourceEdge.content.updated_at}</p>
        {sourceEdge.content.reason && <p>{sourceEdge.content.reason}</p>}
        <p>Record ID: <code>{sourceEdge.record_id}</code></p>
      </section>}
      {positions.map((position) => {
        const { content } = position;
        const actions = actionsForPosition(records, position);
        const edgeEvidence = records.filter((record) => record.owner_id === position.owner_id
          && record.content.record_kind === "EDGE_EVIDENCE"
          && record.content.agent_id === content.agent_id
          && record.content.strategy_revision === content.strategy_revision);
        return (
          <details className="panel" id={`record-${position.record_id}`} key={position.record_id}>
            <summary style={{ minHeight: 44, cursor: "pointer" }}>
              {content.agent_id} · {content.position_id} · {content.asset_id} · {content.position_state}
            </summary>
            <p><strong>Wallet and network.</strong> {content.wallet_id} · {content.network_id}</p>
            <p><strong>Strategy and mandate.</strong> {content.strategy_revision} · {content.mandate_id}</p>
            <p><strong>{content.position_state === "CLOSED" ? "Historical attributed quantity." : "Attributed quantity."}</strong> {content.quantity ? `${formatAmount(content.quantity)} ${content.quantity.asset_id}` : "Unknown"}{content.position_state === "CLOSED" && " Current residual wallet inventory is unavailable."}</p>
            <p><strong>Acquisition basis.</strong> {formatValue(content.basis)}{content.basis?.amount && ` ${content.basis.amount.asset_id}`}</p>
            <p><strong>Realized quote result.</strong> {content.realized_result
              ? formatResult(content.realized_result) : formatValue(content.realized)}{(content.realized_result?.amount ?? content.realized?.amount) &&
                ` ${(content.realized_result?.amount ?? content.realized?.amount)?.asset_id}`}</p>
            <p><strong>Estimated unrealized quote result.</strong> {content.estimated_unrealized_result
              ? formatResult(content.estimated_unrealized_result) : formatValue(content.unrealized)}{(content.estimated_unrealized_result?.amount ?? content.unrealized?.amount) &&
                ` ${(content.estimated_unrealized_result?.amount ?? content.unrealized?.amount)?.asset_id}`}</p>
            {content.reason && <p><strong>Saved note.</strong> {content.reason}</p>}
            <p><strong>Mark.</strong> {formatValue(content.mark)} · {content.updated_at}</p>
            <h3>Revision-linked edge evidence</h3>
            {!edgeEvidence.length && <p>No saved edge evidence for this revision.</p>}
            <ul>{edgeEvidence.map((item) => (
              <li id={`record-${item.record_id}`} key={item.record_id}>
                {item.content.edge_revision} · {item.content.edge_evidence_status ?? item.content.status} · {item.content.updated_at}
                {item.content.reason && <p>{item.content.reason}</p>}
              </li>
            ))}</ul>
            <h3>Actions for this position</h3>
            {!actions.length && <p>No saved actions for this position.</p>}
            <ul>{actions.map((action) => (
              <li id={`record-${action.record_id}`} key={action.record_id}>
                {action.content.action_id} · {action.content.status} · {action.content.quantity && `${formatAmount(action.content.quantity)} ${action.content.quantity.asset_id}`} · {action.content.updated_at}
                {action.content.reason && <p>{action.content.reason}</p>}
                {action.content.gas && <p>Native gas: {formatAmount(action.content.gas)} {action.content.gas.asset_id}</p>}
              </li>
            ))}</ul>
          </details>
        );
      })}
    </div>
  );
}
