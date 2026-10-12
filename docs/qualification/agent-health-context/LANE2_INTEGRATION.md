# Lane 2 integration note (P31 preparation)

Base `f84ef415278196db2c8bba73eaa154a1ef00748b`. This note names the producer/consumer handshake and
the checks still required before any P31 source implementation or P27 consumer acceptance. It
implements nothing and agrees nothing by itself.

## 1. Proposed split

| Side | Responsibility | Status |
|---|---|---|
| Producer | P27 (lane 2) owns the recurring scheduler, the standing permission and the durable health facts, and exposes one read-only projection `edge-os.agent-health-projection/1` | PROPOSED (not implemented) |
| Consumer | P31 owns one read-only adapter that reads the producer snapshot and answers direct and conversation questions with the same values, sources and unknowns | PROPOSED (not implemented) |

The producer stays the only source of schedule, attempts, completions, wait reasons and pending
reconciliation. The consumer computes no schedule, profit, percentage return or new action, and runs
no second engine. This keeps one canonical reference instead of duplicated data.

## 2. Dependency handshake

1. P27 freezes the supported operating profile and the projection version before P31 consumes it
   (controller-workspace plan `docs/superpowers/plans/2026-10-12-public-user-release.md`, Task 7;
   AUT01-AUT08).
2. P27 records the exact projection route, schema version and evidence class, and the stored
   `updated_at` rule for `as_of`.
3. P31 reads that route read-only. It never writes producer tables and never recalculates a producer
   value.
4. A change to the projection version or to the `as_of` rule needs a new agreement revision before a
   consumer depends on it.

P31 remains a P27 dependency. Documentation does not satisfy AUT06 and does not complete P27 or P31.

## 3. Cross-lane choice to agree

Before a P31 adapter is implemented, the lane-2 owner must agree these points. They are a draft
request, not an adopted decision. A draft response is not automatically adopted.

- The exact projection route and record identity (`/v1/agent-health` shape is a proposal).
- Whether the projection reuses the existing `SERVICE_PROJECTION` evidence class or adds a distinct
  health class.
- The exact normalised input/collection time fields (today only `provenance.observations` holds raw
  times).
- The `next_scheduled_work` representation and the catch-up policy (AUT01).
- The `deployment_id` identity and how it maps to `publication_revision_id` (the purpose label is not
  the trial label; a purpose change does not reset accounting).
- Whether the health projection is one record per agent or one row per agent/wallet/network.

This request goes to the controller as a frozen draft. No lane-2 or lane-1 profile is edited
here, and no draft reply is assumed adopted.

## 4. Next separately owned read-only P31 surfaces

These surfaces are proposed for a later, separately assigned P31 lease. They are not built here.

- A read-only health-projection adapter over the producer route.
- A conversation context attachment that reads the exact saved record and returns the same `as_of`
  and `record_refs`.
- A shared-preview reader that binds one `action_id` and shows the same states as the direct view.
- Focused contract tests that compare the direct projection with the conversation summary on one
  candidate.

## 5. Required mounted checks before acceptance

The current certificate is `NOT_RUN` for every runtime check. A later milestone must mount and run:

| Check | What it proves |
|---|---|
| MEM-Q02-MEM-Q05 | correction retrieval, isolation, authority, owner control against real integrated tools |
| WAL-Q26 | two channels read the same agent/wallet/position/action records; A's preview cannot retarget B |
| AUT06 | direct views and P31 conversation reference the same deployment, attempt/completion, input times, next work, wait/fault reason and pending reconciliation; restart-sticky stop/removal; residual inventory; retained owner access |
| API | the projection route and the context/preview routes, owner-scoped |
| UI | the health and context surfaces render the same values as the API |
| SQL | the projection reads the exact saved rows and writes nothing |
| restart | stop, removal, pending reconciliation and versions survive a restart |
| two owners | no cross-owner read, change, retarget or provider call |

A heartbeat, a single queued job or a fixture pass cannot substitute for these checks.

## 6. Retained limits

- No real model, provider, host or chain is qualified by this milestone.
- `execution_mode` stays `unavailable` in production; fixture ports are authored test providers, not
  chain evidence (`core/settings.py`).
- Live health, live chat and an always-on worker are not proved.
- Manual sale (P32), partial exits/additions, unqualified liquidation and withdrawal stay
  unavailable.

## 7. Freeze rule

P31 source implementation and P27 consumer acceptance wait until the lane-2 owner freezes a final
compatible contract for the projection and the choice points in section 3. Until then these
documents are a preparation baseline, not an accepted interface.
