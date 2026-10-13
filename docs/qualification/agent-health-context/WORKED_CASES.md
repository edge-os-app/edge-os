# Worked health and context cases (P31 preparation)

Machine-readable fixtures: [worked_health_cases.json](worked_health_cases.json).
Base `f84ef415278196db2c8bba73eaa154a1ef00748b`, projection `edge-os.agent-health-projection/1`.

These are independently worked, unsigned contract examples. They contain no real data, no signing,
no broadcast and no provider effect. They are reviewable contract checks, not runtime, browser or
chat proof. `NOT_RUN`: no runtime check was performed.

## Method

Each case lists every stored row in `stored_rows`, including the numeric inputs the projection needs.
Each row gives its table, id, the row's real timestamp column (`time_field`), that time, and a
`time_basis`:

- `DIRECT`: the row's own timestamp column. `admission_positions` has no timestamp column, so it is
  never `DIRECT`.
- `DERIVED`: the position time equals the latest intent or receipt of the position
  (`accounts/service_projection.py:117-139`).

Two identities stay separate. `projection_ref` is the aggregate projection identity
(`health:{owner}:{agent}:{wallet}:{network}`). Each `record_refs` entry names an exact source row by
its own id, so the contributing rows are identifiable.

`as_of` equals the newest `DIRECT` time. A case with no stored row has `as_of: null` and no
projection.

Every claimed value recomputes from the listed rows:

- counts come from rows. Each evaluation-job row carries `state`; `evaluation_attempts` equals the
  number of listed job rows and `evaluation_completions` counts `state == 'COMPLETED'`
  (`accounts/service_projection.py:162-177`).
- `last_evaluation_outcome` is the newest job `outcome`; it is `null` when the row `outcome` is null.
  `last_evaluation_state` carries the newest job `state`. A job state is never reported as an outcome.
- `last_submission_attempt_at` is a `started_at`, `last_submission_completion_at` is the last
  `completed_at`, both from listed `execution_submission_attempts` rows;
  `last_decision_input_at` is a listed `execution_decisions.decision_at`; `next_scheduled_at` is that
  time plus five minutes.
- `residual_inventory` copies a listed `admission_positions.inventory_raw`; `basis` copies its
  `cost_basis_raw`; `realized_result` copies its `realized_raw`; `native_gas` equals a listed receipt's
  `gas_used × effective_gas_price`; `deposits` copy a listed `funding_local.funding_flows` amount.

Field classes are labelled in `HEALTH_PROJECTION_CONTRACT.md` §3 and `SOURCE_RECORD_MAP.md`: `EXPOSED`
(the accepted projection or route outputs it), `SERVICE VALUE` (an accepted service computes it, no
read surface), `STORED INPUT / PROPOSED` (a stored column the lane2 P27 producer must expose), and
`MISSING`. The evaluation counts and last activity are exposed today; the evaluation outcome,
completion time, state and wait reason are stored inputs the lane2 producer must derive. The job-bound
scope identities and hashes are stored inputs; the current connected identity at
`GET /v1/agents/{agent_id}/actions` is a separate value that can differ from a saved job's historical
scope.

Every row that supplies a known projected value appears in `record_refs` by its own id. A reference
that merely resolves to a listed row is not enough: the contributing row must be the source of the
value it is cited for. A consequential status or boolean (`stop_state`, `removal_state`,
`pending_reconciliation`, `future_entries_active`) is `KNOWN` only with a named source; without one it
is an explicit `UNKNOWN` with a reason (`control_state_basis` names the stop/removal source).

The expected **direct projection** is the canonical object. The expected **conversation summary**
renders from it and must agree on exact values, sources and unknowns.

| Axis | Check |
|---|---|
| `values_agree` | every number, state and timestamp in the summary equals the projection |
| `sources_agree` | every statement names the same `record_refs` identity the projection names |
| `unknowns_agree` | every `UNKNOWN` stays `UNKNOWN` in both; a summary never turns an unknown into zero |

## Cases

| Case | Requirement covered | Verdict on the contract |
|---|---|---|
| `signal_open_position` | signal, one position, known realized result | 2 job rows, 2 completions; evaluation and submission clocks separate; residual = entry, realized 0; deposit and gas recomputed |
| `no_signal` | no-signal is useful work | 1 job row and 1 decision row; no position row, so basis/realized/residual stay unknown, not zero |
| `stale_input` | stale input | reason `OBSERVATIONS_WRONG_TIME`; unknown stays unknown |
| `missing_input_wrong_market` | missing/wrong input | `OBSERVATIONS_WRONG_MARKET`; no decision |
| `wait_provider_unavailable` | fault/wait | `WAITING:MARKET_UNAVAILABLE`; the queued action stays |
| `pending_unknown_original` | pending unknown original transaction | `pending_reconciliation = true`; exact original action and recovery case kept |
| `stop_sticky_after_restart` | stop/removal sticky after restart | `HALT_ALL_SWAPS` + `CONFIRMED` removal deny; residual = confirmed entry; realized 0; gas recomputed |
| `owner_b_navigation_retarget_denied` | owner B / target navigation | `404`, no provider call, no retarget, `as_of: null` |
| `context_corrected_disabled_cleared` | stale vs corrected/disabled/cleared context | versions 1-4 all cited; entry counts and retrieved ids/text derive from listed `entries`; the correction does not adopt the suggested lesson; disable/clear retrieve none; financial basis cited |
| `repeated_preview_same_action` | repeated preview and job/action identity | a QUEUED action gives an `ENQUEUED` job; the repeated call returns the same job; the PROPOSED preview binds the saved queued action; `future_entries_active` is `UNKNOWN` (no control record) |

## Independently calculated values

- `signal_open_position`: entry intent `act-0001` acquires `100000000` base units (6 decimals) for
  `50000000000000000000` quote units (`0x1111…1111`, 18 decimals). The position
  `ag-health-01:stg-health:dec-0001` holds `inventory_raw 100000000`, `cost_basis_raw
  50000000000000000000`, `realized_raw 0`. The deposit `flow-0001` is `50000000000000000000` quote
  units, a capital flow. Receipt `rcpt-0001`: `150000 × 2000000000 = 300000000000000` native MON.
- `stop_sticky_after_restart`: entry intent `act-0007` acquires `25000000` base units for
  `12500000000000000000` quote units; the position holds `inventory_raw 25000000`, `cost_basis_raw
  12500000000000000000`, `realized_raw 0`. This is a supported confirmed entry, not a partial exit.
  Timeline: decision `dec-0007` `21:23`, intent `act-0007` `21:24`, attempt `sub-0007` `21:25→21:27`,
  receipt `rcpt-0007` `21:27` (`75000 × 2000000000 = 150000000000000` gas), stop `stop-0007`
  `created_at 21:29`, removal `rmv-0007` `updated_at 21:29:30`. `scoped_stops` uses `created_at`;
  `admission_positions` is `DERIVED`.
- `no_signal`: no `admission_positions` row exists, so basis, realized and residual are `UNKNOWN`, not
  `0`. The saved `dec-0002` decision is listed and summarized.
- `repeated_preview_same_action`: a QUEUED action gives an `ENQUEUED` job (`execution/worker.py:410-414`).
  `job-0009` is `ENQUEUED` at `21:44:10`; `act-0009` is `QUEUED` (intent `21:44:05`, queue `21:44:10`).
  No stop, removal or deployment row exists, so `future_entries_active` is
  `{ "state": "UNKNOWN", "reason": "NO_CONTROL_RECORD" }`, never `false`.
- `context_corrected_disabled_cleared`: each of `ctx-v1`..`ctx-v4` is cited in `record_refs` and
  carries its `entries` payload. `entries_count` equals the listed entry count (2, 2, 2, 0). A task
  retrieves only ADOPTED entries while the state is ACTIVE (`agent_context/controls.py:261-278`):
  v1 retrieves `preference-1`, v2 retrieves the corrected `preference-1`, and v3 (DISABLED) and v4
  (CLEARED) retrieve none. The correction changes the adopted text and kind; `lesson-1` stays
  SUGGESTED, so it is not retrieved. The write path creates only `AgentContextRecord` rows
  (`controls.py:134-174`), so no financial state changes; that claim names its source basis.

## Event ordering and expired scope

- Decisions are saved before an intent, and the intent before any submission (IC02). An admitted
  action with a QUEUED queue row leaves the job `ENQUEUED`, not `COMPLETED` (`execution/worker.py:410-414`);
  a job is `COMPLETED` only after an unsent release or a terminal queue outcome (`worker.py:539-563`).
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
action (no-signal). An `action_id` exists only after evaluation admits and enqueues an action.

## Direct and conversation agreement

For each case the direct projection and the conversation summary must agree exactly.
`stop_sticky_after_restart` has `as_of` `2026-10-12T21:29:30Z`, the newest `DIRECT` row time
(`removal_states.updated_at`), never the read time. The owner-B case has no stored row, so its `as_of`
is `null`, not a read time.

## What these cases do not prove

- No provider, chain, signer, model, host or browser ran.
- No financial effect was simulated.
- The preview cases are contract examples; they are not chat runtime proof.
- Partial exits, additions and manual close stay unavailable; the examples use only confirmed entries
  and queued actions. Autonomy, scheduling, standing permission and forward feeds stay `MISSING` until
  P27 implements them.
