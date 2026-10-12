# Source evidence and pins

Every material claim in this package points to one entry below. Each entry gives the exact URL, the check date and, for source code, the pinned commit and content hash. Prepared 2026-10-10.

Evidence vocabulary follows [Edge OS research contracts](../../EDGE_OS_RESEARCH_CONTRACTS.md#3-evidence-vocabulary): `VERIFIED FACT`, `PRODUCT OR SPONSOR STATEMENT`, `INFERENCE`, `HYPOTHESIS`, `UNKNOWN`.

## 1. Retrieval tools used

| Tool | Result |
|---|---|
| Context7 `resolve-library-id` "Monad" | Resolved `/websites/monad_xyz` (High reputation, 606 snippets). Used for network facts. |
| Context7 "Kuru Flow" / "Kuru" | Previous controller resolution returned unrelated libraries. **No unrelated Kuru ID was selected.** Official Kuru documents and source were used instead. This fallback is disclosed as the design and packet permit. |
| Exa (`web_search_exa`, `web_fetch_exa`) | Used for current Kuru and Monad official pages and the hackathon rules. |
| Public unauthenticated RPC | Used for bounded deployment verification only (6 calls). Log in section 4. |

## 2. Kuru and Monad documentation (checked 2026-10-10)

| ID | URL | Supports | Type |
|---|---|---|---|
| K1 | https://docs.kuru.io/contracts/Contract-addresses | Mainnet `143` Flow addresses; testnet `10143` list without Flow contracts | `VERIFIED FACT` (documentation) |
| K2 | https://docs.monad.xyz/guides/kuru-flow | Flow integration requires mainnet `143`; quote API and response example | `VERIFIED FACT` (documentation) |
| K3 | https://docs.kuru.io/kuru-flow/openapi.json | Single server `https://ws.kuru.io`; quote request/response; `path`/`buildResponse` example | `VERIFIED FACT` (documentation) |
| K4 | https://docs.monad.xyz/developer-essentials/network-information | Mainnet chain `143`; public RPC `https://rpc.monad.xyz`; WMON `0x3bd359C1...1433A` | `VERIFIED FACT` (documentation) |
| K5 | https://docs.monad.xyz/developer-essentials/testnet | Testnet chain `10143`; RPC `https://testnet-rpc.monad.xyz`; faucet `https://faucet.monad.xyz` | `VERIFIED FACT` (documentation) |
| K6 | https://www.monad.xyz/developers/hackathons/metropolis | Submission deliverables; no public mainnet-or-testnet network mandate | `VERIFIED FACT` (documentation) |

Documentation is a rolling source with no published version. It describes intended interfaces. It does not prove deployed behavior.

### Mainnet Flow addresses documented (K1, K4)

- `KuruFlowEntrypoint (Aggregator)` `0xb3e6778480b2E488385E8205eA05E20060B813cb`
- `KuruFlowRouter` `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2`
- `KuruForwarder` `0x974E61BBa9C4704E8Bcc1923fdC3527B41323FAA`

### Testnet addresses documented (K1, K5)

- `Router` `0x7EFbE105Ca7415dE98F96622173458ac1c054630`
- `Margin Account` `0xd029C2D98ff85D8F64799017fE00a59B1159CE02`
- `Kuru Forwarder` `0x681bB1508E14433b148a2549ba2726454aDc9BB4`
- `Kuru Deployer` `0xDacd06372cEb638640c9D8466A023b7362324e1A`
- `Kuru Utils` `0xE0841E0F06c5770C1D4930EC6C507ee33199C88C`

The testnet table lists **no Flow entrypoint or router**. The table's omission does not prove flow is unsupported on testnet at another address.

### Quote-schema conflict (NEW, dated 2026-10-10)

- K2 (Monad guide) documents a quote response with `output`, `minOut`, `transaction { to, calldata, value }` and `gasPrices`. It states `calldata` has no `0x` prefix.
- K3 (Kuru OpenAPI) documents a quote response with `output`, `path {}`, `buildResponse {}` and `gasPrices`.

The two public schemas disagree. Both are retained with their dates. Do not assume either. The `buildResponse`/`path` inner schema remains `UNKNOWN`.

### SDK address conflict (retained)

The Kuru SDK quickstart labels router `0x1f5A250c4A506DA4cE584173c6ed1890B1bf7187` and margin account `0xdDDaBd30785bA8b45e434a1f134BDf304d6125d9` as testnet. These addresses differ from the deployment table (section 2). Both are retained. They are conflicting examples that require fresh qualification, not proof of a testnet Flow path.

### Faucet and eligibility

- K5 links `https://faucet.monad.xyz`.
- `BUILDER-ONLY REFERENCE`: `/Users/degencodebeast/Projects/personal/monad-hack/docs/research/P21_TESTNET_FAUCET_CHECK_2026-10-10.md` (private workspace; SHA256 `5b3b5d54010ea59900bc0f45e97aeb7c80e21f961ec16ff6a4e71e8458c6ade7`) records a human web form and a supported agent claim API `UNKNOWN`. This package claims no faucet action and no eligibility.

## 3. Kuru Flow contract source (pinned)

Repository: `https://github.com/Kuru-Labs/Kuru-contracts-flow-public`
- Default branch `main`, pinned commit `70bc0c93c073f78697b99848eedefbf5dbe698c7` (committer date 2026-04-15T05:38:02Z).
- License: file headers carry `SPDX-License-Identifier: BUSL-1.1`. **No code is copied into this package.** Only bounded interface names and two minimal struct shapes are referenced, with attribution.

| ID | Path at pinned commit | SHA256 (raw bytes) | Supports |
|---|---|---|---|
| S1 | `src/entrypoint/KuruFlowEntrypoint.sol` | `15e19667ee20389b396a51143dccf7bbd31a701c610f1d78978c84f3b7fd1841` | `executeSwap`/`executeSwapWithReceiver`; router call; fee rules; min-output-after-fees; `minAmountOut = 0`; approval reset |
| S2 | `src/entrypoint/KuruFlowEntrypointTypes.sol` | `44d913012de00a2814e62f1e9c45c4408c8407c0457325de41efabecd05df1ac` | `SwapIntent` and `FeeCollection` struct fields |

Bounded quote of `SwapIntent` (S2): input token `tokenUserSells`, exact input `amountUserSells`, output token `tokenUserBuys`, minimum received `minAmountUserBuys`. The struct has no maximum-output and no deadline field.

Both `S1` and `S2` were re-fetched from the pinned commit on 2026-10-10 and their SHA256 values matched the retained P20 pins exactly.

Limit: the pinned source is the public Flow repository. It does not prove the deployed `143` bytecode matches this source. Section 4 records deployment presence, not equivalence.

## 4. Bounded read-only RPC verification (deployment evidence only)

Method: `POST` JSON-RPC to unauthenticated public endpoints, verified against K4/K5. No retries. No broadcast. Count = 6 of 30.

| # | Endpoint | Method | Params | Result |
|---|---|---|---|---|
| 1 | `https://rpc.monad.xyz` | `eth_chainId` | `[]` | `0x8f` (143) |
| 2 | `https://testnet-rpc.monad.xyz` | `eth_chainId` | `[]` | `0x279f` (10143) |
| 3 | `https://rpc.monad.xyz` | `eth_getCode` | `0xb3e6778480b2E488385E8205eA05E20060B813cb` | non-empty (`0x6080604052...`) |
| 4 | `https://rpc.monad.xyz` | `eth_getCode` | `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` | non-empty (`0x6080604052...`) |
| 5 | `https://testnet-rpc.monad.xyz` | `eth_getCode` | `0x7EFbE105Ca7415dE98F96622173458ac1c054630` | non-empty (`0x6080604052...`) |
| 6 | `https://testnet-rpc.monad.xyz` | `eth_getCode` | `0xb3e6778480b2E488385E8205eA05E20060B813cb` | `0x` (no code at this address on testnet) |

Interpretation limits: #3/#4 show deployed code at the documented mainnet Flow addresses. Presence is not bytecode equivalence. #6 proves only that the mainnet Flow address is empty on testnet; it does not prove flow is unsupported on testnet at another address.

## 5. Privy official documentation (checked 2026-10-10, reused from P20)

| ID | URL | Supports | Type |
|---|---|---|---|
| P1 | https://docs.privy.io/controls/policies/example-policies/ethereum | Policy rules on `ethereum_transaction.chain_id`, `.to`, `.value`; `ethereum_calldata` fields including `function_name` and ABI argument paths | `VERIFIED FACT` (documentation) |
| P2 | https://docs.privy.io/api-reference/wallets/ethereum/eth-sign-transaction | `eth_signTransaction` returns broadcast-capable `signed_transaction` RLP | `VERIFIED FACT` (documentation) |

Limit: P1 shows ABI-argument matching. It does not show equality or bound checks on opaque `bytes` arguments such as the Flow `program`. Whether the policy can enforce any bound on the opaque route stays `UNKNOWN`.

### Privy policy conditions (checked 2026-10-12, new for the policy binding)

Context7 resolved Privy as `/llmstxt/privy_io_llms_txt` and `/llmstxt/privy_io_llms-full_txt`. Exa fetched the pages. These pages are rolling and publish no version for a pin.

| ID | URL | Supports | Type |
|---|---|---|---|
| P3 | https://docs.privy.io/controls/policies/overview | Field sources; `ethereum_calldata` `function_name` and `function_name.param_name`; the `abi` requirement; the operator list. | `VERIFIED FACT` (documentation) |
| P4 | https://docs.privy.io/controls/policies/example-policies/ethereum | `address` and `uint256` calldata argument examples; a `function_name` example. No `bytes` argument example. | `VERIFIED FACT` (documentation) |
| P5 | https://docs.privy.io/controls/policies/condition-sets | `in_condition_set`; case-insensitive addresses and hex byte strings; every other comparison exact. | `VERIFIED FACT` (documentation) |
| P6 | https://docs.privy.io/api-reference/policies/create | `EthereumCalldataCondition`; the `ConditionOperator` enum; `ConditionValue` as a string or string array. | `VERIFIED FACT` (documentation) |
| P7 | https://docs.privy.io/wallets/wallets/update-a-wallet | `PATCH /v1/wallets/{wallet_id}`; `policy_ids` (one policy per wallet); `additional_signers`; a key-quorum owner can unilaterally update wallet policies and signers. | `VERIFIED FACT` (documentation) |
| P8 | https://docs.privy.io/controls/policies/create-a-policy | Policy `owner_id` is the authorization signature required to modify the policy. | `VERIFIED FACT` (documentation) |
| P9 | https://docs.privy.io/recipes/wallets/conditional-signer-policies and the stateful-policies recipe | Restrictive and permissive override policies; default denial; `DENY` precedence; a calldata decode or typed-data mismatch evaluates false. | `VERIFIED FACT` (documentation) |

Policy-binding limits (new, dated 2026-10-12):

- Documentation only. No provider call ran. The exact `program` `bytes` equality, the tuple-component calldata path and the deployed ABI stay `UNKNOWN`.
- One `get` schema snippet merged `ethereum_transaction` fields into `EthereumCalldataCondition`. The overview and the examples are treated as authoritative; that merged list is unreliable.
- The overview prose lists `neq` but the condition-sets API enum omits it. Both are retained.
- The stateful-policies recipe warns that an aggregation ABI mismatch defaults to `0` and passes, and that a non-decoding `DENY` condition does not fire. This favors a default-deny `ALLOW` design.

## 6. Retained prior evidence

| ID | Path | Status | Use and limit |
|---|---|---|---|
| R1 | `docs/qualification/kuru-flow/` | Accepted P20 package | Route matrix, source pins, control state, live-packet fields. |
| R2 | `docs/qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md` | Accepted bounded evidence | One-owner testnet `10143` sign-only controls, A removal. Not Kuru, mainnet, creation recovery or cross-user backend isolation. |
| R3 | `docs/qualification/p16/README.md` | Accepted with open items | Qualification matrix. |
| R4 | `docs/contracts/P15_WALLET_MANDATE_ACCOUNT_CONTRACTS.md` | Frozen contract | Identity, amounts, mandates, queue, stops, removal. |
| R5 | `docs/EDGE_OS_RESEARCH_CONTRACTS.md#exit-cap-q01-permission-model-qualification` | Requirements | EXIT-CAP-Q01 direction and enforcement boundary. |
| R6 | `docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#exact-monad-operation` | Accepted | Flow fixed-input direction and limits. |
| R7 | `docs/adr/0006-kuru-flow-initial-spot-adapter.md` | Accepted | Fixed-input Flow direction; no resting-order action. |
| R8 | `docs/qualification/p16/CREATION_RECOVERY_PLAN.md` | Preparation only | Owner-linked creation and recovery gaps. |
| R9 | `docs/research/00_HACKATHON_BRIEF.md` | Saved brief | Permits mainnet or testnet. |

## 7. Claim-to-source map

| Claim | Source |
|---|---|
| Flow entrypoint/router documented on mainnet `143` only | K1 |
| Testnet `10143` has no documented Flow contract | K1 |
| Deployed code exists at the documented mainnet Flow addresses | RPC #3, #4 |
| Deployed code exists at the documented testnet order-book router | RPC #5 |
| Quote API schema disagreement | K2 vs K3 |
| Fixed input and minimum received in the intent | S1, S2 |
| No maximum-output and no deadline field | S2 |
| Router called with `minAmountOut = 0`; post-fee check inside the entrypoint | S1 |
| ERC-20 approval set then reset to `0` | S1 |
| Native input requires `msg.value >= amountUserSells` | S1 |
| Policy supports chain/`to`/`value`/decoded-calldata conditions | P1 |
| Opaque `program` enforcement unproven | P1 (absence of bytes-bound example) |
| `eth_signTransaction` returns broadcast-capable bytes | P2 |

Each claim is bounded to what its source shows. A documented capability is not a live proof.
