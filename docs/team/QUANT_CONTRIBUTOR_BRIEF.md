# Quant contributor brief

Updated 10 October 2026. Independent contributor PR development is authorized for the numerical portion of P14 described below. Other tasks remain proposed.

## What we are building

Edge OS helps onchain traders turn a market question into saved research, exact strategy rules, a historical replay and bounded execution. We are focusing on meme-token traders and, later, LP traders.

The work draws on Hanguk's QT101–QT401 material and Robot James' approach to mechanisms and falsifiable claims. The repository's accepted contracts control implementation. You do not need the private courses to contribute. If a task needs a lesson that is not explained in the repository, I will supply a permitted extract or an independently worked example.

Research can finish with no supported strategy. A replay is not proof of a profitable edge, and a research finding cannot grant trading permission.

I am handling the hackathon release candidate. Your track is quantitative backend work outside that release. You do not need to help with its execution qualification, deployment, wallet setup, videos or submission.

## Start with P14

[P14: additions, partial exits and competing-position replay](https://github.com/edge-os-app/edge-os/issues/30) is your authorized first task, limited to numerical PR development outside the release. [P13's accepted result](https://github.com/edge-os-app/edge-os/issues/25#issuecomment-6095690713) supplies the working replay baseline.

The current profile supports one position and full exits. It explicitly rejects additions, partial exits and multiple positions. Develop the proposed extension profile, independent calculations, implementation and tests in one PR. Keep the accepted P12/P13 default and rejection behavior intact. Removing rejection checks does not establish extension semantics.

Your PR should contain:

- A short proposed profile for additions, partial exits, position identity, shared simulated capital and event ordering. Name the supported subset and any undecided behavior.
- Independently calculated event traces for buy → add → partial exit → add again → full exit. Show cash, inventory, allocated basis, fees, realized result and remaining basis at each event.
- A case where two positions compete for insufficient capital. Propose a stable ordering and explicit denial behavior. Do not resize a rejected request silently.
- Missing-mark, missing-cost, unavailable-fill and unsold-inventory cases. Keep unknown values distinct from zero.
- A regression plan that preserves the accepted P12/P13 profile and existing saved runs. Identify any contract or record version that needs an approved extension.

Use small labelled synthetic examples first. Calculate expected values separately from the proposed implementation, so the tests do not repeat the same mistake as the code. Retain the source and units for each assumption.

You can begin this bounded PR without a separate profile approval or preliminary proposal return. Create your own task branch from the latest main in your clone or isolated checkout. Record the actual base SHA, branch and checkout in the PR. Opening an early draft PR is optional.

Owned scope is pure numerical replay/calculation helpers in `apps/api/src/edge_os_api/replay/`, focused replay tests including `apps/api/tests/test_spot_replay.py` and new descriptive replay-test files, and new P14 extension-profile/qualification documents. Preserve existing public routes, shared record registration, schemas, contracts, `conftest`, migrations, lockfiles, web code and the shared verifier until an explicit later lease. Put new contract/profile proposals in owned new documents. Preserve adopted P02/P12 meaning and saved-run compatibility.

Calculation choices in the PR remain proposals until reviewed and adopted. This assignment permits developing and testing them in isolation. It does not adopt a runtime profile or enable the extension through the existing application. Shared API, database and UI wiring requires a separate coordinated lease. P05's shared lease remains reserved, and the release does not depend on this PR. Numerical-only acceptance leaves P14 open until saved API/UI results and all full-ticket checks pass.

If an essential requirement is missing or conflicts with an accepted contract, pause the affected part and report the exact conflict. Continue unrelated safe work. This assignment grants no portfolio optimizer, new signals, live financial effects or work on P42, P10 or LP tickets.

## Other tasks you can own later

| Task | Contribution | Start condition |
|---|---|---|
| [P42: statistical-method qualification](https://github.com/edge-os-app/edge-os/issues/28) | Freeze and test the selected dependent bootstrap/Holm profile. Cover false-support behavior, interval coverage, sparse/unstable inputs, the full comparison family and protected holdout failures. | P09 is accepted. Remaining method choices, numerical tolerances and compute limits need approval. Choose this if you are comfortable with dependence-aware inference and simulation-based qualification. |
| [P10: source-backed Hermes research](https://github.com/edge-os-app/edge-os/issues/27) | Connect adopted questions and deterministic evaluations to saved source evidence, contrary findings and useful unresolved reports. | P05 must pass its applicable acceptance. Tool contracts and actual model/provider runs need separate approval. Local preparation does not complete the actual-runtime ticket. |
| LP model work leading to [P37](https://github.com/edge-os-app/edge-os/issues/32), [P38](https://github.com/edge-os-app/edge-os/issues/34) and [P39](https://github.com/edge-os-app/edge-os/issues/37) | Develop the pool-specific inventory, fee and cost model, then research, rule compilation and simulation. | First resolve the missing P36 model/data choices. P37 also depends on P10; P38 depends on P37; P39 depends on P38. |

P36's [existing qualification package](../qualification/p36/README.md) is unresolved preparation. Its constant-product example is unadopted arithmetic, not a selected venue or supported LP model. A follow-up assignment is needed for the remaining choices. Do not start the full LP implementation because issue12 is closed.

We should start with one task. P14 gives us a concrete way to check numerical reasoning, tests and backend integration. P42 is a separate statistical problem, not a requirement for every research result. If statistical qualification is your stronger area, tell me and we can make its profile preparation the first task instead.

## Read these first

Read [AGENTS.md](../../AGENTS.md), the [README](../../README.md), the [team handoff](../CONTROLLER_HANDOFF.md) and your assigned issue. Then read the [release cut](../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) so you can see the work I am keeping in the release queue. You are not responsible for those release portions.

For P14, read:

1. [The adopted P12 contract](../contracts/p12/README.md), especially scope, ordering, cost assumptions, accounting and repeatability.
2. [The independent worked cases](../qualification/p12/WORKED_CASES.md), especially WC-02 through WC-05. Partial-exit arithmetic there does not mean runtime support.
3. [The P13 runtime profile](../implementation/SPOT_REPLAY_RUNTIME_PROFILE.md) for what actually works and what remains synthetic.
4. [The replay implementation](../../apps/api/src/edge_os_api/replay/simulator.py) and [its tests](../../apps/api/tests/test_spot_replay.py). Inspect these after calculating your reference cases.
5. [The implementation reference map](../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md), P12–P14 row, for required inputs and course-source limits.

For P42, add [STAT-Q01 and ST-01–10](../EDGE_OS_RESEARCH_CONTRACTS.md#stat-q01-method-profile-and-qualification) and the issue's full scope. The selected candidate is not qualified. Repeatable seeded output alone cannot establish statistical validity. Preserve the unopened holdout and every declared comparison, including failures.

Read only the relevant sections of the [full specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md). Use [contributor reference rules](../agents/domain.md#shared-documents-and-private-evidence) when a required input is missing. Public references and independent calculations should be sufficient for the first task.

## Working together

Work in your own clone or isolated checkout on one task branch. For the authorized P14 numerical PR, use the scope above and [contributor setup](../agents/contributor-workflow.md#start-from-your-clone). For other assignments, obtain the controller's starting SHA, allowed paths, checks and return route before source edits. Do not work in the release integration checkout or push to main.

Keep numerical code in the existing responsibility-based domains. Use names that describe the calculation, not ticket names such as p14.py. Preserve exact decimal, timing, missing-data and source-identity conventions unless an approved new profile changes them. Use the locked toolchain and repository commands.

Shared migrations, schemas, routers, model registration, UI wiring and lockfiles need an explicit lease. P05 currently reserves shared interpreter/API/storage/UI work. The controller owns the merge queue; a ready numerical module does not authorize shared wiring.

If you find a blocker in accepted upstream code, reproduce it and report the affected commit, expected/actual behavior and proposed fix. Continue independent work. The controller can grant you the repair paths after checking ownership. Do not silently patch another task or reinterpret its old PASS as approval of your fix.

Each implementation return needs the exact candidate commit, checks and results, original review reports, worked examples, source identities and remaining limits. The project keeps two independent internal reviews and a separate gate before checked local integration. The controller arranges the gate; you do not need the builder's tmux setup. Submit a pull request for shared contribution. Only the builder merges to main.

Coding agents are optional. If you use them, select task-relevant skills from the available catalog and read their instructions before use. Numerical research needs quantitative-research and testing guidance. Python implementation adds codebase-design, python-pro, python-code-style, python-anti-patterns and applicable error-handling/backend skills. Use Karpathy and Ponytail Lite for the smallest complete change. Report actual skill use, instruction sources and any permitted adaptations. Generic skill thresholds, daily-market assumptions and sample counts do not override the accepted five-minute, units or qualification profile. Agents still need explicit ownership and independent reviews.

No real-provider collection, paid compute, model research call, wallet operation or trading is approved by this brief. Keep fixtures labelled and credentials out of the repository. The full issue stays open until all its criteria pass, even when an isolated preparation stage is accepted.

## Your first reply

You can begin the authorized P14 numerical PR now. Include your profile outline, independently calculated traces, code and tests together. List exact missing inputs or unresolved choices in the PR. If P42 is a better fit, propose that alternative for its own assignment before starting it.

## Workflow and prompt templates

Use the [portable contributor workflow](../agents/contributor-workflow.md) for clone setup, skill requirements and the contribution sequence. It links the canonical [worker packet](../agents/controller-workflow.md#worker-activation-packet), [internal-review packet](../agents/templates/internal-review.md) and [gate packet](../agents/controller-workflow.md#gate-activation-packet). Native agents and Smux lanes are optional ways to run that process; you do not need the builder's machine, pane names or subscriptions.

For P14, record this dated numerical assignment, your actual base SHA, branch/checkout, owned scope, required checks and PR/report return. Record an available review route before review begins. The two original independent candidate-bound reviews and separate gate remain required before integration or main merge. They do not prevent opening a PR. Install selected skills in your own agent environment and report missing skills before relying on them. This P14 assignment supersedes contrary preliminary-proposal waits. It grants no provider or financial permission.
