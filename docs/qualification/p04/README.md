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
