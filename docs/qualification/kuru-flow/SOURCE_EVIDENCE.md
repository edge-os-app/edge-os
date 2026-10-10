# Source evidence and pins

Every material claim in this package points to one source below. Each entry gives the exact URL, the check date and, for source code, the pinned commit and content hash. Prepared 2026-10-10.

Evidence vocabulary follows [Edge OS research contracts](../../EDGE_OS_RESEARCH_CONTRACTS.md#3-evidence-vocabulary): `VERIFIED FACT`, `PRODUCT OR SPONSOR STATEMENT`, `INFERENCE`, `HYPOTHESIS`, `UNKNOWN`.

## 1. Retrieval tools used

| Tool | Result |
|---|---|
| `context7` (`resolve-library-id`) for "Kuru" and "Privy" | **Unavailable.** The socket connection closed unexpectedly on both calls. No Context7-derived claim is made. Fallback: official first-party documentation. |
| `webfetch` | Used for the official Kuru and Privy pages below. |
| `websearch` | Available. Not required for the primary sources. |
| Exa | **Not available** to this worker. No `exa` binary, no Exa MCP server, no `EXA_*` key. |

This records the fallback the design and packet permit: "If Kuru has no exact matching library, use official Kuru docs/source and record that fallback."

## 2. Kuru official documentation (checked 2026-10-10)

| ID | URL | Supports | Type |
|---|---|---|---|
| K1 | https://docs.kuru.io/kuru-flow/flow-overview | Flow is a routing/aggregator API over all Monad liquidity | `PRODUCT OR SPONSOR STATEMENT` |
| K2 | https://docs.kuru.io/api-reference/calculate-best-path-quote | `POST /api/quote` request/response schema, fields, auth options | `VERIFIED FACT` (documentation) |
| K3 | https://docs.kuru.io/api-reference/generate-jwt-token | `POST /api/generate-token`; JWT with 1 RPS, burst 1 | `VERIFIED FACT` (documentation) |
| K4 | https://docs.kuru.io/contracts/Contract-addresses | Mainnet `143` addresses including `KuruFlowEntrypoint`, `KuruFlowRouter`, `KuruForwarder`; testnet `10143` list without Flow contracts | `VERIFIED FACT` (documentation) |
| K5 | https://docs.kuru.io/product/flow | Flow product description | `PRODUCT OR SPONSOR STATEMENT` |
| K6 | https://docs.kuru.io/llms.txt | Documentation index used to discover the Flow pages | `VERIFIED FACT` (documentation index) |

Documentation is a rolling source with no published version. It describes intended interfaces. It does not prove deployed behavior.

## 3. Kuru Flow contract source (pinned)

Repository: `https://github.com/Kuru-Labs/Kuru-contracts-flow-public`
- Default branch `main`, pinned commit `70bc0c93c073f78697b99848eedefbf5dbe698c7` (committer date 2026-04-15T05:38:02Z), repo not archived, `pushed_at` 2026-04-15.
- License: GitHub reports `NOASSERTION`; the file headers carry `SPDX-License-Identifier: BUSL-1.1` (Business Source License). **No code is copied into this package.** Only bounded quotes of interface names and two minimal structs are used, with attribution.

| ID | Path at pinned commit | SHA256 (raw bytes) | Supports |
|---|---|---|---|
| S1 | `src/entrypoint/KuruFlowEntrypoint.sol` | `15e19667ee20389b396a51143dccf7bbd31a701c610f1d78978c84f3b7fd1841` | `executeSwap`/`executeSwapWithReceiver`; router call; fee rules; min-output-after-fees; `minAmountOut = 0`; approval reset |
| S2 | `src/entrypoint/KuruFlowEntrypointTypes.sol` | `44d913012de00a2814e62f1e9c45c4408c8407c0457325de41efabecd05df1ac` | `SwapIntent` and `FeeCollection` struct fields |

Bounded quote of `SwapIntent` (S2): input token `tokenUserSells`, exact input `amountUserSells`, output token `tokenUserBuys`, minimum received `minAmountUserBuys`. The struct has no maximum-output or deadline field.

Limit: the pinned source is the public Flow repository. It does not prove the deployed `143` bytecode matches this source. Confirm the deployed bytecode identity before qualification.

## 4. Privy official documentation (checked 2026-10-10)

| ID | URL | Supports | Type |
|---|---|---|---|
| P1 | https://docs.privy.io/controls/policies/example-policies/ethereum | Policy rules on `ethereum_transaction.chain_id`, `.to`, `.value`; `ethereum_calldata` fields including `function_name` and ABI argument paths | `VERIFIED FACT` (documentation) |
| P2 | https://docs.privy.io/api-reference/wallets/ethereum/eth-sign-transaction | `eth_signTransaction` returns broadcast-capable `signed_transaction` RLP; idempotency on 4xx/5xx; policy violations allow same-key retries | `VERIFIED FACT` (documentation) |

Documentation limit: P1 shows ABI-argument matching. It does **not** show equality or bound checks on opaque `bytes` arguments such as the Flow `program`. Whether the policy can enforce any bound on the opaque route stays `UNKNOWN`.

## 5. Retained records referenced

| ID | Path | Status | Use and limit |
|---|---|---|---|
| R1 | `docs/qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md` | Accepted bounded evidence | Sign-only controls and A removal. Does not prove Kuru, mainnet, creation recovery or cross-user backend isolation. |
| R2 | `docs/qualification/p16/README.md` | Accepted with open items | Qualification matrix and the exact per-control status. |
| R3 | `.scratch/p16-integrated.md` (controller workspace) | Accepted local integration | P16 candidate identity and scope. |
| R4 | `docs/EDGE_OS_RESEARCH_CONTRACTS.md#exit-cap-q01-permission-model-qualification` | Requirements | EXIT-CAP-Q01 direction and enforcement boundary. |
| R5 | `docs/contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md` | Frozen contract | Identity, amounts, mandates, queue, stops, removal. |
| R6 | `docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#exact-monad-operation` | Accepted | Flow fixed-input direction and its limits. |
| R7 | `docs/adr/0006-kuru-flow-initial-spot-adapter.md` | Accepted | Fixed-input Flow direction; no resting-order action. |
| R8 | `docs/prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#5-probe-b-delegated-monadkuru-action` | Planning | Probe B required configuration, all `UNSET`. |
| R9 | `docs/planning/EDGE_OS_RELEASE_CUT_2026-10-10.md` | Accepted | Probe B as the application's controlled-execution qualification. |

Retained prior research:
- `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` (primary workspace) - Privy models, Monad support, Assensus reference. Dated 2026-09-29/30. Limit: an Assensus X Layer testnet sign-only proof, not Monad-Kuru.
- `docs/research/01_MONAD_CAPABILITY_AND_INTENT_MAP.md` (primary) - Kuru and Privy sponsor capability maps. Dated 2026-09-27/2026-09-08.
- `docs/research/12_MONAD_KURU_POST_CORE_EXTENSION_EVIDENCE.md` (primary, checked 2026-10-02) - Kuru primitives including the Flow integrator fee route and the JWT quote requirement.

These retained notes need the fresh checks above; the fresh checks are recorded in sections 2 to 4.

## 6. Claim-to-source map

| Claim | Source |
|---|---|
| Flow entrypoint/router on mainnet `143` only | K4 |
| Testnet `10143` has no documented Flow contract | K4 |
| Quote API schema, auth, rate limit | K2, K3 |
| Fixed input and minimum received in the intent | S1, S2 |
| No maximum-output field | S2 |
| Router called with `minAmountOut = 0`; post-fee check inside the entrypoint | S1 |
| ERC-20 approval set then reset to `0` | S1 |
| Native input requires `msg.value >= amountUserSells` | S1 |
| Policy supports chain/`to`/`value`/decoded-calldata conditions | P1 |
| Opaque `program` enforcement unproven | P1 (absence of bytes-equality example) |
| `eth_signTransaction` returns broadcast-capable bytes; idempotency behavior | P2 |

Each claim is bounded to what its source shows. A documented capability is not a live proof.
