# Controlled Kuru action feasibility

Task `P21-CONTROLLED-ACTION-FEASIBILITY-L3-20261014-LOCAL-v1`, issue #58, P20 #19 and P21 #20. Base `1b36fae3c221e5cfe458ea982e31fc848330b125`. Sources checked 2026-10-14.

Stage: documentation and public-source research only. This report ran no provider request, read no credential, created or changed no wallet or policy, requested no quote, signed nothing, broadcast nothing and spent nothing. It adopts no new architecture. Full P20 and P21 stay open.

## 1. Answer

**Result: `NOT_YET_FEASIBLE`.** No currently documented Monad/Kuru route satisfies all 12 mandatory P21 controls at the independent layer for one controlled action. This result completes the research question. It does not qualify execution, and it releases no live step.

The smallest candidate route is Kuru Flow `executeSwap` on Monad mainnet `143`. Testnet `10143` has no documented Flow contract. Six facts block qualification of that route today:

1. **Opaque route bytes (control 12).** Privy documents no Ethereum calldata condition that compares a dynamic `bytes` argument. Equality on the Flow `program` stays `UNKNOWN` and needs a provider control. A Privy page names `ethereum_transaction.data` as a standard condition field (PV-TEMPO). Exact equality on the whole calldata could bind the selector, both tuples and the `program` for one action, but no Ethereum example or tested enforcement exists, and its case rule is unknown. It also stays `UNKNOWN`.
2. **Intent and fee fields inside tuples (controls 4, 5, 7 and 8).** Privy documents only `function_name.param_name` for Ethereum calldata. A path into a tuple argument, such as the intent amount or the fee collector, stays `UNKNOWN`. Without these paths, or a working whole-calldata `data` equality, the policy cannot bind the tokens, the exact input, the minimum received or the fees. Section 4.3 shows why that gap permits a total loss.
3. **Policy administration (wallet/signer binding, control 2).** Separation of policy administration from the executor is a configuration that no one has created or tested. The accepted offline binding reports `POLICY_ADMIN_OWNER_MISSING`. Its evidence class is `NOT_RUN`. A user-owned policy is not enough by itself: Privy documents a server path that turns the user's access token plus the app secret into a user key with owner authority (section 6). Edge OS receives that access token on every request. Every Privy REST call, including `eth_signTransaction`, needs the app secret (PV-REST), so the executor must hold it. The only exception documented is the device-code agent path (PV-AGENT), which this design keeps disabled. The remaining barriers are that the executor process never sees a user access token, which is host-enforced, and that an ordinary login access token cannot be used on the device-code key exchange, which is `UNKNOWN` (section 6). The API process receives every user access token.
4. **Transaction type and EIP-7702 delegation (controls 2 and 3).** `eth_signTransaction` accepts transaction `type` 0, 1, 2 or 4 and an `authorization_list` for type 4 (PV-STX). Monad supports EIP-7702 delegation through type 4 (M-7702). Privy documents no `ethereum_transaction` condition on `type` or `authorization_list`. A policy that binds every route field could still sign an exact `executeSwap` that also delegates the wallet's code to a contract the executor chooses. Independent binding of these fields is `UNKNOWN`.
5. **Deployed identity.** The deployed entrypoint bytecode, its current owner and its current router are not verified. The pinned source lets the entrypoint owner replace the router at any time (section 4.2). No wallet policy can see the router.
6. **Transport.** The application has no actual Privy signer client, quote client or broadcast client. Production configuration permits only the `unavailable` execution mode (section 7).

Items 1, 2 and 4 need a bounded provider probe. Item 3 needs a configured and tested owner separation. Item 5 needs a read-only public chain check. Item 6 needs a separate implementation lease. If the probe in section 8 shows that Privy cannot bind the tuple fields, the `program` bytes or the transaction type, the route stays unsupported. The builder then decides on a different enforcement design (section 9). This report does not adopt one.

## 2. Retrieval tools and source identities

### 2.1 Tools used on 2026-10-14

| Tool | Use | Result |
|---|---|---|
| Context7 `resolve-library-id` "Privy" | Resolve first | `/llmstxt/privy_io_llms_txt` (High reputation). |
| Context7 `query-docs` (Privy) | Three queries: nested and `bytes` calldata arguments; policy and wallet update authority; supported ABI argument types | Returned the overview, Ethereum examples, Solana IDL, owners, wallet update and stateful-policy recipe sections cited below. A fourth query on `/llmstxt/privy_io_llms-full_txt` (repair round) returned the `POST /v1/wallets/authenticate` sections. |
| Context7 `resolve-library-id` "Kuru" | Resolve first | **No Kuru library.** The five results were unrelated projects. Fallback: official Kuru pages and pinned public source. |
| Context7 `resolve-library-id` "Monad" and `query-docs` | Chain IDs and finality; gas and reserve balance | `/websites/monad_xyz`. Returned the block-states, gas-pricing and reserve-balance sections. |
| Exa `web_search_exa` | Locate official Privy pages on nested calldata fields | Found the Privy overview, condition sets, Ethereum examples, stateful policies, template variables and Solana IDL pages. |
| Exa `web_fetch_exa` | Full text of the Privy, Kuru and Monad pages below | Used. |
| `curl` (public, unauthenticated) | Kuru `llms.txt`; GitHub commit API for the Flow repository; raw pinned Flow source; Monad page source for chain IDs | Used. No account, API key or RPC call. |

No provider, chain RPC, quote, wallet or console request ran. No `.env` file or key was read.

### 2.2 Privy sources (rolling pages, no version pin; read 2026-10-14)

| ID | URL | Supports |
|---|---|---|
| PV-OV | https://docs.privy.io/controls/policies/overview | Field sources; `ethereum_calldata` field grammar `function_name` or `function_name.param_name`; required `abi`; operators; default `DENY`; `DENY` precedence; a method with no rule is denied; simulation runs before policy evaluation for sign-and-broadcast; numeric values compared exactly in base units; `system.current_unix_timestamp`; `reference` aggregations only for `eth_signTransaction` and `eth_signUserOperation`; "All string comparisons are case-sensitive". |
| PV-EX | https://docs.privy.io/controls/policies/example-policies/ethereum | `to`, `value`, `chain_id`, `function_name`-only and flat `transfer.amount` examples; `value` compared as a hex string; typed-data `types` mismatch evaluates false, so a permissive `ALLOW` rule can sign. |
| PV-CS | https://docs.privy.io/controls/policies/condition-sets | Case-insensitive comparison applies only to an enumerated list: `ethereum_transaction.to`, address fields on `ethereum_typed_data_message`, address arguments on `ethereum_calldata`, `ethereum_typed_data_domain.verifyingContract`, `ethereum_7702_authorization.contract` and `tempo_transaction.fee_token`. Every other comparison is exact. |
| PV-SP | https://docs.privy.io/controls/policies/stateful-policies | Aggregation function `sum` only; rolling window 3600 to 259200 seconds; at most 10 aggregations per app; values update after signing, so concurrent requests can all pass; a value that cannot be extracted defaults to 0. |
| PV-TPL | https://docs.privy.io/controls/policies/template-variables | `{{wallet.address}}` resolves per request; usable with `eq` and `in` wherever a condition compares an address, including an `ethereum_calldata` address argument. |
| PV-IDL | https://docs.privy.io/controls/policies/example-policies/solana-idls | For **Solana** IDL data only: struct paths such as `deposit_for_burn.args.params.amount` and `bytes` equality are documented. |
| PV-CREATE | https://docs.privy.io/controls/policies/create-a-policy | Policy owner is optional. Without an owner, the app secret alone can update the policy. |
| PV-OWN | https://docs.privy.io/controls/authorization-keys/owners/overview | Policy owners update rules, change owner and delete the policy. Wallet owners update wallet policies, signers and signer policies. Signers cannot update owners, signers or policies and cannot export keys. |
| PV-SIGN | https://docs.privy.io/wallets/using-wallets/signers/overview | Signers support offline actions; signing happens in an enclave; a signer never sees the private key. |
| PV-RM | https://docs.privy.io/wallets/using-wallets/signers/remove-signers | `removeSigners` removes all signers; afterwards the app cannot act for the user. |
| PV-STX | https://docs.privy.io/api-reference/wallets/ethereum/eth-sign-transaction | `POST /v1/wallets/{wallet_id}/rpc` `eth_signTransaction` returns RLP `signed_transaction`; idempotency replay on 4xx/5xx except policy violations; optional request-expiry header in Unix milliseconds; transaction fields include `gas_limit`, `max_fee_per_gas`, `nonce`, `type`. |
| PV-UPD | https://docs.privy.io/recipes/hyperliquid/policies-and-offline-actions and https://docs.privy.io/recipes/agent-integrations/x402-sanctions-screening (through Context7) | `additional_signers` with `override_policy_ids`; a wallet `policy_ids` update needs the wallet owner's authorization signature. |
| PV-PATCH | https://docs.privy.io/recipes/using-stateful-policies (through Context7) | Rule updates apply in place; the policy ID does not change; an owned policy needs the owner's signature for each update. |
| PV-USERKEY | https://docs.privy.io/controls/authorization-keys/keys/create/user/request | A server holding the app ID and app secret can pass a user's access token (`user_jwts`) and receive a time-bound user key. That key signs requests on resources the user owns. |
| PV-AUTH | `POST https://api.privy.io/v1/wallets/authenticate` (through Context7, `/llmstxt/privy_io_llms-full_txt`, sourced from https://docs.privy.io/llms-full.txt) | Exchanges a user JWT for an ephemeral key "authorized to act on the user's wallets"; uses app Basic authentication. |
| PV-CHAINS | https://docs.privy.io/wallets/overview/chains | EVM-compatible networks are tier 3 (sign and send). Transaction policies need tier 2, but "Reaching that tier does not by itself make the capability available", and available conditions "vary by chain and method". No reviewed page names Monad `143` for policy enforcement. |
| PV-TEMPO | https://docs.privy.io/controls/policies/example-policies/tempo | "Standard `ethereum_transaction` conditions (`to`, `value`, `data`, and others) are enforced against all transactions on Tempo." Only page reviewed that names a `data` condition field. |
| PV-REST | https://docs.privy.io/basics/rest-api/setup | "All API endpoints require authentication using Basic Auth" with the app ID as username and the app secret as password. |
| PV-AGENT | https://docs.privy.io/recipes/agent-integrations/agent-authorization (through Context7) | A second exchange: `POST https://auth.privy.io/api/oauth/v2/wallets/authenticate` with a Bearer access token, `privy-app-id` and `privy-grant-type: device_code`, no app secret shown. Returns an encrypted ephemeral signing key. The companion recipe names a dashboard setting for device authorization. |

Reused, not rechecked today: PV-SRV (https://docs.privy.io/controls/authorization-keys/owners/configuration/user/server-updates), recorded 2026-10-12 in [independent-enforcement/SOURCE_EVIDENCE.md](../independent-enforcement/SOURCE_EVIDENCE.md).

### 2.3 Kuru sources

| ID | URL or pin | Read 2026-10-14 | Supports |
|---|---|---|---|
| K-ADDR | https://docs.kuru.io/contracts/Contract-addresses | yes | Mainnet `KuruFlowEntrypoint (Aggregator)` `0xb3e6778480b2E488385E8205eA05E20060B813cb`, `KuruFlowRouter` `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2`, tokens WMON `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A`, AUSD `0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a`, USDC `0x754704Bc059F8C67012fEd69BC8A327a5aafb603`. The testnet table lists Router, Margin Account, Forwarder, Deployer, Utils, USDC `0x3bA3d39AFcf8bb994f7964B3e0171Ea2Ba361570` and one MON-USDC market. It lists **no Flow entrypoint and no Flow router**. |
| K-QUOTE | https://docs.kuru.io/api-reference/calculate-best-path-quote | yes | `POST https://ws.kuru.io/api/quote`; Bearer JWT; fields `userAddress`, `tokenIn`, `tokenOut`, `amount`, `slippageTolerance` or `autoSlippage`, optional `referrerAddress`, `referrerFeeBps`; response `output`, `path` (`tx_builder.SwapRoute`), `buildResponse` (`tx_builder.BuildResponse`), `gasPrices`. Inner schemas are not published. No chain selector. |
| K-FLOW | https://docs.kuru.io/kuru-flow/flow-overview | yes | Flow aggregates liquidity across Monad markets; integrators can add fees. Product statement. |
| K-LLMS | https://docs.kuru.io/llms.txt | yes | The documentation index has one Flow API page. No testnet Flow page. |
| S-HEAD | https://api.github.com/repos/Kuru-Labs/Kuru-contracts-flow-public/commits/main | yes | `main` head is still `70bc0c93c073f78697b99848eedefbf5dbe698c7` (2026-04-15T05:38:02Z). |
| S1 | `src/entrypoint/KuruFlowEntrypoint.sol` at that commit | yes | SHA256 `15e19667ee20389b396a51143dccf7bbd31a701c610f1d78978c84f3b7fd1841`, equal to the retained pin. |
| S2 | `src/entrypoint/KuruFlowEntrypointTypes.sol` at that commit | yes | SHA256 `44d913012de00a2814e62f1e9c45c4408c8407c0457325de41efabecd05df1ac`, equal to the retained pin. |

The source files carry `SPDX-License-Identifier: BUSL-1.1`. This report copies no code. It names functions and fields only.

Retained, not rechecked: the quote-schema conflict between the Monad guide (`transaction { to, calldata, value }`) and the Kuru OpenAPI (`buildResponse`), recorded in [route-restrictions/SOURCE_EVIDENCE.md](../route-restrictions/SOURCE_EVIDENCE.md#quote-schema-conflict-new-dated-2026-10-10). The bounded 2026-10-10 `eth_getCode` reads in section 4 of that file show code at both mainnet Flow addresses. Code presence is not bytecode identity.

### 2.4 Monad sources (read 2026-10-14)

| ID | URL | Supports |
|---|---|---|
| M-NET | https://docs.monad.xyz/developer-essentials/network-information | Mainnet chain ID `143`; current version `v0.15.2` / `MONAD_NINE`. |
| M-TEST | https://docs.monad.xyz/developer-essentials/testnets | Testnet chain ID `10143`. |
| M-GAS | https://docs.monad.xyz/developer-essentials/gas-pricing | The fee charged is `gas_limit * price_per_gas`, not gas used. Minimum base fee 100 MON-gwei. The page's own example: a 200,000-gas swap costs about 0.02 MON at the minimum base fee. |
| M-RES | https://docs.monad.xyz/developer-essentials/reserve-balance | `user_reserve_balance` is 10 MON. For the sender, execution reverts a transaction whose value spend leaves the ending balance lower than `min(balance at start, 10 MON)` by more than the transaction's gas spend. The exception is an "emptying transaction": the sender is undelegated, sent no other transaction in the last `k = 3` blocks, and nobody sent a delegation or undelegation request for the sender in those blocks, including in this transaction. A reverted transaction still pays gas. |
| M-7702 | https://docs.monad.xyz/developer-essentials/eip-7702 | EIP-7702 works on Monad as on Ethereum: an authorization submitted in a type `0x04` transaction makes the EOA delegated. A delegated EOA cannot use the emptying exception. |
| M-FIN | https://docs.monad.xyz/monad-arch/consensus/block-states | RPC `"latest"` maps to `Proposed`, `"safe"` to `Voted` and `"finalized"` to `Finalized`. A proposed block may not enter the final chain. |

## 3. Network separation

| Item | Mainnet `143` | Testnet `10143` |
|---|---|---|
| Flow entrypoint and router | Documented (K-ADDR) | **Not documented** (K-ADDR, K-LLMS) |
| Quote host | `https://ws.kuru.io` (K-QUOTE) | Not documented; the quote API has no chain field |
| Deployed code at Flow addresses | Present, read 2026-10-10 | Mainnet entrypoint address empty, read 2026-10-10 |
| Bytecode identity to S1 | `UNKNOWN` | Not applicable |
| Retained P16 sign-only evidence | None | Exists for existing unfunded wallets; no Kuru action |

Testnet Flow stays `UNKNOWN`. This report treats no testnet address as a Flow address and no mainnet address as a testnet address. P16 evidence on `10143` does not carry over to a `143` action. Its signer-binding and removal pattern can be reused only for the same unchanged controls ([kuru-flow/INTEGRATED_PROBE_B_PLAN.md](../kuru-flow/INTEGRATED_PROBE_B_PLAN.md#3-p16-reuse-map)).

## 4. Findings new since the 2026-10-12 packages

The accepted packages [route-restrictions/](../route-restrictions/README.md) and [independent-enforcement/](../independent-enforcement/README.md) stay valid. The 2026-10-14 recheck adds these facts.

### 4.1 Privy capability

- Ethereum calldata grammar is unchanged: `function_name` or `function_name.param_name` (PV-OV). No Ethereum page shows a tuple component, an array or a `bytes` argument.
- Solana IDL conditions now document struct paths and `bytes` equality (PV-IDL). That page covers `solana_instruction_data` only. It shows the engine design can decode nested fields, but it is no evidence for `ethereum_calldata`. Ethereum tuple and `bytes` support stays `UNKNOWN`.
- `{{wallet.address}}` can pin an address argument to the signing wallet (PV-TPL). This gives a documented recipient condition for the flat `receiver` argument of `executeSwapWithReceiver`.
- Case rules: PV-OV says all string comparisons are case-sensitive. PV-CS lists the only case-insensitive fields; a calldata `bytes` argument and `ethereum_transaction.data` are not in that list, so both pages imply exact comparison for them. A `program` or `data` equality probe still tests a letter-case variant, because enforcement is not proved.
- `ethereum_transaction.data` is named as a standard condition field on the Tempo page (PV-TEMPO). No Ethereum example uses it. Exact `data eq <full calldata hex>` is `UNKNOWN` for Monad. If it works, it is per-action policy content. It does not solve router mutability, type-4 delegation or gas bounds. The 2026-10-12 statement "No documented raw `data` field" ([PRIVY_POLICY_BINDING_FEASIBILITY.md](../route-restrictions/PRIVY_POLICY_BINDING_FEASIBILITY.md#2-reviewed-privy-capability)) is superseded by this page for the field name only.
- Aggregations support only `sum`, update after signing, and allow concurrent requests to pass before the total updates (PV-SP). They limit damage. They are not an exact action counter.
- `eth_signTransaction` accepts a request-expiry header (PV-STX). It bounds when Privy processes the request. It is no onchain deadline.
- `eth_signTransaction` accepts `type` 0, 1, 2 or 4 and an `authorization_list` for EIP-7702 type-4 transactions (PV-STX). The documented `ethereum_7702_authorization` field source applies to `eth_sign7702Authorization` requests (PV-OV). No page documents an `ethereum_transaction` condition on `type`, `authorization_list`, `gas_price`, `gas_limit` or fee fields. Whether a policy can deny a type-4 `eth_signTransaction` is `UNKNOWN`.
- A server holding the app secret can exchange a user's access token for a user key and act as the user on resources the user owns (PV-USERKEY, PV-AUTH). A device-code variant exchanges a Bearer access token without an app secret (PV-AGENT); whether an ordinary login access token works there is `UNKNOWN`. Section 6 covers the consequence.
- Every Privy REST endpoint requires app-secret Basic authentication (PV-REST), except the device-code agent path, where an agent calls the wallet RPC endpoint without an app secret after the exchange (PV-AGENT); this design keeps that path disabled. A signer client for `eth_signTransaction` therefore holds the app secret.
- No documented field source reads token balances, allowances, simulation results or the Edge OS ledger.

### 4.2 Kuru entrypoint (S1, pinned source)

- The entrypoint is `Ownable`. Its owner can call `setRouter` and replace the router at any time. The router executes the `program`. A wallet policy pinned to the entrypoint address therefore does not pin the code that runs the route. The deployed owner and current router are `UNKNOWN`.
- The entrypoint does no token sweeping. For native input it checks `msg.value >= amountUserSells` and keeps any excess; that excess does not return to the wallet. For ERC-20 input, any input the router does not pull stays in the entrypoint, because the router approval is reset and nothing sweeps it. For native input, what happens to value the router does not use depends on router code that S1 does not show: `UNKNOWN`.
- `executeSwap` sends output to `msg.sender`. `executeSwapWithReceiver` sends output to any `receiver`.
- Input-mode fees leave before the swap: `amountUserSells * feeBps / 10000` goes to `feeCollectorAddress`, and the referrer share goes to `referrerAddress`. Output-mode fees leave after the swap. The only check is `feeBps + referrerFeeBps <= 10000` and nonzero addresses for nonzero fees.
- The minimum-received check `amountOut >= minAmountUserBuys` runs after fees. The router receives `minAmountOut = 0`.
- For ERC-20 input the entrypoint pulls exactly `amountUserSells` from `msg.sender`, approves the router for the post-fee amount and resets that approval to 0. The owner's allowance to the entrypoint is separate and stays as set.

### 4.3 Why the outer allowlist allows a total loss

Suppose the policy binds only chain, `to`, `function_name` and `value`. An executor can then sign `executeSwap` with `isInTokenFee = false`, `feeBps = 10000`, its own `feeCollectorAddress` and `minAmountUserBuys = 0`. The swap completes, the output fee takes the whole output (`totalAmountOut * 10000 / 10000`), the wallet receives 0, and the check `0 >= 0` passes (S1, output-fee and minimum-check code). This loss needs no assumption about the router. The input-fee variant (`isInTokenFee = true`) also sends the whole input to the collector, but only if the router does not revert on a zero input, which is `UNKNOWN`; a revert undoes it. Even without the fee fields, a `program` of the executor's choice combined with `minAmountUserBuys = 0` leaves the received amount unbounded. This is the concrete reason controls 4, 5, 7 and 8 need independent tuple binding, and not only host checks.

### 4.4 Monad costs

- The full gas limit is charged, not gas used (M-GAS). The price per gas is `min(base + priority, max_fee_per_gas)`, so the fee per transaction is at most `gas_limit * max_fee_per_gas`, known before signing. This helps capacity control.
- A native-input swap whose value spend takes the ending balance below `min(balance at start, 10 MON)` by more than its gas spend reverts, unless it is an emptying transaction (M-RES). The wallet must be undelegated, send nothing else within 3 blocks, and have no delegation or undelegation request in those blocks. A delegated wallet never gets the exception (M-7702). A reverted transaction still pays gas. An ERC-20-input swap with `value = 0` spends only gas and is not affected in the same way.

## 5. Mandatory control matrix

Evidence classes: `DOCUMENTED`, `SOURCE_INSPECTED`, `LOCAL_TESTED`, `PROVIDER_ACTUAL`, `NOT_RUN`. States: `UNKNOWN` (no reviewed evidence), `UNSUPPORTED` (the layer cannot express it), `INFERENCE` (reasoned, not proved), `UNSET` (a required value no one has chosen yet; it blocks like `REQUIRED_DECISION`). In section 10, `TO_COMPUTE` marks a value fixed by a public definition that must be computed before use, not chosen. The `HOST` layer is Edge OS application accounting. It is never independent enforcement. "Independent authority" names who holds the power that the executor must not hold.

| # | Control | Host layer (Edge OS) | Contract layer (Kuru) | Independent layer (Privy policy) and evidence | Independent authority | Remaining implementation | Positive proof required | Negative proof required | Status | Sources |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `chain` | Approval names one network | None | `ethereum_transaction.chain_id eq 143` (PV-OV, PV-EX): `DOCUMENTED` as a field. Privy policy enforcement on chain `143`: `UNKNOWN` (PV-CHAINS names no chain); decided by probe 8.2 step 2. Provider `NOT_RUN` | Policy owner | Policy content; transport sets `chain_id` | Allowed sign on `143` | Same request with `10143` denied | Expressible; unproved | PV-OV, PV-EX, PV-CHAINS, M-NET |
| 2 | `wallet_signer_binding` | Derives owner, agent and wallet; P16 local and sign-only `10143` evidence | Not applicable | Wallet `policy_ids` (one per wallet) or signer `override_policy_ids` (PV-UPD): `DOCUMENTED`. Administration separation: `NOT_RUN`; the separation from user-key exchange is host-enforced, not provider-enforced. User-key exchange from app secret plus user access token is a documented way to act as the owner (PV-USERKEY, PV-AUTH); a device-code variant needs no app secret (PV-AGENT), and whether it accepts an ordinary login access token, which the API process receives on every request, is `UNKNOWN`. Denial of a type-4 delegation inside `eth_signTransaction`: `UNKNOWN` | Wallet owner (user) for signer attachment and removal; policy owner outside executor control | Explicit policy owner; executor key outside wallet-owner quorum; executor process holds the app secret (PV-REST) and executor key and never receives user access tokens; API process holds no app secret (D13); device authorization for CLI and agent access stays disabled; executor-process split is a builder decision (section 7 item 6) | Executor signs only through its restricted signer | App-secret-only and executor-key updates of the policy or wallet signers denied (provider); no user access token reaches the executor process and device authorization is disabled (host and configuration evidence); with device authorization disabled, the device-code key exchange refuses a probe user's ordinary login access token (provider); type-4 request with an `authorization_list` denied (provider); other wallet not covered | **Blocking:** separation `NOT_RUN`; ordinary-token use of the device-code exchange `UNKNOWN`; delegation denial `UNKNOWN` | PV-UPD, PV-OWN, PV-CREATE, PV-USERKEY, PV-AUTH, PV-AGENT, PV-REST, PV-STX, M-7702; retained P16 result |
| 3 | `entrypoint_method` | Adapter builds one method | Entrypoint exposes two methods | `to eq` entrypoint and `function_name eq executeSwap` with pinned ABI: `DOCUMENTED` | Policy owner | Real selector and deployed ABI check | Allowed `executeSwap` | Wrong contract, `executeSwapWithReceiver`, another method and a type-4 transaction denied | Expressible for `to` and method; deployed identity `UNKNOWN`; router mutable (4.2); transaction `type` binding `UNKNOWN` | PV-OV, PV-EX, PV-STX, S1, K-ADDR |
| 4 | `input_output_assets` | Adapter validates tokens | Intent fields `tokenUserSells`, `tokenUserBuys` | Tuple path such as `executeSwap.swapIntent.tokenUserSells`: `UNKNOWN` | Policy owner | Provider probe of tuple paths | Exact tokens allowed | Swapped or other token denied | **Blocking:** `UNKNOWN` | PV-OV, S1, S2 |
| 5 | `raw_input` | Canonical base-10 raw value checks | `amountUserSells` pulled exactly (ERC-20) or `msg.value >= amountUserSells` (native) | Tuple path `UNKNOWN`. Native `value eq` raw: `DOCUMENTED` but does not bind `amountUserSells`, so excess value can stay in the entrypoint (4.2) | Policy owner; for ERC-20 input, the token allowance set by the wallet owner | Provider probe; exact owner allowance if ERC-20 | Exact amount allowed | Changed amount denied; changed value denied | **Blocking:** `UNKNOWN` | PV-OV, PV-EX, S1, S2 |
| 6 | `recipient` | Approves the agent wallet only | `executeSwap` pays `msg.sender` (S1) | `executeSwap` has no recipient argument. Deny the receiver method by default-deny. For `executeSwapWithReceiver`, flat `receiver eq {{wallet.address}}` is `DOCUMENTED` (PV-TPL) | Policy owner | Use `executeSwap` only | Output reaches the signing wallet | Receiver method denied | Expressible; unproved | S1, PV-OV, PV-TPL |
| 7 | `minimum_output` | Minimum at or below quote, raw units; never from the estimate | Post-fee check against `minAmountUserBuys`; router gets 0 (S1) | Tuple path `UNKNOWN` | Policy owner | Provider probe | Exact minimum allowed | Lowered minimum denied | **Blocking:** `UNKNOWN` | PV-OV, S1, S2 |
| 8 | `fees` | Adopted fee values | Total `<= 10000` bps; nonzero fee needs nonzero address (S1) | Tuple paths for five `FeeCollection` fields `UNKNOWN` | Policy owner | Provider probe | Adopted fee fields allowed | Changed collector, bps or mode denied | **Blocking:** `UNKNOWN`; total-loss case in 4.3 | PV-OV, S1, S2 |
| 9 | `approvals` | Declared allowance equals adopted allowance | Entrypoint resets only its own router approval (S1) | No field source reads allowances: `UNSUPPORTED`. Executor `approve` calls can be denied by default-deny | Wallet owner sets and revokes the owner-to-entrypoint allowance; token contract enforces it | For native input: not applicable. For ERC-20 input: exact allowance, revoke to 0 | Allowance equals `amountUserSells` before the action | Executor `approve` denied; second pull fails after allowance is used | Native input: not applicable. ERC-20: owner-held, no policy proof | PV-OV, S1 |
| 10 | `gas_action_capacity` | Reservations; one economic action | Gas limit charged in full (M-GAS) | Gas fields (`gas_limit`, `max_fee_per_gas`, `gas_price` for type 0): `UNKNOWN` (no documented condition). Native value cap by `reference` aggregation `sum`: `DOCUMENTED`, post-signing update | Policy owner | Exact gas limit and fee cap; aggregation optional | Swap fits the reserved gas | Over-cap request denied at host; independent gas bound `UNKNOWN` | Budget `UNSET`; independent gas bound `UNKNOWN` | PV-SP, PV-STX, M-GAS |
| 11 | `expiry_freshness` | Quote age, input age, intent and mandate expiry | **No onchain deadline** in the intent (S2) | `system.current_unix_timestamp` window: field `DOCUMENTED`; upper cutoff on `eth_signTransaction` is `INFERENCE`. Request-expiry header bounds processing only (PV-STX) | Policy owner (time window) | Host expiry; optional signing window | Sign inside window | Sign after window denied | Host only; no onchain bound; a signed transaction can be sent later | PV-OV, PV-EX, PV-STX, S2 |
| 12 | `opaque_program` | Adapter freezes `program` bytes from the quote | Forwarded unchanged to a router the owner can replace (S1) | `bytes` argument equality: `UNKNOWN`. Whole-calldata `ethereum_transaction.data eq`: `UNKNOWN` (field named on PV-TEMPO only). Inner router operations: invisible to the policy | Policy owner | Provider probe; per-action policy content | Exact `program` or exact `data` allowed | One changed byte denied; case variants tested | **Blocking:** `UNKNOWN` | PV-OV, PV-CS, PV-TEMPO, S1 |

Also mandatory for entries and additions, outside the 12: position inventory stays `UNSUPPORTED` at the independent layer and `LOCAL_TESTED` at the host ([CONTROL_RESTRICTIONS.md](../route-restrictions/CONTROL_RESTRICTIONS.md#position-inventory-restriction-separate)). It does not apply to one controlled qualification action that does not claim exit coverage.

### 5.1 Can the policy inspect the whole intent and program?

No, not on documented evidence.

- The Flow call is one transaction to one contract. Its route is the `program` executed inside the router. The router's inner calls are not transactions, so no Privy field source sees them. A policy can at most compare the `program` argument as bytes, or the whole calldata through `ethereum_transaction.data`. Both comparisons are `UNKNOWN`. Neither sees which router runs the bytes.
- Batched wallet requests (`wallet_sendCalls`) and other methods are denied when the policy has no rule for them (PV-OV). The policy should contain one `ALLOW` rule for `eth_signTransaction` only.
- An outer contract allowlist and a native value bound do not bind ERC-20 notional, minimum output, fees or route behavior (4.3).
- Host risk checks stay separate. They protect against mistakes. They do not protect against a compromised executor.

**`INFERENCE`, not a qualification:** if tuple paths work, binding the tokens, `amountUserSells`, `minAmountUserBuys`, the fee fields, `executeSwap` and, for native input, `value eq amountUserSells` lets the entrypoint's own checks bound the route's economic result, whatever the `program` does: the wallet pays exactly the input and receives at least the minimum. This bound excludes gas, which is charged separately and has no documented independent condition, and it excludes EIP-7702 delegation in the same transaction, which needs its own denial (section 1 item 4). P21 control 12 still requires a bound on the `program`. Accepting the contract bound in place of control 12 would change P21. That is a builder decision. This report does not make it.

## 6. Policy ownership and administration

- Privy separates wallet ownership from policy ownership (PV-OWN, PV-CREATE). An ownerless policy can be updated with the app secret alone. Every REST call needs the app secret (PV-REST), so the executor must hold the app secret and its authorization key. An ownerless policy is therefore not independent.
- Owner authority is reachable from a server. With the app ID and app secret, a server can pass a user's access token and receive a time-bound user key, then sign owner-authorized requests on the user's wallet and policies (PV-USERKEY, PV-AUTH). Edge OS receives the Privy access token as a Bearer token on every authenticated API request (`bearer_token` in `apps/api/src/edge_os_api/core/authentication.py`). A component that holds the app secret and sees a live access token can therefore rewrite a user-owned policy, change signers or their override policies, or sign as the owner. A user-owned policy alone is not independent of such a component.
- The minimum separation for one action: the policy has an explicit owner; the executor key is neither that owner nor a member of the wallet-owner quorum; and the executor process, which holds the app secret and the executor key, never receives user access tokens. The API process that verifies access tokens holds no app secret, as the accepted D13 boundary already requires ([P01_APPLICATION_AUTH_STORAGE_PROFILE.md](../../implementation/P01_APPLICATION_AUTH_STORAGE_PROFILE.md), row D13; `FORBIDDEN_ENV_NAMES` in `apps/api/src/edge_os_api/core/settings.py`). The Privy dashboard setting for device authorization ("Enable for CLI and agent access") stays disabled; record that setting as configuration evidence. PV-AGENT documents the resulting 403 `device_auth_not_enabled` only for the first step of the flow (`device_authorization`). It does not show that the key exchange itself (`POST https://auth.privy.io/api/oauth/v2/wallets/authenticate`, Bearer access token, `privy-grant-type: device_code`, no app secret) refuses an ordinary login access token. The API process receives every user access token, so if that exchange accepts one, the API process could obtain a key with signing authority over the user's wallet without any app secret. That is `UNKNOWN` and keeps control 2 blocking until a provider negative proof exists (section 8.2 step 3). This separation is host-enforced, not provider-enforced. Whether Privy can scope an app secret, issue more than one, or disable user-key exchange is `UNKNOWN`. The executor is attached as an additional signer whose `override_policy_ids` names the restrictive policy (PV-UPD). Signers cannot change owners, signers or policies (PV-OWN).
- The simplest documented owner for one action is the user. Each policy rule change then needs the user's authorization signature (PV-PATCH). A per-action `program` value means a new policy content per action. For one controlled action this is acceptable. For recurring trading it would need repeated user signatures. Recurring trading is deferred.
- Public API support is not configuration. Today no policy exists, no owner is set, no deployed policy content hash exists, and no test showed that the app secret, the executor key or a user-key exchange from the executor runtime cannot change the policy. All of these are `NOT_RUN`.
- The accepted offline module records the owner and the separation flag and blocks while they are absent (`apps/api/src/edge_os_api/kuru_flow/policy_binding/policy_request.py`).

## 7. Fit with the accepted application

Inspected read-only at the base commit:

- `apps/api/src/edge_os_api/core/settings.py`: `execution_mode` is `fixture` or `unavailable`; production allows only `unavailable`. `EDGE_OS_PRIVY_APP_SECRET` is a forbidden environment name. Credentials alone cannot enable execution.
- `apps/api/src/edge_os_api/core/provider_ports.py`: `build_provider_ports` returns fixture ports or ports that raise `ProviderUnavailable`.
- `apps/api/src/edge_os_api/execution/original_transaction.py`: the original-action seam already orders quote, persist, sign, validate, persist signed bytes and Keccak hash, recheck stop and expiry, then one broadcast. It takes injected `RouteQuoteClient`, `SignerClient` and separate broadcast and observer `RpcClient` objects. It retries nothing.
- The same seam rejects native MON on either leg. `token_of` returns no token for an asset ID ending in the native suffix; the caller in `apps/api/src/edge_os_api/execution/worker.py` builds each `Leg.token` as `token_of(...) or ""`; `_prepare` then returns `NATIVE_TRADING_UNSUPPORTED` before any quote, nonce, signing or broadcast. The lower-level Kuru adapter and the pinned contract accept native value, but the mounted application path does not. An action with native MON as input or output cannot run through this seam without further work.
- `apps/api/src/edge_os_api/execution/original_recordings.py`: the only concrete clients replay authored recordings.
- `apps/api/src/edge_os_api/execution/transport.py`: a labelled local fixture transport.
- `apps/api/src/edge_os_api/wallet_setup/provider.py`: a port; concrete implementations in this stage are fakes.
- `apps/api/src/edge_os_api/revocation/enforcement.py`: removal and stop states deny new submission locally. A local stop is not provider removal.

Remaining implementation, for a separate lease and not done here:

1. Concrete Privy `SignerClient` for `eth_signTransaction` only. It needs app ID and app secret Basic authentication (PV-REST) and the executor authorization key, and makes no policy-administration call.
2. Concrete Kuru `RouteQuoteClient` and a frozen quote schema.
3. Two separate RPC clients for broadcast and independent observation.
4. A third execution mode, refused unless an exact released packet is configured. This changes shared settings and needs a builder decision.
5. Owner-side browser steps for signer attachment, policy ownership and removal through the existing Privy login.
6. A separate executor process that holds the app secret and the executor key and never receives user access tokens. The API process keeps holding no app secret (D13). This is a deployment and architecture change, listed in section 9 for a builder decision.
7. Only if the builder selects native MON on either leg (section 8.1 option A): a separately leased compatibility investigation and change for native input or output in the original-action seam. It must check native asset identity, separation of native trading value from gas accounting and reservations, and receipt, holdings and recovery handling for native transfers. It is not a guard removal, and this report does not design it.

## 8. Recommended smallest path

Under the existing architecture, except the executor-process split in section 7 item 6, which needs a builder decision: user-owned Privy wallet, restricted additional signer, Kuru Flow `executeSwap` on mainnet `143`, one fixed-input swap, sign-only transport with local Keccak hash, one broadcast. Network change, new contracts and new approvers are excluded.

### 8.1 Input choice (builder decision)

| Option | Benefit | Cost | Remaining gap |
|---|---|---|---|
| A. Native MON input, ERC-20 output | No approve or revoke transaction; one onchain transaction; `value` is a documented policy field; `sum` aggregation on `value` can cap cumulative native notional | **The accepted original-action seam rejects native legs (`NATIVE_TRADING_UNSUPPORTED`, section 7)**, so it needs section 7 item 7 under a separate lease; reserve-balance rule: must be an emptying transaction or keep 10 MON; excess `value` over `amountUserSells` is kept by the entrypoint | Tuple and `bytes` binding; native seam support |
| B. ERC-20 input and ERC-20 output (for example USDC to WMON) | Reuses the accepted original-action seam, which accepts ERC-20 legs only; token allowance is an onchain cap enforced by the token contract | Owner approve and revoke transactions; needs the input token in the wallet | Tuple and `bytes` binding; allowance is owner-held, not policy-proved |

Option A needs fewer onchain transactions but more application work, because the seam rejects native legs. Option B fits the accepted seam as it stands. This report proposes option B as the smaller path under the existing architecture and leaves option A contingent on section 7 item 7. The builder chooses.

### 8.2 Bounded next investigation (requires separate approval)

1. **Read-only public chain check.** For both mainnet Flow addresses, compare deployed bytecode with S1 build output, and read the entrypoint `owner()` and `getRouter()`. No signing. Proposed ceiling: 6 read-only calls.
2. **No-value provider probe of policy expressibility.** Use a separate probe wallet that is **never funded**, on chain `143`. Create one policy with an explicit owner. Request `eth_signTransaction` once for an exact `executeSwap` candidate and once for each one-field mutation: exact whole-calldata `data` allowed under a `data eq` rule, one changed `data` byte, a `data` letter-case variant, `program` byte, `program` letter case, each intent field (S1 parameter names `swapIntent` and `feeCollection`), each fee field, method, `to`, `chain_id`, transaction `type` 4 with a non-empty `authorization_list`, and `type` 0 with `gas_price`. Discard every signed result. The wallet must never be funded, because an allowed result is a valid transaction for that wallet and nonce. This probe decides blockers 1, 2 and 4.
3. **Administration probe.** On the same probe policy, attempt an update with the app secret alone and with the executor key. Both must be denied. Separately, record evidence that the executor process receives no user access token, so the user-key exchanges (PV-USERKEY, PV-AUTH, PV-AGENT) cannot start there. That evidence is host evidence, not provider evidence. Also run one provider negative proof: with device authorization disabled, present a probe user's ordinary login access token to the device-code key exchange; it must be refused. This decides blocker 3 only as far as host separation and that one provider refusal can.
4. **Builder decision** if step 2 shows `UNSUPPORTED`: stop the route, accept a narrower recorded claim, or start a separate design task (section 9).
5. **Implementation lease** for section 7 items 1 to 6, and item 7 only if option A is selected, after steps 1 to 3 pass. This also decides blocker 6.
6. **Live qualification packet** (section 10) after steps 1 to 5.

Step 1 decides blocker 5. Steps 1 to 3 spend no money but are provider or chain calls. This task does not authorize them.

## 9. Proposals not adopted

Each item is a material architecture choice for the builder. None is adopted, designed or implemented here.

- A wrapper contract that checks the quote-bound `program` hash or the intent fields onchain.
- An approver service that co-signs (key quorum) after independent checks.
- Moving the Privy app secret and executor key into a separate executor process that never receives user access tokens (section 7 item 6). The current API holds no app secret by design (D13), so a real signer client needs this change.
- Treating the contract's post-fee minimum with pinned tuple fields as a substitute for control 12 (section 5.1).

## 10. Qualification packet draft (`NOT_RUN`)

This draft is not a release. It grants no setup, policy, funding, approval, quote, signing or broadcast authority. Values marked `REQUIRED_DECISION` are open. Unknown values block the affected step; unknown is never zero.

### 10.1 Fields

| Field | Value | Class |
|---|---|---|
| Network | Monad mainnet `143` | `DOCUMENTED`; testnet Flow `UNKNOWN` |
| Entrypoint | `0xb3e6778480b2E488385E8205eA05E20060B813cb` | `DOCUMENTED`; bytecode, owner, router `UNKNOWN` |
| Router | `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` at documentation time | `DOCUMENTED`; current router `UNKNOWN` |
| Method | `executeSwap(SwapIntent,FeeCollection,bytes)` | `SOURCE_INSPECTED`; selector `TO_COMPUTE` from `executeSwap((address,uint256,address,uint256),(address,uint256,address,uint256,bool),bytes)` |
| Input asset | Option B (proposed): ERC-20; option A: native MON (`address(0)`), only after section 7 item 7 | `REQUIRED_DECISION` |
| Output asset and decimals | An ERC-20 under the current seam, different from the input (for example WMON `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A` for a USDC input); decimals read from the token contract | `REQUIRED_DECISION` |
| `amountUserSells` raw | — | `REQUIRED_DECISION` |
| Transaction `value` | Option A: equal to `amountUserSells`; option B: `0` | Rule `SOURCE_INSPECTED`; value `REQUIRED_DECISION` |
| `minAmountUserBuys` raw | At or below the frozen quote, after fees | `REQUIRED_DECISION` |
| Fee fields | Proposed: `feeBps 0`, `referrerFeeBps 0`, zero addresses, `isInTokenFee false` | `REQUIRED_DECISION` |
| `program` | Frozen bytes from one quote | `REQUIRED_DECISION` |
| Recipient | Signing wallet (`msg.sender`) | `SOURCE_INSPECTED` |
| Owner-to-entrypoint allowance | Option A: none; option B: exactly `amountUserSells`, revoked to 0 after | `REQUIRED_DECISION` |
| Gas limit and `max_fee_per_gas` | Full limit is charged (M-GAS) | `REQUIRED_DECISION` |
| Quote and input maximum age; intent and mandate expiry; signing window | — | `REQUIRED_DECISION` |
| Finality for reconciliation | Proposed: `"finalized"` (M-FIN) | `REQUIRED_DECISION` |
| Wallet, executor signer, policy owner, policy content hash | — | `REQUIRED_DECISION` |
| Receipt observer RPC | Separate from the broadcast RPC | `REQUIRED_DECISION` |

### 10.2 Capital limit

The builder supplied a total of USD2 for trading capital **including gas**. This draft approves no chain, asset or amount within it.

- Cost feasibility is `UNKNOWN`. No quote, MON price, current base fee or minimum Flow trade size was observed.
- M-GAS gives about 0.02 MON for a 200,000-gas swap at the minimum base fee and labels it about USD0.0005. That figure is the page's own example, not a current price.
- Option A first needs native-leg support in the original-action seam (section 7 item 7). It must also satisfy the reserve-balance emptying conditions (M-RES), or the swap reverts and still pays gas.
- Option B needs input tokens plus MON for three owner and executor transactions.
- Losses from fees, price movement, residual dust kept by the entrypoint and a reverted transaction count against the USD2. This draft does not claim USD2 is sufficient.

### 10.3 Ordered steps

Each step needs its own approval. A later step inherits nothing from an earlier one.

1. **Setup.** User logs in through the accepted Privy flow. The user's wallet exists. Record a public read showing the wallet is undelegated (its code is empty, not an EIP-7702 `0xef0100` designation). Record the wallet ID, address and current raw balances.
2. **Policy.** Create the restrictive policy with the user as owner. Read it back. Freeze its content hash. Confirm one `ALLOW` rule for `eth_signTransaction`, no other method, and a tested denial of type-4 requests (section 8.2 step 2). Confirm, as host evidence, that the executor process receives no user access token and that the API process holds no app secret. Record, as configuration evidence, that device authorization for CLI and agent access is disabled, and require the provider refusal of an ordinary login access token on the device-code key exchange (section 8.2 step 3).
3. **Signer attachment.** User attaches the executor key as an additional signer with `override_policy_ids` set to that policy. Confirm with a read.
4. **Funding.** Owner deposits the approved raw amounts of MON (and the input token for option B). One deposit per asset.
5. **Approval (option B only).** Owner approves exactly `amountUserSells` to the entrypoint.
6. **Unsigned preparation.** Persist decision, revision, mandate, intent, reservations and the exact unsigned candidate hash before any signature.

Then the accepted acceptance sequence runs in its frozen order ([INTEGRATED_PROBE_B_PLAN.md](../kuru-flow/INTEGRATED_PROBE_B_PLAN.md#4-preserved-acceptance-sequence)). This draft maps each item to the route. One deviation is stated openly: the accepted original-transaction packet frames interruption as a lost reply inside the original action ([ACTUAL_ORIGINAL_TRANSACTION_QUALIFICATION_PACKET.md](../original-transaction/ACTUAL_ORIGINAL_TRANSACTION_QUALIFICATION_PACKET.md#proof-the-actual-run-must-produce)). With one economic action, the interruption is therefore injected during step 7 and recorded as item-5 evidence after items 2 to 4. If the builder requires a different timing, that timing is `REQUIRED_DECISION`.

7. **One permitted action, no second user signature.** Sign once; validate the signed bytes; persist bytes and Keccak hash; recheck stop and expiry; broadcast once.
8. **Receipt and effects.** Read the receipt and the `KuruFlowSwap` and `FeeCollected` events from the observer RPC at the selected finality. Record actual input, output, gas and residual holdings.
9. **Local denial.** One deterministic host admission denial.
10. **Independent denial.** One isolated `eth_signTransaction` that changes one guarded field, not masked by a local counter. Expected: policy denial. Use the nonce that step 7 already consumed, so any unexpectedly signed bytes are rejected by the chain. The wallet is funded at this point; if the nonce cannot be reused this way, an unexpected allow returns valid broadcastable bytes. Treat any allow as a breach: stop, do not broadcast, discard the bytes and record it. Running the same denial shape first on the never-funded probe wallet (section 8.2) lowers this risk.
11. **Interruption.** For the action in step 7, record two cases. (a) Lost signer reply: the signer call may have produced bytes, but no reply was saved. Recovery may not re-sign; whether an idempotency replay returns the same bytes is not documented for a 200 response (PV-STX), so the outcome stays unknown until the observer settles it. (b) Lost broadcast reply after possible submission and before completion recording: restart and reconcile the original hash only. In both cases: no second economic action and no replacement route. Also record one negative case: a signed response with a wrong signer or a wrong field is refused before broadcast.
12. **Revocation.** Revoke the allowance to 0 (option B). User removes the signer. One post-removal `eth_signTransaction`, using the nonce step 7 already consumed, must be denied by the provider, not by an exhausted local counter.
13. **Record exposure.** Output tokens remain in the wallet. Flow places no resting order. Excess native value or unspent input, if any, stays in the entrypoint and is not recoverable by the wallet.

Steps 7 and 11 describe one action. The interruption is injected inside that action, so the run has one economic action in total. The two lost-reply cases need two separate interruption points; with one action, only one can occur on the real chain. Which case runs live, and whether the other is shown only by the local recorded seam, is `REQUIRED_DECISION`.

### 10.4 Stop limits

- Economic actions: 1. Broadcasts: 1. Automatic retries: 0. Re-quotes, re-nonces, re-fees and re-signs after the action begins: 0.
- Signing calls, quote calls and RPC reads: finite caps, `REQUIRED_DECISION`.
- Stop and keep all records on: any allowed result where denial was expected; any field mismatch between the signed bytes and the candidate; any policy content hash mismatch; any receipt that does not match the local hash; any CAPTCHA, consent or payment boundary; an unknown outcome. An unknown outcome keeps its reservations and is reconciled, never replaced.

### 10.5 Independent receipts

- The transaction hash is the Keccak-256 of the signed bytes, computed before broadcast.
- The receipt comes from an RPC endpoint separate from the broadcast endpoint, at the selected finality.
- Asset effects come from the receipt logs and from balance reads at the receipt block, not from the quote or the provider response.
- Provider denials keep their raw status and body. A simulation error is not a policy denial (PV-OV).

## 11. Recovery and revocation limits

- `SUBMISSION_UNKNOWN` keeps the original signed bytes, hash and reservations. Only the observer receipt settles it. A timeout never permits a second action.
- Privy idempotency replays the cached response for the same key on 4xx and 5xx, except policy violations (PV-STX). Replay is a different thing from keeping the original signed bytes. Resend stays disabled until decided ([original-transaction packet](../original-transaction/ACTUAL_ORIGINAL_TRANSACTION_QUALIFICATION_PACKET.md)).
- The Flow intent has no onchain deadline. A signed but unsent transaction stays valid until its nonce is used. Local expiry, a signing window and signer removal do not cancel it. Discard unused signed bytes, and keep the wallet nonce state in the records.
- Signer removal stops future signing (PV-RM). It does not reverse a broadcast transaction. Flow has no resting order, so no order cancellation is needed for this route.
- Residual exposure after the action: the output token balance, any remaining allowance (option B, until revoked), any value kept by the entrypoint, and any signed but unbroadcast bytes from an unexpected allow whose nonce is still unused. These are recorded, never treated as zero.

## 12. Claim boundary

- This report shows what documents and pinned source support. It proves no provider policy, wallet, chain or financial behavior.
- Every independent-layer row is at most `DOCUMENTED`. Nothing here is `PROVIDER_ACTUAL`.
- The existing offline checker and policy-binding tests can show only `AUTHORED_FAKE_ONLY` or `AUTHORED_POLICY_ALLOW`. They cannot qualify provider enforcement.
- Mandatory controls that are `UNKNOWN` or `NOT_RUN` keep the financial action closed.
