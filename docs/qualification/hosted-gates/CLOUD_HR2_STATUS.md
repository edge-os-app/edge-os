# CLOUD-HR2 status: hosted deployment record v2

Branch `cloud/hosted-record-v2`, base `origin/integration/edge-os-mvp` at `82290e203982ee710189c4d983edce9a4ddfba9f`.
Normal pushes to this branch only. No PR, no merge, no main or integration push. No network, provider, credential,
key or VPS access was used. Both registries (`APPROVED_HOSTED_DEPLOYMENTS`, `APPROVED_ACTUAL_RELEASES`) stay empty.

## 1. What this lane is waiting for

**Review: done.** Both independent round-6 reviewers PASSED the same commit, **`555353e`**, the final reviewed
candidate. It includes the builder's option A. The commit that adds this text changes only this status file.

The lane is not blocked.

**Builder decision applied: the host research worker's loopback route, option A.** In production, `core/settings.py`
admits the database host `127.0.0.1` only when:

- a hosted deployment record registered in `APPROVED_HOSTED_DEPLOYMENTS` is named and passes every record check;
- the URL's `sslmode` equals the record's TLS mode.

Every other case keeps the refusal `database_url: production needs a hosted database, not a loopback host`: no named
record, an unregistered record, a different `sslmode`, `localhost`, or a host-less socket URL. Non-loopback hosts are
unchanged, and a v1 record still grants no execution. The registry stays empty, so production still refuses the route
until the builder's record is registered. The research worker unit stays disabled until then.

## 2. Candidate, files, tests, verdicts

- **Final reviewed candidate:** `555353e`. `056dd65` was the round-5 PASS candidate, before option A. The RED tests are commit
  `46c95a5` (tests only), followed by `4897972`, `c1c67f5`, `7f450ce`, `dccb7b5` (this status file only),
  `7ca2a4f`, `056dd65` (the round-4 repair), `a838461` (status only), `2d334b4` (option A RED tests) and the
  `555353e` (the option A implementation).
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
    files (185 after the round-4 repair, 194 with option A). `docker compose config` runs inside these tests; only the Docker CLI is present, with no daemon.
  - Full: `cd apps/api && uv run --frozen pytest -q -p no:cacheprovider` gives 2558 passed, 1 skipped, 14 failed and
    1264 errors at `056dd65`. The 1264 errors are database fixtures that need a Docker daemon, which this container does not
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
  | 4 | `7ca2a4f` | FAIL: `must_fail` counted a Docker CLI failure as blocked | FAIL: same finding |
  | 5 | `056dd65` | **PASS** (non-blocking findings only) | **PASS** (non-blocking findings only) |
  | 6 | `555353e` | **PASS** (non-blocking findings only) | **PASS** (non-blocking findings only) |

  After round 1 both reviewers passed, but the hardening they suggested was applied anyway, which is why round 2
  ran. Round 2's blocking finding is fixed in `7f450ce`. The round-3 repair adds runbook §1a: containers are
  selected inside this stack's Compose project, found from the `edgeos-hostdb` bridge, with exactly one per
  service. The round-4 repair makes a check pass only on the probe's own timeout code from a selected, running
  container. It also:
  - gives `private` a fixed bridge (`edgeos-private`, `10.203.0.64/26`) whose gateway is kept off host services
  - refuses `host`/`hostaddr` query keys in the production database URL
  - makes the collision check fail closed
  - follows Docker's resolver-file rule
  - hardens the drill (no stale container, a bounded wait)

  The round-3 repair also added:
  - a check that Coolify attached no extra network
  - `docker rm -fv` for the drill container
  - a complete TLS snippet
  - a root-owned firewall script at `/usr/local/sbin/edge-os-egress-firewall`
  - notes that reload cuts open connections and that the stack runs once per host

- **Correction to the option A wording (found in round 6; the code gap predates this lane).**
  - **The overstatement:** the `settings.py` comment, `HOSTED_RECORD_V2_RUNBOOK.md` §3.2 and `CONTRACT.md` §5.5 say
    every other loopback form is refused.
  - **What the code does:** today's production rule, unchanged since `82290e2`, refuses only the exact hosts
    `127.0.0.1`, `localhost` and no host.
  - **What it misses:**
    - other spellings: `LOCALHOST`, `localhost.`, `127.0.0.1.`, `127.1`;
    - other loopback addresses: `127.0.0.2`, `[::1]`;
    - `0.0.0.0` and a multi-host `127.0.0.1,db.example`.

    These were already admitted before this lane, and still are, with or without a record.
  - **What option A added:** exactly one admitted case, `127.0.0.1` with a registered record and its TLS mode.
    Both reviewers confirmed this by comparing `056dd65` against `555353e`.
  - **Resolved in lane `cloud/loopback-strict` (builder-approved 2026-10-23):** production now refuses every loopback,
    unspecified or multi-host database host, record or not, except option A's literal `127.0.0.1` with a registered
    record and matching `sslmode`; the comment and both passages state that rule (`HOSTED_RECORD_V2_RUNBOOK.md` §3.2, `CONTRACT.md` §5.5).
  - **Original recommended follow-up (it widens a production refusal, so the builder decides):**
    - normalise the host (`rstrip(".").lower()`) and refuse any loopback or unspecified address
      (`ipaddress.ip_address`, plus short IPv4 forms);
    - refuse multi-host URLs;
    - optionally require port 5432 on the loopback route;
    - add RED tests for each of these forms;
    - correct the three texts.
- **Non-blocking follow-ups (not done here).** These are the round-5 findings, all non-blocking; fixing them
  would reopen the review of `056dd65`:
  - Add `enable_ipv6: false` to the `private` network, matching `egress` and `hostdb`; runbook §4.1 says "both
    networks".
  - Also flush the `private` subnet from conntrack in `apply` (`10.203.0.64`, `--mask-src 255.255.255.192`).
  - Probe the fixed `private` gateway `10.203.0.65` directly, or print FAIL when no gateway is reported, so the
    check never silently skips.
  - Make the §2 "must be equal" alias comparison print an explicit pass or FAIL.
  - State that `SH_PROBE` takes IP literals only.
  - Log a warning when a host resolves to no address in `refresh`.
  - Add a local `pg_isready -h 127.0.0.1 -p 5432` check to §3.

  Earlier rounds also left these:
  - Match the reserved database host on its first DNS label, so `postgres.coolify` is also refused.
  - Have `refresh` re-run `apply` if a firewall reload removed the hook, or state that firewalld must not be used.
  - Have the execution runtime check that it runs the record's bound release, and update the stale "local and test
    only" docstring for `controlled` (both in `provider_ports.py`, outside this lane).

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
   - From the worker, `api.privy.io` answers. Every `must_fail` probe prints `pass: blocked`: from the worker,
     `example.com:443`, `10.203.0.1:22` and the `private` gateway on port 22; from Postgres, `10.203.0.17:22` and
     `1.1.1.1:443`.
   - `ip link show edgeos-private` also exists.
   - Repeat these checks after a reboot.
6. **Keep disabled:** controlled execution (the worker stays `EDGE_OS_EXECUTION_MODE: unavailable`) and the host
   research worker until the builder's record is registered and its URL meets §3.2. Hand record v2 to the builder for approval. Registering the record and the execution
   release are separate reviewed code changes.
