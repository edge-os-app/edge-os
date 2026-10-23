# Provider-actual proofs for in-app trade controls 4-8 and 10-12

Task `CLOUD-CONTROL-PROOFS`, builder-approved 2026-10-23 ("collect the proofs"). Base
`3a495cd355262b712afbc966ea49932e19dea575` (`integration/edge-os-mvp`). Status: **collection built, not run.**
Nothing here was run against Privy or Monad. No network, provider, credential or key was used. This document
grants no trade authority and changes no release hash.

`check_release` admits an ACTUAL release only when all 12 controls are `ENFORCED`, carry evidence class
`PROVIDER_ACTUAL` and have a proof hash. Controls 1-3 and 9 come from the recorded v3 result (controller,
pending step 1 of `INAPP_TRADE_RELEASE.md`). This plan covers the other eight.

## Result in one table

| # | Control | Verdict | Evidence |
| --- | --- | --- | --- |
| 4 | `input_output_assets` | **Builder decision** (input side only; the output token has no provider bound) | Chain simulations + one Privy refusal |
| 5 | `raw_input` | Provable | Chain simulations |
| 6 | `recipient` | Provable if the node supports `debug_traceCall` | Chain trace + two Privy refusals |
| 7 | `minimum_output` | Provable | Chain simulations |
| 8 | `fees` | **Builder decision** (sum bound only; fee values and recipients have no provider bound) | Chain simulations |
| 10 | `gas_action_capacity` | Provable for the native gas budget | Chain estimates and base fee |
| 11 | `expiry_freshness` | **Builder decision** (provider signing cutoff only; the control is HOST-layer) | One Privy refusal |
| 12 | `opaque_program` | **Not provable this way** | See "Control 12" |

"Provable" means: if the controller's live run returns the expected results, the proof builder emits an
artifact and a hash in the `check_release` shape under `controls`. "Builder decision" means: with complete
evidence the builder emits the artifact and its hash under `decision_required`, with a fixed reason, but no
state; putting that hash into the release is a builder decision and a separate reviewed change. Any other
result leaves the control in `unproven` with a fixed reason. The builder never writes a state for a control it
did not prove.

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
  exactly `10e18`; only the pool gains WMON; only WMON and MOE move); `raw.ctl_deny_swap_receiver_wallet` and
  `raw.ctl_deny_moe_transfer_sink` are `POLICY_DENY`.
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

### 11 `expiry_freshness` (builder decision: `PROVIDER_COVERS_SIGNING_CUTOFF_ONLY`)

- Evidence: `raw.ctl_deny_expired_request` is refused with `request_expired`; the authored release binds
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
  deadline; after signing, the minimum output (7) is the on-chain protection. The Privy reply code
  `request_expired` is documented, not yet observed. The expiry row has no same-calldata allow twin in this
  packet; that its body is in policy rests on R3 and the v3 row `raw.allow_swap_zero_value`. A different code stops the run (`UNRECOGNIZED_REPLY`)
  and needs a reviewed profile update.

### 12 `opaque_program`: not provable this way

- Reason: no layer outside the host bounds the program bytes. R3 has no condition on `program`, and Privy
  `bytes` equality is undocumented (`UNKNOWN`). The entrypoint forwards `program` opaquely. Only the host's
  exact program check (`LOCAL_TESTED`) stops a different program. A provider-actual proof of a bound that does
  not exist would be fake, so the builder always reports `NO_PROVIDER_BOUND_ON_PROGRAM_BYTES` and no state.
- Supporting evidence (not a proof): when the trace is valid, the builder writes
  `opaque_program.support.json` (state `UNPROVEN_SUPPORT`, evidence class null) showing that the approved
  program calls only the entrypoint, router, pool, WMON and MOE and pays the whole output to the wallet, and
  reports its hash as `supporting_evidence_sha256`.
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
| `scripts/privy_unfunded_proof/actual_run.py` | `--packet control-proofs`; an expected expiry refusal does not stop the run. |
| `scripts/privy_unfunded_proof/chain_proof.py` | Read-only chain client, frozen operations and the one-store chain command. |
| `scripts/privy_unfunded_proof/control_proofs.py` | The pure proof builder and its command. |
| `docs/qualification/privy-unfunded-proof/ACTUAL_PROOF_OPERATION_INPUTS.json` | New `control_proof_operations` section; the v3 content is unchanged. |
| `tests/privy_unfunded_proof/test_control_proof_packet.py`, `test_chain_proof.py`, `test_control_proofs.py`, `_control_support.py` | Tests with recorded fakes only. |

## Checks

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -m pytest -q tests/privy_unfunded_proof
```
