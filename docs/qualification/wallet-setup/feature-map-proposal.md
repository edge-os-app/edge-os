# Feature-map row: authenticated wallet setup

The earlier `OC-P17-LOCAL` proposal asked for a P05-leased map edit. The `OC-P17-WIRING` lease is
now granted, so the row is realized directly in `.agents/skills/verify-edge-os/feature-map.md`
(rows "P17 authenticated agent wallet setup (application wiring)" and its interface check) and in
the browser steps. This file keeps the row, its SQL checks and its limits together.

## Map row (realized)

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P17 authenticated agent wallet setup | On an exact saved revision, the owner saves one durable setup for an agent id and requested network, then sees the truthful state: confirmed empty, saved-not-dispatched, pending, unknown, confirmed, cancelled-before-dispatch and failed. Only the actions safe in the saved state are offered; a reload reconciles by reading and never replays a creation; labels identify the authored local fixture. | Authenticated `POST /v1/wallet-setup/agents/{agent_id}/prepare\|dispatch\|resume\|cancel` and `GET /v1/wallet-setup/agents/{agent_id}`, mounted from application composition. | Additive `wallet_setups`, append-only `wallet_setup_events` and separate `wallet_setup_denials` (migration 0007). | `apps/api/tests/wallet_setup/` (mounted routes, ownership, recovery, real adapter, production refusal, real PostgreSQL); `apps/web/tests/wallet-setup.test.tsx`; `scripts/p03/verify_run.py` P17 inspection and `tests/p03/*` steps. |

## SQL checks

```sql
select agent_id, network_id, state, creation_dispatched, wallet_id, reason
from wallet_setups order by agent_id;
select setup_id, sequence, event_type, content from wallet_setup_events order by sequence;
select code, count(*) from wallet_setup_denials group by code order by code;
select count(*) from wallet_setups where wallet_id is not null;  -- one binding per confirmed agent
select wallet_id, count(*) from wallet_setups where wallet_id is not null group by wallet_id having count(*) > 1;  -- must be empty
```

## Evidence classes and limits

- The mapped run is `HARNESS_EXECUTED`, `PROCESS_EXECUTED` and browser-executed against the
  authored local fixture.
- `PROVIDER_EXECUTED` and `OWNER_OBSERVED` are `NOT RUN`. A real P16/P17 provider qualification is
  required before any live claim.
- The recipe shares the run-labelled PostgreSQL container and cleanup rules of the existing harness
  and removes only its own resources.

## Do not

- Do not enable the local fixture outside local/test configuration; production refuses it.
- Do not describe a local fixture result as provider or wallet evidence.
- Do not add funding, signer, mandate, activation, position or trading behavior to creation.
