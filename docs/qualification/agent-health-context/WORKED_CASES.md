# Worked health and context cases (P31 preparation)

Machine-readable fixtures: [worked_health_cases.json](worked_health_cases.json).
Base `f84ef415278196db2c8bba73eaa154a1ef00748b`, projection `edge-os.agent-health-projection/1`.

These are independently worked, unsigned contract examples. They contain no real data, no signing,
no broadcast and no provider effect. They are reviewable contract checks, not runtime, browser or
chat proof. `NOT_RUN`: no runtime check was performed.

## Method

Each case lists every stored row in `stored_rows` with the table, id, the row's real timestamp
column (`time_field`), that time, and a `time_basis`:

- `DIRECT`: the row's own timestamp column. `admission_positions` has no timestamp column, so it is
  never `DIRECT`.
- `DERIVED`: the position time equals the latest intent or receipt of the position
  (`accounts/service_projection.py:117-139`).

`as_of` equals the newest `DIRECT` time. A case with no stored row has `as_of: null` and no
projection.

Counts come from rows, not from `runs`. Each `execution_evaluation_jobs` row carries its `state`;
`evaluation_attempts` equals the number of listed job rows and `evaluation_completions` counts the
rows whose `state` is `COMPLETED` (`accounts/service_projection.py:162-177`). Every submission field
traces to a listed `execution_submission_attempts` row (`last_submission_attempt_at` is a
`started_at`, `last_submission_completion_at` is the last `completed_at`), and `last_decision_input_at`
traces to a listed `execution_decisions` row. Evaluation health and submission health are separate:
the evaluation timestamps come from job rows, the submission timestamps and the decision input time
come from `HealthView` over `SubmissionAttemptRow` and `DecisionRow`.

The expected **direct projection** is the canonical object. The expected **conversation summary**
renders from it and must agree on exact values, sources and unknowns. The summary states no value the
projection does not hold.

| Axis | Check |
|---|---|
| `values_agree` | every number, state and timestamp in the summary equals the projection |
| `sources_agree` | every statement names the same `record_refs` identity the projection names |
| `unknowns_agree` | every `UNKNOWN` stays `UNKNOWN` in both; a summary never turns an unknown into zero |

## Cases

| Case | Requirement covered | Verdict on the contract |
|---|---|---|
| `signal_open_position` | signal, one position, known realized result | 2 job rows, 2 completions; evaluation and submission clocks separate; realized 0 for a fresh entry; deposit is a flow |
| `no_signal` | no-signal is useful work | 1 job row and 1 decision row; no position row, so basis/realized/residual stay unknown, not zero |
| `stale_input` | stale input | reason `OBSERVATIONS_WRONG_TIME`; unknown stays unknown |
| `missing_input_wrong_market` | missing/wrong input | `OBSERVATIONS_WRONG_MARKET`; no decision |
| `wait_provider_unavailable` | fault/wait | `WAITING:MARKET_UNAVAILABLE`; the queued action stays |
| `pending_unknown_original` | pending unknown original transaction | `pending_reconciliation = true`; exact original action and recovery case kept |
| `stop_sticky_after_restart` | stop/removal sticky after restart | `HALT_ALL_SWAPS` + `CONFIRMED` removal deny; residual inventory and a negative realized result shown |
| `owner_b_navigation_retarget_denied` | owner B / target navigation | `404`, no provider call, no retarget, `as_of: null` |
| `context_corrected_disabled_cleared` | stale vs corrected/disabled/cleared context | versions 1-4 with record ids; no financial record changes |
| `repeated_preview_same_action` | repeated preview and job/action identity | repeated schedule returns the same job; the PROPOSED preview binds a saved action only when one exists |

## Independently calculated values

The worked numbers are small and exact, so a reviewer can recompute them.

- `signal_open_position`: one fresh entry spends `50000000000000000000` quote units of `0x1111…1111`
  to acquire `100000000` base units of `0x2222…2222` (6 decimals). Because the entry retains the full
  inventory and no exit has run, `realized_result` is a stored `0` and `basis` is
  `50000000000000000000`. The deposit `flow-0001` is a capital flow and is not a result.
- Native gas for that entry is `150000 x 2000000000 = 300000000000000` MON (`rcpt-0001`), shown in a
  separate field and not converted.
- `no_signal`: no `admission_positions` row exists, so basis, realized result and residual inventory
  are `UNKNOWN`, never `0`. The saved `dec-0002` decision is listed and summarized.
- `stop_sticky_after_restart`: the timeline is decision `dec-0007` (`decision_at` `21:23`), intent
  `act-0007` (`21:24`), submission attempt `sub-0007` (`started_at` `21:25`, `completed_at` `21:27`),
  receipt `rcpt-0007` (`21:27`), stop `stop-0007` (`created_at` `21:29`), removal state `rmv-0007`
  (`updated_at` `21:29:30`). Residual inventory is `25000000` base units after a confirmed partial
  exit. `realized_result` is `-500000000000000000` quote units; the negative sign is retained, never
  shown as zero. `scoped_stops` uses `created_at`; `admission_positions` has no time column and is
  `DERIVED`.

## Event ordering and expired scope

- Decisions are saved before an intent, and the intent before any submission (IC02). The summary
  reads states in that order: QUEUED → DECIDED → ENQUEUED → SUBMITTED/COMPLETED.
- An expired intent or an expired mandate keeps the original refused before signing as
  `DEFINITELY_UNSENT`; after signing it stays unknown and no broadcast runs
  (USER_RELEASE_INTEGRATION_PROFILE, "Outcomes").
- The decision slot is the latest five-minute UTC grid point at scheduling. A decision for another
  slot is `OBSERVATIONS_WRONG_TIME`; observations for another market are `OBSERVATIONS_WRONG_MARKET`.
- A control (stop or removal) that commits before the admission/submission transition denies the
  transition. A control that commits after ownership does not undo an in-flight original action; it
  stays recoverable (`revocation/enforcement.py`).

## Original pending identity

`pending_unknown_original` keeps the exact original `action_id` (`act-0006`) through its recovery case
(`case-0006`). Reconciliation reads one receipt for that exact action, wallet and network. The system
never constructs a replacement action.

The schedule identity is separate from the action identity. A repeated schedule call returns the same
`execution_evaluation_jobs` row, keyed per `(owner, agent, request_key)` and per
`(owner, agent, adopted consent, decision slot)`; that identity is a job, and a job may produce no
action (no-signal). An `action_id` exists only after evaluation admits and enqueues an action. The
case `repeated_preview_same_action` lists both a job row and the action rows and keeps them distinct.

## Direct and conversation agreement

For each case the direct projection and the conversation summary must agree exactly.
`stop_sticky_after_restart` has `as_of` `2026-10-12T21:29:30Z`, the newest stored row time
(`removal_states.updated_at`), never the read time. The conversation must show the same `as_of`, the
same residual inventory and the same unknown states. The owner-B case has no stored row, so its
`as_of` is `null`, not a read time.

## What these cases do not prove

- No provider, chain, signer, model, host or browser ran.
- No financial effect was simulated.
- The preview cases are contract examples; they are not chat runtime proof.
- Autonomy, scheduling, standing permission and forward feeds stay `MISSING` until P27 implements
  them.
