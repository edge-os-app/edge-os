# Edge OS

An edge-generation and alpha research system for onchain traders and liquidity providers.

Current build, 10 October 2026: saved Research, descriptive comparisons, spot replay and account views work with labelled fixtures. Live trading is not available. See [current status](#current-status) for implemented scope and qualification limits.

The approved [hackathon release cut](docs/planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) targets a connected Research-to-controlled-Kuru-action demonstration. Its live portion is not yet qualified. LP expansion and general ongoing trading remain outside this submission subset.

Edge OS generates market hypotheses, investigates their mechanisms, and turns supported, sufficiently clear trading instructions into inspectable strategy rules. It preserves the evidence, shows uncertainty and separates research findings from permission to trade.

A trading idea can sound convincing while leaving the important questions unanswered. What causes the opportunity? When should a position open or close? What would disprove the thesis? Does the result survive realistic costs, or only look attractive in a backtest?

We are building Edge OS to connect research, strategy construction, testing, delegated execution and monitoring. The wider vision includes publishing strategies and optional token-based distribution or agent funding. These are planned capabilities, not a description of a finished product.

Users can investigate an idea, test it against market history where the data permits, observe it without trading money, or authorize live trading. A live trial is optional. Users can start ongoing live operation directly or continue after a trial, without compulsory graduation, favorable backtests or paper trading. Bad or missing historical results remain visible. All live operation needs clear supported rules, verified execution and a user-approved mandate. An authorized agent can monitor markets and carry out permitted actions while the user is offline. The user controls its limits and can revoke its authority. Compilation, a backtest or a few successful trades cannot prove future profitability.

## Who it is for

Onchain traders and strategy creators can investigate an observation without building their own data pipeline, research notebooks, simulator and trading runtime. Liquidity providers can investigate whether pool fees compensate for inventory exposure and operating costs.

Users can start with:

- A concrete thesis, such as a claim that a specified market condition predicts a later price response.
- A loose intuition, such as noticing that a token keeps moving after a strong move.
- No thesis, but a bounded request to investigate selected markets or pools using approved data and a finite search budget.

The agent asks for missing meaning or proposes an investigation for approval. It cannot silently choose the user's thresholds, sizing or trading permissions. The product is intended to help both experienced and learning traders; it does not promise to make either profitable.

A research request could also be: "These meme coins ran. Who launched them, what happened to their other launches, and is there a pattern?" The planned research mode includes sourced comparisons, participant histories and competing explanations. It can finish with useful findings without a strategy or backtest. Creator histories, wallet PnL and cross-launch comparisons need additional qualified tools and data; they are not capabilities already demonstrated by our prototype.

## The research-to-strategy path

The planned workflow is:

```text
Thesis, intuition or bounded research request
→ clarification or an approved research budget
→ investigation, supporting/contrary evidence and a saved research result
→ optional strategy construction and claim-specific tests
→ historical testing where feasible, forward observation or user-selected live trading
→ separate execution qualification and user-approved mandate if capital is involved
→ bounded agent operation, inspectable receipts and recorded learning
```

Research starts with a mechanism question. Who produces the relevant flow? What incentive or constraint explains it? Why might an opportunity remain after competition? What costs, liquidity limits and capacity restrict capture? Which evidence would disprove the explanation?

A plausible explanation remains a hypothesis. An unexplained statistical association can also be investigated, with its mechanism marked unknown. Agents must retain contrary evidence instead of inventing a causal story.

Each investigation declares its markets, features, horizons, candidate limits, data periods and resource budget. The research ledger records attempted, rejected and abandoned variants, including negative results. Planned validation checks address future-information leakage, selection across variants, holdout results, unstable parameters and unrealistic execution assumptions. Historical gaps can require forward observation rather than a fabricated backtest.

An investigation can finish with no surviving strategy. The user should still receive the evidence, rejection reasons and unanswered questions. A successful transaction or attractive chart cannot establish an edge.

"Live trading" is one workflow. A user can choose a trial with a learning objective and stopping point, or ongoing trading within approved permissions. After a trial, the interface offers "Continue trading", "Review and adjust limits", "Revise strategy" and "Pause trading". Continuing does not reset spending allowances or losses, increase authority or turn limited observations into a validated edge. New approval is needed for expired or changed permissions, not a purpose-label change alone. Allocated capital can be lost in full, and an exit may be unavailable. See the [live-trading contract](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#live-trading-optional-trials-and-forward-learning) and [user journey](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-live-user-journey-and-display). This behavior is documented, not implemented or authorized for a particular trade.

### How the compiler fits

The agent proposes structured meaning. The deterministic compiler checks supported functions, types, units, parameter ranges, timing and risk fields. An accepted strategy becomes a versioned `StrategySpec` that the existing evaluator can run. The user also receives a plain-English interpretation of its rules.

The research hypothesis and its evidence live in an `EdgeSpec` and `ResearchEvidencePackage`. The `ResearchLedger` retains the search history. A `ValidationDecision` records which evidence gates passed, failed or remain unresolved.

The compiler does not execute arbitrary model-generated Python or smart contracts. Missing information produces clarification. Unsupported strategy forms remain unsupported. Compilation alone grants neither validation nor execution authority.

## Delegated agents and observable execution

The planned deployment path lets a user approve a revocable mandate for an exact strategy revision, wallet, venue and set of limits. A persistent worker monitors that strategy while the user is offline. Routine permitted actions do not require another signature.

The accepted design gives each trading agent its own user-owned wallet, funded separately. Creating or funding it must not start trading. Agent A must not use Agent B's money or sell its tokens; each agent can hold multiple positions within its own limits. The account overview combines records, not spending authority. Deposits must not reset allowances, losses or stops, and removing agent access must leave owner access intact. The record contracts and account views are implemented; application wallet creation, funding and live operation are not qualified end to end. A separate bounded Privy test supplied one-owner signing and removal evidence. See [agent wallets and funding](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding) and [P16's retained limits](docs/qualification/p16/README.md).

Models can propose intents. Deterministic checks enforce operational eligibility and approved permissions, preserve evidence status, and check freshness, exposure and risk limits. A restricted Privy signer provides an independent wallet-policy boundary. The execution service holds its authorization credential; models do not receive it. The initial venue adapter targets Kuru on Monad.

The interface keeps agent status, strategy evidence and trading permissions separate. An agent can be "Running" while its evidence says "Limited live observations; edge remains unproven". A trial or ongoing purpose never grants unlimited trading authority.

Durable records retain pending swaps, holdings, capital reservations and stop conditions. After an interruption, the worker must reconcile the original action before submitting another. A changed strategy or expanded authority needs renewed approval. Revocation stops new submissions; it cannot undo a broadcast transaction or remove remaining holdings.

Decision records connect evidence and strategy versions to mandates, risk checks, denied intents, transactions and resulting venue state. Queued, submitted, unknown, confirmed and reverted outcomes remain distinct. The initial Kuru Flow adapter targets fixed-input swaps, not resting orders. Receipts prove recorded execution outcomes, not profitability.

Hermes is the current interpretation-probe runtime and a candidate research investigator. Jev is an optional structured-assessment layer. Neither can override validation or authorize money. The persistent worker owns scheduling and recovery; agent memory does not replace those records.

The planned data path uses Envio for indexed events and history, QuickNode for current state and reconciliation, and Kuru records for venue behavior. Nansen wallet labels and X evidence are conditional research inputs. Each dataset needs coverage, timing and provenance checks. If an essential input is unavailable, its hypothesis remains unresolved.

## Skills and connected tools

The planned MVP includes an Add-ons section for each agent. Users can enable skills and connect tools from a small approved catalog without writing configuration or running installation commands.

Initial skills guide market investigation and price-and-volume analysis. Connected tools provide qualified research data/calculations and read-only access to the user's account records. Each entry explains what it can access, its version and any provider costs. Users can enable, disable or disconnect it for a selected agent.

Skills do not add unimplemented indicators or grant permission to trade. Connections and credentials must remain isolated between users. Custom uploads, arbitrary MCP URLs and executable plugins are later extensions. This catalog is approved product direction, not a working integration. See the [agent add-ons contract](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-add-ons-catalog).

OpenBB is an optional research-component candidate. Its analysis packages could calculate selected indicators on our qualified data, and its MCP interface could expose selected tools. We have not installed or qualified it, and it does not replace our Envio/QuickNode data path. Edge OS's intended difference is the connected investigation, preserved strategy meaning and bounded agent-operation workflow. AI chat and indicators alone are shared capabilities. See the [sourced comparison and reuse limits](docs/research/OPENBB_RESEARCH_REUSE_AND_PRODUCT_DIFFERENCES_2026-10-04.md).

GeckoTerminal is an optional chart and market-data candidate. Start with a "View market chart" link from a report or position; embedding and read-only agent tools can follow if a specific task needs them. Current market charts must stay separate from saved research data, simulated balances and actual account results. No integration is enabled, and the Envio/QuickNode data path and Kuru execution direction remain unchanged. See the [terminal comparison and integration limits](docs/research/MARKET_TERMINALS_AND_GECKOTERMINAL_INTEGRATION_2026-10-05.md).

## First build

The completed research prototype tested bounded short-horizon momentum/reversal rules and a reconstructed MOE/WMON investigation. It preserved the tested meaning and contrary evidence, returned no supported candidate, and rejected deliberately invalid future inputs. Its evidence does not establish production support for arbitrary strategies.

The [first-release build brief](docs/EDGE_OS_BUILD_BRIEF.md) describes the spot-first direction. Accepted tickets have implemented the request-to-saved-record path, a bounded synthetic spot replay and persisted account views. The wider brief is not evidence that real data, model inference or execution have passed qualification.

The planned execution path uses Kuru Flow and a revocable, policy-scoped Privy wallet mandate. Models propose actions. Deterministic checks and wallet policies determine whether an action is permitted. Swap requests, denied actions, confirmed asset changes and transaction receipts remain inspectable.

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

The repository contains a runnable Next.js frontend, FastAPI backend and PostgreSQL persistence. The implemented local path can:

- Save a request, ask clarifying questions, review compiled price/volume rules and reopen immutable revisions after an API restart.
- Review and explicitly adopt a fixture-labelled investigation declaration before outcome access. Preserve its exact settings, origins and prior versions.
- Run an adopted descriptive comparison on authored synthetic inputs, retaining variants, exclusions, missing references, contrary results and saved reports. Statistical support remains `UNRESOLVED`.
- Save and replay the adopted one-position spot subset with next-scheduled-bar fills, explicit costs, immutable configuration identities, cash/holdings and available or unavailable metrics. This is a real implemented simulator driven by synthetic fixtures, not qualified market history or a profitable strategy.
- Display persisted Agents, Positions and Funds records with immutable permission histories and separate deposits/withdrawals. Version agent context through adoption, correction, disable and clear. These are authored account records, not live wallet balances or trading workers.

### Integrated work by ticket

The accepted implementation/decision outputs below are in this codebase. Acceptance refers to each bounded output, including a permitted `UNRESOLVED` qualification result; it does not assert that every GitHub issue is closed or that the product is deployed.

| Ticket | Integrated output | Boundary |
|---|---|---|
| P01 | Application/authentication/storage profile | Production deployment and real-auth checks remain separate |
| P02 | Strict first-slice record contracts and lineage checks | No model or trading authority |
| P03 | Saved Research API, database and Next.js path | Fixture sign-in and interpretation verification |
| P04 | Pinned Hermes local runtime qualification | Fake-provider tests passed; live model/hosting unresolved |
| P06 | Deterministic compiler/evaluator and review/save/reopen path | Supported price/volume subset only |
| P08 | Investigation review, adoption, immutable save and reopen | Fixture-labelled declarations; no real study by adoption alone |
| P09 | Descriptive comparison and saved-report runtime | Authored synthetic inputs; no statistical or profitability claim |
| P12 | Adopted spot-replay accounting/evidence contract | One position, fixed positive quote buys and full exits |
| P13 | Persisted spot-replay API and UI | Implements P12's bounded synthetic subset; no live fills |
| P15 | Wallet, mandate and account record contracts | Does not implement live funding or execution |
| P19 | Persisted account views and versioned agent context | Not live wallet state or Hermes context retrieval |
| P36 | LP model/data requirements and reference case | Overall `UNRESOLVED`; no adopted LP model or simulator |
| NANSEN-D01 | Bounded descriptive-input assessment | Limited sampled access; not qualified wallet PnL or signals |

Also integrated: P07's offline history/lineage checker, P16's bounded one-owner signing/removal evidence, the P43 R9 design export and controller delivery/Stop safeguards. Full P07 real-history and P16 owner-linked creation, lost-response, restart and actual-backend cross-user qualification remain incomplete. P43 is a design milestone, not complete design-parity or unfamiliar-user validation.

P05's Hermes interpretation adapter is staged outside this published tree and is not wired into Research. Its persistence, shared wiring, reviews and live-model qualification remain open. Real data collection, Kuru swaps, funded agent operation, withdrawals, production deployment, live LP execution and optional token/add-on extensions are not available end to end.

The earlier accepted [Probe A](docs/prototypes/EDGE_OS_PROBE_A_RESULT.md) preserved bounded interpretation and contrary evidence, and returned `UNRESOLVED` with no supported MOE/WMON candidate. Keep that evidence separate from the current fixture-backed application. Compilation, simulations, passing tests and sign-only provider results do not prove a trading edge.

### Verification snapshot

On 10 October 2026, code at `8ad71c4` passed all 377 API tests against isolated PostgreSQL. The same application tree passed 118 web tests, typechecking, P02/P06/P15 contract checks, 73 P07 checks, production build and the full 18-step desktop/390px browser/API/SQL/restart/cleanup path. The backend reorganization received two independent internal PASS assessments and a separate gate PASS before integration.

One unchanged desktop saved-heading focus assertion failed in the first mapped run and passed on an unchanged repeat. Its cause remains unexplained. Safari/Firefox, real devices, full screen-reader use, unfamiliar-user comprehension and deployed load remain unqualified. Verification used fixture authentication and synthetic records, not real market execution.

## Run and test locally

The mapped verifier starts a fresh isolated PostgreSQL database, migrates it, builds and starts the API/web app, drives the saved Research/comparison/replay/account paths, inspects actual rows, restarts the API and cleans up only its own resources. It uses fixture interpretation and sign-in. See [startup and configuration](docs/implementation/P03_FIRST_RESEARCH_PATH.md) and the [verification recipe](.agents/skills/verify-edge-os/SKILL.md) for the full steps and evidence locations. Keep credentials out of source control; example configuration is in `apps/api/.env.example` and `apps/web/.env.example`.

```bash
(cd apps/api && uv sync --frozen && uv run --frozen pytest)
(cd apps/web && npm ci && npm run typecheck && npm test)
(cd tests/p03 && npm ci && npx playwright install chromium)
(cd apps/api && uv run --frozen python ../../scripts/p03/verify_run.py)   # fresh isolated instance, full path, evidence, cleanup
```

The commands need Docker, Python 3.14, `uv`, and Node 24.

## Code layout

```text
apps/web/                  Next.js application
apps/api/src/edge_os_api/
  main.py                  application factory and route composition
  core/                    authentication, database, settings, errors, request schemas
  records/                 contract adapter and shared SQLAlchemy definitions
  strategies/              deterministic compiler/evaluator
  research/                request workflow, investigation adoption, comparisons
  replay/                  simulator and saved runs
  accounts/                persisted account views
  agent_context/           versioned context controls
docs/contracts/            frozen/versioned record and execution contracts
docs/implementation/       accepted runtime and decision profiles
docs/qualification/        bounded qualification evidence and reference cases
scripts/p03/, tests/p03/    isolated application verification harness
docs/design/p43/r9/        retained design export
```

See [backend responsibilities and import paths](docs/implementation/BACKEND_PACKAGE_LAYOUT.md). Application filenames describe their responsibility; ticket/schema identifiers remain in contracts and traceability records. The reorganization changed imports and resource paths without changing database schema or application behavior.

## Project documents

The specification, contracts, scoped probe plan and project workflow in this repository are the shared sources of truth. This README explains the product; the specification controls detailed behavior. Their approval status remains explicit.

- [Current state and next action](docs/CONTROLLER_HANDOFF.md).
- [Edge OS Compass workflow](docs/EDGE_OS_COMPASS_WORKFLOW.md).
- [Product scope and qualification requirements](docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md).
- [Research contracts](docs/EDGE_OS_RESEARCH_CONTRACTS.md).
- [Scoped probe plan and approval record](docs/prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md).
- [Probe findings and limitations](docs/prototypes/EDGE_OS_PROBE_A_RESULT.md).
- [Hackathon brief](docs/research/00_HACKATHON_BRIEF.md).
- [Hackathon Winning Compass](playbooks/HACKATHON_WINNING_COMPASS.md).
- [Matt Pocock project workflow](playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md).

## Team and agent setup

Track assigned work in [GitHub Issues](https://github.com/edge-os-app/edge-os/issues). Read [AGENTS.md](AGENTS.md) before an agent task. Tracker, label and domain conventions are under [docs/agents/](docs/agents/).

The builder owns product decisions, all prototyping and the whole backend. One teammate implements the frontend; the other implements the gated tokenization extension after its behavior and interfaces are accepted. The [team ownership section](docs/EDGE_OS_COMPASS_WORKFLOW.md#9-team-ownership) records the boundaries. Assigning an owner does not approve an extension's economics or activation.

Teammates implement accepted tickets on task branches and submit pull requests for builder acceptance. Only the builder merges to `main` by team agreement. The builder selected this manual gate instead of requiring GitHub-enforced approvals or branch protection. Required checks and implementation review still apply.

Contributor coding skills require installation in each contributor's agent environment. They are separate from the planned user-facing agent add-ons catalog. These documentation files do not install either kind of skill or create remote labels.

For supporting evidence and required task inputs, follow the [contributor reference rules](docs/agents/domain.md#shared-documents-and-private-evidence).

Use the locked toolchains and repository verification commands above. New feature work requires its assigned scope, tests and independent reviews; publication does not grant provider access or financial authority.
