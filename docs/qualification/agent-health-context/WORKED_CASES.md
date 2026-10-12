# Worked health and context cases (P31 preparation)

Machine-readable fixtures: [worked_health_cases.json](worked_health_cases.json).
Base `f84ef415278196db2c8bba73eaa154a1ef00748b`, projection `edge-os.agent-health-projection/1`.

These are independently worked, unsigned contract examples. They contain no real data, no signing,
no broadcast and no provider effect. They are reviewable contract checks, not runtime, browser or
chat proof. `NOT_RUN`: no runtime check was performed.

## Method

Each case pins the exact stored rows (`table`, `id`, `updated_at`), the schema version, the evidence
class and `as_of`. The expected **direct projection** is the canonical object. The expected
**conversation summary** renders from that object and must agree with it on exact values, sources and
unknowns. The summary states no value the projection does not hold.

The agreement is checked on three axes:

| Axis | Check |
|---|---|
| `values_agree` | every number, state and timestamp in the summary equals the projection |
| `sources_agree` | every statement names the same `record_refs` identity the projection names |
| `unknowns_agree` | every `UNKNOWN` stays `UNKNOWN` in both; a summary never turns an unknown into zero |

Data is not duplicated: the summary names `renders_from: expected_direct_projection`, so one
canonical object per case is enough.

## Cases

| Case | Requirement covered | Verdict on the contract |
|---|---|---|
| `signal_open_position` | signal, one position, known realized result | health and results stay separate; unrealized and mark unknown |
| `no_signal` | no-signal is useful work | no action; realized 0 is a fact, not a loss of permission |
| `stale_input` | stale input | reason `STALE_CONTEXT`; unknown stays unknown |
| `missing_input_wrong_market` | missing/wrong input | `OBSERVATIONS_WRONG_MARKET`; no decision |
| `wait_provider_unavailable` | fault/wait | `WAITING:MARKET_UNAVAILABLE`; the saved action stays |
| `pending_unknown_original` | pending unknown original transaction | `pending_reconciliation = true`; exact original identity kept |
| `stop_sticky_after_restart` | stop/removal sticky after restart | `HALT_ALL_SWAPS` + `CONFIRMED` removal deny; residual inventory shown |
| `owner_b_navigation_retarget_denied` | owner B / target navigation | `404`, no provider call, no retarget |
| `context_corrected_disabled_cleared` | stale vs corrected/disabled/cleared context | versions 1-4; no financial record changes |
| `repeated_preview_same_action` | repeated preview | same `action_id`; `Idempotent-Replay` |

## Independently calculated values

The worked numbers are small and exact, so a reviewer can recompute them.

- `signal_open_position`: entry sells `100000000` base units (6 decimals) of
  `0x2222...2222` for `50000000000000000000` quote units (18 decimals) of `0x1111...1111`.
  The realized result is `1250000000000000000` quote units. Basis is
  `50000000000000000000`. The exit at nonce 1 is a separate original transaction.
- `stop_sticky_after_restart`: residual inventory is `25000000` base units after a confirmed
  partial exit. Realized result is `-500000000000000000` quote units; the negative sign is retained,
  never shown as zero.
- Native gas in `signal_open_position` is `300000000000000` MON (`150000 x 2000000000`), kept in a
  separate field from the quote result.

## Event ordering and expired scope

- Decisions are saved before an intent, and the intent before any submission (IC02). The summary
  reads states in that order: QUEUED → DECIDED → ENQUEUED → SUBMITTED/COMPLETED.
- An expired intent or an expired mandate keeps the original refused before signing as
  `DEFINITELY_UNSENT`; after signing it stays unknown and no broadcast runs (USER_RELEASE_INTEGRATION_PROFILE,
  "Outcomes").
- The decision slot is the latest five-minute UTC grid point at scheduling. A decision for another
  slot is `OBSERVATIONS_WRONG_TIME`; observations for another market are
  `OBSERVATIONS_WRONG_MARKET`.
- A control (stop or removal) that commits before the admission/submission transition denies the
  transition. A control that commits after ownership does not undo an in-flight original action; it
  stays recoverable (`revocation/enforcement.py`).

## Original pending identity

`pending_unknown_original` keeps the exact `action_id` (`act-0006`) and its recovery-case identity.
Reconciliation reads one receipt for that exact action, wallet and network. The system never
constructs a replacement action, and a repeated request finds the same action
(`execution/evaluation job` unique per `(owner, agent, adopted consent, decision slot)` and
`(owner, agent, request_key)`).

## Direct and conversation agreement

For each case the direct projection and the conversation summary must agree exactly. `stop_sticky_after_restart`
has `as_of` `2026-10-12T21:29:30Z`, the newest stored `updated_at`, never the read time. The
conversation must show the same `as_of`, the same residual inventory and the same unknown states.

## What these cases do not prove

- No provider, chain, signer, model, host or browser ran.
- No financial effect was simulated.
- The preview cases are contract examples; they are not chat runtime proof.
- Autonomy, scheduling, standing permission and forward feeds stay `MISSING` until P27 implements
  them.
