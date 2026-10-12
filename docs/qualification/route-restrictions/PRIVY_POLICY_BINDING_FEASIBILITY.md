# Independent wallet-policy binding feasibility

Task `P21-POLICY-L4-20261012-01` v1, issue #20. Checked 2026-10-12. This note extends the route-restriction package. It is documentation and offline preparation only.

It runs no provider request, loads no credential, creates no wallet, changes no policy, signs nothing and broadcasts nothing. Full P21 stays OPEN.

## Verdict

- **DOCUMENTATION / PREPARATION: PASS within this scope.** The reviewed Privy sources show which policy conditions exist, which controls they can express, and who can change a policy. The offline module `kuru_flow/policy_binding/` builds and validates the declared policy request and simulates it locally.
- **Exact route-byte equality at the independent layer: `UNKNOWN`.** No reviewed source shows a bound or equality check on a dynamic `bytes` argument or on complete calldata.
- **Independent provider restriction: `NOT_RUN`.** A local simulation is `AUTHORED_POLICY_ALLOW` only. It is never a provider result.

A local pass is never `REAL_READY` and never a live approval.

## 1. The exact question

The selected route calls `KuruFlowEntrypoint` with `executeSwap(SwapIntent, FeeCollection, bytes program)`. The third argument, `program`, is the opaque route. The limiting mandatory control is `opaque_program` (row 12 of [CONTROL_RESTRICTIONS.md](CONTROL_RESTRICTIONS.md)). The outer `to == entrypoint` allowlist is necessary but insufficient.

This note answers whether Privy can independently restrict the `program` bytes, the complete calldata, or a supported equivalent.

## 2. Reviewed Privy capability

Privy policy rules use conditions. Each condition has a `field_source`, a `field`, an `operator`, a `value` and, for calldata sources, an `abi`.

| Capability | Reviewed result | Source |
|---|---|---|
| `ethereum_transaction` fields | The verbatim transaction object. Documented examples: `to`, `value`, `chain_id`. No documented raw `data` field. | P3 |
| `ethereum_calldata` fields | The decoded calldata. `field` is `function_name`, or `function_name.param_name` to match one argument. | P3, P4 |
| Calldata argument types shown | `address` and `uint256` argument examples only. No `bytes`, array or tuple-component example. | P4 |
| Operators | `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `in`, `in_condition_set`, `contains`, `starts_with`, `ends_with`. | P3, P6 |
| Condition value type | A string, or an array of strings. | P6 |
| Comparison case | Case-insensitive for EVM addresses and hex byte strings from a signing field source. Every other comparison is exact. | P5 |
| Default and precedence | A rule engine defaults to denial. A `DENY` rule takes precedence over `ALLOW`. | P9 |
| Decode failure | A condition that cannot decode against the ABI evaluates false. A typed-data mismatch also evaluates false, so a permissive `ALLOW` rule can then sign. | P9 |

Consequences for the selected route:

- **Complete calldata equality: `UNSUPPORTED` by documentation.** No reviewed field matches the whole raw calldata.
- **Dynamic `bytes` (`program`) equality: `UNKNOWN`.** The field grammar is `function_name.param_name`, and `eq`/`in` are documented operators. No example shows a dynamic `bytes` argument, and the case rule does not name it. Equality on the `program` bytes is plausible but unproven. It needs an actual provider positive and negative control.
- **Tuple-component arguments: `UNKNOWN`.** The intent and fee arguments live inside tuple parameters. The reviewed examples are flat arguments only. A path such as `executeSwap.intent.amountUserSells` is a best-effort attempt, not a documented path.

Because of the third and fourth points, the declared request cannot be called a complete binding. The `opaque_program`, `input_output_assets`, `raw_input`, `minimum_output`, `recipient` and `fees` controls stay unproven until a provider control confirms them.

## 3. Policy ownership and update authority

A policy can restrict the wallet. The policy itself has an owner.

| Fact | Reviewed result | Source |
|---|---|---|
| Policy `owner_id` | The authorization signature required to modify the policy later. | P8 |
| Wallet `policy_ids` | The policies enforced on the wallet. Only one policy per wallet is supported. | P7 |
| Additional signers | A signer can carry `override_policy_ids`. A wallet update adds signers and their override policies. | P7 |
| Key-quorum owner | A server authorization key that is a member of the wallet-owning key quorum **can unilaterally update the policies and signers**, even while the user is offline. | P7 |
| Additional signer | An additional signer cannot change the wallet owner, its signers or its policies, and cannot export the key. | R2 |

Consequence: the executor cannot be an owner of the wallet. If the application's authorization key sits in the wallet-owning key quorum, that key can loosen the policy. The safe shape is a user-owned wallet whose app key is only an additional signer with a restrictive override policy. This shape is a design requirement, not proven here. Missing ownership evidence stays unresolved.

## 4. Enforcement separation

The three layers stay separate.

| Layer | This route | Expressibility |
|---|---|---|
| `HOST` | Derives identity, binds the action, checks freshness and expiry. | Application accounting. Not independent enforcement. |
| `CONTRACT` | Enforces `amountUserSells`, `minAmountUserBuys`, recipient and fee bounds. | On-chain only. Not proof at the independent layer. |
| `INDEPENDENT_POLICY` | A Privy policy on the wallet. | Documented for chain, contract, function and simple arguments. Opaque `program` unproven. Position inventory unreadable. |

An application check cannot be described as independent wallet enforcement. A fake policy simulator cannot prove an independent provider restriction.

## 5. Offline implementation

New isolated module and tests:

- `apps/api/src/edge_os_api/kuru_flow/policy_binding/` builds the declared Privy-shaped policy request from the approved configuration, validates its coverage, and simulates it locally.
- `apps/api/tests/kuru_flow/policy_binding/` holds the offline unit tests.

The module reuses the accepted adapter decoder and types. It has no network, credential, signing or broadcast code path. It always reports `provider_executed: NOT_RUN`.

Run the offline checks from the repository root:

```sh
(cd apps/api && uv run --frozen pytest tests/kuru_flow -q)
```

## 6. Evidence classes

| Class | Meaning |
|---|---|
| `DOCUMENTED` | An official page describes the behavior. |
| `SOURCE_INSPECTED` | A pinned public source shows the behavior. |
| `LOCAL_TESTED` | The authored offline module or test exercised it. |
| `PROVIDER_ACTUAL` | An approved provider call produced the result. |
| `NOT_RUN` | No evidence exists yet. |

A local success is `LOCAL_TESTED` at most. It cannot become `PROVIDER_ACTUAL` without an actual provider run under a separate released packet.

## 7. Sources

This note reuses P1 and P2 from [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md#5-privy-official-documentation-checked-2026-10-10-reused-from-p20) and adds P3 to P9, recorded in the dated section of that file. Context7 resolved Privy as `/llmstxt/privy_io_llms_txt` and `/llmstxt/privy_io_llms-full_txt`. Exa fetched the official pages. These pages are rolling and publish no version for a pin.

## 8. Claim boundary

- This note proves policy expressibility from documents. It does not prove a working provider restriction.
- The exact `program` byte equality, the tuple-component path and the deployed ABI remain `UNKNOWN`.
- The position-inventory restriction stays `UNSUPPORTED` at the independent layer.
- A real action stays unavailable until a released packet proves the unproven controls, or the builder records a different enforcement design.
