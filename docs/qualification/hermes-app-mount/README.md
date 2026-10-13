# Hermes application mount (LOCAL, AUTHORED transport)

Task `RELEASE-E2E-L2-20261013-HERMES-MOUNT-LOCAL-v1` (#58 support). Status: LOCAL preparation, shown with authored replies, a dummy credential and no network. It is not an actual-data, actual-model or public proof. It gives no authority: no live request, credential, network, spending or deployment.

| File | What it holds |
|---|---|
| `CONTRACT.md` | The composition, the spend reservation interface, the fault matrix and the file plan, written before code, with amendments. |
| `README.md` | What is mounted, what the tests show, how to check and the limits. |

## 1. What is mounted

The accepted transport job (`scripts/hermes_job_support/transport_turn_runner.py::build_transport_job`) now runs behind the saved Research path through the existing seam:

```python
mount = open_transport_mount(settings, limits=SpendLimits(global_cap_usd, owner_cap_usd, price), image=..., run_id=...,
                             evidence_dir=..., script_for=..., credential_file=...)
app = create_app(settings, hermes_runner=mount.runner)   # EDGE_OS_INTERPRETER=hermes_local
```

- `apps/api/src/edge_os_api/research/hermes_transport_mount.py` composes the accepted `GuardedTurnRunner`, `TransportTurnRunner` and container job, and adds no runner of its own. It refuses production, another interpreter, an ACTUAL route and a policy that does not match the application's interpreter before any effect. The spend scope is the saved request of the recorded attempt. At open it runs one recovery pass (budget C) for this `run_id`.
- `apps/api/src/edge_os_api/research/provider_spend_ledger.py` is the shared spend ledger: the accepted `SpendLedger` methods, results and exceptions on PostgreSQL, with an owner cap and a global cap. Every write locks one settings row, so all API processes share one cap. Caps and prices freeze at first use; a different configured value refuses new reservations until `change_caps` records a decision.
- Migration `0013` adds `usage_local.provider_spend_settings`, `provider_spend_reservations` and `provider_spend_events` (append-only). Its downgrade refuses while any reservation or spend event exists.
- A public attempt gains a read-only `spend` field (`state`, `charge_usd`) from the values the accepted runner saved. The web client is unchanged.

Startable LOCAL composition: `scripts/hermes_app_mount/serve_transport_mount.py` runs one API process over the mount with an authored script queue (section 3). The mapped verifier's HERMES-MOUNT phase, right after P05, drives it in the browser (`scripts/p03/hermes_app_mount_phase.py`, `tests/p03/hermes-transport-mount*.spec.mjs`, feature-map row "Hermes transport mount"). Settings, `main.py`, the accepted `scripts/` code, `usage/`, the investigation job engine and the web client are unchanged.

## 2. What the tests show

Fast, no Docker (`apps/api/tests`, part of the full API suite):

- `test_provider_spend_ledger.py`: worst-case reservation before any request; owner cap and global cap across two owners; one reservation per attempt, one open liability per scope, saved attempts only; exact settlement, unusable usage kept, release only while RESERVED, duplicate and conflicting late evidence; a changed configured cap or price refused until a recorded change, which then applies, while old reservations still settle; a new connection sees the same liability; two separate OS processes contending for the last capacity grant exactly what both caps allow. Removing the settings-row lock makes the two-process test fail.
- `test_hermes_transport_mount.py`: every refusal happens before an engine or a folder exists; the real composition over a stand-in job saves, charges exactly and reopens in a new application with owner denial; a lost reply is UNKNOWN, never accepted and not retried; a retry is a new attempt that held liability refuses before any job, and runs once after a released attempt; a report for another attempt is withheld; an exhausted owner cap refuses before the job while another owner continues.

ACTUAL pinned Hermes in a no-egress container (`tests/hermes_app_mount`, Docker):

- one saved request runs one job: the saved transport attempt id, the request attempt ids, the wire `session_id` and the job's own request file all name the saved attempt; exact charge; reopen from another application with owner denial and no model call; the dummy credential is absent from evidence, the database and logs;
- a lost reply is UNKNOWN with its full reservation, nothing published, no retry;
- a hung provider is stopped at D and keeps its reservation;
- two separate API processes (own run ids, one database) and two owners send six requests at once: three run with one request each, three are refused before any job, and neither cap is passed;
- an API process killed mid-turn leaves its container and a RESERVED liability; restarted with the same run id, it stops its own container within C at startup, shows the attempt INTERRUPTED, refuses its replay and serves another saved request.

Not shown: any real provider, model, network, price, provider billing stop or hosted behavior.

## 3. How to check

From `apps/api`, with the locked environment:

```
uv run --frozen pytest -p no:cacheprovider -q tests/test_provider_spend_ledger.py tests/test_hermes_transport_mount.py
HERMES_APP_MOUNT_EVIDENCE_DIR=<private folder> uv run --frozen pytest -p no:cacheprovider -q ../../tests/hermes_app_mount
uv run --frozen pytest -p no:cacheprovider -q tests/provider_safeguards ../../tests/hermes_interpretation/provider_safeguards ../../tests/hermes_job_support
```

The second and third commands need Docker. They build the pinned Hermes image from `git archive` of the pinned commit and remove their own image and containers by exact tag and label.

The full mapped verifier (`uv run --frozen python ../../scripts/p03/verify_run.py --run-id <fresh> --evidence-root <private folder>`) runs the HERMES-MOUNT phase after P05: browser save, attempt and usage, reopen in a new context, another owner refused, a lost reply kept unknown, a restart with the same run id and an unchanged reopen, with SQL against attempts, spend rows and the job's request files (`hermes-mount-*.json` in the run's evidence).

To start the mount yourself (LOCAL only, migrated database, a built pinned image, the usual `EDGE_OS_*` environment):

```
EDGE_OS_INTERPRETER=hermes_local uv run --frozen python ../../scripts/hermes_app_mount/serve_transport_mount.py --port 8000 \
  --image <pinned image tag> --run-id <stable id for this process> --evidence-dir <private folder>/turns \
  --script-file <private folder>/script.json --credential-file <private dummy file> --report-file <private folder>/startup.json \
  --global-cap 0.50 --owner-cap 0.25
```

The script file is a JSON list of `{"case": "<authored case>"}` items (optionally with `"transport_fault"`), one per model turn.

## 4. Limits

- LOCAL only. The mount and the spend ledger add `scripts/` folders to the import path at import time and reuse three private helpers of the accepted `spend_ledger` module; the application factory and `migrations/env.py` do not import them. Package these types properly before any hosted step. The mount is refused in production. Only the AUTHORED transport exists.
- Each API process needs its own stable `run_id`. Two processes that share one are still safe, but their turns serialize (`CleanupPending`).
- The local cap does not cap provider billing. A killed non-streaming request may still be billed (P05 known limit). An UNKNOWN reservation is resolved only by late evidence; a decision path for it is not built.
- Zero-request release relies on counts written inside the job process: the guard's count, the transport's sent count and Hermes' count must all be 0. An ACTUAL route needs independent evidence first.
- The ledger sums reservations under its lock; this is linear in the number of reservations.
- The `spend` field is null when an attempt saved no spend state (refused before reserving, or interrupted by a crash). The ledger still holds a crashed attempt's reservation.
