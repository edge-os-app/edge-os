# CLOUD-HR2 status: hosted deployment record v2

Branch `cloud/hosted-record-v2`, base `origin/integration/edge-os-mvp` at `82290e203982ee710189c4d983edce9a4ddfba9f`.
Normal pushes to this branch only. No PR, no merge, no main or integration push. No network, provider, credential,
key or VPS access was used. Both registries (`APPROVED_HOSTED_DEPLOYMENTS`, `APPROVED_ACTUAL_RELEASES`) stay empty.

## 1. What this lane is waiting for

**Review:** the round-3 spec review of candidate `7f450ce` is still running. The round-3 security review already
PASSED `7f450ce`. If the spec review passes, both reviewers have passed the same commit and the lane is done. If it
fails, the lane repairs the finding and runs a new pair of reviewers on the repaired commit. This status file is a
documentation-only commit on top of `7f450ce` and changes no reviewed code.

**One builder decision (it does not block this lane): the host research worker's loopback database route.**
`core/settings.py` still refuses a loopback database host in production (`database_url: production needs a hosted
database, not a loopback host`). The host research worker loads the same settings, so B2 option a
(`127.0.0.1:5432`) is wired in Compose, TLS and the runbook, but the worker still refuses that URL. This lane did not
widen a production refusal without approval.

| Option | Effect |
|---|---|
| **A (recommended)** | A separate reviewed settings change. In production, admit a loopback database host only when a registered hosted deployment record is named and the URL's `sslmode` equals the record's TLS mode. Everything else keeps the refusal. |
| B | Keep the refusal. The research worker stays disabled (`/etc/edge-os/research-worker.enabled` absent). |
| C | Point the host name `edge-os-postgres` at 127.0.0.1 in the host's `/etc/hosts`. This is not recommended: it gets around the loopback check instead of deciding it. |

## 2. Candidate, files, tests, verdicts

- **Reviewed code candidate:** `7f450ce`. The RED tests are commit `46c95a5` (tests only), followed by `4897972`,
  `c1c67f5` and `7f450ce`.
- **Files changed (82290e2..7f450ce):**
  - `apps/api/src/edge_os_api/core/hosted_deployment.py`
  - `apps/api/src/edge_os_api/core/settings.py`: the production-gate lines only. The `wallet_provider` line and the
    settings fields are untouched.
  - `apps/api/tests/test_hosted_deployment.py`
  - `apps/api/tests/deploy/test_compose_validation.py`, `test_coolify_topology.py`, `test_deploy_artifacts.py` and
    `test_production_settings.py`
  - `compose.coolify.yml`
  - `deploy/coolify/RUNBOOK.md`
  - `deploy/host/edge-os-egress-firewall.sh`, `edge-os-egress-firewall.service`, `edge-os-egress-refresh.service` and
    `edge-os-egress-refresh.timer`
  - `docs/qualification/hosted-activation/CONTRACT.md`
  - `docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md`
- **Tests:**
  - Focused: `cd apps/api && uv run --frozen pytest -q -p no:cacheprovider tests/test_hosted_deployment.py tests/deploy`
    gives **183 passed**. It covers the record and settings gate, the Compose topology, the runbooks and the firewall
    files. `docker compose config` runs inside these tests; only the Docker CLI is present, with no daemon.
  - Full: `cd apps/api && uv run --frozen pytest -q -p no:cacheprovider` gives 2556 passed, 1 skipped, 14 failed and
    1264 errors. The 1264 errors are database fixtures that need a Docker daemon, which this container does not
    have. Of the 14 failures, 12 in `test_harness_isolation.py` and 1 in `test_live.py` also need the Docker daemon.
    The other one, `test_privy_wallet_lookup.py::test_ipc_malformed_or_oversized_frames_get_a_code_only[...]`, fails
    the same way on the untouched base `82290e2`.
  - Firewall script: dry-runs with stub `iptables`, `ipset`, `getent` and `conntrack` binaries. The A/B chain
    switch, the conntrack handling and the missing-config exit (rc=2) all behave as intended.
- **Reviews.** Each round used new independent reviewers:

  | Round | Commit | Spec | Security |
  |---|---|---|---|
  | 1 | `4897972` | PASS | PASS |
  | 2 | `c1c67f5` | FAIL: the firewall unit's `ConditionPathExists` let Docker start without rules | FAIL: same finding |
  | 3 | `7f450ce` | pending | PASS (non-blocking findings only) |

  After round 1 both reviewers passed, but the hardening they suggested was applied anyway, which is why round 2
  ran. Round 2's blocking finding is fixed in `7f450ce`.

- **Non-blocking follow-ups (not done here):**
  - Match the reserved database host on its first DNS label, so `postgres.coolify` is also refused.
  - Have `refresh` re-run `apply` if a firewall reload removed the hook, or state that firewalld must not be used.
  - Give `private` a fixed bridge name and protect its gateway in INPUT.
  - Add a host check that Coolify attached no extra network to the worker or Postgres.
  - Have the execution runtime check that it runs the record's bound release (in `provider_ports.py`, outside this
    lane).

## 3. Exact host steps for the operator (all NOT RUN)

Full commands are in `HOSTED_RECORD_V2_RUNBOOK.md`.

1. **Backups (§5).**
   - Take a Contabo panel snapshot named `edge-os-<UTC>-<sha>`.
   - Dump the database: `docker exec <postgres> pg_dump -Fc -U edge_os -d edge_os > /var/backups/edge-os/edge_os-<UTC>.dump`.
   - Run the restore drill in `edge-os-restore-drill`, started with `--network none` from the same image digest. Use
     TCP `pg_isready -h 127.0.0.1` and then `pg_restore --no-owner --exit-on-error`.
   - Compare `alembic_version` and one known row, then record the dump SHA-256, the recovery point and the restore
     time.
2. **Firewall (§4.1), before any deploy that creates `edgeos-egress`.**
   - `apt-get install -y ipset conntrack`.
   - Write `/etc/edge-os/egress.env` (root, 0600) with `EDGE_OS_EGRESS_HOSTS="api.privy.io <Monad RPC host>"` and
     `EDGE_OS_EGRESS_PORTS="443"`.
   - Install the three units from `/opt/edge-os/deploy/host/` into `/etc/systemd/system/`, run
     `systemctl daemon-reload`, then
     `systemctl enable --now edge-os-egress-firewall.service edge-os-egress-refresh.timer`.
   - Requires Docker's iptables backend and Docker Engine 28.0 or newer.
3. **TLS (§3.1).** Recreate `/etc/edge-os/postgres-tls/server.{crt,key}` with
   `subjectAltName=DNS:edge-os-postgres,IP:127.0.0.1`. Ownership is 999:999, the key is 0600 and the certificate
   0644.
4. **Coolify.** Set
   `EDGE_OS_DATABASE_URL=postgresql+psycopg://edge_os:<URL-encoded password>@edge-os-postgres:5432/edge_os?sslmode=require`,
   then deploy the new compose file with the image digests filled in literally.
5. **Checks (§2, §3, §4.1).**
   - `edge-os-postgres` resolves from the API to the `private` network address and is not on the `coolify` network.
   - `ss -ltnp | grep 5432` shows only `127.0.0.1:5432`, and `nc -vz <public IP> 5432` fails from outside.
   - `ip link show edgeos-egress` and `ip link show edgeos-hostdb` both exist.
   - From the worker, `api.privy.io` answers, while `example.com` and `10.203.0.1:22` fail.
   - From Postgres, `10.203.0.17:22` and `1.1.1.1:443` fail.
   - Repeat these checks after a reboot.
6. **Keep disabled:** controlled execution (the worker stays `EDGE_OS_EXECUTION_MODE: unavailable`) and the host
   research worker (§3.2). Hand record v2 to the builder for approval. Registering the record and the execution
   release are separate reviewed code changes.
