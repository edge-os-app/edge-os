# Delayed history replay profile

`edge-os.delayed-history-replay/1` is an additive timing profile for the pure spot replay in `apps/api/src/edge_os_api/replay/simulator.py`. It models a decision made 300 seconds after each source bucket ends and a hypothetical fill at the next bucket's stale historical close. It does not change `ReplayInput`, the default `p12.spot-replay/1` profile, or any application caller.

## Interface

```python
run_spot_replay(strategy, run, *, timing_profile="p12.spot-replay/1") -> ReplayResult
```

`timing_profile` accepts exactly `"p12.spot-replay/1"` (the default) or `"edge-os.delayed-history-replay/1"`. Any other value, including a non-string, raises `ReplayError` with code `UNSUPPORTED_TIMING_PROFILE` and path `/timing_profile`. The delay is not configurable.

The fixed policy lives in `apps/api/src/edge_os_api/replay/delayed_history_profile.py`:

```python
{
    "schema_version": "edge-os.delayed-history-replay/1",
    "decision_delay_seconds": 300,
    "fill_rule": "NEXT_BUCKET_DELAYED_CLOSE",
    "fill_label": "Hypothetical stale historical close",
}
```

## Semantics

For source index `i`, the decision time is `D_i = bucket_end_i + 300 seconds`.

- Decisions use source indexes with `window_start <= D_i < window_end`. The first selected source must have `D_i == window_start`; otherwise the run fails with `DATASET_COVERAGE_UNPROVEN`. The legacy first index is never reused.
- Warm-up is checked against the first delayed source index. A strategy that passes legacy warm-up with one fewer prior bucket fails here.
- All legacy dataset checks still apply, including complete source coverage of the half-open window, qualification, market binding, schedule, empty-bucket and numeric rules. The final in-window source bucket therefore stays required even though its `D_i` equals the exclusive end and it produces no decision.
- Expressions, essential bindings and every primitive observation used by either Boolean branch are evaluated at `D_i`. An observation available exactly at `D_i` passes; one microsecond later is `LATE_INPUT` or `FUTURE_INFORMATION`; unknown availability blocks.
- An order signalled at `i` settles only against source `i+1` at `D_(i+1)`, using that bucket's qualified close available by `D_(i+1)` with the saved fee and slippage. A late, unknown, unqualified or empty next close produces one `FILL_UNAVAILABLE` event and releases the reservation once. No earlier or later close, retry, extra bucket or window extension replaces it. A signal at the last selected index records `NO_NEXT_BUCKET`.
- Samples, decisions, reservations, fills, trades and open-position marks use the delayed clock in `at`, `entry_at`, `exit_at`, `fill_at` and `last_mark_at`.

## Provenance fields

Delayed output adds keys; default output adds none.

| Record | Added keys |
|---|---|
| Sample | `source_bucket_end`, `timing_profile` |
| `DECISION` event and order events raised by a decision | `signal_at`, `source_bucket_end`, `timing_profile` |
| `BUY_FILLED`, `SELL_FILLED`, `FILL_UNAVAILABLE` | `signal_at`, `fill_at`, `available_at` (of the fill close), `fill_rule`, `fill_label`, `source_bucket_end` (the fill bucket), `timing_profile` |
| Trade | `timing_profile`, `fill_label` |

`ReplayResult.evidence_class` remains the dataset's own evidence class. The `fill_label` is a separate hypothetical-fill claim. A stale close is never labelled an executable quote, and no field grants trading authority.

## Fingerprint

The default profile fingerprint is unchanged byte for byte. The delayed fingerprint uses `profile_version: "edge-os.delayed-history-replay/1"` and adds `timing_policy` with the complete policy above, so the two profiles never share a `repeatability_id` for the same input.

## Example

Window `[10:00, 10:20)` UTC, source closes at 09:55, 10:00, 10:05, 10:10 and 10:15 of `8, 8, 12, 12, 100`, each available exactly at `bucket_end + 300 s`. Entry `price > 7`, exit `price >= 9`, size 400 quote, fee 0.001, slippage 0.25, starting cash 1000.

| `at` | Source | Result |
|---|---|---|
| 10:00 | 09:55 | Entry true; reserve 400.4 quote, `fill_at` 10:05 |
| 10:05 | 10:00 | Buy at 8 × 1.25 = 10; 40 base; fee 0.4; cash 599.6 |
| 10:10 | 10:05 | Exit true; reserve 40 base, `fill_at` 10:15 |
| 10:15 | 10:10 | Sell at 12 × 0.75 = 9; gross 360; fee 0.36; cash 959.24; then entry `NO_NEXT_BUCKET` |

The 10:15 source decides at the exclusive end and is excluded. Gain/loss is −40.76 quote, one completed pair and largest drawdown 120.36. With a four-bucket tuple and a three-decision window, possible outcomes range from zero fills to one round trip.

## Verification

`apps/api/tests/test_delayed_history_replay.py` covers the example arithmetic, availability equality, one-microsecond late and unknown refusal, a hidden Boolean branch, lag warm-up and the shifted first index, missing first-decision coverage, an empty or unavailable next close with one release and no substitution, the exclusive end, unknown profiles, fingerprint separation and policy binding, the unchanged default fingerprint and the four-bucket outcome set. `apps/api/tests/test_spot_replay.py` remains the unchanged P12 oracle.

## Lane 2 wiring and limits

`SpotReplayBody.timing_profile` is optional. It accepts `p12.spot-replay/1` or `edge-os.delayed-history-replay/1`. An omitted value and an explicit default share the original request fingerprint, the saved configuration identity and the output. An unknown or non-string value is refused with `UNSUPPORTED_TIMING_PROFILE` at `/timing_profile` before anything is saved.

A delayed run saves `timing_profile` and `timing_policy` inside `inputs`. The saved configuration identity and the record therefore carry the profile. A repeated idempotency key with a different profile is a conflict. The same `run_configuration_id` with a different profile is the existing configuration conflict. `GET /v1/spot-replays/{replay_id}` returns the saved profile and policy unchanged after an API restart. The delayed run passes the same protected-partition refusal as the default run.

The web control offers the delayed option and preselects the default. For the authored fixture the control starts the window at 12:10, one bucket later than the default, so the first delayed decision keeps its full warm-up. For a saved dataset the window comes from the existing history source control. The panel and the saved result show `Delayed hypothetical replay (300 s decision delay)` and each fill's `fill_label`. The result shows `FILL_UNAVAILABLE` and `NO_NEXT_BUCKET` as recorded order events, not as failures of the run.

This wiring still does not qualify real data, prove fills or costs, or grant execution permission.
