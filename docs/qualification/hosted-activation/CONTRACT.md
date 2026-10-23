# Hosted activation: one code-owned deployment approval (contract)

Task `HOSTED-ACTIVATION-L1-20261021`. Status: LOCAL contract and code. This note grants no deployment, record approval,
provider call, wallet change, funding or public link. The registry is empty in this candidate, so production still
refuses every live part it refused before. `docs/qualification/release-host-preparation/HOST_DECISION_PACKET.md`
section 8 remains the source of the host gates.

## 1. Purpose

Production refused every live part by design: the Hermes relay application, the `hermes_local` interpreter and the
approved research release. The demo needs a reviewed way to admit them later without setting `EDGE_OS_ENV=local`
behind HTTPS.

This contract defines one deployment record and one registry. A production process admits the three named parts only
when the running configuration names a registered record whose canonical SHA-256, origins and database TLS mode match
the running configuration, and whose bound release ids and hashes match the part about to be composed. Every other
production refusal stays.

## 2. The code-owned registry

```python
# apps/api/src/edge_os_api/core/hosted_deployment.py
APPROVED_HOSTED_DEPLOYMENTS: Mapping[str, str] = {}
```

The key is a deployment id. The value is the canonical SHA-256 of that deployment's record.

- The map is empty in this candidate.
- Adding, changing or removing an entry is a reviewed code change that cites the builder's recorded approval of that
  exact record.
- No setting, environment value, file, request body or header adds an entry.
- A record file is read only to compare it with the code-owned hash, and only after its deployment id is registered.

## 3. Running configuration

Two settings name the deployment:

| Setting | Meaning |
|---|---|
| `EDGE_OS_HOSTED_DEPLOYMENT_ID` | The registered deployment id. |
| `EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH` | The absolute path of the frozen record file. |

Both are set together or neither is. `local` and `test` ignore them. In `production`, a named record is validated at
startup by every process that loads settings.

## 4. The record

The file holds one strict JSON object. The canonical form is UTF-8 JSON with sorted keys, compact separators and no
trailing newline. The registry hash covers that canonical form, not the file layout, so whitespace and indentation do
not change the hash. Repeated keys, `NaN` and `Infinity` are refused. The file must be a regular file, not a symbolic
link, of at most 64 KiB.

```json
{
  "schema_version": "edge-os.hosted-deployment/1",
  "deployment_id": "hosted-demo-1",
  "public_origins": ["https://app.example.com"],
  "cors_origins": ["https://app.example.com"],
  "database_tls_mode": "verify-full",
  "hermes_relay": {"release_id": "hermes-first-call-1", "record_sha256": "<64 hex>"},
  "research_release": {"release_id": "actual-moe-nansen-demo-20261018/1", "sha256": "<64 hex>"},
  "host_gates": {
    "h1_egress": {"path": "docs/qualification/...", "sha256": "<64 hex>"},
    "h2_runner_isolation": {"path": "docs/qualification/...", "sha256": "<64 hex>"},
    "h8_provider_spend_cap": {"path": "docs/qualification/...", "sha256": "<64 hex>"},
    "h10_backup_restore": {"path": "docs/qualification/...", "sha256": "<64 hex>"}
  },
  "image_digests": {"postgres": "sha256:<64 hex>"},
  "valid_from": "2026-10-21T00:00:00Z",
  "valid_until": "2026-11-21T00:00:00Z"
}
```

| Field | Rule |
|---|---|
| `schema_version` | `edge-os.hosted-deployment/1`, or `edge-os.hosted-deployment/2` (the v1 fields plus `execution_release`). |
| `deployment_id` | 1 to 64 characters: letters, digits, `.`, `_`, `:`, `-`; must equal the named id. |
| `public_origins` | 1 to 20 unique `https` origins. No wildcard, path, query, fragment or user information. |
| `cors_origins` | 1 to 20 unique `https` origins; each must also be a public origin. Must equal the running `cors_origins` exactly. |
| `database_tls_mode` | `require`, `verify-ca` or `verify-full`; must equal the running `sslmode` exactly. |
| `hermes_relay.release_id` | A registered relay release id. |
| `hermes_relay.record_sha256` | The relay release record's SHA-256, 64 lower-case hex characters. |
| `research_release.release_id` | A registered operating release id. |
| `research_release.sha256` | The operating release SHA-256, 64 lower-case hex characters. |
| `execution_release` | Version 2 only, and required there: exactly `release_id` and `sha256` (64 lower-case hex). Absent from version 1. |
| `host_gates` | Exactly the four named gates. Each has exactly `path` and `sha256`. The path starts with `docs/qualification/`; the hash is 64 lower-case hex characters. |
| `image_digests` | 1 to 20 entries. Each key is 1 to 64 lower-case characters; each value is a Docker image id `sha256:<64 hex>`, not a tag or a registry digest reference. Pin only an image that does not carry the registry hash: a source-built image, including the API image, receives the registry line, so its image id depends on the record hash and cannot appear in the record. The `api` and `execution-worker` images are therefore omitted; at least one independent image id is still required. |
| `valid_from`, `valid_until` | UTC whole seconds, `YYYY-MM-DDTHH:MM:SSZ`. `valid_from < valid_until`; the start-up time must be inside the window. |

A reference is a path plus SHA-256. A free-text claim is not a reference.

## 5. What a correct record admits

One production deployment record admits exactly three parts; a version 2 record can also admit controlled execution (§5.4).

### 5.1 The `hermes_local` interpreter

`Settings.validate_rules` refuses `interpreter != "fixture"` in production unless a registered record matches the
running origins and TLS mode. `create_app` then also requires the relay release configuration: in production,
`hermes_local` needs a live configuration whose release id is the record's `hermes_relay.release_id`. A production
`hermes_local` without that configuration is refused, so the local fake provider cannot serve a hosted deployment.

### 5.2 The Hermes relay application

`open_hermes_application` (`research/hermes_relay_composition.py`) keeps its production refusal when no record is
named. With a record it binds the one approved code-owned relay definition and requires both
`release.actual.release.release_id == hermes_relay.release_id` and
`definition.record_sha256 == hermes_relay.record_sha256`. A record that names another release or another record hash
is refused before the operator handoff is read. The launcher `scripts/hermes_app_mount/serve_relay_application.py`
inherits this rule.

### 5.3 The approved research release

`server_research_runtime` (`core/research/released_runtime_bootstrap.py`) composes the code-owned approved ACTUAL
release for both entry points: the API (`create_app`) and the investigation worker (`investigation_jobs.main`). In
production it requires an approved deployment record whose `research_release.release_id` and `research_release.sha256`
equal the composed release's exact id and SHA-256.

A production configuration that names no record (both `EDGE_OS_HOSTED_DEPLOYMENT_ID` and
`EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH` are unset) composes no research release and starts. Research is then
unavailable: the server logs one line that research is off because no hosted deployment is named, saved-result reads,
sign-in and every other API route keep working, and a research job request is refused on the existing unavailable path
(`operating_release_unavailable`, or `history_source_unavailable` for a recorded source). Nothing runs and no
credential is read.

A named record still refuses startup exactly as before when it is incomplete, unapproved, unreadable, invalid, bound to
other origins or another TLS mode, outside its validity window, or does not name the exact research release. The
Hermes relay application keeps its production refusal without a record.

`local` and `test` keep the existing composition and read no deployment record.

### 5.4 Controlled execution (record version 2 only)

A version 1 record binds no execution release and grants no execution. In production, `Settings.validate_rules`
admits `execution_mode=controlled` only when the named registered record is version 2 and its `execution_release`
equals the code-owned `APPROVED_ACTUAL_RELEASES` entry (`execution/operating_release.py`) by exact id and SHA-256.
Every other case is refused with a named reason. `EDGE_OS_PRIVY_APP_SECRET` stays refused in every process
environment. See `docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md`.

### 5.5 The loopback database route (any record version)

Production refuses a loopback database host, except `127.0.0.1` when a registered record is named and the URL's
`sslmode` equals the record's `database_tls_mode` (builder decision, option A, 2026-10-23). This route is for the
host research worker. Only that literal host qualifies. Every unregistered case keeps the refusal, and so does every
other loopback, unspecified or multi-host form, record or not: a host-less URL, a multi-host list, `localhost` or
`*.localhost` in any case with or without a trailing dot, the rest of `127.0.0.0/8` in any IPv4 spelling, `[::1]`,
IPv4-mapped loopback, `0.0.0.0` and `[::]`. The check uses no DNS lookup.

## 6. Refusal codes

Errors name a code, never a configured value.

| Code | Meaning |
|---|---|
| `hosted_deployment_incomplete` | Only one of the deployment id and record path is set. |
| `hosted_deployment_id_invalid` | The named id is not a valid identifier. |
| `hosted_deployment_record_path_invalid` | The path is not a short absolute path without `..`. |
| `hosted_deployment_not_approved` | The id is not in the code-owned registry. |
| `hosted_deployment_record_unreadable` | The file is missing, not regular, or reached through a link. |
| `hosted_deployment_record_too_large` | The file is larger than 64 KiB. |
| `hosted_deployment_invalid` | The record is not strict JSON, repeats a key, or has a bad field. |
| `hosted_deployment_hash_mismatch` | The canonical hash is not the registered hash. |
| `hosted_deployment_id_mismatch` | The record names another deployment id. |
| `hosted_deployment_origin_mismatch` | The running CORS origins are not the record's origins. |
| `hosted_deployment_tls_mismatch` | The running `sslmode` is not the record's mode. |
| `hosted_deployment_outside_window` | The start-up time is outside the validity window. |
| `hosted_deployment_refused` | A registered record cannot be validated at research composition. |
| `hosted_deployment_not_matched` | No record names the exact part about to be composed. |

## 7. What stays refused

A matching record does not widen any of these:

- `wallet_provider` must stay `unavailable`; the fixture provider is refused.
- `execution_mode` must stay `unavailable`, except `controlled` for a version 2 record that binds the exact approved
  execution release (§5.4); fixture execution is refused.
- `research_history_mode` must stay `unavailable`; recorded synthetic history is refused.
- `research_source_clients` must stay `recorded`; the authored HTTP transport is refused.
- `nansen_research_mode` must stay `unavailable`; the authored Nansen transport is refused.
- Fixture effects, original recordings and the test app id stay refused.
- A stand-in research release stays refused.
- The Hermes transport mount keeps its existing production refusal.
- Funding, trading and signing stay unavailable; this ticket changes no wallet, execution or financial path.
- `EDGE_OS_ENV=local` behind HTTPS is still not an approved route.

## 8. Host gates bound by the record

| Gate | Where the record binds it |
|---|---|
| H1 provider-only egress | `host_gates.h1_egress` path and SHA-256 |
| H2 qualified isolated runner | `host_gates.h2_runner_isolation` path and SHA-256 |
| H5 database TLS | `database_tls_mode`, matched against the running `sslmode` |
| H8 provider money limits | `host_gates.h8_provider_spend_cap` path and SHA-256 |
| H10 off-VPS backup and restore | `host_gates.h10_backup_restore` path and SHA-256 |
| H13 VPS facts and domain | `public_origins` and `cors_origins` |

H3, H4, H6, H7, H9, H11 and H12 are still deployment-plan work. H9 abuse protection and H13 facts are requested in
`worker/HOST_FACTS_REQUEST1.md`. They are not code admission bindings in this record version.

## 9. Change control

- A record is immutable once approved. Any change to any field produces a new canonical hash and needs a new
  reviewed registry entry.
- The validity window is the deployment's review period. An expired record admits nothing until a new record is
  approved.
- Removing a registry entry removes the approval for every process started after that build.
- A running process keeps the deployment it started with. Start a new process to apply a changed record.

## 10. Tests and evidence

Pure tests, no database, Docker or network:

- `apps/api/tests/test_hosted_deployment.py`: empty registry, no record, incomplete pair, unregistered record,
  relative path, matching record, canonical hash, changed field, origin mismatch, TLS mismatch, expired window,
  malformed records, repeated keys, symbolic link, oversized file, part predicates, settings admission, retained
  refusals, local behaviour, production `create_app` and worker startup with research off and one log line, and named
  incomplete, unapproved, expired or non-admitting records still refused at composition.
- `apps/api/tests/test_hosted_relay_admission.py`: production without a record, fixture interpreter, bound relay
  release admitted to the handoff, another release id refused, another record hash refused, local admission unchanged.
- `apps/api/tests/test_approved_nansen_bootstrap.py`: the code-owned default stays registered; `local` composes it;
  `production` composes nothing and logs one line when no hosted record is named.
- `apps/api/tests/test_operating_release_research.py`: a saved release job with an absent runtime ends
  `UNAVAILABLE` on `operating_release_unavailable` before any provider request.

Mounted tests in the existing suite cover the relay composition and the settings routes. The full API suite is the
submission check.

## 11. Non-claims

- No hosted deployment record is approved. The registry is empty.
- No host, DNS name, proxy, certificate, server, account, provider, credential, database or container is created or
  changed by this ticket.
- H1, H2 and H10 remain NOT RUN.
- The record cannot be satisfied by this ticket alone. The builder must supply the host facts and approve one exact
  record in a later reviewed change.
- No public HTTPS link exists after this ticket.

## 12. Sources

- `docs/qualification/release-host-preparation/HOST_DECISION_PACKET.md` section 8 (H1, H2, H5, H8, H10, H13).
- `core/research/operating_release.py` (`APPROVED_RELEASES`, release SHA-256 rules).
- `scripts/hermes_provider_relay/relay_admission.py` (`APPROVED_ACTUAL_RELEASES`, release records).
- `research/hermes_relay_composition.py` (`RELEASE_DEFINITIONS`, `bind_release`, `open_hermes_application`).
- `core/research/released_runtime_bootstrap.py` (`server_research_runtime`).
- `core/settings.py` (production refusals) and `main.py` (`create_app`).
- `docs/CONTROLLER_HANDOFF.md`, demo blocker 6: do not set `EDGE_OS_ENV=local` behind HTTPS.
