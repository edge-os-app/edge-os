# CLOUD-CONTROL-PROOFS status

Task `CLOUD-CONTROL-PROOFS`, builder-approved normal cloud session, 2026-10-23 ("collect the proofs").
Repository `edge-os-app/edge-os`, branch `cloud/control-proofs`, base `origin/integration/edge-os-mvp` at
`3a495cd355262b712afbc966ea49932e19dea575`. Only `cloud/control-proofs` was pushed, with normal pushes. No main or
integration push, no force push, no PR, no merge. No network, provider, credential, key or VPS was used.

## Result

**Final reviewed code SHA: `3cf11a4`** (`3cf11a4` is the full short id; `git rev-parse 3cf11a4` gives the long id).
This status file is the only commit after it, and it is documentation only.

Both new independent reviewers returned **PASS on the same commit `3cf11a4`**:

| Review | Verdict at `3cf11a4` |
| --- | --- |
| Spec (each control's evidence really proves the control) | PASS |
| Standards (no operation can move funds or change a policy; fakes only) | PASS |

Earlier rounds: `615c80d` failed both reviews, and `40be8a4` got standards PASS and spec FAIL. Every blocking
finding was fixed:
- the approve gas estimate ran under an allowance override;
- `input_output_assets`, `fees` and `expiry_freshness` were emitted as ENFORCED beyond their evidence;
- the recipient fee-redirect limit was missing;
- the fee-sum negative had no one-word twin.

Commits: `91d9ef5` (RED tests), `615c80d` (implementation and plan), `40be8a4` and `3cf11a4` (review fixes).

## Per-control outcome (what the builder emits if the live run matches)

| # | Control | Outcome | Reason |
| --- | --- | --- | --- |
| 4 | `input_output_assets` | `decision_required` (artifact and hash, no state) | `OUTPUT_TOKEN_NOT_PROVIDER_BOUND` |
| 5 | `raw_input` | `controls`: ENFORCED / PROVIDER_ACTUAL | Chain simulations |
| 6 | `recipient` | `controls`: ENFORCED / PROVIDER_ACTUAL, if the node supports `debug_traceCall` | Chain trace + two Privy refusals |
| 7 | `minimum_output` | `controls`: ENFORCED / PROVIDER_ACTUAL | Chain simulations |
| 8 | `fees` | `decision_required` | `FEE_VALUES_NOT_PROVIDER_BOUND` |
| 10 | `gas_action_capacity` | `controls`: ENFORCED / PROVIDER_ACTUAL | Chain estimates and base fee |
| 11 | `expiry_freshness` | `decision_required` | `PROVIDER_COVERS_SIGNING_CUTOFF_ONLY` |
| 12 | `opaque_program` | `unproven`, always | `NO_PROVIDER_BOUND_ON_PROGRAM_BYTES` (support artifact only) |

Details, operation ids, expected results, limits, smallest alternatives and the exact controller commands are
in [`CONTROL_PROOFS_PLAN.md`](CONTROL_PROOFS_PLAN.md).

## Files

| File | Change |
| --- | --- |
| `scripts/privy_unfunded_proof/actual_packet.py` | New sealed control-proof packet `501942ec…ae775` (5 new rows, nonce 1000000), registered next to the unchanged v3 packet `8255d003…0528` |
| `scripts/privy_unfunded_proof/actual_run.py` | `--packet control-proofs`; `should_stop` lets an expected `EXPIRY_REFUSAL` through |
| `scripts/privy_unfunded_proof/chain_proof.py` | New: read-only chain client, 27 frozen operations, one-store command |
| `scripts/privy_unfunded_proof/control_proofs.py` | New: pure proof builder and command |
| `scripts/privy_unfunded_proof/actual_runner.py`, `specimens.py` | Docstring/comment only (two sealed packets) |
| `docs/qualification/privy-unfunded-proof/ACTUAL_PROOF_OPERATION_INPUTS.json` | New `control_proof_operations` section; v3 content unchanged |
| `docs/qualification/privy-unfunded-proof/ACTUAL_RUNNER.md`, `CONTRACT.md` | Registry text: two sealed packets and manifests |
| `docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md` | New: the plan |
| `tests/privy_unfunded_proof/test_control_proof_packet.py`, `test_chain_proof.py`, `test_control_proofs.py`, `_control_support.py` | New tests, recorded fakes only |
| `tests/privy_unfunded_proof/test_unfunded_policy_packet.py`, `test_actual_proof_runner.py`, `_actual_support.py` | Registry assertions widened from one to two sealed entries; docstrings |

Not touched: settings, registry lines (`APPROVED_ACTUAL_*`), the release hash, `release.authored.json`, quote
client, worker bootstrap.

## Test commands and counts (at `3cf11a4`)

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -m pytest -q -p no:cacheprovider tests/privy_unfunded_proof
# 386 passed, 1 skipped (the existing skip that needs the private saved live result)
cd apps/api && .venv/bin/python -m pytest -q -p no:cacheprovider tests/execution/test_inapp_trade_release.py tests/operator_trade
# 231 passed, 1 skipped (existing lane-3 skip)
```

Not run: lint (`ruff` is not installed in the venv). No live Privy or chain run: that is the controller's step.

## Open items for the builder and controller

1. **Builder decisions:** whether to accept the `decision_required` artifacts for controls 4, 8 and 11 as
   their proofs, or take an alternative (Privy conditions on intent tokens or fee fields, which is a policy
   edit). Also how to handle control 12 (accept the host-exact program plus the trace, or add a Privy program
   condition). See the plan.
2. **Reviewer notes, non-blocking at `3cf11a4`, for the builder's judgement:**
   - `recipient` is ENFORCED, but its own limit says a host-encoded fee collector could take the output.
     Only the host's zero-fee encoding (control 8, a builder decision) prevents that. The builder may want
     `recipient` to wait on the same decision.
   - `gas_action_capacity`: the cap holds for the host-encoded gas limit and maximum fee. The Privy policy does
     not bind gas fields, and R1 allows up to 70 MON native value through `deposit`. A limit sentence should
     say so.
   - `swap_wrong_input` reverts because the wallet has no MOE allowance or balance, which is ordinary ERC20
     behaviour (control 4 is already a decision).
   - v3 rows cited in the limits text are not verified by the builder.
   - A decision artifact's body says `DECISION_REQUIRED` even after adoption.
   - The two fee twin pairs lack a one-word test (correct by reading).
   - Revert detection could be tightened to code 3 / "execution reverted".
   - JSON-RPC `id` type is not checked strictly.
   - The plan's "only from the wallet" should read "from the wallet when a sender is given", and the router
     is also an `eth_getCode` target.
3. **Controller run preconditions:**
   - An RPC endpoint with `eth_call` and `eth_estimateGas` state overrides, and for control 6,
     `debug_traceCall` with `callTracer`, `withLog` and `stateOverrides`.
   - The Privy expiry reply code `request_expired` is documented, not yet observed. A different code stops
     the run.
   - The Privy command still requires `--confirm-unfunded`. If the wallet now holds funds, ask the builder
     before running.
4. **Adoption** of any proof hash into `release.authored.json` changes the release hash. It is a separate
   reviewed change (pending steps 7-8 of `INAPP_TRADE_RELEASE.md`).
