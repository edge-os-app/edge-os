# Independent-policy capability matrix for the selected Kuru Flow route

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58. Prepared 2026-10-12. Documentation and unsigned preparation only.

Scope: what the current documented independent wallet-policy controls can express for the selected route `executeSwap(SwapIntent, FeeCollection, bytes program)` (and its `executeSwapWithReceiver` variant) on Monad mainnet `143`. Every affirmative claim carries a primary source. Inference and unknown stay marked. A local simulation is not provider enforcement.

Source IDs: `PV-OV`, `PV-EX`, `PV-CS`, `PV-SP`, `PV-CREATE`, `PV-WALLET`, `PV-SRV` (rechecked 2026-10-12, see [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md)); `S1`, `S2` (pinned Kuru source). Evidence classes: `DOCUMENTED`, `SOURCE_INSPECTED`, `LOCAL_TESTED`, `PROVIDER_ACTUAL`, `NOT_RUN`, `UNKNOWN`, `UNSUPPORTED`.

## 1. Minimal supported binding

The **minimum** independent binding the reviewed sources support is:

| Element | Condition | Field source | Evidence |
|---|---|---|---|
| Chain | `chain_id` `eq` the selected chain id | `ethereum_transaction` | `DOCUMENTED` (PV-OV, PV-EX) |
| Contract | `to` `eq` the approved Flow entrypoint | `ethereum_transaction` | `DOCUMENTED` (PV-OV, PV-EX) |
| Method | `function_name` `eq` the approved method, with the pinned ABI | `ethereum_calldata` (+ `abi`) | `DOCUMENTED` (PV-OV, PV-EX) |
| Native value | `value` `eq` the approved input raw for a native input, or `0` for an ERC-20 input | `ethereum_transaction` | `DOCUMENTED` (PV-OV, PV-EX) |

This binding constrains only the chain, the contract, the function and the native transaction value. It does **not** constrain the opaque `program`, the intent or fee tuple components, the tokens, the amounts, the minimum output, the recipient (for `executeSwap`) or approvals. An outer `to == entrypoint` allowlist is **necessary but insufficient**; the mandatory controls below stay unmet.

## 2. Control-by-control matrix

| # | Control | Required restriction | Proposed independent condition | Privy field / operator | Argument type | Independent evidence | Local model semantics | What would prove it |
|---|---|---|---|---|---|---|---|---|
| 1 | `chain` | Exactly Monad `143` (or `10143`); one network per approval | `ethereum_transaction.chain_id` `eq` `<chain_id>` | `ethereum_transaction.chain_id` / `eq` | integer (decimal string) | `DOCUMENTED` | `_transaction_fact("chain_id")` compared exactly | Already documented; provider positive + wrong-chain denial control |
| 2 | `wallet_signer_binding` | Bind the action to the exact agent wallet; policy names that wallet | wallet-level attachment, not a calldata condition | (wallet `policy_ids`; one policy per wallet) | identity | `DOCUMENTED` (PV-WALLET) / cross-user isolation `NOT_RUN` | local model is wallet-agnostic | provider control that a different wallet is not covered by this policy |
| 3 | `entrypoint_method` | Exact entrypoint and exact method | `to` `eq` entrypoint **and** `function_name` `eq` method | `ethereum_transaction.to` / `eq`; `ethereum_calldata.function_name` / `eq` (+ `abi`) | address; string | `DOCUMENTED` | compared exactly; case-insensitive for the address | deployed-ABI equivalence `UNKNOWN`; provider positive + wrong-contract and wrong-function denials |
| 4 | `input_output_assets` | Limit input and output tokens to the adopted assets | `executeSwap.intent.tokenUserSells` and `executeSwap.intent.tokenUserBuys` `eq` adopted token addresses | `ethereum_calldata.<fn>.intent.<token>` / `eq` | **tuple component** (address inside tuple) | `UNKNOWN` | local model compares the derived argument, but that path is not documented | provider control that the tuple-component path is accepted; a positive and a swapped-token denial |
| 5 | `raw_input` | Exact non-negative base-10 base-unit input equal to the approved input | `executeSwap.intent.amountUserSells` `eq` approved raw | `ethereum_calldata.<fn>.intent.amountUserSells` / `eq` | **tuple component** (uint256) | `UNKNOWN` | local model compares exactly | provider control for the uint256 tuple path; a changed-amount denial |
| 6 | `recipient` | Only the agent wallet (`msg.sender`) or an allowed explicit receiver | For `executeSwap`: no calldata argument (the signer is the wallet). For `executeSwapWithReceiver`: `receiver` `eq` the allowed receiver | `ethereum_calldata.<fn>.receiver` / `eq` | flat `address` (receiver method only); none for `executeSwap` | `DOCUMENTED` for the flat receiver arg; **`UNSUPPORTED` at calldata for `executeSwap`** | local model reads `receiver` when present | a provider control on `executeSwapWithReceiver.receiver`; for `executeSwap`, recipient is enforced by the contract and the wallet binding |
| 7 | `minimum_output` | A real minimum received at or below the quote | `executeSwap.intent.minAmountUserBuys` `eq` approved minimum | `ethereum_calldata.<fn>.intent.minAmountUserBuys` / `eq` | **tuple component** (uint256) | `UNKNOWN` | local model compares exactly | provider control for the tuple path; a lowered/raised minimum denial |
| 8 | `fees` | Fee bound and each adopted fee value, collector, referrer and mode | `executeSwap.fees.feeBps`, `.referrerFeeBps`, `.feeCollectorAddress`, `.referrerAddress`, `.isInTokenFee` `eq` adopted values | `ethereum_calldata.<fn>.fees.<field>` / `eq` | **tuple components** (`uint256`, `address`, `bool`) | `UNKNOWN` | local model compares exactly (`true`/`false` for the bool) | provider control for each tuple path; per-field changed-value denials |
| 9 | `approvals` | Owner allowance to the entrypoint is declared, bounded and revoked | none available | **no field source reads token allowance** | n/a | `UNSUPPORTED` (independent layer) | local control checker: `ALLOWANCE_UNKNOWN` / `ALLOWANCE_NOT_APPROVED` | none documented; stays `UNSUPPORTED` unless a mechanism is proved |
| 10 | `gas_action_capacity` | Known native gas budget, action budget, no over-cap actual | Only `value` (native notional) is expressible; the gas budget itself is not | `ethereum_transaction.value` / `eq` | integer | `DOCUMENTED` for `value`; gas budget `UNSET` | local model separates native value from the token notional | exact budget is `UNSET`; unknown is not zero |
| 11 | `expiry_freshness` | Bounded quote/input age and local intent/mandate expiry | none (the Flow intent has no on-chain deadline; no calldata time field) | n/a | n/a | `HOST` only; `UNSUPPORTED` at independent layer | local control checker handles freshness/expiry at `HOST` | no policy time-condition documented for calldata |
| 12 | `opaque_program` | Constrain the opaque route bytes; at least one byte | `executeSwap.program` `eq` the approved program hex | `ethereum_calldata.<fn>.program` / `eq` | **dynamic `bytes`** | **`UNKNOWN`** (no dynamic-`bytes` example) | local model compares case-insensitively for hex byte strings | provider positive for `program` equality plus a changed-program denial, isolated from local counters |
| 13 | `position_inventory` | Sell permission from Edge OS position inventory | none | **no field source reads the position ledger** | n/a | `UNSUPPORTED` (independent layer) / `LOCAL_TESTED` (`HOST`) | local capacity arithmetic (see `../route-restrictions/WORKED_CAPACITY.md`) | none documented; an independent inventory control stays `UNSUPPORTED` unless an actual mechanism is proved |

## 3. Exact units, ABI, decode, case and default semantics

| Topic | Rule | Evidence |
|---|---|---|
| Units | Intent amounts are `uint256` base units. Native MON is `18` decimals (gas separate); USDC is `6` decimals. Raw amounts are canonical base-10 with no sign, float, Boolean, leading zero or trailing character. | `S2` (types), accepted adapter `types.py` |
| Native vs token notional | The `value` condition equals the native input raw for a native input and `0` for an ERC-20 input. Gas stays separate from the token notional. | `PV-OV`; `S1` (`msg.value >= amountUserSells`) |
| Value encoding | `UNKNOWN`: the `value` example uses a hex string (`0x2386F26FC10000`), while the accepted local model compares decimal strings. Whether the provider accepts a decimal string for `value` is not documented. | `PV-EX`; accepted `types.py`; [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md) §2 |
| ABI | Every `ethereum_calldata` condition must carry an `abi`. The pinned ABI is `executeSwap(intent tuple, fees tuple, bytes program)` plus `address receiver` for the receiver variant. | `PV-OV`, `PV-EX`; `S1` |
| Calldata decode | A condition that cannot decode against the `abi` evaluates false. A typed-data mismatch also evaluates false, so a permissive `ALLOW` rule can then sign. | `PV-SP` (metric default 0), accepted P21 note P9 |
| Aggregation decode | A metric whose field is missing or whose calldata does not match the ABI **defaults to 0** — a permissive fallthrough for aggregation-based limits. | `PV-SP` |
| Comparison case | Case-insensitive for EVM addresses and hex byte strings reached through a signing field source (including address arguments on `ethereum_calldata`). Every other comparison is exact. | `PV-CS` |
| Default and precedence | No matching rule → `DENY`. `DENY` takes precedence over `ALLOW`. A method with no rule is denied. | `PV-OV` |
| Simulation interaction | For sign-and-broadcast, transaction simulation runs **before** policy evaluation; a simulation failure suppresses policy evaluation and returns the simulation error, not a policy violation. | `PV-OV` |

Residual hazard: because a decode failure and an aggregation mismatch can both fall through permissively, the binding must use a default-deny `ALLOW` design (an allowlist rule plus no permissive fallback). The selected binding already uses exactly one `ALLOW` rule (accepted `policy_request.py`), but this is a local authored choice, not a proven provider behavior.

## 4. Findings

- **Supported (documented):** `chain_id`, `to`, `function_name`, `value`, and flat `address`/`uint256` calldata arguments (for example the `executeSwapWithReceiver.receiver` address). Wallet-level attachment with one policy per wallet.
- **Unknown (needs a provider control):** the dynamic `bytes` `program`; every tuple-component path (`intent.*`, `fees.*`).
- **Unsupported at the independent layer:** approvals (no field source reads allowance); expiry/freshness (no calldata time field); position inventory (no position-ledger field source). These stay enforced only at `HOST`/`CONTRACT`.
- **Minimal supported binding is insufficient.** Rows 4, 5, 7, 8 and 12 remain unproven, and row 12 is the limiting mandatory control.

## 5. Claim boundary

- This matrix proves expressibility from documents and pinned source. It proves no working provider restriction.
- The exact `program` byte equality, the tuple-component path and the deployed `143` bytecode identity stay `UNKNOWN`.
- A local `AUTHORED_POLICY_ALLOW` is authored behavior only; it is never `PROVIDER_ACTUAL`.
