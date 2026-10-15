# Hermes actual operation: relay operator and application handoff

Task `HERMES-OPERATOR-L1-20261015-LOCAL-v1` (#58, reduced demo connection work). Status: LOCAL implementation with synthetic checks. It is not a provider result and gives no authority. No real key, account, provider request or spending is part of it. `relay_admission.APPROVED_ACTUAL_RELEASES` stays empty, so every ACTUAL configuration is refused.

Sources: `../hermes-provider-relay/CONTRACT.md` (A6, E1-COST1, R9), `../hermes-provider-relay/ONLINE_CONTINUATION.md` sections 2-7 (current code and approval supersede its dated proposals), the controller's `HANDOFF_CONTRACT.md` (53ee240e...) and `HANDOFF_CLARIFICATION_V2.md` (c28167aa...). The model operating packet is [MODEL_OPERATING_PACKET.md](MODEL_OPERATING_PACKET.md).

## 1. Operator entry

`scripts/hermes_provider_relay/relay_operator.py`, run with the API's Python:

```
python scripts/hermes_provider_relay/relay_operator.py CONFIG [check|start|restart|stop]
```

It composes the accepted `RelaySupervisor` with the E1 topology (`online=True`). It does not change the gateway, the relay service, the request parser, the turn runner or the ledger.

| Command | Effect | Refused before any effect when |
|---|---|---|
| `check` (default) | Reads the configuration, the ACTUAL record and its CA bundle, and stats the key file. No Docker call, no write. | any configuration rule below fails |
| `start` | Creates the run root (0700), writes `owner.json`, starts the supervisor, writes `handoff.json` once (0444) and prints `handoff <path> sha256 <hex>`. | the run root exists; `docker image inspect <reference>` does not give the configured id; any container `relay-<id>`, `relay-gateway-<id>`, `relay-provider-<id>`, or network or volume `relay-egress-<id>` exists |
| `restart` | `RelaySupervisor.restart_relay()`. The relay's recovery C marks a started attempt `unknown_restart`; nothing is resent. | `owner.json` is missing or names another configuration hash; `stopped.json` exists |
| `stop` | `RelaySupervisor.stop()` by exact names; writes `stopped.json` the first time; exit 1 if anything is left. | `owner.json` is missing or names another configuration hash |

A failed start calls `stop()` and writes `start-failed.json` with the error class and the cleanup result, and no handoff. `stop()` removes by name; `start` refuses names that exist, so only resources this operation created are removed. The CLI prints only the error class for an unexpected failure, because Docker errors carry mount paths and arguments. Exit codes: 0 done, 2 refused, 1 failed or leftovers.

Image identity: every container runs from the configured Docker image id (`sha256:...`), passed as the existing `image` string. The reference is checked once against that id before start. A moved tag cannot change what runs; a missing image fails the launch.

## 2. Operator configuration `edge-os.relay-operator-config/1`

Strict JSON (no repeated key, no NaN), exactly these fields:

| Field | Rule |
|---|---|
| `format` | `edge-os.relay-operator-config/1` |
| `operation_id` | 1-40 of `a-z 0-9 -`; becomes the supervisor `run_id` and every Docker name |
| `kind` | `AUTHORED` or `ACTUAL` |
| `release` | AUTHORED: exactly `RelayRelease.settings()` with kind AUTHORED. ACTUAL: null |
| `release_record` | ACTUAL: `{path, sha256}`; loaded by `load_actual_release(raw, sha256)` with the default registry only. AUTHORED: null |
| `ca_bundle` | ACTUAL: `{path, sha256}`; the hash must equal the record's `ca_bundle_sha256` and the file bytes. AUTHORED: null (throwaway test CA) |
| `image` | `{reference, id}`; id is `sha256:` plus 64 hex |
| `run_root` | absolute; must not exist at start |
| `channel` | `{name, path}`; the relay channel root name and its host folder (the job evidence folder) |
| `provider_key_file` | absolute; a regular file, not a link, mode with no group/other bits, outside the repository. Stat only, never read by the operator |
| `shutdown_owner` | `relay_operator` |

## 3. Handoff `edge-os.relay-operator-handoff/1`

The operator writes `<run root>/handoff.json` once. The application receives its path and SHA256 from its own trusted configuration and refuses other bytes. Fields, exactly:

`format`, `operation_id`, `config_sha256`, `kind`, `release` (`RelayRelease.settings()`, the heartbeat shape), `release_record` (`{path, sha256}` or null), `ca_bundle_sha256` (or null), `image` (`{reference, id}`), `endpoint` (`grants`, `revocations`, `state`, `admission_key_file`, `channel_root`, `heartbeat_max_age_seconds`), `evidence_dir`, `shutdown_owner` (`relay_operator`), `started_at`.

Application use (lane 2):

- Build `RelayEndpoint` from `endpoint`, give `evidence_dir` and `image.id` (not the reference) to `build_relay_job`. The job then runs the relay's exact image.
- The handoff is not approval. For ACTUAL the application first needs its own code-owned trusted definition. It then reads the raw record bytes itself, calls `load_actual_release(raw, sha256)` with the default registry, requires `actual.release.settings() == release` and `actual.ca_bundle_sha256 == ca_bundle_sha256`, and validates its price snapshot from the same raw bytes (`HANDOFF_CONTRACT.md` items 2-5).
- The handoff never holds the provider key, its path, the admission key bytes or an environment value. The admission key stays the endpoint file.
- `relay_operator.read_handoff(path, sha256)` is the operator's own strict reader (hash, fields, format; no record load). Lane 2 may implement its own bounded read against this format instead; it must not import unaccepted lane-1 code.

Mode 0444 prevents routine accidental writes. It does not protect against the same OS user and is no host-user isolation claim. LOCAL operation runs the operator and the application as one OS user.

## 4. Writer and path map

Read-only ownership applies to the handoff, the configuration and the release record. The accepted runtime writers keep their single-purpose files, each owned per attempt.

| Path | Writer | Readers |
|---|---|---|
| operator configuration file | operator owner (outside the run root) | operator |
| `<run root>/owner.json`, `handoff.json`, `start-failed.json`, `stopped.json` | operator, once each | operator; application reads `handoff.json` only |
| `<run root>/relay/relay-config.json`, `gateway-config.json`, `provider-config.json`, `tls/`, `secrets/admission-key` | `RelaySupervisor._prepare` (operator process) | relay, gateway, stand-in (mounted read-only); application reads the admission key file only |
| `<run root>/relay/grants/<attempt>.json` | application `RelayTurnRunner.run_turn`, once per attempt | relay (read-only mount) |
| `<run root>/relay/revocations/<attempt>.json` | application `RelayTurnRunner._close`, once per attempt | relay |
| `<run root>/relay/state/` (`heartbeat.json`, `events.jsonl`, `<attempt>/started.json`, `finished.json`, `closed.json`) | relay | application `RelayTurnRunner` (heartbeat and records) |
| `<run root>/relay/gateway/receipts/`, `provider/receipts/` | gateway, AUTHORED stand-in | evidence |
| `<channel path>/` (the job evidence folder and channel files) | application job runner (`GuardedDockerTurnRunner`) and the job; relay writes channel replies | application, relay |
| provider key file | its owner outside the repository | relay only (read-only mount; AUTHORED stand-in reads the synthetic key) |

Shutdown: only the operator stops, restarts or removes relay, gateway, stand-in, network and volume. The application never does; its close disposes only its own engine. Job recovery (`recover_pending`) and the per-attempt grant and close stay with the application. UNKNOWN liability and no-resend rules are unchanged.

## 5. Checks

Focused, no Docker: `tests/hermes_provider_relay/test_relay_operator.py` (fake `docker`, synthetic key, record and CA). Docker checks need a separate capacity grant: an owned AUTHORED E1 start and stop through the CLI and an application-handoff compatibility proof (see the lane-1 evidence for the exact request).
