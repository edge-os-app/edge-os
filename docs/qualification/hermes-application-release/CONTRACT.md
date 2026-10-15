# Hermes application release: the relay behind the saved Research path (contract)

Task `HERMES-APPLICATION-COMPOSITION-L2-20261015-LOCAL-v1` (#58 approved reduced demo connection work). Base `c34bd3959e51696193c1a031652a62fa67829e28`. Status: LOCAL. This note gives no authority: no approved release, provider, model, price, key, network, spending, deployment or public operation. No release is approved, so the default application composes nothing. Production stays refused.

## 1. Sources

- Relay admission and the trusted registry: `scripts/hermes_provider_relay/relay_admission.py` (`load_actual_release`, `ActualRelease`, `APPROVED_ACTUAL_RELEASES`, empty). Used read-only.
- Relay host runner: `scripts/hermes_provider_relay/relay_turn_runner.py` (`build_relay_job`, `RelayEndpoint`, the E1-COST1 rule that needs the ledger's own `TokenPrice`). Used read-only.
- Relay contract `docs/qualification/hermes-provider-relay/CONTRACT.md` amendment A6 and its E1-COST1 obligation: "the application successor (lane 2) must pass the SAME TokenPrice it gives its PostgreSQL ledger and prove that price equals the approved price snapshot before any ACTUAL activation".
- Accepted LOCAL relay mount `scripts/hermes_provider_relay/relay_application_mount.py`: unchanged and still AUTHORED only. Its saved-attempt subject rule is repeated here without importing its private helpers.
- Accepted application parts: `HermesInterpreter`/`HermesResearch` and their output contract, `PostgresSpendLedger`, `create_app` and its lifespan recovery. The code-owned release pattern is `core/research/released_runtime_bootstrap.py`.
- Controller handoff agreement `.scratch/demo-next-wave-20261015/HANDOFF_CONTRACT.md` (SHA256 `53ee240e...`), which adopted the lane-2 proposal (SHA256 `70715fe1...`). It keeps the lane-1 interfaces unchanged and leases nothing new.
- Controller clarification `HANDOFF_CLARIFICATION_V2.md` (SHA256 `c28167aa...`), which adopted the lane-1 operator handoff format `edge-os.relay-operator-handoff/1` (lane-1 proposal SHA256 `92760f9f...`) with corrections. Lane 2 reads it with its own bounded strict reader in this module. It imports no lane-1 operator code.

## 2. Data shape

New module `apps/api/src/edge_os_api/research/hermes_relay_composition.py`.

```python
@dataclass(frozen=True)
class RelayApplicationDefinition:     # code-owned; RELEASE_DEFINITIONS = () in this candidate
    record: bytes                     # the frozen ACTUAL release record (relay A6 fields)
    record_sha256: str
    price_snapshot: bytes             # the bytes the record names by price_snapshot_sha256
    response_format: Mapping | None   # the schema the record names by response_format_sha256
    image: str                        # pinned Hermes job image, by digest
    channel_root: str                 # this application's channel under the relay
    global_cap_usd: Decimal
    owner_cap_usd: Decimal

@dataclass(frozen=True)
class HermesApplicationRelease:       # built only by bind_release(definition); pure
    actual: ActualRelease             # from load_actual_release(record, record_sha256), no override
    approval_sha256: str              # re-read from the same accepted record bytes
    price_snapshot_sha256: str        # re-read from the same accepted record bytes
    price: TokenPrice                 # ONE object: SpendLimits.price and build_relay_job(price=...)
    route: TransportRoute             # ACTUAL, the record's endpoint and reply bound
    policy: GuardPolicy               # the record's model, token/byte limits and request shape
    config: HermesInterpreterConfig   # model, route id, max tokens, runtime_label LIVE, LiveRelease
    image: str
    channel_root: str
    limits: SpendLimits
    required_extra_sha256: str        # the bound request shape; checked again before anything is built
```

Price snapshot format (owned by this application): strict JSON (no repeated key, no NaN or Infinity), exactly `model`, `provider`, `prompt_usd_per_million`, `completion_usd_per_million`. The two rates are positive plain decimal strings (`^(0|[1-9][0-9]{0,8})(\.[0-9]{1,12})?$`, above zero). Binding requires all of these:

- The snapshot bytes have the record's `price_snapshot_sha256`.
- `model` is the record's model, and `provider` is the record's one routing slug (`provider.only[0]`).
- Each rate is at most the record's routing `max_price` for the same token kind.

Assumption: `max_price` is USD per million tokens. The qualification packet must confirm this. The snapshot gives one prompt rate and one completion rate. It does NOT capture cached-token discounts, fee variants or actual billing. Under E1-COST1 any reported cost other than this price's charge stays UNKNOWN with the full reservation.

Ownership of the request shape: the policy's `required_extra` (`stream`, `provider`, `reasoning`, `response_format`) is a JSON copy that shares no object with the record or the definition. `compose_application` refuses a release whose copy no longer hashes to `required_extra_sha256`, or whose record routing or reasoning no longer equals the copy.

## 3. Composition and order of refusals

```python
def open_hermes_application(settings, *, handoff_path: Path, handoff_sha256: str, run_id: str,
                            run_budget_seconds=60, seal_grace_seconds=5.0, recovery_budget_seconds=5.0,
                            close_budget_seconds=2.0) -> HermesApplication | None

def compose_application(release, engine, *, endpoint, run_id, evidence_dir, ...) -> HermesApplication  # no I/O

@dataclass
class HermesApplication:
    release: HermesApplicationRelease
    runner: HermesTurnRunner              # accepted GuardedTurnRunner over RelayTurnRunner
    supervision: GuardedDockerTurnRunner
    spend: PostgresSpendLedger
    engine: Engine
    startup_recovery: list[dict]
    config -> release.config
    def close(self) -> None
```

`open_hermes_application` steps, in order:

1. Refuse `settings.env == "production"` and `settings.interpreter != "hermes_local"` (`MountRefused`).
2. Take the code-owned definitions whose record SHA-256 is in `relay_admission.APPROVED_ACTUAL_RELEASES`, read when the function runs. None: return `None`. More than one: refuse.
3. `bind_release(definition)` (pure).
4. Read the operator handoff (section 3.1) and take the relay endpoint and job evidence folder from it.
5. Open its own engine, require the migration head, `compose_application`, then one `recover_pending` pass (budget C).

Steps 1 to 4 run before any engine, key, socket or Docker effect. Steps 1 to 3 also read no file: the default (no approved definition) never opens the handoff. `compose_application` builds `PostgresSpendLedger(session_factory, release.limits)` and `build_relay_job(release.route, release=actual.release, actual=actual, price=release.price, policy=release.policy, timeout_seconds=actual.timeout_seconds, image=release.image, script_for=lambda turn: {}, ...)` with `credential_file=None`. The application holds no provider key. The admission key stays a host/relay endpoint file that only `RelayTurnRunner` reads.

### 3.1 Operator handoff (read only)

The application's trusted configuration owner gives `handoff_path` and `handoff_sha256`: the line the lane-1 operator prints at start. The handoff approves nothing. The release comes only from the code-owned definition, and the handoff's `release_record.path` is never read, because the approved record bytes are the definition's own. The reader refuses (`MountRefused`) in each of these cases:

- The file is not a regular file, is reached through a symbolic link (`O_NOFOLLOW`), is over 16 KiB, or does not have the named SHA-256.
- The JSON is not strict, the fields are not exactly the frozen twelve, or `format` is not `edge-os.relay-operator-handoff/1`.
- `kind` is not `ACTUAL`, `release` differs from `actual.release.settings()`, `release_record.sha256` differs from the record SHA-256, or `ca_bundle_sha256` differs from the record's.
- `image.reference` is not the definition's digest reference (`name@sha256:<64 hex>`), or `image.id` is not `sha256:<64 hex>`. A mutable tag is refused. The job runs the digest reference itself, so the launch argument is immutable.
- `shutdown_owner` is not `relay_operator`.
- The `endpoint` fields are not exactly the six frozen fields, a path is not absolute, `channel_root` is not the release's, or `heartbeat_max_age_seconds` is not a number in (0, 10].
- `evidence_dir` is not absolute.

`operation_id`, `config_sha256` and `started_at` are evidence only. Mode 0444 on the handoff prevents routine accidental writes. It is not protection against the same OS user, and no host-user isolation is claimed.

### 3.2 Writer and path map

Neither actor rewrites the handoff or the other's state. The application never stops, restarts or removes relay or gateway resources. `HermesApplication.close` disposes only its own engine.

| Path | Writer | What |
|---|---|---|
| `<run root>/handoff.json`, `stopped.json`, relay `state/` records (heartbeat, `closed.json`, `finished.json`), gateway receipts | lane-1 operator and relay | operator and relay records |
| `endpoint.grants/<attempt>.json` | application, accepted `RelayTurnRunner.run_turn` | one grant per attempt, written once (`O_EXCL` + link) |
| `endpoint.revocations/<attempt>.json` | application, accepted `RelayTurnRunner._close` | one revocation per attempt, written once |
| `evidence_dir` turn folders and records, job channel files | application, accepted `GuardedDockerTurnRunner` and the job it starts | per-attempt job evidence, recovery records |
| `endpoint.admission_key_file` | lane-1 operator; read only by `RelayTurnRunner` | the admission HMAC key, never in model, job, UI or logs |
| PostgreSQL `interpretation_*`, `usage_local.provider_spend_*` | application | saved attempts and shared spend |

Subject and scope: `scope_for` is `intake:<intake_record_id>` of the saved attempt row. `subject_for` reads the saved attempt's owner and saved request, then requires the attempt's reservation row to name the same owner, request and scope in state `RESERVED`. Anything else raises: `RelaySubjectUnavailable`, no grant, count 0, the reservation released.

Application seam: `create_app(settings, hermes_runner=app.runner, hermes_config=app.config)`. `create_app` refuses a `hermes_config` without its runner, outside `hermes_local`, or in production, before any engine. Without `hermes_config` the factory keeps `LOCAL_FAKE_CONFIG`, so existing callers are unchanged. Settings are unchanged: production already allows only the fixture interpreter.

## 4. Fault matrix (request -> possible effect -> outcome -> accounting -> restart)

| Case | Requests | Outcome | Liability | Restart / retry |
|---|---|---|---|---|
| No approved definition | 0 | `None`, nothing built | none | n/a |
| Production, other interpreter, two approved, foreign channel, bad run id | 0 | `MountRefused` before effect | none | n/a |
| Record outside registry, wrong hash, bad snapshot, schema, image | 0 | `MountRefused` (pure) | none | n/a |
| Reservation no longer names the saved owner/request | 0 | `PROVIDER_FAILED` `RelaySubjectUnavailable`, no grant | RELEASED | new attempt allowed |
| Owner or global cap reached (any instance) | 0 | `SpendCapReached`, job never runs | none added | n/a |
| Reply, cost equal to snapshot charge | 1 | SETTLED at `price.nano_usd` | the charge | reopen elsewhere shows it |
| Reply, any other cost | 1 | UNKNOWN `RelayCostUnverified`, text withheld | full reservation | retry 409, never resent |
| Lost reply, timeout, missing close record | 0 or 1 | UNKNOWN | full reservation | restart keeps UNKNOWN, retry 409 |
| Second grant for one attempt | 0 | UNKNOWN `RelayGrantExists` (accepted) | full reservation | never resent |

## 5. Checks

Pure (no database, Docker or network), in `apps/api/tests/test_hermes_relay_composition.py`: default composes nothing, refusals before effect, factory refusals, one bound identity, registry refusal, record hash, 14 snapshot faults, 4 routing price-limit faults, schema/image/channel faults, the SAME `TokenPrice` object in the ledger and the relay runner, no I/O at construction, post-binding change refused.

Mounted (the session PostgreSQL container; needs a capacity grant), same file: the real composition, `create_app`, the accepted guard and relay runners and `PostgresSpendLedger`. Only the container job and the relay process are stand-ins that write the relay's records (synthetic provider). The record is synthetic and is admitted only by patching the registry inside the test. It is not an approved release. The mounted tests cover these cases:

- A saved request is sent once. It settles at the snapshot price (not the LOCAL 2.00/7.50). The grant names the saved owner, request and scope. Another instance reopens it, and another owner gets 404.
- A different cost stays UNKNOWN and is never resent.
- Interruptions (lost, timeout, missing close) stay UNKNOWN across a restart with the same run id.
- Two instances share one owner cap, and a refused reservation never reaches the job.
- A moved reservation owner gets no grant.

Selectors (frozen at commit): composition `tests/test_hermes_relay_composition.py`, then affected `tests/test_hermes_transport_mount.py` and `tests/test_provider_spend_ledger.py`, then the full API suite. Each runs from `apps/api` with `.venv/bin/python -m pytest -p no:cacheprovider`.

The pure tests also cover the handoff: the exact handoff is accepted, 20 field faults are refused before any engine, and so are wrong hash bytes, a link, a folder, an oversized file, a missing file and a repeated key. The mounted fixture writes a mode-0444 handoff for the stand-in relay.

Not covered here: pinned Hermes through an ACTUAL route. It cannot run without provider network. Pinned Hermes through the relay is the lane-1 AUTHORED proof (`tests/hermes_provider_relay/test_relay_application_mount.py`). No browser or UI is changed.

## 6. Follow-on files and blockers (not in this candidate)

- `research/interpretation_workflow.py` `LABEL` and `HermesResearch.label()`: the `/v1/interpreter` view still says a local fake provider ran and no real model was called. It must follow `config.runtime_label` before any approved release is activated. That is UI/label work for a later milestone.
- An approved release needs the exact qualification packet. It must give the record, price snapshot (with current provider pricing evidence, the `max_price` unit, and cached-token/fee treatment), schema, image digest, CA bundle, caps, channel and the relay operator start (lane 1). Then add it to `RELEASE_DEFINITIONS` and `APPROVED_ACTUAL_RELEASES` in one reviewed change.
- Deployment qualification for production (settings still refuse it). Actual history/Nansen mounting is a later milestone. Settlement at a provider-reported cost needs a later ledger-owner extension (E1-COST1 limit).
- The CA bundle is checked by the relay against the record. The application only carries `ca_bundle_sha256` inside `actual`.
