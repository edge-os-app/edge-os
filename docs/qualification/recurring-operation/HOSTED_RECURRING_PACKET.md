# Hosted/live recurring operation qualification packet (PROPOSED)

Status: **PROPOSED; every actual step is NOT_RUN.** Prepared 2026-10-13 for #58 AUT08 after P27 LOCAL (`RELEASE-E2E-L2-20261013-P27-LOCAL-v1`). This packet authorizes nothing. It lists what one bounded hosted run of recurring operation must fix and prove before any real evaluation, signature, broadcast or spend. The LOCAL milestone proves application composition over authored fixtures only. Every unresolved value is `REQUIRED_DECISION`.

## 1. What the LOCAL milestone proves and does not prove

| Proven LOCAL (authored fixtures, no egress) | Not proven |
|---|---|
| Explicit deployment bound to the exact adopted consent; one per consent; production refuses activation | Any real wallet, signer, policy, provider or chain behavior |
| Producer saves one occurrence per due five-minute slot; two producer processes, repeats and restarts create no duplicate; missed slots counted, never replayed | Real scheduler timing, host clock behavior, process supervision on a host, operating-window suitability |
| Every evaluation saves SIGNAL/NO_SIGNAL/INELIGIBLE/UNAVAILABLE with input and evaluation times before any intent; stale, wrong-market, incomplete or non-forward observations deny | Any actual forward market feed, its freshness, finality or availability |
| Entry, full exit and re-entry under the existing admission counters; cumulative limits, expiry, stops and removal deny | Real quotes, slippage, fees, gas, partial fills, reverts on chain |
| Unknown originals wait on the wallet claim and settle from receipts only; other owners unaffected | Real receipts, reorgs, signer-reply loss on a real provider |

## 2. Values the builder must fix (each blocks an actual run)

| Field | State |
|---|---|
| Network, chain id, route and exact contract identities | `REQUIRED_DECISION` (see `docs/qualification/original-transaction/ACTUAL_ORIGINAL_TRANSACTION_QUALIFICATION_PACKET.md`) |
| Forward observation source, its evidence class name, freshness bound and missing-data rule | `REQUIRED_DECISION` (historical recordings, research data, Nansen findings and swap quotes are not forward feeds) |
| Operating window (start, end, time zone, slots) | `REQUIRED_DECISION` |
| Supported actions (ENTRY and full EXIT only; additions, partial exits, withdrawals and liquidation stay excluded) | fixed by P27 LOCAL |
| Per-action quote input and base amount ceilings | `REQUIRED_DECISION` |
| Cumulative quote, base, gas and attempt allowances for the whole window | `REQUIRED_DECISION` |
| Per-action gas cap and maximum fee per gas | `REQUIRED_DECISION` |
| Provider request ceilings (observations, quotes, holdings, receipts) per slot and per window | `REQUIRED_DECISION` |
| Stop conditions (time, loss, attempt exhaustion, operator stop) and who may trigger them | `REQUIRED_DECISION` |
| Recovery rule for an unknown original (receipt source, finality depth, maximum wait) | `REQUIRED_DECISION` |
| Host, process supervision, clock source, log retention and credential delivery | `REQUIRED_DECISION` (HOST lane; no presumed server access) |
| P31 chat health compatibility with the same durable projection | `REQUIRED_DECISION` after P31 acceptance |

## 3. Proof the hosted run must produce

- Repeated automatic evaluations with the user browser closed, each saved with real input times, including at least one NO_SIGNAL or UNAVAILABLE outcome observed rather than manufactured.
- Supported permitted actions within the fixed ceilings, and independent denials (stop, exhausted allowance, expired terms) observed without a forced trade.
- Original-action recovery after an interrupted reply, settled from an independent receipt only.
- A stop and a verified revocation (removal) that persist across a process restart, with residual holdings and owner access retained.
- The direct projection and P31 chat health showing the same deployment, last attempt/completion, input times, next due slot, wait reason and pending reconciliation.

Never trade to create a signal, and never repeat a swap to make a recording look better. A required case that was not observed stays unqualified.

## 4. Boundaries

No credential, account, wallet, policy change, signing, broadcast, spending, hosting, deployment, publication or provider call is authorized by this document. A real run needs one exact released packet with every `REQUIRED_DECISION` filled and recorded builder approval.
