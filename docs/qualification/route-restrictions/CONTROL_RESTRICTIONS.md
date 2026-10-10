# Mandatory controlled-action restrictions

This file defines the restrictions a controlled Kuru Flow fixed-input action must satisfy before any real submission. Each control maps to an enforcing layer and to its current evidence class. A control that is missing, `UNKNOWN` or `UNSUPPORTED` keeps the affected real action unavailable. Prepared 2026-10-10.

The machine form of these rules is `restriction_checker.py`. The reason codes below match its constants.

## Enforcement layers

| Layer | Responsibility | Not responsible for |
|---|---|---|
| `HOST` | The Edge OS host derives identity, binds the action to owner/agent/wallet/network/strategy/mandate, and checks expiry and freshness before send. | Independent wallet enforcement. The host check is application accounting. |
| `CONTRACT` | The on-chain entrypoint enforces its own arguments: input token, exact input amount, minimum received after fees, fee bound, recipient method and approval handling. | The opaque route `program` content, the token notional beyond the declared intent, or Edge OS position inventory. |
| `INDEPENDENT_POLICY` | The wallet-provider policy independently restricts the exact network, contract, method and ABI-decoded arguments. | The Edge OS position ledger. The reviewed sources do not show that a policy reads position inventory. |

A fake policy simulator cannot prove an independent provider restriction. An application check cannot be described as independent wallet enforcement.

## Mandatory-control matrix

| # | Control | Required restriction | Enforcing layer | Evidence class | Current state |
|---|---|---|---|---|---|
| 1 | `chain` | Exactly Monad mainnet `143` or testnet `10143`; one network per approval. | `HOST` + `INDEPENDENT_POLICY` (`chain_id`) | `DOCUMENTED` / `SOURCE_INSPECTED` | Declarable; no live call run. |
| 2 | `wallet_signer_binding` | Bind the action to the exact agent wallet and its restricted signer policy. | `HOST` + `INDEPENDENT_POLICY` | `SOURCE_INSPECTED` (P16 testnet sign-only) | `LOCAL_TESTED` only; cross-user isolation `NOT_RUN`. |
| 3 | `entrypoint_method` | Allow only the exact Flow entrypoint **and** method (`executeSwap` or `executeSwapWithReceiver`). The action must name an approved entrypoint. | `INDEPENDENT_POLICY` (`to`, decoded `function_name`) | `DOCUMENTED` (P1) | Declarable; deployed ABI equivalence `UNKNOWN`. |
| 4 | `input_output_assets` | Limit the input and output tokens to the adopted assets. | `INDEPENDENT_POLICY` (decoded calldata) + `CONTRACT` (intent tokens) | `DOCUMENTED` / `SOURCE_INSPECTED` | Declarable; testnet Flow assets unverified. |
| 5 | `raw_input` | Exact non-negative base-10 base-unit input; no float, Boolean, negative or leading zero. | `CONTRACT` (`amountUserSells`) + `HOST` | `SOURCE_INSPECTED` | Enforced offline. |
| 6 | `recipient` | Only the agent wallet (`msg.sender`) or an allowed explicit receiver. | `CONTRACT` | `SOURCE_INSPECTED` | Enforced offline. |
| 7 | `minimum_output` | A real minimum received, in raw units, at or below the quote; never derived from the estimate. An unknown quote blocks the action. | `CONTRACT` (post-fee check) + `HOST` | `SOURCE_INSPECTED` | Enforced offline. |
| 8 | `fees` | `feeBps + referrerFeeBps <= 10000`; fee recipients within the adopted set. | `CONTRACT` | `SOURCE_INSPECTED` | Fee recipient/payout live behavior `NOT_RUN`. |
| 9 | `approvals` | The owner allowance to the entrypoint is bounded and revoked; no lasting allowance remains. | `CONTRACT` (entrypoint resets its own router approval) + `HOST` | `SOURCE_INSPECTED` | Owner-to-entrypoint allowance lifetime/revocation `UNQUALIFIED`. |
| 10 | `gas_action_capacity` | A known native gas budget, a known action/attempt budget and no over-cap actual. | `HOST` (reservations) + `CONTRACT` (gas limit) | `SOURCE_INSPECTED` | Exact budget `UNSET`; unknown is not zero. |
| 11 | `expiry_freshness` | Bounded quote age, input age and local intent expiry. | `HOST` | `DOCUMENTED` | The Flow intent has no on-chain deadline; local expiry cannot revoke a broadcast. |
| 12 | `opaque_program` | Constrain the opaque route `program` bytes to the approved route. | `INDEPENDENT_POLICY` (unproven) + `CONTRACT` (forwards opaquely) | `NOT_RUN` | **`UNKNOWN`.** No source shows a policy bound on opaque `bytes`. The entrypoint forwards `program` unchanged. |

## Consequences for the real action

- Row 12 is the limiting control. Because no reviewed source proves a bound on the opaque `program`, the real action stays `UNSUPPORTED` at the `INDEPENDENT_POLICY` layer. An outer `to == entrypoint` allowlist is necessary but insufficient.
- Row 10's exact budget is `UNSET`. An unknown gas or action capacity is not zero and does not release the affected action.
- Row 1 documents mainnet `143` as the only route with a documented Flow path. Testnet `10143` Flow support stays `UNKNOWN`.

`restriction_checker.py` maps these to these offline reason codes:

| Code | Trigger |
|---|---|
| `MISSING_MANDATORY_CONTROL:<name>` | The profile omits a mandatory control. |
| `UNSUPPORTED_CONTROL:<name>` | The profile marks a control `UNSUPPORTED`, `UNKNOWN` or `UNSET`. |
| `EVIDENCE_MISSING:<name>` | The profile marks a control `ENFORCED` but its evidence is `NOT_RUN`. |
| `NETWORK_NOT_ALLOWED` | Network outside the supported set or the approval. |
| `WALLET_BINDING_MISSING` / `WALLET_BINDING_MISMATCH` | Missing signer or a policy binding to another wallet. |
| `ENTRYPOINT_NOT_ALLOWED` | Entrypoint outside the approval. |
| `METHOD_NOT_ALLOWED` | Method outside the approval. |
| `ASSET_NOT_ALLOWED` / `DECIMALS_MISMATCH` | Input or output asset, or decimals, outside the approval. |
| `RAW_AMOUNT_INVALID` / `BOOLEAN_NOT_INTEGER` | Non-canonical, missing or Boolean raw amount or quote. |
| `RECIPIENT_NOT_ALLOWED` | Recipient outside the approval. |
| `MIN_OUTPUT_MISSING` / `MIN_OUTPUT_INVALID` | No minimum, or a minimum above the quote. |
| `QUOTE_UNKNOWN` | The quote output is unknown, so the minimum-output bound cannot be checked. |
| `FEE_BOUND_EXCEEDED` | `feeBps + referrerFeeBps > 10000`. |
| `PROGRAM_MISSING` | Empty or non-hex route program. |
| `CAPACITY_UNKNOWN` / `CAPACITY_EXHAUSTED` | Unknown gas/action capacity, or gas/action over the approved bound. |
| `FRESHNESS_UNKNOWN` / `STALE_INPUT` | Unknown quote age or maximum, or an age above the approved maximum. |
| `EVIDENCE_UNMATCHED` | A local case claims a non-local result class. |

The loader rejects a malformed declaration with a field-specific `ValueError`: a non-integer or negative fee, capacity or age; a non-string identifier or allow-list item; and a non-integer asset decimal. It never coerces these values.

## Position-inventory restriction (separate)

Position-inventory-based sell permission is a further mandatory restriction for entry and addition admission. The reviewed sources do not show that a wallet policy reads the Edge OS position ledger. That restriction therefore stays `UNSUPPORTED` at the `INDEPENDENT_POLICY` layer and `LOCAL_TESTED` at the `HOST` layer. The capacity arithmetic is in [WORKED_CAPACITY.md](WORKED_CAPACITY.md).
