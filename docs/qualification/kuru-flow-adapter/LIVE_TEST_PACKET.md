# Future bounded live-test packet (proposal)

**Proposal only. No live authority.** Prepared 2026-10-11. This packet requests one exact reviewed release for the P20 controlled action. It grants no signing, funding, faucet, approval, policy, quote or broadcast permission. The builder owns every consequential live value.

## 1. Network choice

- Candidate: **Monad mainnet `143`**. It is the only documented Flow path ([NETWORK_DECISION.md](../route-restrictions/NETWORK_DECISION.md)). Testnet `10143` Flow support stays `UNKNOWN`.
- No silent switch. The packet records the selected network and why. A testnet selection requires a source-backed testnet Flow entrypoint/router first.

## 2. Filled source-backed fields

| Field | Value | Class |
|---|---|---|
| Selected route | Kuru Flow fixed-input swap | `DOCUMENTED` |
| Mainnet entrypoint | `0xb3e6778480b2E488385E8205eA05E20060B813cb` | `DOCUMENTED`; deployed bytecode identity `UNKNOWN` |
| Mainnet router | `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` | `DOCUMENTED`; deployed bytecode identity `UNKNOWN` |
| Quote host | `https://ws.kuru.io` (`/api/generate-token`, `/api/quote`) | `DOCUMENTED` |
| Quote schema | `transaction.calldata` (K2) versus `buildResponse`/`path` (K3) | **`UNKNOWN`** (conflict retained) |
| Intent fields | input token, exact input, output token, minimum received | `SOURCE_INSPECTED` |
| Maximum output / on-chain deadline | absent in the intent | `SOURCE_INSPECTED` |
| Signing transport | Privy `eth_signTransaction` returns broadcast-capable bytes | `DOCUMENTED` |

## 3. Unresolved fields (fill only with recorded authority)

| Field | Current value |
|---|---|
| `to` target identity (documented "router" versus source-inspected entrypoint) | `UNSET` |
| Entrypoint/router method and selector | `UNSET` (a real selector needs Keccak-256) |
| Owner, agent, wallet, signer identities | `UNSET` |
| Separate policy administrator, policy content and hash | `UNSET` |
| Strategy revision, mandate, allowed assets and route | `UNSET` |
| Exact input token and raw amount | `UNSET` |
| Exact output token; minimum received (raw) | `UNSET` |
| Recipient | `UNSET` |
| Fee fields, fee recipients, fee mode | `UNSET` |
| Owner-to-entrypoint allowance: spender, raw, lifetime, revocation | `UNSET` |
| Native gas budget and action/attempt ceiling | `UNSET` |
| Quote freshness, input freshness, local intent expiry, mandate expiry | `UNSET` |
| Finality rule, reconciliation rule | `UNSET` |
| Request ceilings, paid-service ceiling, request-cost ceiling | `UNSET` |
| Opaque `program` bytes and their encoding | `UNSET` |

An unknown required value blocks the affected action; it is not zero.

## 4. Setup actions, each separately bounded

Each row needs its own permission. The single swap permission inherits nothing from these rows and they inherit nothing from it.

| Action | Chain/assets/quantity | Ceiling | Stop condition | Cleanup |
|---|---|---|---|---|
| Owner funds agent wallet | `143`, declared quote asset + native MON for gas, raw `UNSET` | one deposit | wrong network or unsupported asset | none; capital flow only |
| Wrap or unwrap (native MON ↔ WMON) | asset pair `UNSET` | not assumed | only if the selected route needs it | revoke any allowance created |
| Owner → entrypoint allowance | spender = entrypoint, asset = input, raw `UNSET`, lifetime `UNSET` | exact amount, revocable | unsupported token behavior | revoke to `0` |
| Restricted signer attachment | wallet `UNSET`, signer `UNSET`, policy `UNSET` | one attachment | any policy mismatch | owner removal |
| Policy administration | policy `UNSET`, content hash `UNSET`, admin `UNSET` | one policy change | executor key must not administer policy | no weakening of policy |

Unknown setup bounds stay `UNSET`; the affected setup action stays closed.

## 5. The bounded packet (one controlled swap)

| Field | Requirement |
|---|---|
| Economic actions | **1** controlled fixed-input swap |
| Provider quote/build requests | `UNSET` cap, one purpose |
| Signing calls | `UNSET` cap, one purpose |
| Broadcast calls | `UNSET` cap, one purpose |
| Allowed method | the exact approved entrypoint method only |
| Allowed network | the one selected network |
| Candidate binding | prepare the exact unsigned candidate offline; persist its `candidate_hash`, `to`, `value`, `data_hex` and decoded intent before any signing |
| Stop conditions | any unexpected authorization, any mismatch between receipt and the derived identity, any CAPTCHA or consent boundary, any payment requirement |
| Cleanup | discard signed bytes in memory; revoke the owner allowance; retain records |

## 6. Wiring the adapter into the live stage

The offline adapter produces an immutable unsigned candidate. The live stage must, in order: carry the exact unsigned bytes through the accepted P23/P24 queue seam; obtain broadcast-capable signed bytes from the approved signer; compute the local Keccak transaction hash from the signed bytes and persist it **before** broadcast; then broadcast once and bind any returned hash to that local identity. If the queue seam cannot carry full chain bytes, or Keccak is unavailable, the resend path stays unqualified and the action stays blocked. This wiring is not built in this stage.

## 7. Acceptance sequence (freeze the order)

1. One offline permitted action with **no second signature**. Persist decision, input, revision, mandate, reservations, transaction/request references, receipt, decoded effects, actual spending/gas and residual holdings.
2. Receipt plus decoded applicable events and actual asset/accounting deltas.
3. A deterministic local admission denial.
4. An **independent safe provider denial**, isolated from any exhausted local counter.
5. Interruption after possible submission and before completion recording. Recover and reconcile the original action with **no second economic action and no replacement route**. Retain unknown capacity.
6. Owner removal, plus an independent post-removal denial not masked by an exhausted local counter.

## 8. Provider-policy restriction research (deliverable 4)

Official Privy sources read on 2026-10-11 ([policies overview](https://docs.privy.io/controls/policies/overview), [ethereum examples](https://docs.privy.io/controls/policies/example-policies/ethereum), [stateful policies](https://docs.privy.io/controls/policies/stateful-policies)):

- **Condition sources**: `ethereum_transaction` (fields `to`, `value`, `chain_id`), `ethereum_calldata` (decoded against a supplied `abi`; field is `function_name` or `function_name.param_name`), `ethereum_typed_data_*`, `ethereum_7702_authorization`, `reference` (aggregation), plus Solana/Tron/Sui sources.
- **Operators**: `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `in`, `in_condition_set`, and, in the general operator list, `contains`, `starts_with`, `ends_with`. The published SDK interface for `EthereumCalldataCondition` lists only `eq | gt | gte | lt | lte | in | in_condition_set`.
- **Composition**: a rule has an `action` (`ALLOW`/`DENY`), a `method`, and `conditions[]`; all conditions in a rule must pass. A policy holds multiple rules.
- **Case**: EVM addresses and hex byte strings reached through a signing field source compare case-insensitively; other comparisons are exact.

**Finding.** Privy documents decoded-calldata argument matching (`eq`, `in`, bounds) when an ABI is supplied. It documents **no** operator that matches an opaque `bytes` argument for equality. The Flow route `program` is an opaque `bytes` argument. Whether a policy can pin `executeSwap.program`, or reach nested tuple fields such as `executeSwap.intent.amountUserSells`, is `UNKNOWN`. Pinning the decoded intent fields with `eq` is a **proposal** until provider behavior is qualified.

**Consequence.** The mandatory `opaque_program` control stays `UNSUPPORTED` at the independent-policy layer. An outer `to == approved entrypoint` allowlist is necessary but insufficient. Pinning the decoded intent arguments does not constrain the route bytes. A new approver, contract wrapper or changed authority architecture is a material builder decision.

## 9. Genuine next blockers and the release request

1. **Network and route.** Confirm or deny a testnet Flow path, or approve mainnet `143` (builder + Kuru).
2. **Deployed identity and `to`.** Bytecode identity for the entrypoint and router against the pinned source, and which address the quote's `transaction.to` names (read-only lookup under a released packet).
3. **Quote schema.** Freeze the actual response shape (Kuru).
4. **Exact wallet/signer/policy.** Owner, agent wallet, restricted signer, separate policy administrator (builder + P16/P17).
5. **Exact financial values.** Assets, raw amounts, minimum received, fees, gas budget, request/action ceilings, freshness and expiry (builder).
6. **Opaque `program` enforcement.** A demonstrated bound on the opaque route bytes, or a recorded material architecture decision (builder).
7. **Keccak and the byte-carrying seam.** A Keccak-256 dependency and a full-chain-bytes submission seam.

Bounded release request: approve **one** exact live packet with the setup rows and the one controlled swap, on one network, with the ceilings above. No automatic fallback to another route, funded mainnet or weaker policy.
