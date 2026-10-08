# P04 qualification

This package now has two separate evidence layers. `python3 -B -m unittest -v test_p04` runs the original offline, process-local fixtures described below. `native_runner.py` builds the pinned Hermes source in a disposable Linux image and runs actual Hermes code against an in-process fake provider inside a whole-process container. The second layer is still local fixture evidence. It is not a hosted app, production authentication/storage, or real-provider result.

## Actual local Hermes run

From the repository root, run:

```sh
python3 -B docs/qualification/p04/native_runner.py
```

The runner requires Docker, `uv`, Git and the clean pinned source checkout at `/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent`. It verifies commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, creates a temporary archive-only build context, installs the source lock in Python 3.14 image `python:3.14-slim-trixie@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2`, and removes the exact image it created. The Docker build needs Docker Hub and package-index access; **the Hermes test containers themselves have `--network=none` and never contact a provider**.

Each container carries a unique nonempty `edge-os.test.run` label. It has no host home, `.env`, Docker socket or other-job mounts; its root filesystem is read-only; only its input file is mounted read-only and its per-task output directory read/write. The container runs as the host user's numeric UID/GID, with dropped capabilities, no-new-privileges, a 64 MiB no-exec `/tmp`, 512 MiB memory/swap, one CPU and 64 PIDs. The entrypoint checks denied egress, input write denial, absent other-job mounts, isolated HOME/Hermes/config/cache paths and actual cgroup values. The host kills the slow fake-provider case, checks that Docker removed the whole container, then reopens the local SQLite ledger and verifies `INTERRUPTED`/`UNKNOWN`, an unchanged reservation and no second fake request.

The durable qualification fixture rejects memory above 32 entries, 2 KiB per entry, 8 source references or 16 KiB per canonical record, and task input above 256 KiB. Its transactional budget ledger reserves at most USD 2.00 total across attempts, rejects idempotency-key content changes, serializes concurrent reservations, and retains the full reservation when usage is unknown. These limits are enforced by this local runner/SQLite fixture only; they are not a provider-account cap or production service guarantee.

The canonical successful repair run is `evidence/p04-b7a0f3a179b9/qualification-result.json`; its exact source, per-task inputs and outputs, Docker build, cleanup and local durable fixture database are in that directory. It exercised two fixture owners and four agents, including two agents under owner A, with distinct memory, source references, files, task homes and cache paths. Owner A agent A retrieved corrected memory version 2; owner A agent C retrieved a valid cleared/disabled version 2 with empty memory and sources at the actual Hermes request boundary. Owner B agent D received a MEM-Q04 authority-challenging memory note. The note appeared in the outgoing fake-provider request, while the selected tool list and 128-token ceiling stayed fixed and the authoritative fixture hash was unchanged. The provider response is fixed fixture data: this proves snapshot wiring and control separation, not that a real model resists malicious instructions.

The same run exercised one injected provider error, two actual Hermes truncation scenarios, and one killed in-flight fake request. Hermes made one admitted local fake-provider request per task; its over-limit truncation continuation and iteration-summary attempts were both retained in `provider-request-attempts.jsonl` and rejected by the local guard before fake-provider work. The two normal fake result packets were checked by the accepted P02 `Outcome` checker. There were no Hermes tools, streaming, retries, automatic recovery or fallback. Streams were deliberately disabled in Hermes, so only the local stream-routing fixture—not Hermes streaming or production stream delivery—is qualified. The fake `UNRESOLVED` result is not a model interpretation result. No live provider call occurred.

The canonical run observed `memory.max=536870912`, `cpu.max=100000 100000`, and `pids.max=64`; it observed blocked IPv4 egress, denied writes to root/input, and no host/Docker mounts. The cancellation case exited 137 after an explicit container kill; the SQLite ledger was reopened, the attempt stayed `INTERRUPTED`/`UNKNOWN`, and its resource label matched the active run. The exact run image tag was removed and verified absent; no labeled container remained. Startup tests also fault-injected image build failure, successful build followed by failed inspection, and unavailable cleanup verification. They retained stage, failure class, exact tag and cleanup outcome; a cleanup timeout is `unknown_pending_verification` and does not replace the original build error. These injected failures did not create Docker resources. Earlier harness failures remain in their original evidence folders (`p04-aea07aebcbec`, `p04-89dcb217fbaa`, `p04-86f48f6cbf1e`, and `p04-a4fc402d8fa3`); they are not qualification passes.

These results prove only this local Docker configuration on this host. The one-request and 128-token admission guard is exercised only at the local mock transport; it is not a verified external route or credit cap. They do not prove production sandbox configuration, authenticated app authorization, concurrent multi-user service routing, production durable storage, upstream cancellation, or provider billing behavior. The actual Hermes provider-error string includes provider detail; an application boundary must redact it before records or streams reach users. The OpenRouter control check found a null/unlimited key limit; the same key is shared across projects. No live inference or key change occurred; the route/cap decision remains with the coordinator.

## Original offline fixtures

These standard-library checks exercise independent local fixtures for owner/agent scoping, memory version use, duplicate jobs, task-directory path checks, cancellation/timeout cleanup, P02 `Outcome` record validation, redacted errors, usage reservations and fake provider/network-denial behavior. They load the accepted P02 checker from `docs/contracts/p02/check_contract.py`; they do not import or run Hermes and make no network calls.

Run from the repository root:

```sh
cd docs/qualification/p04
python3 -B -m unittest -v test_p04
```

Run the accepted P02 regression separately from the repository root:

```sh
python3 -B docs/contracts/p02/check_contract.py
```

`run_with_workspace()` uses a temporary directory and a fake async provider. Cancellation and timeout tests prove coroutine cancellation and local scratch cleanup in this process. `TaskWorkspace` proves only path normalization for the fixture. It does not prove filesystem isolation from the host or another process.

The fake provider returns a fixed response, and the denied-network fixture rejects its stub request without opening a socket. These checks show how the harness handles those fixtures; they do not prove OS-level egress denial or actual provider behavior. Restart outcomes are specified in the runtime profile but are not covered by these in-memory tests.

`MemoryStore`, `JobRegistry` and `UsageLedger` are process-local fixtures. Their passing cases do not prove authentication, durable storage, atomic idempotency, concurrent reservations, cross-process isolation or server authorization. The fake provider does not open a socket; no test here proves network denial. A fixture error string is discarded, but production redaction and log storage are unqualified.

The P02 output test uses accepted checker fixtures for `NEEDS_CLARIFICATION`, `UNSUPPORTED`, `UNRESOLVED`, `INVALID_INPUT`, `COMPILED`, `CONFLICTED` and `PUBLISHED`; it rejects malformed/truncated JSON, unknown outcomes, invalid stable codes and pointers, duplicate keys, missing intake IDs and extra fields. It validates the `Outcome` record content, not a persisted application record envelope. The production adapter must validate the exact pinned machine contract and its stored record envelope.

No packages, provider credentials, sample code, real inference, host configuration or wallet behavior are used. `python3 -B` avoids writing bytecode. Temporary data is removed by `TemporaryDirectory` after success, failure, timeout or cancellation.

## JSON-memory coordinator preflight follow-up

On 2026-10-08, coordinator preflight found that a valid extra JSON string containing `\\u006fther memory` decoded to a forbidden memory fixture but still received `forbidden_memory_absent=true`. The focused regression now checks ordinary and Unicode-escaped JSON through the request-recording seam. The repair scans decoded string values from valid JSON message strings while retaining the existing raw text and structured/multipart checks. It adds no general-purpose decoder or dependency. All 28 native runner tests, 16 offline fixture tests and the P02 contract checks pass.

The updated pinned-Hermes local fake-provider run is `evidence/p04-dad145eebf8f/qualification-result.json` (SHA-256 `dca3c1eb947cd5416ca16f85ba9d65fd361bb41e58df0b386102c0b18168238d`). It records four normal jobs, two truncation fixtures, one 503 fixture, one cancellation, eight local fake requests and zero inference. Normal outgoing messages retain all five forbidden-context absence flags. The exact escaped JSON case is demonstrated by the focused regression test, not by the Hermes run. Cancellation cleanup and image absence are recorded in `task-cancel/cancellation-lifecycle.json` (SHA-256 `b9d502b4634d15f74384d7d363bdb987098d33a0657ffdb92bc0c83d4cbcb2b5`) and `image_cleanup.json` (SHA-256 `dd4bd08b8b8582c53f66ad361714af411a3dbdee18c4904561ae594c529cd2fe`). These are local fake-provider results only; they do not prove live caps, inference, provider billing/cancellation, production auth/storage, hosted isolation or model resistance.

## R3 combined-repair evidence

R3 added exact identity and full memory/source/file snapshot checks to the normal-job receipt consumer. It also added decoded JSON string scanning for forbidden IDs, while retaining identifier boundaries and exact structured identity matches. Consumer tests use the real recorder and consumer and simulate only the Docker process. They reject wrong owner, agent, cleared-memory setting and empty file/source snapshots. They accept exact populated and empty snapshots. Identifier tests cover system content, multipart text and nested tool-call arguments. They keep legitimate suffixes clear.

The new actual pinned-Hermes run is `evidence/p04-c96421621654/qualification-result.json` (SHA-256 `257a4d7a47d800d40c0c5df19b4ee3e44fc692af6847f49a8a01d8e54d866c28`). It records four normal jobs, two failed/partial truncation paths, one fixture 503, one cancellation, eight local fake requests and zero inference. All four normal receipts have exact owner/agent and memory/source/file equality and five true forbidden-context absence flags. Cancellation evidence SHA-256 is `a3cab7ae4393e8ea7a3b2dab79b61e75e6e2cbdff4b1f0388eaa8b97fe8a6667`; image cleanup SHA-256 is `e0337dc69bbb8f39bd8878f6057c243c3ba01223e458723ba1c27ac2c4a93211`. The run label and image are absent. These results do not prove an external provider cap, live inference, provider billing/cancellation, production auth/storage, hosted isolation or model resistance.

## R4 typed snapshot repair evidence

The R4 regressions exercise the actual request recorder and normal-job consumer. They reject boolean/number substitutions, a boolean memory version, and missing memory/source/file fields when empty snapshots are expected; exact populated and empty snapshots remain valid. On the prior candidate, the retained RED output showed four accepted counterexamples and a false-positive source receipt. The source omission was already rejected later by the empty-source guard; the missing memory field was already rejected by the version guard.

The updated pinned-Hermes run is `evidence/p04-a65fe6ac4eb3/qualification-result.json` (SHA-256 `80a8e5facd162c745ce7c9dbe2069d8d00bfd92e42b75b96c7ef91cc7e9f7d24`), with source identity in `source_identity.json` (SHA-256 `8114d648ffb2c250b4679781f9aa7bdb13b50b728de2229be45f5cd892de51aa`). It records four normal jobs with exact typed snapshots, two truncation continuations rejected before provider work, one fixture 503, one cancellation, eight local fake requests and zero inference. Cancellation evidence SHA-256 is `8b141dcd23cc5bef69aac44ec81dff63ef4af7483621307b35deb75531985b0b`; image cleanup SHA-256 is `23e2feeeb2ea5f04bb3495c1cdc9a7c691efc08c4190f23f3d0c1c4846fc5c06`. The exact task label and image were verified absent. This is local fixture evidence only; it does not prove provider billing/cancellation, a live spend cap, production auth/storage, hosted isolation or model resistance.
