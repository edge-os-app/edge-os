# LOCAL Docker rehearsal (#58 DOCKER-REHEARSAL-L4)

Task DOCKER-REHEARSAL-L4-20261013-LOCAL-v1, issue edge-os-app/edge-os#58 (with #47/#48 host preparation). Base `ff1d958c47f2891707b4aa9b5b06541eb5289633`. LOCAL fixture profile only.

## What this adds

| Path | Responsibility |
|---|---|
| `deploy/docker/api.Dockerfile` | API image: Python 3.14 (digest-pinned), frozen `uv.lock`, runtime contract/qualification/fixture assets, non-root uid 10001 |
| `apps/web/Dockerfile` | Web image: Node 24.13.1 (digest-pinned), `npm ci --ignore-scripts`, public build values only, non-root `node` |
| `.dockerignore` | Allow-list build context |
| `compose.local.yml` | Private topology: PostgreSQL 18, explicit `migrate`, API, web, loopback `entry`, research/execution/recurring worker roles |
| `deploy/local/public_entry.py`, `deploy/local/http_probe.py` | Standard-library loopback entry and container health probe (bounded refusal of oversized bodies, below) |
| `deploy/local/RUNBOOK.md` | Manual order, configuration ownership, backup/restore rules and limits |
| `scripts/deployment_rehearsal/` | Run-owned rehearsal driver: stacks, image inspection, identity snapshots, backup/restore |
| `tests/deployment_rehearsal/` | Guards (topology, secret mapping, settings refusals, image definitions, exact build context, entry, restore and cleanup rules) and the GET-only browser reopen spec |
| `FEATURE_MAP_PROPOSAL.md` | Proposed map row for lane 2 |

Application, settings, schema, migrations, research, usage, Hermes, verifier map and lockfiles are unchanged.

## Rehearsal sequence and pre-agreed seams

1. **Fresh image build and configuration.** No-cache builds from the committed source and frozen locks. Image labels carry the commit; runtime users are non-root; the API image opens every module-path asset; an export of each image is searched for the run's database passwords, synthetic key material and tokens, for private-key blocks in the application tree, and for the test-auth label in the web bundle.
2. **Migration and readiness guards.** Before the explicit migration the API exits (`schema revision ... does not match migration head`) and each worker role exits 3 before any effect. The same LOCAL settings are refused as production (`sslmode=require`, fixture modes, test app id, HTTPS origins) and `EDGE_OS_PRIVY_APP_SECRET` is refused. One `migrate` run reaches head and `alembic check` reports no difference. `/readyz` answers ready at head through the loopback entry.
3. **Ports, permissions and secrets.** Only `entry` publishes a port, on 127.0.0.1. Application, database and worker containers sit on an internal network with no host path or Docker socket. The application and worker containers (API, web, entry, migrate and the three worker roles) also run non-root with read-only roots and all capabilities dropped. PostgreSQL uses the official image defaults: its entrypoint starts as root and runs the server as the `postgres` user, with a writable root and default capabilities; it stays private on the internal network. The database password reaches only `postgres` and the composed database URL; the web container gets no Edge OS configuration.
4. **Browser-saved records.** The accepted `research-history-journey`, `research-history-report` and `recurring-journey` specs run unchanged through the packaged web/API at 1280px and 390px. A verifier-only fault kills a research worker container after its collection attempt is saved (exit 9); the packaged research worker reconciles it as held unknown liability. The packaged recurring producer and execution worker record an occurrence per deployment with no browser open.
5. **Process replacement and durability.** API, web and entry containers are recreated and PostgreSQL restarts on its named volume. Every table hash and named identity is unchanged. The GET-only reopen spec then reopens the saved report, jobs, held unknown, revision, labelled replay and recurring deployment, checks keyboard focus and names, axe serious/critical violations, sideways scroll at 390px, console errors and failed responses, and another owner's `This request was not found.` refusal. Direct SQL shows the reopen changed nothing.
6. **Fresh-database restore with no new effects.** `pg_dump -Fc` of the primary database into a private file; the primary stack stops; a separately owned Compose project starts a new, empty, run-named database with a new password; a guarded `pg_restore` (refuses the source name, a non-run name or a non-empty target); `alembic check` without upgrade; API/web/entry start, no worker role starts. Restored identities equal the pre-backup identities; the reopen spec runs again; direct SQL again shows no change.
7. **Cleanup.** Both projects are removed with their volumes and networks, then the run's two image tags. Every resource that still carries this run's `edge-os.rehearsal.run` label is a leftover and fails the run. A resource with exactly one recognized run label of another owner (`edge-os.rehearsal.run` of another run, `edge-os.test.run` of a P03/P05/pytest run, `edge-os.hermes-relay` of a lane-1 relay run) is accounted to that run and listed under `other_runs` in the cleanup step; its labels also stay in `resources-before.json`, `resources-after.json` and `docker-events.jsonl`. A resource with no recognized run label, or with several (conflicting) run labels, that appears or disappears fails the run. Daemon create/remove events are kept for attribution.

Compared identities: schema head; every table in `public` and each `*_local` schema (row count and content MD5); owners; requests (record type and content hash); revisions; investigation reports; replays; recurring deployments (state, consent hash, occurrences, missed slots); investigation jobs (kind, state, terminal reason); usage caps (reserved, consumed, unknown, overrun); reservations; jobs holding unknown liability.

## Evidence

Private evidence stays outside the repository: `<evidence-root>/<run_id>/` holds `run-identity.json` (commit, tree, tools, build-context fingerprint), `steps.json`, `summary.json`, `image-identities.json`, `image-secret-scan.json`, `topology-primary.json`, `topology-restored.json`, `identities/*.json`, `ui/` (accepted specs' results and screenshots), `browser-after-replacement/` and `browser-restored/` (reopen results and screenshots), `logs/`, `docker-events.jsonl`, `resources-before.json`, `resources-after.json`, and `private/<database>.dump`. The candidate run IDs and results are reported in the gate packet, not in this file.

## Oversized bodies at the loopback entry (LOCAL bound)

The entry refuses a declared body above 512 KiB with `413` and never contacts the API or web for it. So that a client which sends its whole body before reading still receives the `413` (instead of a connection reset), the entry reads and discards a refused body of up to 8 MiB in 64 KiB chunks, within one total deadline of 5 seconds measured on a monotonic clock. The remaining time is recomputed before every socket read, so a slow drip cannot extend it. A sender that stalls, drips past the deadline or ends its body early is disconnected without a reply. A declared body above 8 MiB is refused at once without reading it. These are LOCAL rehearsal bounds: 8 MiB is not an accepted body size, and the entry is not a production or TLS proxy; whole-server concurrency and exhaustion limits are not qualified. Tests: `tests/deployment_rehearsal/test_public_entry.py`.

## Limits (NOT_RUN or not claimed)

- Hermes job path: not packaged. The accepted runner needs the trusted host supervisor/relay interface (lane 1). The remaining connection is a supervisor process outside the public API that launches the pinned job containers and owns the relay; this profile runs the `fixture` interpreter and gives no container the Docker socket.
- Production qualification, Contabo host, public HTTPS/DNS, actual egress controls, off-host encrypted backup, retention and recovery-point bounds, real Privy sign-in, providers, models, wallets, funds and judge access.
- Participants, physical phones and screen readers: NOT_RUN. Automated axe checks are necessary, not sufficient.
- Video recording: not done.
