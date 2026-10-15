# Hermes actual operation: relay operator and application handoff

Task `HERMES-OPERATOR-L1-20261015-LOCAL-v1` (#58, reduced demo connection work). Status: LOCAL implementation with synthetic checks. It is not a provider result and gives no authority. No real key, account, provider request or spending is part of it. `relay_admission.APPROVED_ACTUAL_RELEASES` stays empty, so every ACTUAL configuration is refused.

Sources: `../hermes-provider-relay/CONTRACT.md` (A6, E1-COST1, R9), `../hermes-provider-relay/ONLINE_CONTINUATION.md` sections 2-7 (current code and approval supersede its dated proposals), the controller's `HANDOFF_CONTRACT.md` (53ee240e...) and `HANDOFF_CLARIFICATION_V2.md` (c28167aa...). The model operating packet is [MODEL_OPERATING_PACKET.md](MODEL_OPERATING_PACKET.md).

## 1. Operator entry

`scripts/hermes_provider_relay/relay_operator.py`, run with the API's Python:

```
python scripts/hermes_provider_relay/relay_operator.py CONFIG [check|start|restart|stop]
```

It composes the accepted `RelaySupervisor` with the E1 topology (`online=True`). It uses the supervisor's `start()`, `start_relay()` and `endpoint()`. It does not change the gateway, the relay service, the request parser, the turn runner or the ledger.

| Command | Effect | Refused before any effect when |
|---|---|---|
| `check` (default) | Reads the configuration, the ACTUAL record and its CA bundle, and stats the key file. No Docker call, no write. | any configuration rule below fails |
| `start` | Claims the run root (exclusive `mkdir`, 0700), writes `owner.json` (with a fresh random volume claim), creates the channel folder (0700), claims the egress volume, starts the supervisor, records the network id in `resources.json`, checks every started object is owned, writes `handoff.json` once (0444) and prints `handoff <path> sha256 <hex>`. | the run root or channel folder exists; the channel folder is the run root or inside `<run root>/relay`; `docker image inspect <reference>` does not give the configured id; any name is not positively absent (an object exists, or Docker's answer is unknown); another start claimed the run root first |
| `restart` | Kills and removes the owned relay container by id, then `RelaySupervisor.start_relay()`. The relay's recovery C marks a started attempt `unknown_restart`; nothing is resent. | `owner.json` is missing or names another configuration; `start-failed.json`, `stopped.json` or any `stop-incomplete-*.json` exists; no `handoff.json`; the gateway, network, volume or (AUTHORED) stand-in is not owned; the relay name holds a foreign or unknown object |
| `stop` | Removes the owned containers, network and volume (section 2) and checks each is then positively absent. A clean stop (nothing left, foreign, unknown or failed) writes `stopped.json` the first time, exit 0. Any other stop writes `stop-incomplete-<ns>.json`, exit 1. Needs only the configuration bytes and `owner.json`, not the key file or a still-approved record. | `owner.json` is missing or names another configuration |

Exit codes: 0 done, 2 refused, 1 failed or leftovers. The CLI prints only the error class for an unexpected failure, because Docker errors carry mount paths and arguments.

Image identity: every container runs from the configured Docker image id (`sha256:...`), passed as the existing `image` string. The reference is checked once against that id before start. A moved tag cannot change what runs. Whether Docker tries a registry when that id is missing locally depends on the Docker version; the supervisor passes no pull policy (outside this lease, not verified).

## 2. Ownership

- Run id: the supervisor run id, which is every Docker name and label, is `<operation_id>-<first 12 hex of the configuration SHA256>`. Two configurations never share names, even with one `operation_id`.
- Handoff semantics (lane 2): the handoff `operation_id` is the configured logical id. It is NOT the Docker run id, label value or name part. `config_sha256` is the exact identity of the configuration bytes. The application must not derive Docker names or labels from the handoff. No handoff field, endpoint or signature changed.
- Claim: `start` checks that every name is positively absent, then claims the run root with an exclusive `mkdir`. A second start of the same configuration fails at the claim and touches nothing. If the `owner.json` write then fails, the start removes the still-empty run root it just created (`rmdir`, which never removes content) and re-raises.
- Volume claim: Docker re-uses an existing local volume of a requested name without an error and keeps its labels (docker/cli `volume_create.md`). So, before the supervisor starts anything, the operator creates the egress volume itself with the supervisor's exact options and run label plus `edge-os.relay-operator.claim=<random value in owner.json>`, and requires that label. A volume that was already there fails the start before any container mounts it. The supervisor's own `volume create` then re-uses the claimed volume.
- Owned, per object under this run id's names:
  - container: label `edge-os.hermes-relay=<run id>` AND a mount of its role's config file from this run root (`relay-config.json`, `gateway-config.json`, `provider-config.json` under `<run root>/relay`);
  - network: that label AND, after start, the network id recorded in `resources.json`;
  - volume: that label AND this start's claim label.
- States: absent only when Docker's whole error answer is the no-such-object line for that kind and exact name: `No such object: NAME`, `No such KIND: NAME`, or the kind's own Docker 29.4.0 text (`network NAME not found`, `No such container: NAME`, `get NAME: no such volume`), after `Error: ` or `Error response from daemon: `. A daemon that cannot be reached, a permission error, a timeout, a malformed reply, an answer for another name or kind, an extra error line or another error is `unknown`: never treated as gone and never as owned. Anything else under these names that is not owned is `foreign`. The operator never kills, removes or adopts foreign or unknown objects, and reports them.
- Post-start check: after the supervisor starts, every started object must still be owned before the handoff is written. This finds an object swapped in after the claim and refuses the handoff. It cannot undo a mount that a container already made.
- Removal goes by the Docker id just inspected (a volume by its name), never by name alone. After removal each object must be positively absent; failed removals are `errors`, and a failed label listing is `unknown`.
- Failed start: any failure after the claim (channel folder, volume claim, supervisor start, network record, ownership check, endpoint, handoff write) removes only owned objects, using the recorded network id once it exists. It writes `start-failed.json` with `error` (class), `cleanup` (left, foreign, unknown, errors; or null) and `cleanup_error` (class of an exception inside cleanup, or null), then re-raises the start error.
- Limits: ownership rests on labels, the mount source, the recorded network id and the claim value. Any process with Docker control on this host, as the same OS user, can read and copy all of them, so this is protection against mistakes and stale or competing operator runs, not isolation from a deliberate local actor. A volume replaced in the instant between inspect and removal is not detected. Docker's behaviour for a re-used volume with different options is not documented; the operator passes the supervisor's exact options. Container ownership needs Docker to report the bind source as the resolved host path; on Docker Desktop this is checked only by the Docker test (it fails closed: stop exit 1, restart refused).

## 3. Operator configuration `edge-os.relay-operator-config/1`

Strict JSON (no repeated key, no NaN), exactly these fields:

| Field | Rule |
|---|---|
| `format` | `edge-os.relay-operator-config/1` |
| `operation_id` | 1-40 of `a-z 0-9 -`; the start of the run id |
| `kind` | `AUTHORED` or `ACTUAL` |
| `release` | AUTHORED: exactly `RelayRelease.settings()` with kind AUTHORED. ACTUAL: null |
| `release_record` | ACTUAL: `{path, sha256}`; loaded by `load_actual_release(raw, sha256)` with the default registry only. AUTHORED: null |
| `ca_bundle` | ACTUAL: `{path, sha256}`; the hash must equal the record's `ca_bundle_sha256` and the file bytes. AUTHORED: null (throwaway test CA) |
| `image` | `{reference, id}`; id is `sha256:` plus 64 hex |
| `run_root` | absolute; must not exist at start |
| `channel` | `{name, path}`; the relay channel root name and its host folder (the job evidence folder); the folder must not exist at start, and must not be the run root or inside `<run root>/relay` |
| `provider_key_file` | absolute; a regular file, not a link, mode with no group/other bits, outside this repository checkout. Stat only, never read by the operator |
| `shutdown_owner` | `relay_operator` |

## 4. Handoff `edge-os.relay-operator-handoff/1`

The operator writes `<run root>/handoff.json` once. The application receives its path and SHA256 from its own trusted configuration and refuses other bytes. Fields, exactly:

`format`, `operation_id`, `config_sha256`, `kind`, `release` (`RelayRelease.settings()`, the heartbeat shape), `release_record` (`{path, sha256}` or null), `ca_bundle_sha256` (or null), `image` (`{reference, id}`), `endpoint` (`grants`, `revocations`, `state`, `admission_key_file`, `channel_root`, `heartbeat_max_age_seconds`), `evidence_dir`, `shutdown_owner` (`relay_operator`), `started_at`.

Application use (lane 2):

- Build `RelayEndpoint` from `endpoint`, give `evidence_dir` and `image.id` (not the reference) to `build_relay_job`. The job then runs the relay's exact image.
- The handoff is not approval. For ACTUAL the application first needs its own code-owned trusted definition. It then reads the raw record bytes itself, calls `load_actual_release(raw, sha256)` with the default registry, requires `actual.release.settings() == release` and `actual.ca_bundle_sha256 == ca_bundle_sha256`, and validates its price snapshot from the same raw bytes (`HANDOFF_CONTRACT.md` items 2-5).
- The handoff never holds the provider key, its path, the admission key bytes or an environment value. The admission key stays the endpoint file.
- `relay_operator.read_handoff(path, sha256)` is the operator's own strict reader: hash, exact fields and format, and value shapes (operation id, SHA256s, release settings by the `RelayRelease` field rules, image id, absolute paths, channel name, finite numbers). It loads no record. Lane 2 may implement its own bounded read against this format instead; it must not import unaccepted lane-1 code.

Mode 0444 prevents routine accidental writes. It does not protect against the same OS user and is no host-user isolation claim. LOCAL operation runs the operator and the application as one OS user.

## 5. Writer and path map

Read-only ownership applies to the handoff, the configuration and the release record. The accepted runtime writers keep their single-purpose files, each owned per attempt.

| Path | Writer | Readers |
|---|---|---|
| operator configuration file | operator owner (outside the run root) | operator |
| `<run root>/owner.json`, `resources.json`, `handoff.json`, `start-failed.json`, `stopped.json`, `stop-incomplete-<ns>.json` | operator, each once | operator; application reads `handoff.json` only |
| `<run root>/relay/relay-config.json`, `provider-config.json`, `tls/`, `secrets/admission-key` | `RelaySupervisor._prepare` (operator process) | relay, stand-in (mounted read-only); application reads the admission key file only |
| `<run root>/relay/gateway-config.json` | `RelaySupervisor._start_gateway` (operator process) | gateway (read-only mount) |
| `<run root>/relay/grants/<attempt>.json` | application `RelayTurnRunner.run_turn`, once per attempt | relay (read-only mount) |
| `<run root>/relay/revocations/<attempt>.json` | application `RelayTurnRunner._close`, once per attempt | relay |
| `<run root>/relay/state/` (`heartbeat.json`, `events.jsonl`, `<attempt>/started.json`, `finished.json`, `closed.json`) | relay | application `RelayTurnRunner` (heartbeat and records) |
| `<run root>/relay/gateway/receipts/`, `provider/receipts/` | gateway, AUTHORED stand-in | evidence |
| `<run root>/relay/provider/scripts/<attempt>.json` | AUTHORED test scaffolding only (the test's script owner, e.g. `relay_harness.Rig.script_for`); not in the handoff; it sits beside the handoff's `state` folder | AUTHORED stand-in; no ACTUAL equivalent |
| `<channel path>/` (the job evidence folder and channel files) | application job runner (`GuardedDockerTurnRunner`) and the job; relay writes channel replies | application, relay |
| provider key file | its owner outside the repository | relay only (read-only mount; AUTHORED stand-in reads the synthetic key) |

Shutdown: only the operator stops, restarts or removes relay, gateway, stand-in, network and volume. The application never does; its close disposes only its own engine. Job recovery (`recover_pending`) and the per-attempt grant and close stay with the application. UNKNOWN liability and no-resend rules are unchanged.

## 6. Checks

Focused, no Docker: `tests/hermes_provider_relay/test_relay_operator.py -k "not test_docker_"` (stateful fake `docker`: names, ids, labels, mounts and name conflicts; synthetic key, record and CA). Docker checks need a separate capacity grant: `test_docker_the_cli_runs_the_e1_relay_from_the_handoff_restarts_and_stops_with_nothing_left` starts an owned AUTHORED E1 operation through the CLI, runs one turn from the handoff, restarts the relay through the CLI (records unchanged, no new stand-in receipt), stops it and checks that nothing labelled is left.
