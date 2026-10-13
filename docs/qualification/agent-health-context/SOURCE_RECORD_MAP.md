# Source record map (P31 preparation)

Base `f84ef415278196db2c8bba73eaa154a1ef00748b`, tree `91cc55446a6d2dc3672cd153a0bec225a3fed009`.

This map traces every projected field to an accepted caller, table or record at the base commit, or
marks it `MISSING`/`PROPOSED` with a producer obligation. Line numbers refer to the base commit.

## Accepted producers at f84

| Producer | File | Lines |
|---|---|---|
| Evaluation jobs | `apps/api/src/edge_os_api/execution/models.py` | 202-245 |
| Decisions / intents / queue / claims / attempts | `apps/api/src/edge_os_api/execution/models.py` | 50-196 |
| Connected execution (IC01, IC02, IC06) | `execution/connected_identity.py`, `execution/worker.py`, `execution/original_transaction.py` | - |
| Bounded-pipeline health view | `execution/types.py` (`HealthView`), `execution/service.py` (`status`), `execution/routes.py` | 321-332, 828-870, 83-106 |
| Positions / receipts / allowances / decisions | `apps/api/src/edge_os_api/admission/models.py` | 51-178 |
| Funding profiles / flows / credits | `apps/api/src/edge_os_api/funding/persistence.py` | 55-171 |
| Recovery cases / evidence | `apps/api/src/edge_os_api/recovery/models.py` | 51-116 |
| Scoped stops | `apps/api/src/edge_os_api/stops/models.py` | 47-77 |
| Removal requests / states | `apps/api/src/edge_os_api/revocation/records.py` | 53-149 |
| Removal enforcement | `apps/api/src/edge_os_api/revocation/enforcement.py` | 47-86 |
| Consent reviews / adoptions | `apps/api/src/edge_os_api/consent/records.py` | 40-103 |
| Approval derivation (IC05) | `execution/connected_identity.py` | 161-169 |
| P19 memory context | `apps/api/src/edge_os_api/agent_context/controls.py` | 22-285 |
| Account views + projection | `accounts/views.py`, `accounts/service_projection.py` | - |
| Settings / provider mode | `core/settings.py` | 44-75 |

## Worker health fields

Status vocabulary: `EXPOSED (f84)` = the accepted account projection or route outputs it today;
`SERVICE VALUE (f84)` = an accepted service computes it but no read surface exposes it (currently the
`ExecutionService.status` submission values);
`STORED INPUT` = a stored column exists but no projection outputs it; `PROPOSED (lane2)` = the P27
producer must derive and expose it; `MISSING` = no producer.

| Projected field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| `scope.owner_id` | `Principal.user_id` | `core/authentication.py`, `accounts/views.py:273-280` | EXPOSED (f84) |
| `scope.agent_id`, `scope.wallet_id`, `scope.network_id` | saved job columns (`execution/models.py:214-216`); the account projection groups by them | `service_projection.py:162-177` | EXPOSED (f84) |
| `scope.strategy_id`, `scope.publication_revision_id`, `scope.execution_revision_id`, `scope.content_hash`, `scope.consent_adoption_id`, `scope.consent_hash` | saved job columns (`execution/models.py:219-225`), serialized by `job_view` | `execution/worker.py:95-105`; exposed at `execution/routes.py:100` | EXPOSED (f84) as the saved job scope |
| `scope.manifest_hash` (direct column) | saved job column (`execution/models.py:223`); `job_view` omits the direct key | `job_view` exposes `provenance.identity.manifest_sha256` (schedule-time nested digest, `execution/worker.py:141`), not the direct column; representation may differ | direct column STORED INPUT / PROPOSED (lane2); nested digest EXPOSED per-job |
| `current_connected_identity` | `ConnectedAgent.identity()` (`connected_identity.py:72-77`) | exposed at `execution/routes.py:99`; the CURRENT resolution from `resolve_agent` (`connected_identity.py:100-128`), not a saved job's historical scope | EXPOSED (f84) |
| `scope.deployment_id` | no column exists | - | MISSING (P27) |
| `worker_health.last_evaluation_activity_at` | `execution_evaluation_jobs.updated_at` | `service_projection.py:173` | EXPOSED (f84) |
| `worker_health.evaluation_attempts` | count of evaluation-job rows | `service_projection.py:174` | EXPOSED (f84) |
| `worker_health.evaluation_completions` | count where `state='COMPLETED'` | `service_projection.py:175` | EXPOSED (f84) |
| `worker_health.last_evaluation_completion_at` | newest `updated_at` where `state='COMPLETED'` (`execution/models.py:234`) | no exposed caller | STORED INPUT / PROPOSED (lane2) |
| `worker_health.last_evaluation_outcome` | `job.outcome` (nullable, `execution/models.py:229`) | raw `outcome` EXPOSED per-job via `job_view` (`execution/worker.py:95-106`); also read to derive pending reconciliation (`service_projection.py:166`) | raw input EXPOSED per-job / selected health field PROPOSED (lane2) |
| `worker_health.last_evaluation_state` | `job.state` (`execution/models.py:226`) | raw `state` EXPOSED per-job via `job_view` | raw input EXPOSED per-job / selected health field PROPOSED (lane2) |
| `worker_health.wait_or_fault_reason` | `job.reason` (`WAITING:*`, `WORKER_ERROR:*`, `OBSERVATIONS_WRONG_*`, `IDENTITY_*`, `CONSENT_CHANGED`) | raw `reason` EXPOSED per-job via `job_view` | raw input EXPOSED per-job / selected health field PROPOSED (lane2) |
| `worker_health.last_submission_attempt_at` | `HealthView.last_attempt_at` = last `SubmissionAttemptRow.started_at` | `execution/service.py:841-845,864` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `worker_health.last_submission_completion_at` | `HealthView.last_completion_at` = `max(attempt.completed_at)` | `execution/service.py:854,865` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `worker_health.last_decision_input_at` | `HealthView.last_input_at` = last decision time | `execution/service.py:853,866` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `worker_health.last_decision_id` | `HealthView.last_decision_id` | `execution/service.py:867` | SERVICE VALUE (f84) / PROPOSED (read surface) |
| `worker_health.next_scheduled_at` | `HealthView.next_scheduled_at` = last decision + 5 min | `execution/service.py:855-857`; exposed at `execution/routes.py:106` | EXPOSED (f84, route) / recurring MISSING (P27) |
| `worker_health.submission_blocking_reason` | `HealthView.blocking_reason` | `execution/service.py:858-870`; exposed at `execution/routes.py:106` | EXPOSED (f84, route) |
| `worker_health.input_event_time`, `collection_time` | `last_decision_input_at` (decision time); IC02 observation provenance holds raw times | `execution/service.py:866`; `worker.py:285-302` | SERVICE VALUE (f84) decision time / collection time MISSING (P27) |
| `worker_health.pending_reconciliation` | `recovery_cases.state IN ('OPEN','UNKNOWN')` and job `outcome='SUBMITTED_UNKNOWN'` via `UNSETTLED_JOB_OUTCOMES` (`service_projection.py:33,144,159,166,176`) | `service_projection.py` | EXPOSED (f84) |
| `worker_health.stop_state` | `stops_local.scoped_stops` | `stops/service.py`, `revocation/enforcement.py` | STORED INPUT / PROPOSED (lane2) |
| `worker_health.removal_state` | `revocation_local.removal_states.state` | `service_projection.py:79-91` | EXPOSED (f84) via the AGENT projection |
| `worker_health.residual_inventory` | `admission_positions.inventory` | `service_projection.py:126-141` | EXPOSED (f84) as the POSITION quantity |
| `worker_health.dataset_qualification` | `research_local.history_datasets` verdict | `research/history_dataset.py` | MISSING |

## Trading result fields

| Projected field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| `trading_results.realized_result` | `admission_positions.realized_quote` | `service_projection.py:139-140` | EXPOSED (f84) |
| `trading_results.basis` | `admission_positions.cost_basis` | `service_projection.py:137-138` | EXPOSED (f84) |
| `trading_results.estimated_unrealized_result` | no mark source; `UNKNOWN` | `service_projection.py:141` | EXPOSED (f84) as UNKNOWN |
| `trading_results.mark` | no mark source; `UNKNOWN` | `service_projection.py:141` | EXPOSED (f84) as UNKNOWN |
| `trading_results.native_gas` | per-receipt `actual_gas` (`admission/service.py:740-760,998-1003`) exposed at `GET /v1/actions/{action_id}` (`execution/routes.py:142-143`); the per-agent-wallet aggregate has no exposed caller | aggregate not projected | per-receipt gas EXPOSED (f84) / aggregate PROPOSED (lane2) |
| `trading_results.deposits`/`withdrawals` | `funding_flows`, `funding_credits`; `included_in_realized_result=false` | `service_projection.py:93-109`; `views.py:172` | EXPOSED (f84) |
| `trading_results.provider_mode` | `settings.execution_mode` | `execution/routes.py` | EXPOSED (f84) |
| percentage return / account value / drawdown | no adopted calculation profile | - | MISSING (product decision) |

## Edge evidence fields

| Projected field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| `edge_evidence.edge_revision` | `AccountViewRecord` kind `EDGE_EVIDENCE` | `views.py:159,180` | EXPOSED (f84), SYNTHETIC_AUTHORED only |
| `edge_evidence.edge_evidence_status` | same record | `views.py:180` | EXPOSED (f84) |
| real revision-linked findings | `investigation_declarations`, `effect_reports`, `spot_replay_runs` | research callers; not projected | MISSING (P27/P31) |

## Context and preview fields

| Field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| attached `record_id`, `record_kind`, `record_updated_at` | `AccountViewRecord` content | `views.py:83-217,290-311` | EXPOSED (f84) |
| `record_source { table, id }` | `service_projection.py:57-61` | `service_projection.py` | EXPOSED (f84) |
| `memory_version`, entries | `AgentContextRecord` (`agent-context/1`) | `agent_context/controls.py:38-43,261-278` | EXPOSED (f84) |
| memory state ACTIVE/DISABLED/CLEARED | same | `controls.py:42,238-258` | EXPOSED (f84) |
| context source ownership check | `records.record_id` owner-scoped | `controls.py:100-113` | EXPOSED (f84) |
| `action_id` | `execution_intents.action_id`, `execution_queue.action_id` | `execution/routes.py` | EXPOSED (f84) |
| preview permission/reservation/limit | allowances from `AdmissionService.balances` (`admission/service.py:709`); `admission_reservations`, `admission_decisions` | allowances exposed at `GET /v1/agents/{agent_id}/funding` (`funding/routes.py:107-108`); reservations/decisions exposed at `execution/routes.py:139-141` | EXPOSED (f84) |
| consent activation state | `derive_approval` | `connected_identity.py:161-169` | EXPOSED (f84) (fixture only) |

## Accepted tests that already cover these sources

- `apps/api/tests/test_agent_context.py` - MEM-Q02/MEM-Q03/MEM-Q05 behavior (correction, isolation,
  disable/clear, cross-owner denial, version conflict, restart-safe commit).
- `apps/api/tests/test_account_projection.py` - the `SERVICE_PROJECTION` read of connected rows.
- `apps/api/tests/test_account_views.py` - owner-scoped account-view reads.
- `apps/api/tests/test_connected_journey.py` - connected composition and projection.
- `apps/web/tests/service-account-state.test.tsx`, `apps/web/tests/account-records.test.tsx` - the
  read-only UI consumers.

## Summary counts

- `EXPOSED (f84)`: values the accepted account projection or route already outputs (evaluation
  counts and last activity, pending reconciliation, removal state, position results, capital flows,
  provider mode, the `HealthView` route values, and the connected identities).
- `SERVICE VALUE (f84) / PROPOSED (read surface)`: computed by `ExecutionService.status` but not yet
  exposed (submission timestamps, decision input time and id).
- Raw per-job inputs are EXPOSED through the agent route's `jobs` array (`job_view`,
  `execution/worker.py:95-106`; `execution/routes.py:100`): the saved job scope (strategy, publication
  and execution revision, content hash, consent ids), `state`, `outcome`, `reason`, `updated_at` and
  `provenance` (which carries `identity.manifest_sha256`). An exposed raw per-job input is not the same
  as the proposed selected or aggregated health field.
- `STORED INPUT / PROPOSED (lane2)`: the selected/aggregated health fields and inputs with no direct
  route key (`last_evaluation_completion_at`; the selected outcome/state/wait-reason fields; the direct
  `scope.manifest_hash` column; `stop_state`; the per-agent-wallet `native_gas` aggregate).
- `EXPOSED (f84)` also covers the evaluation counts and last activity (`service_projection.py:162-177`),
  pending reconciliation, removal state, position results, capital flows, the per-receipt `actual_gas`
  at `GET /v1/actions/{action_id}`, the `HealthView` route values, and `current_connected_identity` at
  `GET /v1/agents/{agent_id}/actions` (the current resolution, not a saved job's historical scope).
- `MISSING`: `deployment_id`, a normalised per-observation **collection** time,
  `dataset_qualification`, revision-linked real edge evidence, adopted return metrics, and the
  recurring scheduler with its missed-slot policy.
- A job `state` is never reported as an `outcome`. `last_evaluation_outcome` is `null` when
  `job.outcome` is null.
- No field above is fabricated as a caller proof. Every `PROPOSED` field names its owning lane.
