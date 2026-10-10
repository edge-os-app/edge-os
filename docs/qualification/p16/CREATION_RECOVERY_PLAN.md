# P16 remaining qualification plan: owner-linked creation, recovery and backend isolation

Prepares the smallest usable qualification plan for P16's unfinished owner-linked creation, lost-response/restart and actual-backend cross-user authorization checks. Reuses the accepted one-owner signing/removal evidence. Prepared 2026-10-10.

Scope: **preparation only**. No live action is authorized here. Full P16 (issue #14) stays **OPEN**. This plan does not unlock P17, P20 or P21. Sources: [README.md](README.md) and the [provider signing result](PROVIDER_SIGNING_RESULT_2026-10-08.md).

Evidence classes used below:

- `SOURCE_INSPECTED` means a current document or accepted contract describes the behavior.
- `HARNESS_EXECUTED` means the offline Python test ran against invented fixtures.
- `PROVIDER_EXECUTED` requires an approved call to the selected Privy app and wallet.
- `OWNER_OBSERVED` requires the applicable test owner to take part and confirm the action.

A source-inspected or harness-executed result does not imply a provider or owner PASS.

## 1. Existing proof versus remaining gaps (WAL-Q19, WAL-Q20, WAL-Q24)

The accepted contract requires one user-owned wallet per agent and binds every action and position to owner, agent, wallet, network and position. Setup must persist uncertainty before sending, retain one identity through `UNKNOWN`, and reconcile before retry. Signer removal must preserve owner access and pending or residual records and must deny later agent signing. See [P15 wallet contracts](../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md#wallets-ownership-and-flows), [WAL-Q19, WAL-Q20 and WAL-Q24](../EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks) and [ADR 0007](../adr/0007-separate-user-owned-agent-wallets.md). These are accepted requirements, not runtime evidence.

| Check | Accepted requirement | Existing evidence (bounded) | Remaining gap | What the future check can prove |
|---|---|---|---|---|
| WAL-Q19 wallet-specific authority | Prepare and sign a B-wallet action under A's execution identity with altered wallet/position IDs; deterministic ownership checks and independently scoped signing access deny it. | `PROVIDER_EXECUTED` for one owner: A and B signed their own calls, A's signer was refused on B, the removed A signer was refused. `HARNESS_EXECUTED`: local binding rejects a changed owner/agent/wallet/network/position. | Cross-user **application** authorization is `NOT RUN`. The provider signer controls cover one owner only. | A real-backend denial of owner B's valid request against owner A's wallet binding, with no persisted mutation and no provider call. Proves the application derives owner from verified identity, not from a request field. |
| WAL-Q20 creation recovery | Cancel/fail wallet creation or lose its response; reconcile and resume the same setup record and wallet identity; no duplicate wallet, automatic funding, signer access or activation follows. | `PARTIAL` historical: one server-API create response was dropped; one exact query recovered one record; an exact owner-quorum read proved the saved user was the sole member, threshold 1, no extra keys or groups. `HARNESS_EXECUTED`: lost response, malformed response, process interruption, restart, ambiguous/unavailable lookup and the 24-hour retry boundary. | React SDK wallet creation/recovery is not qualified. Cancellation before and after dispatch is not run against the selected route. The harness is an authored fake, not provider evidence. | The selected owner-linked creation route keeps one setup identity through response loss, cancellation, process death and restart, with no duplicate wallet and no signer access or activation. |
| WAL-Q24 removal and owner access | Remove A's signer, preserve owner wallet/withdrawal access and pending/residual records, and deny new A submissions. B's permission and holdings stay unchanged. | `PROVIDER_EXECUTED` for one owner: one A signer removal, owner-positive A signing after removal, removed-A refusal and B signing after removal. `HARNESS_EXECUTED`: removal preserves owner access, a pending record and B's signer. | Pending-record recovery and residual-exposure reconciliation were not tested. | That owner recovery keeps pending and residual records visible and B unaffected, while the removed signer stays denied. |

**Reuse rules.** Reuse only the exact compatible completed controls. Do not repeat the six consumed sign-only calls or the consumed A removal. A future signing or removal request needs its own scoped authority; previously consumed P16 permissions are historical, not reusable allowances.

## 2. Owner-linked creation route and pinned inputs

**Login creates no wallet.** The web config sets `createOnLogin: "off"` for both chains: `apps/web/lib/privy-config.ts` sets `embeddedWallets.ethereum.createOnLogin = "off"` and `embeddedWallets.solana.createOnLogin = "off"`, and `loginMethods = ["email"]`. The test `apps/web/tests/privy-config.test.ts` asserts both values and that no wallet login method is offered. A connected wallet is not an identity; only the verified `sub` identifies a user ([P01 ownership](../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md#ownership)).

**Current app state.** The application has no wallet-creation call. A search of `apps/web` finds `createOnLogin` only in the config and its test; there is no `createWallet` or `useWallets` call. Wallet creation is therefore **not yet implemented**, and this plan prepares it.

Two provider routes can create an owner-linked wallet. Keep them separate:

| Route | Mechanism | Owner binding | Recovery references | Limits |
|---|---|---|---|---|
| A. React SDK embedded wallet | `useCreateWallet().createWallet()` from `@privy-io/react-auth`; the client-side SDK creates a wallet owned by the authenticated user by default. | The authenticated user. | The returned `Wallet` object (its server wallet ID and address). | No provider idempotency key and no `external_id` on this route. A lost response that yields no exact ID stays `UNKNOWN`. HD/additional addresses do not prove signing isolation. |
| B. Server REST `POST /v1/wallets` | `POST https://api.privy.io/v1/wallets` with `chain_type: "ethereum"`, `owner.user_id` = the owner's Privy DID, and a customer `external_id`. | `owner.user_id` controls the wallet; `entity` is attribution only and cannot be changed after set. | `GET /v1/wallets?external_id=...` read across every page; the `privy-idempotency-key` header (24-hour window; wallet create caches 4xx **and** 5xx responses). | `external_id` is URL-safe `[a-zA-Z0-9_-]`, at most 64 characters, unique per app, write-once. A 5xx does not prove no wallet was created. |

**Selected route.** The retained P16 profile selects the owner-linked embedded-wallet flow: authenticate the owner, bind the exact linked wallet ID and address on the server, then request restricted signer consent ([README linked-wallet follow-up](README.md#linked-wallet-follow-up-2026-10-08)). The creation step for that flow is Route A (React SDK). The historical partial recovery used Route B (server REST). The future check exercises the route that P17 records; newer rolling documentation does not silently change that selection.

**Pinned identities.** Record these exact identities in the future packet:

- App web dependency `@privy-io/react-auth` `3.47.0` (`apps/web/package.json`, `apps/web/package-lock.json`).
- The P16 offline harness (`docs/qualification/p16/qualification.py`) has **no** Privy SDK and no live mode. It is an authored fake.
- The historical private helper and its SDK version are private worker evidence, not a shared input. Rolling provider documentation is not the pinned SDK.

**Separate creation from permission and activation.** Wallet creation grants no signer access and starts no trading ([P15](../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md#wallets-ownership-and-flows)). A later signer attachment and any activation are separate steps with their own authority.

## 3. Saved-identity and reconciliation sequence

Contract setup states: `REQUESTED`, `PENDING`, `UNKNOWN`, `CONFIRMED`, `FAILED`. The offline harness adds a local-only `CANCELLED`. Persist the setup identity and its idempotency key **before** dispatch, so a crash after provider acceptance cannot turn an attempted setup into a cancellable unsent setup. The authored offline model is in `docs/qualification/p16/qualification.py` (`SetupManager.prepare`, `_attempt`, `_reconcile`, `cancel`); it is not provider evidence.

| Event | Sequence | Result |
|---|---|---|
| Response loss (Route B) | Persist `UNKNOWN`, keep the exact `external_id` and idempotency key, then reconcile with `GET /v1/wallets?external_id=...` across all pages. Bind only one record with the expected owner, chain type and `external_id`. | `CONFIRMED` only on one exact match. Zero, multiple, mismatched or unavailable results stay `UNKNOWN`. A duplicate wallet is never created to resolve uncertainty. |
| Response loss (Route A) | Persist `UNKNOWN` with the local setup identity. Reconcile only against an exact returned server wallet ID or address for the authenticated user. | If no exact ID is available, stay `UNKNOWN`. Do not retry to resolve uncertainty. |
| Cancel before dispatch | Move `REQUESTED` to `CANCELLED`. | No provider call. No wallet. |
| Cancel after dispatch | Keep `UNKNOWN`. Cancellation cannot undo a sent request. | Reconcile before any further action. |
| Process death / restart | Reload the saved record from durable storage; resume the same identity. | One identity across restart. Reconcile before retry. |
| Retry after no match | Reuse the same key only inside the idempotency window and only when identity is uniquely established. | Outside the window, stay `UNKNOWN`. |

**Do not import REST guarantees into React.** Route B's `external_id`, idempotency replay and page-filtered reconciliation do **not** exist on the React `createWallet` route. Route A reconciles by exact returned ID only. HD or additional addresses do not prove signing isolation.

## 4. Actual backend boundary for owner/agent/wallet/network/position tampering

Inspect current code before naming a route. What exists today (`SOURCE_INSPECTED`, read-only):

- `apps/api/src/edge_os_api/core/authentication.py`: `require_principal` verifies the Privy access token (ES256, issuer `privy.io`, app audience, required claims) and derives `user_id` from the verified `sub`. It rejects a body-supplied owner; the server creates the `users` row on first sight.
- `apps/api/src/edge_os_api/main.py`: every route except `/healthz` and `/readyz` sits under the `require_principal` dependency. Registered routes are `/v1/me`, `/v1/interpreter`, `/v1/spot-replays`, `/v1/research/*`, `/v1/strategies/*`, `/v1/operations/*`, plus the `account-views` and `agent-context` routers.
- `apps/api/src/edge_os_api/accounts/views.py` and `agent_context/controls.py`: reads and writes are filtered by `principal.user_id`; a foreign or absent record returns `404`, the same body as a missing record.

**Absent routes.** There is **no** wallet create/bind route, **no** signer attach/remove route, and **no** agent/wallet/network binding route. The records table is generic (`records/models.py`); account-view rows are seeded directly in tests (`apps/api/tests/test_account_views.py` `_seed`) and served read-only. Existing Research and account tenancy tests (`apps/api/tests/test_ownership.py`, `test_account_views.py`) prove owner-scoped **record** reads only. They do **not** prove wallet tenancy.

**Required future acceptance seam** (to be built under a separate authorized ticket; not implemented here):

1. A wallet-binding route that derives `owner_id` from the verified principal, validates the wallet belongs to that owner on the server, and persists one owner-scoped binding with `wallet_id` and `network_id`.
2. Positive control: owner A binds A's wallet; a read-back under A matches exactly.
3. Negative control: owner B sends a **valid** request against owner A's binding. Require a server-side denial, **no** persisted mutation and **no** provider call.
4. Use the real PostgreSQL harness (`apps/api/tests/conftest.py` starts a real container and a test signing key) with two independently authenticated owners. A fixture-only check does not make a production claim.

## 5. Owner recovery

Prepare owner recovery with pending and residual records retained and B unaffected. Reuse the exact compatible completed evidence rather than repeating consumed calls: A signer removal, owner-positive A signing after removal, and B signing after removal ([provider signing result](PROVIDER_SIGNING_RESULT_2026-10-08.md), calls 4 to 6).

The future check prepares:

- The verified owner restores and keeps access to A's wallet, and can still sign for A after removal.
- A's pending and residual records remain visible after removal.
- A's removed signer stays denied; new A submissions stay blocked until an owner-authorized rebinding is verified.
- B's permission and holdings stay unchanged.

Pending-record retention and residual-exposure reconciliation are **not yet proved** (WAL-Q24 gap). They require the selected-route recovery step and owner participation.

## 6. Future run checklist

Fill every field before a live check. Leave a field `BLOCKED` or `UNRESOLVED` if it is unavailable; do not invent a value.

- **Preconditions.** An approved live packet; one authenticated owner; the exact selected app; the exact network; two unfunded user-owned wallets; the P16 signing/removal result reused, not repeated.
- **Exact source and configuration identities.** Base and candidate SHAs; `@privy-io/react-auth` version; the selected creation route; the app ID scope; the network id (`143` mainnet or `10143` testnet). P16 ran on testnet `10143`.
- **Observable pass/fail evidence.** Per action: the request identity, the returned identity (wallet ID/address), the reconciliation result and the owner confirmation. Separate raw provider responses from any local classifier.
- **Request and counter accounting.** Keep a fresh run ledger. Retained historical counters are the six sign attempts, one A removal, one owner-positive A attempt, five purpose wallet checks, five owner verifications; wallet-list `5` (original `4/4` plus one approved exception); owner-quorum `2/2`; SDK exact-wallet GETs `2/2`; action-time session refreshes `2/3` plus one startup; and the historical analytics `2/1` overrun. Do not reset or extend these; the future run keeps its own ledger.
- **Owner participation.** Record the exact owner actions and confirmations. The run is not a PASS without the applicable owner observation.
- **Provider traffic visibility.** State the observed request set and its source. Visibility remains limited to retained observations and local ledgers; there is no independent provider audit.
- **Cleanup.** Remove only run-owned resources (the test database/container labelled for that run, and temporary local files). Never delete wallets, keys, policies, owners or evidence.
- **Stop conditions.** Stop on a provider payment requirement, an unsupported operation, an unavailable exact identity, an exceeded request ceiling, any unresolved `UNKNOWN` that needs a new wallet to resolve, or any change to accepted behavior. Preserve state and report.

## 7. NOT_AUTHORIZED live release

This section is a template for the live check. It authorizes nothing. Leave every unavailable field `BLOCKED` or `UNRESOLVED`. Do not invent counts, extend historical budgets or request secrets in reports.

| Required field | Value |
|---|---|
| Account / app | `UNRESOLVED` |
| Owner identity | `UNRESOLVED` |
| Network | `UNRESOLVED` (P16 evidence is testnet `10143` only) |
| Route | `UNRESOLVED` (creation route and any execution route unselected) |
| Allowed endpoints and actions | `BLOCKED` |
| Allowed action/request counts | `BLOCKED` — no count is authorized |
| Financial limits | `$0` additional spend; stop on any payment requirement |
| Owner consent | `BLOCKED` |
| Provider traffic visibility | `UNRESOLVED` — limited to retained observations and local ledgers |

Previously consumed P16 permissions are historical, not reusable allowances. No live Privy request, login, wallet creation, signing, removal, funding, broadcast, purchase, deployment or deletion is authorized by this plan.

## 8. Later shared backend wiring after the P05 lease release

P05 owns shared API, storage, migration and web wiring. This local preparation is usable **before** that release. The full live P16 stays incomplete until:

1. P05 releases the shared-wiring lease.
2. An authorized ticket adds the wallet-binding route (or the selected creation seam) and its tests under that lease.
3. The two-owner backend check in section 4 runs against real PostgreSQL and passes with positive and negative controls.
4. The selected owner-linked creation/recovery check in section 3 runs with the exact pinned identities.
5. Both original independent internal reviews PASS one committed candidate and the separate gate returns PASS.

A documentation PASS does not complete P16 and does not unlock P17, P20 or P21. Issue #14 stays OPEN.

## References

- [P15 wallet contracts](../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md)
- [WAL-Q19, WAL-Q20, WAL-Q24](../EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks)
- [ADR 0007](../adr/0007-separate-user-owned-agent-wallets.md), [ADR 0008](../adr/0008-python-api-postgresql-nextjs-privy-auth.md)
- [P01 application auth and storage profile](../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md)
- [P16 README](README.md) and [provider signing result](PROVIDER_SIGNING_RESULT_2026-10-08.md)
- [Release cut](../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md), [implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md)
- Privy current docs (checked 2026-10-10): `POST /v1/wallets` (`https://docs.privy.io/api-reference/wallets/create`), external IDs (`https://docs.privy.io/wallets/wallets/external-ids`), idempotency keys (`https://docs.privy.io/api-reference/idempotency-keys`), create-a-wallet (`https://docs.privy.io/wallets/wallets/create/create-a-wallet`)
