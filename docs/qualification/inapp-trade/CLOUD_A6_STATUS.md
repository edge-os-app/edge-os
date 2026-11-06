# CLOUD-A6 status: one in-app action = approve, swap, revoke

Task `CLOUD-A6`, builder-approved normal cloud session, 2026-10-23. This file is the worker's completion report for
the controller. It grants no authority.

| Item | Value |
| --- | --- |
| Branch | `cloud/a6-approve-swap-revoke` (normal pushes only; no PR, no merge; main and integration untouched) |
| Base | `origin/integration/edge-os-mvp` at `82290e203982ee710189c4d983edce9a4ddfba9f` |
| Reviewed candidate (final code SHA) | `729a1a2` |
| Commits | `7a6167d` RED tests · `a2386e4` implementation · `729a1a2` review repair · this status file (docs only, after review) |

## Files changed (base..`729a1a2`)

- `apps/api/src/edge_os_api/execution/original_transaction.py`: `TradeSteps` step plan, `approve_calldata`, the
  approve → swap → revoke orchestration, the shared per-step send helper, the checks before step 1, fail-closed
  receipt reading for step envelopes, and the owner projection of step records and the allowance.
- `apps/api/src/edge_os_api/recovery/allowance.py` (new): `allowance_status` and `read_revoke_receipt`.
- `apps/api/src/edge_os_api/recovery/service.py`, `recovery/types.py`: `RecoveryCaseView.allowance`.
- `apps/api/tests/execution/test_approve_swap_revoke.py` (new, 39 tests).
- `apps/api/tests/recovery/test_approve_swap_revoke_recovery.py` (new, 3 tests, PostgreSQL).
- `docs/qualification/inapp-trade/INAPP_TRADE_RELEASE.md`: a new section "In-app approve, swap and revoke
  (`CLOUD-A6`)", and one stale bullet updated to point to it.

No forbidden path was edited (`provider_ports.py`, `worker.py`, `financial_services.py`, `wallet_setup/`,
`scripts/privy_wallet_lookup/`, settings, `hosted_deployment.py`, compose, `deploy/`, web, research).

## Test commands and counts (on `729a1a2`)

All commands run from `apps/api`.

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/execution tests/test_original_transaction_journey.py tests/recovery -p no:cacheprovider` | **937 passed** (895 at base) |
| `... tests/execution tests/test_original_transaction_journey.py tests/recovery tests/stops tests/test_financial_routes.py tests/test_connected_journey.py` | 1006 passed |
| `... tests/operator_trade tests/kuru_flow tests/stops tests/test_financial_routes.py tests/test_connected_journey.py tests/test_actual_binding_pipeline.py` (run on `a2386e4`) | 339 passed, 1 skipped (lane-3 signer skip, expected) |

**Docker and PostgreSQL:** everything ran. The container had Docker installed but the daemon was not running. The
worker started `dockerd` and pulled `postgres:18.6-trixie`. After that, every PostgreSQL test ran, including the
recovery crash tests. Nothing was skipped for lack of Docker.

**Not run:** no lint or type checker is installed in `apps/api/.venv` (no ruff, no mypy).

## Reviews

| Round | Candidate | Spec reviewer | Standards reviewer |
| --- | --- | --- | --- |
| 1 | `a2386e4` | FAIL: a lasting stop or expiry after the approve also blocked the revoke | FAIL: the USD ceiling did not check for a WMON input; the owner refusal view could show a policy refusal after the approve was sent; reconciliation could settle the action from the swap receipt alone |
| 2 (two new reviewers) | `729a1a2` | **PASS** (937 passed + 38 edge-case probes) | **PASS** (937 passed + a fault-injection probe of about 110k runs across every signer, broadcast and save fault on every step) |

Both reviewers in round 2 passed the same commit, `729a1a2`. Every round-1 finding was fixed in `729a1a2`.

## Open questions and follow-ups

Builder decisions:

1. **Release limits.** The release fixes `signer_requests` `1` and `broadcasts` `1`, and `operating_release.py`
   requires those values. A three-step action makes 3 of each. Either the limits count per step, or the rule
   changes. Either way the release gets a new hash.
2. **Gas budget.** `gas.budget_raw` is `141400000000000000`, the swap alone. Three steps need
   `169680000000000000`. With this release the step path refuses `FEE_EXCEEDS_GAS_RESERVATION` before step 1. A
   larger budget needs a new release hash.
3. **Revoke recheck.** The revoke rechecks only the release admission. It skips the stop controls, the intent and
   mandate expiry, agent removal and `CONSENT_OR_REVISION_CHANGED`, because it only lowers the allowance. Please
   confirm this, or decide that removal or consent changes should still block the revoke.

Wiring lane (outside A6 paths):

4. `worker.py` and `ControlledRuntime.clients` (`provider_ports.py`) do not pass a step plan yet. The mounted
   clients also expect top-level `SIGN_REQUESTED` / `BROADCAST_REQUESTED` stages and the swap's signed bytes.
5. In `worker._reconcile_original`, treat `in_flight` together with `steps` as in flight. Otherwise a concurrent
   reconcile can end the attempt between the swap and the revoke. The allowance is then reported open but never
   revoked.
6. Step-aware settlement is not built: bound receipts for every sent step, with all step gas charged. Until then a
   step action stays `SUBMISSION_UNKNOWN` with its reservations held. `read_revoke_receipt` has no caller, and it
   should check finality and chain id before it is wired. The step plan should also be tied to the bound release's
   identity.

Small items noted by the reviewers but not changed, because any code change needs a new review:

- The `INAPP_TRADE_RELEASE.md` outcome table says "Refused before step 1 → `NOT_APPROVED`". Such an envelope
  actually has no allowance record (`None`).
- Check `context.sell.token` against the start asset's token as well as its asset id.
- Compare the ceiling in integers instead of `Decimal`.
- Remove duplicated constants (`STEP_ORDER`, `WEI_PER_MON`, `MAX_USD_CEILING`).
- Wrap one line over 120 characters (`original_transaction.py:443`).
- `list_cases` makes one attempt query per case.
