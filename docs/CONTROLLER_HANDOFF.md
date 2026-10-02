# Edge OS team handoff

Last updated: 2026-10-02, Africa/Kinshasa.

This file records team-facing state. The builder's detailed controller history, retired Funnel ledger, courses and research archives are private and are not required inputs for a teammate's clone.

## Current state

- Selected product: Edge OS, edge research and strategy generation for onchain meme traders and liquidity providers.
- Governing method: [Hackathon Winning Compass](../playbooks/HACKATHON_WINNING_COMPASS.md), applied through the [project workflow](EDGE_OS_COMPASS_WORKFLOW.md).
- Current Compass stage: Phase 3, frame the product.
- [Product design](superpowers/specs/2026-09-29-edge-os-hackathon-design.md) and [research contracts](EDGE_OS_RESEARCH_CONTRACTS.md) remain drafts for builder review. The [scoped probe plan](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md) records the individual experiment approvals; these do not approve the complete design.
- Probe A, research/compiler/rejection: `IN_PROGRESS`. Part 1A recovery passed 81/81 mechanics checks. Part 1B offline repair passed 25/25 authored-fixture checks after the rejected live attempt. Live 1B recovery is pending approval; historical checkpoint 2 has not run. Checkpoint 1, complete Probe A and the Compass prototype gate remain unpassed.
- Execution evidence: [Probe A result report](prototypes/EDGE_OS_PROBE_A_RESULT.md). Consult the report for results and limitations, and the plan for approvals. Preserve the original rejections.
- Probe B, delegated Monad–Kuru execution: `NOT_STARTED`.
- Result-state interaction prototype: not started and separately scoped.
- Nansen qualification: `NOT_STARTED`; no paid or authenticated investigation is approved.
- Production implementation: not started under the Compass workflow.
- Team size: three.
- First investigation: bounded short-horizon spot momentum or reversal in a declared set of Monad meme-token markets.
- LP compilation and simulation remain the second product proof. Live LP execution needs a separately verified adapter.
- Optional token/publication/funding extensions are unapproved and outside the first probes.
- A prior Assensus test supports a reusable delegated-wallet pattern, not verified Monad–Kuru behavior. Offline execution, policy denial, restart recovery and signer removal remain to be proved for this path.

## Ownership and document authority

The builder owns product decisions, the whole backend and every prototype, including both probes and any UI interaction prototype. One teammate implements the frontend. The other implements the gated tokenization extension using accepted behavior, interfaces and fixtures. Detailed ownership is in [the workflow](EDGE_OS_COMPASS_WORKFLOW.md#9-team-ownership).

Tokenization ownership does not approve token rights, fees, governance, funding or activation. Those decisions and the extension's verification gate remain separate. Teammates implement accepted tickets; they do not own prototyping.

The specification, research contracts, probe plan, project workflow and `docs/agents/` configuration in this repository are the shared sources of truth. Workspace copies are redirects. Approved product behavior belongs in the specification; this handoff summarizes status without introducing new requirements.

Private source material is marked `BUILDER-ONLY REFERENCE`. Follow the [reference rules](agents/domain.md#shared-documents-and-private-evidence). The builder must supply any verified extract or fixture needed by a ticket. A missing source is not permission to invent behavior or bypass validation.

## Implementation workflow

Use [Matt's project workflow](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md) and the [GitHub tracker configuration](agents/issue-tracker.md).

Implementation starts after the relevant behavior and production scope are accepted. Draft tickets are not ready implementation work. Work on task branches, submit PRs, return the required checks and independent review evidence, and leave acceptance and merging to the builder.

The builder selected a manual merge gate rather than required GitHub approvals or branch protection. This does not waive verification, independent reviews or financial authorization.

## Contest constraints

The [hackathon brief](research/00_HACKATHON_BRIEF.md) records detailed rules, sources, conflicts and unknowns. Its authenticated rubric and timeline control the local contest summary.

- Registration deadline: 2026-10-06 23:59 UTC, 2026-10-07 00:59 Africa/Kinshasa.
- Submission deadline: 2026-10-14 03:59 UTC, 04:59 Africa/Kinshasa.
- Proposed internal cutoff: 2026-10-13 23:59 Africa/Kinshasa.
- Rubric: Technical Execution 20%; Design & Craft 20%; Originality & Track Insight 15%; Founder & Market Readiness 25%; Traction & Path Forward 20%.
- Standard artifacts: logo or graphic; public GitHub repository; live application on Monad mainnet or testnet; technical demo up to three minutes; pitch video up to two minutes; written description; track and bounty selections; any selected bounty's extra proof.
- Unpublished eligibility, maximum team size, KYC, tax, prize-payment, reuse and intellectual-property terms remain unresolved. Entry was accepted conditionally; this is not organizer confirmation of those terms.

## Next authorized action

Review the retained offline repair evidence and the pending live 1B recovery proposal with the builder. The proposal allows four additional calls, five cumulatively, with prior usage retained and the USD 0.10 working cap / USD 0.30 maximum. It is not yet approved. No retries, repair calls or model escalation are included.

Do not rerun completed 1A work merely to restart the workflow. If live 1B passes, review checkpoint 1, then qualify and approve the exact market and historical dataset before checkpoint 2. Probe B remains separately scoped and unstarted. Code, paid access, wallet changes and transactions require their applicable approvals; this status update grants none.

Return separate findings and limitations. Use focused planning or a small Wayfinder map only for unresolved dependent decisions. Accept the production design and build brief before publishing ready implementation tickets.

No prototype gate, production design, optional extension or financial action was approved by this document-ownership update.

## Setup record

The repository's local agent instructions, Matt configuration and shared project documents are present. GitHub CLI access was checked on 2026-10-02 using account `degencodebeast`; repository access succeeds and Issues are enabled.

The remote label check found `wontfix`, but the other four configured triage labels are missing. Their creation is a separate authorized setup step before tickets use them.

The builder authorized publication of the 13 shared Markdown documents on 2026-10-02. This is a one-time documentation-only initial commit and push to `main`, establishing the empty repository's baseline. Subsequent implementation still uses task branches, PRs and builder acceptance. Repository visibility is unchanged; the repository is currently private and must satisfy the public-repository submission requirement before submission.

This publication creates no issues or labels and changes no repository settings. The draft design, probe approvals, service costs, financial authority and current Compass stage remain unchanged. Verify the published commit on GitHub before reporting publication complete.
