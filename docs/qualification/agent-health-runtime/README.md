# Agent health runtime (P31 LOCAL)

Task `P31-HEALTH-RUNTIME-L3-20261013-LOCAL-v1`, #58 (lane 3; also #39). Base `ff1d958`. Status: **LOCAL read-only
consumer only.** It reads the accepted P27 producer and other accepted read services over authored fixture ports. It is
not live health, a live chat, a forward feed, an operating profile or financial permission. Full P31 and AUT06 stay
open: they need the missing producer inputs below and actual recurring evidence.

Agreement sources: [HEALTH_PROJECTION_CONTRACT.md](../agent-health-context/HEALTH_PROJECTION_CONTRACT.md) (P31
preparation), [recurring-operation/CONTRACT.md](../recurring-operation/CONTRACT.md) (P27 producer) and the producer
owner's v1 corrections (controller workspace `p31-owner-response-v1.md`, adopted by this assignment). The producer
source is unchanged.

## Routes (existing mounted execution router, read-only)

| Route | Returns |
|---|---|
| `GET /v1/agents/{agent_id}/health` | One snapshot, `schema_version = edge-os.agent-health-projection/1`, `evidence_class = SERVICE_PROJECTION` |
| `GET /v1/agents/{agent_id}/health/explanation?question=…` (1–500 characters) | `edge-os.agent-health-explanation/1`: the topic, answer lines and the same snapshot the answer was built from |

The owner is the verified principal only. Scope is one saved owner/agent/wallet/network/deployment (the newest
deployment). An agent with neither a deployment nor a confirmed wallet for this owner is `404`, as for another owner.
An agent with a confirmed wallet and no deployment returns a snapshot whose producer fields are `UNKNOWN (NO_DEPLOYMENT)`.

## Snapshot rules

- **Producer:** `RecurringOperation.projection(owner_id, agent_id)`: newest deployment, newest 20 occurrences
  (`window`), UTC five-minute grid.
- **Next work:** `producer.next_due_slot`, or `UNKNOWN` with the producer's `no_next_reason` (`PRODUCER_NOT_SEEN`, or
  the end reason). The bounded pipeline's `next_scheduled_at` (last decision + 5 minutes) is shown only as
  `UNKNOWN (NOT_RECURRING_SCHEDULE…)`.
- **Read clock:** `read_at` is the producer's read clock. `producer_silent` and `wait_reason` are values at `read_at`.
- **`as_of`:** the newest stored write among the saved deployment's rows, with `table`, `id`, `field`, `time`
  (`agent_health/source_times.py`: deployment `updated_at`, job `updated_at`, outcome `evaluated_at`, attempt
  `started_at`/`completed_at`, queue `updated_at`). It means "newest stored write", not "the producer advanced". All
  named times are listed in `record_refs`. With no deployment, `as_of` is `null`, never the read clock.
- **Precision:** every time is whole UTC seconds (`YYYY-MM-DDTHH:MM:SSZ`). A missing time is
  `{"state": "UNKNOWN", "reason": …}` with a source-specific reason, never a default.
- **Evaluation vs trade:** `last_evaluation` (the saved evaluation outcome and its input/collection/evaluation times)
  and `last_trade_attempt` (the latest submission attempt) are separate. A no-signal slot has no trade attempt.
- **Pending reconciliation:** canonical = the producer's unsettled queue (`PRODUCER_UNSETTLED_QUEUE`). Account recovery
  cases `OPEN`/`UNKNOWN` (ACTION records) and `SUBMITTED_UNKNOWN` monitoring (MONITORING record) are listed as
  separately sourced `warnings`, never merged.
- **Controls:** stop rows (`StopService.retrieve_stops`) and removal rows (`RemovalService.read_removal`) with their
  times; the deployment state, end reason and end time. `control_state_basis` stays `UNKNOWN`.
- **Residual inventory:** the account POSITION projection for the exact wallet/network.
- **Identity:** the saved deployment identity, the current resolution (`resolve_agent`) and `changed`, using the
  producer's own comparison. Historical occurrences keep their saved revision.
- **Missing producer inputs (explicit `UNKNOWN`):** native-gas aggregate, `dataset_qualification`, revision-linked edge
  evidence, `control_state_basis`, selected completion/outcome, job `manifest_hash`.
- **`snapshot_digest`:** SHA-256 of the canonical snapshot without `read_at`. Unchanged rows give the same digest;
  a read across the silence boundary can change the read-clock values and so the digest.

## Conversation

The explanation maps the question to one topic by words (`last`, `next`, `waiting`, `reconciliation`, `controls`,
`inventory`, `identity`, `unknowns`; otherwise a summary) and answers only from the snapshot read in the same request.
There is no model or provider call, no write and no tool. Controls stay on the direct pages. In the web app the
Conversation panel on an opened agent's account view (`#/agents?agent=…`, and the other account views) is this
read-only branch; Research keeps its own conversation. Each reply shows its own `read_at`, `as_of` and digest; a new
question reads the current snapshot. Replies live in the open page only; they are not saved on the server.

## Fault matrix (request → effect → fault → evidence)

| Case | Expected snapshot | Proof |
|---|---|---|
| Signal slot | evaluation SIGNAL with times; trade attempt with completion; next = cursor + 5 min | API test; browser desktop |
| No signal / ineligible | evaluation saved; `last_trade_attempt` UNKNOWN | API test |
| Missing feed | UNAVAILABLE `OBSERVATIONS_UNAVAILABLE`; input times UNKNOWN with their reasons | API test |
| Silent producer | wait `PRODUCER_NOT_SEEN` at `read_at`; next UNKNOWN; `as_of` = deployment `updated_at` | API test |
| Unknown original | canonical pending = the action; warnings separate; wait `WAITING_RECONCILIATION` | API test; browser 390px |
| Stop / removal / owner end | dated stop and removal rows; ENDED with reason; next UNKNOWN; inventory kept | API tests; browser desktop |
| Changed revision (authored row change) | saved vs current identity distinct, `changed = true`; then `ENDED IDENTITY_CHANGED` | API test |
| Sibling agents, same token; second owner | own deployment/wallet/positions only; other owner `404`; unauthenticated `401` | API test; browser |
| Read / question | zero writes (every financial and record row digest unchanged); zero provider calls (every port refuses) | API tests; browser SQL/effects |
| API restart, new browser context | same `record_id`, digest, `as_of` and unknowns | API test; browser |

## Proof in this candidate

- API: `apps/api/tests/test_agent_health.py`.
- Web: `apps/web/tests/agent-health-conversation.test.tsx`.
- Isolated mounted recipe (not the shared verifier):
  `apps/api/.venv/bin/python scripts/p03/agent_health_runtime_run.py --evidence <new empty directory>` with
  `tests/p03/agent-health-runtime.spec.mjs`. See [MAP_PROPOSAL.md](MAP_PROPOSAL.md).

## Retained limits

- Every observation, quote, transport and receipt is an authored fixture. The LOCAL producer recipe runs with
  `--clock-offset-minutes`, so stored producer times can be later than the API's real read clock.
- No live user, provider, model, hosted worker or chain action was used. No full P31/AUT06 claim.
- The bounded pipeline section (`ExecutionService.status`) covers the agent wallet, manual and recurring jobs together.
