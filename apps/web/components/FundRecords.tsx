import { actionsForFlow, formatAmount, type AccountViewRecord } from "../lib/account-views";

export function FundRecords({ records }: { records: AccountViewRecord[] }) {
  const wallets = records.filter((record) => record.content.record_kind === "AGENT");
  const flows = records.filter((record) => record.content.record_kind === "CAPITAL_FLOW");
  const walletActions = records.filter((record) => record.content.record_kind === "ACTION" && !record.content.position_id && record.content.flow_id);
  const actionsWithLoadedFlow = new Set(flows.flatMap((flow) => actionsForFlow(records, flow).map((action) => action.record_id)));
  const actionsWithoutLoadedFlow = walletActions.filter((action) => !actionsWithLoadedFlow.has(action.record_id));
  if (!wallets.length && !flows.length && !walletActions.length) return <p className="muted">No saved fund records.</p>;
  return (
    <div className="stack">
      <p>Each wallet keeps its own funds, reservations, authority, and network gas. Deposits and withdrawals are capital flows, not trading results.</p>
      {wallets.map(({ record_id, content }) => (
        <section className="panel" id={`record-${record_id}`} key={record_id}>
          <h2>{content.agent_id} · {content.wallet_id}</h2>
          <p>{content.network_id} · authored synthetic record · updated {content.updated_at}</p>
          <dl>
            <dt>Wallet balance</dt><dd>{content.wallet_balance ? `${formatAmount(content.wallet_balance)} ${content.wallet_balance.asset_id}` : "Unknown"}</dd>
            <dt>Available funds</dt><dd>{content.available_balance ? `${formatAmount(content.available_balance)} ${content.available_balance.asset_id}` : "Unknown"}</dd>
            <dt>Reserved</dt><dd>{content.reserved_amount ? `${formatAmount(content.reserved_amount)} ${content.reserved_amount.asset_id}` : "Unknown"}</dd>
            <dt>Remaining authority</dt><dd>{content.remaining_authority ? `${formatAmount(content.remaining_authority)} ${content.remaining_authority.asset_id}` : "Unknown"}</dd>
            <dt>Native gas</dt><dd>{content.native_gas ? `${formatAmount(content.native_gas)} ${content.native_gas.asset_id}` : "Unknown"}</dd>
          </dl>
        </section>
      ))}
      <section className="panel">
        <h2>Capital flow history</h2>
        {!flows.length && <p>No saved capital flows.</p>}
        <ul>{flows.map((flow) => {
          const { record_id, content } = flow;
          const actions = actionsForFlow(records, flow);
          return (
          <li id={`record-${record_id}`} key={record_id}>
            {content.agent_id} · {content.wallet_id} · {content.flow_id} · {content.flow_kind} · {content.status}
            {content.quantity && ` · ${formatAmount(content.quantity)} ${content.quantity.asset_id}`}
            {` · ${content.updated_at}. Capital flow, not trading profit.`}
            <h3>Wallet actions for this flow</h3>
            {!actions.length && <p>No saved wallet actions for this flow.</p>}
            <ul>{actions.map((action) => <li id={`record-${action.record_id}`} key={action.record_id}>
              {action.content.action_id} · {action.content.status} · {action.content.updated_at}
              {action.content.reason && <p>{action.content.reason}</p>}
              {action.content.gas && <p>Native gas: {formatAmount(action.content.gas)} {action.content.gas.asset_id}</p>}
            </li>)}</ul>
          </li>
        );})}</ul>
        {actionsWithoutLoadedFlow.length > 0 && <>
          <h2>Wallet actions whose flow is not loaded</h2>
          <p>These exact action records are shown without flow attribution because the matching flow is unavailable.</p>
          <ul>{actionsWithoutLoadedFlow.map(({ record_id, content }) => <li id={`record-${record_id}`} key={record_id}>
            {content.agent_id} · {content.wallet_id} · {content.network_id} · {content.flow_id} · {content.action_id} · {content.status} · {content.updated_at}
            {content.reason && <p>{content.reason}</p>}
            {content.gas && <p>Native gas: {formatAmount(content.gas)} {content.gas.asset_id}</p>}
          </li>)}</ul>
        </>}
      </section>
    </div>
  );
}
