# H10 backup and restore drill (HOSTED_RECORD_V2_RUNBOOK §5.2, §5.3)

Status: **PASS** for the logical dump and the on-VPS restore drill. The Contabo snapshot is **DONE**.

Operator: controller over SSH. Builder advance approval 2026-10-23. Host: VPS `vmi3674409`.

## Logical dump (§5.2)

| Item | Recorded value |
|---|---|
| Dump path | `/var/backups/edge-os/edge_os-20261023T073738Z.dump` |
| File mode and owner | `0600`, root |
| Size | 181074 bytes |
| SHA-256 | `15cfc20bf0ae86384d680b8f146176f4e7819f97f53ad066410100fb2b028a5d` |
| Recovery point | `2026-10-23T07:37:38Z` |
| Dump readable | the restore drill read this dump with `pg_restore --exit-on-error` (exit 0); a separate `pg_restore -l` result is not recorded |
| Result | PASS |

## Restore drill (§5.3)

| Item | Recorded value |
|---|---|
| Image | `postgres:18.6-trixie@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336` (same as live) |
| Drill container | `--network none`, no published port, removed with `-v` after the check |
| `pg_restore --exit-on-error` | exit code 0, 0 seconds (rounded) |
| `alembic_version` | drill `0013` = live `0013` |
| Known row | `users` count drill 1 = live 1 |
| User tables in the drill | 59 |
| Result | PASS |

## Snapshot (§5.1)

Contabo snapshot: **DONE** by the builder in the Contabo panel (builder screenshot, 2026-10-30).

| Item | Recorded value |
|---|---|
| Name | `Edgeos-pre-hermes-20261030` |
| Description | Before Hermes app start and hosted record |
| Created | Oct 30, 2026 8:55 AM (panel display; time zone not shown) |
| Auto-deletion | Nov 29, 2026 9:55 AM (panel display) |
| State captured | VPS after the `275b399` apply, app unit installed but disabled, UFW 8011 rule; before the hosted record registration and the Hermes app start |
| Result | DONE |

The hosted record `valid_until` must not be later than the snapshot auto-deletion, or a new snapshot is needed first.
The record uses `2026-11-27T00:00:00Z`, before `2026-11-29`.

## Sanitization

This file holds no password, key, token, connection string or credential. The drill container password was generated
inside the drill command and is not recorded here.

## Limit

The dump sits on the VPS disk. The next Contabo snapshot carries it. An encrypted off-VPS copy
(`deploy/coolify/RUNBOOK.md` §8) remains recommended and is not recorded.
