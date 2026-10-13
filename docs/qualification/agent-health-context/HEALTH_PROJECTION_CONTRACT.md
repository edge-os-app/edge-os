# Agent health projection contract (P31 preparation)

Agreement `edge-os.agent-health-projection/1`, PROPOSED. Base `f84ef415278196db2c8bba73eaa154a1ef00748b`.

This is one versioned read-only projection. Direct agent views and the P31 conversation read the
same projection. It writes nothing and owns no ledger. Every field below maps to an accepted
caller, table or record at the base commit, or is marked `MISSING`/`PROPOSED` with a producer
obligation. `NOT_RUN`: no runtime, provider, model or host check supports this milestone.

## 1. Version and envelope

A projection record has this shape. Field names shown in `code` are exact.

```text
AgentHealthProjection
  schema_version        "edge-os.agent-health-projection/1"     PROPOSED
  record_type           "AgentHealthProjection"                 PROPOSED
  record_id             "health:{owner_id}:{agent_id}:{wallet_id}:{network_id}"
  source                the producer route, table and updated_at
  as_of                 the newest stored updated_at across the named rows; never the read clock
  notice                a plain-language evidence-class note
  scope                 section 2
  worker_health         section 3
  trading_results       section 4
  edge_evidence         section 5
  record_refs           section 6
```

`evidence_class` is `SERVICE_PROJECTION`, the same label `accounts/service_projection.py` already
uses for read-only projections of connected rows. It is not `SYNTHETIC_AUTHORED`. The projection
is never stored as an account record.

A worked case may carry only the sections it demonstrates. A section that is absent means "not
applicable in this case", not an empty value. The `context` section (section 8) appears only in a
context case and does not change the meaning of a missing `worker_health` or `trading_results`.

## 2. Scope identity: `scope`

The owner is the verified principal (`Principal.user_id`). No request body, query, navigation
target or conversation turn can set or retarget it. This reuses the accepted boundary in
`core/authentication.py` and the `owner_id`-only reads in `accounts/views.py`.

The projection scope binds the saved evaluation-job identity, not the current resolution. The saved
job scope is exposed through the agent route's `jobs` array (`job_view`, `execution/worker.py:95-105`;
`execution/routes.py:100`); the current connected identity is a separate route value.

| Field | Source | Status |
|---|---|---|
| `scope.owner_id` | verified `Principal.user_id` | EXPOSED (f84) |
| `scope.agent_id`, `scope.wallet_id`, `scope.network_id` | saved job columns `execution_local.execution_evaluation_jobs` (`execution/models.py:214-216`); the account projection groups by them (`accounts/service_projection.py:162-177`) | EXPOSED (f84) |
| `scope.strategy_id`, `scope.publication_revision_id`, `scope.execution_revision_id`, `scope.content_hash`, `scope.consent_adoption_id`, `scope.consent_hash` | saved job columns (`execution/models.py:219-225`), serialized by `job_view` (`execution/worker.py:95-105`), exposed at `execution/routes.py:100` | EXPOSED (f84) as the saved job scope |
| `scope.manifest_hash` (direct column) | saved job column (`execution/models.py:223`); `job_view` omits the direct key | STORED INPUT / PROPOSED (lane2). `job_view` exposes `provenance.identity.manifest_sha256` (saved by `schedule`, `execution/worker.py:141`), which is the schedule-time nested digest, not the direct column; its representation may differ. |
| `current_connected_identity` (agent/wallet/network, strategy, publication/execution revision, content/manifest digest) | `ConnectedAgent.identity()` (`execution/connected_identity.py:72-77`), exposed at `execution/routes.py:99` | EXPOSED (f84), the CURRENT resolution |
| `deployment_id` | no deployment identity column exists | MISSING (P27 producer obligation) |
| `network_id` treatment | network prefix on asset ids (`docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`, IC01); descriptive | descriptive |

`resolve_agent` builds `ConnectedAgent` from the current wallet setup and the current `StrategyRevision`
(`execution/connected_identity.py:100-128`). So `current_connected_identity` is the current resolution;
it is distinct from a saved job's historical scope, which comes from the job row's own columns. The
projection's job scope uses the saved job columns and must equal the intent and decision identities
(IC01), never the current resolution. Do not assume equality across revisions. Digest representation
also differs: the saved job's `content_hash` is a job column, while the current identity's
`content_sha256` is the same underlying digest under a different name and possibly a different prefix;
do not treat one as byte-identical to the other without a stated normalization.

A record scope is exact. Two positions that hold the same token but differ in agent, wallet or
network stay separate. A conversation attaches one record identity; it cannot silently widen that
scope to a sibling record or another owner.

## 3. Worker health: `worker_health`

Worker health answers: what did the worker try, what did it finish, with which inputs, what is
next, why did it wait or fault, what needs reconciliation, and what stops or removals apply.

Worker health mixes two different clocks. Evaluation health is the bounded decision pipeline; it is
not submission health. The projection keeps them as separate fields with separate producers, so a
no-signal evaluation is never reported as a completed trade attempt.

Status vocabulary (used across this contract and `SOURCE_RECORD_MAP.md`):

- `EXPOSED (f84)`: the accepted account projection (`accounts/service_projection.py`) or the route
  (`execution/routes.py`) outputs this value today.
- `SERVICE VALUE (f84)`: an accepted service computes it, but no accepted read surface exposes it yet.
  Name the exact computing service, for example `ExecutionService.status` for the submission values.
- `STORED INPUT`: a stored column exists, but no projection outputs it today.
- `PROPOSED (lane2)`: a derived projection field the lane2 P27 producer must expose.
- `MISSING`: no producer exists.

**Evaluation-level fields** (producer `execution_local.execution_evaluation_jobs`):

| Field | Source | Status |
|---|---|---|
| `last_evaluation_activity_at` | `execution_evaluation_jobs.updated_at` | EXPOSED (f84): aggregate at `service_projection.py:173`; raw per-job at `job_view` (`execution/worker.py:95-106`) |
| `evaluation_attempts` | count of evaluation-job rows for the scope | EXPOSED (f84) (`service_projection.py:174`) |
| `evaluation_completions` | count where `state = 'COMPLETED'` | EXPOSED (f84) (`service_projection.py:175`) |
| `last_evaluation_completion_at` | newest `updated_at` where `state = 'COMPLETED'` | STORED INPUT / PROPOSED (lane2): no direct completion key exists; `job_view` exposes only `updated_at` |
| `last_evaluation_outcome` | newest job `outcome`; `null` until an outcome is saved | raw job `outcome` EXPOSED per-job via `job_view` (`execution/worker.py:95-106`, route `execution/routes.py:100`); the selected health field is PROPOSED (lane2) |
| `last_evaluation_state` | newest job `state` (`execution/models.py:226`); carries the truthful status such as `ENQUEUED` | raw job `state` EXPOSED per-job via `job_view`; the selected health field is PROPOSED (lane2) |
| `wait_or_fault_reason` | newest job `reason` | raw job `reason` EXPOSED per-job via `job_view`; the selected health field is PROPOSED (lane2) |

`last_evaluation_outcome` and `last_evaluation_state` are separate. A job state is never reported as an
outcome. The route's `jobs` array exposes the raw per-job `state`, `outcome` and `reason`; the health
projection's selected, exact-job field is still PROPOSED and needs its selection rule and consumer
agreement. An exposed raw per-job input is not the same as the proposed aggregate.

**Submission-level fields** (producer `SubmissionAttemptRow` via `ExecutionService.status`,
`execution/types.py:321-332`, `execution/service.py:828-870`):

| Field | Source | Status |
|---|---|---|
| `last_submission_attempt_at` | `HealthView.last_attempt_at` = the last `SubmissionAttemptRow.started_at` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `last_submission_completion_at` | `HealthView.last_completion_at` = `max(attempt.completed_at)` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `last_decision_input_at` | `HealthView.last_input_at` = the last decision time; the one normalised input time | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `last_decision_id` | `HealthView.last_decision_id` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `next_scheduled_at` | `HealthView.next_scheduled_at` = last decision + 5 minutes, a bounded-pipeline estimate; no recurring scheduler exists | EXPOSED (f84) at `GET /v1/agents/{agent_id}/actions` (`execution/routes.py:106`) / recurring schedule MISSING (P27) |
| `submission_blocking_reason` | `HealthView.blocking_reason` | EXPOSED (f84) at the same route (`execution/routes.py:106`) |

**Other fields:**

| Field | Source | Status |
|---|---|---|
| `input_event_time`, `collection_time` | `last_decision_input_at` gives the decision time; IC02 observation provenance holds raw per-observation times; a normalised collection time does not exist | SERVICE VALUE (f84) decision time / collection time MISSING (P27) |
| `pending_reconciliation` | `recovery_local.recovery_cases.state IN ('OPEN','UNKNOWN')` for the action, and job `outcome = 'SUBMITTED_UNKNOWN'` | EXPOSED (f84) (`service_projection.py:176`) |
| `stop_state` | `stops_local.scoped_stops` (P25); read by admission, not projected | STORED INPUT / PROPOSED (lane2) |
| `removal_state` | `revocation_local.removal_states.state` (P30) | EXPOSED (f84) within the AGENT projection (`service_projection.py:79-91`) |
| `control_state_basis` | names the source of `stop_state` and `removal_state`: the listed stop/removal rows, or the empty P25/P30 reader result when no row exists (`revocation/enforcement.py:80-86`) | PROPOSED |
| `residual_inventory` | `admission_local.admission_positions.inventory` | EXPOSED (f84) as the POSITION quantity (`service_projection.py:126-141`) |
| `dataset_qualification` | `research_local.history_datasets` verdict (QUALIFIED/LIMITED/UNRESOLVED) | MISSING (producer obligation) |

Invariant: a process label, heartbeat or liveness signal alone cannot fill worker health. Health
requires the saved evaluation attempt, completion, next-work or wait reason and the pending
reconciliation. A settled agent with no scheduler row is `UNKNOWN`, not `RUNNING`, exactly as
`accounts/service_projection.py` already reports it.

A consequential status or boolean (`stop_state`, `removal_state`, `pending_reconciliation`,
`future_entries_active`) is `KNOWN` only with a named source. Without a source it is an explicit
`UNKNOWN` with a reason, never `false` or `NONE`. `control_state_basis` names the source of the
stop and removal state.

`ExecutionService.status` (`execution/service.py:828-870`) already computes `HealthView`
(`execution/types.py:321-332`) over owner-scoped rows: the two submission timestamps from
`SubmissionAttemptRow`, the decision input time and id from `DecisionRow`, and the blocking reason.
The route `GET /v1/agents/{agent_id}/actions` (`execution/routes.py:83-106`) exposes only
`blocking_reason` and `next_scheduled_at` from `HealthView`; its other fields need a read surface
(projection PROPOSED). The accepted account projection (`accounts/service_projection.py:162-177`)
exposes the evaluation counts and the last activity time. The raw per-job `state`, `outcome`, `reason`,
scope and `updated_at` are exposed through the agent route's `jobs` array (`job_view`,
`execution/worker.py:95-106`; `execution/routes.py:100`). The health projection's selected completion
time, and its selected outcome/state/wait-reason fields, remain PROPOSED (lane2 obligation) and need
their selection rule and consumer agreement. The projection must keep the evaluation clock and the
submission clock separate; it must not relabel one as the other, and it must not present a job `state`
as an `outcome`. The `MISSING` obligation is the recurring scheduler, its missed-slot policy and a
normalised per-observation collection time; a lane-2 implementer must not invent a second source for a
value an
accepted caller already computes.

## 4. Trading results: `trading_results`

Trading results answer: what did this agent's positions gain or lose, and what capital flowed in.

| Field | Source | Status |
|---|---|---|
| `realized_result` | `admission_local.admission_positions.realized_quote` (`KNOWN` with amount) | EXPOSED (f84) as the POSITION realized result |
| `basis` | `admission_positions.cost_basis` (`KNOWN` with amount) | EXPOSED (f84) as the POSITION basis |
| `estimated_unrealized_result` | no observed mark exists; stays `UNKNOWN` | EXPOSED (f84) as UNKNOWN |
| `mark` | no mark source exists; stays `UNKNOWN` | EXPOSED (f84) as UNKNOWN |
| `native_gas` | per-receipt `actual_gas` is exposed at `GET /v1/actions/{action_id}` (`execution/routes.py:142-143`); the per-agent-wallet aggregate is derived from those receipts and kept separate from the reported unit | per-receipt gas EXPOSED (f84) / aggregate PROPOSED (lane2) |
| `deposits` / `withdrawals` | `funding_local.funding_flows` and `funding_credits`; `included_in_realized_result = false` | EXPOSED (f84) as CAPITAL_FLOW |
| `provider_mode` | `core/settings.py` `execution_mode` (`fixture`/`unavailable`) | EXPOSED (f84) (`execution/routes.py`) |

Invariants:

- Deposits and withdrawals are capital flows. They are never a trading result and never profit.
- Unknown marks, costs, conversions and transaction outcomes stay `UNKNOWN`. They cannot become
  zero. A reconciled raw gain or loss may be shown without an adopted percentage-return,
  account-value or drawdown profile; those metrics stay unavailable until a versioned calculation
  profile is adopted (spec, "Accepted research declaration and agent monitoring handoff").
- Native MON is gas only. Converting it into the reported unit needs a qualified conversion and is
  not asserted here.
- A profit receipt or a single reconciled receipt alone does not establish health.

## 5. Edge evidence: `edge_evidence`

Edge evidence answers: which revision-linked findings, comparisons, contrary results and unresolved
assumptions exist.

| Field | Source | Status |
|---|---|---|
| `edge_revision` | an `AccountViewRecord` of kind `EDGE_EVIDENCE` in `records` | EXPOSED (f84), `SYNTHETIC_AUTHORED` only |
| `edge_evidence_status` | same record: `HYPOTHESIS`/`DESCRIPTIVE_ONLY`/`UNRESOLVED`/`SUPPORTED`/`CONFLICTED` | EXPOSED (f84) |
| revision-linked real findings | `records.investigation_declarations`, `effect_reports`, `spot_replay_runs` hold findings but are not projected as edge evidence | MISSING (P27/P31 producer obligation) |

Invariants:

- Positive account results alone do not establish a repeatable edge.
- Edge evidence status cannot grant or remove financial permission by itself.
- Edge evidence is revision-linked. It never borrows another revision's status.

## 6. Record references: `record_refs`

Each projected value carries a canonical reference rather than duplicated data:

```text
record_refs[] = { kind, table, id, time_field, time }
```

`time_field` names the row's real timestamp column. A position has no timestamp column, so its
`time_field` is `derived` and its time is the latest intent or receipt of the position.

`record_refs` names exact source rows by their own ids. The aggregate projection identity is a separate
field (`projection_ref`, `record_id = health:{owner_id}:{agent_id}:{wallet_id}:{network_id}`), so a
grouped projection reference is never confused with a source-row identity.

The conversation and direct view quote the same `record_refs` identity. One canonical projection
reference is enough; the agreement must not repeat the same saved value in several places.

## 7. Unknown, stale and unavailable rules

- `as_of` is the newest stored row time among the referenced rows. A row that has no timestamp
  column (a position) contributes only a derived time. The read clock never becomes an `as_of` value.
  When no row exists, `as_of` is `null`, never a read time. `accounts/service_projection.py` already
  follows this rule.
- A missing row is `UNKNOWN` with a reason, never a fabricated value and never zero.
- A stale input or a fresh-record override is explicit: current financial records override a stale
  conversation context (`docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md`, "Account
  questions and exact context"; MEM-Q04).
- The projection names one evidence class. Fixture ports produce `SERVICE_PROJECTION` over authored
  ports and say so; production leaves the ports `UNAVAILABLE`.

## 8. Owner control and conversation interaction

- The authenticated owner controls lookup. A navigation target, an attached record or a conversation
  turn cannot retarget a saved task context to another owner, agent or wallet.
- Retrieval returns ADOPTED `context_id`/`text` only while the state is `ACTIVE`; a `DISABLED` or
  `CLEARED` state returns none (`agent_context/controls.py:261-278`). A correction changes the
  adopted text and kind; it does not adopt a suggested lesson.
- Clearing or disabling P19 memory (`clear_context`/`disable_context`) omits the memory entries from
  later tasks. It keeps every required owner, safety and permission state. The P19 write path creates
  only an `AgentContextRecord` row, so no financial record, reservation, pending action or permission
  changes (`agent_context/controls.py:134-174`).
- Memory never grants authority, changes adopted rules or changes the schedule.

## 9. Consumer interface

A frozen P31 health consumer reads the producer snapshot. It:

- reads only, and returns the same values, sources and unknowns as the producer;
- cannot calculate a schedule, a profit, a new action or a percentage return;
- runs no second engine and holds no financial cursor;
- names the producer revision and `as_of` with every answer.

## 10. Out of scope for this agreement

No producer is implemented here. The bounded-pipeline `HealthView` already exists and must be
reused; the recurring scheduler (`next_scheduled_at` for repeated operation), `deployment_id`, a
normalised per-observation collection time and revision-linked real edge evidence remain `MISSING`.
Full P27 recurring operation, manual sale P32 and every unqualified operation stay separate and OPEN.
