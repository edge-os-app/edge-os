# Account-view records

Version 1.0.0 adds P19-owned record content. Each record uses the P02 envelope. P19 does not add its types to P02's closed schema registry.

Every record binds to the verified owner and exact agent. Wallet, network, asset, position, strategy revision, mandate, action, or flow identities are present when the record kind needs them. The server derives `owner_id` from authentication and rejects a client-supplied owner.

Amounts preserve `{asset_id, raw, decimals}`. `raw` is a canonical non-negative base-10 integer string. A view does not sum amounts with different assets. Native MON gas stays separate from trading assets. Unknown basis, realized result, unrealized result, or mark stays `UNKNOWN`; the view does not substitute zero. Deposits and withdrawals remain capital flows and do not count as profit or restore permission.

Each position's action list uses the exact owner, agent, wallet, network, and position identity. An action that belongs to another wallet or position cannot appear in that position view. Closed positions, failed actions, and pending or unknown actions remain inspectable.

This P19 fixture content uses only `SYNTHETIC_AUTHORED` evidence. It cannot claim a live wallet, balance, health check, mark, receipt, account value, percent return, or drawdown. The P15 profile and record meanings remain controlling for later operational records.
