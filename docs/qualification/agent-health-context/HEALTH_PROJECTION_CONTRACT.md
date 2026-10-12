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

## 2. Scope identity: `scope`

The owner is the verified principal (`Principal.user_id`). No request body, query, navigation
target or conversation turn can set or retarget it. This reuses the accepted boundary in
`core/authentication.py` and the `owner_id`-only reads in `accounts/views.py`.

| Field | Source | Status |
|---|---|---|
| `owner_id` | verified `Principal.user_id` | PRESENT (f84) |
| `agent_id`, `wallet_id`, `network_id` | `execution_local.execution_evaluation_jobs`, `funding_local.funding_profiles`, `admission_local.admission_positions` | PRESENT (f84) |
| `strategy_id`, `publication_revision_id`, `execution_revision_id` | `execution_local.execution_evaluation_jobs` (IC01) | PRESENT (f84) |
| `content_hash`, `manifest_hash` | `execution_local.execution_evaluation_jobs` | PRESENT (f84) |
| `consent_adoption_id`, `consent_hash` | `execution_local.execution_evaluation_jobs` | PRESENT (f84) |
| `network_id` treatment | network prefix on asset ids (`docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`, IC01) | PRESENT (f84) |
| `deployment_id` | no deployment identity column exists | MISSING (P27 producer obligation) |

A record scope is exact. Two positions that hold the same token but differ in agent, wallet or
network stay separate. A conversation attaches one record identity; it cannot silently widen that
scope to a sibling record or another owner.

## 3. Worker health: `worker_health`

Worker health answers: what did the worker try, what did it finish, with which inputs, what is
next, why did it wait or fault, what needs reconciliation, and what stops or removals apply.

| Field | Source | Status |
|---|---|---|
| `last_attempt_at` | newest `execution_local.execution_evaluation_jobs.updated_at` for the scope | PRESENT (f84) |
| `last_completion_at` | newest `updated_at` where `state = 'COMPLETED'` | PRESENT (f84) |
| `last_outcome` | the newest job `outcome` and `reason` | PRESENT (f84) |
| `evaluation_attempts` | count of jobs for the scope (projected today as `evaluation_attempts`) | PRESENT (f84) |
| `evaluation_completions` | count where `state = 'COMPLETED'` | PRESENT (f84) |
| `latest_input_updated_at` | `execution_evaluation_jobs.provenance.observations` holds observation times, but no canonical input-time field is projected | MISSING (producer obligation) |
| `input_event_time`, `collection_time` | IC02 supplies observation provenance; no normalised field exists | MISSING (P27 producer obligation) |
| `next_scheduled_work` | no scheduler table exists; `accounts/service_projection.py` sets `next_work` only for a pending reconciliation | MISSING (P27 producer obligation) |
| `wait_or_fault_reason` | job `reason`, including `WAITING:<PORT>_UNAVAILABLE`, `WORKER_ERROR:<class>`, `OBSERVATIONS_WRONG_MARKET`, `OBSERVATIONS_WRONG_TIME`, `IDENTITY_CHANGED`, `IDENTITY_UNAVAILABLE`, `CONSENT_CHANGED` | PRESENT (f84) |
| `pending_reconciliation` | `recovery_local.recovery_cases.state IN ('OPEN','UNKNOWN')` for the action, and `outcome = 'SUBMITTED_UNKNOWN'` | PRESENT (f84) |
| `stop_state` | `stops_local.scoped_stops` (P25); read today by admission, not yet projected | PRESENT (f84) / projection PROPOSED |
| `removal_state` | `revocation_local.removal_states.state` (P30) | PRESENT (f84) |
| `residual_inventory` | `admission_local.admission_positions.inventory` | PRESENT (f84) |
| `dataset_qualification` | `research_local.history_datasets` verdict (QUALIFIED/LIMITED/UNRESOLVED) | MISSING as a health field (producer obligation) |

Invariant: a process label, heartbeat or liveness signal alone cannot fill worker health. Health
requires the saved evaluation attempt, completion, next-work or wait reason and the pending
reconciliation. A settled agent with no scheduler row is `UNKNOWN`, not `RUNNING`, exactly as
`accounts/service_projection.py` already reports it.

## 4. Trading results: `trading_results`

Trading results answer: what did this agent's positions gain or lose, and what capital flowed in.

| Field | Source | Status |
|---|---|---|
| `realized_result` | `admission_local.admission_positions.realized_quote` (`KNOWN` with amount) | PRESENT (f84) |
| `basis` | `admission_positions.cost_basis` (`KNOWN` with amount) | PRESENT (f84) |
| `estimated_unrealized_result` | no observed mark exists; stays `UNKNOWN` | PRESENT (f84) as UNKNOWN |
| `mark` | no mark source exists; stays `UNKNOWN` | PRESENT (f84) as UNKNOWN |
| `native_gas` | funding profile gas asset and `admission_local.admission_receipts` actual gas; kept separate from the reported unit | PRESENT (f84) |
| `deposits` / `withdrawals` | `funding_local.funding_flows` and `funding_credits`; `included_in_realized_result = false` | PRESENT (f84) |
| `provider_mode` | `core/settings.py` `execution_mode` (`fixture`/`unavailable`) | PRESENT (f84) |

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
| `edge_revision` | an `AccountViewRecord` of kind `EDGE_EVIDENCE` in `records` | PRESENT (f84) as SYNTHETIC_AUTHORED only |
| `edge_evidence_status` | same record: `HYPOTHESIS`/`DESCRIPTIVE_ONLY`/`UNRESOLVED`/`SUPPORTED`/`CONFLICTED` | PRESENT (f84) |
| revision-linked real findings | `records.investigation_declarations`, `effect_reports`, `spot_replay_runs` hold findings but are not projected as edge evidence | MISSING (P27/P31 producer obligation) |

Invariants:

- Positive account results alone do not establish a repeatable edge.
- Edge evidence status cannot grant or remove financial permission by itself.
- Edge evidence is revision-linked. It never borrows another revision's status.

## 6. Record references: `record_refs`

Each projected value carries a canonical reference rather than duplicated data:

```text
record_refs[] = { kind, table, id, updated_at }
```

The conversation and direct view quote the same `record_refs` identity. One canonical projection
reference is enough; the agreement must not repeat the same saved value in several places.

## 7. Unknown, stale and unavailable rules

- `as_of` is the newest stored `updated_at` among the referenced rows. The read clock never becomes
  an `as_of` value. `accounts/service_projection.py` already follows this rule.
- A missing row is `UNKNOWN` with a reason, never a fabricated value and never zero.
- A stale input or a fresh-record override is explicit: current financial records override a stale
  conversation context (`docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md`, "Account
  questions and exact context"; MEM-Q04).
- The projection names one evidence class. Fixture ports produce `SERVICE_PROJECTION` over authored
  ports and say so; production leaves the ports `UNAVAILABLE`.

## 8. Owner control and conversation interaction

- The authenticated owner controls lookup. A navigation target, an attached record or a conversation
  turn cannot retarget a saved task context to another owner, agent or wallet.
- Clearing or disabling P19 memory (`agent_context/controls.py`, `clear_context`/`disable_context`)
  omits the memory entries from later tasks. It keeps every required owner, safety and permission
  state. The financial records are unchanged.
- Memory never grants authority, changes adopted rules or changes the schedule.

## 9. Consumer interface

A frozen P31 health consumer reads the producer snapshot. It:

- reads only, and returns the same values, sources and unknowns as the producer;
- cannot calculate a schedule, a profit, a new action or a percentage return;
- runs no second engine and holds no financial cursor;
- names the producer revision and `as_of` with every answer.

## 10. Out of scope for this agreement

No producer is implemented here. `next_scheduled_work`, `deployment_id`, normalised input/collection
times and revision-linked real edge evidence remain `MISSING`. Full P27 recurring operation, manual
sale P32 and every unqualified operation stay separate and OPEN.
