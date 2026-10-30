# Research environment credentials

Status: source seam (#58 RESEARCH-ENVIRONMENT-CREDENTIALS-L4). That milestone enabled no release and delivered no
credential. Current state: exactly one Nansen-only ACTUAL release is registered in the code-owned default and this
source reads a slot lazily at job preparation; no actual operation is proved. See
`docs/qualification/research-provider-composition/NANSEN_ACTUAL_RELEASE.md`.

## What exists

`edge_os_api.core.research.environment_credentials.EnvironmentCredentialSource` implements the existing
`CredentialSource.read(slot: str) -> str` from `released_source_runtime.py`.

- Allowed slots: `HYPERSYNC_API_KEY`, `QUICKNODE_API_URL`, `NANSEN_API_KEY` (`ALLOWED_SLOTS`). The slot name is the
  exact server-owned name a release's `*_credential_slot` field carries.
- Any other slot raises `CredentialUnavailable("the credential slot is not allowed")` before `os.environ` is read.
- An allowed slot reads `os.environ` only inside `read(slot)`. A missing, empty or whitespace-only value raises
  `CredentialUnavailable("the credential slot has no value")`. A nonblank value is returned unchanged.
- Import and construction read nothing. The object holds no state, so every call sees the current environment.
- It does no logging, file read, settings lookup, URL parsing or network call. Messages hold no value or slot name.
- The QuickNode URL host and scheme stay checked by `prepare_history` (`operating_release_endpoint_mismatch`), and any
  source failure stays mapped by `_read` to `operating_release_credential_unavailable`.

## Current state

`RELEASE_DEFINITIONS` and `operating_release.APPROVED_RELEASES` now carry exactly one approved Nansen-only ACTUAL
release, so `server_research_runtime` composes that one release and still reads no credential at composition. This
source reads its slot lazily at `prepare_history` / `prepare_nansen` only. No actual operation, credential read or
public right is proved. See `docs/qualification/research-provider-composition/NANSEN_ACTUAL_RELEASE.md`.

## Caller handoff (later owned tasks)

1. API and worker composition pass `credentials=EnvironmentCredentialSource()` explicitly to
   `released_runtime_bootstrap.server_research_runtime`. The registries now carry exactly one approved Nansen-only
   release, so the call composes that release and reads nothing; an explicitly emptied registry returns `None` and
   reads nothing.
2. Keep the bootstrap refusal when no source is passed (`operating_release_credential_unavailable`).
3. Deliver the three variables to the API and worker processes in a later owned compose edit.
4. An actual release needed its reviewed definition and approved SHA-256; the registration is recorded in
   `NANSEN_ACTUAL_RELEASE.md`. This source adds neither, and no actual operation follows.

## Proof

`apps/api/tests/test_environment_credentials.py` runs with `--noconftest` and literal fake values on a recording copy
of `os.environ`. It covers the three reads, missing/empty/blank refusal, unchanged values, unknown slots refused before
any lookup, no read at import or construction, fresh reads, no value in repr/errors/logs, and preparation through the
existing stand-in release with no stand-in request, including the endpoint mismatch, the registered default
composition and the explicitly emptied-registry no-effects branch.
