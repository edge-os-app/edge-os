# Hermes job support: the provider transport job (P05 / issue 58 support)

Task HERMES-JOB-L1-20261012-01. Status: LOCAL support, shown with authored replies only. The actual provider path is NOT_RUN and unavailable in this code. This folder gives no authority: no live request, no credential, no network, no spending.

| File | What it holds |
|---|---|
| `README.md` | The integration note: the contract for lane 2, what is shown locally, how to check it. |
| `ACTUAL_QUALIFICATION_PACKET.md` | The concrete NOT_RUN packet for a later actual-provider qualification, with its open decisions. |
| `JOB_IDENTITIES.json` | SHA-256 of each new helper file and of the accepted files it depends on. A test compares it with the code. |

## 1. What it adds

Pinned Hermes (commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, `uv.lock` SHA-256 `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01`) runs in the accepted no-network container. Its one HTTP request now goes through an injected provider transport, behind the accepted provider guard:

```
Hermes client (placeholder URL and key)
  -> physical admission   POST to the placeholder URL, SDK header names only, JSON, no streaming, SDK retry count 0,
                          body session_id = "p05-<attempt id>"
  -> provider guard       accepted P05 guard: model, max_tokens, prompt, task, envelope, one request per attempt
  -> host request         route endpoint, three fixed headers, host credential, the admitted body byte for byte
  -> ProviderTransport    AUTHORED only in this candidate
  -> reply admission      status 100-599, at most max_reply_bytes, a JSON object; otherwise 502 and its content dropped
```

Hermes' client never holds the host's endpoint or credential. The credential file is mounted read-only into the job container, and only the transport passes its value on; Hermes' client carries `fixture-only-not-a-secret`, which the guard requires. The job, the transport and Hermes share one process, so Hermes code could read the copy: this is not isolation from Hermes code. It keeps the credential out of Hermes' client, its request dumps and its logs, and sealing still removes it from all evidence.

New files:

| Path | Responsibility |
|---|---|
| `scripts/hermes_job_support/provider_transport.py` | The contract: route, physical request, host request, reply, the three admission functions, `ProviderTransport`, `TransportLost`, `ActualProviderUnavailable`. Standard library, no I/O. |
| `scripts/hermes_job_support/authored_transport.py` | The AUTHORED transport: plays the accepted fake provider's scripted reply, with optional faults `lost_reply`, `oversized_reply`, `crash_after_send`. |
| `scripts/hermes_job_support/transport_turn_job.py` | The container entrypoint. Reuses the accepted `hermes_turn_job` and `provider_guard`. |
| `scripts/hermes_job_support/transport_turn_runner.py` | The host side: `build_transport_job`, `TransportTurnRunner` (identity check), `TransportJob`. |

Changed accepted file: `scripts/hermes_interpretation/guarded_docker_runner.py` gets one seam, `JobEntry` (`job_entry=` on the runner). The default is the accepted guarded job, unchanged. Another entry adds read-only files under `/opt/p05job` only, its script must be one of them, and its settings reach the job as `job_settings`. The entry is captured once per turn in the turn plan, like the policy. `guarded_turn_job.py` is unchanged. `docs/qualification/hermes-provider/IDENTITIES.json` changes only in the runner's hash (lease amendment A1).

## 2. The contract for lane 2

This is the consumable interface. Lane 2 owns the application mounting; nothing here is mounted.

**Construction.** `build_transport_job(route, *, policy, ledger, scope_for, image, run_id, evidence_dir, script_for, credential_file=None, forbidden=(), timeout_seconds=90, run_budget_seconds=60, seal_grace_seconds=5.0, recovery_budget_seconds=5.0) -> TransportJob`. It does no I/O: it reads no file, writes nothing, reads no credential and starts nothing. An ACTUAL route raises `ActualProviderUnavailable` before anything is built. There is no flag that enables a network transport or a real credential; adding one needs a separate approval packet and its own reviews.

**Use.** `TransportJob.runner` is a `HermesTurnRunner`; give it to `HermesInterpreter` (`apps/api/src/edge_os_api/research/hermes_interpreter.py`), which records the attempt before the call and settles it after. One `interpret`/`follow_up` call is one attempt, one `HermesTurn`, at most one physical request. Nothing retries.

**Identity.** The interpreter's attempt id is the only identity: the attempt ledger row, the spend reservation (`SpendLedger`, keyed by attempt id), the job input, the wire body `session_id` (`p05-<attempt id>`), the host request's `attempt_id`, and the saved `runtime_observed` fields `transport_attempt_id`, `transport_request_attempt_ids` and `transport_route_id`. `TransportTurnRunner` withholds a result as UNKNOWN (`TransportIdentityMismatch`, text dropped, request count unknown) when the job's report names another attempt, another route, more than one request, or a count that disagrees.

**Results and accounting** (all from the accepted `GuardedTurnRunner`):

| Outcome | Saved status | Spend |
|---|---|---|
| One request, usable reported usage | COMPLETED or TRUNCATED | SETTLED, exact |
| Refused before the transport (physical or guard) | UNKNOWN (Hermes raises after the 429) with request count 0 | RELEASED: the guard's own count is 0 |
| Policy, cap, scope or cleanup refusal before a job | PROVIDER_FAILED, count 0 | RELEASED, or never reserved |
| Lost reply, oversized reply, job crash, missing usage, timeout, identity mismatch | UNKNOWN, PROVIDER_FAILED or TIMED_OUT | UNKNOWN: the full reservation stays and blocks the scope |
| Settlement write fails | the result stands | SETTLEMENT_NOT_RECORDED: the reservation stays RESERVED |

**Cancellation and deadlines.** D is made once per turn from the admitted settings (`timeout_seconds + seal_grace_seconds`) and never renewed; the transport adds nothing to it. The job wait ends early enough for stop, sealing and the move. A hung provider is stopped at the job deadline. The ledger commit after the runner is outside D, as the accepted cleanup rule allows. A kill does not prove that the provider stopped: OpenRouter's documentation (checked 2026-10-12, below) says a non-streaming request keeps running and is billed in full.

**Supervision and restart.** `TransportJob.supervision` is the accepted runner: `recover_pending(C)`, `pending_cleanup()`, `retry_exhausted()`, `purge_quarantine()`. Each turn runs `recover_pending` first. After a host crash, the turn's pending record (container, label, turn folder) survives; a later process with the same `run_id` and evidence folder recovers it within one budget C: it kills the container only if name and label match, removes the output and deletes the record. Recovery never touches the spend ledger. The dead attempt's reservation stays RESERVED and blocks its scope until a person reconciles it. Another run's recovery never touches this run's record or container.

**Bounds.** Request: the guard's `max_request_bytes`. Reply: `TransportRoute.max_reply_bytes` (at most 1 MiB), checked before anything parses it. Job output, stdout, result file and evidence: the accepted runner's bounds (1 MiB stdout, 256 KiB result, 8 MiB per scanned file, 10,000 entries, quarantine on overflow). Transport evidence: at most 16 records per turn. Container: no network, read-only root, 512 MB, 1 CPU, 64 processes, no capabilities, private `HOME` and `HERMES_HOME` under `/tmp`, no socket, no host workspace mount.

**Proposed for later mounting (lane 2, not done here).** Select this runner behind the existing refused-in-production setting; keep `runtime_label` LOCAL until a recorded live release; call `recover_pending` from a supervised scheduler as well as per turn; move the spend ledger to shared durable storage with the same rules. These are proposals.

## 3. What the local tests show

Authored replies, a dummy sentinel credential, no network. `tests/hermes_job_support/`:

- `test_provider_transport.py`: the physical admission refuses wrong method, URL, query, streaming accept, SDK retry, unknown or repeated headers, non-JSON bodies and another attempt's `session_id`; the host request carries only the host's endpoint, headers and credential with the exact body; replies over the limit or not JSON are refused; routes must be bounded https endpoints.
- `test_transport_turn_runner.py`: construction does no I/O; an ACTUAL route is refused before anything is built; an identity mismatch is withheld and keeps the reservation; a turn that started no job releases it; a failed settlement keeps it.
- `test_transport_job_through_pinned_hermes.py` (ACTUAL pinned Hermes, Docker): one admitted request with every identity equal to the attempt and an exact charge; guard refusal and physical refusal before the transport, both released; lost reply, oversized reply, crash after the provider worked and missing usage keep the full reservation and publish nothing; a hung provider is stopped by D; two tasks at the same time keep their own identities and charges; a host killed mid-turn leaves a pending record that a restart recovers, while the dead attempt's reservation stays and blocks its scope.
- `test_job_support_package.py`: `JOB_IDENTITIES.json` equals the code, and these documents keep their NOT_RUN labels and hold no credential.

Not shown: any real provider, model, network, price, billing stop or production host behavior.

## 4. How to check

From `apps/api`, with the locked environment:

```
uv run --frozen pytest -p no:cacheprovider -q ../../tests/hermes_job_support/test_provider_transport.py ../../tests/hermes_job_support/test_transport_turn_runner.py ../../tests/hermes_job_support/test_job_support_package.py
HERMES_JOB_EVIDENCE_DIR=<private folder> uv run --frozen pytest -p no:cacheprovider -q ../../tests/hermes_job_support/test_transport_job_through_pinned_hermes.py
uv run --frozen pytest -p no:cacheprovider -q tests/provider_safeguards ../../tests/hermes_interpretation/provider_safeguards
```

The second and third commands need Docker. They build the pinned Hermes image from `git archive` of the pinned commit; with Docker's layer cache the build reuses unchanged layers and needs no network. Each run removes its own image and containers by exact tag and label. The pinned real-Hermes runs take about two to three minutes.

To regenerate `JOB_IDENTITIES.json` after a pinned file changes: `uv run --frozen python ../../scripts/hermes_job_support/job_identities.py > ../../docs/qualification/hermes-job-support/JOB_IDENTITIES.json`.
