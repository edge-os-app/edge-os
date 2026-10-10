# Integrated Probe B plan and acceptance sequence

Prepares the staged application path for Probe B. Source pins are in [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md). Prepared 2026-10-10.

Scope: preparation. No live action. Full P20 issue #19 stays OPEN.

## 1. Integrated sequence

Probe B becomes the application's controlled-execution qualification, not a second throwaway helper ([release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md)). The stages run in this order. Each stage consumes the accepted result of the previous one.

| Order | Stage | Prerequisite | This stage's product |
|---|---|---|---|
| 1 | Stored exact rule and immutable approval | Accepted P06/P15/P19 | Frozen strategy revision plus the immutable approval snapshot and mandate binding |
| 2 | Local P22 admission | Stage 1; P21 profile | Deterministic admission with atomic capital/action/gas/inventory reservations and a denial path |
| 3 | P23 durable intent and exclusive claim | Stage 2 | Saved input/decision lineage before intent; one exclusive wallet/network claim; revalidation at send |
| 4 | P24 original-action recovery | Stage 3 | Reconciliation of the original action after acknowledgement loss; no duplicate economic action |
| 5 | P25 scoped stop | Stage 4 | Scoped stop that denies unsent work and retains pending work and monitoring |
| 6 | Inactive P26 consent preparation and P30 removal preparation | Local P24/P25 portions | Prepared consent review and removal procedure, still inactive |
| 7 | Separately authorized P20 one-action qualification | Stages 1 to 6; exact live packet approval | One controlled fixed-input swap while the owner is offline, plus denial, recovery and removal observations |
| 8 | Final P26/P30 acceptance | Stage 7 result | Final consent and removal qualification that consumes the P20 result |

The dependency direction matters. P20 qualification consumes the **inactive** P26 review/consent preparation and P30 removal preparation. The final P26/P30 acceptance consumes the P20 result. Do not make final P26/P30 acceptance a prerequisite of the live test that produces their evidence.

## 2. Durable acknowledgement-loss reconciliation

The design and P15 require one identity per action through `PROPOSED`, `QUEUED`, `SUBMITTED`, `CONFIRMED`, `REVERTED`, `DENIED`, `CANCELLED`, `SUBMISSION_UNKNOWN`. A timeout is not a failure verdict and never authorizes a duplicate.

Available durable references, as documented or source-inspected:

| Reference | Availability | Limit |
|---|---|---|
| Signed transaction bytes | Privy `eth_signTransaction` returns `signed_transaction` RLP plus `encoding`. The transport is documented. | Treat the bytes as broadcast-capable. Same-action resend needs byte-identical reuse. The actual retrieval and preservation path is **requires live proof**. |
| Locally derived transaction identifier | When the transport returns the serialized signed bytes, the Ethereum transaction hash is computed locally by Keccak of the encoded transaction. It exists **before** broadcast for both legacy and typed encoding, with no network or broadcast dependency. | It identifies the transaction. It is **not** proof of submission or confirmation. Require durable original bytes plus this derived identifier before broadcasting on a sign-then-send route. |
| Provider request identity | Privy `privy-idempotency-key`; on 4xx/5xx Privy caches and replays the response for the same key. Policy violations allow same-key retries. | Replay for the same key is not the same as preserving the original signed bytes. Distinct references. |
| Broadcast acknowledgement | Returned by broadcast. | Reconcile any broadcast-returned hash against the locally derived identifier. A mismatch is a new identity, not the original action. |
| Edge OS intent/reservation records | Application records bound to owner, agent, wallet, network, strategy revision and mandate. | Application records are not provider or chain evidence. |

Rules to preserve:

- **Same-action retrieval or resend** reuses the original signed bytes and its locally derived transaction hash and keeps one economic-action identity. Record each provider request separately.
- **A new economic action** means changed bytes, a changed transaction, a fresh route or a new transaction. It needs its own authority.
- No automatic replacement strategy. No fresh route on an unknown outcome.
- If the transport cannot retrieve the original signed bytes, the derived identifier cannot be reproduced and resend stays **unqualified**.
- `SUBMISSION_UNKNOWN` retains the original references and all reservations until reconciliation.
- Preserve the original serialized signed bytes and the locally derived hash **before** broadcasting. The broadcast-returned acknowledgement is a separate reference; reconcile it against the derived identity. This resolves the acknowledgement-loss boundary: an unknown outcome has a durable identity even when no broadcast response was observed.

## 3. P16 reuse map

P16 proves a narrow one-owner, two-wallet sign-only scope on Monad testnet `10143` ([provider signing result](../../qualification/p16/PROVIDER_SIGNING_RESULT_2026-10-08.md)). Reuse is allowed only for the unchanged tested controls.

| Control | P16 status | Reusable for P20 unchanged? | Gap |
|---|---|---|---|
| One verified owner with separate user-owned agent wallets | PASS (sign-only, testnet `10143`) | Yes, for the same one-owner shape | Cross-user application authorization is `NOT RUN`. |
| Per-wallet signer isolation (A's signer refused on B) | PASS (sign-only) | Yes, for the same wallet/policy shape | Does not prove the Kuru action. |
| Signer removal and removed-signer refusal | PASS | Yes, for the removal control | Pending-record recovery and residual exposure were not tested. |
| Independent provider denial | PASS as `CONTROLLED_PROVIDER_REFUSAL` (raw HTTP 401, no code) | Partial | The vendor denial reason is unknown. |
| Policy administration separation from agent signing | `NOT COVERED` / `PARTIAL` | No | Independent separation remains unqualified. |
| Wallet creation and lost-response/restart via React SDK | Partial; existing API recovery only | No | React `createWallet` recovery is not qualified. |
| Kuru execution, mainnet `143`, swaps, broadcast | Not tested | No | Out of P16 scope. |
| Production auth and storage | `NOT RUN` | No | Separate. |

P16 ran on testnet `10143`. The only documented Flow path is mainnet `143`. P16 therefore does **not** transfer to the P20 Flow action directly. Reuse only the owner/wallet/signer-baseline controls and the removal pattern. Run no new signing test for preparation.

## 4. Preserved acceptance sequence

Freeze this order. Do not reorder or collapse it.

1. One offline permitted action with **no second signature**. Persist decision, input, revision, mandate identities, original intent, reservations, transaction/request references, receipt, decoded effects, actual spending/gas and residual holdings.
2. Receipt plus decoded applicable events and actual asset/accounting deltas.
3. A deterministic local admission denial.
4. An independent safe provider denial, isolated from any exhausted local counter.
5. Interruption after possible submission and before completion recording. Recover and reconcile the original action with **no second economic action and no replacement route**. Retain unknown capacity.
6. Owner removal, plus an independent post-removal denial that is not masked by an exhausted local counter.

The ordinary fixture verifier stays non-spending. A live verifier and feature-map step is a **separate explicitly enabled** proposal, not an implemented check in this stage. Full P20 requires the mapped UI/verifier wiring under the P05 lease.

## 5. Circular-dependency avoidance

- Preparation of P20 does not wait for P05 wiring. It needs no shared-file lease.
- P26/P30 final acceptance is downstream of the P20 result, never upstream.
- The live test needs the **inactive** P26/P30 preparation, which this stage can reference without activating it.
- No stage may silently enable general strategy entries or bypass a required restriction.
