# P04 offline qualification fixtures

These standard-library checks exercise independent local fixtures for owner/agent scoping, memory version use, duplicate jobs, task-directory path checks, cancellation/timeout cleanup, strict P02 `Outcome` parsing, redacted errors, usage reservations and fake provider/network-denial behavior. They do not import or run Hermes and make no network calls.

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

The P02 output test preserves `NEEDS_CLARIFICATION`, `UNSUPPORTED`, `UNRESOLVED`, `INVALID_INPUT`, `COMPILED` and `CONFLICTED`, rejects malformed/truncated JSON, unknown outcomes, missing intake IDs and extra fields. The production adapter must validate against the exact pinned machine contract, not trust this small independent checker.

No packages, provider credentials, sample code, real inference, host configuration or wallet behavior are used. `python3 -B` avoids writing bytecode. Temporary data is removed by `TemporaryDirectory` after success, failure, timeout or cancellation.
