# Runtime guards (local, enforced in code)

All guards use the existing FastAPI/SQLAlchemy/PostgreSQL stack. No new dependency was added.

## Shared quotas (`edge_os_api/usage/quota.py`, migration 0010)

- **Scopes:** each resource (`provider_requests`, `compute_seconds`) has one GLOBAL allocation and one OWNER allocation per owner.
- **Reservation:** a reservation binds the owner and one original subject. A research job is subject `investigation_job:<job_id>`, unique.
  - It takes row locks in one fixed order: GLOBAL first, then OWNER.
  - It checks both caps before any adapter call.
  - It is taken in the same transaction as the saved job, so a crash before commit reserves nothing.
- **Settlement:** each resource settles once; a repeat changes nothing.
  - Known usage consumes all measured use, releases only the unused part and records any excess as overrun.
  - Missing or invalid usage, a timeout, a killed process, a lost result or an interrupted calculation keeps the whole open amount as unknown liability.
- **Caps:** each cap is frozen when its allocation is first used.
  - A different configured value is never applied silently. New reservations against that allocation return 503 `quota_cap_mismatch`.
  - A GLOBAL mismatch affects every owner: `/readyz` returns 503 `quota_cap_mismatch` with the affected resources.
  - An OWNER mismatch affects only that owner: `/readyz` stays ready and adds `attention.owner_quota_cap_mismatch` with a count per resource (no owner id or value). Only that owner's new research starts pause.
  - Settlement never compares caps. A reservation taken before a cap change settles normally, so a running job never stays open because of a cap change.
  - An operator changes a cap only through `python -m edge_os_api.usage.quota set-cap --scope … --resource … --cap N --reason …`, which appends a `CAP_CHANGED` event. A cap recorded this way is authoritative: it is not compared with configuration again.
- **No resets:** nothing resets, renews or credits capacity. A request body, a new process or a new request key cannot change an allocation.
- **Allocation meaning:** owner caps (`EDGE_OS_RESEARCH_BUDGET_*`) and the global caps (`EDGE_OS_USAGE_GLOBAL_*`) are total lifetime allowances for this deployment, not paid plans or periods. Values for a public deployment belong to the later configuration packet.
- **Compute measurement:** tools record milliseconds, and a job settles `ceil(total_ms / 1000)` seconds.

## Request and job bounds

| Guard | Setting (default) | Behavior |
|---|---|---|
| Body size | built in (256 KiB) | 422 `body_too_large` |
| Writes per owner per minute, shared by all API processes (`usage_local.request_windows`) | `EDGE_OS_WRITE_RATE_PER_MINUTE` (600) | 429 `rate_limited` with `Retry-After`; reads are not limited |
| Research jobs waiting or running per owner (counted under the owner's quota locks) | `EDGE_OS_RESEARCH_MAX_ACTIVE_JOBS` (10) | 409 `too_many_active_jobs`, nothing reserved |
| Longest SQL statement | `EDGE_OS_DATABASE_STATEMENT_TIMEOUT_MS` (30000) | statement cancelled → 503 |
| Job deadline | declared per job (≤ 3600 s) | `DEADLINE_EXCEEDED`, liability rules above |

## Startup and readiness

- **Production startup refuses** each of the following. Messages name the setting only, never its value:
  - fixture, recorded and `hermes_local` modes;
  - fixture wallet and execution providers and fixture effects;
  - wildcard or non-https CORS;
  - the test Privy app id;
  - a missing build identity;
  - a loopback database;
  - a database URL without `sslmode=require` or stricter.
- **Open decision:** the deterministic fixture interpreter (`EDGE_OS_INTERPRETER=fixture`, records labelled `p03-fixture-interpreter/1`) stays the only interpreter production accepts, under the earlier accepted rule. Stage 2 does not change it. Refusing it too would stop every production start until a qualified interpreter exists; that is a controller decision.
- **`/readyz`** returns 503 with one reason: `database_unavailable`, `schema_drift`, `verification_keys_missing` or `quota_cap_mismatch` (GLOBAL caps only). OWNER cap mismatches appear under `attention` in a ready reply.
- **Workers** (`edge_os_api.execution.worker`, `edge_os_api.research.investigation_jobs`) check the schema head before every pass.
  - On drift they stop before any effect (exit code 3). An unreachable database skips the pass.
  - Saved jobs, attempts and original actions stay, and a restart after migration recovers them.

## Not covered here

- F3 (original transaction references for every real transport) is reserved for Stage 3: the signing/adapter seam is not changed in this milestone.
- Hosted multi-process load, provider-side spending caps and real authentication remain hosted checks.

## Research findings closed in this milestone

- **G-N2 (interrupted comparison compute):** a job settles its compute as unknown liability, never as released capacity, when any tool attempt is unmeasured. That covers three cases: an attempt reconciled as interrupted or unknown; an attempt that started and never finished, whether a restart, a cancel or the deadline ends the job; and an attempt that finished without a compute measurement, such as a failed comparison. Tests: `test_interrupted_comparison_keeps_its_compute_as_unknown_liability`, `test_a_killed_comparison_then_cancel_or_deadline_keeps_compute_unknown`, `test_a_failed_comparison_keeps_its_unmeasured_compute_unknown`.
- **N4 (one-second overrun):** tools record milliseconds and settle `ceil(total_ms / 1000)` seconds. A known overrun is booked in full and recorded as overrun; it is never hidden or released.
- **Immutable caps:** see "Caps" above.
- **G-N1 (compute/deadline mismatch in the actual-data proposal):** the research proposal (`.scratch/…/r58-research/evidence/ACTUAL_DATA_AUTHORIZATION_PACKET.md` §6, frozen and not edited) gives a 1,800 s deadline but no compute reservation. The job API accepts `compute_seconds` ≤ 600 and `deadline_seconds` ≤ 3600. Compute is measured as the wall time of the job's tool calls, including provider pacing. With a 1,800 s deadline and a 600 s reservation, up to 1,200 s could be booked as overrun.
  - **Corrected resource bounds for any later actual-data packet:** `compute_seconds = 600` and `deadline_seconds = 600`. Then the reservation covers the whole run, and the deadline ends the job before the reservation can overrun.
  - At the proposal's pacing (at most 10 HyperSync requests per minute, at most 20 HyperSync requests), collection needs about two minutes.
  - The owner budget must hold at least 600 compute seconds and 36 provider requests.
  - A larger run needs a separate reviewed bounds decision. This milestone does not authorize actual-data collection.
