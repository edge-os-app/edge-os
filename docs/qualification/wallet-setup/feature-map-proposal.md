# Feature-map proposal: local wallet setup

The shared verification recipe and its map (`.agents/skills/verify-edge-os/feature-map.md`) are
owned by P05 and stay unchanged. This is an owned local proposal for a later P05-leased edit. It
does not edit the shared map and claims no browser or live PASS. The module is unwired, so the
shared browser recipe cannot exercise it.

## Proposed map row

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P17 local wallet setup (unwired) | None. No UI route; the module is not production wiring. | Test-only `POST /v1/wallet-setup/agents/{agent_id}/prepare\|dispatch\|resume\|cancel` and `GET /v1/wallet-setup/agents/{agent_id}` in the test harness only. | Local `wallet_setup_local` tables: `wallet_setups`, append-only `wallet_setup_events`, `wallet_setup_denials`. | `apps/api/tests/wallet_setup/` (30 controls, real PostgreSQL, authored fake provider); `docs/qualification/wallet-setup/` recipe. |

## Proposed SQL checks

```sql
select agent_id, network_id, state, creation_dispatched, wallet_id, reason
from wallet_setups order by agent_id;
select setup_id, sequence, event_type, content from wallet_setup_events order by sequence;
select code, count(*) from wallet_setup_denials group by code order by code;
select count(*) from wallet_setups where wallet_id is not null;  -- one binding per confirmed agent
select wallet_id, count(*) from wallet_setups where wallet_id is not null group by wallet_id having count(*) > 1;  -- must be empty
```

## Evidence classes and limits

- The map row is `HARNESS_EXECUTED` and `PROCESS_EXECUTED` only.
- `PROVIDER_EXECUTED` and `OWNER_OBSERVED` are `NOT RUN`. A later qualified P16/P17 request is
  required before any live claim.
- No UI, browser, accessibility or cleanup row is proposed: the module is unwired and creates no
  browser surface.
- The recipe shares the run-labelled PostgreSQL container and cleanup rules of the existing
  harness. It removes only its own resources.

## Do not

- Do not add the test-only routes to the production router.
- Do not add the local tables to a shared model or migration under a different lease.
- Do not describe a local fake result as provider or wallet evidence.
