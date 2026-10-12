# Nansen research local package

Task `NANSEN-REPORT-L4-20261012-01` v1, issue #51 scoped LOCAL slice. The isolated local package is `apps/api/src/edge_os_api/nansen_research/` with tests in `apps/api/tests/nansen_research/`.

## Stage

Local preparation only. No provider request, credential read, account, quota, wallet, signature, broadcast, payment, deployment or publication is run. This package is not actual Nansen qualification and not bounty readiness. Full D02 and the bounty stay OPEN.

## Proposed verdicts

- Local package: `LOCAL_TESTED`.
- Actual provider run: `NOT_RUN`.
- Lane-2 application mount, save and reopen: `NOT_STARTED` (outside this lease).

## Documents

- `INTERFACE_FREEZE.md` - the frozen request/evidence/report interface and the resource/fault matrix.
- `SOURCE_EVIDENCE.md` - the current first-party endpoint facts and the accepted D01 sources.
- `INTEGRATION_NOTE.md` - how lane 2 mounts the package into the authenticated investigation path.
- `LIVE_TEST_PACKET.md` - the bounded actual Nansen qualification packet. No live authority.

## What the package does

1. Builds a versioned typed `NansenRequest` from the exact question, token, network, observation window, filters, label tier and finite limits.
2. Calls an injected read-only transport through a `NansenClient`. The client enforces the operation allowlist, finite request/page/byte/credit/deadline limits, error sanitization and no retry.
3. Extracts typed evidence that keeps raw numbers as exact text, keeps nulls null and keeps missing or incomplete flow buckets visible.
4. Builds a deterministic, source-linked `NansenReport` with supported findings, coverage, unknowns and the preserved unsupported questions.

## What a pass shows

- Input, client, extraction, report and JSON round-trip semantics behave as the frozen interface describes.
- Every finding is bound to the exact evidence and source hashes.

## What a pass does not show

- No actual Nansen response, account access or data-use right.
- No durable application storage, save or reopen. A serialized round-trip here is not durable storage.
- No concentration percentage, no qualified token unit, no hourly price, no all-holder flow and no trading edge.

## Mandatory honest limits

1. Concentration percentages stay unresolved without a documented total supply and qualified matching units.
2. `token_amount`, `ownership_percentage` and flow quantities keep raw text; no scaling is applied.
3. A null value stays null and never becomes zero.
4. A partial page is never normalized to the total population.
5. A fractional or negative count is not an event count and is never summed.
6. The selected flow category is not all holders.

## Authority

The builder owns product decisions, live values and any paid access. This package grants no provider, account, payment, wallet, deployment or publication authority. A factory default performs no I/O; the only transport in this package replays authored offline responses.
