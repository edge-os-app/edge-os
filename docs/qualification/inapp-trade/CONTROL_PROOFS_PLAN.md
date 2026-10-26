# Provider-actual proofs for in-app trade controls 4-8 and 10-12

Task `CLOUD-CONTROL-PROOFS`, builder-approved 2026-10-23 ("collect the proofs"). Base
`3a495cd355262b712afbc966ea49932e19dea575` (`integration/edge-os-mvp`). Status: **first live run done
2026-10-23 (controller); two findings fixed in `CLOUD-CONTROL-PROOFS-2`; one Privy row to re-run.** See
"Live run of 2026-10-23: findings and resolution". The cloud sessions used no network, provider, credential or
key. This document grants no trade authority and changes no release hash.

`check_release` admits an ACTUAL release only when all 12 controls are `ENFORCED`, carry evidence class
`PROVIDER_ACTUAL` and have a proof hash. Controls 1-3 and 9 come from the recorded v3 result (controller,
pending step 1 of `INAPP_TRADE_RELEASE.md`). This plan covers the other eight.

## Result in one table

| # | Control | Verdict | Evidence |
| --- | --- | --- | --- |
| 4 | `input_output_assets` | **Builder decision** (input side only; the output token has no provider bound) | Chain simulations + one Privy refusal |
| 5 | `raw_input` | Provable | Chain simulations |
| 6 | `recipient` | **Builder decision** when the trace pays the pinned fee recipients (the live trace does): `FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND`; provable when it pays only the pool | Chain trace + two Privy refusals |
| 7 | `minimum_output` | Provable | Chain simulations |
| 8 | `fees` | **Builder decision** (sum bound only; fee values and recipients have no provider bound) | Chain simulations |
| 10 | `gas_action_capacity` | Provable for the native gas budget | Chain estimates and base fee |
| 11 | `expiry_freshness` | **Builder decision**: `PRIVY_REFUSAL_REASON_NOT_READABLE` for the recorded 401 re-run (2026-10-26); `PROVIDER_COVERS_SIGNING_CUTOFF_ONLY` if a recognized expiry code is ever recorded | One Privy refusal, twice, with the same body + the positive control + the app's own expiry checks |
| 12 | `opaque_program` | **Not provable this way** | See "Control 12" |

"Provable" means: if the controller's live run returns the expected results, the proof builder emits an
artifact and a hash in the `check_release` shape under `controls`. "Builder decision" means: with complete
evidence the builder emits the artifact and its hash under `decision_required`, with a fixed reason, but no
state; putting that hash into the release is a builder decision and a separate reviewed change. Any other
result leaves the control in `unproven` with a fixed reason. The builder never writes a state for a control it
did not prove.

## Live run of 2026-10-23: findings and resolution

The controller ran both stores on 2026-10-23: real Monad mainnet reads through QuickNode, and a sign-only
Privy run. Privy signed nothing but the revoke-to-zero positive control.

### Finding 1: the release swap pays two fee recipients, and the trace check refused them

- Observed: all 27 chain operations matched their expectation. The builder then returned `recipient` =
  `unproven`, `TRACE_TRANSFERS_INVALID`. The net ERC20 movements of `chain.swap_trace` (the release swap of
  10 WMON at minimum output `595679419908705379337` MOE) were:
  - MOE: wallet `+595679419908705379337`, pool `-595679419908705379337`.
  - WMON: wallet `-10000000000000000000`, pool `+9865000000000000000`,
    `0xe1c8b73343f5a83ebe165be90470d84b00e33022` `+100000000000000000` (1.00% of the input),
    `0x681c3f796ae388026634c26025504d7c45248998` `+35000000000000000` (0.35% of the input).
- Cause: the trace check allowed only the pool to gain WMON, so the swap's own fee payouts failed it.
- What the repository can establish: nothing about these two addresses. Neither address, nor a 1.00% or
  0.35% rate, appears anywhere in the repository; no nad.fun pair source or ABI is checked in (the pool is
  described only as a "nad.fun pair" in `docs/qualification/kuru-flow/DIRECT_ROUTE.md`). So the recipients
  cannot be justified from source, only from the observed trace.
- How 1.00% + 0.35% relates to `PROGRAM_FEE_PPM = 16000`: the two payouts total 13500 ppm of the input, below
  the 16000 ppm program fee field. `DIRECT_ROUTE.md` records that 16000 ppm is the lowest value that passed
  the builder's fee search (0 to 10000 ppm reverted with `NadFunPair: K`); the search step is in the
  builder-only `fee_search.py`. One reading fits: the pair pays 1.35% of the input out and then charges an
  LP fee `f` on the 98.65% it keeps; the program fee covers both when `(1 - 0.0135)(1 - f) >= 1 - 0.016`,
  that is `f <= 0.2534%` (a 0.25% LP fee gives an effective 15966 ppm, which a coarse search would round up
  to 16000). This is arithmetic only. Without the pair source or the reserves at the pinned block (they are in
  the controller's chain store, not here), the LP fee, which contract makes the payouts, and whether the rates
  are fixed or configurable cannot be established from the repository.
- Resolution (`chain_proof.OBSERVED_FEE_RECIPIENTS_PPM`, `control_proofs._trace_findings`): the two
  recipients are pinned with bounds of 10000 and 3500 ppm of the input (exactly the observed 0.1 and 0.035
  WMON), with the live trace named as their source. The check still requires the wallet to gain exactly the
  output in MOE and nobody else to gain MOE, and the wallet to pay exactly the input in WMON. A WMON gain is
  accepted only for the pool or a pinned recipient within its bound (net per address, so split payouts sum).
  Any other WMON or MOE gain, or a pinned recipient above its bound, stays `TRACE_TRANSFERS_INVALID`. Every log
  must be readable (a list of mappings whose topics are 32-byte hex words; the Transfer topic is matched
  without regard to case); a `logs` or `calls` field that is not a list, or a log the check cannot read, refuses
  the trace instead of being skipped, so it cannot hide a transfer. Because
  the pins are observed, not justified, a trace that pays them makes `recipient` **decision_required**
  (`FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND`, option A the builder accepted for decision-required
  controls). The artifact lists each observed recipient, amount, ppm bound and raw bound in
  `findings.fee_transfers`, and the pool's WMON gain in `findings.wmon_received_by_pool_raw`. A trace that
  pays only the pool stays `ENFORCED`.
- Smallest way to make it provable: check in the nad.fun pair source or verified ABI that names the fee
  recipients and rates (or a read of them from the pair or factory at the pinned block, added as a frozen
  chain operation), then cite that source next to the pins.
- No chain re-run is needed: rebuild the proofs from the saved chain store (step 4).

### Finding 2: the expiry row got a 401 the runner did not know, and its code was not saved

- Observed: `ctl_allow_revoke_zero` (`ALLOW`, `SIGNED_FIELDS_MATCH`) and the three deny rows (`POLICY_DENY`,
  `PRIVY_POLICY_VIOLATION`) matched. `ctl_deny_expired_request` got HTTP 401 with a 113-byte
  `application/json` body: `UNKNOWN` / `UNRECOGNIZED_REPLY`, and the run stopped as designed. The capture kept
  only the body hash, so the Privy error code is unknown. Privy did not sign.
- Resolution, saved fields (`actual_runner._capture_error_fields`, `actual_profile.error_fields`): for an
  error reply (status 400 or above, JSON, within the 16384-byte bound) the capture now also saves
  `error_code` (read as `reply_code` reads it: `code`, the string `error`, or `error.code`) and `error_type`
  (`type` or `error.type`), next to `status` and `raw_body_sha256`. Each is saved only when it is letter words
  joined by underscores (at most 64 characters, 24 per word); anything else (free text, digits, hex, base64)
  is saved as null. Headers, messages, keys and signed bytes are never saved, and a reply below 400 is never
  parsed for the capture.
- Resolution, recognition (`actual_profile.is_expiry_refusal`): on the expiry row only, a 401 whose saved
  code has an expiry word (`expired`, `expire`, `expires`, `expiry`, `expiration`) and a subject word
  (`request`, `signature`, `signatures`, `authorization`), and no word naming another credential (`token`,
  `jwt`, `session`, `key`, `secret`, `access`, ...) or a malformed or out-of-range expiry (`invalid`,
  `missing`, `too`, `future`, ...), is `UNKNOWN` / `EXPIRY_REFUSAL`, after the positive-control check. A body
  with `data` or `method` is never one. Every other 401 stays `UNKNOWN` / `UNRECOGNIZED_REPLY` and stops the
  run. The documented 400 `request_expired` still matches. A 401 expiry code on any other row stays
  `UNRECOGNIZED_REPLY`.
- Resolution, one-row re-run (`actual_run --rerun-expiry-from`): the expiry row is sent alone, once, into the
  new store `<earlier store>.expiry-rerun`. That path is fixed by the earlier store and `--store` is refused, so
  each earlier store has exactly one re-run: a second attempt finds the store or its claimed row and is refused,
  and a re-run that signed or lost its reply cannot be replaced by a later clean one. The earlier store is only
  read and must show: the expiry row ended `UNKNOWN` /
  `UNRECOGNIZED_REPLY` on a captured 401 (an error status, so nothing was signed); every other row matched;
  no unresolved or breached attempt; and the qualified positive-control `ALLOW`, which the re-run reuses. The
  new intent and outcome carry `rerun_of`: the SHA-256 of the earlier expiry outcome record and of the
  earlier positive-control outcome record. No other row can be re-run this way. The proof builder reads the
  re-run with `--with-expiry-rerun` (from `<privy store>.expiry-rerun`); it refuses a re-run store holding any
  other row, an earlier expiry capture that no longer hashes to its record or does not show 401, and accepts the
  re-run record only when both cited hashes match the earlier store. The artifact's evidence carries `rerun_of`.
- The packet, its hash and the row's request bytes are unchanged, so the re-run sends the same idempotency key
  (`control-proofs-1:raw.ctl_deny_expired_request`). Privy may answer with its stored reply for that key,
  which is the same 401 whose code is now saved. If the saved code is not an expiry code (for example an
  authorization-signature or idempotency error), the row stays `UNRECOGNIZED_REPLY`, the run stops, and the
  saved `error_code` tells the builder why; `expiry_freshness` then stays unproven until a reviewed change.
  If Privy's body carries only a human-readable message (for example `{"error": "Request expired"}`), no code is
  saved (`error_code` null, by the code/type-only rule), the row stays `UNRECOGNIZED_REPLY`, and the builder
  must decide from the status and the raw-body hash; the runner never saves message text.
- The saved code is in the capture, which the proof cites by hash; the builder reads it there, not in the
  `expiry_freshness` findings.

### Re-run of 2026-10-26 and the builder's decision

- Result (controller's record): the builder ran the one-row re-run. Privy answered
  `raw.ctl_deny_expired_request` with HTTP 401, `application/json`, 113 bytes, `raw_body_sha256`
  `76a0174db6daea58159332a34aacd9d9274290b7372b4acb3f3c95066eb95140`, the same body hash as the 2026-10-23
  capture. `error_code` and `error_type` are both null: the body has no code or type field the capture rule
  accepts. The outcome is `UNKNOWN` / `UNRECOGNIZED_REPLY`, `matches_expectation` false, and
  `rerun_of.positive_control_outcome_record_sha256` is
  `581ee1c6cdde61213c2a3bf98072d4a46bb24385c39ea9e4e28bdf96635fc442`. Privy did not sign. The re-run slot is
  spent; no further Privy call will be made. The positive control `ctl_allow_revoke_zero` (same packet, policy
  id, policy hash and agent key) was `ALLOW` / `SIGNED_FIELDS_MATCH`.
- Decision (builder, 2026-10-26, option A, "industry standard"): `expiry_freshness` is **decision_required**
  with reason `PRIVY_REFUSAL_REASON_NOT_READABLE`, not unproven. The proof builder emits it only when all of the
  following hold (`control_proofs._Privy.refused_unreadably`); anything else stays `PRIVY_RECORD_INVALID`, as
  before:
  1. Both expiry attempts, the 2026-10-23 one and its one re-run, are outcome records with exactly the runner's
     error-reply keys, so neither holds `signed_bytes_sha256` or `signed_field_reasons`. Each is
     `UNKNOWN` / `UNRECOGNIZED_REPLY`, not matched, and bound to the sealed packet, policy id, policy hash, reply
     profile and request hash. Its `completed_at` is a UTC time at or after its capture's `captured_at`.
  2. Each capture has exactly the runner's capture keys, hashes to its record's `capture_record_sha256`, and
     shows integer status 401, `application/json`, valid metadata, null `error_code` and `error_type`, a time
     after the request's frozen expiry, a positive byte count and a hex content-type hash. The two captures have the same
     `raw_body_sha256`, byte count and content-type hash, and the re-run was captured after the earlier
     attempt, after the earlier attempt completed. The re-run capture file hashes to the re-run record, as for
     every other row.
  3. The positive control is valid as before (`ALLOW` / `SIGNED_FIELDS_MATCH`, signed hash, capture hash). The
     re-run's `rerun_of` cites the earlier expiry record and that positive control by hash.
  4. The expired request differs from a fresh request only in its expiry. This is checked from the sealed packet
     (`expiry_request_difference`). The row's only frozen header is `privy-request-expiry: 1792000000000`
     (2026-10-14), below the packet's `auth_header_expiry` `1796083200000`. The transport sends a frozen expiry
     header when a row has one and the packet's otherwise, with the same app id and the row's own idempotency
     key (`actual_transport.py`). So the fresh twin is the same body with the future expiry. That twin was
     never sent. Against the positive control, the only signed request, the transaction differs in `to`,
     `data` and `gas_limit`, and the headers differ in `privy-request-expiry` and the idempotency key.
- A signed reply, any 2xx, a status other than 401, a readable code or type, differing body hashes, a missing
  or mismatched positive control, a missing earlier record or capture, and a re-run record that fails its
  existing `rerun_of` checks all stay `PRIVY_RECORD_INVALID`. A recognized expiry code
  (`UNKNOWN` / `EXPIRY_REFUSAL`) still takes the unchanged path to `PROVIDER_COVERS_SIGNING_CUTOFF_ONLY`.
- The app refuses an expired request itself before any Privy signing call. The artifact lists these checks under
  `findings.app_expiry_checks` (`control_proofs.APP_EXPIRY_CHECKS`), and a test checks that each cited line
  still returns the refusal:

  | Refusal | Where | Test that shows the refusal (and what else it shows) |
  | --- | --- | --- |
  | `REQUEST_EXPIRED` | `execution/privy_signer.py:214`, `PrivySignerClient._stop`, checked before the local authorization (line 153) and immediately before the send (line 183). The expiry is the release's `transaction.request_expires_at` (`core/provider_ports.py:735`). | `test_privy_signer.py`: `test_a_stop_before_authorization_sends_nothing`, `test_a_stop_that_arrives_during_authorization_sends_nothing`, `test_a_stop_before_authorization_never_reaches_the_key`, `test_a_stop_during_signing_sends_nothing_and_keeps_the_original_expiry`: no Privy call; an expiry during authorization comes after the local key signed |
  | `INTENT_EXPIRED` | `execution/original_transaction.py:603`, `_prepare`, before the quote and any signer call | `test_approve_swap_revoke.py::test_existing_refusals_still_precede_the_steps`: no signer call |
  | `INTENT_EXPIRED` | `execution/original_transaction.py:753`, `_recheck`, run at line 504 after `SIGN_REQUESTED` is saved and before `signer.rpc` (line 513), for the swap step (the revoke uses `_release_problem`) | none isolates this return |
  | `MANDATE_EXPIRED` | `execution/original_transaction.py:755`, `_recheck`; the unit test reaches it through the recheck after the quote (line 648), the journey test through the one at line 504 before `signer.rpc` | `test_saved_attempt_signing.py::test_mandate_expiry_during_quote_preserves_exact_refusal` (no `signer.rpc`); `test_original_transaction_journey.py::test_an_authority_change_during_a_stage_save_allows_no_next_effect[SIGN_REQUESTED-expiry-expected0]` (needs Docker Postgres) |
  | `EXECUTION_RELEASE_EXPIRED` | `execution/operating_release.py:223`, `check_release`, at or after `valid_until` or `transaction.request_expires_at`. The worker's signer factory admits the release (`core/provider_ports.py:730`, reaching `check_release` at `operating_release.py:299`) before it builds the Privy client (line 734). | `test_operating_release.py::test_signer_request_expiry_is_enforced_before_release_expiry`: the refusal only, not the call order |
  | `INTENT_EXPIRED` | `execution/service.py:656`, `ExecutionService._revalidate`, called from `_begin_submission` (line 442) before submission | `test_revalidation.py::test_expired_intent_denies_before_submission` (needs Docker Postgres): no attempt is created |

- What the decision does not show:
  - Privy did not say why it refused, so the refusal is not shown to be an expiry refusal. A 401 can also be
    an authorization or credential failure. That the same key signed the positive control is the
    controller's statement; the records do not name the key.
  - The re-run sent the same request and idempotency key, so Privy may have answered with its stored reply.
    The two replies may then be one refusal.
  - No fresh twin of the expired request was sent.

## Why these kinds of evidence

The live Privy policy `c30racyru6duaipj815cvjce` has three rules (fixture
`tests/privy_unfunded_proof/fixtures/policy_v2_live_rules.json`):

- R1: WMON `deposit`, chain 143, value at most 70 MON.
- R2: WMON `approve`, chain 143, value 0, spender the entrypoint, amount at most 70 WMON.
- R3: entrypoint `executeSwap`, chain 143, value 0. No condition on any argument.

So Privy cannot refuse an `executeSwap` with another token, amount, minimum, fee or program. A refusal test for
those fields would be signed, not refused. Privy evidence is used only where a rule really decides: which token
the entrypoint may be approved on (R2), which function may be called (R3), which contracts the agent may call
at all, and the request expiry.

Controls 4-8 are enforced by the deployed Kuru entrypoint (`CONTROL_RESTRICTIONS.md`, layer `CONTRACT`). Their
current evidence is `SOURCE_INSPECTED`, and the deployed source is not reproducible
(`kuru-deployed-source/SOURCE_IDENTITY.md`). Provider-actual evidence of a contract check is the deployed code's
behaviour on the chain. Read-only `eth_call` runs the deployed bytecode at a pinned block. Each negative
simulation changes exactly one word of the release swap. Its positive twin runs at the same block with the
same overrides and succeeds, differing in that one word: `swap_min_above` from `swap_min_equal`;
`swap_input_above_allowance`, `swap_wrong_output` and `swap_wrong_input` from `swap_probe`;
`swap_fee_over_bound` (10001 bps) from `swap_fee_charged` (100 bps, same collector); `swap_fee_sum_over_bound`
(5000 + 5001 bps) from `swap_fee_sum_at_bound` (5000 + 4999 bps, same recipients). Only that one change
explains the revert.

The wallet holds no WMON allowance, so a plain `eth_call` of the swap would revert for every input. The calls
therefore carry temporary storage overrides on WMON: wallet balance `2 x 10 WMON` (slot 3) and entrypoint
allowance `10 WMON` (slot 4). These are the slots the accepted operator dry run uses
(`scripts/operator_trade/dry_run.py`), confirmed by the builder's live check of 2026-10-22. Two override checks
(`chain.override_balance`, `chain.override_allowance`) prove the overrides took effect before any swap result
counts. An override changes only the simulation. The approve estimate overrides the balance only, so it prices
the live write of the allowance from 0 to the input, as the operator dry run does.

## Operations

### Privy: sealed control-proof packet (`raw` profile, policy `c30racyru6duaipj815cvjce`)

New rows only. The v3 packet `8255d003…` and its 19 rows are unchanged and stay registered.

| Field | Value |
| --- | --- |
| Packet SHA-256 | `501942ec92178a5621f25acb7395b44884a0d9770cbb23f44bc0c459656ae775` |
| Table manifest SHA-256 | `556fdeb5fb8101cc35b3f2b119cc7c86680544155a731b81680b920f4f5fff1d` |
| Attempt identity | `control-proofs-1` (new idempotency keys) |
| Packet expiry | `1796083200` (2026-11-30T00:00:00Z) |
| Nonce on every row | `1000000` |

| # | Operation id | Request | Expected Privy result | Why the policy decides it |
| --- | --- | --- | --- | --- |
| 1 | `raw.ctl_allow_revoke_zero` | WMON `approve(entrypoint, 0)`, value 0 | `ALLOW` (signed fields match) | R2 allows it. Positive control: no refusal counts without it. |
| 2 | `raw.ctl_deny_approve_moe_entrypoint` | MOE `approve(entrypoint, 10e18)` | `POLICY_DENY` (400 `policy_violation`) | R2 requires `to` = WMON; no rule allows a call to MOE. |
| 3 | `raw.ctl_deny_swap_receiver_wallet` | `executeSwapWithReceiver` (`0x31343b21`), the release swap, receiver = the wallet | `POLICY_DENY` | R3 allows the function `executeSwap` only. |
| 4 | `raw.ctl_deny_moe_transfer_sink` | MOE `transfer(0x…dead, 1)` | `POLICY_DENY` | No rule allows a call to MOE. |
| 5 | `raw.ctl_deny_expired_request` | the in-policy release `executeSwap` (minimum 1) with header `privy-request-expiry: 1792000000000` (2026-10-14) | refusal code `request_expired`, recorded as `UNKNOWN` / `EXPIRY_REFUSAL` | R3 allows the body. Only the past expiry can refuse it. It runs last. |

A test evaluates every row against the saved live rules: rows 1 and 5 match a rule, rows 2-4 match none.

### Chain: read-only operations (`scripts/privy_unfunded_proof/chain_proof.py`)

All at one block `B`, read first with `eth_getBlockByNumber("latest", false)`. `from` is always the wallet,
`value` always 0. `R` is the output of `chain.swap_probe`; the operations marked * use it and are skipped,
never guessed, when the probe fails. "Swap" means the release `executeSwap` built exactly as the app's
`build_calldata_hex` builds it (a test compares the bytes): sell 10 WMON, buy MOE, zero fees, the approved
program.

| Operation id | Call | Expected result |
| --- | --- | --- |
| `chain.chain_id` | `eth_chainId` | `0x8f` |
| `chain.block` | `eth_getBlockByNumber("latest", false)` | block number, hash, base fee |
| `chain.code_entrypoint`, `chain.code_router`, `chain.code_wmon`, `chain.code_pool` | `eth_getCode` at `B` | SHA-256 equals the authored `deployment` and `facts.code_sha256` values |
| `chain.get_router` | `getRouter()` on the entrypoint | the authored router `0x2f84…bbcb` |
| `chain.pool_token0`, `chain.pool_token1` | `token0()`, `token1()` on the pool | WMON, MOE |
| `chain.pool_reserves` | `getReserves()` on the pool | reserves at `B` |
| `chain.override_balance`, `chain.override_allowance` | WMON `balanceOf(wallet)`, `allowance(wallet, entrypoint)` with overrides | `20e18`, `10e18` |
| `chain.swap_probe` | swap, minimum 1 | success, returns `R > 0` |
| `chain.swap_min_equal` * | swap, minimum `R` | success, returns `R` |
| `chain.swap_min_above` * | swap, minimum `R + 1` | revert |
| `chain.swap_input_above_allowance` | swap, amount `10e18 + 1`, minimum 1 | revert |
| `chain.swap_wrong_output` | swap, `tokenUserBuys` = WMON, minimum 1 | revert |
| `chain.swap_wrong_input` | swap, `tokenUserSells` = MOE, minimum 1 | revert |
| `chain.swap_fee_over_bound` | swap, `feeBps` 10001, collector `0x…dead` | revert |
| `chain.swap_fee_sum_over_bound` | swap, `feeBps` 5000 and `referrerFeeBps` 5001, both to `0x…dead` | revert |
| `chain.swap_fee_sum_at_bound` | swap, `feeBps` 5000 and `referrerFeeBps` 4999, both to `0x…dead` | success |
| `chain.swap_fee_charged` | swap, `feeBps` 100, collector `0x…dead`, minimum 1 | success, `0 < output < R` |
| `chain.swap_trace` * | `debug_traceCall` of swap with minimum `R`, `callTracer` with logs | trace with Transfer logs |
| `chain.estimate_approve` | `eth_estimateGas` WMON `approve(entrypoint, 10e18)`, balance override only (allowance 0, as live) | estimate |
| `chain.estimate_swap` * | `eth_estimateGas` swap with minimum `R` | estimate |
| `chain.estimate_revoke` | `eth_estimateGas` WMON `approve(entrypoint, 0)` | estimate |
| `chain.swap_at_release_gas` * | swap with minimum `R` and `gas` 700000 | success, returns `R` |

## Per control: evidence, why it proves the control, what it does not prove

Every contract-based control (4-8, 10) first needs the **chain preconditions**: chain id 143; the entrypoint,
router, WMON and pool code hashes equal the authored values; `getRouter()` returns the authored router; the pool
tokens are WMON and MOE; both overrides took effect; the probe succeeded. Otherwise the control is
`CHAIN_PRECONDITION_FAILED`. Every Privy-based claim also needs the positive control's `ALLOW` record.

### 4 `input_output_assets` (builder decision: `OUTPUT_TOKEN_NOT_PROVIDER_BOUND`)

- Evidence: `chain.swap_wrong_output` (output token WMON, the input token) and `chain.swap_wrong_input` (input
  token MOE, not approved) revert while `chain.swap_probe` succeeds; `raw.ctl_deny_approve_moe_entrypoint` is
  `POLICY_DENY`.
- Why it proves the input side: Privy refuses approving the entrypoint on a non-WMON token, so the agent cannot
  create an input allowance on another asset (with v3 row `raw.deny_approve_wrong_to` and R3's `value` 0, which
  rules out native input), and the entrypoint pulls the named input token. The Privy row covers new approvals
  only; an allowance granted on another token before the policy is not covered.
- Why it is not proven: the control also limits the output token, at the `INDEPENDENT_POLICY` layer. Privy does
  not bind `tokenUserBuys`; a host could name any token with a matching program. The wrong-output case shows
  only that the input token is refused as output, not that every other token is. So the builder emits the
  artifact under `decision_required`, not a state.
- Smallest alternatives: the builder accepts the input-side proof for this control; or a Privy R3 condition on
  `executeSwap.intent.tokenUserBuys` (and `tokenUserSells`) equal to the release tokens (a policy edit with the
  builder's key; nested tuple paths are unqualified) plus an allow/deny row pair.

### 5 `raw_input`

- Evidence: `R` equals the pool formula `floor(x * 984000 * R_moe / (R_wmon * 10^6 + x * 984000))` for
  `x = 10e18` at the reserves of `chain.pool_reserves`; `chain.swap_input_above_allowance` reverts.
- Why: the output is consistent with exactly the approved input being swapped at those reserves (at the current
  price one input unit moves the output by many units). With an allowance of exactly the input, one unit more
  reverts: the entrypoint pulls the full intent amount and the allowance bounds it.
- Not proven: Privy caps an approval at 70 WMON (v3 row `raw.deny_approve_above_cap`), not at the release
  input; the host approves exactly the input. Overrides fund the simulation, not the live wallet.

### 6 `recipient`

- Evidence: `chain.swap_trace` (net MOE gain only at the wallet and equal to `R`; net WMON loss of the wallet
  exactly `10e18`; only the pool and the two pinned fee recipients gain WMON, each recipient at most 1.00% or
  0.35% of the input; only WMON and MOE move); `raw.ctl_deny_swap_receiver_wallet` and
  `raw.ctl_deny_moe_transfer_sink` are `POLICY_DENY`.
- Builder decision when the trace pays the pinned fee recipients (`FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND`):
  the recipients and bounds come from the live trace of 2026-10-23, not from source. See Finding 1.
- Why: the deployed code pays the whole output to `msg.sender`, the wallet. Privy lets the agent sign neither
  the receiver variant (even to itself) nor a later move of the output.
- Not proven: if the node does not support `debug_traceCall` with `stateOverrides` and `withLog`, the control
  stays unproven (`TRACE_UNAVAILABLE` or `TRACE_TRANSFERS_INVALID`). The smallest alternative is an endpoint
  that supports it, or a builder decision to accept the Privy refusals plus the method's signature (no receiver
  argument) without a trace. A different program could route value elsewhere; that is control 12.
- Not proven either: the trace covers the release's zero-fee calldata. Privy does not bind the fee fields, so a
  host-encoded fee collector could take up to 100% of the output in one signed swap. Only the host's zero-fee
  encoding prevents that (control 8, itself a builder decision). The trace check also refuses any frame that
  moves native value.

### 7 `minimum_output`

- Evidence: `chain.swap_min_equal` succeeds and returns `R`; `chain.swap_min_above` reverts.
- Why: the deployed entrypoint enforces the minimum received at the exact boundary.
- Not proven: Privy does not bind `minAmountUserBuys`; the host computes the minimum from its reserves read.
  The boundary is tested with the release's zero fees only.

### 8 `fees` (builder decision: `FEE_VALUES_NOT_PROVIDER_BOUND`)

- Evidence: `R` equals the pool formula (zero fees take nothing); `chain.swap_fee_over_bound` reverts where
  `chain.swap_fee_charged` succeeds; `chain.swap_fee_sum_over_bound` reverts where `chain.swap_fee_sum_at_bound`
  succeeds; `chain.swap_fee_charged` returns less than `R`.
- Why it proves the sum bound: the deployed code reads the fee fields, bounds `feeBps + referrerFeeBps` at
  10000 bps, and deducts a nonzero fee; with the release's all-zero fees no fee is taken.
- Why it is not proven: the control also requires the fee values, collector and referrer to equal the adopted
  (zero) values (`CONTROL_RESTRICTIONS.md`, layer `CONTRACT`). No provider enforces that: Privy does not bind the
  fee fields, and a fee up to 10000 bps with any collector would be signed and would execute. Only the host
  encodes zero fees. So the artifact goes under `decision_required`.
- Smallest alternatives: the builder accepts the sum-bound proof plus the host's zero-fee encoding; or a Privy
  R3 condition binding `executeSwap.fees.feeBps` and `fees.referrerFeeBps` to 0 (a policy edit with the
  builder's key; nested tuple paths are unqualified) plus an allow/deny row pair.

### 10 `gas_action_capacity`

- Evidence: `chain.estimate_approve`, `chain.estimate_swap`, `chain.estimate_revoke`, `chain.swap_at_release_gas`
  and the base fee of `chain.block`.
- Why: each authored step limit (approve 70000, swap 700000, revoke 70000) is at least `ceil(1.2 x estimate)`;
  the swap succeeds at its release limit; `2 x base fee + 2 gwei` fits the 202 gwei maximum fee; the budget
  `169680000000000000` covers every step's limit at that fee. Monad charges at most limit x maximum fee, so the
  native spend cannot pass the budget.
- Not proven: the estimates are for block `B` (the 1.2 margin covers a small change). The action, attempt,
  signer and broadcast counts are host limits (`LOCAL_TESTED`); no provider bounds them. Refusal reasons:
  `GAS_LIMIT_BELOW_ESTIMATE_MARGIN`, `BASE_FEE_ABOVE_RELEASE_FEE`, `GAS_BUDGET_SHORT`.

### 11 `expiry_freshness` (builder decision: `PRIVY_REFUSAL_REASON_NOT_READABLE`, or `PROVIDER_COVERS_SIGNING_CUTOFF_ONLY`)

- Recorded result: the 2026-10-23 attempt and its 2026-10-26 re-run were both refused with the same unreadable
  401. The builder decided on 2026-10-26 to treat that as `decision_required` with reason
  `PRIVY_REFUSAL_REASON_NOT_READABLE`. The gate, the evidence the artifact carries, the app's own expiry checks
  and what this does not show are listed in "Re-run of 2026-10-26 and the builder's decision". The artifact has
  its own claims and limits (`_EXPIRY_UNREADABLE_CLAIMS`, `_EXPIRY_UNREADABLE_LIMITS`). The rest of this section
  describes the recognized-code path, which is unchanged.

- Evidence: `raw.ctl_deny_expired_request` is refused with an expiry code (400 `request_expired`, or a 401
  whose code says the request or its authorization signature expired; see Finding 2); the authored release binds
  `transaction.request_expires_at`, `valid_until` and `route.freshness.intent_expires_at` to the same
  `valid_until` fill.
- Why: the worker sends the release's `request_expires_at` as `privy-request-expiry`
  (`core/provider_ports.py`). Privy refusing an otherwise in-policy swap after that time means no signature is
  issued after `valid_until`, which is also the intent expiry and not after the mandate expiry.
- Why it is a builder decision: control 11 is defined at the HOST layer (quote age, input age, intent and
  mandate expiry). The proof covers a provider-side property, the signing cutoff. Adopting it as the
  control's proof is the builder's call, so the artifact is emitted under `decision_required`, not as a state.
  The smallest alternative is that decision; no provider can see the quote time.
- Not proven: the quote age (30 s) and input age (60 s) are host checks. The Flow intent has no on-chain
  deadline; after signing, the minimum output (7) is the on-chain protection. The live run got a 401 whose code
  was not saved; the re-run saves it. The expiry row has no same-calldata allow twin in this
  packet; that its body is in policy rests on R3 and the v3 row `raw.allow_swap_zero_value`. A code that is not
  an expiry code stops the run (`UNRECOGNIZED_REPLY`) and needs a reviewed profile update.

### 12 `opaque_program`: not provable this way

- Reason: no layer outside the host bounds the program bytes. R3 has no condition on `program`, and Privy
  `bytes` equality is undocumented (`UNKNOWN`). The entrypoint forwards `program` opaquely. Only the host's
  exact program check (`LOCAL_TESTED`) stops a different program. A provider-actual proof of a bound that does
  not exist would be fake, so the builder always reports `NO_PROVIDER_BOUND_ON_PROGRAM_BYTES` and no state.
- Supporting evidence (not a proof): when the trace is valid, the builder writes
  `opaque_program.support.json` (state `UNPROVEN_SUPPORT`, evidence class null) showing that the approved
  program calls only the entrypoint, router, pool, WMON and MOE and pays the whole output to the wallet, and
  reports its hash as `supporting_evidence_sha256`. If the live trace calls any other address (for example a
  pair factory or fee contract, which the fee payouts of Finding 1 may involve), the support file is not
  written. When the trace pays the pinned fee recipients, the support file lists them in
  `findings.fee_transfers` and a limit line says they are observed, not sourced.
- Smallest alternatives, each a builder decision:
  1. Accept "host-exact program + provider-actual trace of that exact program" as control 12's proof. This
     changes the rule and is a separate reviewed change to the release module or this builder.
  2. Add a Privy R3 condition on `executeSwap.program` equality (a policy edit with the builder's owner key),
     then add an allow row with the approved program and a deny row with one changed byte. Privy's support for
     a `bytes` condition is unknown until that pair runs.

## What no operation can do

- No `eth_sendRawTransaction`, `eth_sendTransaction` or any send path. The chain client accepts only
  `eth_chainId`, `eth_getBlockByNumber`, `eth_getCode`, `eth_call`, `eth_estimateGas` and `debug_traceCall`,
  only from the wallet, only to the entrypoint, WMON or pool, only with value 0 and only with the frozen WMON
  overrides. Anything else refuses before any I/O.
- The Privy runner is the accepted sign-only runner; it has no broadcast path and never saves signed bytes.
  The only expected signature is a revoke to zero. Every row uses nonce `1000000`, so even a leaked signature
  could not be included until the wallet had sent a million transactions.
- No policy edit, wallet change, owner-key action, approve or swap broadcast.

## Controller run (the controller holds the keys)

From the checkout root, with `<venv>` = `apps/api/.venv`. Each store is a new directory.

1. Dry runs (no credential, no socket):

   ```sh
   PYTHONPATH=apps/api/src:. <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.actual_run --dry-run --packet control-proofs
   PYTHONPATH=apps/api/src:. <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.chain_proof --dry-run
   ```

2. Privy rows (after an independent zero-balance read of the wallet; the command still requires
   `--confirm-unfunded`). If the wallet now holds funds, stop and ask the builder: the nonce-1000000 argument
   above is the only reason a funded run would still move nothing, and accepting it is the builder's decision.

   ```sh
   PRIVY_APP_ID=... PRIVY_APP_SECRET=... PRIVY_AGENT_KEY_FILE=<agent pem> \
   PYTHONPATH=apps/api/src:. <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.actual_run \
     --packet control-proofs --store <new privy store> --confirm-unfunded
   ```

   It stops on the first `BREACH`, unexpected outcome or unknown reply. The expected `EXPIRY_REFUSAL` on the
   last row does not count as a stop.

   **Expiry row re-run (after the 2026-10-23 run; the builder runs it once).** Only
   `raw.ctl_deny_expired_request` is sent, into the new store `<the 2026-10-23 privy store>.expiry-rerun`
   (created by the command; do not pass `--store`). The earlier store is only read and no other row is sent:

   ```sh
   PRIVY_APP_ID=... PRIVY_APP_SECRET=... PRIVY_AGENT_KEY_FILE=<agent pem> \
   PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -B -s -m scripts.privy_unfunded_proof.actual_run \
     --packet control-proofs --confirm-unfunded --rerun-expiry-from <the 2026-10-23 privy store>
   ```

   It prints one line for `raw.ctl_deny_expired_request`. The capture
   `<the 2026-10-23 privy store>.expiry-rerun/raw.ctl_deny_expired_request.capture.json` holds `status`,
   `error_code` and `error_type`. A refusal before sending prints `REFUSED raw.ctl_deny_expired_request <code>`.
   A second run prints `STORE_ALREADY_EXISTS`: each earlier store has one re-run.

3. Chain reads. The endpoint must support `eth_call` and `eth_estimateGas` with `stateDiff` overrides (the
   operator endpoint did on 2026-10-22) and, for control 6, `debug_traceCall` with `callTracer`, `withLog` and
   `stateOverrides`. The URL may hold a key; it is never printed or saved.

   ```sh
   EDGE_OS_CONTROL_PROOF_RPC_URL=https://... \
   PYTHONPATH=apps/api/src:. <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.chain_proof --store <new chain store>
   ```

4. Build the proofs (no request):

   ```sh
   PYTHONPATH=apps/api/src:. <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.control_proofs \
     --authored docs/qualification/inapp-trade/release.authored.json \
     --privy-store <new privy store> --chain-store <new chain store> --out <new proofs dir>
   ```

   After the expiry re-run, add `--with-expiry-rerun` (the earlier store stays the `--privy-store`; the
   builder reads `<privy store>.expiry-rerun`, which must hold only the expiry row). The builder also reads
   the expiry capture from both stores. With the recorded unreadable 401 it then emits `expiry_freshness`
   under `decision_required` with `PRIVY_REFUSAL_REASON_NOT_READABLE`.

   It writes `<control>.proof.json` (the exact canonical bytes whose SHA-256 is the proof hash) for proven and
   decision-required controls, `opaque_program.support.json` when available, and `controls.json`. It prints
   `controls` (ready to paste into `release.controls`), `decision_required` (reason and hash, for the builder)
   and `unproven` with reasons. A Privy outcome counts only when its saved capture file hashes to the
   record's `capture_record_sha256`.

5. Commit the two raw stores and the proofs directory, then, as a separate reviewed change, put the printed
   `controls` entries (and any `decision_required` entry the builder accepts) into `release.authored.json`. That changes the release hash (pending steps 7-8 of
   `INAPP_TRADE_RELEASE.md`). This task does not do it.

## Proof artifact format

`edge-os.inapp-control-proof/1`, canonical JSON (sorted keys, compact separators), `proof_sha256` = SHA-256 of
those bytes:

| Field | Content |
| --- | --- |
| `control`, `state`, `evidence_class`, `decision_required` | the control name; `ENFORCED` or `DECISION_REQUIRED`; `PROVIDER_ACTUAL`; null or the decision reason |
| `release_id`, `authored_binding_sha256` | the release and a hash of its authored facts without `controls`, so adopting the proof does not invalidate it |
| `chain` | chain id, block number and hash, or null |
| `privy` | packet id, policy id, policy hash and reply profile, or null |
| `evidence` | per operation: kind, id, request hash, SHA-256 of the whole saved record, status / outcome |
| `findings` | the computed values (outputs, formula, estimates, fees) |
| `claims`, `limits` | fixed text: what the evidence shows and does not show |

The builder refuses (`ProofRefused`) a chain record set that is incomplete or reordered, a record whose request
is not the frozen operation for its recorded block and baseline, and an authored release whose values differ
from the frozen inputs.

## Limits of the whole method

- The artifacts are only as authentic as the records. Chain records can be re-checked by anyone by repeating
  the same calls at block `B` on an archive node. Privy records cannot; the controller commits the raw store.
  The runner labels every saved record `LOCAL_TESTED` / `UNQUALIFIED` (its fixed constant); the provider
  nature comes from the controller's live run, as for the v3 result.
- Simulations prove the deployed code at one block. The router is owner-mutable; the release's
  `mutable_router_proof_sha256` and the pre-run recheck cover later blocks.
- Overrides fund the simulation only. They prove nothing about the live balance.

## Files

| File | Role |
| --- | --- |
| `scripts/privy_unfunded_proof/actual_packet.py` | The sealed control-proof packet (new rows), registered next to the unchanged v3 packet. |
| `scripts/privy_unfunded_proof/actual_run.py` | `--packet control-proofs`; an expected expiry refusal does not stop the run; `--rerun-expiry-from` re-runs the expiry row alone. |
| `scripts/privy_unfunded_proof/actual_runner.py` | Saves the identifier-shaped error code and type of an error reply; recognizes a 401 expiry code on the expiry row; the `rerun_of` admission. |
| `scripts/privy_unfunded_proof/actual_profile.py` | `error_fields`, `safe_reply_field`, `is_expiry_refusal`. |
| `scripts/privy_unfunded_proof/chain_proof.py` | Read-only chain client, frozen operations, the pinned observed fee recipients and the one-store chain command. |
| `scripts/privy_unfunded_proof/control_proofs.py` | The pure proof builder and its command. |
| `docs/qualification/privy-unfunded-proof/ACTUAL_PROOF_OPERATION_INPUTS.json` | New `control_proof_operations` section; the v3 content is unchanged. |
| `tests/privy_unfunded_proof/test_control_proof_packet.py`, `test_chain_proof.py`, `test_control_proofs.py`, `test_control_proof_expiry_rerun.py`, `test_control_proof_expiry_decision.py`, `_control_support.py` | Tests with recorded fakes only. |

## Checks

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -m pytest -q tests/privy_unfunded_proof
```
