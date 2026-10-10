# Submission checklist

Task OC-P41-PREP-20261010-01, issue #48. Prepared 2026-10-10.

Scope: preparation only. This checklist names roles, dates, artifacts and current asset status. It invents no result, URL, approval or user feedback.

## 1. Deadlines

The authenticated timeline `S29` controls the local plan. The public page `S1` disagrees on two entries; the brief records that `S29` wins.

| Event | Authenticated value (S29) | Kinshasa, UTC+1 | Public page (S1) |
|---|---|---|---|
| Registration and team formation | 2026-10-06 23:59 UTC | 2026-10-07 00:59 | Closed |
| Submission form opened | 2026-09-22 03:59 UTC | 2026-09-22 04:59 | Not shown |
| Submission deadline | 2026-10-14 03:59 UTC | 2026-10-14 04:59 | 13 Oct, 11:59 PM ET |
| Judging | 2026-10-14 to 2026-11-03 23:59 UTC | 2026-10-14 04:59 to 2026-11-04 00:59 | 14 to 27 Oct |
| Winners announced | 2026-11-04 17:00 UTC | 2026-11-04 18:00 | 3 Nov |
| Internal submission cutoff | Builder decision | 2026-10-13 23:59 | Not applicable |

Source: [hackathon brief](../../research/00_HACKATHON_BRIEF.md) section 4. Public pages rechecked 2026-10-10.

## 2. Accountable roles and decision checkpoints

| Work | Accountable owner | Checkpoint, Kinshasa |
|---|---|---|
| Hosting and access assessment, evidence and script preparation | Controller prepares; builder supplies account access and approves deployment and cost | Feasibility 11 October 18:00; claim and access freeze 12 October 18:00 |
| Actual route, network and provider preparation | Controller prepares evidence; builder approves consequential choices | 11 October 18:00 |
| Participant sessions | Builder recruits and conducts; controller prepares tasks and collates evidence | Start with existing Research by 11 October; collate by 12 October 18:00 |
| Pitch and demo recording, final submission | Builder; controller prepares the checklist and evidence links | Rehearse by 12 October; internal cutoff 13 October 23:59 |

Source: [release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) section "Owners and decision checkpoints".

## 3. Required artifacts

Status values: EXISTS, PARTIAL, MISSING, NOT DONE, UNSELECTED.

| Artifact | Requirement | Status | Owner | Evidence or gap |
|---|---|---|---|---|
| Working product | Live product on Monad mainnet or testnet | MISSING | Builder | No deployment exists; hosting is UNSELECTED |
| Project logo or graphic | JPG, JPEG, PNG or WEBP, at most 3 MB | MISSING | Builder or controller prepares | No image asset exists in the repository |
| Public GitHub repository | Fully accessible to `metropolis@hackathon.monad.xyz` | NOT DONE | Builder | The repository is currently private; visibility is unchanged |
| Technical demo video | At most 3 minutes on YouTube, Loom or Vimeo; shows the live product, not slides | MISSING | Builder records; controller prepares the script | Script drafted in [DEMO_AND_PITCH_SCRIPTS.md](DEMO_AND_PITCH_SCRIPTS.md); the live product does not exist |
| Pitch video | At most 2 minutes; team, problem and reason to build | MISSING | Builder records; controller prepares the script | Script drafted in [DEMO_AND_PITCH_SCRIPTS.md](DEMO_AND_PITCH_SCRIPTS.md) |
| Live product link and access instructions | Live URL plus access instructions and any judge test credentials | MISSING | Builder | Depends on deployment and judge access |
| Written description and project details | Short description in the project workspace | NOT PREPARED | Builder | The repository README describes the product; the submission text is not written |
| Event-period work evidence | Evidence that judges can verify the work built during the event | PARTIAL | Controller | Dated commits and the accepted release record exist; the exact submission evidence set is not assembled |
| Primary track and bounties | One primary track and any selected sponsor bounties | UNSELECTED | Builder | The product maps to Onchain Finance and Trading; no track or bounty is selected |
| Optional product advertisement | At most 30 seconds | NOT DONE | Builder | Not scored |

Sources: [hackathon brief](../../research/00_HACKATHON_BRIEF.md) sections 10 and 11; [release cut](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md).

## 4. Asset inventory

| Asset class | Found | State |
|---|---|---|
| Logo or graphic | None | MISSING; must be produced or approved by the builder |
| Product screenshots | None tracked | MISSING; a demo needs fresh screens |
| Video recordings | None | MISSING |
| Design export | `docs/design/p43/r9/` HTML sources | EXISTS as a design milestone, not a logo or a submission graphic |
| Fonts | `apps/web/public/fonts/` (Caprasimo, Figtree) | EXISTS |
| Environment examples | `apps/api/.env.example`, `apps/web/.env.example` (names only) | EXISTS |

The search covered the worktree for image files outside dependency and build directories. No image matched.

## 5. Judge access

A judge needs a live product on Monad mainnet or testnet, access instructions, and any test credentials. None of these exist yet.

Prerequisites before judge access:

1. A deployed product with a working live URL.
2. A judge-ready owner or test account with bounded, disclosed access.
3. A public repository that `metropolis@hackathon.monad.xyz` can read.
4. Clear instructions that separate synthetic fixtures from live account state.

## 6. Unmet conditions

- No host, account or cost is selected. The builder decides.
- No live Monad deployment exists. The release cut lists the exact live qualification still open.
- No logo exists.
- No video exists.
- The repository stays private until the builder changes it.
- The exact release claim is not frozen. The cut sets a claim-freeze checkpoint on 12 October.

## 7. Source freshness and access limits

- Public pages were rechecked 2026-10-10 through Exa and a direct fetch of `https://www.monad.xyz/developers/hackathons/metropolis` and `https://hackathon.monad.xyz/`.
- The authenticated timeline, catalog and project workspace (`S28` to `S36`) returned an access boundary during the original check. Their detailed rules rest on the brief snapshot, not a fresh authenticated read.
- The judged rubric, the exact bounty requirements and the submission form fields need a fresh authenticated check before submission.
- Eligibility, KYC, tax, prize-payment and intellectual-property terms remain unresolved in the brief.

This checklist changes no repository visibility, no hosting choice and no submission.
