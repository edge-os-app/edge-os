# Inactive consent profile (local stage)

Owned package: `apps/api/src/edge_os_api/consent/`. This profile records the
local inactive controlled-qualification consent domain for P26 #38. It is the
approved 2026-10-10 release portion only: **preparation**. It is not API/UI
wiring, not a production migration, not activation and not live qualification.

## Responsibility

The package groups one selected agent's exact saved strategy revision, its rules
and evidence status, the resolved wallet/network, and the reviewed limits, then
persists an owner's explicit adoption of that exact meaning as a clearly
**INACTIVE** consent. It mints no active authority snapshot. It enables no
release action: activation is deferred to the later qualified P20/P21/P24/P25
release evidence.

It is application accounting over authored reviewed terms. It creates no wallet,
signer, funding, mandate activation, position, admission, reservation, stop or
trading action.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Strict typed models: amounts, reviewed terms, route/policy/evidence, requests and views. |
| `records.py` | Owned SQLAlchemy tables on `ConsentBase`, in the `consent_local` schema. |
| `grouped_review.py` | Pure grouped-review composition and its canonical content hash. No database access. |
| `adoption.py` | Durable adoption: per-review advisory lock, idempotent save, conflict guard, consent hash and view. |
| `service.py` | `ConsentService`: owner-scoped review, adopt and read; identity resolution; fail-closed denials. |

Application names describe responsibility. The ticket number is not a module name.

## Verified-owner rule

Every `ConsentService` call receives `verified_owner_id` from the caller's
verified identity. A `ReviewRequest` or `AdoptionRequest` never carries an owner,
wallet, balance or approval; `extra="forbid"` rejects one at the boundary.
Retrieval is owner-scoped; another owner sees the same result as a missing record.
The service resolves the exact owner-scoped `StrategyRevision` and the accepted
P17 confirmed wallet binding server-side. A caller-supplied matching-looking
object alone does not establish ownership.

## Grouped review

`review` resolves, for the requested agent and exact revision:

- the owner-scoped immutable saved `StrategyRevision`, re-validated through the
  accepted P06 compiler (not a second compiler);
- the accepted P17 confirmed wallet binding, checked so its revision and content
  hashes match the requested revision exactly;
- the requested Monad network, checked against the bound network;
- the accepted funding confirmed balance (a capital flow, kept **separate from
  allocation**);
- the accepted admission allowances, decisions and any `SUBMISSION_UNKNOWN`
  pending action;
- the accepted durable scoped stops for that wallet.

The review shows the rules, evidence status and material limitations, operating
purpose, wallet/network/route, the explicit allocation, per-asset cumulative
allowances, attempts, gas, expiry and stop effects. An unknown component is named
in `unknowns`; it is never replaced with an invented value. Route and policy
qualification values are restricted to `UNQUALIFIED` or `UNKNOWN`, so the stage
cannot claim a live operational gate passed.

A second review for the same `(owner, agent, revision)` with changed terms is a
`changed_review` conflict. The exact reviewed meaning is not silently replaced.

## Durable adoption

`adopt` re-validates the stored review against the current revision and wallet
binding, re-hashes the stored terms and the reviewed meaning against the recorded
`terms_hash` and `review_hash`, checks the expiry, then persists one adoption per
`(owner, review)` in one transaction. After the per-review advisory lock it
re-reads the accepted wallet-setup row with the same row lock the wallet-setup
writer takes (`SELECT ... FOR UPDATE`) and holds it through commit, so a binding
that becomes unconfirmed between any earlier read and the save is denied. It binds
the strategy revision/hash, wallet/network, the reviewed term version/hash, and
the route/policy identity when present. An identical repeated adoption is
idempotent with the same `consent_hash`; a changed reuse of the same identity
conflicts. A crash, a concurrent adopter or a concurrent wallet change cannot
adopt a different meaning under the same identity or create a second consent.

## Fail-closed denials

A denial is saved in `consent_denials` with a stable code, and no affirmative
consent is written. Codes include `UNKNOWN_REVISION`, `UNREADABLE_REVISION`,
`WALLET_NOT_CONFIRMED`, `REVISION_WALLET_MISMATCH`, `NETWORK_MISMATCH`,
`WRONG_NETWORK_ASSET`, `CHANGED_REVIEW`, `UNKNOWN_REVIEW`, `STALE_REVIEW`,
`EXPIRED_TERMS`, `REVISION_DRIFTED`, `WALLET_DRIFTED` and `CHANGED_ADOPTION`.

Amounts use the accepted canonical unsigned raw integer string with decimals.
Missing required limits are rejected; an explicit zero stays a value; boolean,
float, negative, leading-zero, non-UTC and over-long values are rejected. Unlike
assets are never summed. Unknown costs or qualification stay unknown.

## Invariants preserved

- A consent is always `INACTIVE`. No activation, signing, admission, scheduler or
  provider-policy operation exists in this stage.
- Review and adoption write only the owned `consent_local` tables. They do not
  change holdings, allocation, consumed allowances, reservations, claims, pending
  recovery, stop history, breach state or another agent.
- Inactive preparation cannot reset or raise an existing budget. A stop and an
  unknown pending action stay visible and unchanged.

## Boundaries

- Local fixture work only. Live admission, execution and full P26 activation stay
  closed pending P20/P21 and the operational gates.
- No API route, UI, browser check or shared migration is added here.
- No signing path, provider call, wallet action, credential or policy wrapper.
- The shared `public` schema is unchanged. Owned tables live in the
  `consent_local` schema of the run-labelled test database.
- P17 shared wiring, P05 provider safeguards, P25 leased admission/execution and
  quant P14 remain protected. Shared files stay read-only.

## Evidence classification

Review and adoption behavior here is local application behavior under authored
synthetic terms, approvals and fixtures. It is not provider enforcement, live
wallet state, a real transport result or a signed approval. Direct SQL inspection
of saved rows is part of the evidence. See `docs/qualification/inactive-consent/`.
