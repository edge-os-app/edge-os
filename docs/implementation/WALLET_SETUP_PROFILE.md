# Wallet setup profile (P17 local preparation)

Task: `OC-P17-LOCAL-20261010-01`, issue [#22](https://github.com/edge-os-app/edge-os/issues/22).
Status: **local preparation only. Not production wiring.** The application exposes no wallet
setup route. This package creates no wallet, signer, funding, mandate activation, position or
trading action. External wallet creation and lookup are authored fakes, not provider evidence.
Full P17 stays open, and no live provider or financial action follows from this profile.

## Scope

New code lives in one owner-scoped package:

```text
apps/api/src/edge_os_api/wallet_setup/
  types.py         setup states, cancellation intent, networks, events, reasons, records
  provider.py      the wallet-creation boundary port and its evidence types
  persistence.py   the local `wallet_setup_local` schema and row helpers
  recovery.py      uncertain-setup reconciliation
  service.py       prepare, dispatch, cancel, resume and read
```

New tests live in `apps/api/tests/wallet_setup/`. New qualification material lives in
`docs/qualification/wallet-setup/`. Nothing else changes: no shared model, router, migration,
fixture, UI, contract, verifier map, lockfile, configuration, hook or script is edited. P05 keeps
the shared-file lease. P23 keeps execution ownership.

## Accepted inputs

- [P15 wallet, mandate and account contracts](../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md)
  and `docs/contracts/p15/contract.json`: wallet ownership, the five setup states, the one-wallet
  per-agent rule and the explicit Monad 143 / testnet 10143 network names.
- [P01 application, authentication and storage profile](P01_APPLICATION_AUTH_STORAGE_PROFILE.md):
  the verified `Principal`, owner-scoped uniqueness and the request-to-record boundary.
- [P16 creation and recovery plan](../qualification/p16/CREATION_RECOVERY_PLAN.md), sections 2 to
  4 and 8: the selected React creation route, no `external_id` and no provider idempotency, and
  the future two-owner backend seam. The new plan remains preparation.
- [ADR 0007](../adr/0007-separate-user-owned-agent-wallets.md) and ADR 0008.
- The existing verified [Principal](../../apps/api/src/edge_os_api/core/authentication.py) and
  immutable saved [StrategyRevision](../../apps/api/src/edge_os_api/records/models.py).

## Setup identity and authorization

`prepare_setup` persists one setup row before any creation-capable call. The row binds:

- the owner, taken from the verified `Principal`. A request body can never carry an owner
  (`extra="forbid"` at every depth).
- the agent identifier.
- the requested network (`143` or `10143`), an application binding.
- the exact owned saved strategy revision: `strategy_id`, `strategy_revision_id`,
  `content_sha256` and `manifest_sha256`, all resolved server-side from the owned
  `strategy_revisions` row.

A foreign or absent revision is `404`, the same body as a missing one. A second `prepare` for one
`(owner, agent)` with a different network or revision is `409 changed_setup_identity` and changes
nothing. A new request key never creates a second setup; an existing setup is returned instead.
`UNIQUE (owner_id, agent_id)` enforces one setup, and therefore one wallet binding, per agent,
including across independent processes. `UNIQUE (owner_id, wallet_id)` prevents one wallet from
binding to two agents of one owner.

## States, cancellation and evidence

Only the five accepted P15 states are stored: `REQUESTED`, `PENDING`, `UNKNOWN`, `CONFIRMED`,
`FAILED`. Cancellation is a separate intent (`NONE`, `REQUESTED_BEFORE_DISPATCH`,
`REQUESTED_AFTER_DISPATCH`). The P16 harness-only `CANCELLED` state is not added.

- A proved pre-dispatch cancellation moves `REQUESTED` to `FAILED` with reason
  `CANCELLED_BEFORE_DISPATCH` and causes zero creation calls.
- A post-dispatch cancellation records intent and keeps the setup uncertain. It cannot undo a
  dispatched request.

Every dispatch writes a `DISPATCH_INTENT` event and sets `creation_dispatched` in one commit
**before** the provider boundary. A crash, timeout or expired local claim therefore cannot make an
attempted setup look unsent, and a second process sees `creation_dispatched` and never calls
creation. Events are append-only. Denials are recorded in a separate `wallet_setup_denials` table,
never in protected setup state.

## Provider boundary and reconciliation

The selected React route returns only a client-side wallet object. It has no `external_id` and no
provider idempotency. The package therefore:

- binds a wallet only from an exact returned server wallet ID plus an independent provider lookup
  that matches the same wallet ID, the bound owner, an Ethereum chain type and a non-empty address.
- keeps `UNKNOWN` when the response is lost, the result is malformed, the lookup is unavailable or
  malformed, the match is wrong, or the wallet is already bound to another agent of the same owner.
- never selects a first or latest wallet and never creates a second wallet to resolve uncertainty.
- reconciles a retained exact late result after a restart only when the current lookup is identical
  to the retained result in wallet ID, owner, chain type and address. A changed address stays
  `UNKNOWN` with `RECONCILE_WRONG_IDENTITY`, so recovery never weakens the initial check.
- validates the runtime fields of a provider result before writing any event or binding, so a
  malformed result — a wrong type, or a malformed field inside a valid-looking `WalletEvidence` —
  records `UNKNOWN` with a sanitized reason (`MALFORMED_RESULT` or `RECONCILE_NO_MATCH`) instead of
  failing with a `500` or leaving the setup `PENDING` without a reason. A dataclass annotation does
  not validate a value.

The requested network stays an application binding. Provider evidence carries a chain type and
address only, because an Ethereum provider wallet is not inherently bound to one chain ID. No
mainnet or testnet support is inferred.

## Recovery and restart

A fresh process reloads the setup and binding history unchanged from `wallet_setup_local`. Tested
crash boundaries: during dispatch after the intent commit, and after the result commit but before
the binding commit. In both cases the setup stays uncertain, no second creation happens, and an
exact retained result reconciles to `CONFIRMED` without rewriting history.

## Local schema

Three tables in a dedicated `wallet_setup_local` metadata: `wallet_setups`, append-only
`wallet_setup_events` and `wallet_setup_denials`. `owner_id` follows the verified `users.id` by
application convention and carries no foreign key, so the local schema is self-contained and ships
no migration. The test harness creates these tables in its run-labelled database only.

## What this does not prove

This profile does not qualify a wallet provider, a React SDK creation or recovery path, a Monad
deployment, signer or policy enforcement, funding, positions, removal or recovery, or any live
owner access. A browser or live PASS is not claimed. Position accounting, live owner access and
removal remain future qualification under P16, P20 and P21.
