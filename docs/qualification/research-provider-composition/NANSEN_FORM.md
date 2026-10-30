# Release-aware Nansen report form

Status: candidate for NANSEN-RELEASE-FORM-L4-20261016. Web client only. This change activates no release, sends no
provider request and reads no credential. The server stays the final authority for every new request.

## Behavior

The form reads `listing.operating_release` from `GET /v1/research/requests/{id}/nansen-reports` through
`apps/web/lib/nansen-release-request.ts`. That parser accepts `unknown` and returns one of three states. The global
`api.ts` types stay unchanged.

| Listing | Form | New request |
|---|---|---|
| No `operating_release` key (legacy server) | Authored form and authored label, as before | Authored body, as before |
| Readable release | Fixed request shown read-only: token, window, records, holder/flow query, request, page, byte, credit and time bounds | The whole fixed request, sent as listed with the existing owner keys |
| `null`, malformed, unknown evidence class, kind/class conflict, missing or out-of-range field | Reason shown; editable fields hidden | Blocked. No fallback to the authored request |
| `available: false` | Unavailable notice | Blocked |

- The parser checks the exact field sets and the `NansenReportBody` ranges in `core/request_schemas.py`. It never
  fills a missing field with a default and never widens a limit.
- The request keys come from the existing `keysFor` session store. Under a release, the fingerprint also holds the
  release name and SHA-256, so a changed release gets new keys. An unconfirmed request keeps its keys and tells the user
  to check saved reports. The form never resubmits by itself.
- A listing that returns after a newer refresh or an intake change is ignored. The form posts the release of the latest
  listing for the current intake only. Until that listing is read, a new request is disabled.

## Labels

Labels come from metadata, not from configuration effects.

- Before a report: an `ACTUAL` release says the server is *configured* for actual Nansen collection and that nothing
  is collected until the user saves and reserves a report. A `STAND_IN` release says its responses are not provider
  data.
- A saved report uses its own `content.evidence_class` and shows `content.notice` unchanged.
  - `PROVIDER_ACTUAL`: "Data from Nansen" with links to `https://www.nansen.ai` and `https://docs.nansen.ai`. It says
    that holder records are a partial returned list, not full ownership, and that flows do not show buying or profit.
  - `RELEASE_STAND_IN_RESPONSE` and `AUTHORED_FIXTURE`: not provider data, with no Nansen attribution.
  - Any other class: unrecognized; do not treat as provider data.
- The saved view shows settlement (unknown credits stay "reserved amount held"), partial coverage, source-reference
  hash counts and the hash check. An empty hash map does not count as verified.

## Limits

- The test records are SYNTHETIC fixtures in the server's response shapes. They are not provider data and not sponsor
  proof.
- This note grants no display, retention or licence permission for Nansen data. That qualification stays separate.
- Checks run for this candidate are listed in the worker's terminal report.
