# Release host preparation (P40/P41 expansion; proposal and preparation only)

Task RELEASE-HOST-PREP-L4-20261012-01, issues edge-os-app/edge-os#47 and #48. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12 in the `release-host-prep-worker` worktree, branch `ticket/release-host-preparation`.

Status: **documentation and preparation only.** No host, account, plan, region, secret or domain was selected. Nothing was purchased, configured or deployed. No provider was called. No recording, submission, participant contact or repository change happened. Every live, hosted, provider and participant result is `NOT_RUN`.

This package extends the accepted [P41 release preparation](../release-preparation/README.md) and [P40 release journey](../release-journey/README.md) for the expanded release (real-data research, Nansen, and P27 recurring operation). It does not overwrite them.

## Documents

| Document | Purpose |
|---|---|
| [HOST_DECISION_PACKET.md](HOST_DECISION_PACKET.md) | Render candidate reconciled against Fly/Vercel; smallest topology proposal; first-party costs; exact unmet decision gates H1–H12 |
| [HOST_QUALIFICATION_RUNBOOK.md](HOST_QUALIFICATION_RUNBOOK.md) | Future ordered host checks: fresh checkout, secrets, migrate/start, real auth, jobs/isolation, persistence/restore, live action/revocation, judge access; fail-closed rules |
| [RELEASE_EVIDENCE_MAP.md](RELEASE_EVIDENCE_MAP.md) | Every RC01–20 / PU01–08 / RG01–06 / IC01–08 / AUT01–08 plus P40/P41 and selected sponsor criteria, with owner, source, existing evidence and missing proof |
| [DEMO_AND_JUDGE_ACCESS_PLAN.md](DEMO_AND_JUDGE_ACCESS_PLAN.md) | Evidence-led demo flow, pitch, interactive/participant checks, judge-access inventory, deadlines |
| [INTEGRATION_NOTE.md](INTEGRATION_NOTE.md) | How lane 2, lane 3 and the controller consume this preparation after their outputs qualify |

## Scope and exclusions

Owned new path: `docs/qualification/release-host-preparation/` only. This package changes no application code, shared document, contract, migration, script, lockfile or verifier entry. It installs nothing and runs no application recipe. Source inspection, public first-party documentation and read-only research supply the facts.

## Exact base and source limits

- Accepted code facts come from inspection of base `3e7ff8bd` (class: inspected source). Where an earlier document states a different state, this package records the correction (for example, Render internal database TLS **is** supported with `sslmode=require`; PostgreSQL 18 **is** a supported Render major version).
- Host prices and capabilities come from first-party pages fetched 2026-10-12. A price or capability not stated by a first-party page stays `UNKNOWN`.
- Criterion text comes from the ticket, checklist and issue snapshots. Dated public bounty criteria are retained with their dates and marked unchecked where the current detailed card was inaccessible.

## Current versus dated evidence

- The accepted local integration `3e7ff8bd` is newer than published main `3292bb784cf00a22dd4b9e943c0df585e5ef41e5`. Publication, its reviews and a manual approval are a separate step (RC19).
- The earlier `HOSTING_AND_ACCESS_ASSESSMENT.md` inspected integration `c119e409` and records several `MISSING_CONNECTION` findings. The accepted base now mounts the financial routers and ships migrations `0008`–`0010`. Those earlier findings are stale for the current base and are reconciled here against accepted code.
- The public-runtime Stage 2 records remain valid LOCAL evidence; they do not prove hosted or actual operation.

## Remaining required decisions

| Decision | Owner | Where recorded |
|---|---|---|
| Region, service sizes, workspace tier | builder | HOST_DECISION_PACKET §4 |
| Provider-only egress (H1) | builder | HOST_DECISION_PACKET §6 |
| Qualified isolated Hermes job runtime (H2) | lane 1 output + builder | HOST_DECISION_PACKET §6 |
| Quota/rate/freeze values before the first owner | builder | HOST_QUALIFICATION_RUNBOOK Stage 2 |
| Provider-side money limits (H8) | builder | HOST_DECISION_PACKET §6 |
| Real Privy app, model, data, wallet and live packets | builder | RELEASE_EVIDENCE_MAP |
| Exact release claim and repository visibility | builder | DEMO_AND_JUDGE_ACCESS_PLAN §8 |

## How this preparation is consumed

1. **Lane 2** mounts the accepted provider and P27 outputs into the connected journey under its own lease. It uses the criterion ownership and missing-proof columns in `RELEASE_EVIDENCE_MAP.md` to know which evidence each criterion still needs.
2. **Lane 3** supplies the P21/P20 enforcement and (later) P31 health outputs. This package records their criteria (RC05, RC11, IC08, AUT03, AUT06) as owned there.
3. **The controller** reports each affected edited path that this preparation touched on the qualification side and integrates accepted outputs serially. The controller picks the provider/host packet boundaries from `HOST_DECISION_PACKET.md` §6 and `HOST_QUALIFICATION_RUNBOOK.md` Stage 0.
4. **The lane-4 worker** returns this committed candidate to gate `%8` and supports controller acceptance and safe release.

## Data retention and support (conditional)

Any future data-retention, deletion or support promise stays **conditional on implemented behavior and provider obligations**. The current proposal is in [RETENTION_DELETION_SUPPORT.md](../public-runtime/RETENTION_DELETION_SUPPORT.md). Do not publish a retention or deletion guarantee before the implementation and the provider obligations match it (PU07).

## Authority limits

The builder owns product decisions, account access, deployment, recording and submission. This package grants no spending, signing, funding, broadcast, deployment, publication, tracker or recording authority. Full issues #47, #48 and umbrella #58 stay OPEN.
