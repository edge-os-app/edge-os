# Funding reconciliation profile (local stage)

Owned package: `apps/api/src/edge_os_api/funding/`. This profile records the local, deterministic
named-agent funding reconciliation domain for P18 #26. It is a local stage. It is not API/UI wiring,
not a production migration and not a qualified funding transport.

## Responsibility

The package reviews one funding flow for a confirmed agent wallet, observes deposits through a
controlled boundary, credits only independently reconciled actual amounts exactly once, and reads the
funding history and confirmed available amounts. It records capital flows and never trades.

The package is application accounting over authored observations. It is not provider enforcement and
not chain evidence. It creates no transfer, provider call, signer, mandate, position or trading
action, and it writes no admission, allowance or stop record.

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Funding identities, capital-flow states, asset amounts and result records. |
| `accounting.py` | Pure amount/asset validation. No database access. |
| `observation.py` | The controlled deposit-observation boundary port. |
| `persistence.py` | Owned SQLAlchemy tables on `FundingBase`, in the `funding_local` schema. |
| `service.py` | Declare, prepare, observe/reconcile, read and available-credit functions. |

Application names describe responsibility. The ticket number is not a module name.

## Verified-owner rule

Every function receives `owner_id` from the verified `Principal`. A funding flow has no owner field
and a request body that asserts an owner, wallet, binding or balance is rejected at the request
boundary. Retrieval is owner-scoped; another owner's identity sees a `404`, the same as an absent
record. The confirmed agent-wallet binding is resolved from the accepted P17 wallet-setup interface
read-only; a missing or unconfirmed setup is a `404`.

## Amounts

An amount is `asset_id`, canonical unsigned base-10 `raw` string, and `decimals`. Amounts with
different `asset_id` values are never added. Native MON gas, the declared trading asset and compute
usage stay separate. Boolean, float, negative, leading-zero and over-long raw values are rejected. The
raw value is bounded to 78 digits (the owned ledger storage bound). Decimals and asset identity must
agree between the flow and the observation before any credit.

An asset id names its network (`monad:143/...` or `monad-testnet:10143/...`). Every declared or
observed asset must carry the wallet's own network prefix. An asset from another network is denied,
stays visible and never becomes available.

## Declared assets and flows

- `declare_funding_assets` persists the declared supported assets for one `(owner, agent)` confirmed
  wallet: a trading asset, a native gas asset and an optional compute asset. Every declared asset must
  belong to the requested Monad network, and the gas, trading and compute asset ids must be distinct.
  It is idempotent per agent; a changed declaration for an existing wallet is denied. This is the
  server-side "declared supported asset", not a per-request caller assertion.
- `prepare_funding` persists one reviewed flow before any transfer: kind, asset, declared raw amount,
  decimals, optional declared fee, reviewed transport, sender/recipient where known and a reference.
  Unknown fields stay `None`, never `0`. A reviewed transport or address is not a sent transfer. This
  stage prepares deposits only; a withdrawal is denied as unsupported.
- A declared fee keeps its own asset identity: it needs an explicit asset id, raw amount and decimals,
  and the fee asset must be a declared asset with matching decimals. A partially specified fee is
  rejected rather than stored under the transfer's asset. A native MON network fee therefore stays
  separate from a trading-asset fee.

## Observation boundary and once-only credit

`reconcile_funding` calls the caller-supplied `DepositObservationPort` for the exact wallet and
network. Every observation is appended to `funding_observations`, so request and actual amounts stay
distinguishable and the history is preserved. A `PENDING`, `FAILED` or `UNKNOWN` observation is
recorded and stays unavailable. Only a `CONFIRMED` observation credits an actual amount.

Credit is once-only on the exact `(wallet_id, network_id, asset_id, event_id)` identity:

- a unique constraint on `funding_credits` is the durable guard;
- a per-wallet PostgreSQL advisory transaction lock serializes concurrent reconciles;
- a replayed event, a concurrent process, a lost commit response or a fresh process finds the
  existing credit and records a `DUPLICATE` observation without a second credit;
- a conflicting terminal amount or fee for the same event fails closed with a recorded reason and
  never overwrites the credit;
- an existing credit that belongs to another owner or agent is not this owner's duplicate: the flow
  stays unavailable, no credit is added, and a `WRONG_OWNER` denial is recorded. A foreign event
  stays inspectable.

An observed fee keeps its own asset identity and declared decimals. A fee with no asset id, a
non-declared asset, malformed values or non-matching decimals is left unknown rather than stored
under the transfer's asset. The actual credit amount is unaffected.

Available credit counts only `CONFIRMED` credits, per wallet and asset. It never pools across wallets
or across asset classes.

## Fail-closed denials

A denial is recorded in `funding_denials` with a stable code. Codes include: `WALLET_NOT_CONFIRMED`,
`NETWORK_MISMATCH`, `UNSUPPORTED_ASSET`, `UNSUPPORTED_KIND`, `CHANGED_DECLARATION`,
`CHANGED_FLOW_IDENTITY`, `NO_MATCHING_FLOW`, `WRONG_OWNER`, `WRONG_WALLET`, `WRONG_NETWORK`,
`MALFORMED_OBSERVATION`, `CONFLICTING_TERMINAL_EVIDENCE`, `DUPLICATE_EVENT`, `DECIMALS_MISMATCH` and
`OBSERVATION_UNAVAILABLE`. An unsupported, wrong-network, wrong-wallet or wrong-owner deposit stays
inspectable and never becomes strategy capital.

## Invariants preserved

- A deposit is an external capital flow, not profit and not a swap attempt.
- A top-up changes confirmed funds only. It does not activate the agent, raise allocation, replenish a
  consumed limit, remove a stop or change expiry. This package writes no admission, mandate, stop or
  allowance record; a top-up control proves those digests are unchanged.
- No bridging, wrapping, card purchase, sponsorship or automatic conversion is selected.
- No cross-wallet pooled available balance.

## Boundaries

- Local fixture work only. Real funding, transport and shared wiring remain unqualified.
- No API route, UI, browser check or shared migration is added here.
- No signing path, provider call, wallet action or policy wrapper.
- The shared `public` schema is unchanged by this package. Owned tables live in the `funding_local`
  schema of the run-labelled test database and are created only by the test harness.

## Evidence classification

Funding behavior here is application accounting under authored synthetic observations. It is not
provider, chain or financial evidence. Direct SQL inspection of saved rows is part of the evidence.
See `docs/qualification/funding/`.

## Integration update (#58, 2026-10-12)

The local-stage statements above record the preparation history. In the #58 connected candidate the `funding_local` schema ships in migration 0008, and `funding/routes.py` mounts owner-scoped declaration, reviewed-deposit, reconcile and read routes. Asset identities come from the agent's saved revision; deposits are observed only through the server deposit port (authored fixture in local/test, unavailable in production). See `USER_RELEASE_INTEGRATION_PROFILE.md`. Fixture evidence only; live qualification stays NOT_RUN.
