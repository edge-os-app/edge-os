# Edge OS Compass workflow

Release-scope amendment, 2026-10-10: use the [approved hackathon release cut](planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) for submission scope and staged prerequisites. The dated statuses below are historical where contradicted by the latest team handoff. Wider Compass/product requirements remain visible. No missing runtime, participant or financial gate passes through the cut.

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Last updated: 2026-10-06, Africa/Kinshasa

Focused handoff clarifications accepted, 2026-10-06: carry the [canonical research declaration and monitoring amendment](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-declaration-and-agent-monitoring-handoff) into existing P02/P06/P08/P09/P19/P23/P24/P26/P27/P33 outputs. It makes source portability, pre-outcome declarations, actual rule evaluation, deployment and health/performance/evidence checks explicit. Additional displayed metrics need adopted calculation conventions. These local documentation changes pass no runtime gate and do not approve the whole graph, testing boundary, publication or dispatch. Review the amended candidate before ready assignments.

P01 stack direction accepted, 2026-10-06: use the [canonical application stack](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-application-stack). The frameworks, PostgreSQL and Privy auth are selected; remaining integration/configuration and verification choices still need their scoped outputs. No workflow gate, implementation dispatch, hosting purchase or financial permission follows from this decision.

Current controller setup, 2026-10-06: prepare a local exact-commit documentation freeze and proposed ticket graph under the builder's request. Complete tracker labels and isolated lanes through the [controller procedure](agents/controller-workflow.md). Decomposition readiness does not approve the proposed breakdown, testing boundary, implementation dispatch or publication. Probe A, frontend participant verdicts, Probe B and full Compass proof retain their existing limits. Matt Step 7 can draft now; publication and ready assignments follow review of the actual graph.

Current specification decision: the builder approved product scope and requested `to-spec` on 2026-10-05. The [canonical synthesis](superpowers/specs/2026-09-29-edge-os-hackathon-design.md) records user stories, test coverage and unresolved dependencies. Local review comes before publication, as explicitly requested. Matt workflow Step 6 is in progress toward ticket handoff. This approval does not pass missing Compass challenge, participant, execution or implementation checks. Earlier full-scope-approval-pending statements below are historical.

Build-handoff consolidation: the builder authorized a [draft first-release brief](EDGE_OS_BUILD_BRIEF.md) and reconciliation of the existing specification. Both are prepared for review. The reported completed walkthrough is recorded as [assisted general feedback](prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md#builder-walkthrough-and-build-handoff-2026-10-05), not new task-level or unfamiliar-trader passes. This pass starts no implementation or tickets and advances no gate by itself.

This repository document is authoritative for team workflow. The workspace path redirects here. The builder owns all prototypes; teammate ownership below refers to accepted implementation work. Private evidence follows the [reference rules](agents/domain.md#shared-documents-and-private-evidence).

Current frontend status, 2026-10-05: the single local prototype is v0.12.2, with separate agent wallets, funding/withdrawal, Funds and the two controller defects repaired. Scoped functional checks and both independent repair confirmations pass; builder closure remains pending. [Findings](prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md#controller-verification-and-repair-v0122-2026-10-05) control actual history. Older frontend “unstarted” or future-approval paragraphs below are historical; Research comprehension remains REVISE and the other four tasks UNRESOLVED. Full design/build-brief acceptance and real execution remain separate. Probe A stays closed and Probe B unstarted.

## 1. Purpose

Current wallet decision, 2026-10-05: the builder accepted [separate user-owned agent wallets and funding](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding). [ADR 0007](adr/0007-separate-user-owned-agent-wallets.md) supersedes the cross-agent shared-wallet direction. The [single frontend packet](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#one-frontend-interaction-prototype) covers the completed local wallet repair and v0.12.2 follow-up. Eight new regression cases, 49 existing checks and 123 assertions pass. Fresh post-repair browser confirmation was unavailable. Earlier shared-wallet approvals remain historical. Per-wallet isolation, funding/withdrawal reconciliation and owner access/removal need qualification before affected live use. No new broad grilling session, Wayfinder map or extra prototype phase is selected. Documentation approval is not production or financial authorization.

This document controls the remaining Edge OS hackathon workflow.

Use the Hackathon Winning Compass as the method. Use this document to apply that method to Edge OS, the Monad Metropolis deadline, and the assigned contributors.

The earlier Monad Idea Funnel no longer controls phase order or gates. Use HACKATHON_COMPASS_SESSION_PROMPT.md, BUILDER-ONLY REFERENCE `playbooks/HACKATHON_COMPASS_SESSION_PROMPT.md` for fresh sessions; the builder approved that flexible, hackathon-independent replacement on 2026-09-30. This document supplies the Edge OS context. Earlier artifacts remain historical evidence. A failed Funnel gate remains visible, but it does not block the Compass workflow.

This document does not replace:

- current official Metropolis rules;
- the canonical hackathon brief;
- the Monad capability map;
- the Hackathon Winning Compass;
- a later approved Edge OS product specification.

## 2. Authority order

When sources disagree, use this order:

1. Current official Metropolis rules and authenticated event information control contest facts.
2. [`research/00_HACKATHON_BRIEF.md`](research/00_HACKATHON_BRIEF.md) controls the local summary of verified contest facts.
3. BUILDER-ONLY REFERENCE `docs/research/01_MONAD_CAPABILITY_AND_INTENT_MAP.md` controls the broad capability and sponsor evidence.
4. BUILDER-ONLY REFERENCE `docs/research/04_EDGE_OS_COMPILER_PRIOR_ART.md` controls the inspected compiler and research-system precedents.
5. BUILDER-ONLY REFERENCE `docs/research/05_EDGE_OS_X_AND_ONCHAIN_DATA_ACCESS.md` controls current Edge OS data-access decisions.
6. BUILDER-ONLY REFERENCE `docs/research/06_JEV_TRADER_ALCHEMY_ENVIO_REVIEW.md` controls the current execution-RPC boundary and the inspected JEV Trader lessons.
7. BUILDER-ONLY REFERENCE `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` controls wallet evidence, the Assensus proof limits, and remaining Monad–Kuru questions.
8. [`../playbooks/HACKATHON_WINNING_COMPASS.md`](../playbooks/HACKATHON_WINNING_COMPASS.md) controls the working method.
9. This document controls current workflow status, build order, gates, and team coordination.
10. An approved Edge OS design specification will control settled product behavior.
11. Implementation plans will control ordered engineering work after the design is approved.
12. BUILDER-ONLY REFERENCE `docs/ideas/inbox/edge-strategy-os.md` and BUILDER-ONLY REFERENCE `monad_agentic_strategy_launchpad_synthesis.md`, held outside the repository preserve product reasoning. The builder authorized both as context for this workflow. They do not override approved specifications.
13. [`CONTROLLER_HANDOFF.md`](CONTROLLER_HANDOFF.md) records team-facing current state and the next authorized action. The private controller history, Monad Idea Funnel and old phase prompts are historical after the switch to the Compass. Their Funnel phase status does not control current work.

Do not use `p.md`, BUILDER-ONLY REFERENCE `p.md` as a product specification. It is a conversation record and contains superseded interpretations.

## 3. Current state

| Item | Status |
|---|---|
| Contest entry decision | Accepted with recorded conditions |
| Selected product | Edge OS |
| Governing workflow | Hackathon Winning Compass |
| Current Compass phase | Phase 3, finalize the product frame after the accepted bounded research probe; challenge/build-brief gates remain open |
| Product design | Product scope approved 2026-10-05; local to-spec synthesis under review. Dependent engineering choices and qualification remain open. |
| Research contracts | Drafted in `docs/EDGE_OS_RESEARCH_CONTRACTS.md`; review with the design |
| Nansen data qualification | `NOT_STARTED`; token/venue, feature, access costs and budget require separate approval |
| Execution direction | Kuru Flow fixed-input swaps with a restricted, revocable Privy signer; design direction accepted, actual route/policy unqualified |
| Existing delegation proof | Assensus X Layer testnet spike passed; see Privy research for scope and sources |
| Monad–Kuru delegated execution | Unproved; no Edge OS spike or runtime gate marked complete |
| Dangerous-claim prototype | Probe A accepted and closed for its revised research-process claim; complete prototype gate unpassed |
| Scoped probe plan | Individual approvals and closed live recovery recorded at `docs/prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md`; complete product design remains a draft |
| Probe A, research/compiler/rejection | `ACCEPTED AND CLOSED — BOUNDED RESEARCH PROCESS ONLY`, builder decision 2026-10-03; checkpoint 1 and reconstructed MOE checkpoint 2 accepted; strategy `UNRESOLVED`, zero supported candidates; owner is the builder |
| Probe B, Monad–Kuru delegation | `NOT_STARTED`; exact configuration and permissions pending; owner is the builder |
| Single frontend interaction prototype | v0.12.2 built; wallet/two-defect repair functionally checked and independently approved; bounded closure pending; human Research REVISE and other tasks UNRESOLVED; owner is the builder |
| Optional post-core extensions and demo revision | Proposed; scope/economics and revised recording contract remain unapproved |
| Product code | Not started under this workflow |
| Main execution domains | Monad meme-token spot trading and LP strategy management |
| Team size | Three |
| Submission deadline | 2026-10-14 03:59 UTC, 04:59 Africa/Kinshasa |
| Internal cutoff | 2026-10-13 23:59 Africa/Kinshasa |

Checkpoint 1 now passes for its bounded meaning, compilation and known-invalid-input scope. Part 1A passed 81/81 mechanics checks; part 1B `1B-sol-an-recheck-09` passed all five fresh live Sol cases under one v6 candidate. Final offline suites passed 35/35 interpretation and 19/19 boundary checks. Earlier failures remain in [the result report](prototypes/EDGE_OS_PROBE_A_RESULT.md). Both model behavior and contract/checker defects contributed to those failures. This evidence does not establish arbitrary-language reliability, historical research quality or profitability.

The builder accepted and closed Probe A on 2026-10-03. Checkpoint 2's actual two-call Hermes investigation retained one hypothesis, four declared variants and all contrary results from reconstructed MOE/WMON history. Its strategy result is `UNRESOLVED`; the sample floor could not be met in the approved window and the holdout stays unopened. Original historical delivery/finality, realistic execution effects and a deployable real-market compiler binding remain unproved. Read [the accepted result and its limits](prototypes/EDGE_OS_PROBE_A_RESULT.md#builder-acceptance-and-closure-2026-10-03); this is a process pass, not a trading-edge finding.

The [focused core product choices](#post-probe-a-focused-decision-session) are complete through Q31 with named qualification gaps. The builder confirmed shared understanding and closed grilling on 2026-10-03. Review the updated single frontend packet and separate Probe B configuration/permissions. Probe B remains separately scoped and unstarted; the frontend is built through v0.12.2, with wallet/two-defect repair checks passing and human acceptance pending. Full-design/build-brief acceptance and the complete Compass prototype gate remain open. The completed model runs are closed, with 28 cumulative requests/USD 0.0814978625 and no unresolved reservations. This synchronization grants no new inference, data collection, wallet, implementation or publishing approval.

For intake and task scoping, follow the design's [bounded-request intake](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#no-thesis-bounded-request), [pool/route binding](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-market-binding-and-data-route) and [first research completion boundary](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-first-research-journey). Carry forward accepted compiler policies into implementation checks. Pending verification does not reopen those decisions, and research completion does not mark the remaining product capabilities complete.

Builder-authorized amendment, clarified 2026-10-03: [observational research](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#research-mode-and-observational-investigations) can finish without a strategy or backtest. [Live trading](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#live-trading-optional-trials-and-forward-learning) is one workflow with an optional trial; ongoing operation may start directly or continue after a trial without compulsory graduation, favorable historical results or paper trading. Carry forward the [accepted live user journey](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-live-user-journey-and-display). Evidence, operating purpose and permissions remain separate. Exact live configuration, additional research tools and provider enforcement remain focused decisions, not newly proved capabilities or financial permissions.

### Engineering execution

Use the builder-approved [model policy](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#approved-model-policy) when assigning the gate, implementer, and internal reviewers. That section controls model IDs, effort, independent review, and optional escalation. It does not advance the current phase or approve implementation.

Use Codex with Matt Pocock's `implement` as the default executor for approved implementation tickets during the remaining build window. Follow the [execution policy](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#execution-policy), [candidate review sequence](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#step-8-implement-one-ready-ticket), and [controller task packet](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md#controller-role-for-multi-session-work). Compass continues to control product scope, stage results, and approval status.

Use selected pstack skills for bounded investigation or unresolved architectural questions. A full Poteto or Superpowers execution route requires an explicit task assignment with its ownership and authority boundaries. Keep one executor responsible for each assigned unit. Installing a plugin is not a build prerequisite.

Require fresh, independent review before integrating changes to mandate enforcement, signing authority, deterministic risk admission, recovery, duplicate prevention, or revocation. Give the reviewer the exact base and candidate SHAs, approved behavior, relevant contracts, diff, and verification evidence. Record the verdict against that candidate. An implementer's report alone cannot satisfy this review.

Each completed ticket must retain evidence of its relevant behavior and important failure case. Preserve the existing schedule's narrowing rules. This documentation update does not approve the product design, a prototype, a paid data run, financial execution, or delegation beyond an assigned task's authority.

### Judging constraints

The authenticated rubric controls product trade-offs:

| Criterion | Weight | Required Edge OS evidence |
|---|---:|---|
| Technical Execution | 20% | A real end-to-end Monad action, deterministic strategy semantics, tests, and inspectable receipts. |
| Design & Craft | 20% | A user can understand assumptions, evidence, rejection, authorization, and results without reading the architecture. |
| Originality & Track Insight | 15% | Edge generation with explicit false-edge rejection, research lineage, and a non-decorative onchain action. |
| Founder & Market Readiness | 25% | A specific first user, direct problem knowledge, honest evidence gaps, and a credible reason to adopt the workflow. |
| Traction & Path Forward | 20% | Target-user tests plus a concrete distribution, integration, liquidity, and continuation plan. |

Technical depth alone addresses only one fifth of the rubric. User evidence, product clarity, and continuation work must run in parallel with implementation.

## 4. Canonical product frame

### Product definition

Edge OS is an edge-generation, validation, deployment, and monitoring system for onchain traders and strategy creators.

It helps a user move through this complete job:

```text
bring an observation, question or possible edge
        ->
investigate and save observations, explanations and unknowns
        ->
optionally define a hypothesis and test the claims data can address
        ->
compile supported capture rules when a strategy is requested
        ->
simulate where feasible or define a forward learning experiment
        ->
preserve evidence status and review the requested next action
        ->
execute only after separate qualification and an explicit bounded mandate
        ->
record what happened
        ->
monitor and record learning without silently changing strategy or authority
```

### First users

The first credible users are active onchain traders and strategy creators who lack a complete quantitative research and execution stack.

The first two user groups are:

1. Meme-token spot traders and trenchers.
2. Liquidity providers and LP strategy operators.

The product may become simpler for less experienced users over time. The hackathon build must not claim that a user with no trading knowledge can safely deploy profitable autonomous strategies.

### Three starting states

Both domains accept the same three starting states:

| Starting state | Meme spot example | LP example |
|---|---|---|
| Concrete thesis | Deployer selling into accelerating retail demand predicts a short-horizon reversal. | Pools with high fee-to-TVL and moderate volatility may compensate for inventory risk. |
| Loose intuition | Funny memes with organic attention seem to keep running. | Providing liquidity during calmer periods seems safer. |
| No thesis | Find a defensible short-horizon edge in a bounded Monad meme universe. | Find a defensible LP opportunity under a fixed capital and risk budget. |

Copying or inspecting a profitable wallet can supply observations for hypothesis generation. Direct trade mirroring is not the Edge OS product. Runner/creator comparisons remain within these starting states; use the [research-mode scope](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#research-mode-and-observational-investigations) to distinguish the broader vision from first-build capability.

### Canonical flow

```text
USER OR RESEARCHER
        |
        | thesis, intuition, or bounded search request
        v
INPUT CLASSIFICATION AND CLARIFICATION
        v
SUPPORTED RESEARCH INVESTIGATION
        |
        | observations, hypotheses, competing explanations and unknowns
        v
SAVED RESEARCH RESULT
        | may finish here without a strategy or backtest
        | when a strategy is requested
        v
SUPPORTED MEANING AND CLAIM-SPECIFIC EVIDENCE
        | EdgeSpec, evidence package and ledger; status retained
        v
STRATEGY COMPILER
        v
versioned StrategySpec
        v
HISTORICAL/SIMULATION TESTS WHERE FEASIBLE
        |---------------------------|
        v                           v
Meme spot backtester          LP simulator
        |                           |
        |---------------------------|
                    v
USER REVIEW OF STRATEGY AND EVIDENCE
                    v
USER SELECTS LIVE TRADING
        | optional trial or ongoing purpose
        | evidence status shown independently; no graduation
                    v
EXECUTION QUALIFICATION, CURRENT INPUTS AND RECOVERY PROOF
                    v
USER APPROVES EXECUTION MANDATE AND RESTRICTED SIGNER
                    v
PERSISTENT WORKER VERIFIES AUTHORITY AND RECOVERS STATE
                    v
TYPED INTENT
                    v
DETERMINISTIC RISK ENGINE
        |---------------------------|
        v                           v
Kuru spot adapter          verified Monad LP adapter
        |---------------------------|
                    v
PRIVY POLICY CHECK AND SIGNING
                    v
TRANSACTION, ORDER, FILL, OR POSITION RECEIPT
                    v
EDGE AND STRATEGY HEALTH MONITORING
```

This diagram shows possible continuations, not a mandatory sequence through backtests or paper trading. Historical tests may be absent for either a trial or ongoing operation. The design's [readiness requirements](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-claim-specific-support-and-readiness-gates) and [live-trading contract](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#live-trading-optional-trials-and-forward-learning) control eligibility; financial consent never rewrites failed evidence or supplies missing execution proof. Continuation follows that contract without automatic permission expansion or accounting resets.

Monad does not create the edge, validate profitability, or prove demand. Monad supplies the bounded market, inspectable state, settlement, execution, and transaction proof. Edge quality comes from research and validation.

### Data and evidence boundary

The first meme-market path uses this source order:

1. Kuru supplies venue metadata, trades, order-book state, order events, and the bounded execution route.
2. Envio supplies reproducible Kuru and Monad event backfill, live indexing, and reorg-aware derived state.
3. QuickNode is the initial standard Monad RPC. It supplies current contract state, gas estimation, receipts, and WebSocket subscriptions.
4. Privy supplies user-owned embedded wallets and policy-scoped delegated signing. The verified transport may use Privy broadcast or signed-transaction submission through QuickNode.
5. Nansen can add wallet labels, flows, holdings, and Smart Money cohorts when a hypothesis needs them.
6. Tenderly can add pre-execution simulation and trace evidence when that evidence changes an authorization decision.
7. The official X API can add timestamped attention and narrative evidence.

QuickNode remains behind a provider-neutral interface. Use Monad's public RPC as a fallback only after the required method checks pass. The user approves a mandate and restricted signer once. Each permitted action then requires deterministic checks and Privy policy enforcement, not another user signature. Select one tested submission transport. Never bypass the signer boundary during provider failure. Envio HyperRPC is read-only and does not replace current-state calls, gas estimation, or submission. Alchemy remains optional when a measured requirement justifies it.

X is optional. Edge OS must support a separately declared onchain-only investigation when X is unavailable, unaffordable, delayed, or outside the approved use case. A social-dependent hypothesis remains unresolved when its essential feature is missing; changing the hypothesis requires a new recorded declaration.

Nansen can contribute to hypothesis discovery, evaluation and monitoring. The [research contracts](EDGE_OS_RESEARCH_CONTRACTS.md#8-nansen-qualification-investigation) define a bounded, unrun data-qualification plan. Nansen is optional at platform level but may be necessary to a specific label/flow hypothesis. Provider loss cannot silently remove that dependency or retain the same validation result. Perpl observations require a separately declared research need; perpetual execution remains deferred.

Social evidence cannot authorize capital. It can generate or support a hypothesis. Execution requires a `ValidationDecision`, a deterministic risk pass, an active user-approved mandate, and the restricted wallet policy.

### Delegated execution and recovery boundary

The draft [design](superpowers/specs/2026-09-29-edge-os-hackathon-design.md) defines mandate fields, runtime recovery, risk checks, revocation, and acceptance tests. Review sections 7, 8, 12, and 17 before assigning execution work. Those definitions remain proposed until the builder approves the design.

The LLM and research agents emit typed records. Only the deterministic execution service can authorize Privy requests. Its credential remains in the backend secret store. The user wallet key remains with Privy. Execution credentials must not be able to weaken the approved policy.

Assensus's completed X Layer test proves restricted signing, owner removal, and a denied repeat for one zero-value call. It does not prove Monad–Kuru operation, unattended strategy execution, or restart safety. Reuse the inspected pattern instead of repeating a generic app-owned wallet test.

Before claiming deployed autonomy, prove one permitted Kuru action without a second user signature, an independent wallet-policy denial, restart reconciliation without duplication, and verified signer removal. Preserve denial records and distinguish accepted orders from fills.

Apply the accepted [scoped stop boundaries](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#pause-revoke-and-pending-exposure). Stop new entries may retain approved exit rules; Halt all swaps and expired/revoked authority permit no new swaps in scope. Neither mode closes positions or undoes broadcasts. Show residual exposure and queue delays. A timeout requires reconciliation of the original attempt before another action. The initial Flow adapter has no resting-order action.

Every social record used by research must preserve:

- the query or stream rule;
- the post identifier and creation time;
- the collection time;
- the engagement values observed at collection time;
- the language, spam, repost, and author-concentration filters;
- the feature or sentiment model and version;
- the aggregation window;
- the linked token address or Kuru market.

Historical engagement counts cannot be reconstructed from current counts. Begin forward snapshots now. When a historical point-in-time value is unavailable, mark the feature unavailable instead of filling it with current information.

The submitted product must use the official X API if it uses X. Unofficial scrapers can inform no production or demo dependency without written permission and a separate policy decision.

### Shared product objects

The two domains share these objects:

- `PromptInterpretation`
- `ResearchBudget`
- `ResearchLedger`
- `EdgeSpec`
- `ResearchEvidencePackage`
- `StrategySpec`
- `ValidationDecision`
- `ExecutionMandate`
- persistent deployment state
- risk policy
- trade or LP intent
- decision receipt
- edge-health record

Compiler outcomes must distinguish:

- `COMPILED`
- `NEEDS_CLARIFICATION`
- `UNSUPPORTED`
- `REJECTED`

Research and validation outcomes must distinguish:

- `EDGE_REJECTED`
- `UNRESOLVED`
- `VALIDATED_FOR_BACKTEST`
- `READY_FOR_PAPER_TEST`
- `READY_FOR_BOUNDED_EXECUTION`

Do not convert every input into a runnable strategy.

The domain simulators and action vocabularies differ.

Before defining a mechanism thesis, accepting an agent evidence package, creating research fixtures or qualifying a provider, read [EDGE_OS_RESEARCH_CONTRACTS.md](EDGE_OS_RESEARCH_CONTRACTS.md). It owns the detailed proposed fields, evidence distinctions, timing/failure rules and examples. Review these contracts with the design. Their completeness does not prove an edge or authorize a trade.

| Meme spot | LP management |
|---|---|
| Token discovery and directional signals | Pool discovery and fee analysis |
| Buy, sell, and exit rules | Add, remove, rebalance, and collect rules |
| Market depth, spread, price impact, slippage, and latency | Fee accrual, inventory, impermanent loss, range or allocation behavior, and rebalancing cost |
| Kuru order, fill, cancellation, and transaction proof | LP position and transaction proof from a verified Monad venue |

### Working one-sentence explanation

> For active onchain traders and liquidity providers, Edge OS turns a thesis, intuition, or bounded research request into an inspectable edge hypothesis and typed strategy. It rejects unsupported results and executes permitted Monad actions under a user-approved, revocable mandate.

This is a framing test, not final marketing copy.

## 5. Scope model

### Product MVP

The product MVP contains two domains:

- meme-token spot strategies;
- LP strategies.

The two domains prove that Edge OS is a financial-strategy runtime rather than a renamed meme bot.

### First dangerous-claim prototype

The first prototype must be narrower than the product MVP.

Its broader product claim is:

> Given a bounded onchain-market research request, Edge OS can generate or formalize inspectable hypotheses, preserve every tested variant, reject plausible false edges without silently inventing assumptions, and compile only supported survivors into typed strategy specifications.

The first approved probe domain was Monad meme spot, using a predeclared continuation family. The builder accepted its narrower interpretation/reconstructed-research process claim, including a useful unresolved result and known leakage rejection. It did not establish general alpha generation or the broader product claim above. Read [the shared probe plan](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#24-builder-acceptance-and-probe-a-closure-2026-10-03) for closure and retained limits. Probe B independently tests the still-unproved delegated action, denial, recovery and revocation boundary; one component cannot pass the other.

### Second proof of generality

After the shared runtime and first spot path work, add one narrow LP path through the same objects and evaluator boundary.

The minimum LP proof is:

1. Accept one LP thesis or bounded search request.
2. Produce an LP `EdgeSpec`.
3. Compile an LP `StrategySpec`.
4. Simulate fees, inventory behavior, impermanent loss, and rebalance costs under declared assumptions.
5. Produce a validation decision.
6. Prepare or execute one bounded LP action only when a verified Monad LP adapter exists.

Do not build a broad LP portfolio manager before this proof works.

### Deferred features

Keep these outside the first complete path:

- strategy marketplace;
- strategy or agent tokens;
- autonomous treasuries;
- public funding and revenue loops;
- lending, perps, prediction markets, and tokenized stocks;
- cross-chain execution;
- asset launch and market creation;
- unrestricted Hermes research;
- broad QT401 formula search;
- multi-edge portfolio optimization;
- full edge-decay automation;
- user governance over risk controls.

They may appear in the path-forward section of the pitch. They do not belong in the initial implementation plan.

This exclusion applies to the initial core and the two probes, not a permanent prohibition on writing optional contracts. The post-core reassessment, BUILDER-ONLY REFERENCE `docs/research/13_EDGE_OS_POST_CORE_SCOPE_AND_DEMO_REASSESSMENT.md` proposes gated publication, tokenization and operating-funding extensions. The builder has not approved their classification, economics or activation. They must not delay the scoped probes, change LP commitments or acquire execution authority by implication. Minimum freshness, drift and stop-condition checks remain required for an acting worker; only broader edge-decay automation is deferred.

## 6. Evidence discipline

Use these labels in research, design, implementation notes, and the demo:

- `VERIFIED FACT`: supported by an official source, inspected source code, or reproducible test.
- `FOUNDER OBSERVATION`: supplied from the builder's experience.
- `DIRECT USER EVIDENCE`: supplied by an identified target user about a real event.
- `PRODUCT OR SPONSOR STATEMENT`: a claim made by a project, sponsor, or product team.
- `INFERENCE`: a conclusion drawn from verified material.
- `HYPOTHESIS`: a claim Edge OS still needs to test.
- `UNKNOWN`: evidence is missing.

A successful receipt confirms transaction execution at the recorded commitment state. Venue events establish order or fill results. Neither proves edge validity, profitability, or demand.

A backtest proves only what its data, semantics, costs, search history, and validation procedure support. It does not prove future profitability.

A model-generated course note is an orientation source. Check the video, transcript, course code, paper, or implementation test before using an exact formula, threshold, algorithm, or API behavior.

## 7. Compass stages and gates

The stages below use the Compass phase numbers. They are the default route, not a mandatory sequence of documents. The session prompt, BUILDER-ONLY REFERENCE `playbooks/HACKATHON_COMPASS_SESSION_PROMPT.md` permits bounded research, combined short reviews and builder-approved narrow experiments where they resolve a named uncertainty. Record route changes and retained risks without claiming skipped work passed. Current full-product gates remain in force unless the builder explicitly changes them; a scoped experiment approval applies only to that experiment. Do not translate stages into the retired Funnel numbers or require numerical incident/match/candidate quotas.

### Phase 0: choose the contest

Status: `COMPLETE`

Evidence:

- the builder accepted the conditional entry verdict;
- a three-person team is planned;
- the schedule and unresolved official terms are recorded.

### Phase 1: read the room

Status: `COMPLETE ENOUGH TO BUILD`

Evidence:

- hackathon brief completed;
- capability map completed;
- authenticated judging rubric recorded;
- official submission artifacts recorded;
- winner patterns recorded separately from official rules.

Selected sponsor and venue documentation must be rechecked before implementation when an API, SDK, or bounty requirement controls behavior.

### Phase 2: generate ideas from experience

Status: `COMPLETE BY BUILDER DECISION`

The builder selected Edge OS. Earlier evidence gaps remain visible. Selection does not convert raw-idea claims into user demand.

### Phase 3: frame the product

Status: `IN PROGRESS`

Required output:

`docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md`

The design must contain the complete Compass idea card:

- exact first user;
- triggering moment;
- current failed process;
- consequence;
- complete job;
- accepted inputs;
- product action;
- visible result;
- necessary Monad and venue behavior;
- canonical data sources and their failure modes;
- the optional X evidence contract and onchain-only degraded mode;
- point-in-time and look-ahead safeguards;
- mechanism-first `EdgeSpec` and structured research-agent evidence, with research-contract references;
- definition of finished;
- smallest complete path;
- excluded features;
- one-sentence explanation;
- one-minute explanation;
- three-minute demo contract.

Exit gate:

- the builder approves the written design;
- the design distinguishes the two-domain product from the one-domain first prototype;
- the design names the first research family;
- the design names the Kuru, Envio, QuickNode, fallback-RPC, and optional-enrichment boundaries;
- the builder reviews the research contracts, evidence-package examples and hypothesis-essential data failure behavior;
- the design separates models from the Privy execution service and defines the mandate, persistent recovery, and revocation limits;
- the product still completes the primary investigation without X;
- every unresolved claim is labeled;
- a listener can identify the user, failure, product action, Monad role, and visible proof.

#### Post-Probe A focused decision session

Status: `FOCUSED GRILLING CLOSED; BUILDER-CONFIRMED UNDERSTANDING; QUALIFICATION UNRUN`. The builder accepted the [loose-intuition starting scenario](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-main-starting-scenario), [journey's steps, finished result and failure path](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-first-research-journey), and [price/volume input scope](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-initial-research-inputs) on 2026-10-03. The builder also accepted the [typed language, scheduled-history and three-valued Boolean policies](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-strategy-language-and-missing-data-policies), with [focused unrun fixtures](EDGE_OS_RESEARCH_CONTRACTS.md#typed-language-and-missing-data-acceptance-fixtures). The [calculation conventions](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-calculation-conventions) and their [authored unrun checks](EDGE_OS_RESEARCH_CONTRACTS.md#calculation-convention-acceptance-fixtures) are also accepted. The [operator registry](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-initial-operator-registry), [pool binding/data route](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-market-binding-and-data-route), [claim-specific readiness gates](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-claim-specific-support-and-readiness-gates) and [focused unrun requirements](EDGE_OS_RESEARCH_CONTRACTS.md#operator-binding-and-readiness-acceptance-fixtures) are accepted. The [effect outcome/control definitions](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-effect-outcomes-and-comparisons) and [authored unrun checks](EDGE_OS_RESEARCH_CONTRACTS.md#effect-outcome-and-control-acceptance-fixtures) are accepted. The [statistical-support policy](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-statistical-support-policy) is accepted; [STAT-Q01](EDGE_OS_RESEARCH_CONTRACTS.md#stat-q01-method-profile-and-qualification) has a selected candidate for qualification, currently unqualified and optional for the core build. This governs evidence claims and does not force historical tests, paper trading or graduation before the accepted live flow. The [persistent independent display and one frontend prototype](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-independent-status-display-and-one-frontend-prototype) and [Flow fixed-input swap direction](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#exact-monad-operation) are accepted. The [grouped activation review, multiple positions, finite allocation/cumulative allowances and guarded temporary recovery](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-activation-positions-and-shared-wallet-accounting) are accepted through Q21, amended Q22 and conditional Q23. [Focused wallet checks](EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks) are unrun. Q24–Q27 accept [scoped stops](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#pause-revoke-and-pending-exposure), [asset-specific allowances/full-inventory exit reservations and an initial wallet queue](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-allowance-units-and-exit-capacity), plus explicitly permitted additions for supported strategies. Q28–Q30 accept cumulative renewal accounting, original signed-transaction/hash resend boundaries and weighted average position cost, preserving realized/unrealized results and external flows. Q31 A selects preapproved position-inventory-based sell permission as the initial direction. [EXIT-CAP-Q01](EDGE_OS_RESEARCH_CONTRACTS.md#exit-cap-q01-permission-model-qualification) must qualify attribution, agent-wallet/asset coordination, sufficient exit capacity and the distinction between application checks and independent wallet restrictions. Inventory enforcement/capacity, route/provider behavior, accounting/queue qualification, exact profiles and measured resource bounds remain open with named unrun checks. Broader research extensions remain unselected. The [single frontend packet](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#one-frontend-interaction-prototype) records built v0.12.2 and the completed local repair checks. The accepted [separate-agent-wallet amendment](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding) supersedes the earlier cross-agent shared-wallet assumptions. Runtime wallet qualification and human comprehension remain unproved. Probe B remains unstarted; its [exact outstanding configuration/permissions](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#probe-b-outstanding-configuration-and-permissions) remain unset/unqualified. If qualification needs another approver or authority architecture, present alternatives and obtain a builder decision before adoption. The builder accepted the bounded research-process result and authorized synchronization on 2026-10-03. This session settles the production route, not whether to keep searching until a backtest wins. The builder confirmed the closing understanding and accepted the [direct account/contextual-conversation amendment](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-account-views-and-contextual-conversation) on 2026-10-03. The existing single frontend packet prioritizes unresolved research, live permission, positions through both channels, stop/close behavior and continuation. Prototype leads; Impeccable Operate supports layout/clarity. The builder owns product decisions and all prototyping.

Use the existing draft design, [research contracts](EDGE_OS_RESEARCH_CONTRACTS.md#interpretation-classification-and-field-level-evidence) and [accepted probe report](prototypes/EDGE_OS_PROBE_A_RESULT.md#builder-acceptance-and-closure-2026-10-03). The following core choices are recorded. Use their authoritative specification sections and named qualification checks; implementation details belong in the accepted build brief, not a new competing spec.

| Decision | What to settle | Current boundary |
|---|---|---|
| First complete user journey | Exact first trader, starting question, useful end state and understandable failure path | Meme spot first; an explained unresolved result is useful. LP remains the separate second proof unless the builder explicitly changes scope. |
| Supported strategy meaning | Initial grammar/features, units, timing, missing-data behavior and unsupported actions | Reuse verified probe lessons. Its four variants and thresholds are experiment limits, not permanent product rules. Bind production artifacts to real market/asset identity. |
| Classification and clarification | Starting-state names, requested job, field source/origin/uncertainty, preserved restrictions and changed-field display | Record these in the first intake ticket. Ask only for stage-required meaning. High model confidence cannot grant readiness; ranking scores wait for multiple investigations. |
| Data and simulation claim | First provider/dataset route, availability assumptions, gaps, fill/cost coverage, sample feasibility and displayed limits | Envio history and QuickNode state/reconciliation are the existing route. MOE reconstruction does not prove live fillability, delivery or net tradability. Keep unsupported claims unresolved. |
| Evidence and readiness | Required run outputs, lineage, decision reasons and gates for compilation, research, paper and execution | Draft saving and compilation are not evidence support. Unresolved adopted settings remain configuration, not a selected strategy. Keep holdout/trial history intact. |
| Observational research scope | Which runner/creator or participant investigation, if any, belongs in the hackathon build; tools, data and useful report | First rule/evaluation slice remains one pool with price/volume. Findings need not compile. Broader attribution/accounting capabilities must be qualified rather than assumed from Hermes. |
| Live trading and continuation | Exact consent, supported operation, capital/action/duration limits, optional trial stop, current permissions and forward records | Carry the accepted single live flow and user journey into implementation. Trial/ongoing purpose does not change evidence status. Continuing under active authority differs from renewing or expanding permissions. No live action is approved by discussion. |
| Monad execution and demo | Intended Kuru interface/operation, remaining authority/recovery proof, and distinction between research and execution cases | MOE used an external pool indexed by Kuru Flow, not a Kuru CLOB. The initial Flow fixed-input direction is accepted; the deployed route and enforceable restrictions remain unqualified. Probe B must pass before autonomous-execution claims. No wallet action is approved here. |
| Frontend and team handoff | Which states the interaction prototype must communicate; schemas, sanitized examples and API expectations | Use the real unresolved investigation and labeled fixtures for other states. The builder owns backend/prototypes; teammates implement accepted UI and gated token-extension tickets. |

Test the one-minute explanation with a target user and technically strong teammate inside the separately approved single frontend prototype, applying Phase 4 below. Keep human observations separate from technical results. Missing target-user participation leaves comprehension and demand gaps; discussion does not satisfy them.

Completion requires an agreed smallest path, a closed decision list or named blockers/owners, explicit limits, and enough state/contract detail to scope the interaction prototype. Then approve that small prototype separately, review whether a non-technical viewer understands the decision, accept the design/build brief, and publish implementation tickets. Do not create ready tickets from pending choices.

Keep all interaction and comprehension checks inside one frontend prototype; do not create a separate interaction-prototype phase. Scope that same prototype around the accepted [live user journey](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-live-user-journey-and-display): include the real unresolved research report plus labeled fixtures for direct ongoing start, optional trial, favorable limited observations, continuation within active permission and continuation requiring changed permission. Test whether a viewer understands that both operating purposes use real money, that running can coexist with unproven evidence, and that continuation does not grant unlimited authority. Show "Continue trading", "Review and adjust limits", "Revise strategy" and "Pause trading" without graduation language. Preserve the real MOE report as unresolved and unpermitted; these fixtures supply no wallet proof. Approve the scope before starting this builder-owned prototype.

Use Wayfinder only if unresolved dependent decisions cannot fit this session. The builder selects that route; its map covers remaining core blockers, not settled product selection or optional-token economics. If the session resolves them, skip the map. This route follows the Compass's challenge, dangerous-claim and completed-user-job rules while retaining the earlier experiment's approved out-of-order placement.

### Phase 4: challenge the idea

Status: `NOT STARTED`

Actions:

1. Give the one-minute explanation to at least one active onchain trader or LP operator.
2. Give it to at least one experienced builder or technically strong teammate.
3. Ask each person to explain the product back without coaching.
4. Record what they misunderstood, doubted, or considered unnecessary.
5. Run the After It Works questions against the complete job.

Exit gate:

- at least two people can repeat the core product without turning it into a copy trader, generic bot builder, dashboard, or backtest generator;
- the smallest substitute is explicit;
- the dangerous claim and likely failure are explicit;
- unsupported demand remains labeled.

If direct users are unavailable within one day, record the limitation and continue with a builder challenge. Do not claim user validation.

### Phase 5: write the build brief

Status: `DRAFT PREPARED FOR BUILDER REVIEW`, 2026-10-05. [First-release brief](EDGE_OS_BUILD_BRIEF.md). The builder authorized preparation before full scope acceptance; unresolved contracts and qualification are named. This is not a completed exit gate.

Required output:

`docs/EDGE_OS_BUILD_BRIEF.md`

This is the full-build brief, not a prerequisite for either narrow experiment. The builder may approve [the shared probe plan](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md) as the sufficient scoped design/plan before this phase passes. Do not mark the full brief or challenge complete merely because an experiment starts.

Before the relevant work becomes ready, the brief must identify and link the frozen contracts for:

- one primary user path;
- one failure path;
- input and output contracts;
- fixture examples;
- Monad or venue operation;
- user-owned wallet binding, mandate limits, policy content, and exact signing and submission transport;
- persistent runtime states, recovery rules, idempotency, and stop conditions;
- proof or receipt;
- non-goals;
- team ownership;
- prototype acceptance tests;
- the [approved per-agent add-ons catalog](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-add-ons-catalog), including exact entries, versions, tool access, authentication/cost display, isolation and enable/disable lifecycle. Qualify required research/account tools before exposing them through the catalog; broader custom plugins remain outside MVP scope.

The catalog is builder-approved direction from 2026-10-04, not an installed integration or implementation approval. Its [acceptance checks](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#agent-add-ons-acceptance-checks) are unrun. It does not reopen Probe A or expand the existing five-task frontend prototype. Freeze catalog details in the build brief and assign accepted implementation tickets; keep wallet authority and the separate execution gate unchanged.

The [OpenBB assessment](research/OPENBB_RESEARCH_REUSE_AND_PRODUCT_DIFFERENCES_2026-10-04.md) supplies optional research-component and UI-context lessons. It is not a new dependency or stage gate. If an accepted ticket selects a component, freeze its release, supported calculation/tool semantics, provenance, access/costs and focused checks in the build brief under the [candidate boundary](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#openbb-research-reuse-candidate). Keep Envio/QuickNode roles and the core runnable without OpenBB. Continue existing frontend tasks; do not start another broad prototype or copy a terminal layout merely to adopt this reference.

Exit gate:

- each teammate can start from stable fixtures;
- the frontend does not depend on unfinished quant internals;
- the quant engine cannot bypass the deterministic risk and execution boundary;
- the brief distinguishes compiler proof from the still-required delegated-execution gate;
- the demo contract fits within three minutes.

### Phase 6: prototype the dangerous claim

Status: `PROBE A ACCEPTED AND CLOSED; FULL PHASE GATE UNPASSED`

The [result report](prototypes/EDGE_OS_PROBE_A_RESULT.md) records the passing 1A recovery, all five fresh live Sol v6 cases, the reconstructed MOE investigation and the builder's accepted Probe A closure. Earlier failures and historical-delivery uncertainty remain preserved. This closes the revised bounded research-process question, not the earlier challenge/build-brief gates or full prototype gate. No supported strategy exists. Probe B and viewer-understanding evidence remain unproved; the current full-product stage remains Phase 3.

The prototype must test the research and rejection engine before building the full application.

The route separates Probe A and Probe B under [EDGE_OS_SCOPED_PROBE_PLAN.md](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md). Probe A is closed; further research needs a new declared question, not an extension to manufacture a survivor. The plan owns Probe B's pending inputs, approval and result path. Financial and provider permissions remain separate. Record `PASS`, `NARROW`, `REJECT` or `UNRESOLVED` for each actual claim. A compiler/fixture pass and a real execution pass cannot stand in for one another. The checks below govern the assembled dangerous-claim prototype, not permission to build all of it in either small probe.

Minimum prototype:

1. One bounded market universe.
2. One approved strategy family.
3. One fixed primitive set.
4. One declared `ResearchBudget`.
5. A `ResearchLedger` that retains failed candidates.
6. An inspectable `EdgeSpec`.
7. A typed and canonical `StrategySpec`.
8. Costs, slippage, latency, liquidity, and capacity assumptions.
9. A point-in-time feature dataset with source and collection timestamps.
10. A train or research period and a sealed holdout or honest substitute.
11. At least one deliberately attractive false-edge case.
12. A clear rejection trace.
13. An onchain-only run that does not require X.
14. At most one controlled survivor for paper testing.
15. One mandate-scoped execution intent from the controlled survivor, or a clearly labeled fixture for mechanical testing.
16. One real Monad or Kuru test operation when the selected adapter and network state make it safe and reproducible.

Prototype pass gate:

- the system makes missing assumptions visible;
- it preserves search lineage and trial count;
- it rejects unavailable or future information instead of filling the gap silently;
- a plausible false edge is rejected for a specific reason;
- the evaluator uses the same strategy meaning intended for paper and live modes;
- the research agent cannot submit the execution itself;
- the host connects one mandate-authorized intent to a real Monad operation and receipt; if blocked, preserve the exact adapter blocker and return a limited or unresolved verdict instead of a full prototype pass;
- an X failure does not block the onchain-only investigation;
- one failure case is understandable without a long explanation;
- the output is useful even when zero strategies survive.

The prototype does not need to prove demand or future profitability.

The separate delegated-execution gate in design section 17 must pass before the team claims autonomous deployment works. An adapter blocker or the old Assensus proof cannot satisfy it.

After reviewing probe evidence, use Wayfinder only when dependent core decisions cannot fit into one focused session. Matt also permits probes inside Wayfinder; this project's probe-first route is a bounded schedule choice, not a universal rule. Resolve only decisions blocking the approved core, aim to finish that planning within one day, and keep unselected optional-token economics outside its critical path. If a focused session suffices, finalize the accepted production design/build brief directly. No component verdict automatically advances the Compass stage or grants full implementation authority.

### Phase 7: complete the product

Status: `NOT STARTED`

Build order:

1. Freeze schemas and JSON fixtures.
2. Complete the shared compiler and deterministic evaluator.
3. Complete the meme spot simulation path.
4. Add deterministic risk checks.
5. Connect the user-owned wallet, restricted signer, and one real Kuru spot operation.
6. Prove runtime recovery and revocation. Save inspectable denial, transaction, order, and fill records.
7. Add the narrow LP path through the shared runtime.
8. Connect a verified LP adapter only after its behavior and proof are known.
9. Add agent investigation only where a deterministic or bounded method cannot complete the job.

Completion gate:

- a new user can finish the primary job;
- the core result is not a dashboard;
- the deployed application performs real Monad behavior;
- failure states remain visible;
- the repository explains how to reproduce the proof.

### Phase 8: design with references

Status: `NOT STARTED`

Design the working application, including slow research, missing data, rejected edges, delegation refusal, policy denial, recovery, revoked authority, pending orders, and degraded services.

The frontend should emphasize:

- the user's input;
- assumptions and clarification;
- `EdgeSpec` evidence;
- `StrategySpec` interpretation;
- why a result passed, failed, or remained unresolved;
- what mandate the user is authorizing and which actions it permits;
- current authority, pause and removal controls, and any remaining exposure;
- the resulting receipt.

Avoid long animations and financial-dashboard decoration that does not help the user complete the job.

### Phase 9: test completeness

Status: `NOT STARTED`

Required checks:

- compiler intent-fidelity corpus;
- invalid and adversarial input cases;
- parser and type-checker property tests;
- canonical serialization and hash stability;
- lookahead and point-in-time checks;
- deterministic replay;
- cost and latency sensitivity;
- risk-policy denial cases;
- onchain adapter failure cases;
- Privy policy denial independent of risk denial;
- signer removal, expiry, and policy-content drift;
- restart, uncertain submission, concurrent workers, and duplicate prevention;
- order acceptance versus partial fill, fill, and cancellation;
- frontend empty, loading, rejection, and failure states;
- deployment and public reproduction check.

### Phase 10: build the demo

Status: `NOT STARTED`

Read [design section 18](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#18-three-minute-technical-demo-contract) for the provisional recording contract. It remains pending probe findings and builder review. Use the [Compass timing](../playbooks/HACKATHON_WINNING_COMPASS.md#curated-three-minute-demo): the main user path receives the longest uninterrupted segment, the useful result appears early, and working content ends by 2:55. Do not duplicate the timed script here. Separately label any unresolved investigation, execution fixture or replay. Token behavior enters only after its own approval, implementation and tests; it is not a prerequisite for either probe.

Keep a replayable local proof in case the live network or an external service fails during recording. A replay is not evidence of a live action during that recording.

### Phase 11: submit

Status: `NOT STARTED`

Required standard artifacts:

- project logo or graphic;
- public GitHub repository;
- live application on Monad mainnet or testnet;
- technical demo video of no more than three minutes;
- pitch video of no more than two minutes;
- written project description;
- selected track and bounties;
- extra proof required by any selected bounty.

Finish and submit by the internal cutoff. Use the remaining time as recovery margin.

### Phase 12: treat the result as data

Status: `NOT STARTED`

After judging, record what users understood, what failed, which claim survived, and whether the product earned continued development.

## 8. Schedule

This schedule protects the internal submission cutoff of 2026-10-13 23:59 Africa/Kinshasa.

Replanned on 2026-10-02. Earlier design/build-brief targets elapsed without a recorded pass. The dates below are proposed work targets, not approved scope or evidence of completion. Use actual team capacity when approving the plan; calendar days alone do not establish feasibility.

Begin forward X snapshots during product design if official API access is available. Do not delay the compiler prototype for X access. Historical searches cannot recover the engagement state that existed at an earlier decision time.

| Date | Target |
|---|---|
| 2026-10-02 | Instantiate/review the shared probe plan. Start only approved experiments. Run A and B independently within their approved budgets; review initial answers today. |
| 2026-10-03 | Close bounded probe blockers or approve a narrower claim. Run a short product challenge with a target user and teammate when available; preserve missing user evidence. Resolve linked core decisions through focused planning or a small Wayfinder map. |
| 2026-10-04 | Record verdicts and evidence limits. Approve the production scope/build brief and ready tickets if the evidence supports them; otherwise replan explicitly. |
| 2026-10-04 to 2026-10-08 | Complete shared runtime, meme spot path, frontend path, API, persistence, and first Monad proof in parallel. |
| 2026-10-08 to 2026-10-10 | Add the narrow LP proof. Stabilize integration and failure states. |
| 2026-10-10 to 2026-10-11 | Deploy, test with users, verify reproduction, and close critical defects. |
| 2026-10-12 | Record technical and pitch videos. Prepare graphic and written submission. |
| 2026-10-13 | Buffer, final proof check, public repository check, and submission before 23:59 Africa/Kinshasa. |

If either probe remains unresolved or rejects its claim by 2026-10-04, record the exact cause and approve a narrower useful path or stop the affected work. Do not hide the failed core behind more frontend work or a token feature. A token extension needs its own later activation gate and time budget; no implementation slot is committed by this schedule.

If the primary meme spot path is unstable on 2026-10-08, defer live LP execution. Preserve one LP compile-and-simulate proof only if it reuses the stable runtime and does not endanger the main path.

## 9. Team ownership

Ownership amendment, builder-requested 2026-10-10. The former fixed backend/frontend/tokenization teammate split is superseded. Ownership follows explicit ticket assignments and shared-file leases. The [approved release cut](planning/EDGE_OS_RELEASE_CUT_2026-10-10.md) controls hackathon scope.

### Builder: product, prototypes and consequential permissions

The builder owns product decisions and prototypes, including research, execution and UI interaction probes. The builder approves release claims, new product behavior, provider access, spending, wallet operations and financial actions. Participant recruitment, recordings and submission follow the owners recorded in the release cut.

Backend and frontend implementation may be delegated through accepted tickets. This does not delegate product or financial authority. Preserve accepted record semantics, risk rules, owner isolation and recovery requirements regardless of the implementation owner.

### Codex controller: coordination and local integration

The controller prepares task worktrees and frozen packets, assigns owners, selects relevant skills and manages shared-file leases. It coordinates the two independent internal reviews and separate gate. It verifies the exact candidate and evidence, accepts the proved technical scope and integrates serially into `integration/edge-os-mvp` under the recorded controller authority.

The selected execution workflow controls agent context and transport. A new document does not switch active assignments. The controller may implement a specifically authorized change itself, but independent reviewers and the separate gate still assess that change.

Publication and `main` merges require recorded builder authorization. The controller can execute a specifically authorized merge. Technical acceptance, an assigned owner or a gate PASS does not grant deployment, provider or financial permission.

### Implementation agents and contributors: assigned tickets

Each agent or human contributor implements only its accepted assigned scope in an isolated worktree and branch. The packet identifies the exact base, owned paths, shared-file lease, skills, tests and return route. Backend and matching UI work may belong to the same ticket owner. There is no standing frontend or tokenization teammate assignment.

The existing Claude owner retains P05, including its issued backend/UI shared-wiring lease. Preserve its session, branch, staged history and continuation. Do not create a second P05 writer. Current assignments and completion evidence are recorded in the team handoff and controller ledger.

A prospective quant/backend teammate may receive a separate optional extension such as P14 or P42 after explicit assignment. That recommendation assigns neither ticket and creates no submission dependency. Required inputs must be published contracts, permitted extracts, labelled fixtures and public references. Private courses are not mandatory contributor inputs.

Core wallet, signing, money and recovery work stays in the builder-directed execution queue unless explicitly reassigned. The same acceptance, review and permission rules apply to human and agent implementations.

### Optional tokenization extension

No tokenization contributor is assigned by this ownership update. The extension remains outside the hackathon cut and needs accepted behavior and interfaces before implementation.

Before a dependent extension ticket is ready, accept the holder's utility/rights, immutable strategy-revision binding, eligibility evidence, fee route, liquidity source, pause/version-change behavior, governance limits and absent claims. Ownership does not authorize these decisions or expand trading authority.

Implementation may use labelled fixtures after its behavior and interfaces are accepted. Activation needs the core proof, extension checks and separate builder approval. Optional economics and activation remain unapproved and must not block the core release.

### Integration contract

The controller must ensure required versioned schemas and representative fixtures are published under builder authorization before a contributor depends on live quant output.

Minimum fixtures:

- complete, vague and unexplained mechanism hypotheses with evidence-package examples;
- transfer misclassified as purchase, future label leakage, incomplete buckets, omitted contradictions and budget breaches;
- loss of a hypothesis-essential provider input, with unresolved or separately declared replacement behavior;
- concrete thesis requiring clarification;
- loose intuition producing an `EdgeSpec`;
- no-thesis request with bounded search parameters;
- rejected false edge;
- unresolved result due to missing data;
- onchain-only result with X unavailable;
- social-evidence result with source and collection timestamps;
- validated edge with a compiled StrategySpec;
- risk-denied trade intent;
- approved spot intent with receipt;
- active, expired, paused, and revoked mandate;
- Privy policy-denied action without a transaction;
- submission with unknown outcome and recovered order;
- signer removal with a still-open order;
- LP StrategySpec and simulated result.

Assigned frontend work can use these fixtures while the real engine is being built. Optional tokenization work uses its separately accepted publication contract and revision/eligibility fixtures. A fixture grants no live authority and establishes no profitability.

## 10. Quant course knowledge base

The QT101 to QT401 material is a design and implementation reference. It is not a product requirement by itself.

The course knowledge base starts at BUILDER-ONLY REFERENCE `course-insights/README.md`. BUILDER-ONLY REFERENCE `course-insights/manifest.csv` records 92 lessons:

- QT101: 25 lessons;
- QT201: 21 lessons;
- QT301: 20 lessons;
- QT401: 26 lessons.

All 92 lessons have a Gemini whole-video orientation pass. Current word-timestamp text transcript coverage is:

- QT101: 18 of 25 lessons;
- QT201: 21 of 21 lessons;
- QT301: 15 of 20 lessons;
- QT401: 8 of 26 lessons.

The whole-video files are model-generated first passes. The transcripts establish spoken content more directly, but formulas and code still require source or video checking.

### QT101: quant engine foundations

Use for:

- alpha-unit representation;
- sizing and volatility targeting;
- portfolio construction;
- vectorized evaluation;
- performance and memory considerations;
- type compatibility.

Primary local material:

- BUILDER-ONLY REFERENCE `course-insights/QT101`
- BUILDER-ONLY REFERENCE `course-insights/transcripts/QT101`

Use QT101 when implementing position sizing, portfolio state, vectorized primitives, and simulation mechanics. Do not delay the compiler prototype to reproduce the entire course library.

### QT201: false-edge rejection

Use for:

- portfolio metrics;
- hypothesis tests and confidence intervals;
- price and bar permutations;
- Monte Carlo permutation tests;
- asset-timing and asset-picking skill tests;
- decision shuffling;
- p-values;
- multiple-hypothesis and family-error controls.

Primary local material:

- BUILDER-ONLY REFERENCE `course-insights/QT201`
- BUILDER-ONLY REFERENCE `course-insights/transcripts/QT201`

QT201 controls the prototype's strongest product claim. Use its methods to design rejection tests, but source-check exact formulas and assumptions before implementation.

### QT301: strategy language and runtime

Use for:

- recursive strategy representation;
- parsing and canonical serialization;
- tree traversal and deterministic evaluation;
- primitive registries;
- alignment and missing-value policies;
- time-series and cross-sectional operations;
- branching and specialized logic;
- compound functions and macro expansion;
- no-code backtesting.

Primary local material:

- BUILDER-ONLY REFERENCE `course-insights/QT301/COMPILER_LESSONS_DISTILLATION.md`
- BUILDER-ONLY REFERENCE `course-insights/QT301`
- BUILDER-ONLY REFERENCE `course-insights/transcripts/QT301`

The compiler distillation combines Scribe transcripts, Gemini orientation passes, a course note, and the course source archive. It is the strongest course-specific implementation guide currently available in the workspace.

### QT401: bounded search, later

Use for:

- search as an intelligent process;
- genetic-program representations;
- primitive-set design;
- brute-force numerical and boolean trees;
- mutation, crossover, warm starts, and elitism;
- multi-objective optimization;
- bloat control and parsimony;
- adding proprietary datasets.

Primary local material:

- BUILDER-ONLY REFERENCE `course-insights/QT401`
- BUILDER-ONLY REFERENCE `course-insights/transcripts/QT401`

QT401 is not the first implementation target. Add broad search only after the compiler, research ledger, complexity controls, multiple-testing controls, and sealed validation boundary work.

### Mechanism-first research context

The Robot James synthesis is separate from QT101 to QT401. It supplies the mechanism-first research discipline used by `EdgeSpec`:

- BUILDER-ONLY REFERENCE `course-insights/robot-james/synthesis/AGENT_CONTEXT.md`
- BUILDER-ONLY REFERENCE `course-insights/robot-james/synthesis/MASTER_SYNTHESIS.md`
- BUILDER-ONLY REFERENCE `course-insights/robot-james/synthesis/EVIDENCE_AUDIT.md`

Use it to ask who is structurally disadvantaged, why the behavior persists, what frictions prevent immediate arbitrage, and what would falsify the explanation. Treat author claims as hypotheses until Edge OS tests them.

The source manifest, BUILDER-ONLY REFERENCE `course-insights/robot-james/SOURCE_MANIFEST.md#archived-thread` now includes the copied Robot James thread PDF. Its participants may willingly or necessarily accept unfavorable prices; a forced or guaranteed loser is not a universal requirement. The [research contracts](EDGE_OS_RESEARCH_CONTRACTS.md) apply this lens without turning an explanation into proof of profitability. Source-derived sample thresholds and multi-year periods are not universal requirements for Monad data.

## 11. Compiler and research prior art

The canonical review is BUILDER-ONLY REFERENCE `docs/research/04_EDGE_OS_COMPILER_PRIOR_ART.md`.

The repositories are available as shallow Git clones under BUILDER-ONLY REFERENCE `references/prior-art/edge-os-compiler-git`.

The prior-art report predates these successful clones and still describes an earlier snapshot directory. Use the `edge-os-compiler-git` clones for local code inspection.

| Repository | Local directory | Primary lesson |
|---|---|---|
| QuantLab | `quantlab` | Nearest prompt-to-typed-strategy compiler, semantic checks, repair, fixtures, and property tests. Replace its always-approximate policy with clarification and rejection. |
| Nano | `nano` | Versioned canonical IR, deterministic interpreter, explicit effects, and host-owned execution. |
| sigc | `sigc` | Compiler front end, source spans, declarations, and parser organization. License remains unresolved. |
| FactorMiner | `factorminer` | Research budgets, candidate lineage, resampling, FDR, and deflated-performance controls. |
| alpha-foundry | `alpha-foundry` | Typed search grammar, complexity limits, deduplication, marginal contribution, and holdout admission. |
| Qlib | `qlib` | Expression registry, cached evaluation, history requirements, and warmup accounting. |
| AlphaGen | `alphagen` | Bounded formula construction and search actions inside a typed expression space. |
| RD-Agent | `rd-agent` | Iterative experiment feedback. Its generated-Python boundary is a counterexample for the Edge OS core. |
| x2strategy | `x2strategy` | Strategy extraction fields and human review. General Python generation remains outside the Edge OS trust boundary. |
| trading-rule-parser | `trading-rule-parser` | Small whitelist DSL, precedence, declarations, and typed sum forms. |
| LEAN | `lean` | One strategy contract across backtest and live engines. It is a reference, not a short-build dependency. |
| Freqtrade | `freqtrade` | Truncated-window lookahead analysis and one strategy interface across modes. GPL limits direct reuse. |
| Backtesting-Agent | `backtesting-agent` | README-described safeguards were not confirmed in the earlier audit. Use only as an unverified counterexample until source inspection proves more. |

JEV Trader is cloned separately at BUILDER-ONLY REFERENCE `references/prior-art/jev-trader`. Use it only as a Kuru execution and proof reference. Its useful patterns are separate read, write, and WebSocket endpoints, dry-run defaults, asynchronous receipts, and venue-event fill detection. Its model prompt and executor disagree about order type, so it is also a direct counterexample for strategy-execution semantic drift.

### Reference stack for the first vertical path

Use these ideas, not entire frameworks:

1. QuantLab recursive schema and evaluation-fixture shape.
2. Nano versioned IR, canonical serialization, effect manifest, and intent-only execution boundary.
3. QT301 parser, evaluator, primitive-registry, and decompiler lessons.
4. sigc or trading-rule-parser source-span and whitelist patterns.
5. Qlib history and warmup declarations.
6. Freqtrade truncated-data lookahead tests.
7. FactorMiner research budgets, lineage, FDR, and deflated-performance controls.
8. alpha-foundry complexity, redundancy, and marginal-contribution gates.
9. LEAN's single strategy boundary as an architectural check, not a dependency.

### Reuse rules

- Inspect licenses before copying code.
- Prefer learning the boundary or test from each repository over importing its framework.
- Record borrowed code and its license in the public repository.
- Preserve the difference between inspected implementation and README claims.
- Keep arbitrary generated Python outside the financial trust boundary.
- Keep LLM and research agents outside execution authority.

## 12. Build invariants

These rules survive every scope reduction:

1. Edge before strategy.
2. Mechanism before mining when evidence permits it.
3. Prompt to typed specification, not prompt to arbitrary executable code.
4. Unsupported meaning produces clarification, unresolved, unsupported, or rejected output.
5. The system may return zero deployable edges.
6. Every search records its budget, lineage, datasets, variants, and holdout access.
7. Historical, paper, and live modes share canonical strategy meaning. Order type, side, size, price or limit semantics, timing, costs, and fill assumptions must agree.
8. Model outputs are proposals or bounded judgments. Deterministic code performs arithmetic, validation, risk, and mandate authorization.
9. Execution adapters receive mandate-scoped intents. Privy applies its independent wallet policy. The host records denials and results.
10. Spot and LP domains share the research and strategy runtime but use domain-specific simulation and action semantics.
11. Costs, liquidity, latency, capacity, and missing information remain visible.
12. A transaction proves execution, not edge validity.
13. A public track record preserves strategy version, evidence, decision, and transaction context.
14. Kuru is the venue truth. Envio supplies history. QuickNode supplies current state and reconciliation. Privy supplies delegated signing. Freeze the broadcast route in the build brief.
15. Social data is optional evidence. It cannot authorize execution.
16. Point-in-time features preserve source time and collection time. Missing historical state stays missing.
17. A primary onchain-only investigation must work without X, Nansen or Tenderly. A different hypothesis that requires an optional input becomes unresolved when that input is missing; changing it creates a recorded declaration.
18. Credentials remain outside model context, browser bundles, logs, and receipts. Execution cannot weaken its own policy.
19. Recover pending actions before new execution. Ambiguous outcomes and changed authority stop new submissions.
20. Revocation does not reverse pending transactions or cancel existing orders. Show remaining exposure until it closes.
21. Research packages preserve evidence, interpretations, contrary findings, timing, budgets and lineage. An agent's confidence cannot promote capital authority.

## 13. Stop conditions

Stop and reframe when any of these becomes true:

- the product explanation requires unrelated features;
- Edge OS is described only as a bot builder, copy trader, dashboard, or backtester;
- the no-thesis path has an unlimited search space;
- the product requires an unofficial X scraper or cannot operate when X is unavailable;
- a historical feature uses information collected after the decision time without an explicit leakage label;
- a model can silently add assumptions or execute funds;
- a strategy can reach capital without a recorded validation decision and deterministic risk pass;
- execution bypasses its approved mandate, Privy policy, or durable recovery checks;
- an accepted order or signer removal is presented as proof of a fill or closed exposure;
- historical and live evaluators interpret the specification differently;
- LP support becomes a separate platform rather than a second adapter and simulator;
- the Monad layer stores a claim only after the useful work is complete;
- the prototype cannot show a useful rejected result;
- frontend progress is being used to hide a missing core prototype;
- the project cannot be explained and demonstrated inside the official limits.

## 14. Session contract

Every fresh design or implementation session must:

1. For team implementation, work inside the assigned `edge-os` clone or worktree. Builder research and throwaway probes use the separately approved private workspace boundary; teammates need no access to that workspace.
2. Read the repository's `AGENTS.md`, assigned issue and required sections of this workflow.
3. Read the Compass sections required for the current stage.
4. Read only the shared product documents and evidence supplied for the assigned task. The builder may consult authorized private research, course and prior-art sources. Missing teammate inputs must be supplied as verified extracts or fixtures before dependent work proceeds.
5. State the current Compass phase, assigned artifact, write boundary, and completion gate before changing files.
6. Preserve verified facts, direct evidence, inferences, hypotheses, and unknowns as separate categories.
7. Stop after its assigned artifact or implementation gate passes.
8. Update this document's current state only when the builder approves the stage result.

Do not revive Funnel phase gates, candidate ranking, or product selection. Edge OS is selected. The current job is to frame it, challenge it, prototype its dangerous claim, and finish the smallest complete product.

## 15. Current next action

Review the [draft build brief](EDGE_OS_BUILD_BRIEF.md) and reconciled specification. Approve, revise or narrow the release scope, with a separate decision on bounded frontend closure. Then resolve the first slice's technical choices and publish accepted contracts/fixtures before dependent tickets. Include the small runtime-verification setup with the first runnable path. The v0.12.2 repairs are complete within their source/state checks; no broad UI repair or new grilling session is pending. This replaces older instructions to dispatch that repair.

Probe A is accepted and closed for the revised bounded research-process claim. Carry forward [the acceptance and limits](prototypes/EDGE_OS_PROBE_A_RESULT.md#builder-acceptance-and-closure-2026-10-03). The [focused core product choices](#post-probe-a-focused-decision-session) are complete through Q31 with explicit qualification gaps. Carry forward accepted research and live journeys, input/language/calculation policies and outcome/control definitions. The 2026-10-05 [separate-agent-wallet amendment](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding) supersedes pooled cross-agent funds and authority. Preserve multiple positions, cumulative allowances, inventory attribution, queues, renewal and weighted cost within each agent wallet. Funding, withdrawal, ownership and signer isolation remain unqualified runtime requirements. Focused grilling is closed; no broad interview is needed for the accepted amendment. The frontend is built at v0.12.2; the wallet-flow and controller repairs pass scoped checks, while human comprehension and explicit bounded closure remain pending. Use the [updated prototype scopes and approval checklist](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#remaining-approval-and-qualification-checklist). Probe B execution approval remains separate. The initial preapproved inventory-based permission direction is selected; enforcement/capacity and factual tests remain open. Another approver or authority architecture requires alternatives and a builder decision before adoption. Live trial/ongoing choice and absence of compulsory graduation are recorded requirements, not questions to reopen. Research/UI implementation need not wait for every execution gate once its own design/build brief and task are approved. No profitable strategy was established or required for this process closure.

Do not repeat passed 1A/1B, open the MOE holdout or extend the closed investigation merely to obtain a survivor. Original delivery/finality and omitted execution effects remain unresolved. Probe B is unstarted and requires its own configuration and permissions. This update records acceptance and design rules; it authorizes no new experiment, implementation, publishing or financial action.

Review:

`docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md`

The revised draft records Privy delegation, mandate limits, persistent recovery, independent policy denial, and revocation with pending exposure. It preserves the Kuru, QuickNode, and Envio boundaries and the JEV Trader semantic-drift test. The Privy research note records Assensus's completed narrow proof and its limits. Monad–Kuru delegated execution remains unproved.

Review `docs/EDGE_OS_RESEARCH_CONTRACTS.md` with the design. The full production contracts are not implemented; the report identifies the tested interpretation, compilation and reconstructed evidence-preservation subset. `NANSEN-Q01` remains `NOT_STARTED`; its coverage/access approval is separate and does not block the current onchain-only decision session.

The full design still needs `APPROVE`, `REVISE`, or `NARROW`, or explicit approval of a narrower production slice. Preserve unknown demand and the missing independent user/teammate challenge. Use Wayfinder only for dependent choices that cannot fit one session. Record bounded frontend closure separately without inventing participant passes. Approve the relevant design/build scope before ready tickets. Research/UI implementation may start after those approvals without claiming delegated execution is proved; Probe B gates that claim separately.

The builder authorized the documentation revisions and replacement Compass session prompt on 2026-09-30. Those authorizations do not approve the complete design, advance a Compass stage or run a prototype.

### Historical setup record

On 2026-10-02, the builder authorized synchronizing the spec, this workflow and controller handoff and creating the shared probe plan. At that point both probes were `NOT_STARTED`; that setup update approved no experiment, paid access, financial execution, phase completion or optional-token activation.

The same day's controller follow-up revised Probe A for an actual bounded Hermes investigator and a separate data qualification preflight. Direct inspection resolved the named S15/S16 compiler-source questions, not runtime correctness or course-wide parity. At that planning checkpoint, Hermes isolation, usage/cost qualification and historical market data remained unproved, and experiment approvals were pending. Later approvals and executed findings are recorded in the scoped plan and result report; those records supersede this historical setup status.
