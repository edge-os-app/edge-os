# Probe B live-packet configuration fields

The complete proposed field checklist for the separate live-packet approval. Unknown fields are `UNSET` or `UNQUALIFIED`. Do not invent financial defaults. Prepared 2026-10-10.

Source basis is in [SOURCE_EVIDENCE.md](SOURCE_EVIDENCE.md). This document selects no live value.

## 1. Amount and unit mapping (acceptance item 2)

| Field | Meaning | Source basis | Current value |
|---|---|---|---|
| `tokenUserSells` | Input token; `address(0)` means native MON | source-inspected entrypoint | `UNSET` |
| `amountUserSells` | Exact fixed input in raw base units | source-inspected entrypoint | `UNSET` |
| Input decimals | Display precision of the raw input | P15 amount rule | `UNSET` |
| `tokenUserBuys` | Output token | source-inspected entrypoint | `UNSET` |
| `minAmountUserBuys` | Minimum received output, in raw base units | source-inspected entrypoint | `UNSET` |
| Output decimals | Display precision of the raw output | P15 amount rule | `UNSET` |
| Maximum output / acquisition upper bound | Required when a fixed token-quantity sell ceiling is adopted | design EXIT-CAP-Q01 | `ABSENT` in the intent |
| Native `msg.value` | Must cover `amountUserSells` when the input is native | source-inspected entrypoint | `UNSET` |
| ERC-20 versus native notional | Native value is not the ERC-20 notional | design "Exact Monad operation" | `UNSET` |
| Owner wallet → entrypoint allowance | The owner must allow the `KuruFlowEntrypoint` as spender of the input token; `_transferTokensFromUser` calls `safeTransferFrom(token, msg.sender, entrypoint, amountUserSells)` | source-inspected entrypoint | `UNSET`; spender/amount/lifetime/revocation all unqualified |
| Entrypoint → router approval | The entrypoint approves the router for the input, then resets that approval to `0` | source-inspected entrypoint | source-inspected; **distinct** from the owner allowance above |
| Recipient | `msg.sender` or an explicit `receiver` | source-inspected entrypoint | `UNSET` |
| Route `program` bytes | Opaque bytes forwarded to the router | source-inspected entrypoint | `UNSET`; encoding undocumented |
| Fee fields | `feeBps`, `referrerFeeBps`, `feeCollectorAddress`, `referrerAddress`, `isInTokenFee` | documented + source-inspected | `UNSET` |
| Fee total bound | `feeBps + referrerFeeBps <= 10000` | source-inspected entrypoint | enforceable bound only |
| Gas | Native gas budget and actual gas, separate from trading assets | P15 / design | `UNSET` |
| Residual holdings | Unsold or partially routed assets | design | **requires live proof** |

Rules to preserve:

- Keep raw units and decimals. Never sum raw amounts of different assets.
- Native MON gas stays separate from WMON and other trading assets.
- A **quote estimate** is not an **enforceable bound**. `output` from the quote API is an estimate. `minAmountUserBuys` is the enforced minimum.
- A **local expiry** is not an **on-chain deadline**. The Flow intent has no time field. Local intent/mandate expiry cannot revoke a broadcast transaction.
- The owner's allowance to the entrypoint and the entrypoint's allowance to the router are **different relationships**. The entrypoint resets only its own router approval to `0`; it does not reset the owner's allowance to the entrypoint. Both need their own limit and, where applicable, revocation.

## 2. Identity, authority and isolation

| Field | Requirement | Current value |
|---|---|---|
| Network | Monad `143` or `10143`, chosen explicitly | `UNSET`; only `143` has a documented Flow path |
| Deployment | Exact entrypoint/router address plus bytecode identity | Mainnet addresses documented; **deployed bytecode identity `UNKNOWN`** |
| ABI / version | Exact entrypoint and router ABI version | Pinned public source `70bc0c93`; deployed equivalence `UNKNOWN` |
| Owner | Verified owner identity | `UNSET` |
| Agent | Agent identity bound to the wallet | `UNSET` |
| Wallet | One user-owned wallet per agent | `UNSET` |
| Signer | Restricted additional signer | `UNSET` |
| Policy administrator | Separate from the executor | `UNSET` |
| Policy content | Exact allow/deny rules and content hash | `UNSET` |
| Strategy revision | Immutable revision bound to the mandate | `UNSET` |
| Mandate | Finite allocation, actions, expiry, stop effects | `UNSET` |
| Assets and routes | Allowed assets and the allowed route | `UNSET` |

## 3. Freshness, finality and expiry

| Field | Requirement | Current value |
|---|---|---|
| Quote freshness | Maximum age of the quote before send | `UNSET` |
| Input freshness | Maximum age of the decision input | `UNSET` |
| Local intent expiry | Edge OS local expiry | `UNSET` |
| Mandate expiry | Approval expiry | `UNSET` |
| On-chain swap deadline | Actual contract deadline, if any | `NOT PRESENT` in the Flow intent |
| Finality rule | Confirmation depth or finality rule | `UNSET` |
| Reconciliation rule | How an unknown outcome is resolved | `UNSET` |

## 4. Ceilings (all `UNSET`)

- Per-request provider-request cap.
- Per-request build/quote cap.
- Cumulative provider-request cap.
- Economic-action ceiling (one controlled action).
- Buy input allowance in the quote asset.
- Sell allowance in the base asset.
- Native gas budget and actual gas.
- Exposure limit and loss limit.
- Request cost ceiling and paid-service ceiling.

## 5. Denial, recovery and removal observations

| Observation | Required result | Current value |
|---|---|---|
| Deterministic local admission denial | Deny before any provider call or broadcast | `UNSET` plan |
| Independent provider denial | Provider denies without a weakened policy | `UNSET` plan |
| Interrupted original-action recovery | Reconcile without a duplicate | `UNSET` plan |
| Owner removal | Verified removal with owner access retained | `UNSET` plan |
| Post-removal independent denial | Denied, not masked by an exhausted local counter | `UNSET` plan |
| Success criteria | Confirmed receipt, decoded effects, actual deltas | `UNSET` |
| Failure criteria | Explicit fail-closed conditions | `UNSET` |

## 6. Setup actions and separate approval scope

Preparation acceptance item 7 requires every funding, wrap, approval, signer and policy setup action, with its own bounds. Permission for the one controlled swap does not grant permission for any setup, exit, transfer, replacement or cleanup action. Each action needs its own scope.

| Setup action | Fields to freeze | Separate approval scope | Current value |
|---|---|---|---|
| Owner funding of the agent wallet | network, asset, raw amount, decimals, fees, recipient, transaction reference | one funding approval; not part of the swap permission | `UNSET` |
| Wrap or unwrap (for example native MON and WMON) | asset pair, raw amount, mechanism, fees | only if the selected route needs it; not assumed | `UNQUALIFIED` |
| Wallet → entrypoint token allowance | spender (the entrypoint), asset, raw amount, lifetime or revocation | its own approval, distinct from the swap | `UNSET` |
| Restricted signer attachment | wallet, signer identity, policy binding, consent | its own owner-approved action | `UNSET` |
| Policy administration | policy identity, content, version, administrator | separate from the executor credential | `UNSET` |

Rules:

- Preserve the **one-controlled-swap** ceiling. List every auxiliary action separately and bound it. No setup, follow-up or cleanup inherits the swap permission.
- State acquired and residual holdings and any separately permitted follow-up.
- Unknown setup bounds stay `UNSET`; the affected setup action stays closed.

## 7. Transport, transaction identity and durable claim

| Field | Requirement | Current value |
|---|---|---|
| Quote/build service | Exact endpoint and method for the selected route | `UNSET` |
| Quote authentication | JWT (`Bearer`) or `X-API-Key` | `UNSET`; documented options only |
| Signing transport | Exact service, endpoint and method (for example Privy `eth_signTransaction`) | `UNSET` |
| Broadcast transport | Exact service, endpoint and method, if separate from signing | `UNSET`; whether signing and broadcast are separate is `UNKNOWN` |
| Transaction identity and nonce | Exact serialized transaction fields plus nonce source | `UNSET` |
| Locally derived transaction hash | Keccak of the encoded signed transaction, before broadcast | method documented; value `UNSET` |
| Provider request reference | Exact provider request identity | `UNSET` |
| Idempotency reference | `privy-idempotency-key` value and its 24-hour scope | `UNSET` |
| Fee and gas fields | Exact fee fields, fee recipients, gas limit, fee fields, price guards | `UNSET` |
| Durable storage | Where original signed bytes, derived hash, intent and reservations persist | `UNSET` |
| Exclusive claim | One exclusive wallet/network claim before the external effect | `UNSET` |

The selected transport, endpoints, methods and durable references must be frozen **before** the applicable external effect. No paid or authenticated call inherits approval from planning.

## 8. Negative-control isolation and containment

| Item | Required behavior | Current value |
|---|---|---|
| Safe denial request | A dedicated, isolated request that the provider must deny | `UNSET` plan |
| Removal request | The owner removal request, isolated from the denial | `UNSET` plan |
| Isolation from local counters | Do not let an exhausted local counter mask the provider result | `UNSET` plan |
| Unexpected authorization containment | If an ostensibly denied request is unexpectedly authorized, halt the affected capability, retain the breach and residual exposure, and stop new work | `UNSET` plan |
| Stop behavior | Scoped stop that denies new work and retains pending work and monitoring | `UNSET` plan |

If a negative control is unexpectedly authorized, do not treat it as a pass. Record the breach and containment. Preparation runs no provider test.

## 9. Unsupported and unknown markers

- Testnet `10143` Flow support: **UNKNOWN / not documented**.
- Opaque `program` enforcement by the policy: **requires live proof**.
- Position-inventory enforcement: **requires live proof**.
- `buildResponse` schema and transport: **UNKNOWN**.
- Deployed mainnet bytecode identity: **UNKNOWN**.

Any field left `UNSET` or `UNQUALIFIED` blocks the affected capability. The builder selects the consequential live configuration.
