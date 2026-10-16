# Saved-history payload binding

Status: LOCAL implementation contract for task `SAVED-HISTORY-BINDING-L2-20261015-LOCAL-v1`. It connects the accepted
forward-history checker (`docs/qualification/forward-history-recorder/CONTRACT.md`, section "Saved-export checker") to
saved application datasets. It authorizes no provider, credential, chain, account, wallet or recording operation.
All evidence in this ticket is SYNTHETIC.

## What a binding proves

A binding compares the raw records that the application saved with the exact recorder handoff bytes. A PASS proves
payload equality for the four 300-second buckets only. It does not prove the owner, database provenance, provider
provenance, source rights, P07 qualification, market adoption, replay authority or execution timing. The P07 verdict,
raw records and bucket times are never changed by any binding outcome.

## Release definition

A history release may name one frozen handoff in `HistoryRelease.provider_facts["forward_history_binding"]`:

```text
{handoff_json: str, handoff_sha256: str}
```

The value is part of the release content, so its bytes enter the release SHA-256. A release without the key keeps its
hash. Admission (`core/research/operating_release.check_release`) validates the value before any credential read and
refuses with a stable code:

| Condition | Code |
|---|---|
| Release kind is not `STAND_IN` | `forward_history_binding_not_admitted` |
| Not exactly the two text fields | `forward_history_binding_invalid` |
| Handoff larger than the checker's 8 MiB handoff ceiling | `forward_history_binding_invalid` |
| Digest differs from the UTF-8 bytes | `forward_history_binding_invalid` |
| Not strict JSON, or not an object | `forward_history_binding_invalid` |
| Other handoff schema or canonicalization version | `forward_history_binding_invalid` |
| Evidence class is not `SYNTHETIC` | `forward_history_binding_invalid` |
| Source, window or scan differs from the release | `forward_history_binding_invalid` |
| Pinned checker is missing or changed | `forward_history_checker_unavailable` |

`APPROVED_RELEASES` and `RELEASE_DEFINITIONS` stay empty. Only local and test code composes a stand-in release.

## Checker adapter

`research/history_payload_binding.py` loads `scripts/history_payload_binding.py` by repository path, as the P02
adapter does. It pins the accepted bytes (SHA-256 `1c74d8c9bce020e35bb372dd4a363641f1ed35566263163a9dd18807264fd667`)
and executes exactly the bytes it hashed. A missing or changed checker gives INCOMPLETE, never PASS. The adapter calls
`check_saved_export(bytes, Mapping, Mapping) -> dict` and `PayloadError.code` and copies no canonicalization. Because
it bypasses the CLI's bounded file reads, it enforces the CLI ceilings itself: handoff 8 MiB, canonical export 64 MiB
and expected identities 64 KiB.

The API image copies only this checker from `scripts/` (`deploy/docker/api.Dockerfile`, `.dockerignore`), at
`/app/scripts/history_payload_binding.py`. `tests/deployment_rehearsal/test_image_definitions.py` lists it as a required
runtime asset. If the file is missing or changed, every required binding is INCOMPLETE.

A saved binding records the checker identity it ran with, and its row and `HISTORY_PAYLOAD_BOUND` event are immutable.
After a reviewed re-pin of the checker, every binding saved under the earlier identity stays INCOMPLETE with reason
`CHECKER_IDENTITY_DIFFERS`. Its earlier PASS is never adopted and the dataset is never rebound: a consumer needs a new
collection bound under the currently accepted checker.

## Collection

1. The collection attempt's `ATTEMPT_STARTED` event freezes `payload_binding_requirement`
   `{basis: "RELEASE_FORWARD_HISTORY_BINDING", handoff_sha256}` before any credential read or request.
2. The worker copies the same requirement identity into the dataset content before the content is hashed. The
   handoff text never enters the dataset content.
3. The worker saves the dataset, flushes it, reads the stored owner-scoped row back and runs the checker on that row's
   `raw_records`. The expected owner, dataset, source, release and handoff hash come from the job, the row and the
   attempt's started event. No request field and no external PASS report is used.
4. One `HISTORY_PAYLOAD_BOUND` event joins the dataset transaction under the existing unique
   `(job_id, attempt_id, kind)` constraint. It holds the exact handoff text, the trusted expected identities, the
   checker identity, the report or null, the report hash, the result and a reason. Every outcome is saved.

Job views show this event without `handoff_json`, with `handoff_bytes` instead.

## Consumers

Market adoption and history replay call `require_bound`. It selects the started event and the binding event through
the same owner, job and attempt, checks the dataset id, expected identities, handoff hash and saved report hash, then
reruns the checker on the stored row. A saved PASS alone grants nothing: the rerun must PASS and reproduce the saved
report hash.

| State | Meaning | Consumers |
|---|---|---|
| `NOT_REQUIRED` | Unbound synthetic dataset | Unchanged behavior; no lineage is added |
| `PASS` | Rerun passes and equals the saved report | Allowed; lineage saved |
| `MISMATCH` | A hash, identity, payload, count, delivery or version contradiction, or a rerun that differs from the saved report | Refused, 409 `payload_binding_mismatch` |
| `INCOMPLETE` | Required evidence, event, requirement or checker missing, or a binding saved without a report | Refused, 409 `payload_binding_incomplete` |

Binding is required for every dataset of an explicitly bound release and for every `PROVIDER_ACTUAL` dataset. An
actual dataset has no admitted binding yet, so it is INCOMPLETE. A synthetic handoff never binds an actual dataset:
the checker's evidence-side check reports MISMATCH, and nothing is relabelled.

Adoption saves `payload_binding` lineage in its saved response. Replay saves it in
`inputs.history_input.payload_binding`, which is part of the run-configuration identity. A changed binding under a
reused configuration id is the existing `run_configuration_id_reused` conflict.

Owner views expose `payload_binding` with status, `required_by`, evidence class, reason, handoff, report and checker
hashes and the claim limit: the dataset list, the dataset view and each job's dataset summary. The web views block
adoption and replay controls for MISMATCH and INCOMPLETE and show the reason. A reopened replay shows its saved binding
lineage and replay profile identity.

## Failure matrix

| Condition | Result |
|---|---|
| Foreign owner or dataset | Existing 404; no evidence and no consumer write |
| Missing required handoff, event or checker | INCOMPLETE; consumers blocked |
| Hash, identity, payload, count, delivery or version contradiction | MISMATCH; consumers blocked |
| Malformed or oversized admission | Stable refusal before credentials or effects |
| QUALIFIED P07 with failed binding | QUALIFIED kept; consumers blocked |
| Synthetic handoff with actual dataset | Blocked; never relabelled |
| Crash before the dataset transaction commits | Unknown collection liability kept; no recollection |
| Crash after commit | One dataset and one event reused; no duplicate collection |
| Changed binding with reused configuration id | Existing configuration conflict |

## Verification

Pure checks need no database, socket or provider. One test in `test_forward_history_binding_pure.py`,
`test_the_loopback_provider_serves_the_four_bucket_page_and_restores_the_lookup`, starts an owned 127.0.0.1 server for
the mapped verifier's stand-in. It is not pure, so the pure command deselects exactly that node. pytest takes its
rootdir from `apps/api/pyproject.toml`, so node IDs are relative to `apps/api`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONPATH=apps/api/src:apps/api/tests:scripts/p03:. apps/api/.venv/bin/python -B -m pytest --noconftest \
  -p no:cacheprovider -q apps/api/tests/test_forward_history_binding_pure.py \
  apps/api/tests/test_operating_release_validation.py tests/test_history_payload_binding.py \
  --deselect tests/test_forward_history_binding_pure.py::test_the_loopback_provider_serves_the_four_bucket_page_and_restores_the_lookup
```

`apps/api/tests/test_saved_history_payload_binding.py` proves the matrix with PostgreSQL and the worker. The mapped
release verifier (`scripts/p03/research_phase.py`, `run_bound_release_phase`) runs one bound four-bucket stand-in source
plus the existing Nansen stand-in through the API, restarts the API and worker, inspects SQL directly and reopens the
results in a new browser context at desktop and 390 px.

## Limits

The four-bucket stand-in source and its handoff (`apps/api/tests/forward_history_stand_in.py`) are authored from a local
recording. They are not provider, chain or delivery evidence. Actual transport provenance, an `ACTUAL` handoff, provider
reads, exact release approval, credentials, market, mechanics, finality and rights evidence remain separate decisions.
The delayed replay profile is not active here: replays keep the existing profile and honest results until the accepted
lane 4 handoff and a recorded amendment.
