# Unsigned positive and adversarial worked cases

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58. Prepared 2026-10-12. Documentation and unsigned preparation only.

Bounded machine vectors: [`worked_vectors.json`](worked_vectors.json) (schema `p21-independent-enforcement/1`). They tie to the accepted route/profile/ABI and the accepted adapter's original-action identity. They are data for a future released packet, not a new test suite.

## 1. What the vectors are tied to

- **Route/profile.** The accepted `truthful_route_profile` `truthful-2026-10-10` in [`../route-restrictions/fixtures.json`](../route-restrictions/fixtures.json). Its `opaque_program` stays `UNKNOWN` and `gas_action_capacity` stays `UNSET`.
- **ABI.** The pinned Flow entrypoint methods `executeSwap(SwapIntent, FeeCollection, bytes program)` and `executeSwapWithReceiver(SwapIntent, FeeCollection, bytes program, address receiver)` (`S1`, `S2`).
- **Original-action identity.** The accepted adapter's `candidate_identity` over the normalized payload. The `executeSwap` vector identity is `sha256:2c176702addc761f494c1a9d23130683991dc44ef577e314b19b72c186e4e05b`, computed with the accepted `edge_os_api.kuru_flow.types.candidate_identity` function. It is **not** an Ethereum transaction hash.
- **Baselines.** Three approved configurations in the `baselines` array: `native_zero_fee` (pinned default), `native_nonzero_fee`, and `erc20_zero_value`. The two non-default baselines need their own approved policy content and signature budget, marked `REQUIRED_DECISION`; they are not implicit authority.
- **Local semantics.** The accepted offline module `edge_os_api.kuru_flow.policy_binding`.

## 2. Verdict vocabulary

| Field | Values |
|---|---|
| Local layer | `AUTHORED_POLICY_ALLOW`, `BLOCKED`, `DECODE_BLOCKED`, `HOST_BLOCKED`, `NOT_APPLICABLE` |
| Independent layer | `NOT_RUN`, `DENY_REQUIRED`, `PROVIDER_POSITIVE_REQUIRED`, `UNSUPPORTED`, `UNKNOWN` |

A local `AUTHORED_POLICY_ALLOW` is authored behaviour only. It is never an independent provider result. `DENY_REQUIRED` means an isolated provider denial must be observed; it is not a claim.

## 3. Diagnostic mutation rule

A denial case proves the control it names only when it changes **one** guarded fact under a declared baseline. A case that changes two guarded facts at once is non-diagnostic: a provider denial cannot show which control caused it.

- Every diagnostic denial case carries `"diagnostic": true` and a single changed fact relative to its `baseline`.
- The `native_nonzero_fee` and `erc20_zero_value` baselines exist so the collector, referrer, fee-mode, ERC-20 value and ERC-20 amount controls can be tested with one changed fact each. Their extra policy, signature and test budget stays `REQUIRED_DECISION`.
- The `admin_attempt` pair is split: `admin_attempt_local_setup` records the unseparated default precondition (local `POLICY_ADMIN_NOT_SEPARATED`), and `admin_attempt_override_provider` records the desired provider denial under a **separated** policy-resource owner. Those are opposite preconditions and must not be combined.
- Non-diagnostic informational cases carry `"diagnostic": false`.

## 4. Case coverage

| Group | Cases | Expected local | Expected independent | Distinguishing evidence |
|---|---|---|---|---|
| Positive | `positive_execute_swap`, `positive_receiver`, `positive_native_nonzero_fee`, `positive_erc20_zero_value` | `AUTHORED_POLICY_ALLOW` | `PROVIDER_POSITIVE_REQUIRED` | A provider-signed positive the policy allows. Included so a refusal-only policy cannot pass. |
| Route bytes | `changed_program` | `BLOCKED` | `DENY_REQUIRED` | Isolated provider denial for changed `program` bytes. |
| Assets | `changed_input_asset`, `changed_output_asset` | `BLOCKED` | `DENY_REQUIRED` | Provider denial on the changed tuple token path. |
| Amounts / min output | `changed_amount_user_sells`, `changed_amount_user_sells_erc20`, `changed_min_output` | `BLOCKED` | `DENY_REQUIRED` | Provider denial on the changed tuple numeric path. The native case keeps the approved native value so only the amount differs; the ERC-20 case keeps value `0`. |
| Recipient | `changed_recipient` | `BLOCKED` | `DENY_REQUIRED` | Provider denial on the flat `receiver` argument (receiver variant only). |
| Fees | `changed_fee_bps`, `changed_referrer_fee_bps`, `changed_fee_collector`, `changed_referrer`, `changed_fee_mode` | `BLOCKED` | `DENY_REQUIRED` | One changed fee fact each; the collector/referrer/mode cases run under the `native_nonzero_fee` baseline. |
| Native value | `native_value_zero`, `native_value_high`, `native_value_missing`, `erc20_value_nonzero` | `BLOCKED` | `DENY_REQUIRED` | The ERC-20 case runs under `erc20_zero_value`, so only the value differs. Native notional and gas stay separate. |
| Chain/contract/function | `wrong_chain`, `wrong_contract`, `wrong_function`, `wrong_rpc_method` | `BLOCKED` | `DENY_REQUIRED` | Provider denial per wrong dimension. |
| Approvals | `approvals_unexpressible` | `NOT_APPLICABLE` | `UNSUPPORTED` | No field source reads allowance. |
| Capacity | `capacity_unset` | `NOT_APPLICABLE` | `UNSUPPORTED` | The exact gas/action budget is `UNSET`; the accepted checker returns `CAPACITY_UNKNOWN`. |
| Position inventory | `position_inventory_unexpressible` | `NOT_APPLICABLE` | `UNSUPPORTED` | No field source reads the position ledger; `HOST`-only capacity arithmetic. |
| Malformed decode | `malformed_program_empty`, `malformed_truncated` | `DECODE_BLOCKED` | `DENY_REQUIRED` | Provider denial on a non-decoding payload; confirm no permissive fallback signs. |
| Expiry (local) | `expiry_intent_past` | `HOST_BLOCKED` | `UNSUPPORTED` | Quote/input age and local mandate expiry stay `HOST`; they cannot revoke a broadcast. |
| Expiry (system time) | `expiry_system_time_field` | `NOT_APPLICABLE` | `UNKNOWN` | Privy documents the chain-agnostic `system.current_unix_timestamp` field; a fixed upper cutoff for this `eth_signTransaction` policy is an inference, not a proved selected-method control. |
| Revocation | `revocation_signer_removed` | `NOT_APPLICABLE` | `DENY_REQUIRED` | Post-removal provider denial not masked by an exhausted local counter. |
| Provider failure | `provider_lost_reply` | `NOT_APPLICABLE` | `NOT_RUN` | Recovery of the original action with no second economic action. |
| Policy weakening | `policy_weakening_ownerless`, `admin_attempt_local_setup`, `admin_attempt_override_provider` | `NOT_APPLICABLE` | `UNSUPPORTED` / `NOT_RUN` / `DENY_REQUIRED` | Bounded provider denial for an executor update attempt under a separated owner. |
| Restart / residual | `restart_original_action`, `residual_exposure` | `NOT_APPLICABLE` | `NOT_RUN` | Original-action identity preserved; explicit residual-exposure record. |

## 5. Isolated denial harness versus application execution

- The independent denial cases (`DENY_REQUIRED`) run in a **separate, isolated harness** under its own approval. That harness keeps production risk checks active and is **not** the application path.
- Actual application execution is a **different** approval: one controlled action under the qualification packet ([QUALIFICATION_PACKET.md](QUALIFICATION_PACKET.md)).
- **No case asks production risk checks to be disabled.** A local-exhausted counter must not mask a provider result; each denial is observed independently.
- A simulation failure is **not** policy-denial evidence. The provider runs simulation before policy evaluation for sign-and-broadcast, and a simulation failure suppresses policy evaluation (PV-OV). An insufficient-funds or reverting simulation therefore proves nothing about the policy.

## 6. Local-verdict consistency (accepted module)

The positive and single-fact mutation cases mirror the accepted `test_local_evaluation.py`. The `validate_binding` reasons in the vector metadata (`POLICY_ADMIN_OWNER_MISSING`, `POLICY_ADMIN_NOT_SEPARATED`, `POLICY_REQUEST_INCOMPLETE:<control>`) mirror `test_policy_request.py`. For the `restriction_checker.py` reasons: `CAPACITY_UNKNOWN` is its literal code, while `UNSUPPORTED_CONTROL:position_inventory` is an authored instance of its documented `UNSUPPORTED_CONTROL:<name>` pattern applied to a control that its mandatory matrix lists separately. This preparation adds no test that mirrors prose; it records data only.

## 7. Claim boundary

- These cases prove a local authored verdict and the evidence needed to distinguish it from an independent verdict. They prove no provider behaviour.
- `changed_program`, tuple paths, approvals, system-time-for-this-method and position inventory stay `UNKNOWN`/`UNSUPPORTED` at the independent layer until observed.
