# Feature-map proposal: local funding reconciliation

The shared verification recipe and its map (`.agents/skills/verify-edge-os/feature-map.md`) are owned
by P05 and stay unchanged. This is an owned local proposal for a later P05-leased edit. It does not
edit the shared map and claims no browser, provider or live PASS. The module is unwired, so the shared
browser recipe cannot exercise it.

## Proposed map row

| Feature | UI | API | Saved records | Evidence |
|---|---|---|---|---|
| P18 local funding reconciliation (unwired) | None. No UI route; the module is not production wiring. | Test-only `POST /v1/funding/agents/{agent_id}/declare\|flows\|reconcile`, `GET /v1/funding/agents/{agent_id}/flows\|flows/{flow_id}\|balances\|available` in the test harness only. | Local `funding_local` tables: `funding_profiles`, `funding_flows`, append-only `funding_observations`, once-only `funding_credits` (unique `wallet_id, network_id, asset_id, event_id`), `funding_denials`. | `apps/api/tests/funding/` (47 controls, real PostgreSQL, authored fake observer, independent-process driver); `docs/qualification/funding/` recipe. |

## Proposed SQL checks

```sql
select agent_id, network_id, state, asset_id, declared_raw, decimals, transaction_reference
from funding_local.funding_flows order by created_at;
select flow_id, sequence, status, asset_id, actual_raw, fee_asset_id, event_id, reason
from funding_local.funding_observations order by sequence;
select wallet_id, network_id, asset_id, event_id, actual_raw, fee_asset_id, count(*)
from funding_local.funding_credits group by 1,2,3,4,5,6 having count(*) > 1;  -- must be empty
select code, count(*) from funding_local.funding_denials group by code order by code;
select asset_id, sum(actual_raw) from funding_local.funding_credits
where wallet_id = 'wallet-a' group by asset_id order by asset_id;  -- per-asset, never pooled
```

## Evidence classes and limits

- The map row is `HARNESS_EXECUTED` and `PROCESS_EXECUTED` only.
- `PROVIDER_EXECUTED`, `OWNER_OBSERVED` and `WIRING_EXECUTED` are `NOT RUN`. A later qualified P18
  real-transport request and the P17/P05 shared-wiring lease are required before any live claim.
- No UI, browser, accessibility or cleanup row is proposed: the module is unwired and creates no
  browser surface.
- The recipe shares the run-labelled PostgreSQL container and cleanup rules of the existing harness.
  It removes only its own resources.

## Do not

- Do not add the test-only routes to the production router.
- Do not add the local tables to a shared model or migration under a different lease.
- Do not describe a local fake observation as provider, chain or financial evidence.
