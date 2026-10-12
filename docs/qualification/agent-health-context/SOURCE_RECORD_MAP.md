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

| Projected field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| `scope.owner_id` | `Principal.user_id` | `core/authentication.py`, `accounts/views.py:273-280` | PRESENT (f84) |
| `scope.agent_id` | `execution_evaluation_jobs.agent_id` | `service_projection.py:162-177` | PRESENT (f84) |
| `scope.wallet_id` | `execution_evaluation_jobs.wallet_id` | same | PRESENT (f84) |
| `scope.network_id` | `execution_evaluation_jobs.network_id` | same | PRESENT (f84) |
| `scope.strategy_id` | `execution_evaluation_jobs.strategy_id` | `worker.py`; not projected today | PRESENT (f84) / projection PROPOSED |
| `scope.publication_revision_id` | `execution_evaluation_jobs.publication_revision_id` | same | PRESENT (f84) / projection PROPOSED |
| `scope.execution_revision_id` | `execution_evaluation_jobs.execution_revision_id` | IC01, `connected_identity.py` | PRESENT (f84) |
| `scope.content_hash`, `manifest_hash` | `execution_evaluation_jobs.content_hash`, `manifest_hash` | IC01 | PRESENT (f84) |
| `scope.consent_adoption_id`, `consent_hash` | `execution_evaluation_jobs.consent_adoption_id`, `consent_hash` | IC01 | PRESENT (f84) |
| `scope.deployment_id` | no column exists | - | MISSING (P27) |
| `worker_health.last_attempt_at` | `max(execution_evaluation_jobs.updated_at)` | `service_projection.py:173` | PRESENT (f84) |
| `worker_health.last_completion_at` | `max(updated_at)` where `state='COMPLETED'`; `HealthView.last_completion_at` | derivable from `service_projection.py:175`; `execution/service.py:854,865` | PRESENT (f84) / projection PROPOSED |
| `worker_health.evaluation_attempts` | count of jobs | `service_projection.py:174` | PRESENT (f84) |
| `worker_health.evaluation_completions` | count where `state='COMPLETED'` | `service_projection.py:175` | PRESENT (f84) |
| `worker_health.last_outcome` | `job.outcome` | `service_projection.py:166,177` | PRESENT (f84) |
| `worker_health.wait_or_fault_reason` | `job.reason` (`WAITING:*`, `WORKER_ERROR:*`, `OBSERVATIONS_WRONG_*`, `IDENTITY_*`, `CONSENT_CHANGED`); `HealthView.blocking_reason` | `worker.py:282-302,446-473`; `execution/service.py:858-870` | PRESENT (f84) / projection PROPOSED |
| `worker_health.pending_reconciliation` | `recovery_cases.state IN ('OPEN','UNKNOWN')` (lines 144,159) and job `outcome='SUBMITTED_UNKNOWN'` via `UNSETTLED_JOB_OUTCOMES` (line 33, used at 166,176) | `service_projection.py` | PRESENT (f84) |
| `worker_health.stop_state` | `stops_local.scoped_stops` | `stops/service.py`, `revocation/enforcement.py` | PRESENT (f84) / projection PROPOSED |
| `worker_health.removal_state` | `revocation_local.removal_states.state` | `service_projection.py:79-91` | PRESENT (f84) |
| `worker_health.residual_inventory` | `admission_positions.inventory` | `service_projection.py:126-141` | PRESENT (f84) |
| `worker_health.latest_input_updated_at` | `HealthView.last_input_at` (last decision time) | `execution/types.py:321-332`, `execution/service.py:866` | PRESENT (f84) / per-observation collection time MISSING |
| `worker_health.input_event_time`, `collection_time` | `HealthView.last_input_at` (decision time); IC02 observation provenance holds raw times | `execution/service.py:866`; `worker.py:285-302` | PRESENT (f84) decision time / collection time MISSING (P27) |
| `worker_health.next_scheduled_work` | `HealthView.next_scheduled_at` = last decision + 5 min (bounded-pipeline estimate); no recurring scheduler table | `execution/service.py:855-857`, `execution/routes.py:106`; `service_projection.py:177` sets `next_work` only for pending reconciliation | PRESENT (f84) derived estimate / recurring schedule MISSING (P27) |
| `worker_health.dataset_qualification` | `research_local.history_datasets` verdict | `research/history_dataset.py` | MISSING as health field |

## Trading result fields

| Projected field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| `trading_results.realized_result` | `admission_positions.realized_quote` | `service_projection.py:139-140` | PRESENT (f84) |
| `trading_results.basis` | `admission_positions.cost_basis` | `service_projection.py:137-138` | PRESENT (f84) |
| `trading_results.estimated_unrealized_result` | no mark source; `UNKNOWN` | `service_projection.py:141` | PRESENT (f84) as UNKNOWN |
| `trading_results.mark` | no mark source; `UNKNOWN` | `service_projection.py:141` | PRESENT (f84) as UNKNOWN |
| `trading_results.native_gas` | funding profile gas asset; `admission_receipts` actual gas | `funding/persistence.py:66-67`; `original_transaction.py` | PRESENT (f84) |
| `trading_results.deposits`/`withdrawals` | `funding_flows`, `funding_credits`; `included_in_realized_result=false` | `service_projection.py:93-109`; `views.py:172` | PRESENT (f84) |
| `trading_results.provider_mode` | `settings.execution_mode` | `service_projection.py` (`ports`) | PRESENT (f84) |
| percentage return / account value / drawdown | no adopted calculation profile | - | MISSING (product decision) |

## Edge evidence fields

| Projected field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| `edge_evidence.edge_revision` | `AccountViewRecord` kind `EDGE_EVIDENCE` | `views.py:159,180` | PRESENT (f84), SYNTHETIC_AUTHORED only |
| `edge_evidence.edge_evidence_status` | same record | `views.py:180` | PRESENT (f84) |
| real revision-linked findings | `investigation_declarations`, `effect_reports`, `spot_replay_runs` | research callers; not projected | MISSING (P27/P31) |

## Context and preview fields

| Field | Producer source | Caller at f84 | Status |
|---|---|---|---|
| attached `record_id`, `record_kind`, `record_updated_at` | `AccountViewRecord` content | `views.py:83-217,290-311` | PRESENT (f84) |
| `record_source { table, id }` | `service_projection.py:57-61` | `service_projection.py` | PRESENT (f84) |
| `memory_version`, entries | `AgentContextRecord` (`agent-context/1`) | `agent_context/controls.py:38-43,261-278` | PRESENT (f84) |
| memory state ACTIVE/DISABLED/CLEARED | same | `controls.py:42,238-258` | PRESENT (f84) |
| context source ownership check | `records.record_id` owner-scoped | `controls.py:100-113` | PRESENT (f84) |
| `action_id` | `execution_intents.action_id`, `execution_queue.action_id` | `execution/routes.py` | PRESENT (f84) |
| preview permission/reservation/limit | `admission_allowances`, `admission_reservations`, `admission_decisions` | `admission/service.py` | PRESENT (f84) |
| consent activation state | `derive_approval` | `connected_identity.py:161-169` | PRESENT (f84) (fixture only) |

## Accepted tests that already cover these sources

- `apps/api/tests/test_agent_context.py` - MEM-Q02/MEM-Q03/MEM-Q05 behavior (correction, isolation,
  disable/clear, cross-owner denial, version conflict, restart-safe commit).
- `apps/api/tests/test_account_projection.py` - the `SERVICE_PROJECTION` read of connected rows.
- `apps/api/tests/test_account_views.py` - owner-scoped account-view reads.
- `apps/api/tests/test_connected_journey.py` - connected composition and projection.
- `apps/web/tests/service-account-state.test.tsx`, `apps/web/tests/account-records.test.tsx` - the
  read-only UI consumers.

## Summary counts

- `PRESENT (f84)`: the fields `service_projection.py` already projects plus the stored identities.
- `PRESENT (f84) / projection PROPOSED`: stored today, not yet projected (strategy/revision,
  wait/fault reason, stop state).
- `MISSING`: `deployment_id`, a normalised per-observation **collection** time,
  `dataset_qualification`, revision-linked real edge evidence, adopted return metrics, and the
  recurring scheduler with its missed-slot policy. The bounded-pipeline `next_scheduled_at` and
  `last_input_at` already exist in `HealthView`; only the recurring scheduler is missing.
- No field above is fabricated as a caller proof. Every `PROPOSED` field names its owning lane.
