# The registered actual Nansen release

Status: LOCAL source registration (#58 NANSEN-RUNTIME-RELEASE-L4-20261018). This change registers one code-owned ACTUAL
release in the existing default bootstrap. It approves no provider call, reads no credential at composition, and makes
no public-rights determination. See [CONTRACT.md](CONTRACT.md) and [CREDENTIAL_DELIVERY.md](CREDENTIAL_DELIVERY.md).

## The one registered release

The registration adds one definition to `core/research/released_runtime_bootstrap.py` (`RELEASE_DEFINITIONS`) and its
exact SHA-256 to `core/research/operating_release.py` (`APPROVED_RELEASES`). The definition is Nansen-only: `history` is
`null`.

| Field | Value |
|---|---|
| `release_id` | `actual-moe-nansen-demo-20261018/1` |
| `kind` | `ACTUAL` |
| `release_sha256` | `dce1e05ffdecf72eedaf340e55fad0e2a4271c1ea7860d15aed17fd2c1b1d743` (canonical content, 817 bytes) |
| endpoint | `https://api.nansen.ai` |
| credential slot | `NANSEN_API_KEY` |
| token | `MOE`, `0xd8e004acba279417c04c0633cb5a21ceca207777` |
| window | `2026-10-17T12:00:00Z` to `2026-10-18T12:00:00Z` |
| operations | `holders`, `flows` (one first page each) |
| limits | max requests 2, max pages 1, max bytes 2000000, max credits `6`, per page 100 |
| time bounds | deadline 300 s, compute 300 s |
| client bounds | connect 10 s, request 16384 bytes, response 1000000 bytes |

The canonical content is reproduced above so a teammate needs no private file. It equals the accepted private
`RELEASE.json` `release_content` byte for byte, and `release_sha256` recomputes to the literal SHA-256 above.

## Authority provenance

The builder owns this release under the settled demo/configuration authority. Accepted private records carry the
authority; this repository doc carries only the sanitized result and their digests.

| Record | SHA-256 |
|---|---|
| Controller acceptance `ROOT_ACCEPTANCE5.json` | `b8ecce0e9ac21487ea1867d84a594fc50fd397026cb1820e5db08b1d63a03734` |
| Independent gate verdict `VERDICT3.md` (PASS 3/3) | `9c8ab6619959aff159ed53e81e2455f68b13359600d9950d3f263b3b3eeb7062` |
| Frozen proposal `worker/v2/RELEASE.json` | `2d1ec8e8db94f66f015d1f1a1aa81154b664f8809beb525bb6b4dd178a42dc19` |
| Proposal `worker/v2/ACTIVATION.md` | `e8892267e438028a99a3e23803d61368b5984229348c93882dee77d678f03225` |
| Correction `worker/v2/CORRECTION_ADDENDUM1.md` | `584666a9f3a47de6b067f4ea70dd10cfedf2c71dab65e5cad5d01fbe72323975` |
| Root disposition `nan-accept5.md` | `4ffcb7c7fde5cf7193d760e157165efdf990c220b09bd22c4125b4041cc31ef7` |

The controller acceptance records `status: ACCEPTED_PRIVATE_CONFIGURATION`, `actual_provider_operation: NOT_GRANTED`
and `public_rights: UNRESOLVED`. The correction addendum controls the earlier guard, accounting and UI-key wording.

## The existing entry points (unchanged)

No launcher, reader, provider client, registry framework, UI field or settings mode is added. The registered release
uses the existing path:

- Composition: `released_runtime_bootstrap.server_research_runtime`, called by the API (`main.create_app`) and the
  worker (`research/investigation_jobs.py` `main`). Both processes compose the same release and the same SHA-256.
- Registry checks: a definition filed under another id, a second approved definition, or a SHA-256 that is not the
  approved one refuses or composes nothing. No setting, environment value, file or request can add a definition.
- Credential: the accepted `EnvironmentCredentialSource` reads the one allowed slot `NANSEN_API_KEY` only at job
  preparation. A missing or blank slot refuses before any provider attempt.
- UI: the Nansen report form under the application route `/app`. It reads `listing.operating_release` from
  `GET /v1/research/requests/{intake_id}/nansen-reports` through `apps/web/lib/nansen-release-request.ts`, posts the
  fixed request to `POST /v1/research/requests/{intake_id}/nansen-reports` with the existing generated
  `ui-<UUID>` owner keys, and reopens a saved report at `GET /v1/research/nansen-reports/{report_id}`. The release
  SHA-256 is visible at `GET /v1/research/history-sources` (`operating_release.sha256`).

## Limits and unproved scope

- The run sends at most holders page 1 and flows page 1. It is **not** a complete, all-pages report and must not claim
  complete coverage.
- Settlement follows the requests actually sent and the replies actually received. Standard 5+1 is one authored case,
  not a guarantee: `provider_requests` and `nansen_credits` are `KNOWN` only when nothing was lost and every received
  call reported a valid deducted amount. Otherwise the credit reservation stays `UNKNOWN` liability, held until
  reconciled.
- `holders` is a collection-time snapshot. The window is a chosen finished 24-hour descriptive window, not observed
  history, coverage or point-in-time evidence.
- Account plan, available credits, MOE coverage, actual charges, save, restart and reopen remain unproved until an
  authorized operator run.
- Public holder display and retention remain unresolved. This registration grants no display, retention or licence
  permission for Nansen data.
- This registration does not run a job and does not grant provider, credential, account or spending authority. An
  operator grant within the existing shared USD 2 remains necessary.

## Earlier milestone statements

`CONTRACT.md`, `PAYLOAD_BINDING.md` and the `README.md` milestone section describe the registry as empty. Those are
historical milestone records and do not describe the current default. `CREDENTIAL_DELIVERY.md` and
`docs/implementation/RESEARCH_ENVIRONMENT_CREDENTIALS.md` carry the current state.
