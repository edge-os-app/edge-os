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
    image: str                        # pinned Hermes job image, by Docker image id sha256:<64 hex> (section 7.1)
    channel_root: str                 # this application's channel under the relay
    global_cap_usd: Decimal
    owner_cap_usd: Decimal

@dataclass(frozen=True)
class HermesApplicationRelease:       # built by bind_release(definition); pure (the type does not enforce it, 3.3)
    actual: ActualRelease             # from load_actual_release(record, record_sha256), no override
    approval_sha256: str              # re-read from the same accepted record bytes
    price_snapshot_sha256: str        # re-read from the same accepted record bytes
    price: TokenPrice                 # ONE object configures SpendLimits.price and build_relay_job(price=...)
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

Price identity: the SAME `TokenPrice` object configures `SpendLimits`/`PostgresSpendLedger` and `build_relay_job(price=...)`, where the relay runner's E1-COST1 check uses it. `PostgresSpendLedger` computes reservation and settlement amounts with a `TokenPrice` rebuilt from its database-frozen settings row. `reserve` refuses (`LedgerConfigMismatch`) unless that copy has exactly the same `Decimal` values as the configured object. `settle` does not check again, because frozen prices never change.

That settings row is a single row per database, shared with the LOCAL transport and relay mounts. If it was frozen first at another price, every reservation of this composition is refused (`SpendLedgerUnavailable`, request count 0). Actual activation therefore needs a ledger-owner procedure or a fresh approved ledger. This candidate grants no reset, migration, data deletion or price change.

Ownership of the request shape: the policy's `required_extra` (`stream`, `provider`, `reasoning`, `response_format` and, when the record names it, `prompt_cache_options`) is a JSON copy that shares no object with the record or the definition. `compose_application` refuses a release whose copy no longer hashes to `required_extra_sha256`, or whose record routing, reasoning or cache options no longer equal the copy.

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

Steps 1 to 4 run before any engine, key, socket or Docker effect. Steps 1 to 3 also read no file: the default (no approved definition) never opens the handoff.

`compose_application` builds `PostgresSpendLedger(session_factory, release.limits)` and `build_relay_job(release.route, release=actual.release, actual=actual, price=release.price, policy=release.policy, timeout_seconds=actual.timeout_seconds, image=release.image, script_for=lambda turn: {}, ...)` with `credential_file=None`. The application holds no provider key. The admission key stays a host/relay endpoint file that only `RelayTurnRunner` reads.

Two refusals come later. A bad `run_id` (checked in `compose_application`) and invalid caps (checked when `PostgresSpendLedger` is built) are refused in step 5, after the engine opens and `require_head` reads the migration head from the database. The engine is then disposed. No grant, provider request, key read or Docker effect occurs.

`bind_release` maps the `ValueError` refusals of `load_actual_release` to `MountRefused`. Some malformed code-owned records raise `TypeError` instead, for example a `destination` with extra keys, unhashable `allowed_fields` items, or a schema that is a `Mapping` but not a `dict`. Both happen before any effect. This candidate does not promise `MountRefused` for every malformed definition.

### 3.1 Operator handoff (read only)

The application's trusted configuration owner gives `handoff_path` and `handoff_sha256`: the line the lane-1 operator prints at start. The handoff approves nothing. The release comes only from the code-owned definition, and the handoff's `release_record.path` is never read, because the approved record bytes are the definition's own. The reader refuses (`MountRefused`) in each of these cases:

- The file is not a regular file, is itself a symbolic link, is over 16 KiB, or does not have the named SHA-256. `O_NOFOLLOW` checks the final path part only; symbolic links in parent folders are followed. The exact hash still binds the bytes that are read.
- The JSON is not strict, the fields are not exactly the frozen twelve, or `format` is not `edge-os.relay-operator-handoff/1`.
- `kind` is not `ACTUAL`, `release` differs from `actual.release.settings()`, `release_record.sha256` differs from the record SHA-256, or `ca_bundle_sha256` differs from the record's.
- `image.id` is not exactly the definition's Docker image id, or `image.reference` is not 1-200 characters without white space. The reference is the operator's name for that id (often a local tag); it is evidence only and never selects what runs. The job runs the image id itself, so the launch argument is immutable (section 7.1).
- `shutdown_owner` is not `relay_operator`.
- The `endpoint` fields are not exactly the six frozen fields, a path is not absolute, `channel_root` is not the release's, or `heartbeat_max_age_seconds` is not a number in (0, 10].
- `evidence_dir` is not absolute.

The endpoint folders that the handoff names are not checked when the application opens. If the grants folder is missing or not writable, each turn becomes UNKNOWN (`RelayGrantExists`, from the accepted runner) and keeps its full reservation. Nothing is sent.

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

### 3.3 Trusted code seams

`compose_application`, `HermesApplicationRelease` and the `create_app(hermes_runner=..., hermes_config=...)` pair are trusted code seams. They are not checked again against every approval, environment and configuration property.

- `compose_application` checks the request shape, the endpoint channel and the run id again. It does not check the trusted registry, the environment or the interpreter setting again.
- Code that builds a `HermesApplicationRelease` by hand could compose without a registry entry. No production caller does this, and no setting, environment value, file, request or handoff can.
- `create_app` does not check that `hermes_config` belongs to `hermes_runner`. A composition runner without its configuration fails closed at the guard's model check. A `LIVE` configuration given with another runner would label that runner's attempts `LIVE`.

## 4. Fault matrix (request -> possible effect -> outcome -> accounting -> restart)

| Case | Requests | Outcome | Liability | Restart / retry |
|---|---|---|---|---|
| No approved definition | 0 | `None`, nothing built | none | n/a |
| Production, other interpreter, two approved, foreign channel or other handoff fault | 0 | `MountRefused` before any engine | none | n/a |
| Bad run id or invalid caps, through the opener | 0 | `MountRefused` or `ValueError` after the engine reads the migration head; engine disposed | none | n/a |
| Record outside registry, wrong hash, bad snapshot, schema, image | 0 | `MountRefused` (pure) | none | n/a |
| Malformed code-owned record (see section 3) | 0 | `MountRefused` or `TypeError` (pure) | none | n/a |
| Ledger price row frozen at another price | 0 | `SpendLedgerUnavailable` (`LedgerConfigMismatch`), job never runs | nothing reserved | n/a |
| Reservation no longer names the saved owner/request | 0 | `PROVIDER_FAILED` `RelaySubjectUnavailable`, no grant | RELEASED | new attempt allowed |
| Owner or global cap reached (any instance) | 0 | `SpendCapReached`, job never runs | none added | n/a |
| Reply, cost equal to snapshot charge | 1 | SETTLED at `price.nano_usd` | the charge | reopen elsewhere shows it |
| Reply, any other cost | 1 | UNKNOWN `RelayCostUnverified`, text withheld | full reservation | retry 409, never resent |
| Lost reply, timeout, missing close record | 0 or 1 | UNKNOWN | full reservation | another instance with the same run id keeps UNKNOWN; retry 409 |
| Second grant for one attempt, or grants folder missing or not writable | 0 | UNKNOWN `RelayGrantExists` (accepted) | full reservation | never resent |
| Process crash during a turn (by code reading; not tested) | 0 or 1 | reservation stays RESERVED | counted as liability, scope blocked | never resent |

## 5. Checks

Pure (no database, Docker or network), in `apps/api/tests/test_hermes_relay_composition.py`: default composes nothing, refusals before effect, factory refusals, one bound identity, registry refusal, record hash, 14 snapshot faults, 4 routing price-limit faults, schema/image/channel faults, the SAME `TokenPrice` object in the ledger and the relay runner, no I/O at construction, post-binding change refused.

Limits of the pure proof:

- The opener's production and other-interpreter test can pass on the missing-handoff refusal. It does not prove the opener's own check. Production is also refused by settings and by `create_app`, and the `create_app` test does prove that check.
- The handoff repeated-key, snapshot repeated-key, snapshot `[]` and `max_price` Infinity cases can be refused by another guard: the duplicate value is also wrong, `[]` also lacks the fields, and the record cannot hold Infinity. They do not isolate the repeated-key, object or `is_finite` checks.

Mounted (the session PostgreSQL container; needs a capacity grant), same file: the real composition, `create_app`, the accepted guard and relay runners and `PostgresSpendLedger`. Only the container job and the relay process are stand-ins that write the relay's records (synthetic provider). The record is synthetic and is admitted only by patching the registry inside the test. It is not an approved release. The mounted tests cover these cases:

- A saved request is sent once. It settles at the snapshot price (not the LOCAL 2.00/7.50). The grant names the saved owner, request and scope. Another instance reopens it, and another owner gets 404.
- A different cost stays UNKNOWN and is never resent.
- Interruptions (lost, timeout, missing close) stay UNKNOWN when a second live instance opens with the same run id. The test does not kill or restart a process, so it gives no crash proof.
- Two instances share one owner cap, and a refused reservation never reaches the job.
- A moved reservation owner gets no grant.

The recorded charge evidence is 73,056,000 nano-USD reserved and 9,768,000 nano-USD charged at the synthetic 3.00/9.00 snapshot. The saved rows of these tests carry `runtime_label` `LIVE` because the synthetic record is kind ACTUAL. They do not prove an actual provider.

Overflow (a matching cost whose charge is above the reservation) and invalid or unknown usage are not tested on this composition. They are proved by the unchanged accepted relay components: `tests/hermes_provider_relay/test_relay_turn_runner_actual.py` (`test_a_matching_cost_whose_charge_exceeds_the_reservation_is_unknown`, `test_invalid_or_different_usage_keeps_the_full_reservation`), with the SQLite ledger. The relay runner and the ledger rules they use are unchanged here.

Selectors (frozen at commit): composition `tests/test_hermes_relay_composition.py`, then affected `tests/test_hermes_transport_mount.py` and `tests/test_provider_spend_ledger.py`, then the full API suite. Each runs from `apps/api` with `.venv/bin/python -m pytest -p no:cacheprovider`.

The pure tests also cover the handoff: the exact handoff is accepted, 20 field faults are refused before any engine, and so are wrong hash bytes, a link, a folder, an oversized file, a missing file and a repeated key. The mounted fixture writes a mode-0444 handoff for the stand-in relay.

Not proved by this file: pinned Hermes producing the ACTUAL request shape. Task `HERMES-LIVE-PATH-L1-20261015-LOCAL-v1` adds that proof in `tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py` (section 7.4). The lane-1 pinned-Hermes relay proof (`tests/hermes_provider_relay/test_relay_application_mount.py`) still uses the AUTHORED policy with an empty `required_extra`. No browser or UI is changed.

## 6. Follow-on files and blockers (not in this candidate)

Section 7 records which of these the follow-on task `HERMES-LIVE-PATH-L1-20261015-LOCAL-v1` closed locally. The list is kept as written for the earlier candidate.

- `research/interpretation_workflow.py` `LABEL` and `HermesResearch.label()`: the `/v1/interpreter` view still says a local fake provider ran and no real model was called. It must follow `config.runtime_label` before any approved release is activated. That is UI/label work for a later milestone.
- An approved release needs the exact qualification packet. It must give the record, price snapshot (with current provider pricing evidence, the `max_price` unit, and cached-token/fee treatment), schema, image digest, CA bundle, caps, channel and the relay operator start (lane 1). Then add it to `RELEASE_DEFINITIONS` and `APPROVED_ACTUAL_RELEASES` in one reviewed change.
- Deployment qualification for production (settings still refuse it). Actual history/Nansen mounting is a later milestone. Settlement at a provider-reported cost needs a later ledger-owner extension (E1-COST1 limit).
- Pinned Hermes must be proved to send the record's `provider`, `reasoning` and `response_format` fields (the policy's `required_extra`) through the isolated job before activation. Otherwise the job guard refuses every ACTUAL turn.
- The shared ledger price row (section 2) needs a ledger-owner procedure or a fresh approved ledger before activation.
- No server launcher or factory composition calls `open_hermes_application` and `create_app` yet (compare `scripts/hermes_app_mount/serve_transport_mount.py`). A launcher is follow-on work together with the runtime labels, the actual release and the deployment.
- The CA bundle is checked by the relay against the record. The application only carries `ca_bundle_sha256` inside `actual`.

## 7. Amendment: local launcher, labels, request shape and image identity

Task `HERMES-LIVE-PATH-L1-20261015-LOCAL-v1`, base `19e6063ec72fc676e479a1d9f477c2af3e23020a`. LOCAL only. Both registries stay empty, so the default still composes nothing. This amendment approves no release, provider, model, price, key, network, spending, deployment or recording.

### 7.1 Image identity

The relay operator starts its containers by the Docker image id it inspected for its configured reference, and hands off `image: {reference, id}`. A locally built image has an image id (`sha256:<64 hex>`, the hash of its configuration) and no registry manifest digest; the two are different identities. `RelayApplicationDefinition.image` is therefore the Docker image id, and the handoff's `image.id` must equal it exactly. `build_relay_job(image=release.image)` launches every job by that id. A tag, a registry digest reference (`name@sha256:...`) or an upper-case id is refused when the definition binds. No registry service is added, and no RepoDigest is made up.

### 7.2 Request shape

`hermes_turn_job.request_options` maps the job's `guard.policy.required_extra` onto pinned Hermes' own `AIAgent` options: `stream` and `response_format` go to the top level of `request_overrides`; `provider`, `reasoning` and `prompt_cache_options` go to its `extra_body`, which Hermes merges into the top level of the request body. A required `reasoning` value is also given as `reasoning_config`, so Hermes' own setting agrees with the routed value. The session id stays `p05-<attempt_id>`. An empty or absent policy adds no option, so the direct, guarded, transport and relay AUTHORED jobs build the same agent as before. A required field the mapping does not know is not sent, and the guard refuses the request before it leaves the job.

The optional record field `prompt_cache_options` (relay contract A7) is bound like `reasoning`: when the record names it, `bind_release` adds its exact value to `required_extra`, and `unchanged()` compares it with the record again.

### 7.3 Interpreter label

`HermesResearch.label()` keeps the shape `{kind, id, notice}`. The local fake configuration keeps `HERMES_LOCAL_FAKE_PROVIDER` and its notice. A `LIVE` configuration with its `LiveRelease` gives `kind` `HERMES_LIVE_RELEASE`, `id` the release id, and a notice that names the release, provider, model and model budget and states that it describes the configuration only and does not show that a model call completed. The release id is shown as recorded, so a SYNTHETIC test release stays visibly SYNTHETIC even though its record is kind ACTUAL and its configuration is `LIVE`.

### 7.4 Launcher and checks

`scripts/hermes_app_mount/serve_relay_application.py` (`main(argv=None) -> int`) is the launcher listed in section 6. See `docs/qualification/hermes-application-launcher/LOCAL_VERIFICATION.md` for its inputs, refusals, lifecycle, recipe and limits.

Pure checks: `apps/api/tests/test_hermes_application_launcher.py` (launcher refusals, serving and close, labels), this file's composition tests (image id binding and the handoff image rules), and the pure part of `tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py` (request options, cache field). Docker and PostgreSQL checks (`-k test_docker_` in that file) need a separate capacity grant and a kept image receipt.

Still open before activation: an approved record, schema, image, CA bundle, price snapshot and caps with their qualification packet; the ledger price row (section 2); the operator start; provider-side proof that the documented cache setting is honoured and billed as expected (E1-COST1 keeps any other cost UNKNOWN with full liability); deployment; and browser verification of the label.
