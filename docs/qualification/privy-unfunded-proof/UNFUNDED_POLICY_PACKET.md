# Frozen unfunded policy-layer packet

Task `UNFUNDED-POLICY-PROOF-L3-20261022`. Status `LOCAL_TESTED`. Provider proof `UNQUALIFIED` until the controller runs the live proof. This file freezes one packet. It approves no trade, funding, broadcast or policy change.

## Scope

This packet proves one claim only: the real Privy policy `c30racyru6duaipj815cvjce` refuses the out-of-policy signing requests below and allows the in-policy requests below. The agent wallet `0x91BB52A63c91986813288965e4681FF111De1b63` is unfunded. The runner has no broadcast path. A signed transaction cannot move funds.

Controls enforced by the host, the Kuru contract or a later stage are outside this proof. The packet records their true states and does not claim them.

## Identities

| Item | Value |
| --- | --- |
| App | `cmuyj4smt00tw0dla2j19tlu7` |
| Executor (agent signer key quorum) | `zu1qjdfqlbcq1ct7sdxendgg` |
| Wallet owner | `a5gwmgrsn6903ac09lphyv9a` |
| Policy owner | `a5gwmgrsn6903ac09lphyv9a` |
| Wallet id | `bsb2feecuxl81dl5jz4u9xxo` |
| Wallet address | `0x91BB52A63c91986813288965e4681FF111De1b63` |
| Policy id | `c30racyru6duaipj815cvjce` |
| Policy body SHA-256 | `cd543346a75ab342e04282f4fd5764ff0f19e1d7a354d5f09d208e53ad0d7477` |
| Network | `eip155:143` (Monad mainnet) |
| Signing route | `https://api.privy.io/v1/wallets/bsb2feecuxl81dl5jz4u9xxo/rpc` |
| Signing method | `eth_signTransaction` |
| Packet SHA-256 | `5835579cc1a0f1935d3e9b0c29bf7521d651e30d47e40c79f9cc32f34ebf0edf` |
| Table manifest SHA-256 | `62107fc64cc96387f835093962a032b88f8169d106afdce17b584cd762ba2a01` |
| Profile id | `privy.raw.v1` (profile `raw`) |
| Attempt identity | `unfunded-policy-proof-1` |
| Packet expiry | `1793836800` (2026-11-05T00:00:00Z) |
| Auth-header expiry | `1793836800000` |

The policy body hash is SHA-256 over the canonical JSON of `policy_body` in `PRIVY_SETUP1.json` (sorted keys, compact separators, UTF-8). The whole setup record has its own SHA-256 `7b272a7fb04546ec8c1729d8c70b308329454c91e90e2e0241c72bb0fefaa9cd`.

The executor is the only identity outside policy administration. The builder owns both the wallet and the policy. The packet records this honestly: the accepted check refused equality between the wallet owner and the policy owner, but this real setup has one human owner and one agent executor. The check now refuses a policy owner or wallet owner that is the executor. A policy change still needs the builder key.

## Exact request body

Every row uses one canonical body:

```json
{"method":"eth_signTransaction","params":{"transaction":{"chain_id":143,"data":"0x...","gas_limit":100000,"max_fee_per_gas":100000000000,"max_priority_fee_per_gas":2000000000,"nonce":0,"to":"0x...","type":2,"value":0}}}
```

The exact key set is `type`, `chain_id`, `nonce`, `to`, `value`, `data`, `gas_limit`, `max_fee_per_gas`, `max_priority_fee_per_gas`. Bytes are `json.dumps(body, sort_keys=True, separators=(",", ":"))` in UTF-8. The request envelope hash is the SHA-256 of `{"body_sha256":..., "headers":{}, "http_method":"POST", "url":...}`. No row sets a request header; the transport adds the frozen `privy-request-expiry` value.

A quantity at or below `2**53 - 1` is a JSON number. A quantity above that bound is a canonical lowercase `0x` string with no leading zeros. The body never carries a JSON number above `2**53 - 1`. The five deposit rows use a hex `value`:

| Row | Logical value (wei) | Wire `value` |
| --- | --- | --- |
| `raw.allow_deposit_1_mon` | 1000000000000000000 | `0xde0b6b3a7640000` |
| `raw.allow_deposit_at_cap` | 70000000000000000000 | `0x3cb71f51fc5580000` |
| `raw.deny_deposit_wrong_chain` | 1000000000000000000 | `0xde0b6b3a7640000` |
| `raw.deny_deposit_wrong_to` | 1000000000000000000 | `0xde0b6b3a7640000` |
| `raw.deny_deposit_above_cap` | 70000000000000000001 | `0x3cb71f51fc5580001` |

The other rows use small `value` numbers (`0` or `1`). The `approve` amount and the swap tuple live inside `data`, which is a hex string; they are not quantity fields. `chain_id` stays a JSON number in the safe-integer range. The signed-field check decodes the wire value back to the exact integer and compares it with the frozen unsigned value. A one-wei difference is `SIGNED_VALUE_MISMATCH` and a `BREACH`.

The fee fields are fixed for signing only. The policy does not constrain them. `nonce` is `0` for the fresh, unfunded wallet. The operator rechecks the wallet nonce and balance before the run.

## Ordered requests and expected outcomes

The runner runs this exact order. The first row is the positive control; no negative is admitted before its saved `ALLOW` binds to this packet, request and policy. The first negative is the bootstrap: it is a chain-143 request, so the policy engine evaluates a policy-owned condition even if a wrong chain is rejected by a different provider check.

| # | Specimen | Expected | Policy boundary | Chain | `to` | `value` (wei) | `gas_limit` | `data` | `request_sha256` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `raw.allow_deposit_1_mon` | `ALLOW` | R1 all conditions | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 1000000000000000000 | 100000 | `0xd0e30db0` | `f3a177f244b7df7cb97a19b0b448f0c28207e4d799981dc586f94c685b45fbc5` |
| 2 | `raw.allow_deposit_at_cap` | `ALLOW` | R1 `value` `lte` 70 MON | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 70000000000000000000 | 100000 | `0xd0e30db0` | `ac375d66c36cf3d7499cd1624808035ab853d6316423fe43330430a96926db34` |
| 3 | `raw.allow_approve_at_cap` | `ALLOW` | R2 all conditions | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 0 | 100000 | `0x095ea7b3...` (spender entrypoint, amount 70 MON) | `31d39674e5e49b16f918179dd3a8326cbfb4c15fc66a8f35e575336ed708cf81` |
| 4 | `raw.allow_swap_zero_value` | `ALLOW` | R3 all conditions | 143 | `0xb3e6778480b2e488385e8205ea05e20060b813cb` | 0 | 500000 | `0xce1e7030...` (exact below) | `f31cde63df34f78379574114e4705415df911a72d78779ba679c294cb98e3946` |
| 5 | `raw.deny_deposit_wrong_to` | `POLICY_DENY` | R1 `to` `eq` WMON | 143 | `0x000000000000000000000000000000000000dead` | 1000000000000000000 | 100000 | `0xd0e30db0` | `4a06afc533a587960769c568f5462d0a98312d797c08fdb92778859433a75761` |
| 6 | `raw.deny_deposit_wrong_chain` | `POLICY_DENY` | R1 `chain_id` `eq` 143 | 10143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 1000000000000000000 | 100000 | `0xd0e30db0` | `e46b5391dd3454334bc4449ed96442c6fd20ad3cd3f7ce06e1f75d5b1b7460f2` |
| 7 | `raw.deny_approve_wrong_chain` | `POLICY_DENY` | R2 `chain_id` `eq` 143 | 10143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 0 | 100000 | `0x095ea7b3...` (spender entrypoint, amount 70 MON) | `3ed7df166475122dde27d7aeec4dac97ac29f208d5b321dc85d9fdb3be768f3f` |
| 8 | `raw.deny_swap_wrong_chain` | `POLICY_DENY` | R3 `chain_id` `eq` 143 | 10143 | `0xb3e6778480b2e488385e8205ea05e20060b813cb` | 0 | 500000 | `0xce1e7030...` (exact below) | `9692f91e51babf1b2be3dca5a02f4a8a867a18ebfbfa38ca21adab9ed985d827` |
| 9 | `raw.deny_approve_wrong_to` | `POLICY_DENY` | R2 `to` `eq` WMON | 143 | `0x000000000000000000000000000000000000dead` | 0 | 100000 | `0x095ea7b3...` (spender entrypoint, amount 70 MON) | `d0969fa5c4bf781539446ae164fc02dfc9d0ae3540a4c52fb25d63b173480315` |
| 10 | `raw.deny_swap_wrong_to` | `POLICY_DENY` | R3 `to` `eq` entrypoint | 143 | `0x000000000000000000000000000000000000dead` | 0 | 500000 | `0xce1e7030...` (exact below) | `4e54dfb167ee31d019b7f9cf621b87a9713205bad94098904913302802bfc058` |
| 11 | `raw.deny_wmon_wrong_function` | `POLICY_DENY` | R1/R2 `function_name` not `deposit`/`approve` | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 0 | 100000 | `0xa9059cbb...` (`transfer(sink, 1)`) | `6810d9fe5ecf519d5ca4f3aa4a435c6658f8500f8ef34d24eee0da633935b0d3` |
| 12 | `raw.deny_entrypoint_wrong_function` | `POLICY_DENY` | R3 `function_name` not `executeSwap` | 143 | `0xb3e6778480b2e488385e8205ea05e20060b813cb` | 0 | 100000 | `0xd0e30db0` | `c76af7e72ead99978fac762a685ceafd687ca3cb04bdce92bc5d9250befc35af` |
| 13 | `raw.deny_approve_other_spender` | `POLICY_DENY` | R2 `approve.spender` `eq` entrypoint | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 0 | 100000 | `0x095ea7b3...` (spender sink, amount 70 MON) | `622e80643d6c122968bab33068b48c6665c0a8e8a363cf7baa5990617220a5af` |
| 14 | `raw.deny_approve_above_cap` | `POLICY_DENY` | R2 `approve.amount` `lte` 70 MON | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 0 | 100000 | `0x095ea7b3...` (amount 70 MON + 1) | `9e632b9f5be6a385f12525926e55dbbcffb4bdfe9e3e3077236e8f404998b526` |
| 15 | `raw.deny_approve_with_value` | `POLICY_DENY` | R2 `value` `eq` 0 | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 1 | 100000 | `0x095ea7b3...` (amount 70 MON) | `47bd9c58d2ce5ea6112f807fa9bbbd80a197789cacc413e535917eca395ed3d4` |
| 16 | `raw.deny_deposit_above_cap` | `POLICY_DENY` | R1 `value` `lte` 70 MON | 143 | `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | 70000000000000000001 | 100000 | `0xd0e30db0` | `a8b918f8066bba734aea573f4ac6359a8056aa9bbcddf21b0170226729e14f50` |
| 17 | `raw.deny_swap_with_mon` | `POLICY_DENY` | R3 `value` `eq` 0 | 143 | `0xb3e6778480b2e488385e8205ea05e20060b813cb` | 1 | 500000 | `0xce1e7030...` (exact below) | `ac3277ebd460be8fedf0f1745d163eda5e3d8becea9b0027bf727d18d689b652` |
| 18 | `raw.deny_plain_mon_transfer` | `POLICY_DENY` | No ALLOW rule matches | 143 | `0x000000000000000000000000000000000000dead` | 1 | 100000 | `0x` | `24445a29234ebac7936acaa2c2ca4eb0f8867d122af7303a5afb48dcafe1dae4` |

The sink `0x000000000000000000000000000000000000dead` is a burn address, not a trade recipient. The swap pair is WMON/WMON with a one-byte program `0x01`; it is an inert policy sentinel, not a route.

### Exact `executeSwap` data

```
0xce1e70300000000000000000000000003bd359c1119da7da1d913d1c4d2b7c461115433a0000000000000000000000000000000000000000000000000de0b6b3a76400000000000000000000000000003bd359c1119da7da1d913d1c4d2b7c461115433a0000000000000000000000000000000000000000000000001bc16d674ec8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000010100000000000000000000000000000000000000000000000000000000000000
```

The selector `0xce1e7030` is the Keccak-256 selector for `executeSwap((address,uint256,address,uint256),(address,uint256,address,uint256,bool),bytes)`, the five-component fees tuple in the real policy ABI. The accepted Kuru Flow decoder decodes this exact layout: intent tuple (4 words), fees tuple (5 words, the last a zero `isInTokenFee`), bytes offset `320`, length `1`, one program byte `01`, canonical zero padding.

## Policy-owned and out-of-scope controls

The policy owns these P21 rows for this packet: `chain` (1), `wallet_signer_binding` (2), `entrypoint_method` (3) and `approvals` (9). The packet tests each of them.

These rows stay outside this proof and keep their true states: `input_output_assets` (4) `UNKNOWN`, `raw_input` (5) `SOURCE_INSPECTED`, `recipient` (6) `SOURCE_INSPECTED`, `minimum_output` (7) `SOURCE_INSPECTED`, `fees` (8) `SOURCE_INSPECTED`, `gas_action_capacity` (10) `UNSET`, `expiry_freshness` (11) `DOCUMENTED`, `opaque_program` (12) `UNKNOWN`. The separate position-inventory obligation stays `UNSUPPORTED`.

The swap allow does not prove an input/output asset bound, a minimum-output bound, a fee bound or an opaque-program bound. Privy has no condition on those fields in this policy. The Kuru contract and the host own them. A successful swap signature is not a trade approval.

## Reply profile and bootstrap

The profile `privy.raw.v1` is registered from current Privy documentation: a denied signing request returns HTTP `400` with code `policy_violation`. The accepted code reads `code`, `error.code` and the string `error` from the JSON reply; it never saves reply text.

The first negative, `raw.deny_deposit_wrong_chain`, is the bootstrap. Its bounded capture records `status`, `media_type`, `content_type_sha256`, `byte_count`, `raw_body_sha256`, `metadata_valid` and `captured_at`. It records no body text, credential or signature.

If the observed status or code differs from the registered profile, the runner classifies the reply `UNKNOWN`, writes `STOP.json`, and refuses every later specimen. The operator must then stop, keep the capture, and request a reviewed profile update. The packet does not claim a refusal that the provider did not return.

## Run commands

Dry run (no credential, no socket, no file effect):

```
PYTHONPATH=<checkout>/apps/api/src:<checkout> <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.actual_run --dry-run
```

Live run (operator only, after an independent zero-balance read):

```
PRIVY_APP_ID=... PRIVY_APP_SECRET=... PRIVY_AGENT_KEY_FILE=<agent pem> \
PYTHONPATH=<checkout>/apps/api/src:<checkout> <venv>/bin/python -B -s \
  -m scripts.privy_unfunded_proof.actual_run --store <new empty dir> --confirm-unfunded
```

The command refuses an existing store, a missing confirmation, a missing environment value, an unreadable key, an expired packet, a profile refusal and any unexpected outcome. It stops on the first `BREACH`, `UNKNOWN` or mismatch and never retries.

## Limits

- No worker call to Privy, no `edge-os/.env` read and no agent-key use produced this packet.
- The live run signs only. It never broadcasts. The wallet must be unfunded.
- A `LOCAL_TESTED` result proves the packet machinery, not Privy enforcement. The live run is the provider proof.
- The packet expires at `1793836800`. A later run needs a new frozen packet and a new review.
- The Kuru deployed source and deployed-code identity stay `UNRESOLVED_KURU_SOURCE` and `UNRESOLVED_KURU_DEPLOYED_CODE`. This proof does not depend on them.
