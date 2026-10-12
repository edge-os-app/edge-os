# Independent-enforcement qualification packet (NOT_RUN proposal)

Task `POLICY-PREP-L3-20261012-01` v1, P21/P20/#58. Prepared 2026-10-12.

**Status: `NOT_RUN`.** This is a proposal for one exact, separately approved release. It grants no provider, wallet, signing, funding, policy or broadcast authority. The builder owns every consequential value. A local `AUTHORED_POLICY_ALLOW` never satisfies any step here.

This packet extends the accepted [`../route-restrictions/LIVE_TEST_PACKET.md`](../route-restrictions/LIVE_TEST_PACKET.md) section 9. It reuses the accepted acceptance sequence and stays consistent with it.

## 1. Network order

1. **First choice: a verified complete testnet `10143` Flow path.** It is `UNKNOWN` today. Use it only if a source-backed testnet Flow entrypoint/router and a testnet quote/build response exist.
2. **Fallback: mainnet `143`.** The only documented Flow path. It needs the builder's separate approval of the exact controlled amount and financial scope.
3. **No silent switch.** A network change is a recorded decision.

## 2. Required authority (each separately bounded)

| Authority | Holder | What it permits | Not granted here |
|---|---|---|---|
| Provider policy create/update | Privy policy-resource owner (outside executor control) | Attach the approved policy and update it | No policy change is requested |
| Wallet owner | Wallet owner key quorum | Attach an additional signer; remove it | No attachment or removal is requested |
| Executor credential | Edge OS execution service | Submit a bounded request under the policy | No submission is requested |
| Funding | Builder | Fund the agent wallet | No deposit is requested |
| Broadcast | The selected transport | Submit the controlled action | No broadcast is requested |

The application authorization key must not be a satisfying member of the wallet-owning key quorum, and the policy must have an explicit owner outside executor control. Missing ownership evidence keeps the action closed.

## 3. Identity placeholders (no identifier is selected here)

| Identity | Placeholder | Status |
|---|---|---|
| Network | `NETWORK_ID` (`monad:143` or `monad-testnet:10143`) | `REQUIRED_DECISION` |
| Entrypoint | `ENTRYPOINT_ADDRESS` (mainnet `0xb3e6778480b2E488385E8205eA05E20060B813cb` when mainnet) | `REQUIRED_DECISION` |
| Router | `ROUTER_ADDRESS` (mainnet `0x0d3a1BE29E9dEd63c7a5678b31e847D68F71FFa2` when mainnet) | `REQUIRED_DECISION` |
| Method | `METHOD` (`executeSwap` or `executeSwapWithReceiver`) | `REQUIRED_DECISION` |
| Pinned ABI | the Flow ABI at commit `70bc0c93c073f78697b99848eedefbf5dbe698c7` | `DOCUMENTED` |
| Selector | `SELECTOR` (real selector needs Ethereum Keccak-256, unavailable here) | `REQUIRED_DECISION` |
| Policy content | `POLICY_CONTENT_HASH` | `REQUIRED_DECISION` |
| Policy owner | `POLICY_OWNER_ID` | `REQUIRED_DECISION` |
| Wallet | `WALLET_ID` / `WALLET_ADDRESS` | `REQUIRED_DECISION` |
| Executor signer | `EXECUTOR_SIGNER_ID` + `EXECUTOR_OVERRIDE_POLICY_ID` | `REQUIRED_DECISION` |
| Flow profile | accepted `truthful_route_profile` `truthful-2026-10-10` | `SOURCE_INSPECTED` |
| Input asset + raw | `INPUT_ASSET_ID`, `INPUT_RAW` | `REQUIRED_DECISION` |
| Output asset | `OUTPUT_ASSET_ID` | `REQUIRED_DECISION` |
| Minimum received (raw) | `MIN_OUTPUT_RAW` | `REQUIRED_DECISION` |
| Recipient | `RECIPIENT` (the agent wallet, or an allowed explicit receiver) | `REQUIRED_DECISION` |
| Fee fields | `FEE_BPS`, `REFERRER_FEE_BPS`, `FEE_COLLECTOR`, `REFERRER`, `IS_IN_TOKEN_FEE` | `REQUIRED_DECISION` |
| Route bytes | `PROGRAM_HEX` | `REQUIRED_DECISION` |

## 4. Ownership, holdings and qualified inputs

- **Ownership.** Confirm policy ownership and wallet ownership per [ADMINISTRATION_IDENTITY.md](ADMINISTRATION_IDENTITY.md). Both separations are required.
- **Current holdings.** Record the agent wallet's current input-token balance, output-token balance and native gas balance, in raw units, before the action. Different asset IDs are never summed.
- **Qualified inputs.** The quote/build response must be a frozen, source-backed response with a single schema variant; the accepted adapter must accept it offline first. The deployed `143` bytecode identity for the entrypoint and router stays `UNKNOWN` until a read-only public lookup confirms it.

## 5. Ceilings (all `REQUIRED_DECISION`)

| Ceiling | Current value | Rule |
|---|---|---|
| Provider quote/build requests | `UNSET` | one purpose, finite cap |
| Signing calls | `UNSET` | one purpose, finite cap |
| Broadcast calls | `UNSET` | one purpose, finite cap |
| Economic actions | `1` controlled fixed-input swap | preserve the single-action ceiling |
| Request bytes | `UNSET` | finite cap |
| Raw input amount | `UNSET` | exact approved input |
| Gas budget (native) | `UNSET` | exact budget; unknown is not zero |
| Request cost / paid-service | `UNSET` | no paid service by implication |
| Residual exposure | `UNSET` | retained and reconciled; never treated as zero |

An unknown limit is not zero and does not release the action.

## 6. Exact action order (freeze, do not reorder)

1. One offline permitted preparation with **no signature**: persist decision, input, revision, mandate, intent, reservations, transaction/request references. The accepted adapter's candidate identity anchors the original action.
2. Attach the approved policy to the agent wallet and the executor as an additional signer with the restrictive override policy. Confirm content hash equals `POLICY_CONTENT_HASH`.
3. One provider-signed **positive control** the policy must allow.
4. One isolated **independent denial** per [WORKED_CASES.md](WORKED_CASES.md), separate from any exhausted local counter.
5. One **controlled action**: sign and broadcast one swap; capture receipt, decoded events and asset/accounting deltas.
6. Interruption after possible submission, before completion recording: recover and reconcile the original action with **no second economic action and no replacement route**. Retain unknown capacity.
7. Owner removal: remove the executor signer; record an independent post-removal denial not masked by an exhausted local counter.
8. Record residual holdings and any resting exposure with its separate cancellation path.

## 7. Unknown liability, stop, recovery and revocation evidence

- **Unknown liability.** A lost acknowledgement is `SUBMISSION_UNKNOWN`, not zero spend. Retain the signed-reference identity and every reservation.
- **Stop conditions.** Any unexpected authorization of an ostensibly denied request: halt, retain the breach and residual exposure, stop new work. Any policy mismatch or provider refusal: stop the capability and do not weaken the policy. Any CAPTCHA, consent or payment boundary: stop.
- **Recovery.** Reconcile the original action; no duplicate and no replacement route. Keep one continuation mechanism per session.
- **Revocation.** Signer removal blocks future signing; it cannot reverse a broadcast or cancel a resting venue order. Record remaining exposure and the separate authority needed to cancel it.
- **Simulation is not denial evidence.** A simulation failure suppresses policy evaluation and is not a policy violation.

## 8. Resource cleanup

- Discard signed bytes from memory.
- Revoke the owner-to-entrypoint allowance to `0`.
- Remove the executor signer (owner action).
- Retain records, receipts and residual-exposure notes.
- Do not reuse a faucet or claim route.

## 9. Acceptance criteria

1. Both original reviewers PASS the committed candidate.
2. The independent gate confirms source support, vector calculations and the applicability of the existing offline checks.
3. A released, separately approved packet exists for each bounded action.
4. The policy content hash matches the approved version at every step.
5. The positive control is allowed and every independent denial is observed.
6. Recovery preserves the original action with no duplicate.
7. Residual exposure is recorded and is not zero.

A **boundary-only feasibility PASS** may be accepted while actual enforcement stays `NOT_RUN`. This packet does not claim enforcement.

## 10. Boundary decisions that must not be bypassed

- No new provider, network or wallet is chosen to bypass a limitation.
- An independent **inventory** control stays `UNSUPPORTED` unless an actual mechanism is documented and proved. The position ledger is not readable at the independent layer.
- No permissive `ALLOW` fallback is added to make a decode failure pass.
- The opaque `program` and tuple-path controls stay `UNKNOWN` until a provider control proves them, or the builder records a different enforcement design.

## 11. Claim boundary

- This packet is a `NOT_RUN` proposal. It proves no provider, chain, policy, wallet or financial behaviour.
- Numeric values and identifiers remain `REQUIRED_DECISION`.
