# Restore and rollback runbook (local rehearsal)

Status: rehearsed locally on an owned, run-labelled PostgreSQL 18 container by `apps/api/tests/test_restore_rehearsal.py`. A hosted provider's backup and point-in-time restore tools are not tested here; the hosted procedure needs its own rehearsal before any public use.

## Order of operations for a release

1. Stop the workers: `edge_os_api.execution.worker` and `edge_os_api.research.investigation_jobs`. A worker that sees a schema head it does not know stops itself (exit code 3) before any effect, so a missed worker is safe but noisy.
2. Take a backup: `pg_dump -Fc -f <file> <database>`.
3. Migrate forward: `cd apps/api && uv run --frozen alembic upgrade head`, then `uv run --frozen alembic check`. The check must report no difference.
4. Start the API. `/readyz` must return `{"status": "ready"}`. A 503 names one reason: `database_unavailable`, `schema_drift`, `verification_keys_missing` or `quota_cap_mismatch`.
5. Start the workers. Saved jobs, attempts and original actions continue from saved state; interrupted work is reconciled, never repeated.

## Restore (preferred rollback)

1. Stop the API and the workers.
2. Create an empty database and restore: `pg_restore -d <new database> <file>`.
3. Point `EDGE_OS_DATABASE_URL` at the restored database.
4. Run `alembic check` and confirm `/readyz` is ready.
5. Compare owner budgets (`GET /v1/research/budget`) and a known job with their values before the backup.

The rehearsal confirmed steps 2–5: the budget and the saved job were equal after restore, and readiness was ready.

Records written after the backup are lost by a restore. For financial records this includes actions that may already have reached a provider. Read the provider's record of every action after the backup time before you allow new work.

## Schema downgrade (last resort)

`alembic downgrade 0009` removes the 0010 quota tables and rebuilds `research_local.research_budgets` from the OWNER allocations. The rehearsal confirmed that OWNER totals are equal after `downgrade 0009` and `upgrade head`.

A downgrade loses data that 0009 cannot hold:

- the usage event history (`usage_local.usage_events`), including `CAP_CHANGED` events;
- overrun amounts;
- GLOBAL allocations and any changed GLOBAL cap. A later upgrade recreates GLOBAL rows with the default caps from the owner totals;
- per-owner request windows.

Use a restore instead of a downgrade when the backup is recent enough.

## Caps after a restart or restore

Caps are frozen in the database. A changed `EDGE_OS_RESEARCH_BUDGET_*` or `EDGE_OS_USAGE_GLOBAL_*` value does not change them. Readiness then reports `quota_cap_mismatch` and research starts are refused with 503. Either restore the previous setting or record an operator change:

```
cd apps/api && uv run --frozen python -m edge_os_api.usage.quota set-cap \
  --scope OWNER --owner <owner id> --resource compute_seconds --cap <n> --reason "<why>"
```
