# CLOUD-LOOPBACK-STRICT status

Branch `cloud/loopback-strict`, base `origin/integration/edge-os-mvp` at `1d2311dcef7e849db97464974e35a8aa4156ac9d`.
Builder-approved normal cloud session, 2026-10-23. Normal pushes to this branch only. No PR, no merge, no main or
integration push. No network, provider, credential, key or VPS access was used.

## Result

**Final reviewed candidate: `7b43f06`.** Both round-2 independent reviewers PASSED this commit. The commit that adds
this file changes only this file.

In production, `core/settings.py` now refuses, with the existing reason
`database_url: production needs a hosted database, not a loopback host`:

- a URL with no host and any multi-host list (a comma in the host);
- `localhost` and `*.localhost` in any letter case, with or without trailing dots;
- every loopback or unspecified address, parsed with `ipaddress` (all of `127.0.0.0/8`, `::1` in any spelling or with a
  zone, IPv4-mapped forms, `0.0.0.0`, `::`), plus short and legacy IPv4 spellings parsed with `socket.inet_aton`
  (`127.1`, `2130706433`, `0x7f000001`, `0177.0.0.1`). No DNS lookup is made.

Option A is kept exactly: only the literal host `127.0.0.1`, with a registered named record whose TLS mode equals the
URL's `sslmode`, is admitted. Every other loopback form stays refused even with a record. `local` and `test` behavior
and non-loopback hosts are unchanged.

Two small widenings beyond the literal task wording, both stricter and documented, and both judged acceptable by the
spec reviewers: `*.localhost` names (RFC 6761 loopback) and legacy numeric IPv4 spellings.

## Commits

- `aa6a3db`: RED tests only (54 failed against the base code, confirmed by me and independently by both spec reviewers).
- `13b0997`: implementation, settings comment, `HOSTED_RECORD_V2_RUNBOOK.md` §3.2, `CONTRACT.md` §5.5, and the
  `CLOUD_HR2_STATUS.md` open item.
- `7b43f06`: round-1 repair (removed a reference to a not-yet-existing file, noted the hosts-file limit in the runbook,
  added whitespace-host test cases).

## Files changed (since 1d2311d)

- `apps/api/src/edge_os_api/core/settings.py` (imports, helper `is_loopback_database_host`, production host condition)
- `apps/api/tests/test_hosted_deployment.py`
- `docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md` (§3.2)
- `docs/qualification/hosted-activation/CONTRACT.md` (§5.5)
- `docs/qualification/hosted-gates/CLOUD_HR2_STATUS.md` (open-item line)
- `docs/qualification/hosted-gates/CLOUD_LOOPBACK_STRICT_STATUS.md` (this file)

## Tests

`cd apps/api && uv run --frozen pytest -q -p no:cacheprovider tests/test_hosted_deployment.py tests/deploy` gives
**272 passed** at `7b43f06` (268 at `13b0997`). `tests/deploy` includes `test_production_settings.py`. `docker compose
config` runs inside these tests with the Docker CLI; no daemon was needed. The full suite was not run (its database
fixtures need a Docker daemon; out of scope for this lane). `ruff` without project config reports the same 12
pre-existing findings in both touched Python files on the base and on this branch; none is on an added line.

## Reviews (new independent subagents each round)

| Round | Commit | Spec | Standards |
|---|---|---|---|
| 1 | `13b0997` | FAIL: `CLOUD_HR2_STATUS.md` cited a file that did not exist yet | PASS (non-blocking only) |
| 2 | `7b43f06` | **PASS** (non-blocking only) | **PASS** (non-blocking only) |

## Non-blocking findings (not done; outside this lane or builder decisions)

- Names mapped to loopback only by a hosts file (`ip6-localhost`, `localhost.localdomain`, `localhost6`) are not detected;
  a no-DNS rule cannot see them. Now stated in runbook §3.2. A small fixed name list could be added if wanted.
- IPv4-compatible `[::127.0.0.1]`, IPv4-translated `[::ffff:0:127.0.0.1]` and NAT64 `[64:ff9b::7f00:1]` are admitted;
  Linux does not route them to loopback.
- libpq can still take a host from query keys other than `host`/`hostaddr` (`service` with a service file) or from
  `PGHOSTADDR`/`PGSERVICE` in the environment. Refusing `service` or allowlisting query keys would close this.
- The Coolify reserved-host check keeps its own `rstrip(".").lower()` normalisation.
