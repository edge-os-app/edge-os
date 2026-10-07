# P16 wallet qualification

Status: **PREPARATION ONLY. P16 remains unqualified.** The harness uses authored fakes. It makes no network calls, reads no environment values, and stores no credentials.

## Run the offline checks

From the repository root, run:

```sh
python3 -B -m unittest discover -s docs/qualification/p16 -p 'test_*.py' -v
python3 -B docs/qualification/p16/qualification.py
```

The tests check local identity binding and same-token position separation. They check setup recovery after a lost response and restart. They check cancellation and direct fake-provider denial. They check signer removal, owner access, retained pending records, and B's access. The demo prints `AUTHORED_FAKE_ONLY`, `provider_executed: NOT_RUN`, and `owner_observed: NOT_RUN`.

The harness has no live provider mode. It cannot read credentials or contact Privy. The on-disk JSON ledger is temporary test data. Tests create it under a temporary directory and remove only that directory.

## Qualification matrix

| Accepted check | Source inspected | Harness executed | Provider executed | Owner observed | Current status and consequence |
|---|---|---|---|---|---|
| WAL-Q19: A and B have separate wallets under one owner; C has a separate owner; bind owner, agent, wallet, network, position and same-token holdings | P15 wallet contract; WAL-Q19; ADR 0007; current Privy wallet owner and signer docs | PASS, authored fixtures only. Mutating each binding ID denies locally. A's fake signer is attempted directly against B and C. Same-token positions retain separate wallet and position identities. | NOT RUN | NOT RUN | BLOCKED by provider and owner authorization. This proves no Privy or application behavior. |
| WAL-Q20: stable setup identity, lost response, cancellation, retry and restart do not duplicate a wallet | P15 setup states; current Privy create, idempotency and wallet-list APIs | PASS, authored fake only. A lost create response leaves `UNKNOWN`; restart repeats the same request/key and binds one fake wallet. Local cancellation after the lost response stays `UNKNOWN`. | NOT RUN | NOT RUN | BLOCKED by provider and owner authorization. The current source docs expose an app-unique `external_id`, lookup by that ID, and a 24-hour idempotency key. The selected account and exact recovery flow remain untested. |
| WAL-Q24: remove A's signer, keep owner access and pending records, deny new A signing, and leave B active | P15 removal/recovery rules; current Privy owner and signer-removal docs | PASS, authored fake only. | NOT RUN | NOT RUN | BLOCKED by provider and owner authorization. No live owner recovery or signer removal has been observed. |
| Separate policy administration from agent signing | P15 enforcement boundary; current Privy owner/signer and policy docs | NOT COVERED | NOT RUN | NOT RUN | UNQUALIFIED. The harness does not create or inspect policies. The authorized runner must prove the agent key cannot edit policy or signer bindings. |
| Independently deny a wallet-specific sign request at Privy | P15 WAL-Q19; current Privy wallet RPC, authorization-key, and signer docs | PASS only in the explicit fake; local and fake-provider results stay separate | NOT RUN | NOT RUN | BLOCKED by provider and owner authorization. A fixture denial is not provider evidence. |

`SOURCE_INSPECTED` means a current document or accepted contract describes the behavior.

`HARNESS_EXECUTED` means this Python test ran against invented fixtures. `PROVIDER_EXECUTED` requires an approved call to the selected Privy app and wallet. `OWNER_OBSERVED` requires the applicable test owner to take part and confirm the action. A source-inspected or harness-executed result does not imply a provider or owner PASS.

## Current source findings

The accepted contract requires one user-owned wallet per agent. It requires every action and position to bind to owner, agent, wallet, network and position. Setup must retain one identity through `UNKNOWN` and reconcile before retry. Signer removal must preserve owner access and pending or residual records. It must deny later agent signing. See [P15 wallet contracts](../../contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md), [WAL-Q19, WAL-Q20, and WAL-Q24](../../EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks), and [ADR 0007](../../adr/0007-separate-user-owned-agent-wallets.md). These are accepted requirements, not runtime evidence.

Privy's current docs, checked on 2026-10-07, describe these mechanisms:

- [`POST /v1/wallets`](https://docs.privy.io/api-reference/wallets/create) creates an Ethereum wallet for a user owner. `external_id` is unique per app and write-once. The API accepts the `privy-idempotency-key` header.
- [`GET /v1/wallets`](https://docs.privy.io/api-reference/wallets/get-all) can filter by `external_id`, `user_id`, chain type, or address. Read every returned page. Bind only one record with the expected owner, chain type, and external ID. Zero, multiple, mismatched, or unavailable results stay unresolved.
- [Idempotency keys](https://docs.privy.io/api-reference/idempotency-keys) prevent duplicate request execution for 24 hours. Wallet creation replays its cached 4xx/5xx response for the same key. A 5xx does not prove that the request created no wallet. Reconcile by `external_id` before any new key or request.
- Privy's [EVM network guide](https://docs.privy.io/basics/react/advanced/configuring-evm-networks) allows app configuration for EVM chains. The [EVM wallet-action chain list](https://docs.privy.io/wallets/actions/swap/overview) lists Monad `143` and Monad Testnet `10143`. This confirms documented chain support and identifiers. It does not prove the selected account's wallet, signer, policy, or RPC configuration.
- The [EVM `eth_signTransaction` API](https://docs.privy.io/api-reference/wallets/ethereum/eth-sign-transaction) returns signed transaction bytes without broadcasting. Treat those bytes as broadcast-capable. Never save or broadcast them.
- Privy's [Ethereum policy examples](https://docs.privy.io/controls/policies/example-policies/ethereum) document `ethereum_transaction.chain_id`, `to`, and `value` conditions. The [template guide](https://docs.privy.io/controls/policies/template-variables) documents `{{wallet.address}}`. The [policy overview](https://docs.privy.io/controls/policies/overview) says unmatched requests default to deny. These sources support a minimal self-call rule. They do not prove the selected policy behaves as configured on Monad Testnet.
- Privy's [user-owner configuration](https://docs.privy.io/controls/authorization-keys/owners/configuration/user) and [signer removal guide](https://docs.privy.io/wallets/using-wallets/signers/remove-signers) describe user ownership and signer revocation. The provider and owner still need to pass the live checks.

No Privy SDK or dependency is installed. No Privy endpoint has been called.

## Prior implementation patterns checked

These sources informed the check design. No source code was copied.

- Assensus commit `02860cc5daf46d49f8b6a8ac8a524e0af7ac0b0a`: `docs/assensus/spike-gates.md`, section “Privy constrained Agent Signer gate result,” records a user-owned signer proof on X Layer Testnet. Its limit is X Layer, not Monad or Kuru. `services/api/app/adapters/privy_agent_signer_execution.py` submits `eth_sendTransaction`; this ticket uses sign-only calls and does not reuse that path.
- Veridex commit `8274245d971d9805c4e9bde295018bc5616dc0a2`: `veridex/dust_execution/privy_provisioning.py` persists a stable external recovery ID before creation and fails closed on ambiguous reconciliation. `privy_control_plane.py` keeps signing behind a fake client and checks policy/quorum bindings. Those are prior project patterns. Its offline tests do not prove Edge OS or live Privy behavior.
- The worker checked the private research note `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` in the controller workspace. Its older setup-blocked result for Assensus is superseded by the later, narrow X Layer testnet proof. Neither project qualifies Monad–Kuru execution.

## Later provider recipe

Run these steps only after the builder approves the development app, owners, provider operations, and call cost. The worker saved the current request outside the candidate. It requests no purchase and sets operation counts. Keep secrets outside this repository and model context.

1. Use one isolated Privy development app. Use two test owners. Use Monad Testnet `10143` only.
2. Create three unfunded EVM wallets. Assign wallets A and B to owner 1. Assign wallet C to owner 2.
3. Create three independent authorization keys. Attach key A only to wallet A, key B only to wallet B, and key C only to wallet C. The wallet owner approves each signer.
4. Keep policy administration separate from the agent keys. The owner or approved administrator creates the test policies.
5. Attach one default-deny policy to each wallet. Each policy has one allow rule for `eth_signTransaction`. Require chain ID `10143`, recipient `{{wallet.address}}`, and value `0x0`. Add no other allow rule. Inspect the complete policy and owner before signing.
6. Use a sign-only type-2 transaction. Set chain ID to `10143`, recipient to the same wallet, value to `0x0`, data to `0x`, and gas limit to `21000`. Use a valid test nonce and fee fields supplied by the approved runner. Do not call `eth_sendTransaction` or another broadcast operation. Never broadcast or save signed bytes.
7. Sign once with key A on wallet A. Then send the same request directly to wallets B and C with key A. Bypass the application's local ID guard. Record local and provider results separately.
8. Deliberately drop A's successful create response. Restart the runner from its saved setup record. Query `GET /v1/wallets?external_id=<A external ID>`. Inspect all pages. Bind exactly one wallet with the expected owner, chain type, and external ID. If none appears, retry the same request and key within 24 hours. If the result is ambiguous, keep `UNKNOWN` and stop. Never make a new wallet to resolve uncertainty.
9. Cancel one setup before send. Confirm that no provider wallet exists. Then lose a response after provider acceptance. Cancel locally. Confirm that setup stays `UNKNOWN` until reconciliation. Cancellation does not undo a provider request.
10. Have owner 1 remove key A once. Sign the safe request once as owner 1. Retry it with key A and record the provider denial. Sign once with key B on wallet B. Keep pending and residual records unchanged.
11. Retain redacted status codes, opaque evidence references, needed identity hashes, timestamps, safe transaction fields, and before/after owner and signer state. Do not retain credentials, authorization signatures, tokens, headers, unredacted responses, or signed bytes. Stop only the runner. Remove only its temporary files. Keep wallets, policies, keys, and evidence.

This recipe does not qualify policy administration, real app authentication/storage, funded behavior, Kuru, position-inventory enforcement, Monad mainnet, a transaction broadcast, or swap execution. A provider denial from a local fake stays a fixture PASS.
