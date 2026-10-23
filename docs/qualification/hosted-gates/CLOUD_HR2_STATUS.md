# CLOUD-HR2 status: hosted deployment record v2

Branch `cloud/hosted-record-v2`, base `origin/integration/edge-os-mvp` at `82290e203982ee710189c4d983edce9a4ddfba9f`.
Normal pushes to this branch only. No PR, no merge, no main or integration push. No network, provider, credential,
key or VPS access was used. Both registries (`APPROVED_HOSTED_DEPLOYMENTS`, `APPROVED_ACTUAL_RELEASES`) stay empty.

## 1. What this lane is waiting for

**Review:** round 4 is running on the repaired candidate (the commit that adds this text). Round 3 at `7f450ce`
ended with security PASS and spec FAIL. The spec failure was in the runbook: containers were chosen by the Compose
service label alone, which can select Coolify's own `postgres` service, and the negative checks counted a failed
`docker exec` as "blocked". If both new reviewers pass the same commit, the lane is done; otherwise the lane repairs
and reviews again.

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

- **Candidate:** the head of `cloud/hosted-record-v2` that adds this text (round 4). The RED tests are commit
  `46c95a5` (tests only), followed by `4897972`, `c1c67f5`, `7f450ce`, `dccb7b5` (this status file only) and the
  round-3 repair.
- **Files changed (since 82290e2):**
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
  - `docs/qualification/hosted-gates/CLOUD_HR2_STATUS.md` (this file)
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
  | 3 | `7f450ce` | FAIL: runbook container selection and false-pass checks | PASS (non-blocking findings only) |
  | 4 | the round-3 repair | pending | pending |

  After round 1 both reviewers passed, but the hardening they suggested was applied anyway, which is why round 2
  ran. Round 2's blocking finding is fixed in `7f450ce`. The round-3 repair adds runbook §1a: containers are
  selected inside this stack's Compose project, found from the `edgeos-hostdb` bridge, with exactly one per
  service, and a check passes only when the connection itself fails. It also adds:
  - a check that Coolify attached no extra network
  - `docker rm -fv` for the drill container
  - a complete TLS snippet
  - a root-owned firewall script at `/usr/local/sbin/edge-os-egress-firewall`
  - notes that reload cuts open connections and that the stack runs once per host

- **Non-blocking follow-ups (not done here):**
  - Match the reserved database host on its first DNS label, so `postgres.coolify` is also refused.
  - Have `refresh` re-run `apply` if a firewall reload removed the hook, or state that firewalld must not be used.
  - Give `private` a fixed bridge name and protect its gateway in INPUT.
  - Add a host check that Coolify attached no extra network to the worker or Postgres.
  - Have the execution runtime check that it runs the record's bound release (in `provider_ports.py`, outside this
    lane).

## 3. Exact host steps for the operator (all NOT RUN)

Full commands are in `HOSTED_RECORD_V2_RUNBOOK.md`. Define the §1a helpers (`PROJECT`, `one`, `must_fail`) before
running any host command.

1. **Backups (§5).**
   - Take a Contabo panel snapshot named `edge-os-<UTC>-<sha>`.
   - Dump the database: `docker exec "$PG" pg_dump -Fc -U edge_os -d edge_os > /var/backups/edge-os/edge_os-<UTC>.dump`.
   - Run the restore drill in `edge-os-restore-drill`, started with `--network none` from the same image digest. Use
     TCP `pg_isready -h 127.0.0.1` and then `pg_restore --no-owner --exit-on-error`.
   - Compare `alembic_version` and one known row, then record the dump SHA-256, the recovery point and the restore
     time.
2. **Firewall (§4.1), before any deploy that creates `edgeos-egress`.**
   - `apt-get install -y ipset conntrack`.
   - Write `/etc/edge-os/egress.env` (root, 0600) with `EDGE_OS_EGRESS_HOSTS="api.privy.io <Monad RPC host>"` and
     `EDGE_OS_EGRESS_PORTS="443"`.
   - Install the script, root-owned, as `/usr/local/sbin/edge-os-egress-firewall`, and the three units from
     `/opt/edge-os/deploy/host/` into `/etc/systemd/system/`. Then run
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
   - `edge-os-postgres` resolves from the API to our Postgres container's `private` address, and no container on the
     `coolify` network carries that name.
   - The worker is attached to exactly `private` and `egress`, and Postgres to exactly `private` and `hostdb`.
   - `ss -ltnp | grep 5432` shows only `127.0.0.1:5432`, and `nc -vz <public IP> 5432` fails from outside.
   - `ip link show edgeos-egress` and `ip link show edgeos-hostdb` both exist.
   - From the worker, `api.privy.io` answers, while `example.com` and `10.203.0.1:22` fail.
   - From Postgres, `10.203.0.17:22` and `1.1.1.1:443` fail.
   - Repeat these checks after a reboot.
6. **Keep disabled:** controlled execution (the worker stays `EDGE_OS_EXECUTION_MODE: unavailable`) and the host
   research worker (§3.2). Hand record v2 to the builder for approval. Registering the record and the execution
   release are separate reviewed code changes.
