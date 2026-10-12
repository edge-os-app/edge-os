# Nansen actual qualification packet

Proposal only. No live authority. This packet prepares a bounded actual Nansen run. It runs nothing now. The builder must authorize the account, the token, the request limit and the credit ceiling before any call.

## Goal

Produce a real, source-linked holder-only inventory and flow-coverage report for one Monad token, with explicit coverage and unknowns. Prove that the local package works against a real response without inventing concentration, amounts or edge.

## Filled source-backed fields

| Field | Value |
|---|---|
| Provider | Nansen Token God Mode |
| Endpoint origin | `https://api.nansen.ai` |
| Operations | `POST /api/v1/tgm/holders`, `POST /api/v1/tgm/flows` |
| Network | `monad` |
| Chain ID | `143` |
| Token | `MOE`, `0xd8e004acba279417c04c0633cb5a21ceca207777` (from the D01 profile) |
| Holder label tier | `all_holders`, `premium_labels=false` |
| Holder order | `token_amount` descending |
| Holder filter | default (no `value_usd` filter) plus a linked `min: 0` variant |
| Flow label | `top_100_holders` |
| Observation window | `2026-10-06T09:44:14Z` through `2026-10-07T09:44:14Z` (inclusive cutoff) |
| Profile | `nansen-descriptive-reviewed/1` |
| Conventions | `d01-conventions/1` |

## Unresolved fields to set before a run

| Field | State |
|---|---|
| Account plan and exact per-call cost | `UNSET` |
| Numeric request limit | `UNSET` |
| Credit ceiling | `UNSET` |
| Collection time and clock | `UNSET` |
| Retention window and rights decision | `UNSET` |
| Whether the run is historical qualification or prospective collection | `UNSET` |

## Hard limits for the proposed run

- Basic labels only. `premium_labels` stays `false`. No x402 and no MPP payment.
- At most two operations per token per run. No retry, no upgrade, no alternate paid route.
- The request and credit caps are approved numbers, not defaults from this document.
- A `401`, `402`, `403`, `429` or provider error stops the run and is recorded. It is not retried.
- Raw responses are not stored in shared candidates. The evidence package keeps hashes, request identities and typed observations only.

## Exact commands

Focused suite (offline, no provider):

```sh
cd apps/api
uv run --frozen pytest tests/nansen_research -v
```

D01 authored controls (offline):

```sh
python3 docs/qualification/nansen/check_d01_profile.py
```

An actual run is a later, separately authorized script that injects a real transport. That script does not exist in this package, keeps the credential outside source control, and records the provider request ids and credit headers.

## Evidence to retain

- Request bodies and their canonical hashes.
- Provider `X-Request-Id`, `X-Nansen-Credits-Cost`, `X-Nansen-Credits-Used` and `X-Nansen-Credits-Remaining`.
- Response content hashes and collection times.
- The typed evidence package and the deterministic report with its hash.
- Any coverage gap: missing or incomplete buckets, partial pages, warnings.
- The data-use rights decision for the retained output.

## Completion criteria

The run completes when a real response produces a report whose findings match the accepted D01 limits, with every missing or unresolved item explicit. A provider failure completes when it is recorded with its stable code and the partial result. Neither outcome is bounty readiness. Full D02 and the bounty stay OPEN until the application mount, the approved actual run, a working demo and public integration documentation exist.

## Rights assumption

Derived explanations and source attribution are in scope for D02. Raw export, training and premium uses stay outside scope. The exact account-specific rights remain unresolved until the builder decides them.
