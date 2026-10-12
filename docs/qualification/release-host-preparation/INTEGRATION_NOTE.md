# Integration note (lane 2 / lane 3 / controller handoff)

Task RELEASE-HOST-PREP-L4-20261012-01. Base `3e7ff8bd4498a1b7ddf6aa7a167951328d5c48fa`, tree `31e71d47b63cf14686470d46e5469de59565d3f9`. Prepared 2026-10-12.

This note explains how the [release-host-preparation package](README.md) is consumed after lane 2's provider/P27 outputs and lane 3's P31 output qualify. It commits nothing and grants no authority.

## What this package is

Six Markdown documents under `docs/qualification/release-host-preparation/` only:

- `HOST_DECISION_PACKET.md` — host reconciliation, cost separation, unmet gates H1–H12;
- `HOST_QUALIFICATION_RUNBOOK.md` — future ordered host checks;
- `RELEASE_EVIDENCE_MAP.md` — RC/PU/RG/IC/AUT + P40/P41 + sponsor trace;
- `DEMO_AND_JUDGE_ACCESS_PLAN.md` — demo, checks, judge inventory, deadlines;
- `README.md` — index and current status;
- `INTEGRATION_NOTE.md` — this handoff.

It changes no application, contract, migration, script or verifier file. The controller integrates it as documentation only.

## Exact base and ancestry

- Assigned branch `ticket/release-host-preparation`; base `3e7ff8bd`; tree `31e71d47`.
- The candidate adds only new files under the owned path. `git diff --check` must pass and no other path may change.
- The controller verifies ancestry against `3e7ff8bd` before acceptance.

## What each owner supplies next

### Lane 2 (Claude, #58 connected journey and P27 LOCAL)

- Mounts the accepted provider boundaries (P07 Envio/QuickNode, Nansen core mount) and the P27 scheduler under its own lease.
- Uses `RELEASE_EVIDENCE_MAP.md` §1 (RC), §3 (RG), §4 (IC), §5 (AUT) to know the missing proof for each criterion.
- Supplies the connected **hosted** evidence that `HOST_QUALIFICATION_RUNBOOK.md` Stages 4–7 require.
- Keeps the **Nansen core mount, durable save/reopen and actual qualification** as open work (still MISSING at this base).

### Lane 3 (P21/P20 enforcement; then P31)

- Supplies the independent restriction/exposure evidence for RC05 and IC08.
- Its independent-enforcement preparation is accepted LOCAL and integrated at `f84ef415`, with documents under `docs/qualification/independent-enforcement/` (boundary-only feasibility; actual enforcement `NOT_RUN`). Lane 2 consumes those documents for the #58 and P20 packets.
- Supplies the P20/P21 qualification that IC05/AUT03 consume.
- After its enforcement preparation is accepted, integrated and safely released, supplies the P31 matching direct/chat health projection that AUT06 and P27 require.

### Lane 1 (Hermes job support and P05 safeguards)

- Supplies the qualified isolated Hermes job runtime for gate H2 and RC01/PU04.
- Until it is accepted, this package records real-model/research capability as unavailable.

### Lane 4 (this task)

- Returns the committed candidate and both original GLM assessments to gate `%8`.
- Supports controller acceptance and the final checkpoint/safe release.

### Controller

- Verifies the exact candidate, both original PASS assessments and the owned-path inventory.
- Integrates the documentation serially. No application behavior changes.
- Opens the host/provider packet boundaries from `HOST_DECISION_PACKET.md` §6 and `HOST_QUALIFICATION_RUNBOOK.md` Stage 0 for the builder's decisions.

## Blocking order

1. **H1 (provider-only egress)** blocks any release claim that enables a real provider. It needs a builder risk/architecture decision before a host is chosen for that claim.
2. **H2 (isolated Hermes job runtime)** blocks real-model interpretation (RC01) and the hosted research capability (PU04).
3. **Lane 2 P27 LOCAL** blocks the recurring-operation criteria (AUT01–AUT08) and their hosted checks.
4. **Lane 3 P31** blocks AUT06's matching health evidence.
5. **Builder packets** (auth, model, data, wallet, live, recurring) block Stages 4–7.
6. **Publication** (RC19) blocks any claim that main contains this release.

None of these blocks the documentation integration of this package.

## Current versus dated limits to preserve

- Keep the earlier preparation documents' history intact. The earlier `HOSTING_AND_ACCESS_ASSESSMENT.md` was prepared against base `5689e1d6` with `NOT RUN`/`UNTESTED` statuses; the `c119e409` integration and the `MISSING_CONNECTION` class come from the workspace planning audit. Their `P05 unwired` and `not implemented` statements are stale for base `3e7ff8bd`; this package corrects them without rewriting the originals.
- Record which statements are first-party facts (observed 2026-10-12) and which are inspected code at base `3e7ff8bd`.
- Keep future data-retention and support promises conditional on implemented behavior and provider obligations (PU07).

## Authority

The builder owns product decisions, account access, deployment, recording and submission. This note and package grant no spending, signing, funding, broadcast, deployment, publication, tracker or recording authority. Full issues #47, #48 and umbrella #58 stay OPEN.
