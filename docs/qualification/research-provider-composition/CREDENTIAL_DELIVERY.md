# Research credential delivery

Status: LOCAL composition (#58 RESEARCH-CREDENTIAL-BOOTSTRAP-L4-20261016). It approves no release, delivers no
variable to any host process and makes no provider claim.

## Decision

The builder stated that the existing research credentials are in the process environment. That settles the credential
delivery `REQUIRED_DECISION` in `CONTRACT.md` section 12 and replaces step 2 of the caller handoff in
`docs/implementation/RESEARCH_ENVIRONMENT_CREDENTIALS.md` (keep the refusal when no source is passed).

## What the bootstrap does

`released_runtime_bootstrap.server_research_runtime(settings, *, credentials=None)` is the one function the API
(`main.create_app`) and the worker (`investigation_jobs.main`) already call. Neither caller changed.

1. The existing registry gates run first and read nothing: a definition filed under another id or two approved
   definitions refuse `operating_release_invalid`; an empty registry, a stand-in, or a definition whose SHA-256 is not
   the approved one returns `None`. No credential source is constructed on any of these paths.
2. For one approved ACTUAL definition, an injected `credentials` object is used as given. Without one, the bootstrap
   constructs the accepted `EnvironmentCredentialSource`. A broken injected object is never replaced by the
   environment source.
3. Composition reads no slot and opens no socket. The API and the worker each compose a runtime with the same release
   SHA-256 and the same transport selection (`StdlibHttpTransport`, `NansenHttpFactory()`).
4. A job reads a slot only at `prepare_history` / `prepare_nansen`. A missing or blank allowed slot, an unknown slot
   (refused before any environment lookup) or a failing injected source all refuse
   `operating_release_credential_unavailable` there, before any transport is built or provider is reached.

No dotenv or file loading, bulk environment read, export, cache, store or new setting was added.

## Still empty, still separate

- `RELEASE_DEFINITIONS` and `operating_release.APPROVED_RELEASES` stay empty. The default server composes nothing.
- An actual release needs its reviewed definition and approved SHA-256 in a later change.
- Giving the API and worker processes only the three selected variables under an actual operator is a later operation.

## Proof

Pure, `--noconftest`, run in an empty process environment with synthetic definitions and fake sentinel values:
`apps/api/tests/test_environment_runtime_bootstrap.py` (registry refusals, default and explicit sources, allowed,
missing, blank and unknown slots, no import or composition read, no socket), the accepted reader tests in
`apps/api/tests/test_environment_credentials.py`, and the bootstrap tests in
`apps/api/tests/test_nansen_runtime_mount.py`.
