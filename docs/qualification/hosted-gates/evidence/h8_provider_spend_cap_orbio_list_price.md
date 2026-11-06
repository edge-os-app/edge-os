# H8 provider spend caps with the Orbio list-price route (HOSTED_RECORD_V2_RUNBOOK §6)

Status: **documented, with the limits below**. This file replaces `h8_provider_spend_cap_orbio.md` for the record
`edgeos-fun-vps1-orbio-list-price`. That file names the retired release and its price. It stays unchanged as the evidence
of the record `edgeos-fun-vps1-orbio`.

No host, key, provider call or Orbio account read happened for this file. Each fact names its source. The one paid local
call of 2026-11-06 is in `ORBIO_RELEASE_DRAFT.md` §1.5.

## Provider accounts

| Provider | Use in this deployment | Funding | Provider-side limit | Remaining balance visible in |
|---|---|---|---|---|
| Orbio | model calls, release `orbio-list-price-1` | paid, not sponsored: the builder bought USD 5 of balance on 2026-11-06 | the prepaid balance; see Limits | the Orbio account page, or `GET /api/v1/key` in the builder's terminal |
| Nansen | research data | sponsored | the sponsor's allocation | the Nansen account dashboard |
| QuickNode | Monad RPC access | sponsored | the sponsor's allocation | the QuickNode account dashboard |
| Envio HyperSync | history source | free | the free allowance | the Envio account dashboard |

Sources: the USD 5 purchase is in the controller handoff, 2026-11-06. The `GET /api/v1/key` route is Orbio's public
documentation (`ORBIO_RELEASE_DRAFT.md` §1.2). The Nansen, QuickNode and Envio rows are copied from
`h8_provider_spend_cap.md`. Their amounts stay in each provider account.

No card-backed cap is recorded. No source in this repository shows the Orbio account's limit settings. The size of the
purchase is the only provider-side limit on record.

## Application-side caps

These caps are not provider caps. They limit what the application asks for.

| Cap | Value | Where it is set | State |
|---|---|---|---|
| Provider spend ledger, all owners | USD 2.00 | `RELEASE_DEFINITIONS`, `global_cap_usd` (code) | fixed in code |
| Provider spend ledger, each owner | USD 2.00 | `RELEASE_DEFINITIONS`, `owner_cap_usd` (code) | fixed in code |
| Reservation for each request | USD 0.17216 | the Orbio price snapshot (`ORBIO_RELEASE_DRAFT.md` §4) | fixed by the release record |
| `EDGE_OS_USAGE_GLOBAL_PROVIDER_REQUESTS` | 60 | Coolify | saved on 2026-11-06, not applied at the last handoff entry; the host environment files need a separate check |
| `EDGE_OS_USAGE_GLOBAL_NANSEN_CREDITS` | 50 | Coolify | saved on 2026-11-06, not applied at the last handoff entry; the host environment files need a separate check |
| `EDGE_OS_RESEARCH_BUDGET_*` | not recorded here | Coolify, optional | bounds research spending, as in `h8_provider_spend_cap.md` |

The ledger is the money limit. The request limit is not: 60 requests at USD 0.17216 is USD 10.3296, which is more than
the USD 5 balance. The ledger admits at most 11 open reservations, because 11 × USD 0.17216 is USD 1.89376 and a twelfth
passes USD 2.00.

## Limits

- Not known: whether Orbio refuses a request when the balance reaches zero. No test or document shows this. The balance
  is therefore not a proven hard stop.
- Not known after one paid call: the unit of the balance (U11), whether a fee applies to later requests (U10) and the
  timing of `X-Orbio-Balance` (U9).
- A reply settles only when `usage.cost` equals the snapshot charge (`ORBIO_RELEASE_DRAFT.md` §5). If Orbio returns
  another figure, the answer is kept, but each attempt stays UNKNOWN and keeps its full USD 0.17216. The ledger then
  refuses new requests after 11 attempts, whatever the real charges were.
- A charge above the reservation is possible (`ORBIO_RELEASE_DRAFT.md` §6). The ledger cannot see that before the send.
- The ledger sees only its own database. The hosted ledger does not see spend from a local run, and a local ledger does
  not see hosted spend. Each ledger has its own USD 2.00 cap, so together they can admit USD 4.00. That is below the USD 5
  balance, but it is above the shared USD 2.00 ceiling of `h8_provider_spend_cap.md`. No code joins the two ledgers.

This file records the state. It sets no new limit and approves no provider call.
