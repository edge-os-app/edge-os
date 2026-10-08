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

The retained successful run is `evidence/p04-d47539cd31d6/qualification-result.json`; its exact source, per-owner task inputs and outputs, Docker build, cleanup and local durable fixture database are in that directory. It exercised two owners/two agents with distinct memory, source references, files and cache paths, then one injected provider-error case and one killed in-flight fake request. A separate SQLite stream fixture confirmed owner/agent/job-scoped event reads after reopen and denied a cross-owner read. The two completed fake result packets were checked by the accepted P02 `Outcome` checker. Hermes made one local fake HTTP request per case, with no tools, no streaming, one configured API attempt, zero automatic recovery and zero fallback. Streams were deliberately disabled in Hermes, so only the local stream-routing fixture—not Hermes streaming or production stream delivery—is qualified. The local fake result is `UNRESOLVED`; it is not a model interpretation result.

The test run observed `memory.max=536870912`, `cpu.max=100000 100000`, and `pids.max=64`; it observed blocked IPv4 egress, denied writes to root/input, and no host/Docker mounts. The cancellation case exited 137 after an explicit container kill; the SQLite ledger was reopened, the attempt stayed `INTERRUPTED`/`UNKNOWN`, and its resource label matched the active run. No labeled container remained. The source and dependency lock hashes are recorded beside the result. `p04-aea07aebcbec` and `p04-89dcb217fbaa` retain earlier failed harness runs and their sanitized failure notes. Those failures are not qualification passes.

These results prove only this local Docker configuration on this host. They do not prove production sandbox configuration, authenticated app authorization, concurrent multi-user service routing, production durable storage, upstream cancellation, or provider billing behavior. The actual Hermes provider-error string includes provider detail; an application boundary must redact it before records or streams reach users. No real inference was sent. The OpenRouter control check found a null/unlimited key limit; see the frozen controller evidence for the resulting live-call hold.

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
