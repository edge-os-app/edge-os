# Edge OS

An edge-generation and strategy research system for onchain traders and liquidity providers.

A trading idea can sound convincing while leaving the important questions unanswered. What causes the opportunity? When should a position open or close? What would disprove the thesis? Does the result survive realistic costs, or only look attractive in a backtest?

We are building Edge OS to investigate those questions before an idea reaches capital.

Users can start with a concrete thesis, a loose intuition, or a bounded research request without an existing thesis. Research agents investigate the proposed mechanism, retain supporting and contrary evidence, and make missing assumptions visible. The system records attempted variants and translates sufficiently defined hypotheses into explicit, inspectable strategy rules.

The intended workflow is:

```text
Thesis, intuition or bounded research request
→ mechanism hypothesis and evidence
→ explicit strategy rules
→ false-edge checks and execution simulation
→ reject, unresolved or ready for paper testing
→ separately authorized, bounded Monad execution
```

An investigation can finish with no surviving strategy. The user should still receive the evidence, rejection reasons and unanswered questions.

## First build

The first prototype focuses on short-horizon momentum and reversal research in a declared set of Monad meme-token markets. It will test whether Edge OS can preserve strategy meaning, expose missing assumptions and reject a deliberately invalid result that initially looks attractive.

The planned execution path uses Kuru and a revocable, policy-scoped Privy wallet mandate. Models propose actions. Deterministic checks and wallet policies determine whether an action is permitted. Orders, fills, denied actions and transaction receipts remain inspectable.

Liquidity-provider research is the second product domain. Its initial scope is compilation and simulation, including fees, inventory exposure, impermanent loss and rebalancing costs. Live LP execution requires a separately verified adapter.

## Current status

Edge OS is in design and prototype preparation. The research/compiler/rejection probe and the Monad–Kuru delegated-execution probe have not yet run.

Research results, profitable strategies and autonomous execution are not established capabilities. A passing test or completed transaction does not prove a trading edge.

## Project documents

The specification, contracts, scoped probe plan and project workflow in this repository are the shared sources of truth. Their approval status remains explicit. Workspace paths outside this checkout redirect to these documents rather than maintaining another specification.

- [Current state and next action](docs/CONTROLLER_HANDOFF.md).
- [Edge OS Compass workflow](docs/EDGE_OS_COMPASS_WORKFLOW.md).
- [Product design, draft for builder review](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md).
- [Research contracts, draft for builder review](docs/EDGE_OS_RESEARCH_CONTRACTS.md).
- [Scoped probe plan, draft for builder review](docs/prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md).
- [Hackathon brief](docs/research/00_HACKATHON_BRIEF.md).
- [Hackathon Winning Compass](playbooks/HACKATHON_WINNING_COMPASS.md).
- [Matt Pocock project workflow](playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md).

## Team and agent setup

Track assigned work in [GitHub Issues](https://github.com/edge-os-app/edge-os/issues). Read [AGENTS.md](AGENTS.md) before an agent task. Tracker, label and domain conventions are under [docs/agents/](docs/agents/).

The builder owns product decisions and prototyping. Teammates implement accepted tickets on task branches and submit pull requests for builder acceptance. Only the builder merges to `main` by team agreement. The builder selected this manual gate instead of requiring GitHub-enforced approvals or branch protection. Required checks and implementation review still apply.

Skills require installation in each contributor's agent environment. These documentation files do not install skills or create remote labels.

Research sources marked `BUILDER-ONLY REFERENCE` remain in the builder's private workspace. Teammates do not need that workspace. The builder must supply required verified extracts and fixtures with each task. See [reference and document rules](docs/agents/domain.md#shared-documents-and-private-evidence).

Verified installation, build and test commands will be added when the runnable application and its tooling exist.
