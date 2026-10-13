# Hermes application mount: runner composition and shared spend reservation (contract)

Task `RELEASE-E2E-L2-20261013-HERMES-MOUNT-LOCAL-v1` (#58 support). Status: LOCAL, AUTHORED transport only, no egress. Written before code on base `da59f3193b272274fd74c434698df8d404fba0bc`. This note gives no authority: no actual provider, model, network, credential, spending or public operation. Production and every ACTUAL route stay refused.

## 1. Sources and the choice of storage

- Accepted transport job: `scripts/hermes_job_support/transport_turn_runner.py::build_transport_job` and its README section 2 (the lane-2 contract). Used unchanged.
- Accepted guarded runner and SQLite `SpendLedger`: `scripts/hermes_interpretation/{guarded_turn_runner,spend_ledger}.py`. Used unchanged; their rules are the rules below.
- Accepted hosting assessment (`docs/qualification/hermes-provider/HOSTING_ASSESSMENT.md`, sections 2 and 3): the durable spend ledger is "one shared PostgreSQL table with the same reserve, settle, release and reconcile rules, and the same atomicity", "a PostgreSQL implementation of the ledger behind the same methods".
- Private release plan Stage 2: shared PostgreSQL usage storage with owner and global reservations, reserved atomically before provider invocation; missing usage and timeouts keep full liability; attempts to raise caps are tested.

Choice: a PostgreSQL spend ledger with the same methods and exceptions as `SpendLedger`, in new tables created by migration `0013`. The SQLite file stays test support. The existing `usage/quota.py` framework is not reused: its resources are a fixed list in read-only code, and its settlement rules differ (no scope block, no release-only-when-unsent, no late reconcile). Its proven patterns are copied: one lock order, caps frozen at first use, an explicit recorded cap change.

## 2. Composition (the mount)

New module `apps/api/src/edge_os_api/research/hermes_transport_mount.py`:

```python
@dataclass(frozen=True)
class SpendLimits:
    global_cap_usd: Decimal      # every owner together
    owner_cap_usd: Decimal       # each owner
    price: TokenPrice            # accepted spend_ledger.TokenPrice

def open_transport_mount(settings: Settings, *, limits: SpendLimits, image: str, run_id: str, evidence_dir: Path,
                         script_for: Callable[[HermesTurn], Mapping[str, Any]], credential_file: Path | None = None,
                         route: TransportRoute = AUTHORED_ROUTE, policy: GuardPolicy = DEFAULT_POLICY,
                         timeout_seconds: float = 90, run_budget_seconds: int = 60, seal_grace_seconds: float = 5.0,
                         recovery_budget_seconds: float = 5.0) -> HermesTransportMount

@dataclass
class HermesTransportMount:
    runner: HermesTurnRunner              # the accepted GuardedTurnRunner; give it to create_app(settings, hermes_runner=...)
    supervision: GuardedDockerTurnRunner  # recover_pending, pending_cleanup, retry_exhausted, purge_quarantine
    spend: PostgresSpendLedger
    startup_recovery: list[dict]          # pending_cleanup() after the one recovery pass made at open
    def close(self) -> None               # disposes the mount's own database engine
```

Order inside `open_transport_mount`:

1. Refuse, before any effect (no engine, no file, no Docker command): `settings.env == "production"`, `settings.interpreter != "hermes_local"`, a route whose kind is not `AUTHORED` (the accepted `ActualProviderUnavailable`), and a policy whose model or output limit differs from the application's interpreter configuration (`LOCAL_FAKE_CONFIG`). Every refusal raises; nothing is built.
2. Open its own engine on `settings.database_url` and require the migration head.
3. Build `PostgresSpendLedger(session_factory, limits)`. Construction does no I/O.
4. `build_transport_job(route, policy=..., ledger=spend, scope_for=<intake scope>, image, run_id, evidence_dir, script_for, credential_file, timeout_seconds, run_budget_seconds, seal_grace_seconds, recovery_budget_seconds)`.
5. Run one `supervision.recover_pending(recovery_budget_seconds)` pass (budget C), so a restarted process cleans up its dead turns without waiting for a new request. Record `pending_cleanup()` as `startup_recovery`.

The application is unchanged at its seam: `create_app(settings, hermes_runner=mount.runner)` with `EDGE_OS_INTERPRETER=hermes_local`, which settings already refuse in production. The application interpreter configuration stays `LOCAL_FAKE_CONFIG` and `runtime_label` stays `LOCAL_FAKE_PROVIDER`.

Scope: `scope_for(turn)` is `intake:<intake_record_id>` of the saved attempt row (looked up by the attempt id the interpreter recorded before the call). An attempt with unresolved liability blocks further attempts on the same saved request only. A failed lookup raises inside the accepted runner's reservation step, so the turn is refused (`SpendLedgerUnavailable`) and nothing is reserved.

Process identity: each API process uses its own stable `run_id`; a restarted process reuses its `run_id` and evidence folder to recover its dead turns within C. Two processes that share one `run_id` are still safe (a live turn of the other process blocks new turns as `CleanupPending`), but they serialize. The shared spend cap does not depend on `run_id`.

## 3. Spend reservation interface

New module `apps/api/src/edge_os_api/research/provider_spend_ledger.py`, class `PostgresSpendLedger(session_factory, limits)`. Same methods, arguments, return types and exceptions as the accepted `SpendLedger` (imported from `spend_ledger`, so the accepted runner maps them unchanged):

| Method | Rule |
|---|---|
| `reserve(attempt_id, *, scope, max_input_tokens, max_output_tokens) -> Reservation` | One transaction. The attempt must be a saved interpretation attempt (owner and saved request are copied from that row; see A1). Refused, writing nothing, on: existing attempt id (`ReservationExists`), unresolved liability in the scope (`ScopeBlocked`), configured caps or prices that differ from the frozen ones (`LedgerConfigMismatch`), owner liability + amount > owner cap or global liability + amount > global cap (`CapExceeded`). |
| `settle(attempt_id, *, input_tokens, output_tokens) -> Settlement` | RESERVED with usable usage: exact charge at the frozen prices. Unusable usage: UNKNOWN, full reservation kept. Already SETTLED: compared as evidence (duplicate, or conflicting keeps the higher). |
| `mark_unknown(attempt_id, *, reason)` | RESERVED becomes UNKNOWN; full reservation kept, scope stays blocked. |
| `release_unsent(attempt_id, *, reason)` | Only from RESERVED; the only way liability is freed. The accepted runner calls it only when the job reported zero requests, the guard's own count is 0, the status is not TIMED_OUT, and (through `TransportTurnRunner`) the transport's own sent count agrees. |
| `reconcile(attempt_id, *, input_tokens, output_tokens, source)` | Late evidence: never frees or doubles liability. |
| `committed_usd()`, `liability_usd(id)`, `state(id)`, `unresolved()`, `events(id)` | Reads. `committed_usd(owner_id=None)` also reports one owner. |
| `change_caps(*, global_cap_usd, owner_cap_usd, reason)` | The only cap change: explicit, with a reason, recorded as an event. After it the stored caps are authoritative and are not compared with configuration again. Prices never change. |

Liability is: SETTLED rows at their charge, RESERVED and UNKNOWN rows at their full reservation, RELEASED rows at 0. Money is integer nano-USD; prices are exact decimals, as in the accepted ledger.

Atomicity: every write runs in one transaction that first locks the single configuration row (`SELECT ... FOR UPDATE`). This serializes all ledger writes across threads and API processes, as `BEGIN IMMEDIATE` does for the SQLite file. Caps and prices are frozen in that row at the first reservation. A different configured cap or price later refuses new reservations until `change_caps` records a decision; existing reservations always settle at the frozen prices.

Tables (migration `0013`, schema `usage_local`): `provider_spend_settings` (one row), `provider_spend_reservations` (attempt id, owner, saved request, scope, state, amounts, token bounds, times; no foreign key, see A1), `provider_spend_events` (append-only). The downgrade is refused while any reservation or event exists (A2).

## 4. What a user sees

The saved attempt keeps the accepted runner's `spend_state` and `spend_charge_usd` in `runtime_observed`. The public attempt view gains one read-only field, `spend: {"state", "charge_usd"}`, from those saved values (null when the attempt saved none, for example after a crash). A failed, unknown or interrupted attempt is never shown as an accepted result: its parse result is not `ACCEPTED` and no revision links to it. The web client is unchanged.

## 5. Fault matrix (request -> timeout/crash -> stop -> evidence -> cleanup -> accounting -> restart)

| Fault | Physical requests at the transport | Stop | Evidence | Cleanup | Spend | Restart |
|---|---|---|---|---|---|---|
| Production, ACTUAL route, wrong policy | none: mount refused | - | none | - | nothing | - |
| Policy, cap, scope, config mismatch, unsaved attempt, ledger down | 0, no job | - | none | - | never reserved (PROVIDER_FAILED, count 0) | - |
| Pending cleanup of an earlier turn | 0, no job | - | none | recovery pass first | RELEASED | recovered within C |
| Physical or guard refusal | 0 | job ends | sealed | sealed output kept in the turn folder | RELEASED (guard 0, transport 0) | - |
| One request, usable usage | 1 | job ends | sealed | sealed output kept in the turn folder | SETTLED exact | - |
| Lost reply, oversized reply, crash after send, missing usage, identity mismatch | 1 (may be billed) | job ends | sealed, reply dropped | sealed output kept in the turn folder | UNKNOWN, full reservation, scope blocked | still held |
| Hung provider | 1 (may be billed) | stopped at D | sealed or quarantined | removed or quarantined | UNKNOWN (TIMED_OUT) | still held |
| API process killed mid-turn | 0 or 1 | the next process with the same run id stops the container by name and label within C | output removed | record deleted when confirmed | stays RESERVED; recovery never touches spend | attempt closed INTERRUPTED by `recover_all`; scope blocked |
| Settlement write fails | as above | - | - | - | SETTLEMENT_NOT_RECORDED, stays RESERVED | still held |

Known limits kept from P05: a killed non-streaming request may still be billed; the local cap does not cap provider billing; an UNKNOWN reservation has no resolution path except late evidence; zero-request release relies on counts written inside the job process (an ACTUAL route needs independent evidence first).

## 6. Test seams (pre-agreed in the packet)

1. `create_app(settings, hermes_runner=mount.runner)` with the accepted runner over the PostgreSQL ledger (controlled boundary, no Docker) and over the actual pinned Hermes transport job (Docker, no network).
2. Authenticated research request and reopen routes: create, reopen in a new application instance, two-owner denial, retry identity.
3. Shared spend reservation from two separate OS processes against one migrated local PostgreSQL: concurrent final-slot contention across two owners, owner cap, global cap, fixed and changed caps, restart.
4. Accepted `TransportJob` identity and supervision: transport attempt id equals the saved attempt id; independent request count from the transport's own record and request files; kill and restart recovery within C; deadline D; no credential in records, logs or evidence.

## 7. Files

| Path | Responsibility |
|---|---|
| `apps/api/src/edge_os_api/research/provider_spend_ledger.py` | PostgreSQL spend ledger, same rules as `SpendLedger`. |
| `apps/api/src/edge_os_api/research/hermes_transport_mount.py` | The mount: refusals, composition, intake scope, startup recovery. |
| `apps/api/migrations/versions/0013_provider_spend_ledger.py`, `research/provider_spend_tables.py`, `migrations/env.py` | The three tables, their definitions for `alembic check`, and their registration. |
| `apps/api/src/edge_os_api/research/interpretation_workflow.py` | The read-only `spend` field of a public attempt. |
| `apps/api/tests/test_provider_spend_ledger.py`, `test_hermes_transport_mount.py` | Fast tests (PostgreSQL, no Docker). |
| `apps/api/tests/{test_live,test_package_layout,test_runtime_guards,test_spot_replay_configuration_identity}.py` | Migration head literal `0012` -> `0013` only. |
| `tests/hermes_app_mount/` | Pinned-Hermes and two-process tests, with a test-only API host. |
| `docs/qualification/hermes-app-mount/` | This contract and the results and verification recipe. |

Not changed: `scripts/hermes_job_support/`, `scripts/hermes_interpretation/`, `usage/`, `research/investigation_jobs.py`, the web client, settings, dependencies and lockfiles.

## Amendments

A1 (during slice 1): no database foreign key from a reservation to its attempt. No table in this repository declares a foreign key across metadata, and `alembic check` must compare the new tables. Instead `reserve` reads the saved attempt row inside its locked transaction and copies the owner and saved request from it; that row is append-only (an immutability trigger rejects updates and deletes), so the copy cannot drift. An id that is not a saved attempt raises `AttemptNotSaved` and writes nothing. The table definitions live in `research/provider_spend_tables.py` and are registered in `migrations/env.py`.

A2 (after internal review round 1, non-blocking findings): corrections only. Section 3 and the tables row no longer claim a composite foreign key (A1 removed it). In the fault matrix, a turn that ends normally keeps its sealed output in its turn folder (the accepted runner removes output only for pending cleanup, quarantine and crash recovery); the earlier "output removed" in three rows was wrong. The migration downgrade now also refuses while any spend event exists, so a recorded cap decision is not dropped. The ledger documents its reliance on READ COMMITTED isolation.

A3 (gate review 1/3 and controller amendment D1, HERMES-MOUNT-D1-20261013): the test-only host becomes the startable LOCAL composition `scripts/hermes_app_mount/serve_transport_mount.py` (same code, reused by `tests/hermes_app_mount`). The full default mapped verifier gains the HERMES-MOUNT phase (`scripts/p03/hermes_app_mount_phase.py`, registered in `scripts/p03/verify_run.py` after P05, which is unchanged): its own pinned image, the mount on the standard port and database, `tests/p03/hermes-transport-mount.spec.mjs` and `...-reopen.spec.mjs` at desktop and 390px, SQL against attempts, spend rows and the job's request files, owner denial, a restart with the same run id, a credential scan and exact cleanup. The feature map and `verify-edge-os` recipe text record the phase.
