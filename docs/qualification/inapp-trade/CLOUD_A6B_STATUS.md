# CLOUD-A6B status: the in-app release names its three steps and covers their gas

Task `CLOUD-A6B`, builder-approved normal cloud session, 2026-10-23. This file is the worker's completion report
for the controller. It grants no authority.

| Item | Value |
| --- | --- |
| Branch | `cloud/a6b-release-steps` (normal pushes only; no PR, no merge; main and integration untouched) |
| Base | `origin/integration/edge-os-mvp` at `c0d59cae84560617254720a2f818f0dc07c60344` |
| Reviewed candidate (final code SHA) | `41db698aa577dc61bb4738e1e489f222f7cd415a` |
| Commits | `48742c4` RED tests · `41db698` implementation · this status file (docs only, after review) |
| **New `release.authored.json` SHA-256** | **`d3b4be5a84a674a67fe3947300ba8d57b2c74f6e7308ff0567f2fea3df054e38`** |
| Registered | Nothing. `APPROVED_ACTUAL_RELEASES` and `APPROVED_ACTUAL_BINDINGS` are still empty. |

The authored release still carries `{"$fill": name}` markers. The registrable `release_sha256` exists only
after the controller's fill. Step 7 of `INAPP_TRADE_RELEASE.md` prints it, and the builder approves that hash
later. Both reviewers accepted this reading.

## What changed

- **Limits per step (decision 1).** `operating_release.validate_limits` admits exactly two `limits` shapes:
  - **Single action, unchanged.** Its bytes and hash are the same as before: the pinned synthetic hash `7fee779d…3b30`
    matches the base.
  - **Steps.** No top-level `signer_requests` or `broadcasts`. `steps` is exactly `[approve, swap, revoke]`, and each
    entry is `{step, signer_requests: 1, broadcasts: 1}`.

  Any other shape refuses `EXECUTION_RELEASE_INVALID`. The new `release_steps(release)` returns the named order.
- **Step path.** With a bound release, `OriginalTransactionTransport` refuses `RELEASE_STEPS_MISMATCH` before the
  quote, the nonce read or any signer call in two cases: the step plan's order differs from the release's steps,
  or a step release runs without a plan.
- **Gas budget (decision 2).** `budget_raw` is now `169680000000000000` = (70000 + 700000 + 70000) × 202 gwei.
  `inapp_trade_release` refuses `INAPP_AUTHORED_INVALID` in three cases: the release lacks the step shape, its
  steps differ from `active_steps`, or the budget is below the sum of the active step limits × `max_fee_per_gas`.
  The USD figures at 0.02 USD/MON:
  - input plus budget: USD 0.2033936;
  - worst case including the wrap: USD 0.203636.

  Both are below USD 2.
- **Revoke after a stop (decision 3).** No behaviour change from A6. This is now recorded as a builder decision in
  `INAPP_TRADE_RELEASE.md`. Two tests cover it:
  - `test_builder_decision_a_stop_agent_removal_or_consent_change_never_blocks_the_revoke`, for a stop, an agent
    removal and a consent change;
  - the existing intent-expiry test.

## Files changed (base..`41db698`)

- `apps/api/src/edge_os_api/execution/operating_release.py` (release shape and admission only)
- `apps/api/src/edge_os_api/execution/inapp_trade_release.py`
- `apps/api/src/edge_os_api/execution/original_transaction.py` (`_release_steps_problem`, docstring)
- `apps/api/tests/execution/test_operating_release.py`, `test_inapp_trade_release.py`, `test_approve_swap_revoke.py`
- `docs/qualification/inapp-trade/release.authored.json`, `INAPP_TRADE_RELEASE.md` (new section "Release steps
  and gas budget (`CLOUD-A6B`)")

No forbidden path was edited.

## Test commands and counts (from `apps/api`)

| Command | Base | `41db698` |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/execution tests/test_original_transaction_journey.py tests/recovery tests/operator_trade -p no:cacheprovider` | 1072 passed, 1 skipped | **1135 passed, 1 skipped** (about 2 min 37 s) |
| `... tests/test_actual_binding_admission.py tests/test_actual_binding_pipeline.py tests/test_release_integration_contracts.py tests/test_operating_release_research.py tests/test_environment_runtime_bootstrap.py tests/test_nansen_runtime_mount.py tests/kuru_flow tests/stops tests/test_financial_routes.py tests/test_connected_journey.py` | – | 341 passed |

- The skip is `test_lane3_signer_limit.py:82` ("lane 3 is present"), which is expected.
- Docker: the worker started `dockerd`, and all PostgreSQL tests ran.
- RED: at `48742c4`, `test_approve_swap_revoke.py` had 12 failing tests. The other two test files failed to
  collect because `release_steps` did not exist yet.
- Not run: no lint or type checker is installed in `.venv`.

## Reviews (both on `41db698`)

| Reviewer | Verdict | Evidence |
| --- | --- | --- |
| Spec | **PASS** | 1135 passed, 1 skipped. Confirmed RED-first, all three decisions, the doc hash, empty registries and scope. |
| Standards | **PASS** | 1135 passed, 1 skipped. Base-vs-new probe over 20,170 single-action mutations: 0 disagreements in accept/refuse, hash or bytes. A 30,000-mutation step-shape probe found 0 unexpected admissions. |

## Non-blocking notes from the reviewers (not changed, because any change needs a new review)

1. `CLOUD_A6_STATUS.md` "Open questions" 1-3 are now resolved by this task. That file still shows the old budget.
2. "Expiry" in decision 3 means intent and mandate expiry. The revoke still rechecks the release admission, so if
   the release's own `valid_until` passes between the swap and the revoke, the revoke is refused and the allowance
   stays reported open. This was already so in A6. The builder may want to confirm it.
3. The step order is defined twice (`operating_release.RELEASE_STEPS`, `original_transaction.STEP_ORDER`). Drift
   fails closed.
4. `OperatingRelease` alone cannot check that a step release's budget covers approve and revoke, because the
   release carries only the swap gas limit. The rule is enforced in `inapp_trade_release` and at run time
   (`FEE_EXCEEDS_GAS_RESERVATION` before step 1).
5. An unbound `TradeSteps` run (synthetic, no release) has no release steps to compare against. This is a note
   for the wiring lane.
6. Two lines are over 120 characters (`operating_release.py:72`, `test_inapp_trade_release.py:24`). This is
   cosmetic.
