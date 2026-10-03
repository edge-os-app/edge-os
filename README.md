# Edge OS

An edge-generation and alpha research system for onchain traders and liquidity providers.

Edge OS generates market hypotheses, investigates their mechanisms, and turns sufficiently supported ideas into inspectable strategy rules. It preserves the evidence and rejects unsupported results before they reach capital.

A trading idea can sound convincing while leaving the important questions unanswered. What causes the opportunity? When should a position open or close? What would disprove the thesis? Does the result survive realistic costs, or only look attractive in a backtest?

We are building Edge OS to connect research, strategy construction, testing, delegated execution and monitoring. The wider vision includes publishing strategies and optional token-based distribution or agent funding. These are planned capabilities, not a description of a finished product.

The goal is to take a trading idea through research, explicit strategy rules, historical backtesting and risk checks. Where historical data is insufficient, the strategy needs further observation or paper testing. Once it meets the required evidence checks, the user can deploy it as an agent that monitors markets and carries out permitted actions while they are offline. The user controls its limits and can revoke its authority. Passing compilation or a backtest alone does not qualify a strategy for deployment or prove future profitability.

## Who it is for

Onchain traders and strategy creators can investigate an observation without building their own data pipeline, research notebooks, simulator and trading runtime. Liquidity providers can investigate whether pool fees compensate for inventory exposure and operating costs.

Users can start with:

- A concrete thesis, such as a claim that a specified market condition predicts a later price response.
- A loose intuition, such as noticing that a token keeps moving after a strong move.
- No thesis, but a bounded request to investigate selected markets or pools using approved data and a finite search budget.

The agent asks for missing meaning or proposes an investigation for approval. It cannot silently choose the user's thresholds, sizing or trading permissions. The product is intended to help both experienced and learning traders; it does not promise to make either profitable.

## The research-to-strategy path

The planned workflow is:

```text
Thesis, intuition or bounded research request
→ clarification or an approved research budget
→ mechanism hypothesis and supporting/contrary evidence
→ quantitative effect tests and inspectable strategy rules
→ historical backtesting or replay where the data supports it, with realistic execution costs
→ false-edge and robustness checks, plus paper or forward testing where needed
→ rejected, unresolved or eligible for the next evidence stage
→ user-approved deployment as a bounded strategy agent
→ ongoing monitoring, permitted Monad execution and inspectable receipts
```

Research starts with a mechanism question. Who produces the relevant flow? What incentive or constraint explains it? Why might an opportunity remain after competition? What costs, liquidity limits and capacity restrict capture? Which evidence would disprove the explanation?

A plausible explanation remains a hypothesis. An unexplained statistical association can also be investigated, with its mechanism marked unknown. Agents must retain contrary evidence instead of inventing a causal story.

Each investigation declares its markets, features, horizons, candidate limits, data periods and resource budget. The research ledger records attempted, rejected and abandoned variants, including negative results. Planned validation checks address future-information leakage, selection across variants, holdout results, unstable parameters and unrealistic execution assumptions. Historical gaps can require forward observation rather than a fabricated backtest.

An investigation can finish with no surviving strategy. The user should still receive the evidence, rejection reasons and unanswered questions. A successful transaction or attractive chart cannot establish an edge.

### How the compiler fits

The agent proposes structured meaning. The deterministic compiler checks supported functions, types, units, parameter ranges, timing and risk fields. An accepted strategy becomes a versioned `StrategySpec` that the existing evaluator can run. The user also receives a plain-English interpretation of its rules.

The research hypothesis and its evidence live in an `EdgeSpec` and `ResearchEvidencePackage`. The `ResearchLedger` retains the search history. A `ValidationDecision` records which evidence gates passed, failed or remain unresolved.

The compiler does not execute arbitrary model-generated Python or smart contracts. Missing information produces clarification. Unsupported strategy forms remain unsupported. Compilation alone grants neither validation nor execution authority.

## Delegated agents and observable execution

The planned deployment path lets a user approve a revocable mandate for an exact strategy revision, wallet, venue and set of limits. A persistent worker monitors that strategy while the user is offline. Routine permitted actions do not require another signature.

Models can propose intents. Deterministic checks enforce evidence, freshness, exposure and risk limits. A restricted Privy signer provides an independent wallet-policy boundary. The execution service holds its authorization credential; models do not receive it. The initial venue adapter targets Kuru on Monad.

Durable records retain pending transactions, open orders, capital reservations and stop conditions. After an interruption, the worker must reconcile the original action before submitting another. A changed strategy or expanded authority needs renewed approval. Revocation stops new permitted submissions; existing orders require explicit reconciliation and handling.

Decision records connect evidence and strategy versions to mandates, risk checks, denied intents, transactions and resulting venue state. Order acceptance, partial fill, fill, cancellation and failure remain distinct. Receipts prove recorded execution outcomes, not profitability.

Hermes is the current interpretation-probe runtime and a candidate research investigator. Jev is an optional structured-assessment layer. Neither can override validation or authorize money. The persistent worker owns scheduling and recovery; agent memory does not replace those records.

The planned data path uses Envio for indexed events and history, QuickNode for current state and reconciliation, and Kuru records for venue behavior. Nansen wallet labels and X evidence are conditional research inputs. Each dataset needs coverage, timing and provenance checks. If an essential input is unavailable, its hypothesis remains unresolved.

## First build

The first prototype focuses on short-horizon momentum and reversal research in a declared set of Monad meme-token markets. It will test whether Edge OS can preserve strategy meaning, expose missing assumptions and reject a deliberately invalid result that initially looks attractive.

The planned execution path uses Kuru and a revocable, policy-scoped Privy wallet mandate. Models propose actions. Deterministic checks and wallet policies determine whether an action is permitted. Orders, fills, denied actions and transaction receipts remain inspectable.

Liquidity-provider research is the second product domain. Its initial scope is compilation and simulation, including fees, inventory exposure, impermanent loss and rebalancing costs. It needs an explicit comparison, such as holding the same initial assets. Gross fee revenue alone does not establish a benefit. Live LP execution requires a separately verified adapter and authority.

## Publication, tokens and the wider vision

A strategy should remain useful when its creator keeps it private and no associated token exists. After the applicable evidence gates, the creator could keep running it privately, publish an inspectable record or select an optional token model.

Publication would expose a chosen immutable strategy revision, evidence coverage, limitations, risk rules and operating state. Historical, fixture, paper and live results must remain distinguishable. Publication is opt-in and must protect private data and credentials.

The raw vision contains three possible token models. They are alternatives, not three required launches:

| Model | Intended purpose | Open decisions |
|---|---|---|
| Agent-community token | Identity, community and distribution around an agent or strategy. | Holder utility and the functional connection to the strategy. |
| Agent-financing token | A verified fee route could help pay for inference, data and operating costs. | Actual fee source, collection, recipients, budgets and funding failure behavior. |
| Strategy-associated token | Connect a token to an exact strategy revision, its evidence and observable operation. | Eligibility, holder rights, issuance, initial liquidity and revision changes. |

A public page could show the associated strategy, actual evidence status, operating funding, risk limits and decision receipts. Performance figures require measured records with periods, costs and limitations. A token must not turn an unresolved strategy into a validated one.

Association or operating funding does not grant ownership of trading assets, redemption rights, profit entitlement or wallet authority. Those rights are not selected. Token holders cannot directly expand a strategy's risk limits or execution mandate. Operating revenue does not automatically become trading capital.

The token extension can be built after the agreed core works, including during the hackathon if its own decisions, tests, funding approvals and remaining time permit it. No token model, fee split or issuance terms are settled by this README. The [product design](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#conditional-publication-token-and-funding-extensions) records the conditional extension requirements. They remain proposed and require separate implementation and activation approval.

Longer-term possibilities include strategy forks and exports, licensing, marketplaces, broader hypothesis search, additional venues and portfolio-level research. A fork needs its own identity, evidence and mandate. These possibilities are outside the current core. Public pooled capital, profit distribution and autonomous treasuries need separate designs and approvals. Copy trading is outside the selected product direction.

## Current status

Edge OS is in design and scoped prototyping. Probe A has started:

- Part 1A recovery passed the deterministic compiler, timing, leakage and accounting checks: 81/81 checks passed.
- Part 1B passed all five fresh live GPT-6.1 Sol cases under contract v6: a concrete thesis, loose intuition, bounded no-thesis request, unsupported request and clarification follow-up. The concrete thesis and clarified rules compiled, saved and reloaded without changing their tested meaning. Unclear requests produced questions; missing evidence remained unresolved; unsupported requests were not replaced with another strategy.
- The final offline suites passed 35 interpretation checks and 19 boundary checks. Earlier model failures and contract defects remain in the report. Both the model choice and corrections to our instructions/checker contributed to the recovery.
- Checkpoint 1 passes for this bounded interpretation, compiler and known-invalid-input experiment. This is not proof of reliable interpretation of every arbitrary strategy.
- The historical investigation has not run. Complete Probe A and the Compass prototype gate remain unpassed. Probe B, delegated Monad–Kuru execution, has not started.

See the [probe result report](docs/prototypes/EDGE_OS_PROBE_A_RESULT.md) for the latest live result, retained failures and limitations. The next step is to qualify one exact market and its historical data before approving the bounded research investigation. No further inference is authorized by this README.

Research results, profitable strategies and autonomous execution are not established capabilities. A passing test or completed transaction does not prove a trading edge.

## Project documents

The specification, contracts, scoped probe plan and project workflow in this repository are the shared sources of truth. This README explains the product; the specification controls detailed behavior. Their approval status remains explicit.

- [Current state and next action](docs/CONTROLLER_HANDOFF.md).
- [Edge OS Compass workflow](docs/EDGE_OS_COMPASS_WORKFLOW.md).
- [Product design, draft for builder review](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md).
- [Research contracts, draft for builder review](docs/EDGE_OS_RESEARCH_CONTRACTS.md).
- [Scoped probe plan and approval record](docs/prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md).
- [Probe findings and limitations](docs/prototypes/EDGE_OS_PROBE_A_RESULT.md).
- [Hackathon brief](docs/research/00_HACKATHON_BRIEF.md).
- [Hackathon Winning Compass](playbooks/HACKATHON_WINNING_COMPASS.md).
- [Matt Pocock project workflow](playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md).

## Team and agent setup

Track assigned work in [GitHub Issues](https://github.com/edge-os-app/edge-os/issues). Read [AGENTS.md](AGENTS.md) before an agent task. Tracker, label and domain conventions are under [docs/agents/](docs/agents/).

The builder owns product decisions, all prototyping and the whole backend. One teammate implements the frontend; the other implements the gated tokenization extension after its behavior and interfaces are accepted. The [team ownership section](docs/EDGE_OS_COMPASS_WORKFLOW.md#9-team-ownership) records the boundaries. Assigning an owner does not approve an extension's economics or activation.

Teammates implement accepted tickets on task branches and submit pull requests for builder acceptance. Only the builder merges to `main` by team agreement. The builder selected this manual gate instead of requiring GitHub-enforced approvals or branch protection. Required checks and implementation review still apply.

Skills require installation in each contributor's agent environment. These documentation files do not install skills or create remote labels.

For supporting evidence and required task inputs, follow the [contributor reference rules](docs/agents/domain.md#shared-documents-and-private-evidence).

Verified installation, build and test commands will be added when the runnable application and its tooling exist.
