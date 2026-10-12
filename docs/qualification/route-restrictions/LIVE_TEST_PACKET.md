# Future bounded live-test packet (proposal)

Deliverables 4, 6, 7 and 8. **Proposal only. No live authority.** Prepared 2026-10-10. Source pins are in [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md). The builder owns every consequential live value.

This packet is a request for one exact reviewed release. It grants no signing, funding, faucet, approval, policy, quote or broadcast permission. The builder's standing willingness to deposit mainnet MON, or a deposit itself, does not approve any swap, mandate change, stop change or limit change.

## 1. Network choice

- **First choice:** testnet `10143`, but only if the complete selected Flow path becomes verified. It is `UNKNOWN` today ([NETWORK_DECISION.md](NETWORK_DECISION.md)).
- **Fallback:** mainnet `143`. Requires the builder's separate approval of the exact controlled amount and financial scope.
- No silent switch. The packet records which network was selected and why.

## 2. Filled source-backed fields

| Field | Value | Class |
|---|---|---|
| Selected route | Kuru Flow fixed-input swap | `DOCUMENTED` (K1, R6, R7) |
| Entrypoint (mainnet) | `0xb3e6778480b2E488385E8205eA05E20060B813cb` | `DOCUMENTED` + deployed code (RPC #3) |
| Router (mainnet) | `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` | `DOCUMENTED` + deployed code (RPC #4) |
| Quote host | `https://ws.kuru.io` (`/api/generate-token`, `/api/quote`) | `DOCUMENTED` (K3) |
| Quote schema | `transaction.calldata` (K2) versus `buildResponse`/`path` (K3) | **`UNKNOWN`** (conflict) |
| Intent fields | input token, exact input, output token, minimum received | `SOURCE_INSPECTED` (S1, S2) |
| Maximum output / deadline | absent in the intent | `SOURCE_INSPECTED` (S2) |
| Signing transport | Privy `eth_signTransaction` returns broadcast-capable bytes | `DOCUMENTED` (P2) |
| Deployed bytecode identity | mainnet entrypoint/router vs pinned source | **`UNKNOWN`** |

## 3. Unresolved fields (must be filled before submission)

Leave these unset. Do not invent them.

| Field | Current value |
|---|---|
| Network | `UNSET` |
| Owner identity | `UNSET` |
| Agent identity | `UNSET` |
| Wallet identity and address | `UNSET` |
| Restricted signer identity | `UNSET` |
| Policy administrator (separate from executor) | `UNSET` |
| Policy content and hash | `UNSET` |
| Strategy revision and mandate | `UNSET` |
| Allowed assets and allowed route | `UNSET` |
| Exact input token and raw amount | `UNSET` |
| Exact output token | `UNSET` |
| Minimum received (raw) | `UNSET` |
| Recipient | `UNSET` |
| Fee fields and fee recipients | `UNSET` |
| Exact gas budget and action/attempt ceiling | `UNSET` |
| Quote freshness, input freshness, local intent expiry | `UNSET` |
| Finality rule and reconciliation rule | `UNSET` |
| Request ceilings, paid-service ceiling, request cost ceiling | `UNSET` |

## 4. Setup actions, each separately bounded

Each row needs its own permission. The single swap permission inherits nothing from these rows and they inherit nothing from it.

| Action | Chain/assets/quantity | Ceiling | Stop condition | Cleanup |
|---|---|---|---|---|
| Faucet claim (testnet only) | `10143`, testnet MON, exact amount `UNSET` | one claim | any CAPTCHA or consent boundary | none; do not reuse a claim route |
| Owner funds agent wallet | network, asset `UNSET` (declared quote asset + native MON for gas), raw amount `UNSET` | one deposit, exact raw `UNSET` | wrong network or unsupported asset | none; capital flow only |
| Wrap or unwrap (native MON ↔ WMON) | asset pair `UNQUALIFIED` | not assumed | only if the selected route needs it | revoke any allowance created |
| Owner → entrypoint allowance | spender = entrypoint, asset = input token, raw `UNSET`, lifetime `UNSET` | exact amount, revocable | unsupported token behavior | revoke to `0` |
| Restricted signer attachment | wallet `UNSET`, signer `UNSET`, policy `UNSET` | one attachment | any policy mismatch | owner removal |
| Policy administration | policy `UNSET`, content hash `UNSET`, admin `UNSET` | one policy change | executor key must not administer policy | no weakening of policy |

Rules: preserve the one-controlled-swap ceiling. Unknown setup bounds stay `UNSET` and the setup action stays closed.

## 5. The bounded packet (one controlled swap)

| Field | Requirement |
|---|---|
| Economic actions | **1** controlled fixed-input swap |
| Provider quote/build requests | `UNSET` cap, one purpose |
| Signing calls | `UNSET` cap, one purpose |
| Broadcast calls | `UNSET` cap, one purpose |
| Allowed method | the exact approved entrypoint method only |
| Allowed network | the one selected network |
| Stop conditions | any unexpected authorization, any mismatch between receipt and derived identity, any CAPTCHA or consent boundary, any payment requirement |
| Cleanup | discard signed bytes in memory; revoke the owner allowance; retain records |

## 6. Acceptance sequence

Freeze this order. Do not reorder.

1. One offline permitted action with **no second signature**. Persist decision, input, revision, mandate, intent, reservations, transaction/request references, receipt, decoded effects, actual spending/gas and residual holdings.
2. Receipt plus decoded applicable events and actual asset/accounting deltas.
3. A deterministic local admission denial.
4. An **independent safe provider denial**, isolated from any exhausted local counter. Do not let a local exhausted counter mask the provider result.
5. Interruption after possible submission and before completion recording. Recover and reconcile the original action with **no second economic action and no replacement route**. Retain unknown capacity.
6. Owner removal, plus an independent post-removal denial not masked by an exhausted local counter.

## 7. Reuse and dependency coordination

- **Reuse P16 without repeating consumed actions.** P16 proves a one-owner, two-wallet, testnet `10143` sign-only baseline and A signer removal ([R2](../../qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md)). Reuse only the unchanged wallet/signer/removal controls. Do not repeat the six sign-only calls, the attachment or the removal.
- **P16 does not transfer to the Flow action.** P16 ran on testnet `10143`. The only documented Flow path is mainnet `143`.
- **Dependency stages.** The sequence in the [P20 Probe B plan](../../qualification/kuru-flow/INTEGRATED_PROBE_B_PLAN.md) names P22 (local admission), P23 (durable intent and exclusive claim), P24 (recovery), P25 (stop) and P26/P30 (consent/removal preparation). This packet **references** them. It does not claim their implementation exists.

## 8. Genuine next blockers and the bounded release request

Next blockers, each with its owner:

1. **Network and route.** Confirm or deny a testnet Flow path, or approve mainnet `143` (builder + Kuru).
2. **Exact deployment identity.** Bytecode identity for the entrypoint and router against the pinned source (a read-only public lookup under a released packet).
3. **Quote/build schema.** Freeze the actual response shape before implementation (Kuru).
4. **Exact wallet/signer/policy.** Owner, agent wallet, restricted signer and separate policy administrator (builder + P16/P17).
5. **Exact financial values.** Assets, raw amounts, minimum received, fees, gas budget, request/action ceilings, freshness and expiry (builder).
6. **Opaque `program` enforcement.** A demonstrated bound on the opaque route bytes, or a recorded material architecture decision (builder).

Bounded release request: approve **one** exact live packet with the six setup rows and the one controlled swap, on one network, with the ceilings above. Once approved, ordinary in-scope tests need no repeated permission. Authority, capacity or anti-abuse failures escalate with evidence. No automatic fallback to another route, funded mainnet or weaker policy.

## 9. Independent policy binding (added 2026-10-12)

This section extends the packet. Sections 1 to 8 stay intact. The feasibility check is in [PRIVY_POLICY_BINDING_FEASIBILITY.md](PRIVY_POLICY_BINDING_FEASIBILITY.md). It grants no provider or policy authority.

### 9.1 Exact proposed method and configuration

| Field | Proposed value | Class |
|---|---|---|
| Provider policy method | a Privy policy rule on `eth_signTransaction` | `DOCUMENTED` (P1, P3) |
| Chain condition | `ethereum_transaction.chain_id` `eq` the selected chain id | `DOCUMENTED` (P3) |
| Entrypoint condition | `ethereum_transaction.to` `eq` the selected entrypoint | `DOCUMENTED` (P3) |
| Function condition | `ethereum_calldata.function_name` `eq` `executeSwap` or `executeSwapWithReceiver`, with the pinned ABI | `DOCUMENTED` (P3, P4) |
| Argument conditions | `ethereum_calldata` `eq` on the intent, fee and `program` arguments | **`UNKNOWN`** (no `bytes` or tuple-component example) |
| Policy owner | the user; the application key is an additional signer only | design requirement (P7, R2) |
| Executor key | an additional signer with a restrictive override policy | design requirement (P7) |

### 9.2 Positive control

One offline permitted preparation with **no second signature**, then one provider-signed positive control the policy must allow. Persist the decision, input, mandate, intent, reservations and provider references. Reuse the preserved acceptance sequence in section 6.

### 9.3 Independent denial evidence

A dedicated, isolated request the provider must deny, separate from any exhausted local counter. Candidate denials: changed `program` bytes, changed input or output asset, changed amount, changed minimum output, changed recipient, changed fee, changed chain, changed entrypoint and changed function. A malformed encoding, a local denial or an insufficient-funds simulation is **not** policy-denial evidence.

### 9.4 Authority separation

The application authorization key must not be a member of the wallet-owning key quorum. If it is, that key can unilaterally update the wallet policy and signers (P7). Prove the executor cannot loosen the policy before any real action. Missing ownership evidence keeps the action closed.

### 9.5 Finite request, gas and action limits

The exact request cap, provider-request cap, gas budget and action/attempt ceiling stay `UNSET` (sections 3 and 5). An unknown limit is not zero and does not release the action. The local parse and simulation bounds are finite: `MAX_RULES`, `MAX_CONDITIONS_PER_RULE` and `MAX_CONDITION_VALUE_ITEMS`.

### 9.6 Stop conditions

- Any unexpected authorization of an ostensibly denied request: halt, retain the breach and residual exposure, stop new work.
- Any policy mismatch or provider refusal: stop the affected capability and do not weaken the policy.
- Any CAPTCHA, consent or payment boundary: stop.

### 9.7 Unresolved fields

- Exact `program` byte equality at the provider: `UNKNOWN`.
- Tuple-component calldata path support: `UNKNOWN`.
- Deployed mainnet bytecode identity: `UNKNOWN`.
- Policy administration separation proof: `NOT_RUN`.
