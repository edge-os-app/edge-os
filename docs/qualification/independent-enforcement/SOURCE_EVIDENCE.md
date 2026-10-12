# Independent enforcement preparation — source evidence (recheck 2026-10-12)

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58. Prepared 2026-10-12. This file records only the sources this preparation rechecked on 2026-10-12. It reuses, and does not overwrite, the accepted pins in [`../route-restrictions/SOURCE_EVIDENCE.md`](../route-restrictions/SOURCE_EVIDENCE.md).

Evidence vocabulary: `DOCUMENTED` (an official page describes the behavior), `SOURCE_INSPECTED` (a pinned public source shows it), `LOCAL_TESTED` (the accepted offline module exercised it), `PROVIDER_ACTUAL` (an approved provider call produced it), `NOT_RUN` (no evidence). This preparation added no `PROVIDER_ACTUAL` evidence.

## 1. Retrieval tools

| Tool | Use on 2026-10-12 |
|---|---|
| Context7 `resolve-library-id` "Privy" | Resolved `/llmstxt/privy_io_llms_txt` (High reputation, 7829 snippets). Three `query-docs` calls: condition fields/operators; ownership and administration; dynamic-bytes/tuple support and decode behavior. |
| Exa `web_fetch_exa` | Fetched the seven primary Privy pages below, plus the Kuru addresses page and the Monad network page. |
| `curl` | Re-fetched the two pinned Kuru Flow source files at the retained commit and recomputed SHA256. |

No authenticated console, account, provider or signing call ran. No credential was read.

## 2. Primary Privy pages rechecked (2026-10-12)

These pages are rolling and publish no version pin. Claims below are `DOCUMENTED` unless marked otherwise.

| ID | URL | Supports |
|---|---|---|
| PV-OV | https://docs.privy.io/controls/policies/overview | Field sources `ethereum_transaction` and `ethereum_calldata`; `field` may be `function_name` or `function_name.param_name`; `ethereum_calldata` conditions must carry an `abi`; default DENY when no rule resolves; DENY precedence; a method with no rule is denied; for sign-and-broadcast, transaction simulation runs before policy evaluation and a simulation failure suppresses policy evaluation. |
| PV-EX | https://docs.privy.io/controls/policies/example-policies/ethereum | `ethereum_transaction` `to`/`value`/`chain_id` examples; `value` compared with a hex string; `ethereum_calldata` `transfer.amount` compared with `lte`; `function_name`-only example; the `abi` shape. |
| PV-CREATE | https://docs.privy.io/controls/policies/create-a-policy | Policies optionally have owners; **without an owner the policy can be updated by the app secret alone**. |
| PV-CS | https://docs.privy.io/controls/policies/condition-sets | `in_condition_set`; creating a condition set requires an owner; updating it requires an authorization signature; comparisons are case-insensitive for EVM addresses and hex byte strings reached through a signing field source (including address arguments on `ethereum_calldata`); every other comparison is exact. |
| PV-SP | https://docs.privy.io/controls/policies/stateful-policies | Aggregations; four primitives; a metric whose field is missing or whose calldata does not match the ABI **defaults to 0**; aggregations update after signing; per-app maximum of 10; supports `eth_signTransaction` and `eth_signUserOperation`. |
| PV-WALLET | https://docs.privy.io/wallets/wallets/update-a-wallet | `PATCH /v1/wallets/{wallet_id}`; only one policy per wallet; `additional_signers` as `{signer_id}`; a wallet with `owner_id` requires an authorization signature. |
| PV-SRV | https://docs.privy.io/controls/authorization-keys/owners/configuration/user/server-updates | A 1-of-k key quorum that owns a wallet; a **satisfying** member can unilaterally update the wallet policies and additional signers while the user is offline. |

### Documentation versus inference (Privy)

- `DOCUMENTED`: `chain_id`, `to`, `value`, `function_name` conditions, and the `abi` requirement for calldata.
- `DOCUMENTED`: flat `address` and `uint256` calldata argument examples. No dynamic `bytes`, array, or tuple-component argument example appears on any rechecked page.
- `INFERENCE` (not a proof): a `function_name.param_name` path to a tuple component, such as `executeSwap.intent.amountUserSells`, is plausible because the field grammar permits dot paths and `ethereum_typed_data_message` documents a dot path into a nested struct (`owner.wallet`). This is a different field source and is not a calldata proof. Treat the tuple path as `UNKNOWN`.
- `UNKNOWN`: dynamic-`bytes` equality or bound on `program`. The field grammar and `eq` operator are documented; no source shows a dynamic `bytes` argument.
- `UNKNOWN`: whether the provider accepts a decimal string for `value`; the example uses a hex string, and the accepted local model compares decimal strings.
- Discrepancies retained: PV-OV lists `neq` and a wider operator set than PV-SP; PV-SP lists `neq` but omits `contains`/`starts_with`/`ends_with`; the condition `value` type appears as `string | string[]` (earlier sources) and `string | number | string[]` (PV-SP).

## 3. Kuru and Monad sources rechecked (2026-10-12)

| ID | URL or pin | Result |
|---|---|---|
| K1 | https://docs.kuru.io/contracts/Contract-addresses | Mainnet Flow addresses unchanged: `KuruFlowEntrypoint (Aggregator)` `0xb3e6778480b2E488385E8205eA05E20060B813cb`; `KuruFlowRouter` `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2`; `KuruForwarder` `0x974E61BBa9C4704E8Bcc1923fdC3527B41323FAA`. Testnet page still lists **no Flow entrypoint or router**. Official tokens: USDC `0x754704Bc059F8C67012fEd69BC8A327a5aafb603`, WMON `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A`. |
| K4 | https://docs.monad.xyz/developer-essentials/network-information | Mainnet chain `143`; WMON `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A`; current version `v0.15.2` / `MONAD_NINE`. |
| S1 | `Kuru-contracts-flow-public` commit `70bc0c93c073f78697b99848eedefbf5dbe698c7`, `src/entrypoint/KuruFlowEntrypoint.sol` | SHA256 `15e19667ee20389b396a51143dccf7bbd31a701c610f1d78978c84f3b7fd1841` — **matches the retained P20 pin**. |
| S2 | same commit, `src/entrypoint/KuruFlowEntrypointTypes.sol` | SHA256 `44d913012de00a2814e62f1e9c45c4408c8407c0457325de41efabecd05df1ac` — **matches the retained P20 pin**. |

### Pinned-source reading (S1, S2)

- `executeSwap(SwapIntent, FeeCollection, bytes calldata program)` and `executeSwapWithReceiver(SwapIntent, FeeCollection, bytes calldata program, address receiver)` exist at the pinned commit.
- `SwapIntent { tokenUserBuys, minAmountUserBuys, tokenUserSells, amountUserSells }`; `FeeCollection { feeCollectorAddress, feeBps, referrerAddress, referrerFeeBps, isInTokenFee }`. No maximum-output and no deadline field.
- The entrypoint forwards `program` to the router with `minAmountOut = 0` and checks `amountOut >= minAmountUserBuys` after fees. It sets and resets its own router approval. A native input requires `msg.value >= amountUserSells`.
- Limit: the pinned source is the public Flow repository. It does not prove the deployed `143` bytecode matches it. Deployed-code presence was recorded by the accepted package; bytecode identity stays `UNKNOWN`.

## 4. Reused accepted evidence (not re-derived)

- `../route-restrictions/SOURCE_EVIDENCE.md` P1–P10 (Privy), K1–K6 (Kuru/Monad), S1–S2 (pins), R1–R9 (retained prior evidence).
- `../route-restrictions/PRIVY_POLICY_BINDING_FEASIBILITY.md`, `CONTROL_RESTRICTIONS.md`, `NETWORK_DECISION.md`, `LIVE_TEST_PACKET.md`, `POLICY_BINDING_INTEGRATION_NOTE.md`, `WORKED_CAPACITY.md`.
- `docs/qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md` R2 (bounded testnet `10143` sign-only; not Kuru, mainnet or cross-user isolation).
- `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` (private workspace research; Assensus X Layer proof is a pattern, not Monad/Kuru enforcement; Veridex local fakes are not live proof).

## 5. Claim boundary

- This file proves capability from documentation and pinned source. It proves no working provider restriction.
- Exact `program` byte equality at the provider, tuple-component calldata paths, and deployed `143` bytecode identity stay `UNKNOWN`.
- The position-inventory restriction stays `UNSUPPORTED` at the independent layer.
- A local `AUTHORED_POLICY_ALLOW` is never `PROVIDER_ACTUAL`.
