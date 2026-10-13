# Map proposal: P31 LOCAL agent health (lane 3)

PROPOSED for the controller's serial mounting. Lane 3 did not edit the shared feature map or the default verifier
(`scripts/p03/verify_run.py`); they belong to lane 2 in this wave.

## Proposed entry

| Field | Value |
|---|---|
| Feature | P31 LOCAL read-only agent health snapshot and conversation |
| Routes | `GET /v1/agents/{agent_id}/health`, `GET /v1/agents/{agent_id}/health/explanation` |
| API tests | `apps/api/tests/test_agent_health.py` |
| Web tests | `apps/web/tests/agent-health-conversation.test.tsx` |
| Isolated recipe | `scripts/p03/agent_health_runtime_run.py` + `tests/p03/agent-health-runtime.spec.mjs` |
| Evidence class | `SERVICE_PROJECTION` over authored fixture ports |

## Mounting options

1. **Separate step (smallest change):** after the mapped verifier, run the recipe as its own command with its own
   evidence directory. It starts and removes its own container, API, web build and web server.
2. **Phase inside `verify_run.py`:** the recipe's seeding, producer passes, browser stages, SQL inspection and restart
   check can move into a `health_phase.drive/after_restart` pair like `recurring_phase.py`. It then needs two more
   owner tokens per width (`P31_TOKEN_*`), its two agent ids (`P31_AGENT_*`), the intruder token, and its own effect
   record. Its producer passes must run on slots that do not disturb the recurring phase's expected counts.

Option 1 adds no coupling to the recurring phase's slot expectations.
