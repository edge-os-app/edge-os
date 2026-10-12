# Context and preview agreement (P31 preparation)

Agreement `edge-os.agent-context-preview/1`, PROPOSED. Base `f84ef415278196db2c8bba73eaa154a1ef00748b`.

This agreement fixes the exact read-only context a P31 conversation attaches, and the exact preview
it may show, for the supported accepted controls only. It exists so conversation and direct controls
read one action identity and one record identity. It enables no chat runtime, no action and no
submission. `NOT_RUN`: no chat, provider, model or browser check supports this milestone.

## 1. Attached context object

A conversation turn carries exactly one context object. It is read-only.

```text
AgentContextAttachment
  schema_version     "edge-os.agent-context-preview/1"          PROPOSED
  scope              owner_id, agent_id, wallet_id, network_id  (section 2)
  record_id          the exact saved record this turn is about
  record_kind        AGENT | POSITION | ACTION | CAPITAL_FLOW | MONITORING | EDGE_EVIDENCE | PERMISSION_SNAPSHOT
  record_source      { table, id } from the projection (section 6 of HEALTH_PROJECTION_CONTRACT.md)
  record_updated_at  the stored update time, not the read time
  revision           strategy_revision, publication_revision_id, execution_revision_id where present
  action_id          the exact action, when the turn is about an action
  memory_version     the P19 context version used, when memory applies
```

The `record_id`, `record_kind`, `record_source` and `record_updated_at` come from the accepted
`accounts/views.py` and `accounts/service_projection.py` shapes. `memory_version` comes from
`agent_context/controls.py` (`retrieve_agent_context`). The context label is visible, and it returns
a link to the exact record.

## 2. Owner and scope

- The owner is the verified `Principal.user_id`. A request body, query, navigation target or
  conversation turn cannot set or change it (`core/authentication.py`; `accounts/views.py` reads by
  owner only).
- A foreign or absent agent, action, review or removal is `404`. Adopting another owner's review is
  `404`. Scheduling for an agent the caller does not hold is `409 agent_not_ready`.
- A token ticker alone is not sufficient scope. When several positions hold the same token, the
  conversation must ask which position and quantity the request concerns before it does anything
  consequential (spec line 1419; WAL-Q26).

## 3. Ambiguity and clarification

- An ambiguous same-token sell or an ambiguous "pause it" requires clarification before any
  consequential preview. The conversation must resolve the position/deployment/wallet scope and the
  intended stop effect first.
- The system must not choose another agent's holdings. It asks only for the missing meaning needed
  for that request.
- A clarification is a `Clarification` record linked to its interpretation (accepted intake
  contract). A clarification is not authority and is not a preview.

## 4. Supported accepted controls

Only these accepted controls can appear in a preview or a direct control. Each maps to an accepted
caller at the base commit.

| Control | Accepted route / caller | State |
|---|---|---|
| Review + adopt consent (stays INACTIVE) | `POST …/consent/review`, `POST …/consent/adopt` (`consent/service.py`; IC05) | PRESENT (f84) |
| Schedule one bounded evaluation job (may later evaluate, admit and submit) | `POST …/agents/{agent_id}/actions` `{request_key}` → `ConnectedExecution.schedule` (`execution/routes.py:72-81`; `execution/worker.py:119-150`) | PRESENT (f84) |
| Read the agent's jobs, decisions, queue, positions and blocking reason | `GET /v1/agents/{agent_id}/actions` (`execution/routes.py:83-106`) | PRESENT (f84) |
| Read one action | `GET /v1/actions/{action_id}` | PRESENT (f84) |
| Stop new entries / halt all swaps | `POST/GET …/stops` `{mode, scope, position_id?}` (`stops/`) | PRESENT (f84) |
| Request removal | `POST/GET …/removal` `{request_key, reason}` (`revocation/`) | PRESENT (f84) |
| Correct / adopt / disable / clear memory | `agent_context/controls.py` | PRESENT (f84) |

The schedule call is not a harmless action save. It inserts one `EvaluationJobRow` with `state=QUEUED`,
`decision_id=None` and `action_id=None`; a later worker pass may evaluate, admit and submit. The
conversation must present it as a consequential control that can lead to a trade, not as a draft.

Unavailable or unqualified operations, including manual sale (P32), partial exits, additions,
liquidation and withdrawal, must be shown as unsupported. They must not appear as an actionable
preview.

## 5. The shared preview

For a consequential request, both channels use one preview shape (spec line 1421). It records:

- exact target and context (section 1);
- the requested operation and quantity;
- the current data and time, and the record `updated_at`;
- the expected asset movement;
- the applicable permissions, reservations and limits;
- the costs, and any unknown value as `UNKNOWN`, never zero;
- the remaining exposure;
- whether future entries stay active.

A read-only action preview is PROPOSED. It binds one `action_id` only when a saved action exists
(`execution_local.execution_intents`, `execution_queue`). Before an action exists, the safe retained
identity is the evaluation job, keyed by `request_key` on `(owner, agent, request_key)` and
`(owner, agent, adopted consent, decision slot)`. A job may produce no action (no-signal) or an
action later, so a job is not an action. The preview is an estimate for a quote, not a guarantee.

## 6. Preview identity and the action record

- A preview does not create a second ledger. When an action exists, it reads the same action identity
  the direct control reads (`execution_local.execution_intents`, `execution_queue`,
  `admission_decisions`).
- A repeated schedule call returns the same evaluation job. Its idempotency is per
  `(owner, agent, request_key)` and per `(owner, agent, adopted consent, decision slot)`; that identity
  is a job, not an action. The conversation must not claim a saved action exists when only a job
  exists, and it must not silently create a second economic action.
- A preview is not execution permission and is not submission support. Recheck current operational
  eligibility, authority and the target agent-wallet reservations before admission or submission.
  A stale preview cannot grant authority.
- Conversation, a preview, a submission acknowledgment or a refresh cannot claim a completed
  liquidation. States stay PROPOSED, QUEUED, SUBMITTED, CONFIRMED, REVERTED, DENIED or
  SUBMISSION_UNKNOWN, with reasons and update times.

## 7. Direct read, suggestion and confirmed write

The conversation must distinguish three different things and never blur them:

| Kind | Meaning | Effect |
|---|---|---|
| Direct read | A question answered from saved records | No write, no financial action |
| Suggested change | A proposed correction, rule change or memory adoption | A suggestion until the owner adopts it through the exact accepted flow |
| Confirmed write | A completed accepted control call | The saved record changes; the response names the record and version |

Guarantees:

- A suggestion cannot change rules or permission. It needs the existing adoption/revision flow
  (MEM-Q04; `consent/service.py`, `agent_context/controls.py`).
- Memory or a conversation cannot silently change adopted rules, schedule or authority.
- No model chain-of-thought, private reasoning, credential, signing secret or provider text is
  exposed. The conversation explains recorded decisions from the saved records (`GET
  /v1/actions/{id}` allow-list), never from model reasoning.

## 8. Repeated preview and cross-owner behavior

- A repeated schedule call returns the same evaluation job (`Idempotent-Replay` on
  `POST …/agents/{agent_id}/actions`); it does not prove an action exists.
- An action preview binds one saved `action_id`; before an action is saved, only the job identity is
  retained (section 6).
- A cross-owner target is `404` and makes no provider call.
- A stale target is refused. A's preview cannot retarget B after navigation; the owner and scope are
  read from the verified principal, not from the attached label.

## 9. Frozen consumer

The P31 conversation attaches context and shows a preview. It reads the health projection snapshot
(`HEALTH_PROJECTION_CONTRACT.md`) and the saved action records. It:

- cannot calculate a schedule, a profit, a percentage return or a new action;
- cannot make a second financial engine;
- returns the same values, sources and unknowns as the producer.

## 10. Out of scope

No chat backend, no conversation endpoint and no preview renderer is implemented here. Manual sale
(P32), partial exits, additions, unqualified liquidation and withdrawal stay unavailable. The
runtime cases in `WORKED_CASES.md` are contract examples, not browser or chat proof.
