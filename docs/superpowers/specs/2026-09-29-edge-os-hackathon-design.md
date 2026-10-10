# Edge OS hackathon design

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](../../agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Status: `PRODUCT SCOPE APPROVED; TO-SPEC HANDOFF; DEPENDENT TECHNICAL CHOICES OPEN`

Date: 2026-09-29, Africa/Kinshasa

Last updated: 2026-10-06, Africa/Kinshasa

Approval record, 2026-10-05: the builder stated, "okay I approve the spec, run to-spec" and requested a detailed synthesis of the relevant workspace sources. This accepts the recorded product scope and authorizes this specification handoff. It does not resolve the named technical choices, approve implementation dispatch, pass an unrun check, or authorize spending or financial execution. Earlier statements that full product-scope approval is pending are historical. Explicitly proposed extensions and unresolved engineering choices remain proposed.

Memory approval, 2026-10-06: the builder accepted the [thin per-agent memory contract](#accepted-thin-per-agent-memory-contract) below. This refines the existing persistent-agent and contextual-conversation requirements. Storage encoding and runtime qualification remain open; no implementation, ticket publication or financial action is authorized by this approval.

Revision scope: preserve the accepted research/live decisions through Q31, separate agent wallets, v0.12.2 interaction requirements and the research-first build order with agent deployment in the intended release. Add user stories, testing boundaries, source adaptations and dependency coverage for ticket decomposition. Existing numbered sections retain their anchors and detailed requirements. Probe A remains closed at its bounded claim. Probe B and Nansen qualification remain unstarted. The complete Compass gates and participant checks do not pass through document approval.

2026-10-03 research/live amendment, clarified by the builder: document broader observational research and one live-trading workflow with optional trial settings. Users may start ongoing live operation directly or continue after a trial, without compulsory graduation, favorable backtests or paper trading. Evidence status, operating purpose and execution permissions remain separate. Exact execution configuration and financial permission remain pending; no capability or live action is proved or activated by this amendment.

2026-10-02 amendment: name the optional Hermes research and Jev assessment roles while keeping their contracts independent of the selected runtime or model. This amendment does not adopt either dependency, start implementation or change execution authority.

Historical setup record, 2026-10-02 scoped-probe amendment: proposed separate research/compiler/rejection and Monad–Kuru delegation probes before final production planning. At that setup point both probes were `NOT_STARTED` and awaited their own approved boundaries. Later approvals and execution supersede that status; consult [the shared probe plan](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md) and [result report](../../prototypes/EDGE_OS_PROBE_A_RESULT.md) for current findings. The two-domain product, full acceptance checks and execution-authority limits remain unchanged.

Build-handoff consolidation, 2026-10-05: the [first-release brief](../../EDGE_OS_BUILD_BRIEF.md) explains build order and component responsibilities. This specification owns accepted behavior. Later accepted decisions supersede the original idea/synthesis's compulsory validation-to-live sequence and former shared-wallet direction. The wider research, backtesting, execution and LP commitments remain visible. The current synthesis adds no profitable result, provider guarantee or new financial approval.

## Accepted hackathon release subset, 2026-10-10

The builder approved the [release-cut record](../../planning/EDGE_OS_RELEASE_CUT_2026-10-10.md). That record controls this submission's deliverables, staged dependencies and deferrals. The wider specification remains the product direction. All safety requirements applicable to an included operation remain binding. A controlled qualification fixture does not enable general entries, continuing operation, exits or withdrawal. Missing qualification remains unresolved.

## Problem Statement

A Monad trader can recognize a possible pattern without knowing how to investigate it. Moving between charts, social feeds, notebooks and trading tools loses the original question, contrary evidence and trading restrictions. A generated rule can look precise while changing the user's meaning. A historical gain can hide missing costs, repeated trials or information unavailable at the decision time.

When the user delegates trading, the user also needs to know which agent owns each position, which wallet funds it and what permission remains. A chat response alone cannot establish that a purchase, sale, withdrawal or stop took effect.

The detailed user, job and evidence limits are in [section 3](#3-complete-idea-card). Broader demand remains unvalidated.

## Solution

Edge OS preserves the question, clarifies missing meaning, proposes a bounded investigation and saves an inspectable result. It shows supporting and contrary findings even when no strategy survives. Supported rules can become an immutable strategy revision, an optional historical trading simulation and a separately authorized trading agent.

Each trading agent uses its own user-owned wallet. The user can inspect Research, Agents, Positions and Funds directly or ask contextual questions about the same records. Funding, evidence and trading permission remain independent. A user can choose a live trial or ongoing operation without a favorable backtest, but only qualified execution with explicit bounded permission may trade.

The intended release includes the spot research path, narrow simulator, persistent agent operation and a small approved read-only add-on catalog. The LP research/compile/simulate path is the second domain proof. Build research first. Do not silently remove the later commitments to call the full product complete. [Section 5](#5-product-scope) and the brief retain conditional extensions and exclusions.

## User Stories

Story numbers are stable handoff references, not implementation tickets. Each story inherits the detailed requirements linked by the coverage table. The table distinguishes core behavior, conditional capabilities and their blockers.

### Intake and interpretation

1. As a trader, I want to start with a clear thesis, rough hunch or bounded market question, so that I can investigate without writing technical rules.
2. As a trader, I want my original request and restrictions preserved, so that I can compare the interpretation with what I asked.
3. As a trader, I want questions only about meaning needed now, so that I do not complete an unnecessary technical questionnaire.
4. As a trader, I want supplied facts, agent suggestions and unknown fields distinguished, so that I can spot assumptions before adopting them.
5. As a trader, I want to correct an answer without losing earlier restrictions, so that clarification changes only the intended meaning.
6. As a trader, I want conflicting answers identified, so that the system does not silently choose between them.
7. As a trader, I want unsupported parts of my request retained and explained, so that an easier substitute does not misrepresent my idea.
8. As a trader, I want a malformed model response identified as a system failure, so that it does not falsely label my idea unsupported.
9. As a trader, I want to adopt suggested research settings visibly, so that the agent can help without inventing my consent.
10. As a trader, I want an exploration request to remain unresolved without an invented signal, so that no winner is manufactured.

### Bounded research and evidence

11. As a trader, I want to review the market, question, variants, horizons and resource budget before investigation, so that the scope is clear.
12. As a trader, I want the research pool distinguished from the possible execution route, so that a market label does not imply trading availability.
13. As a trader, I want missing data and uncertain historical timing disclosed, so that reconstructed history is not presented as observed availability.
14. As a trader, I want the agent to gather evidence through approved tools, so that findings have inspectable sources and access limits.
15. As a trader, I want each proposed and attempted variant recorded, so that unsuccessful trials cannot disappear from the result.
16. As a trader, I want observations, interpretations and contrary findings separated, so that a plausible explanation does not become a fact.
17. As a trader, I want identical outcome clocks for triggered and control observations, so that their comparison answers the declared question.
18. As a trader, I want missing and ineligible observations retained with reasons, so that the reported sample does not hide exclusions.
19. As a trader, I want later validation and protected holdout use recorded, so that unseen data does not quietly become another search set.
20. As a trader, I want descriptive results when formal statistical support is unavailable, so that useful research can finish honestly.
21. As a trader, I want a clear completed report with reasons and next actions, so that an unresolved finding remains useful.
22. As a trader, I want to save and reopen the report with its exact inputs and evidence, so that I can inspect the same investigation later.
23. As a trader, I want a stopped or failed investigation to preserve completed work and usage, so that I can decide how to continue.
24. As a trader, I want unavailable creator, wallet-history or social tools named, so that a broader research request is not fabricated from price data.

### Rules and strategy identity

25. As a trader, I want a plain-language rule summary beside exact supported rules, so that I can review what the strategy means.
26. As a trader, I want price and executed quote volume combined through supported typed operations, so that units and comparisons remain consistent.
27. As a trader, I want lookbacks, timing, warm-up and missing-data behavior explicit, so that a signal uses only the information allowed at that time.
28. As a trader, I want invalid types, unsupported operations and resource excess rejected, so that generated rules cannot bypass validation.
29. As a trader, I want incomplete drafts saved separately from compiled revisions, so that saving work does not imply readiness.
30. As a trader, I want evidence and permission bound to the exact immutable strategy revision, so that an edit cannot change an authorized strategy silently.
31. As a trader, I want concurrent publications to return their own revision identities, so that the system does not deploy whichever edit became latest.
32. As a trader, I want changes to calculation semantics to change strategy identity, so that old results are not reused for different behavior.

### Optional historical trading simulation

33. As a trader, I want an optional Test on past prices action for sufficiently specified supported rules, so that I can inspect simulated trading consequences.
34. As a trader, I want to review the period, starting capital, trade size and cost assumptions, so that the test uses settings I adopted.
35. As a trader, I want simulated trades, cash and holdings derived from the same saved revision, so that the account result corresponds to the rules.
36. As a trader, I want gains or losses, trade count, account value and drawdown, so that I can inspect both returns and adverse movement.
37. As a trader, I want assumed fills and omitted execution effects visible, so that I do not mistake simulated profit for attainable profit.
38. As a trader, I want unavailable tests to explain the missing data or behavior and preserve my work, so that I have a useful next action.
39. As a trader, I want saved simulation settings, results and trades retrievable, so that I can review or deliberately revise the test.
40. As a trader, I want an unfavorable or unavailable backtest kept visible without compulsory graduation, so that I can separately review qualified live operation.

### Agents, wallets and funding

41. As a user, I want authenticated access to only my records, so that knowing another record ID grants no access.
42. As a trader, I want each trading agent assigned its own user-owned wallet, so that agents cannot spend each other's funds or holdings.
43. As a trader, I want wallet setup to resume after cancellation or an uncertain result, so that retrying does not create unexplained duplicate wallets.
44. As a trader, I want to fund a named agent from my connected personal wallet, so that the receiving wallet and asset are clear.
45. As a trader, I want trading assets, native gas and research usage separated, so that funding one does not appear to fund the others.
46. As a trader, I want a transfer review showing sender, recipient, network, amount and fees, so that I can check the proposed movement.
47. As a trader, I want pending transfers distinguished from spendable balances, so that unknown outcomes do not create available money.
48. As a trader, I want a top-up to leave strategy permission and stopped state unchanged, so that depositing money does not start trading.
49. As a trader, I want to withdraw only reconciled unreserved assets through the reviewed owner path, so that withdrawals do not double-use pending commitments.
50. As a trader, I want owner access retained after agent permission removal, so that removing delegation does not strand my funds.
51. As a trader, I want insufficient asset or gas funds explained, so that the system does not silently bridge, wrap, borrow or expand access.
52. As a trader, I want a combined account overview with separate wallet balances, so that aggregation does not imply pooled spending authority.

### Activation and persistent operation

53. As a trader, I want to select the exact agent and strategy for activation, so that permission does not extend to an unselected agent.
54. As a trader, I want the strategy, wallet, limits, expiry and stop behavior visible together before approval, so that I know what can happen with real money.
55. As a trader, I want direct ongoing operation or an optional live trial, so that a trial is a chosen learning configuration rather than a required stage.
56. As a trader, I want routine permitted actions to run while I am offline, so that operation does not depend on an open chat or repeated signatures.
57. As a trader, I want deterministic checks and the restricted signer to reject unauthorized actions, so that a model cannot grant itself authority.
58. As a trader, I want several positions within an agent wallet, so that the product does not impose a one-position account model.
59. As a trader, I want additions and partial exits attributed to their positions, so that available inventory and costs remain correct.
60. As a trader, I want capital, inventory, gas and action allowances reserved before submission, so that competing actions cannot use the same capacity.
61. As a trader, I want pending or unknown swaps reconciled before another conflicting action, so that an uncertain response does not cause a duplicate trade.
62. As a trader, I want one wallet's unresolved action isolated from other wallets, so that an agent cannot block or borrow another agent's resources by default.
63. As a trader, I want the same original submitted action recovered after a restart, so that recovery does not silently substitute a fresh trade.
64. As a trader, I want actual inputs, received assets, attempts and gas reconciled, so that failed or reverted swaps have honest accounting.

### Account inspection and control

65. As a trader, I want to open Agents, Positions or Funds directly, so that I can inspect the account without talking to an agent first.
66. As a trader, I want positions filtered by agent, wallet and asset, so that identical tokens in different wallets remain distinguishable.
67. As a trader, I want contextual conversation to use the same records and update times as direct views, so that the two channels do not disagree silently.
68. As a trader, I want an ambiguous sell request to ask which position I mean, so that the system cannot choose another agent's holdings.
69. As a trader, I want the exact target and amount in a shared action preview, so that chat and direct controls cannot create different actions from one approval.
70. As a trader, I want submitted sales and confirmed holdings shown separately, so that requesting a sale does not look like a completed sale.
71. As a trader, I want to stop one agent before its first trade, so that another active agent can keep running.
72. As a trader, I want stopping new entries, stopping all swaps, selling and removing permission explained separately, so that I understand what happens to remaining holdings.
73. As a trader, I want pending transactions and residual assets visible after removal, so that revocation does not imply an onchain action was undone.
74. As a trader, I want realized results, estimated unrealized results, deposits and withdrawals separated, so that account funding is not counted as profit.
75. As a trader, I want closed positions and failed actions retained in history, so that current holdings do not erase earlier activity.
76. As a trader, I want temporary-fault recovery only after data, accounting and authority checks pass, so that recovery does not clear deliberate stops.
77. As a trader, I want continuation under existing permission to retain consumption, reservations and losses, so that changing purpose does not reset accounting.
78. As a trader, I want time extensions, increased ceilings and changed strategy rules reviewed as distinct changes, so that one button cannot hide extra authority.
79. As a trader, I want a usable narrow layout, labeled controls and predictable keyboard focus, so that I can inspect and control the account without a desktop mouse.
80. As a new user, I want the result and current primary action first, so that internal test controls and technical explanations do not obscure the task.

### Add-ons, second proof and build verification

81. As a trader, I want to enable qualified instruction skills and approved read-only connections per agent, so that I can choose supported research help.
82. As a trader, I want add-on capability, version, access and usage costs disclosed, so that enabling a tool does not imply new trading permission.
83. As a trader, I want disabling an add-on to remove future access without rewriting financial history, so that tool control and wallet control remain distinct.
84. As an LP researcher, I want one bounded pool-specific fee, inventory and cost investigation, so that I can compare liquidity provision with its declared alternative.
85. As an LP researcher, I want a separate LP compile-and-simulate result with limitations, so that spot calculations are not passed off as LP evidence.
86. As a builder, I want a demo that includes actual qualified agent deployment and recorded operation, so that fictional account screens do not stand in for execution.
87. As a maintainer, I want a fresh agent to run the accepted path and inspect saved records from portable fixtures, so that verification does not depend on the controller's private machine.
88. As a maintainer, I want model failures retained in a regression set with usage and completion evidence, so that a few passing probe cases do not become a general reliability claim.

## Implementation Decisions

These are behavioral boundaries. They do not select an unapproved framework, database, queue package, API route name or deployment address. Existing detailed sections own field meanings.

### Accepted application stack

Builder decision, 2026-10-06, for proposed P01: Python/FastAPI backend, PostgreSQL durable application storage, Next.js frontend and Privy user authentication. [ADR 0008](../../adr/0008-python-api-postgresql-nextjs-privy-auth.md) records the boundary and trade-offs. This resolves the framework/database/auth-provider choices, not every P01 detail or implementation readiness.

The frontend uses the approved design's tokens and components. CSS and Tailwind are both permitted; retain compatible exported CSS and use Tailwind where it reduces implementation work. Do not substitute a component kit's default appearance for the approved design. Pin compatible dependency/runtime versions in the actual implementation.

FastAPI verifies Privy authentication before deriving the requesting user from signed claims. Validate the signature, adopted algorithm/key handling, issuer, app audience, expiration and required subject; reject missing, invalid or misbound tokens and another user's record access. Determine the actual verification-key/rotation and token-delivery mechanism using current official Privy docs through Context7 and Exa. Authentication is separate from wallet creation, funding, restricted signer delegation and trading permission. Client-supplied identity or a connected wallet cannot bypass application ownership.

P01 still supplies startup/configuration, database access and migrations, the authenticated ownership boundary, isolated test data/cleanup, version choices and the first local runnable profile. Hosting and the persistent worker's production lifecycle need explicit handoffs before deployment; no cloud vendor, ORM, queue framework or paid service is selected here. Relevant TX Odds/OKX sources are comparison inputs, not code or authorization to copy wholesale. Teammates receive portable required inputs before dispatch.

### Accepted research declaration and agent monitoring handoff

Builder approval, 2026-10-06: make these existing research, persistent-deployment and monitoring requirements explicit in the proposed tickets. This approves the focused requirements below, not the whole ticket graph, implementation, publication or financial actions. All new acceptance checks remain unrun.

Before an evaluation reads its outcome labels, save the candidate `EdgeSpec` revision, claim and falsification criteria, adopted budget, declared trial identities and evaluation configuration in the research records. The configuration identifies variants, direction, horizon, comparisons, data partitions and permitted access. Bind each attempt and result to those saved identities. Reject an unregistered trial or an attempt to overwrite the declaration after outcomes. A revised candidate has new lineage and retains its prior access history; previously inspected data cannot become unseen evidence. Observational exploration may still produce descriptive findings, with its actual access order visible. It cannot retrospectively present a discovered pattern as a prediction declared beforehand.

A persistent trading worker evaluates the approved `StrategySpec` revision on its declared decision schedule using qualified available inputs and the compiler's semantics. Persist the decision time, input and semantic identities, signal/no-signal/ineligible result and reason before admitting a `TradeIntent`. A no-signal decision is useful work, not a failed trade. Missing, stale or insufficient history preserves the applicable reason and prevents affected action. Restart must retain decisions and reconcile unresolved actions before new submission. Replaying a decision cannot create a duplicate economic action. Models and memory cannot silently change the adopted rules, schedule or authority.

Direct agent views and contextual answers use the same records to distinguish:

- **Worker health:** last attempted and completed evaluation, latest input/update time, next scheduled work or waiting/stopped/fault reason, and pending reconciliation. Show timestamps and deployment/revision scope. A process label or heartbeat alone does not prove strategy evaluation or submission.
- **Trading results:** per-agent realized results, separately dated unrealized estimates, qualified costs and separately identified deposits/withdrawals. Aggregate reconciled attributable positions and receipts. Unknown marks, costs, conversions and transaction outcomes remain unknown; they cannot become zero or proven profit. Native gas remains separately recorded unless conversion into the reported unit is qualified.
- **Edge evidence:** revision-linked historical and forward findings, attempted comparisons, contrary results and unresolved assumptions. Positive account results alone do not establish a repeatable edge, and evidence status cannot grant or remove financial permission by itself.

Before displaying a new return, account-value or drawdown metric, adopt a versioned calculation profile. Define the reporting unit and period, cost and valuation inputs, treatment of external cash flows, sampling and high-water-mark rules where applicable, and missing-data behavior. Retain small independently calculated examples and the exact profile identity with results. A supported raw gain/loss display need not wait for an additional percentage-return metric. These requirements do not select an annualization or cash-flow-adjustment convention.

Required worker inputs are task-specific and portable under the [implementation reference map](../../research/EDGE_OS_IMPLEMENTATION_REFERENCE_MAP.md). P02/P06 supply the selected compiler requirements, source/version provenance, adaptation exclusions and independently authored applicable fixtures before dependent consumers start. Private course archives and unrelated project folders are not mandatory teammate inputs. The controller checks rights and provides permitted extracts in the clone or issue; links to unavailable private originals alone cannot satisfy readiness.

### Modules and interfaces

| Boundary | Receives | Produces and preserves | May not do |
|---|---|---|---|
| Application and ownership | Authenticated owner, scoped request, explicit record identity | Authorized reads/writes, progress, saved artifacts and action previews | Trust a caller-supplied owner/agent ID as authorization |
| Intake and clarification | Original text, restrictions, previous answers, supported capabilities | Versioned `PromptInterpretation`, field origins, questions or structured failure | Invent consequential settings or salvage a plausible fragment from invalid whole output |
| Research coordinator and Hermes | Adopted question, `ResearchBudget`, approved evidence tools | `ResearchLedger`, proposed `EdgeSpec`, `ResearchEvidencePackage`, usage and completion record | Grade its own quantitative claims, access signer secrets or submit financial actions |
| Data gateway | Exact market identity, feature requirements, time and coverage constraints | Source-qualified observations, availability information and explicit missing reasons | Treat pool coverage as route qualification or substitute essential data silently |
| Compiler and revision publication | Adopted typed rules and locked semantic dependencies | Validated immutable `StrategySpec` identity or field-specific rejection | Convert saved drafts into validated strategies or bind callers to mutable latest state |
| Effect evaluator and validation | Exact dataset, rules, declared comparisons and time partitions | Reproducible evaluations and claim-specific `ValidationDecision` | Select undeclared trials after results or claim formal support with an unqualified method |
| Spot simulator | Exact revision, dataset, capital, sizing, timing and cost assumptions | Saved simulated trades, cash, holdings, account values and metrics | Treat price association, prototype fixtures or assumed fills as real execution |
| Deployment scheduler and account ledger | Exact revision, agent wallet, current mandate, qualified state | Durable decisions, reservations, intents, stops and reconciled account records | Keep financial truth only in a chat, reset accounting on restart or use another wallet's assets |
| Execution service and adapter | Admitted `TradeIntent`, current policy binding and restricted credential | Persisted attempt and transaction/receipt lineage, reconciled outcome | Weaken policy, silently replace a transaction or assume a provider timeout means no broadcast |
| Direct UI and contextual conversation | Same owner-scoped records and action contract | Consistent displays, exact previews, saved-result links and status | Create separate financial truth or hide consequential settings in expandable details |
| Approved add-ons | Per-agent selection, manifest, scoped tool access | Versioned instructions and qualified read-only research/account results | Upload executable packages, accept arbitrary MCP endpoints or acquire wallet authority |
| LP proof | Declared pool model, LP rules, qualified fee/inventory history and comparison | Domain-specific compilation, simulation and evidence | Use the spot simulator or grant live LP permission |

### Records and durable identity

Use the definitions in [section 7](#7-core-product-objects) and the [research contracts](../../EDGE_OS_RESEARCH_CONTRACTS.md). Preserve these relationships:

- `PromptInterpretation` links the original request, field evidence, clarification answers and adopted configuration.
- `ResearchBudget` bounds one declared investigation. `ResearchLedger` records all its proposals, attempts, evaluations and usage, including failures.
- `EdgeSpec` proposes an opportunity. `ResearchEvidencePackage` supports or challenges its claims. Neither is execution permission.
- `StrategySpec` defines immutable supported rules. Its semantic identity includes the dependencies that determine meaning, not only expression text.
- `ValidationDecision` names the claim, exact revision, dataset, evaluation configuration and limitations. It does not authorize capital.
- `ExecutionMandate` binds the exact revision, owner, agent wallet, allowed actions, limits and expiry. Its policy binding must be verified.
- A durable deployment owns state and references. Each `TradeIntent`, reservation, attempt, transaction and receipt retains exact agent/wallet/position lineage.
- Funding and withdrawal records remain distinct from trade results. Saved simulation records remain distinct from both.

Schema encoding remains open; PostgreSQL is the selected database under the accepted application stack. Required relationships and ownership checks remain authoritative. Ticket authors must freeze versioned machine contracts before parallel consumers implement them. Do not copy the frontend's in-memory representation into the production schema as an assumed decision.

### State, timing and authority

Use [ADR 0002](../../adr/0002-separate-evidence-and-financial-authority.md) for independent evidence, readiness and permission. Use [ADR 0007](../../adr/0007-separate-user-owned-agent-wallets.md) for separate wallets. [ADR 0003](../../adr/0003-durable-shared-wallet-accounting.md) retains cumulative accounting only within each agent wallet.

The accepted operator registry, five-minute schedule, decimal arithmetic, three-valued conditions and missing-data rules remain in [section 10](#10-first-research-family). The initial production compiler is broader than Probe A's fixed templates. Its extra operations require tests before use. Course sampling ranges are not production resource limits.

Hermes is the investigated integration direction for bounded interpretation and research. Production must pin and qualify the runtime and provider route. Hosting choices must prevent cross-user access to memory, files, tools and credentials. A fresh conversation ID alone cannot establish that boundary. The persistent trading worker schedules approved computations and stores state outside model memory. Jev remains optional and cannot change authority or replace deterministic calculations.

The spot adapter starts with fixed-input Kuru Flow swaps. Exact route, network, ABI, transport, inventory-based exit enforcement and independent policy denial remain qualification dependencies. One successful swap does not qualify every position, withdrawal or recovery path. Preserve [section 12](#12-authorization-and-risk-design) and the named wallet checks when decomposing work.

### Narrow simulator contract

The simulator must replay one supported saved strategy over a fixed qualified historical dataset without future information. Review and persist capital, trade size, entry/exit timing, data availability and cost assumptions before the run. Reuse the compiler's meaning and units. Keep the simulated execution model separate from the live adapter.

Each run records scheduled decisions, ineligible opportunities, proposed and simulated fills, fees, cash, holdings and marks. Deterministic ordering must settle coincident actions and capital reservations before results are presented. The simulation ticket must freeze that ordering and the fill/mark model. No same-bar fill, interpolation, daily annualization or hidden carry-forward rule is adopted here.

Return simulated gain/loss, trade count, account-value series, drawdown, a trade list and explicit limitations. Missing costs or marks must not become zero or verified profit. Deposits are not returns. Multiple-position and addition support must match the selected simulation scope. An unsupported rule combination receives a specific unavailable-test result, not a partial simulation presented as full coverage. The backend ticket must name its supported subset and obtain approval for any release reduction.

The frontend's past-price interaction tests navigation and meaning only. It supplies no calculated performance evidence. Preserve the actual MOE investigation without attaching a fictional profitable simulation.

## Testing Decisions

The proposed highest practical test boundary is the authenticated application request through persisted records and retrieval. A browser check verifies that the UI reads and acts on those same records. The controller asked the builder to confirm this boundary during synthesis. No reply has been recorded yet, so seam confirmation remains open.

Use focused pure calculation/compiler tests where the application boundary cannot expose numerical edge cases precisely. Qualify real model/provider behavior and wallet enforcement separately under explicit budgets and authority. A mocked signer cannot prove independent denial or revocation.

### Observable acceptance and story coverage

Every implementation ticket must select story IDs and applicable checks from this table. Rows define verification families, not mandatory service boundaries or a preapproved ticket graph.

| Stories | Required observable result and failures | Detailed contract | Dependency before affected implementation or claim |
|---|---|---|---|
| 1–10 | Reopen preserved input and clarification revisions. Distinguish supplied facts, unknowns, conflicts, unsupported capabilities and invalid output. Reject truncation, multiple objects and changed known meaning. | Intake classification and field evidence; retained 1B cases | Versioned input/output contract and pinned route for live evaluations |
| 11–24 | Adopt budget, qualify dataset, retain all variants and exclusions, then save and retrieve a useful unresolved report. Reject future information and undeclared validation access. | Research contracts, effect/control rules, Probe A | Production data/run contract. STAT-Q01 only before formal support claims |
| 25–32 | Compile and canonically reload valid rules. Reject type/unit/history defects, hidden invalid branches and invalid parameters. Concurrent publish results retain exact identity. | Operator registry, calculation fixtures, ADRs 0001/0004 | Canonical encoding, semantic manifest and measured resource limits |
| 33–40 | Independently calculate a small trade/account example. Reconcile cash, quantities, costs and drawdown. Test missing marks, capital competition, unavailable behavior and saved-result retrieval. | Narrow simulator contract and brief section 5 | Adopted replay order, fill/mark/cost model and supported subset |
| 41–43 | Reject another owner's read, stream, resume, cancel and mutation requests. Retry uncertain wallet creation without assuming a new wallet is needed. | Ownership and per-agent wallet contract | Authentication, durable store and qualified wallet lifecycle |
| 44–52 | Show exact transfer preview. Pending money is unavailable. Top-up changes neither permission nor stops. Withdrawal cannot use another wallet's or reserved funds. | Wallet funding/withdrawal and WAL checks | Real funding/withdrawal transport, owner access, gas and balance qualification |
| 53–57 | Activate only the selected exact revision/wallet after reviewed terms. Deny stale/mismatched policy and excess authority independently. Run a permitted action offline. | Execution mandate, ADRs 0002/0005/0006/0007 | Probe B and affected policy/route qualification, explicit transaction approval |
| 58–64 | Competing positions cannot double-reserve funds or inventory. Unknown submissions keep reservations. Restart reconciles original intent; revert counts attempt and gas correctly. | Applicable WAL-Q01–26, EXIT-CAP-Q01, Q31 | Durable ledger, queue, attributable inventory and transport semantics |
| 65–70 | Direct filters and chat resolve the same position/action. Ambiguity asks for clarification. A's sale status cannot appear as B's position status. | Account-view/conversation contract, frontend regressions | Shared authenticated records and action contract |
| 71–78 | Stop A before its first trade while B remains active. Test entry-only versus all-swap stops, removal with pending transactions, continuation and explicit renewal deltas. | Stop/recovery/renewal rules and frontend regressions | Current authority and reconciled per-wallet accounting |
| 79–80 | Current task and primary action are understandable. Keyboard focus, labeled controls and narrow layouts work. Record participant answers before explanations. | Accepted frontend requirements and findings | Real interface, browser/accessibility checks and participant availability |
| 81–83 | Enabled entries have qualified tools and versioned manifests. Cross-user access and arbitrary endpoints fail. Disabling access preserves financial records and existing mandate meaning. | Accepted add-ons catalog | Tool contracts and qualified runtime isolation |
| 84–85 | LP fees, inventory, costs and declared comparison reconcile under a named pool model. Spot adapters reject LP actions. | LP proof, section 15 | Bounded LP model and data qualification. No live LP authorization |
| 86–88 | Fresh setup runs the complete path and exposes actual saved evidence. Demo distinguishes real research, authored examples and real operation. New model failures join regression coverage. | Demo, brief verification section, retained probes | Accepted implementation and separately authorized live evidence |

### Test quality and reusable verification

Test observable meaning, ownership, balances, state transitions and saved identities. Do not make tests depend on private helper names, exact HTML structure or a single model's wording. Use distinguishing inputs around strict comparisons, timing boundaries, decimal thresholds, ambiguous owners and missing data. A serialization match alone cannot establish meaning.

The first runnable production slice must include exercised instructions and portable fixtures for a fresh agent to start an isolated instance, send a request, answer clarification, save a supported result, reopen it and inspect the saved records. Include one rejected or unresolved path and cross-owner denial. Cleanup must remove only the test state it created. Required missing fixtures fail explicitly rather than silently skipping.

Retain a small model regression set for concrete thesis, loose intuition, bounded no-thesis, unsupported extension and follow-up. Add paraphrases and meaning-changing variations. Record format validity, meaning preservation, useful clarification, completion, compiler compatibility, latency and usage separately. A retry or repair is a new recorded attempt, not a replacement for the failure. Numeric budgets and provider limits require task-level approval.

Use General Review Protocol for evidenced defects and Impeccable for the implemented interaction. Runtime verification, independent review and human comprehension answer different questions. Record unperformed physical-phone, screen-reader and full keyboard checks. Neither a critique score nor the prototype's assertions proves production wallet isolation.

### Prior art and evidence boundary

Probe A provides retained bounded interpretation, compiler and reconstructed research cases. Frontend v0.12.2 provides scripted interaction regressions. These are starting cases to adapt into portable tests, not already passing production tests. The proposed compiler, WAL and STAT checks retain their current unrun status.

| Reference | Lesson carried into this spec | Limit |
|---|---|---|
| QT101 portfolio material and QT201 portfolio companion code | Separate signals, sizing, holdings, cash and account results. Verify quantities with small worked cases. | Daily timing, 253-day scaling, filled missing prices and leveraged portfolio sizing are not adopted for Monad spot. |
| QT201 selection/permutation material | Preserve all trials and account for selecting attractive results. Separate descriptive output from formal support. | Course permutation/family-test code does not qualify the selected STAT-Q01 bootstrap/Holm procedure. |
| QT301 compiler distillation, verified S15 calculations and S16 typing | Explicit units, operator signatures, history requirements, canonical meaning and complete input rejection. | Sampling typed expressions does not validate arbitrary user/model expressions. Corrected windows do not prove production timing. |
| QT401 typed generation and search code | Preserve type constraints and resource limits independently of generation. | Broad genetic search, mutation and portfolio optimization remain outside the first build. |
| Keel/GT inspected source | Lock semantic dependencies, separate draft save from publication, consume returned revision identity and record uncertain tool outcomes. | Client code does not prove hosted evaluation or financial enforcement. |
| Agno/semantic-parsing source assessment and 1B failures | Keep schema and validator aligned; measure output validity and meaning separately. | No framework migration, parser-model repair loop or provider guarantee is adopted. |
| Competitor UX and v0.12.2 | Direct records plus contextual conversation, clear wallet ownership, task-led display and separate usage/funds. | No competitor transaction or comparative first-user usability was established. |
| Matt workflow and qualified Poteto/pstack lessons | Accepted vertical work, actual persisted-state verification and fresh-agent reproducibility. | Planning documents are not runtime proof. Partial transcript coverage limits speaker attribution. |

Required course-derived behavior is stated here and in the research contracts. A teammate must not need the private course archive to interpret a ready ticket. Supply any missing verified test extract before assigning that ticket. Do not redistribute course code or videos as application fixtures without established rights.

## Out of Scope

The [section 5 exclusions](#excluded-from-the-hackathon-core) remain controlling. In particular, this synthesis does not add broad QT401 search, unrestricted generated code, a strategy marketplace, arbitrary MCP endpoints, pooled agent funds, token rights, cross-chain/perpetual execution or guaranteed profitability.

Formal statistical support remains unavailable until its selected method passes qualification. Live LP execution, Nansen/X/creator-history tools, realistic Kuru fill modeling and optional OpenBB integration require their own qualified scope. Stating those dependencies does not remove the accepted narrow simulator or LP proof.

This task creates no implementation tickets, production code, wallets, paid requests or financial transactions. It does not open the MOE holdout, rerun Probe A or redesign the frozen interaction prototype.

## Further Notes

### Decisions needed before dependent tickets

| Decision | Required output | Blocks | Does not block |
|---|---|---|---|
| First-slice application stack, authentication and durable storage | Selected existing-fit components, ownership enforcement and runnable setup | Production API/storage implementation | Accepted product meaning and sanitized fixtures |
| Canonical strategy and publication encoding | Versioned machine schemas, semantic manifest, atomic publication identity and compatibility rules | Compiler/publication consumers and exact revision binding | Story decomposition and input examples |
| Hermes hosting and model route | Pinned runtime/provider, isolation, tool allowlist, completion/cancellation and usage behavior | Shared live-model jobs and add-on access | Deterministic contract/UI fixtures |
| Data and simulator execution contract | Exact qualified market/dataset, availability model, replay ordering, fill/mark/cost assumptions and supported rules | Claimed production evaluations and backtests | Unresolved-report UI and portable calculation cases |
| Wallet, Flow and independent enforcement qualification | Tested owner/agent binding, route/transport, reservations, exit authority, denial, recovery and removal evidence | Affected real-wallet actions and agentic deployment claims | Independent research and UI work |
| LP proof configuration | One pool model, qualified data, comparator and bounded simulator acceptance | LP implementation and claims | Spot build |
| STAT-Q01 qualification | Tested method profile and failure criteria | Formal statistical support claims | Descriptive research, simulator or independently qualified live operation |
| Numerical resource and commercial settings | Measured runtime limits and explicit provider/research budgets | Runs requiring those values | Interface/schema work that rejects absent limits |

Resolve a consequential implementation choice in its assigned decision work, then update the existing ADR if it changes an accepted boundary. Do not create an ADR to invent a choice. Accepted ADRs 0001–0008 remain authoritative within their recorded scope.

### Ticket handoff rule

Use `to-tickets` after review of this synthesis and resolution of each affected blocker. Make small vertical slices with observable outcomes, selected story IDs, dependencies, required evidence and owner. Do not create one ticket per document or hand the full evolving specification to an unattended executor.

The first production slice should connect request, interpretation or clarification, reviewed rules, saved result and retrieval. It must include the working verification setup. Extend that path into the bounded investigation and simulator. Research/UI work may proceed independently of Probe B only where its dependencies permit. Agent deployment remains part of the intended release and demo.

The tracker specification issue will index the published canonical document and its exact revision. It must not maintain a second editable specification or imply every implementation dependency is ready. `ready-for-agent` on that index means the accepted specification can be decomposed, not permission to start financial work. The builder explicitly requested local review first on 2026-10-05. No issue, label, branch publication or PR is authorized in this pass. Later publication must first make the required shared documents accessible.

The private source-coverage note records the audit scope and limitations. Relevant source inspection is not a claim that every video, screenshot, clone or historical artifact was reread. No source review adds passing production evidence.

## 1. Purpose

This document defines the smallest complete Edge OS product for Monad Metropolis. It applies the Hackathon Winning Compass to the selected Edge OS idea.

The builder approved product scope on 2026-10-05. Implementation still requires accepted assigned tickets with resolved dependencies. A narrow experiment requires its own approved scoped design and instantiated plan. Neither document approval nor a ready label grants paid access or financial authority.

The product must be demonstrable in three minutes. It must perform real Monad work. It must also remain useful when no strategy survives validation.

## 2. Authority and evidence

Use these sources in this order:

1. Current official Metropolis rules and authenticated event information control contest facts.
2. [`../../research/00_HACKATHON_BRIEF.md`](../../research/00_HACKATHON_BRIEF.md) controls the local contest summary.
3. BUILDER-ONLY REFERENCE `docs/research/01_MONAD_CAPABILITY_AND_INTENT_MAP.md` controls broad Monad and sponsor evidence.
4. BUILDER-ONLY REFERENCE `docs/research/04_EDGE_OS_COMPILER_PRIOR_ART.md` controls inspected compiler and research-system precedents.
5. BUILDER-ONLY REFERENCE `docs/research/05_EDGE_OS_X_AND_ONCHAIN_DATA_ACCESS.md` controls current Edge OS data-access evidence.
6. BUILDER-ONLY REFERENCE `docs/research/06_JEV_TRADER_ALCHEMY_ENVIO_REVIEW.md` controls the execution-RPC boundary and inspected Kuru execution lessons.
7. BUILDER-ONLY REFERENCE `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` controls wallet evidence, the Assensus proof limits, and remaining Monad–Kuru questions.
8. [`../../../playbooks/HACKATHON_WINNING_COMPASS.md`](../../../playbooks/HACKATHON_WINNING_COMPASS.md) controls the working method.
9. [`../../EDGE_OS_COMPASS_WORKFLOW.md`](../../EDGE_OS_COMPASS_WORKFLOW.md) controls the stage order and team coordination.
10. This approved specification controls settled product behavior. Named proposals and qualification gaps remain open.

Read [`../../EDGE_OS_RESEARCH_CONTRACTS.md`](../../EDGE_OS_RESEARCH_CONTRACTS.md) before defining an `EdgeSpec`, accepting research-agent evidence, qualifying a data provider or creating research fixtures. It contains the detailed proposed contracts and acceptance examples. Review it with this design; it does not independently approve implementation or paid API access.

Compiler semantics and identity draw on the amended compiler guide, BUILDER-ONLY REFERENCE `course-insights/QT301/COMPILER_LESSONS_DISTILLATION.md` and verification report, BUILDER-ONLY REFERENCE `course-insights/QT301/COMPILER_VERIFICATION_REPORT.md`. Component locks, revision publication, tool outcomes and lifecycle failures draw on the Keel/GT clone review, BUILDER-ONLY REFERENCE `docs/research/KEEL_GT_PROTOCOL_CLONE_REVIEW.md` and engineering lessons, BUILDER-ONLY REFERENCE `docs/research/KEEL_GT_PROTOCOL_ENGINEERING_LESSONS.md`. These are inspected-source references, not approved implementations or evidence that hosted engines work. Compiler tests T01–T36 remain proposed and unrun. The builder supplies the verified subset required by an implementation ticket. The requirements below are Edge OS engineering proposals; they do not inherit either product's execution defaults or approval interaction.

Use these evidence labels:

- `VERIFIED FACT`: an official source, inspected source code, or reproducible test supports the claim.
- `FOUNDER OBSERVATION`: the builder supplied the claim from direct experience.
- `DIRECT USER EVIDENCE`: an identified target user described a real event.
- `PRODUCT OR SPONSOR STATEMENT`: a project or sponsor made the claim.
- `INFERENCE`: verified evidence supports the conclusion, but no source states it directly.
- `HYPOTHESIS`: Edge OS must test the claim.
- `UNKNOWN`: required evidence is missing.

The shared [OpenBB reuse assessment](../../research/OPENBB_RESEARCH_REUSE_AND_PRODUCT_DIFFERENCES_2026-10-04.md) records current documentation evidence for optional analysis/MCP components and research-view patterns. It does not establish a working integration, Monad/Kuru coverage or unique product capabilities. The builder authorized recording the assessment, not dependency adoption.

## 3. Complete idea card

### Exact first user

The first user is an active onchain meme-token trader on Monad. This person watches tokens, wallets, liquidity, price, volume, and social attention. The person does not have a complete quantitative research and execution system.

The first user can be experienced or still learning. Edge OS does not promise to make an inexperienced trader profitable.

Liquidity providers and LP strategy operators are the second user group. They investigate pools, fees, inventory exposure and the conditions for adding, removing or rebalancing liquidity. The proposed shared job is to make hypotheses and capture rules explicit and testable. LP-specific user demand remains unvalidated; naming the job does not establish that users want this mechanism. The first dangerous-claim prototype is spot-first and does not include live LP management.

### Triggering moment

The user has one of these inputs:

1. A concrete market thesis.
2. A loose intuition.
3. No thesis, but a bounded request to investigate a declared Monad market or pool universe.

The user wants to know whether the observation can become a testable strategy before risking capital.

For the first spot implementation, each investigation concerns one qualified Monad meme-token pool under the [accepted research binding](#accepted-research-market-binding-and-data-route). Research identifies the underlying pool separately from any intended Kuru execution route. For the LP path, the investigation concerns declared pools and a liquidity-management question. The available data and supported operations constrain each investigation separately.

### Accepted main starting scenario

Builder decision, 2026-10-03: use a [loose intuition](../../../CONTEXT.md#language), described to the user as a rough hunch, as the main starting scenario for the first production journey. The working example is "Recent rises seem to keep running. Is that worth testing?" Concrete theses and bounded no-thesis requests remain intended entry types into the same research process.

The reason for this choice is to address the proposed trader's difficulty making an observation testable and to test whether clarification preserves the trader's meaning. User understanding and demand remain unproved. Full-design approval remains separate.

### Accepted first research journey

Builder decision, 2026-10-03: adopt the following steps, finished result and failure path for the first production research journey. This is intended behavior, not tested production behavior or approval to implement.

1. Preserve the original request and restrictions.
2. Clarify only meaning needed for the investigation.
3. Let the user review the proposed question and bounded research budget.
4. Qualify the required data.
5. Investigate and validate under the declared scope and budget.
6. Explain and save the result.

The finished result is a saved research decision showing what was tested, supporting and contrary evidence, every attempted variant, failed gates, remaining unknowns and a specific next step. Include interpreted strategy rules where supported; a selected strategy may remain absent. An explained unresolved result can finish this research job. Paper testing and execution remain separately gated continuations, with no authority granted by the report or compilation.

This completion boundary covers the first research journey. Persistent strategy deployment and management retain their own execution and recovery requirements; the LP compile-and-simulate path remains the second product proof. The [conditional publication, token and funding extensions](#conditional-publication-token-and-funding-extensions) retain their separate scope and activation decisions. A completed report does not mark any of those capabilities complete.

When progress stops, preserve the work and identify whether the cause is missing meaning, unsupported capability, missing evidence or an invalid generated representation. Show the next permitted action. The [intake routing contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#interpretation-classification-and-field-level-evidence) owns these distinctions; representation failure does not make the user's idea unsupported.

The reason for this boundary is to answer the trader's immediate research question without inventing a strategy or waiting for execution proof. Probe A supports the bounded process lessons, not general strategy support or user comprehension. The interaction prototype must test whether a user understands the result and its next permitted action. Data coverage, realistic fills and the later readiness gates need their own evidence.

### Current failed process

The user currently moves between social feeds, wallet explorers, token pages, charts, notebooks, backtests, and a trading venue. The process has several failure points:

- the user cannot convert an informal idea into explicit entry, exit, invalidation, sizing, and data rules;
- a model or script can silently invent missing assumptions;
- a search can test many variants and report only the attractive result;
- current information can leak into a historical test;
- the simulation can ignore spread, depth, slippage, latency, liquidity, and capacity;
- the live implementation can differ from the tested strategy;
- an agent can propose an action without a deterministic risk boundary;
- a completed transaction can be mistaken for proof that the strategy has an edge.

The proposed LP problem also includes mistaking fee revenue for net benefit while omitting inventory exposure, impermanent loss, gas, rebalancing costs or a suitable comparison. This is a problem hypothesis, not a documented founder LP incident or established demand.

Founder incidents support failures in trade planning, exit discipline, and the gap between historical tests and live results. Broader demand in both domains remains unvalidated.

### Consequence

The user can act on a vague thesis, trust a false edge, misunderstand a generated strategy, or deploy a rule that never passed an honest test. The result can be an avoidable loss, a round trip, repeated unproductive research, or false confidence.

### Complete job

Edge OS must help the user complete this job:

> Investigate a thesis, intuition or bounded research request and preserve findings, competing explanations and unknowns. When the user wants a strategy, compile supported, sufficiently specified meaning and test the claims the available data can address. Let the user choose a live trial or ongoing operation with honest evidence labels and explicit permissions. Permit only actions that pass deterministic checks and the delegated wallet policy.

The shared job applies to spot and LP strategies. The initial LP result is research, compilation and simulation; live LP execution has a separate venue/adapter gate in section 15. The first spot onchain proof permits at most one controlled fixed-input Kuru Flow swap under a short-lived mandate. Any required setup/token approval needs separate explicit permission and limits.

### Definition of finished

The user receives one of these outcomes:

- `NEEDS_CLARIFICATION`
- `UNSUPPORTED`
- `EDGE_REJECTED`
- `UNRESOLVED`
- `VALIDATED_FOR_BACKTEST`
- `READY_FOR_PAPER_TEST`
- `READY_FOR_BOUNDED_EXECUTION`

For an executable result, the user can inspect the interpretation, evidence, tests, risk rules, execution mandate, wallet policy, intents, and Monad results. The user approves delegation once for that mandate. Routine permitted actions do not require another signature. A changed strategy version or expanded permission requires renewed approval.

For a rejected or unresolved result, the user can inspect the reason and the missing or failed evidence.

The [accepted claim-specific support and readiness gates](#accepted-claim-specific-support-and-readiness-gates) control transition meaning; the labels above are draft presentation vocabulary pending their distinct frontend mapping. Saving a draft and returning `COMPILED` are separate persistence/compiler outcomes, not research eligibility or execution authority. An incomplete draft can be preserved with its findings. Each later transition requires its own evidence gate; a save, tool success or compiler result cannot grant one of the readiness states above.

## 4. Product explanation

### One sentence

> Edge OS helps onchain traders and liquidity providers investigate opportunities, test supported strategy rules and run explicitly authorized agents, with evidence, uncertainty and execution limits visible.

### One minute

Edge OS is for meme traders and liquidity providers who want to investigate opportunities and learn from market evidence. It accepts a thesis, intuition or bounded research request, records every tested variant, and makes missing assumptions visible. Research can finish without a strategy. Supported, sufficiently specified rules can compile into an inspectable `StrategySpec`. Capture tests account for the domain's costs and risks. Users can start a live trial or ongoing live operation without a favorable backtest or prior paper trading; evidence stays visibly unproven where applicable. Every live action still requires supported rules, verified execution, risk checks and a revocable Privy mandate. A trial can continue under existing authority or user-approved revised permissions, without graduation. The first execution proof is one Kuru spot action with an inspectable receipt. LP support starts with research, compilation and simulation; live LP actions require a verified adapter. Envio supplies event history, QuickNode supplies current state, and X is optional evidence.

## 5. Product scope

### Product MVP

The product MVP has two action domains:

1. Meme-token spot strategies on Kuru.
2. LP research and strategies over declared Monad pools, with execution conditional on a verified venue and adapter.

Both domains share the research ledger, edge representation, strategy compiler, validation decisions, risk boundary, and receipts. They use separate simulators and action vocabularies.

The LP result required for the second proof is an inspectable research decision and compile-and-simulate path. This does not promise live LP deployment. Spot-first build order is not a change to the two-domain product frame.

The MVP includes a small approved catalog of per-agent skills and MCP connections under [Agent add-ons](#accepted-agent-add-ons-catalog). Users can enable supported entries themselves. Catalog acceptance does not approve arbitrary uploads, new strategy operations, provider spending or wallet authority.

### First dangerous-claim prototype

The first prototype supports one domain:

- Monad meme-token spot research, with the underlying research pool and any Kuru execution route identified separately. The retained Probe A market and findings are recorded in the [result report](../../prototypes/EDGE_OS_PROBE_A_RESULT.md); this wording does not revise that closed experiment.

It supports one bounded family:

- short-horizon directional momentum and reversal hypotheses.

It does not search every token, feature, horizon, threshold, or strategy structure. The `ResearchBudget` fixes the market set, feature set, horizons, candidate count, and validation access before the search starts.

### Second proof of generality

After the shared runtime and spot path work, the team can add one narrow LP compile-and-simulate path. The LP proof must reuse the shared objects. It must not become a separate product.

### Excluded from the hackathon core

- Copy trading.
- A strategy marketplace.
- Strategy or agent tokens.
- Autonomous treasuries.
- Public funding and revenue loops.
- Lending, perpetuals, prediction markets, and tokenized stocks.
- Cross-chain execution.
- Asset launch and market creation.
- Unrestricted agent research.
- Arbitrary skill/code uploads, user-supplied MCP endpoints and a public plugin marketplace. The accepted per-agent catalog below remains in MVP scope.
- Broad QT401 formula search.
- Multi-edge portfolio optimization.
- Automated edge-decay management.
- Live LP portfolio management before the spot path is stable.
- Any claim of guaranteed profitability.

### Conditional publication, token and funding extensions

Status: `PROPOSED; ECONOMICS, ELIGIBILITY AND ACTIVATION UNAPPROVED`.

These extensions preserve the wider product vision in the shared specification. They can be implemented after the agreed core works, including during this hackathon when separately accepted scope, dependencies and time permit. Documenting them does not expand the first probes or authorize token issuance, market creation, funding or financial actions.

A strategy can remain private and useful without a token. Publication is opt-in. A public record binds an immutable strategy revision and semantic identity to its evidence manifest, actual validation coverage, risk policy, operating state and permitted execution history. Label fixture, historical, paper and live records separately. Publish only authorized material; exclude credentials and private user or research data.

The token models are alternatives:

| Model | Proposed purpose | Boundary |
|---|---|---|
| Agent-community token | Identity, community and distribution. | No default claim on assets, operating funds or strategy profits. Define holder utility before selecting it. |
| Agent-financing token | A verified fee route finances declared inference, data or operating costs. | Verify collection and accounting. Keep operating budgets separate from user trading capital and execution authority. |
| Strategy-associated token | Associate a token with an exact strategy revision, evidence status and observable operation. | Association alone grants no asset backing, redemption, profit rights or validation status. |

A financing mechanism and strategy association may form one extension. No requirement exists to implement all models. Funding trading capital, buybacks, profit distribution, pooled assets and autonomous treasuries are separate unresolved mechanisms, not automatic consequences of token trading.

Before an extension becomes an implementation ticket, the builder must accept its choices and observable behavior:

1. **Purpose and rights.** Define the creator, holder, actual utility, enforceable rights and expressly absent rights. Keep identity, funding and ownership distinct.
2. **Strategy identity.** Bind the public/token record to the immutable strategy revision, semantic manifest and evidence identity. A changed strategy creates a new recorded relationship and applicable validation/approval decision; it cannot overwrite the earlier record.
3. **Eligibility.** Define required validation and any forward observation, warning limits and disqualification conditions. Compilation, a running worker, a token purchase or a completed transaction cannot independently satisfy eligibility.
4. **Public evidence.** Define displayed periods, costs, limitations, funding balances and operating state. Report measured performance only. Unknown or stale evidence must not appear as a current passing result.
5. **Issuance and liquidity.** Select network, supply, allocation, market parameters, initial liquidity source, permitted actors and failure handling. Qualify the actual deployment path. Issuance and funding require separate authority from the spot mandate.
6. **Funding.** Identify the verified fee source, collection path, recipients, budgets and reconciliation. No fee percentage or onward payment is assumed. Extra revenue grants no extra trading authority. Insufficient operating funding pauses affected work instead of weakening controls.
7. **Control.** Separate creator, wallet owner, signer and policy administrator. Holder or governance proposals can request a new revision; they cannot directly change risk limits, wallet policy or a user's mandate.
8. **Failure behavior.** Specify pause, revocation, strategy replacement, expired evidence, unavailable fee routes and insufficient liquidity. State whether token trading can continue while the agent is inactive. Do not imply a relationship that contracts do not enforce.
9. **Claims.** Describe the implemented rights and evidence. Do not call a token asset-backed or redeemable without the corresponding designed and verified mechanism. Funding or transaction proof does not establish profitability or demand.
10. **Acceptance.** Test ineligible-launch denial, revision mismatch, unauthorized changes, actual collection/accounting, stale public status and the approved issuance/liquidity path where applicable. A page displaying these fields is not proof of the underlying operation.

Activation requires accepted core checks, a useful research path and the agreed spot and LP proof scope, or an explicit builder-approved scope revision. Delegated execution must pass its separate gate when the extension depends on a live agent. Submission artifacts and the core recording path must remain viable. The extension needs a concrete user benefit, verified dependencies, accepted economics, funds/access approval, a bounded work budget and passing acceptance evidence. An implementation ticket is not approval to move funds.

Strategy export or forks can be considered separately. A fork receives its own revision, lineage and evidence; it cannot inherit execution eligibility or another user's mandate. Licensing, marketplaces, public rankings, broad search and additional venues remain later research-dependent possibilities. The core and its demonstration must work with every optional extension disabled.

## 6. Accepted inputs

### Concrete thesis

The user supplies a causal or statistical claim with enough detail to identify the market or pool, condition, horizon and expected effect. Spot claims may concern continuation or reversal. LP claims may concern whether fee income compensates for declared inventory and operating costs under specified conditions. These are hypotheses, not assumed edges.

Edge OS extracts the claim and asks only for missing information. It must not change the meaning to make compilation easier.

### Loose intuition

The user supplies an observation such as organic attention, wallet activity, accelerating volume or a suspected reversal after a crowded move. An LP observation may concern changing fees, volatility, inventory or rebalancing frequency. The system asks for missing meaning rather than silently turning the observation into an action.

Edge OS converts the observation into one or more explicit hypotheses. Each hypothesis remains a proposal until validation supports it.

### No-thesis bounded request

The user can ask Edge OS to explore a market without supplying a hypothesis or designing the experiment. Preserve the user's objective and restrictions. The agent may suggest a supported pool, research settings and a validation plan, explaining the assumptions and available evidence. The user reviews and adopts the consequential scope and settings before the affected investigation runs, under the [accepted parameter-adoption policy](#accepted-calculation-conventions).

The adopted research configuration records:

- the research market or pool scope, initially one qualified Monad meme-token pool per spot investigation, with any intended Kuru execution route identified separately;
- a finite feature set;
- allowed strategy forms;
- allowed horizons;
- a candidate and compute budget;
- a validation plan.

Users need not choose every technical setting themselves. Ask only for missing meaning or adoption needed at this stage. Proposed configuration does not create a selected strategy or grant readiness or financial permission. An unresolved result may retain adopted settings without a signal or strategy.

Edge OS can return zero surviving hypotheses. An unbounded search remains unsupported. For a request such as "find any profitable edge", explain the supported scope and offer a bounded investigation for adoption, preserving the original request. Run only after the required scope is settled; unsupported capabilities receive their own explanation rather than a silent substitute.

All three input states apply to both product domains. First implementation coverage remains the bounded spot family; LP coverage must be shown by the separate proof rather than inferred from shared field names.

### Research mode and observational investigations

Builder direction, 2026-10-03: research mode includes investigating observations, comparing cases, examining participants and proposing explanations. Concrete thesis, loose intuition and bounded no-thesis request remain the starting states; research mode describes the requested job, not a fourth input class.

Examples include "This creator seems to launch runners; is there a pattern?" and "Compare these past runners, their creators and unsuccessful launches." A finished investigation may contain a sourced comparison, possible mechanisms, contrary findings, unknowns and proposed next tests without a selected strategy, compiler output or backtest. Only executable strategy construction requires supported grammar; descriptive findings need their own evidence and claim checks, not forced conversion into a price formula. See the [observational evidence contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#observational-investigation-and-forward-learning-evidence).

Separate what can be described, tested historically, simulated for capture, observed prospectively or measured in an authorized live experiment. Explain why a proposed test is feasible or lacks essential data. An explanation for a runner remains a hypothesis unless the evidence supports the stronger claim. Research findings do not themselves authorize trading.

The first production rule/evaluation slice remains one qualified pool with price and executed quote volume. Creator attribution, prior launch histories, wallet PnL, rug-risk evidence and cross-launch comparisons are intended research extensions requiring qualified tools, data and acceptance checks. Hermes alone does not implement them. The focused decision session must select any extension included in the hackathon build; this amendment does not silently expand the first implementation ticket.

## 7. Core product objects

### `PromptInterpretation`

Records:

- input class;
- extracted claims;
- named market or universe;
- missing information;
- unsupported assumptions;
- requested outcome;
- clarification state.

Record starting-state classification separately from the requested job. Use the [interpretation and field-evidence contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#interpretation-classification-and-field-level-evidence) for source passages, origin, uncertainty, adopted configuration and clarification revisions. Classifications use names, not ordered scores. Ask only for meaning needed at the current stage. The first production intake ticket implements these rules; it does not expand the closed prototype grammar.

Preserve the original request and previous restrictions through clarification. Show proposed assumptions and changed fields. User-adopted timing or sizing may remain research configuration in an unresolved no-thesis case without creating a selected signal, strategy or readiness claim. Optional research rankings and defined numeric strategy signals have separate purposes; a model-confidence score cannot grant eligibility or authority.

### `ResearchBudget`

Records:

- markets;
- features;
- horizons;
- candidate limit;
- parameter limit;
- compute limit;
- research period;
- validation and holdout boundaries;
- allowed external sources.

### `ResearchLedger`

Records every hypothesis and variant, including failed results. Each entry includes:

- parent and child relationship;
- generator;
- specification hash;
- data version and time range;
- features and parameters;
- tests run;
- result;
- holdout access;
- rejection reason;
- cost and runtime where available.

### `EdgeSpec`

Use the [mechanism-first contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#4-edgespec). It records the effect, flow-producing participants, incentives or constraints, economic explanation, persistence against competition, simple capture mechanism, trigger/horizon, costs/capacity, alternatives, falsification and mechanism-health observations. Each claim has evidence references or explicit uncertainty and a version/ledger binding.

Participants may willingly or necessarily accept unfavorable prices. A guaranteed or forced loser is not required. An unexplained statistical association may remain a bounded research hypothesis; the agent must not invent its causal story. Missing meaning or essential data produces clarification or `UNRESOLVED`, not silent approval.

### `ResearchEvidencePackage`

Use the [agent output contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#5-researchevidencepackage). A package links the exact edge version to the question, budget, source records, observations, timing/quality, cohort classification, interpretations, alternatives, proposed test and complete run history. It references `ResearchLedger`, not a separate trial store.

A package can be ready for quantitative review, unresolved or contradicted. Those conclusions are not deployment states. Model confidence is not statistical significance. Only the deterministic validation and risk paths can advance an action toward capital.

A completed observational report can also be the requested research result without quantitative-review eligibility. Use the research contract's [observational and forward-learning evidence](../../EDGE_OS_RESEARCH_CONTRACTS.md#observational-investigation-and-forward-learning-evidence). Supported findings and unresolved claims may coexist in that report.

### `StrategySpec`

Records:

- domain and market or pool universe;
- data inputs;
- features;
- signal;
- entry;
- exit;
- invalidation;
- sizing;
- costs;
- risk limits;
- execution permissions;
- warmup and history requirements;
- canonical version and hash;
- a semantic manifest identifying compiler, primitive/component implementations, serialization and numerical-policy versions.

The manifest pins the meaning of returns, lookbacks, warm-up, missing values, alignment, branch validity and applicable rounding/unit rules. Only used components require locks. An automatic library upgrade cannot change an existing revision. A material semantic change creates a new revision and requires fresh applicable validation and mandate approval. The build brief freezes the allowed subset, exact canonical bytes and hash algorithm; course ZIP labels are source identities, not this protocol.

Domain semantics distinguish a numeric signal, a target allocation and an action intent. Spot entry/exit fields do not substitute for LP add/remove/rebalance/collect rules. Unsupported domain actions remain unsupported. Every action must retain its domain, venue, assets, units and limits through simulation and intent preparation.

### Revision publication and draft persistence

The [immutable revision ADR](../../adr/0004-immutable-strategy-revision-binding.md) records the accepted identity principle; the detailed publication encoding/protocol remains build-brief work.

Saving an incomplete draft preserves its source and validation findings under a draft identity, with no readiness or capital authority. Publishing a compiled revision atomically stores the immutable content and returns its revision ID, content hash and semantic-manifest identity. A separate fetch of "latest" cannot supply the identity for the preceding write.

Validation, paper evaluation and deployment reference the exact published revision. A `ValidationDecision` also binds the dataset revision, evaluation configuration and cost assumptions used; these are run evidence, not a claim that market data is immutable forever. A concurrent edit creates another revision without overwriting the artifact or inheriting its validation or mandate. Unknown, unreadable or mismatched identity stops promotion and new execution. Identical content does not restore an unseen holdout or erase trial history.

### `ValidationDecision`

Records:

- decision state;
- evidence used;
- tests passed and failed;
- robustness and temporal checks;
- execution assumptions;
- failed gates;
- paper-test or execution eligibility;
- human-readable reason.

### Execution intent and receipt

The `TradeIntent` contains one bounded action. It includes an intent ID, mandate ID and version, wallet binding, market, side, amount, price guard, expiry, network, risk-policy version, strategy hash, and decision hash.

The execution record links the intent to its checks, policy version and content hash, exact transaction fields, provider reference, and idempotency key. A denied intent records its failed rule and has no transaction hash.

The receipt links a submitted intent to its transaction hash, block, status, emitted events, resulting state, and explorer route. Submission, transaction confirmation, order acceptance, partial fill, fill, cancellation, and revert are distinct results. An accepted resting order is not a fill.

### `ExecutionMandate`

An execution mandate is the user's permission for a particular deployed strategy. It records:

- user and user-owned Privy wallet binding;
- strategy version and hash;
- validation-decision hash and risk-policy version;
- linked evidence status and user acknowledgement of material limitations, separately from operating purpose and any optional trial objective;
- selected Monad network;
- allowed contracts, markets, tokens, functions, and argument limits;
- per-swap input/price guards, aggregate capital, approval, gas, exposure, and loss limits;
- maximum economic-action/attempt count, separately permitted setup actions, start time, and expiry;
- allowed cancellation and emergency-stop behavior;
- signer identity, attached policy identity, version, and content hash;
- approval evidence, lifecycle state, and revocation evidence.

The Probe B fixture mandate permits one fixed-input Flow swap. The build brief must define exact units and any separately permitted setup/approval actions; it does not inherit cancellation or resting-order permissions. An empty or unknown limit denies execution.

### Persistent deployment state

Store the mandate, strategy version, validation decision, worker state, last processed data position, capital reservations, open orders, pending transactions, and intent records durably. Model memory and chat history are not execution state.

## 8. System boundaries

### Prompt interpreter

The prompt interpreter classifies the input and extracts meaning. It can ask for clarification. It cannot emit executable code or add silent assumptions.

It proposes structured meaning with field-level evidence. Deterministic routing checks stage requirements, supported capabilities and qualified data. Missing meaning, unsupported capability, missing evidence and an invalid generated representation have distinct outcomes under the research contract. A user does not need to learn the compiler grammar. A repair of a supported representation retains the user's meaning; a changed idea needs adoption and a new revision.

### Evidence gateway

The evidence gateway normalizes Kuru, Envio, RPC, optional Nansen, optional Tenderly, and optional X records. It preserves source and collection metadata.

Apply the research contracts' [timing and failure rules](../../EDGE_OS_RESEARCH_CONTRACTS.md#6-timing-validation-and-failure-rules). The authorized collector keeps API credentials outside model context and frontend output. External source content cannot change tool permissions or project policy.

### Hypothesis engine

The hypothesis engine proposes bounded `EdgeSpec` records. It can use human observations, agent investigation, or a finite quantitative search.

Research agents return a `ResearchEvidencePackage` with observations separated from interpretations and contrary evidence retained. Quant code tests the effect independently. Read/network/tool permissions and request/compute/cost budgets are scoped to the declared investigation; a timeout or budget breach stops and records affected work.

### Optional Hermes and Jev roles

The research and assessment interfaces below are required when their corresponding roles are enabled. Hermes and Jev are replaceable implementation choices, not required dependencies or independent sources of validation authority. A run can omit Jev and use deterministic rules. A human-authored hypothesis can enter the same evidence contract without a Hermes invocation.

| Role | Placement and input | Required output and boundary |
|---|---|---|
| Hermes-style investigator | Hypothesis engine, using the bounded question, approved evidence-gateway tools and declared `ResearchBudget`. | Proposed `EdgeSpec` and `ResearchEvidencePackage`, linked to the ledger. Preserve observations, interpretations, contrary evidence and unresolved claims separately. Deterministic quant code evaluates the proposed effect independently. |
| Jev-style assessment | Optional classifier over versioned structured market features and their availability times. It may route a case to bounded investigation before Hermes runs. During deployment it may assess state only where the exact approved `StrategySpec` permits model-based decisions. | A typed assessment containing input and model/version references, the permitted decision label, evidence references and a concise rationale. The build brief freezes the vocabulary and abstention behavior. Missing or stale inputs return unresolved/abstain rather than an invented action. A trade proposal becomes a `TradeIntent` only through the approved strategy contract and existing deterministic gates. |

Evaluate Jev against a declared deterministic or simpler-model baseline before treating it as necessary. Fast responses or model confidence do not establish better decisions, a trading edge or permission to execute. Neither role can award a `ValidationDecision`, expand a mandate, access signing credentials or authorize a Privy request. Expose source-linked findings and a concise decision explanation to the user, not private model reasoning as evidence.

The persistent worker owns scheduling, durable records, recovery and order reconciliation. Hermes conversation memory and Jev outputs do not replace that state. Separate agent services are optional and remain outside the first proof. The build brief must select and version any adopted runtime/model and qualify its actual outputs; these roles are not implemented by this amendment.

The cloned JEV Trader application is a Kuru execution/proof reference described in the JEV review, BUILDER-ONLY REFERENCE `docs/research/06_JEV_TRADER_ALCHEMY_ENVIO_REVIEW.md#7-what-edge-os-should-take-from-jev-trader`. It is distinct from the proposed Jev assessment role. Edge OS does not adopt its trading loop, local-key signing or forced direction choice.

### Accepted thin per-agent memory contract

Builder approved on 2026-10-06. Use one small, versioned context record per agent in the application store selected for production. Existing application storage owns this context; the MVP requires no separate vector database, whole-chat replay or full Hermes feature parity.

| Concern | Accepted requirement |
|---|---|
| Stored context | User-adopted preferences, corrections and source-linked research lessons. Generated lessons remain labeled suggestions until adopted. |
| Task retrieval | At task start, the backend authenticates the owner and agent, supplies only that agent's authorized context and records the memory version used. An unscoped task receives no private agent memory. |
| User control | The owner can inspect, correct, disable or clear the agent's context. Corrections create a new version for subsequent tasks. |
| Isolation | Agent A cannot read or change B's private memory, even under the same owner. Cross-user reads and changes are denied. Source links receive the same ownership checks as the context record. |
| Financial authority | Strategy rules, mandates, balances, positions and pending actions come from authoritative saved records. A memory note or suggested lesson cannot change those records, grant tool access or expand financial permission. A proposed strategy change uses the existing revision and approval flow. |
| Clearing and disabling | Future tasks stop using cleared or disabled context. Financial history, pending records and permission remain unchanged. This does not promise erasure of context already supplied to an in-flight task or provider. |

Keep the owner/agent binding, context version, adopted content and source references in the memory contract. Retain the version used with each applicable task. Credentials and signing secrets stay outside memory. Storage encoding, resource limits and version-history retention need definition before affected implementation; this approval selects no database or new service.

The following requirements are **unrun**. Authored checks and document approval do not qualify Hermes isolation or production behavior.

| Check | Required evidence |
|---|---|
| MEM-Q01: persistence | Save context, restart the application/runtime and retrieve the same owner/agent context and version. |
| MEM-Q02: correction and retrieval | Correct adopted context; the next applicable task uses the new version and records it. Generated lessons remain suggestions until adoption. |
| MEM-Q03: isolation | Deny A-to-B and cross-user reads, edits and source-link retrieval. Check API, task tools and runtime files/caches, not only visible UI filtering. |
| MEM-Q04: authority | A note requesting different rules, spending, credentials or tool access changes no authority. Current saved account records prevail over a stale note. |
| MEM-Q05: owner control | Inspect, disable and clear context through the owner path. Later tasks omit disabled/cleared context while financial records, reservations, pending actions and permission remain unchanged. |

This contract follows the existing [model/execution boundary](../../adr/0005-model-and-execution-authority-boundary.md). It supplies continuity for explanations and investigation, not execution state or automatic strategy modification.

### Accepted agent add-ons catalog

Builder decision, 2026-10-04: provide a small approved catalog that users can install or enable for individual agents. Intended MVP behavior, not implemented or tested support. This is a product-agent feature, separate from contributors installing Codex skills for implementation.

**Initial entries.** Offer a market-investigation instruction skill and a price-and-volume analysis instruction skill. Expose qualified research history/calculation tools and read-only account tools through approved MCP connections. These entries reuse the accepted evidence gateway, supported operators and shared account records; they do not add RSI, chart patterns, creator histories or another research domain. A skill guides an investigation; deterministic code performs supported calculations. List only entries whose declared capability has been qualified. A planned or unavailable entry must not appear usable.

**User interaction.** Each agent has an Add-ons view showing available, enabled, disconnected and failed entries. An entry explains its purpose, exact data/tool access, version, authentication requirement and any provider or inference costs. The user selects an entry, reviews access, connects an account where needed and enables it for that agent. Provide disable/disconnect controls with the resulting loss of capability explained. No technical MCP configuration or shell command is required from an ordinary user.

**Configuration and provenance.** Keep a backend-owned, versioned catalog manifest and per-user/per-agent selections. Record enabled skill versions/content identities, connection versions, selected tools and relevant configuration identity with each investigation or action that uses them. Credential values are excluded. Review updates before activation; do not silently replace a running investigation's skill or tool set. Changes affecting strategy meaning require the existing strategy-revision and applicable mandate review. Merely enabling a research skill does not create a new executable strategy.

**Access boundary.** For the initial catalog, skills supply reviewed instructions and supporting text, not arbitrary executable scripts or installers. MCP exposes only selected read-only research/account tools. The backend authenticates the user and agent, enforces ownership on every record access and restricts connections to approved endpoints and tools. A caller-supplied user ID or agent ID is not proof of ownership. Keep secrets outside prompts, chat, logs and published configuration. Use scoped credentials and isolated runtime access; shared backend service credentials never become model-visible or user-readable.

Hermes profiles can separate configuration and memory, but do not by themselves prove secure hosted-user isolation. The pinned runtime's skill/MCP behavior, credential handling and cross-user isolation need qualification before activation. Current upstream installation documentation is a reference, not evidence that the retained probe runtime supports this UI: [skills](https://hermes-agent.nousresearch.com/docs/guides/work-with-skills/), [MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/), [profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/).

**Authority and failure behavior.** An add-on cannot change compiler capabilities, validation decisions, spending limits, signer policy or execution permissions. Account answers use the same qualified records and update times as direct views. Disabling an add-on removes future access; it neither cancels submitted actions nor revokes the wallet mandate. If an investigation requires that connection, preserve the work and name the missing input instead of substituting data. Its loss blocks only work that actually requires it. Explain authentication failures and costs without exposing secrets. Existing approved research/compute budgets apply; final numerical limits follow provider terms and measured behavior, not new arbitrary probe quotas.

**Scope and sequencing.** Custom skill uploads, arbitrary MCP URLs, executable packages and a public marketplace remain later extensions with separate security design. First implement the required evidence/account tools, then expose the small catalog and per-agent controls through accepted tickets. This amendment does not reopen Probe A, expand the approved five-task frontend walkthrough, start another prototype or qualify Probe B. The build brief freezes exact catalog entries, schemas and runtime lifecycle behavior. Full design approval, implementation and spending remain separate.

### OpenBB research reuse candidate

Recorded with builder authorization, 2026-10-04. OpenBB is an optional component candidate, not a core dependency or enabled add-on. Reuse selected calculations, provider/result-interface patterns or a self-hosted analytical MCP only where they reduce work for an accepted requirement. The [sourced assessment](../../research/OPENBB_RESEARCH_REUSE_AND_PRODUCT_DIFFERENCES_2026-10-04.md) owns the comparison, current version differences and documentation limits.

Keep Envio history and QuickNode state/reconciliation roles unchanged. No exact Monad/Kuru historical adapter was verified. The initial operator registry remains unchanged; an available RSI/MACD function does not become a supported strategy operation through installation. Pin and qualify any selected release against our timing, units, missing-data, alignment, warm-up and numerical conventions before adoption. Preserve requested operations and their failures; a library helper that skips an unknown indicator cannot silently change the investigation. Add tested semantic/dependency identity to the relevant calculation and strategy revision.

Use the existing catalog's ownership, secret, selected-tool, provenance and cost boundaries. Restrict generic MCP dispatch as well as named tools. OpenBB's browser-linked Workspace MCP requires an open connected tab; do not make it an essential unattended-worker dependency. A self-hosted ODP MCP is a candidate, not a qualified transport. Library code does not make provider data or inference free; approve actual access/costs separately.

The intended product distinction is the complete request/meaning, all-trial evidence, immutable strategy and delegated-operation contract, not AI chat or indicators alone. OpenBB already supports agents and research interfaces and could be extended toward similar workflows. Neither an absent turnkey equivalent in reviewed docs nor Probe A's bounded pass proves a unique or complete production system. Record a selected component and focused qualification in the applicable build brief/ticket; do not reopen Probe A or require another broad probe. The core must work without OpenBB.

### Market terminal and chart integration direction

Recorded with builder authorization, 2026-10-05. Use external terminals as optional market context and selected data sources rather than build a full terminal. Start with a "View market chart" link for an exact pool from Research or position details. GeckoTerminal embedding is a later option within an accepted frontend ticket; selected read-only market-data tools are candidates within an accepted backend ticket. Neither is implemented, qualified or an enabled catalog entry. The [sourced comparison and integration note](../../research/MARKET_TERMINALS_AND_GECKOTERMINAL_INTEGRATION_2026-10-05.md) records GeckoTerminal, DEX Screener and Birdeye references, provider behavior and outstanding checks.

Keep chart access secondary to the research conclusion or account task. Identify its chain, pool, denomination and provider. Current market charts, frozen investigation data, simulated account-value charts and actual position results remain distinguishable. Chart changes do not rewrite a saved study. Missing external coverage leaves the chart unavailable, preserving the report and account controls.

Any selected API connection follows the existing evidence gateway and per-agent catalog boundaries. Qualify the exact route/plan, coverage, units, aggregation, missing intervals, timing and numerical compatibility before calculation use. Preserve source and collection evidence; provider-filled gaps cannot silently become observed prices. Envio history, QuickNode reconciliation, closed Probe A evidence and the Kuru Flow/Privy execution boundary remain unchanged. Chart/data access grants no wallet authority. The complete research-to-operation workflow is the intended distinction, not charts or AI conversation alone. This direction creates no new prototype phase, service purchase or execution approval.

### Strategy compiler

The compiler converts supported meaning into a typed intermediate representation and canonical `StrategySpec`. It uses a whitelist of data fields, operators, actions, and risk fields.

The [typed-language ADR](../../adr/0001-typed-strategy-language.md) records the accepted architectural rationale. Resolve locked component metadata before evaluation. Check static input shape, domain types, argument counts, parameter ranges, units and cross-field constraints before data access or effects. State-dependent preflight checks may read current venue and portfolio state, but must pass before a financial effect. Revalidate stored/decompressed input through the same boundary as fresh input. The later course registry demonstrates typed generation; it does not establish a rejecting validator for arbitrary supplied expressions. Sample ranges used by a generator are not the compiler's accepted ranges. Use the amended compiler references in section 2 to choose and test the supported subset.

### Shared tool outcomes and modes

UI, API and agent tools use the same stage-specific contracts. A result carries operation ID, stage, outcome code, relevant artifact/revision identity, findings, safe explanation and retry classification. Strategy-related success requires the expected revision; missing identity cannot be treated as a successful promotion. The build brief freezes the schemas and outcome vocabulary. Tool descriptions and annotations communicate these rules but do not enforce authority.

Research, paper and live are explicit modes. An absent mode grants no capital authority. Draft saving and compilation cannot create an active deployment. Tools that move capital or change execution authority remain inaccessible to research agents; scoped draft and research-record writes do not grant that authority. Only the deterministic execution service can request a permitted financial effect.

Provider calls have explicit deadlines and bounded retry budgets. Read retries must stay within the declared investigation budget and retain collection times. A timeout, lost acknowledgement or authentication refresh cannot turn an uncertain mutation into a fresh action. The execution service first reconciles the original attempt under the recovery rules below. An unexpected guard failure denies the affected transition rather than continuing optimistically.

Authenticated provider transport and secret storage must meet the approved deployment contract. Return redacted provider errors and safe diagnostic references, not raw credentials or private payloads. A model repair may propose a new draft; it cannot weaken policy, silently rewrite an approved intent or bypass a failed gate.

### Deterministic evaluator

The evaluator runs backtests and adversarial checks. It applies point-in-time data rules, execution costs, search accounting, and the selected validation procedure.

### Risk engine

The risk engine checks the approved intent against deterministic limits. A model cannot override this result.

### Execution host

The execution host accepts a typed intent within an active, user-approved mandate. It checks the deterministic risk decision and current wallet-policy binding. A fixed Kuru adapter encodes the transaction. The host authorizes a Privy request through a backend-only credential. Privy evaluates the policy and signs the transaction.

The Monad–Kuru spike must select one transport: Privy submits directly, or Privy returns a signed transaction for submission through the standard RPC. QuickNode remains the initial current-state and reconciliation provider. The public Monad RPC can become a fallback after the required method checks pass. A provider outage never permits a local wallet-key fallback or a fresh duplicate transaction.

The LLM and research agents cannot access credentials or call Privy. The authorized execution service can act while the user is offline. It does not require another user signature for each permitted action.

The proof record separates:

1. The user approved a mandate and attached its restricted signer.
2. An intent passed or failed deterministic checks and wallet-policy enforcement.
3. A provider accepted submission, or its outcome remains unknown.
4. A Monad receipt confirmed the transaction result.
5. Kuru events and state confirmed order acceptance, cancellation, or fills when applicable.

A Proposed head or log is provisional. The product must not present it as settled execution.

### Persistent worker

Before evaluating a new action, the worker verifies the mandate, strategy version, signer, policy content, current data, and portfolio state. Startup begins in `RECOVERING`, not in executable mode.

Persist each intent and its exact transaction fields before submission. Use a durable unique intent key and an exclusive worker claim. Reserve capital for outstanding actions. A timeout after submission records `SUBMISSION_UNKNOWN`, not a failure that permits a new order.

After a restart, reconcile provider references, transaction hashes, receipts, Kuru orders, and fills before issuing another action. Reuse the original idempotency reference only when the selected provider's documented behavior permits it. An unresolved outcome, nonce conflict, expired intent, or changed policy stops new execution. Do not claim unconditional exactly-once execution.

The worker resumes only after reconciliation and current authority checks pass. It records stop reasons and pending exposure. Agents may contribute research or decisions through typed records. Separate agent processes and agent-to-agent payments are outside the first proof.

## 9. Data design

### Source-of-truth order

| Need | Source | Required behavior |
|---|---|---|
| Research market identity | Qualified venue/pool and chain records, with QuickNode corroboration | Use the accepted real-pool binding; token symbols or Kuru indexing alone cannot establish venue identity |
| Execution route and venue behavior | Kuru Flow fixed-input swaps; actual route/deployment unqualified | Separately qualify route metadata, executable actions and venue-linked proof; order-book semantics apply only if that interface is selected |
| Historical and live contract events | Envio | Filtered backfill and qualified pool-event records for research; live/reorg behavior and any execution-event indexing require their applicable qualification |
| User wallet and delegated signing | Privy | User-owned embedded wallet, explicit signer consent, policy-scoped signing, and owner removal of the signer |
| Current state and reconciliation | QuickNode, initial provider | `eth_call`, gas estimation, receipts, block-state checks, and WebSocket subscriptions. Broadcast only if the verified transport uses signed transactions from Privy |
| Wallet and trader enrichment | Nansen, optional | Labels, holdings, flows, DEX trades, cohorts, and historical enrichment for a declared hypothesis |
| User wallet summary | Zerion, optional | Portfolio, positions, transaction history, and PnL for the user-facing result |
| Pre-execution trace | Tenderly, optional | Simulation, logs, state effects, and revert diagnosis when the result changes authorization |
| Social attention | Official X API, optional | Timestamped posts and forward engagement snapshots for bounded research |

Optional at platform level does not mean dispensable within every hypothesis. A label- or social-dependent test stops when its essential input is unavailable. A separate onchain-only investigation may continue under its own declaration and ledger entry.

The [Nansen qualification plan](../../EDGE_OS_RESEARCH_CONTRACTS.md#8-nansen-qualification-investigation) is `NOT_STARTED`. It first tests coverage, meaning, timing and reproducibility for one builder-selected token/venue. No token, paid access, budget or trading strategy is approved by this revision. Perpl data requires a separate declared hypothesis; perpetual execution and broad search remain deferred.

The accepted initial research route uses Envio and QuickNode. Kuru Flow fixed-input swaps and Privy belong to the separately gated execution proof; the actual deployment/route and signing/broadcast transport remain unqualified. Envio HyperRPC is read-only and must not be configured as the execution RPC. Use Monad's public RPC as a fallback only after the required method checks pass. Execute a test action only after its separate approval and within its approved mandate. Keep the Privy signing boundary during provider changes. Alchemy remains optional when a measured requirement justifies it.

### Point-in-time rule

Every feature must state what information was available at the decision time. The evaluator rejects a feature when it cannot establish that boundary.

Each normalized record includes:

- source;
- source identifier;
- event time;
- collection time;
- chain, block, and transaction identifiers when applicable;
- market or token identifier;
- data version or query version;
- completeness state;
- finality or reorg state when applicable.

### X evidence contract

X is an optional evidence source. It can support:

- post and unique-author velocity;
- attention acceleration;
- original-post and repost ratios;
- author concentration;
- contract-address mention accuracy;
- narrative or sentiment classification;
- disagreement and uncertainty measures.

X does not provide a trading decision. Edge OS combines any X feature with venue and onchain evidence inside a declared hypothesis.

For each X-derived feature, store:

- search query or stream rule;
- post identifier and creation time;
- collection time;
- engagement values at collection time;
- language and filtering rules;
- author-count and concentration inputs;
- classifier name and version;
- aggregation window;
- linked contract address or Kuru market.

The product uses the official X API. It does not depend on `twscrape`, Twikit, Nitter, `snscrape`, or another unpublished X interface.

When X is unavailable, stop any hypothesis that requires its social features and record the unresolved dependency. A separately declared onchain-only investigation may continue with its own hypothesis identity, budget and ledger lineage. Do not remove an essential feature while preserving the original validation result. This follows the hypothesis-specific failure rule in section 13.

## 10. First research family

The first family tests short-horizon directional momentum and reversal in Monad meme spot. The accepted initial implementation binds each investigation to one qualified pool; this is not a permanent product restriction.

### Accepted initial research inputs

Builder decision, 2026-10-03: the first production research rules support price and executed volume, with volume measured in the declared quote asset. This is intended capability scope, not tested volume support. The language/history/Boolean and calculation conventions below are accepted. The operator registry, pool binding, data route and claim-specific readiness requirements below are also accepted. Outcome/control definitions below are also accepted. The statistical-support policy below is accepted. Its exact method profile/qualification, measured resource bounds and execution-route qualification remain unresolved.

The reason for choosing price and volume over price-only is to permit both price hunches and questions about trading activity within a small onchain input set. Price-only has stronger existing mechanics evidence and less implementation work. Broader wallet/social inputs add separate classification, availability and provider dependencies. This choice establishes neither volume's predictive benefit nor a trading edge.

Supporting an input does not authorize adding it to a user's rules. A price-only idea stays price-only unless the user adopts a changed hypothesis. Preserve unsupported wallet, social or LP meaning and explain the missing capability; a replacement requires user adoption. A run that requires volume cannot silently drop it when evidence is missing.

Trade-direction/order-flow imbalance, wallet features, social attention and further market features remain possible later research inputs, not adopted first-slice signals. Cost, liquidity, price-impact and risk evidence remain separate requirements for applicable simulation and execution gates. LP remains the second proof.

Before claiming production support, complete the [focused input qualification and compiler checks](../../EDGE_OS_RESEARCH_CONTRACTS.md#focused-price-and-volume-support-checks). Probe A remains closed; no broad research experiment is required by this capability decision.

### Accepted strategy language and missing-data policies

Builder decisions, 2026-10-03. These are intended production behavior, not implemented or passing checks. They do not change Probe A's historical semantics, fixtures or results.

**Language form.** Adopt a small typed expression language. Optional UI templates are presets over that same language, with the same validation boundary; templates do not form a separate evaluator or permission system. Preserve the user's adopted meaning and restrictions. Use the accepted operator registry below. Resource bounds and the execution action subset remain to be frozen. General Python generation remains outside the draft trust boundary.

**Scheduled history.** Lookbacks count scheduled buckets, not retained valid observations. Each operation requires its actual inputs. A return requires its referenced, qualified point-in-time endpoint prices; lag requires the referenced value of its supported numeric series; an intermediate coverage gap does not itself erase a calculable endpoint return. A rolling aggregate requires every value in its declared window. Keep scheduled positions and coverage gaps even where an operation remains calculable. A return spanning N intervals reaches N scheduled positions back; a window of N values contains N scheduled positions. Use the accepted calculation conventions below for bucket width, close aggregation and no-fill behavior. Use the accepted registry below for each operation's inclusion and dependency rules.

The reason for this policy is to preserve elapsed-time meaning while avoiding rejection of an operation because of an unused intermediate value. Requiring every intermediate value would unnecessarily reject some endpoint calculations; counting only valid observations would silently change elapsed time. Historical collection today does not qualify an endpoint's historical availability. Use the research contracts' [timing rules](../../EDGE_OS_RESEARCH_CONTRACTS.md#6-timing-validation-and-failure-rules).

**Three-valued Boolean logic.** Conditions have TRUE, FALSE or UNKNOWN values. AND is FALSE if either operand is FALSE, TRUE if both are TRUE, and UNKNOWN otherwise. OR is TRUE if either operand is TRUE, FALSE if both are FALSE, and UNKNOWN otherwise. NOT exchanges TRUE and FALSE and preserves UNKNOWN. Keep all missing-input reasons even where the final Boolean value is determinable. Evidence qualification is separate from that value: a TRUE result does not qualify missing hypothesis-essential evidence or grant readiness, and UNKNOWN cannot trigger an action.

The builder selected determinable three-valued results over propagating every missing operand to the combined value. This permits a result when another operand determines it while retaining the explanation of missing evidence. Validate the whole expression's types and dependency timing before Boolean simplification. Invalid types, unsupported nodes and future-information dependencies cannot disappear through short-circuiting, constant folding or a decisive sibling condition.

The [focused acceptance fixtures](../../EDGE_OS_RESEARCH_CONTRACTS.md#typed-language-and-missing-data-acceptance-fixtures) specify the required checks. They are authored, unrun fixtures, separate from recorded market research. Remaining validation and execution-route choices and the full specification/build brief still require builder decisions.

### Accepted calculation conventions

Builder decisions, 2026-10-03. These production conventions and their [focused acceptance fixtures](../../EDGE_OS_RESEARCH_CONTRACTS.md#calculation-convention-acceptance-fixtures) are accepted requirements, not tested behavior. Preserve Probe A's original definitions, rounding and results.

**Resolution and availability.** The initial research resolution is fixed five-minute UTC buckets, each `[start, end)`. This defines neither worker frequency nor decision frequency. A bucket close cannot become available before bucket completion; it is usable only when its required source evidence is also qualified as available. Preserve event time, bucket end, actual availability where known, collection time and any assumed historical delivery delay. Bucket completion or collection today cannot prove historical delivery or finality. Requests needing another resolution require explicit limitation or adoption of a changed request, not silent conversion.

**Observed close.** Use the last qualified executed trade inside the bucket. Resolve equal timestamps by canonical chain ordering (block number, transaction index, log index), with the chain/block identity retained. Missing ordering evidence leaves the affected close unqualified; arbitrary provider row order cannot establish it. Preserve the closing trade's identity, timestamp, base/quote amounts and size. An empty bucket has no observed close; use no implicit carry-forward, interpolation or backfill. Qualification still controls whether a price can serve as a point-in-time endpoint. VWAP and a prior-trade as-of lookup are separate potential operations, not substitutions for this close.

The reason for five minutes and last-trade close is the existing bounded aggregation evidence and a clear endpoint-price meaning. This establishes neither an optimal trading resolution nor adequate samples. A tiny final trade can dominate the close; retain its provenance rather than treating the close as a promised fill. The actual MOE five-minute window contained no empty price buckets, so empty-bucket behavior requires authored fixtures.

**Parameter adoption.** Permit visible suggestions, preset values and declared search ranges. Beginners need not supply every technical setting. Preserve each consequential value's source/origin and whether the user adopted it under the [field-level evidence contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#interpretation-classification-and-field-level-evidence). Complete the stage-required adoption before running the affected investigation. Accept finite unit-correct parameters within declared resource limits; freeze exact per-operation domains in the operator registry/build brief. Do not silently clamp values. Distinguish invalid representations, unsupported capabilities and insufficient samples. Declare search ranges, comparisons and budgets before viewing outcomes, and preserve every tested variant in the existing ledger. The probe's parameter whitelist is not a production restriction.

**Numerical convention.** Use a versioned 50-significant-digit decimal arithmetic context with half-even rounding. Preserve raw integer trade amounts and declared asset decimals; retain their source identities. Apply the declared context to calculations without the probe's separate 20-significant-digit ingestion rounding. Compare calculation values before display rounding; displayed equality is not calculation equality. Include the convention's version in strategy/evaluation identity under the existing revision contract. This is a reproducible calculation convention, not exact market prices or guaranteed threshold accuracy. Keep pool-gross measurement, source qualification, trader-net prices and achievable fills distinct. Use the accepted registry below for operator domains and numerical-failure behavior.

### Accepted initial operator registry

Builder decision, 2026-10-03, including amendments to Q9. Intended capability, not passing implementation evidence. This registry defines research features and conditions; it does not define or authorize financial actions. Constants and numeric series carry units and the applicable asset/market binding. Exact machine encoding and measured resource bounds are frozen in the build brief.

| Signature | Result and dependencies |
|---|---|
| `constant(value, unit)` | Finite typed numeric constant. Preserve an explicit decimal representation and unit: dimensionless, declared quote asset, or declared quote/base price. A user percentage can normalize to a dimensionless ratio with field provenance. No non-finite or untyped threshold. |
| `price()` | Qualified last-trade bucket close in declared quote/base units, with trade provenance. Empty bucket: no observed close. |
| `quote_volume()` | Sum of the qualified quote-asset leg amounts for trades in the completed bucket, in declared quote units. Count each trade once. |
| `price_return(n)` | `price[t] / price[t−n] − 1`, dimensionless. Both referenced endpoint prices must be qualified, available and positive. Missing unused intermediate prices do not erase the result or their coverage gaps. |
| `lag(x,n)` | Value of any supported numeric series `x` at scheduled position `t−n`, preserving units, binding and qualification reasons. Not restricted to prices; no coercion of Boolean series to numeric. |
| `sum(x,n)`, `mean(x,n)` | Numeric series window from `t−n+1` through current completed position `t`, inclusive. Require every value; preserve units/binding. |
| `relative_volume(n)` | `quote_volume[t] / mean(quote_volume[t−n .. t−1])`, dimensionless. Require current volume and every preceding baseline value; exclude current from the baseline. |
| `>`, `>=`, `<`, `<=` | Two compatible numeric operands; a typed constant may be compared with a numeric series. Preserve strict/inclusive meaning. UNKNOWN for unavailable valid numeric operands, with reasons. Incompatible units/bindings are invalid types. |
| `AND`, `OR`, `NOT` | Two Boolean operands for AND/OR and one for NOT, under the accepted three-valued policy. Preserve all reasons and whole-graph validation. |

All lookback/window parameters `n` are positive integers. Warm-up is computed from the actual expression dependencies, including nesting, rather than one universal valid-row count. Insufficient required history is UNKNOWN with positioned reasons; never shrink the window. Constants do not create evidence or availability for their dependent series.

For quote volume, qualify the event's quote-asset leg and amount conversion, not the sum of both legs or a guessed token symbol. Deduplicate by trade identity before aggregation; preserve conflicts rather than silently choose one duplicate. Complete qualified empty trade coverage establishes zero volume; incomplete coverage produces UNKNOWN. Preserve pool-gross measurement and token-mechanics limitations, including any unproved relationship to trader-net transfers/proceeds. A zero relative-volume baseline produces UNKNOWN with `ZERO_BASELINE` for both zero/zero and positive/zero; no epsilon or infinity trigger. Other invalid arithmetic produces a reasoned numeric failure, not a fabricated value. Invalid input types/parameters remain preflight rejections.

### Accepted research market binding and data route

Builder decisions, 2026-10-03, including Q10/Q11 amendments. One qualified pool per investigation is the initial implementation scope, not a permanent product restriction. Bind research observations and numeric units to chain/network, underlying venue, pool address, token addresses/order, base/quote orientation, asset decimals, event schema/version and amount-conversion version. Evaluations additionally bind dataset revision, source records and timing/quality evidence. Unsupported or unqualified pool/event semantics cannot inherit support from another pool.

Keep Kuru execution-route identity and qualification separate. The recorded MOE/WMON investigation concerns a nad.fun pool indexed by Kuru's aggregate API, not a Kuru order book. WMON is not native MON. A Flow route may use another pool or several pools; research-pool support alone establishes neither that route's prices nor fillability. The [Probe A report](../../prototypes/EDGE_OS_PROBE_A_RESULT.md#data-and-frozen-configuration) owns that historical binding and its limitations. This decision does not select MOE permanently or authorize fresh collection.

Use Envio event history with QuickNode corroboration as the initial route. Qualify each adopted market's event meaning, chain ordering, duplicates, amounts, units, completeness and point-in-time suitability. Preserve source/collection identities and sampled-versus-complete corroboration. Reconstructed research with explicitly assumed delivery can finish as a limited research result; it cannot establish historically attainable execution or historical finality. Before qualifying evaluation, check schedule/partition/sample feasibility and missingness against the declared claim. No new broad research round or Probe A rerun is required.

### Accepted claim-specific support and readiness gates

Builder decisions, 2026-10-03, including Q12 amendments. The [independent evidence/authority ADR](../../adr/0002-separate-evidence-and-financial-authority.md) records the rationale. Define readiness transitions now and keep unproved gates closed. Required evidence follows the declared claim: support for an observed/predictive effect is separate from support for a tradable capture strategy. Apply costs and execution assumptions where the claim requires them. Illustrative costs are sensitivities, not proof of achievable net returns. Use the accepted outcomes/controls below. Use the accepted statistical-support policy below; its exact method profile and statistical qualification remain required before formal inference.

| Gate or transition | Accepted requirement |
|---|---|
| Draft → compiled revision | Supported, well-formed adopted meaning under the exact semantic version and real research binding. No research support or authority follows. |
| Data → qualified evaluation inputs | Required fields, units, coverage and timing are qualified for the declared analysis. Assumed historical delivery restricts the claim instead of becoming observed delivery. |
| Evaluation → supported effect | Evidence passes the declared effect's sample, comparison and applicable validation requirements. Do not relabel this as a capture strategy or promise causality. |
| Evaluation → supported capture candidate | Exact revision additionally passes applicable cost, execution, sizing/capacity and validation requirements for its capture claim. Unknown required assumptions block that claim. |
| Capture candidate → paper-ready | Separately qualify forward inputs, stale/missing behavior, accounting and the declared paper fill/cost model for the exact revision. Diagnostic collection may precede readiness if labeled separately. |
| Supported executable revision → execution-ready | Separately qualify the intended adapter/route and remaining Probe B authority, denial, recovery and revocation checks under the [live-trading contract](#live-trading-optional-trials-and-forward-learning). Historical support may remain absent, unfavorable or inconclusive for either a trial or ongoing live operation. This is operational eligibility, not active financial permission or an evidence-support finding. |
| Execution-ready → permitted financial action | Active user-approved mandate, exact revision/policy binding and passing deterministic plus wallet-policy checks. Keep revocation and pending exposure behavior under the execution contract. |

These are separate evidence findings, not an automatic linear funnel: effect research can finish without a capture candidate, and an unresolved report can finish the user job without any readiness transition. The legacy draft state name `VALIDATED_FOR_BACKTEST` cannot imply both input qualification and supported research; the build brief/frontend wording must map each accepted gate distinctly. A score or determinate Boolean cannot promote a failed gate.

Evidence status, operating purpose and execution permissions are separate records. Unfavorable, absent or insufficient backtests block a claim of demonstrated support; they do not automatically prohibit a user-authorized trial or ongoing live operation. Preserve the findings and reasons instead of changing a failed evidence gate to PASS. A trial is already live and is optional; continued trading grants no automatic evidence promotion or permission expansion. Exact machine fields remain build-brief decisions; the [accepted live user journey](#accepted-live-user-journey-and-display) controls presentation.

Research/UI implementation need not wait for every execution gate. It still requires the relevant accepted design/build brief and separately authorized implementation task; this planning acceptance authorizes neither code nor prototype runs. Execution readiness and active financial permission remain separately gated. The real MOE result stays UNRESOLVED with no candidate and no paper/execution permission. New authored fixtures and controlled execution cases remain separate from its recorded research.

### Accepted effect outcomes and comparisons

Builder decisions, 2026-10-03, Q13/Q14 with amendments. These definitions apply prospectively to the first production effect investigation, not retrospectively to Probe A. The [focused fixtures](../../EDGE_OS_RESEARCH_CONTRACTS.md#effect-outcome-and-control-acceptance-fixtures) are authored requirements and unrun.

**Decision clock.** Freeze the exact decision frequency and schedule alignment before outcomes, along with predicted direction, horizon and reference selection. This schedule is separate from both five-minute feature resolution and worker frequency. For each scheduled decision time `d`, required signal information must be qualified as available by `d`; otherwise preserve the ineligible opportunity and reason. An assumed historical delivery boundary permits only an explicitly limited reconstructed result, not proof of attainable historical prediction/execution. Do not shift a decision retrospectively to accommodate a late input or favorable outcome.

**Target response.** Offer 30 minutes as a visible user-adopted target-horizon preset, not a permanent restriction or exact holding duration. For adopted horizon `H`, select the first qualified trade by chain ordering in start window `[d, d + 1 minute)` and the first qualified trade in end window `[d + H, d + H + 1 minute)`. Response is `end_price / start_price − 1`, in the declared pool's quote/base price convention. Preserve both trade identities/timestamps, target horizon and actual elapsed time. These raw-trade outcome references do not change feature bucket resolution. They are observed pool-price responses, not achievable fills, a simulated position or portfolio returns.

A missing reference is a missing outcome. Keep the scheduled opportunity and reason; never widen the window, carry a price or assign zero response silently. Report coverage/missingness by group and time, including any restriction of conclusions to observed outcomes and possible selection bias. Use the accepted statistical-support policy below to address overlapping response intervals and dependent observations; its exact method profile and qualification remain pending.

**General control.** Use evidence-qualified FALSE opportunities from the same pool, declared schedule and outcome windows, with the same qualification rules. Report triggered results, control results and their difference. Keep UNKNOWN and evidence-ineligible opportunities separate: a determinate FALSE with missing hypothesis-essential evidence is not a qualified control. Control outcomes are observed responses, not zero returns merely because a strategy would make no entry. This estimates association; it does not establish causality.

**Incremental volume comparison.** A claim that volume adds information beyond price requires a predeclared comparison holding the price condition constant, separate from the original rule's general FALSE control. For a conjunction of price condition `P` and volume condition `V`, compare qualified opportunities with `P=TRUE, V=TRUE` against qualified opportunities with the same `P=TRUE, V=FALSE`, under identical outcome clocks and qualification. Retain the original general control separately, and keep unknown/ineligible inputs out of both qualifying groups with reasons. Other rule forms require an explicit equivalent comparison; do not invent it after outcomes. This tests the declared incremental association, not a causal contribution of volume or an automatic change to the original strategy.

The reason for these choices is to separate an after-information response from prior movement and to distinguish general market rises from the declared rule's comparison. Capture claims require their own position/accounting outcomes, costs, exposure and execution assumptions under the accepted readiness gates. Use the accepted primary statistic and validation policy below. Exact method-profile parameters and empirical statistical qualification remain unresolved requirements.

### Accepted statistical-support policy

Builder decision, 2026-10-03: Q15 A, Q16 A and Q17 A, with clarifications. This defines conditions for a formal effect-support claim, not conditions requiring historical tests, paper trading or graduation before live operation. Follow the accepted [single live flow](#live-trading-optional-trials-and-forward-learning) and [live display](#accepted-live-user-journey-and-display). No inference spending, code, prototype or financial action is authorized.

**Primary measure.** Use triggered-minus-control mean response difference for the declared effect, with the separately adopted price-held-constant comparison for volume incrementality. Freeze predicted direction and minimum relevant difference before inspecting outcomes. Show medians, missingness and results across time as diagnostics. A favorable diagnostic cannot replace a failed primary test. Report the effect's magnitude and uncertainty, not a profitability probability. Absolute directional claims also require evidence matching their wording; a relative contrast alone cannot prove that triggered prices rise.

**Dependence-aware uncertainty.** Retain complete scheduled opportunity records and jointly account for contiguous time dependence, overlapping outcome windows, group labels, missingness and shared comparisons. Specify and version the exact uncertainty/test method, assumptions, block-length selection, sensitivity checks and behavior for sparse groups, short history and unstable results before a formal evaluation. Use elapsed-time split boundaries; exclude outcome windows crossing protected partitions before reading their labels. Qualified earlier feature history may supply warm-up. Chronological separation does not by itself establish independent observations or future stability.

The builder selected the [STAT-Q01 candidate](../../EDGE_OS_RESEARCH_CONTRACTS.md#selected-stat-q01-candidate-for-qualification) for qualification only. Its exact remaining settings and statistical behavior remain a named builder-owned requirement. Formal statistical support is unavailable until its checks pass; this optional qualification does not block the core build, descriptive research or independently eligible, user-approved live trading. Qualify statistical behavior on dependent observations and known no-effect examples, including the complete selection procedure; proving code execution or deterministic replay alone is insufficient. No universal sample floor or block length is adopted from Probe A or a course.

**Comparison family and confirmation.** Freeze every validation comparison used to select the finalist and the selection rule before validation outcomes. Apply Holm correction across that entire family, including failed comparisons with valid test results. Preserve invalid/uncomputed comparisons and their reasons; they cannot silently disappear or become invented favorable results. The exact profile must define how such failures affect family conclusions. Keep all exploratory trials in the ledger separately; logging is not statistical correction. The adopted nominal family-wise error setting is 5%, conditional on valid underlying inference. Ordinary confidence intervals are not automatically simultaneous intervals.

Select at most one eligible finalist under the frozen rule. Freeze its exact revision, outcome/control, test and acceptance criterion before one protected holdout confirmation at the adopted nominal 5% setting. Preserve all access. After failure or inadequate evidence, permit no runner-up substitution under the same holdout. Changed meaning requires new lineage and genuinely unseen confirmation evidence or unresolved support. Existing Probe A holdout outcomes remain unopened.

**Useful completion and independent permission.** If assumptions, coverage or inference qualification fail, produce the descriptive report with observations, controls, diagnostics, every variant, limitations and a named next step. Leave the statistical-support claim UNRESOLVED without blocking completion of the research journey. Evidence status remains separate from compilation, operational readiness and active financial permission. Absent, unfavorable or unresolved statistical support does not itself prohibit direct ongoing live trading or an optional live trial under the accepted live contract. Missing required current inputs, unsupported executable rules, broken accounting or unproved execution authority still block the affected action. User consent cannot turn failed evidence into supported evidence.

The [method-profile and focused qualification requirements](../../EDGE_OS_RESEARCH_CONTRACTS.md#stat-q01-method-profile-and-qualification) are authored and UNRUN. Probe A remains accepted and closed, with original sample settings, findings and numerical conventions preserved.

The search can test whether a declared condition predicts continuation or reversal over the allowed horizon. It must account for the number of variants tested. It must reject results that fail the declared statistical, temporal, execution, or complexity gates.

This design does not assert that momentum, reversal, social attention, or wallet behavior creates a real edge. Those are hypotheses.

## 11. Dangerous claim and prototype

### Dangerous claim

> Edge OS can turn a messy market request into inspectable hypotheses and a typed strategy without silently inventing assumptions. It can also reject a plausible false edge before the result reaches capital.

If this claim fails, Edge OS becomes another prompt-to-bot or backtest generator. The team must test this claim before building the full application.

### Accepted Probe A evidence and production implications

On 2026-10-03 the builder accepted and closed Probe A for the revised bounded research-process claim. Read [the result report](../../prototypes/EDGE_OS_PROBE_A_RESULT.md#builder-acceptance-and-closure-2026-10-03) for the acceptance boundary and execution evidence. Retained checkpoint 1 covers tested interpretation, clarification, compilation/reload and known-invalid-input rejection. Checkpoint 2 covers an actual two-call Hermes investigation of reconstructed MOE/WMON pool history, one hypothesis, four predeclared variants, complete attempt/evidence reconciliation and an honest `UNRESOLVED` result. It establishes no supported candidate.

The original historical-delivery/finality claim remains unresolved. Availability delays are reconstruction assumptions. The two-day partition cannot satisfy both 30-outcome sample groups; this tests insufficient-evidence handling, not candidate qualification. Missing reference trades, illustrative costs, omitted execution effects and current-volume selection bias remain visible. Holdout outcomes stay unopened. Known leakage checks do not establish general overfitting detection or causality. Demand and autonomous execution remain unproved.

Use these findings in production design:

- Bind compiler identity to the real venue, market/pool, asset order, quote and units before claiming a deployable strategy. The probe's synthetic/native-MON templates and separate MOE/WMON bindings do not supply that artifact.
- Separate observed event history from assumed delivery and execution timing. Explain gaps and omitted costs instead of presenting pool-gross associations as achievable trader PnL.
- Check proposed sample feasibility before evaluating a run intended to qualify a candidate. Keep descriptive/mechanics investigations explicitly separate. No universal sample floor is adopted from this probe.
- Preserve every attempted variant, contrary result, missing observation and eligibility reason. An unresolved report remains a complete useful research outcome.
- Keep template compilation, evidence support, paper readiness and execution permission distinct. Probe B supplies no research support, and Probe A supplies no delegated-execution proof.

No further research run is required merely to close Probe A. A longer support test, broader grammar or forward collection needs its own prospective question and approval. The full dangerous-claim acceptance checks below remain unpassed.

### False-edge case

The prototype uses one deliberately attractive result whose ordinary backtest looks convincing. The rejection path must expose at least one real failure such as:

- engagement information collected after the historical decision time;
- multiple-testing inflation;
- a holdout failure;
- unstable parameters;
- unrealistic spread, slippage, depth, or latency;
- a live-data feature that cannot be reconstructed historically;
- a strategy meaning that changes between backtest and execution.

The demo must show the same case before and after the failing control is applied.

### Controlled survivor

The prototype can produce at most one controlled survivor for paper testing. Zero survivors is a valid research result.

If a survivor exists, the system compiles it into a `StrategySpec`, applies deterministic risk limits, and prepares one execution intent.

### Exact Monad operation

Builder decision, 2026-10-03, Q20 A: the initial adapter direction is Kuru Flow fixed-input swaps, with bounded input and minimum received amount. The [initial-adapter ADR](../../adr/0006-kuru-flow-initial-spot-adapter.md) records this bounded scope and its alternative. This is a routing interface, not a Kuru order-book limit order. It may use external pools or Kuru books. The research pool and actual execution route have distinct identities and qualification. The initial adapter exposes no resting-order action.

Refine the [existing Probe B plan](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#5-probe-b-delegated-monadkuru-action) around one controlled fixed-input swap, independent of any supported research candidate. Before execution, verify the actual network/deployment/ABI, input/output tokens and decimals, route/program restrictions, recipient, input amount, minimum output, fees, native value, approvals and gas. Qualify the actual quote/build shape and independently enforceable Privy restrictions; an outer-entrypoint allowlist does not prove restrictions on opaque route bytes or token notional. Unknown applicable restrictions leave the corresponding execution claim unproved.

Freeze quote/input freshness, local intent expiry and mandate expiry. These local rules cannot establish an unverified onchain swap deadline or revoke a broadcast transaction. Native MON, WMON, ERC-20 amount limits and gas are distinct. Consent, cumulative accounting, scoped stops and renewal directions are accepted below; exact numeric profiles and route/provider enforcement remain qualification/build-brief requirements.

Probe B requires one separately approved fixture mandate and signer, offline permitted execution without another signature, deterministic and independent provider denial, durable recovery without a duplicate economic action, verified owner removal and an isolated post-removal denial. Preserve pending transactions and acquired/residual assets. Approval/setup actions need their own permissions and bounds.

Prefer testnet only if the complete selected Flow path is verified. Testnet order-book addresses do not prove a testnet Flow path. If only mainnet is verified, obtain the builder's separate approval for the exact controlled amount and financial scope before execution. This planning decision authorizes no wallet action.

Record a successful swap using its confirmed receipt, decoded applicable events and actual asset/accounting changes. One action proves only that tested operation/authority/recovery boundary; it does not prove the complete entry/exit strategy, ongoing live operation, profitability or production security. Both intended entry and exit semantics need their applicable qualification before unattended rules use them. Assensus remains evidence of a narrow reusable delegation pattern, not Monad–Kuru proof.

## 12. Authorization and risk design

### Model and research roles

The [model/execution boundary ADR](../../adr/0005-model-and-execution-authority-boundary.md) records the core authority separation; it does not approve a service topology or prove credential isolation.

The LLM and research agents can:

- classify input;
- propose hypotheses;
- explain missing information;
- propose a strategy specification;
- summarize validation evidence;
- prepare a bounded execution intent.

The LLM and research agents cannot:

- add undeclared data or parameters;
- modify the deterministic validation decision;
- override the risk engine;
- access a wallet secret;
- authorize a Privy request or submit a transaction directly;
- increase the approved notional;
- modify a persisted intent or expand a mandate.

### User-owned delegation

The user reviews the strategy, risk limits, policy summary, expiry, and permitted actions. The user explicitly creates or resumes the wallet assigned to this trading agent and approves its restricted signer. Selecting another agent's wallet is not an activation option. Routine actions within that approved mandate need no further signature.

A new strategy version or expanded permission requires a new approved mandate. Deployment readiness is separate from `READY_FOR_BOUNDED_EXECUTION`. A validated strategy with no active mandate has no execution authority.

The execution host can authorize Privy requests. It cannot use the user's wallet private key. Application credentials and the authorization private key remain in the backend secret store. Neither the LLM, browser bundle, logs, nor receipts receive them.

<a id="experimental-live-authorization-and-forward-learning"></a>

### Live trading, optional trials and forward learning

Builder direction, 2026-10-03: offer one live-trading workflow with an optional trial setting. "Experimental live" means a live trial for learning, not a lower tier or compulsory prerequisite for ongoing trading. Users may start ongoing live operation directly or continue after a trial, even when historical support is absent, unfavorable or inconclusive. Favorable backtests, paper trading and graduation are not required. Explain the evidence and material limitations; retain prior findings without automatically granting an evidence-supported or profitable-strategy label.

Before unattended execution, require:

1. An exact immutable, supported strategy revision with clear entry, exit, timing and pause/failure behavior. An exploratory story or unsupported action cannot substitute for executable meaning.
2. User review of the evidence status and material limitations. For a chosen trial, also record its learning objective, expected observations and challenging observations. Ongoing trading does not require an artificial experiment objective or minimum confidence score.
3. Explicit live-trading consent and a mandate defining the wallet, network, permitted actions, allocated capital, per-action and aggregate limits, approvals/gas, duration, action count and stop/revocation behavior. The user chooses settings within declared platform and verified provider constraints. The platform must not automatically fund every unproven idea. A trial may add an earlier stopping point within those permissions; ongoing operation remains bounded by the mandate and its expiry.
4. Qualified current inputs, accounting, tested execution semantics and the applicable Probe B authority, policy-denial, recovery and revocation evidence. Preserve freshness, liquidity/price checks, duplicate prevention and independent wallet restrictions.

Historical uncertainty may be accepted for either operating purpose; unknown executable meaning, unavailable required current inputs, broken accounting or unverified authority still deny the affected action. Deterministic admission checks operational eligibility, the exact evidence/acknowledgement record and active permissions. It never rewrites an unfavorable validation decision or bypasses a wallet policy. Direct discretionary trades chosen by the user are a different workflow from an unattended agent executing rules.

On "Continue trading", reuse the same strategy revision and durable deployment/accounting lineage. Existing authority is sufficient only while it is active and covers the requested actions; an expired mandate or change beyond its permissions requires an approved extension/replacement and verified policy binding before new actions. A display-purpose change alone needs no new signature. Removing a user-adopted trial stop requires explicit user review, even when wallet permissions are unchanged. Changing purpose does not reset consumed allowances, losses, pending intents or exposure. Counter periods and any new allocation follow explicit permission rules, not a trial-to-ongoing label change.

Allocated capital can be lost in full. Price guards, loss-triggered pauses and revocation do not guarantee an exit or undo pending actions. Record residual exposure and failed exit attempts rather than promising a loss ceiling that market execution cannot enforce.

Save prospective observations and lessons through the [forward-learning evidence contract](../../EDGE_OS_RESEARCH_CONTRACTS.md#observational-investigation-and-forward-learning-evidence). The agent may propose a revised hypothesis or strategy afterward. Preserve the earlier records; a changed executable revision needs renewed approval and never inherits expanded authority automatically.

The single live flow, Flow operation direction and consent/limits/stops/renewal behavior are recorded. Qualify actual provider enforcement and freeze numeric profiles before claiming financial readiness or permitting affected live use. Implementation and prototype work still need their separate scoped approvals. Research/UI scope can receive separate design/build-brief approval. Do not claim universal numerical "industry-standard" limits or verified enforcement from documentation alone. These decisions authorize no capital movement and do not qualify the MOE result for execution.

<a id="accepted-activation-positions-and-shared-wallet-accounting"></a>

### Accepted activation, positions and agent-wallet accounting

Builder decisions, 2026-10-03, Q21 A, amended Q22, conditional Q23 A, Q24 A, Q25 A, amended Q26 A, Q27 B, Q28–Q30 A and Q31 A with attribution/enforcement amendments. These are accepted requirements, not implemented or qualified behavior. The [focused accounting checks](../../EDGE_OS_RESEARCH_CONTRACTS.md#live-wallet-accounting-acceptance-checks) are unrun. [ADR 0003](../../adr/0003-durable-shared-wallet-accounting.md) preserves the earlier shared-wallet rationale.

Amendment accepted by the builder, 2026-10-05: [separate agent wallets and funding](#accepted-agent-wallet-ownership-and-funding) replace cross-agent shared-wallet ownership and reservations. [ADR 0007](../../adr/0007-separate-user-owned-agent-wallets.md) records the trade-off. Q21–Q31's position, permission, stop, renewal, cost and recovery rules remain in force within each agent wallet. The former heading anchor remains only for existing links; it does not retain shared-wallet authority.

Activation uses one grouped review. Keep consequential settings visible and provide expandable explanations. The user must adopt allocated capital, limits, permitted actions and expiry for the exact strategy revision, wallet and network. Never infer permission to use the wallet's full balance. Show evidence and operational limitations separately from this financial permission.

Support multiple simultaneous positions across supported markets and strategies. Track each position and enforce its limits together with aggregate wallet limits. Additions are permitted only for explicitly supported strategies with adopted sizing rules and permissions. Each addition updates position size, cost accounting, aggregate limits and exit reservations. Preserve its individual intent/receipt and strategy attribution. A repeated signal cannot silently authorize an addition. This does not approve additional strategy types. One qualified pool per research investigation remains the initial research binding scope; several positions do not broaden that investigation's inputs or silently authorize another execution route.

Coordinate reservations across all positions and pending actions in the assigned agent wallet. The same funds cannot back two spending commitments. Other agents' wallets supply no funds or permission to this agent. Preserve positions, consumed allowances, pending actions, reservations and remaining exposure through recovery. External wallet activity or discrepancies require reconciliation before the affected action can pass accounting checks.

Keep allocated capital, reusable proceeds, cumulative trading allowances, swap-attempt counts and actual gas costs separate. Finite allocation and cumulative allowances are accepted. Returning proceeds, restarting a worker or continuing after a trial does not replenish allowances. Record amounts with asset identity, raw amounts and decimals; never sum raw amounts of different tokens. Apply the accepted renewal, submission/spending and cost conventions below.

Position count and transaction concurrency are separate. The one-open-position proposal is rejected. Probe B's one controlled action bounds its experiment only.

Automatic recovery from a temporary fault is permitted only after successful freshness, reconciliation, accounting and authority checks. Recovery must preserve user-imposed stops and cannot create new permission. It cannot silently remove an adopted trial stop, loss stop, exhausted limit, expiry or revocation.

#### Accepted agent-wallet ownership and funding

Builder-approved documentation amendment, 2026-10-05. Each trading agent has one separately funded user-owned wallet. It may maintain multiple supported positions within that wallet and its adopted limits. Agent A cannot spend, transfer or sell assets from Agent B's wallet. An account overview may combine records and qualified valuations, but never combines spending authority or treats one wallet's balance as another's available funds. The model receives no wallet credentials. Bind every intent, position, approval and execution request to the owner, agent, wallet, network, exact strategy revision and mandate; independently qualify cross-agent signing denial before real use.

**Creation and recovery.** Create an empty wallet when the user creates a trading agent from supported reviewed rules. Research and saved strategy drafts require no funded wallet. Creating a wallet starts no trading and grants no signer access. Preserve the agent/setup identity through cancellation or failure; reconcile an unknown creation result before retrying so it cannot create a second wallet or overwrite the existing binding. Wallet creation may complete before funding or permission, with that state visible.

**Funding.** Provide Add funds to the named agent through an explicitly reviewed connected-wallet transfer or a deposit address/QR code. Show destination, Monad network, supported asset, amount and fees. Initially accept the strategy's declared trading asset and native MON for network fees; the WMON spot examples keep WMON and MON separate. Bridging, card purchases, automatic wrapping/conversion and gas sponsorship are not selected by this amendment. Unsupported deposits do not silently become usable strategy capital. Show waiting, confirmed, failed or outcome-unknown transfers with transaction references; confirmed deposits are capital flows, not profit.

**Permission and top-ups.** Funding does not activate the agent, grant use of its full balance or raise/reset allowances. Activation reviews the exact agent wallet, adopted rules, allocated capital, limits, actions, expiry and stop effects. A running agent may use a confirmed top-up only within its existing allocation and remaining permissions. User/trial/loss stops and expired/revoked authority remain in force. Show insufficient trading funds or network fees specifically; never borrow from another agent. Temporary funding faults may recover only under the adopted recovery rules after reconciliation, freshness and current authority checks. Deposits do not remove exhausted limits or create new approval.

**Owner withdrawals and transfers.** Keep owner-controlled wallet access and an explicit withdrawal review separate from agent trading access. Identify the asset, amount, recipient, network fees, available holdings and pending commitments. Recheck and reconcile affected balances/reservations before further agent actions. Pending or unknown transfers cannot appear completed or release commitments. Preserve capital-flow history and prevent new agent work from racing an owner withdrawal. An external owner transfer requires reconciliation, not reassignment of losses or borrowed inventory. A token withdrawal does not sell the token, stop the agent or authorize a later re-entry. Transfers between agent wallets require explicit owner authorization; the agent cannot move funds between them automatically. Exact owner-action and pending-transaction handling remains a qualification requirement, not a promise to cancel an already broadcast transaction or lock the owner out indefinitely.

**Removal and display.** Verified signer removal blocks new agent submissions for that wallet without removing the owner's access to remaining assets. Show pending transactions and residual holdings until reconciled. An agent can be stopped before its first position exists, independently of other agents. Agents show wallet balance, funding action, fees, permission and operation status; Positions provides direct cross-agent inspection with exact agent/wallet filters and contextual conversation. One agent's position panel shows only that position's actions. Combined activity belongs in the account overview, with ownership labels. Keep compute credits separate from trading funds.

**Evidence and scope.** [Clawpump's guide](https://www.clawpump.tech/guide) describes separate agent and billing wallets. [Almanak's deployment documentation](https://platform.docs.almanak.co/deploy.html) describes configuration review but shares a Safe across agents on a chain; that wallet architecture is not adopted. [Privy's multiple-wallet documentation](https://docs.privy.io/recipes/hd-wallets) establishes a possible implementation route, not qualified isolation; shared-seed HD wallets and broad backend access require explicit security analysis. Exact wallet/signer/policy support, ownership, retries, funding, withdrawals and removal require runtime qualification. The single frontend experiment uses labeled authored fixtures only. This amendment selects no new provider, funded transaction, production implementation or additional prototype phase.

#### Accepted allowance units and exit capacity

Buy allowances measure cumulative fixed-input amounts in the declared quote asset. Sell allowances measure cumulative fixed-input amounts in the declared base asset. Maintain asset-specific position and aggregate wallet records, including consumed and reserved capacity. Native MON gas is separate from WMON and other trading assets. Aggregate exposure limits use a user-adopted reporting unit and qualified valuation sources/freshness rules; unknown required valuation blocks the affected action. Per-asset limits remain independently enforced.

Sell permission covers only attributable inventory of the approved position/strategy within finite adopted limits. Unrelated wallet holdings do not become sale permission. Before an entry or addition, reserve approved sell capacity for the entire resulting inventory, along with the required exit-action capacity and native gas budget. Apply position and agent-wallet limits atomically. The intended exit, including applicable token mechanics and any multiple-swap sizing, must be supported and have approved capacity before entry admission.

`EXIT-CAP-Q01` qualifies sufficient authority and capacity under the explicitly selected permission model. It does not require an acquisition upper bound for every possible model. Record the model, adopted terms, attribution rules and enforcement boundary before admission. Incorporate qualified extra token debits/fees and intended exit sizing in capital, action and gas checks. Unsupported token mechanics or unknown required capacity deny the entry/addition.

For a **fixed token-quantity sell ceiling**, consumed sell allowance plus outstanding sell reservations must not exceed that ceiling. Reserve reconciled unsold inventory plus a qualified conservative upper acquisition bound for pending entries/additions. A minimum-output guard or expected quote supplies no upper bound. Deny admission when the bound or required capacity is unknown. After receipt reconciliation, replace the bound with actual attributable inventory and release only demonstrated unused reservations.

Q31 A selects **explicitly preapproved position-inventory-based sell permission** as the initial design direction, subject to qualification. The prior adopted rule covers attributable inventory from confirmed approved acquisitions and additions, adjusted for confirmed exits and other relevant qualified balance changes. Preserve actual asset credits/debits and link them to the approved action, strategy revision and position. Exclude unrelated transfers/deposits and other positions' inventory from that strategy's sale authority. A receipt determines quantity under prior permission; it creates no new permission.

Coordinate allocations and reservations across all positions in the assigned agent wallet, network and asset. The same inventory cannot be attributed or reserved twice; another agent's wallet is never a fallback source. Compare attributed holdings and reservations with reconciled wallet availability before preparation and submission. External outflows and token-mechanics changes must be reconciled. When their effect on attribution is ambiguous, deny affected actions until resolved; do not silently assign losses, reallocate another position's inventory or classify external flows as trading results. Burn, transfer-fee, reflection and rebase behavior require asset-specific supported rules or an explicit unsupported/unresolved verdict.

Keep supported assets/routes, recipient, buy capital/cumulative allowances, action/gas budgets, exposure/loss limits, operational checks and expiry intact. Continue measuring cumulative sales in base-asset units and preserve their history. If an adopted fixed quantity ceiling also constrains this model, its applicable ceiling/bound checks still apply. Q31 selects no arbitrary full-wallet sale permission or automatic allowance increase.

Qualify the smallest workable enforcement design. Separate application accounting/attribution checks from independently enforced wallet restrictions; do not assume Privy reads the position ledger. Establish how acquired inventory stays covered under prior permission, how reservations prevent double sale, and which exact restrictions each layer enforces. A wallet balance or broad token allowlist is not position attribution. An app check or additional authorization signature alone cannot be described as independent provider verification of that attribution. Required but unenforceable restrictions leave the corresponding capability unsupported/unresolved. If another approver component, contract wrapper or changed authority architecture is necessary, present its alternatives and return the material choice to the builder before adoption.

After a fully reconciled receipt, update actual inventory, reservations and cost accounting under the adopted model. Release only demonstrated unused reservations; consumed allowance stays consumed. If a receipt breaches the model or approved capacity, retain the breach and residual exposure, block affected new actions and reconcile. Never expand authority or bypass limits to close it. A separately approved remedy may be required.

The inventory-based model is selected as intended behavior, but no enforcement mechanism or sufficient exit capacity is qualified for the selected Flow direction. Entry/addition admission remains unqualified until its model-specific checks and intended exit checks pass. [EXIT-CAP-Q01 findings and remaining work](../../EDGE_OS_RESEARCH_CONTRACTS.md#exit-cap-q01-permission-model-qualification) record documentary facts separately from required runtime tests. A fixed-ceiling acquisition bound is still required wherever that additional ceiling depends on it. No partial-coverage policy, wrapper or automatic permission increase is approved. Reservations do not guarantee later execution or affordable gas.

#### Accepted renewal, attempts and position cost

Q28 A: preserve cumulative consumption, reservations, positions, pending actions and losses through permission renewal. Show the old terms, proposed terms and additional authority explicitly. Expiry extension changes time only; it does not replenish any allowance. No automatic periodic replenishment is selected. Keep the same accounting lineage and verify changed policy/mandate binding before using additional authority. A requested reduction must account for outstanding commitments; it cannot erase them. Renewal cannot silently clear an adopted stop.

Q29 A: distinguish economic actions, provider requests and actual spending. Reserve trading input, a swap-attempt slot and gas before submission. Count a distinct swap submission once when broadcast becomes possible, including a reverted transaction. A confirmed successful swap consumes its reconciled trading-input amount. A confirmed revert consumes the attempt and actual gas, with unused input reservations released only after reconciliation. Unknown outcomes retain capacity and original references until reconciled; they are not free retries or known zero spend.

A qualified resend preserves the original signed transaction bytes and transaction hash. Record each provider request separately under a bounded transport/request budget; resending that same transaction does not become a new economic action. Exact byte/hash preservation and selected provider behavior require qualification. If the transport cannot preserve the original signed transaction/hash, this resend claim is unqualified. Replacements, changed transaction fields, fresh routes or new transactions need separately defined authority; no automatic replacement is approved. Actual gas and provider charges are separate from trading-token spending and attempt counts. A proved pre-broadcast denial is not a broadcast attempt or actual trading spend.

Q30 A: use weighted average acquisition cost for each position while retaining every acquisition, addition and exit record. Additions update inventory and its acquisition-cost basis; a partial exit removes the proportional average cost basis. Preserve realized results, estimated unrealized results and external capital flows separately. Deposits, withdrawals and transfers do not become trading profit or permission to attribute unrelated holdings to a position.

Use reconciled acquisition consideration and qualified trading fees for cost basis. Record actual native gas separately and include it in common-unit net results only through qualified conversion, exactly once. Keep gross flows, fees and net amounts auditable without double counting. Loss checks use net tracked strategy results at the adopted position and aggregate wallet scope. Marked unrealized results remain estimates, not achievable-fill claims. Unknown required costs, basis or marks remain unknown and deny affected risk admission; they cannot become zero or profit. Exact cost/fee attribution, valuation timestamps, capital-flow reconciliation and threshold profiles are focused build-brief/qualification requirements, not executed evidence.

#### Accepted initial wallet submission queue

Use one durable submission/reconciliation queue per agent wallet and network across its positions. Initially allow one unresolved economic transaction in that queue. This is an implementation choice, not a chain requirement or permanent product restriction. Multiple positions and concurrent monitoring remain supported. An unresolved transaction in A's wallet does not by itself block B's separate wallet; platform-wide service faults still apply where relevant.

Choose eligible exits before entries/additions that have not been submitted. Within that priority class, preserve a deterministic order. Recheck current revision, authority/policy, expiry, stop scope, inputs/quote freshness, inventory, reservations and limits at submission. A queued payload cannot retain eligibility from an earlier check. A stale or expired intent must be denied/reprepared through the approved intent rules, not silently altered and submitted.

Exit priority cannot preempt a broadcast transaction or bypass `SUBMISSION_UNKNOWN`. Reconcile the original durable transaction/provider references and accounting before another economic action. Preserve reservations while its outcome is unknown; never interpret a timeout as permission for a duplicate. Recheck current eligibility afterward.

Show queued action, position/deployment, waiting time, blocking reason and delayed exits. Qualify contention, priority, freshness, unknown-outcome recovery and measured delays on the supported trading path. If measured delays make that path unsuitable, move to wallet-coordinated concurrent submissions with separately qualified nonce/reservation/recovery behavior. Do not increase concurrency silently or claim that the initial queue proves suitable timing.

### Two enforcement layers

Deterministic code checks:

- specification hash;
- unchanged validation state, acknowledged material limitations and operational eligibility for the exact revision, independently of trial or ongoing purpose;
- active mandate, signer, and policy binding;
- market allowlist;
- maximum notional;
- reserved capital, aggregate exposure, loss limits, and action-count limits;
- source freshness and current portfolio state;
- price or slippage guard;
- expiry;
- wallet and network;
- duplicate intent;
- receipt status.

Privy's policy independently restricts permitted networks, contracts, signing methods, functions, and supported argument limits. The chosen network is either Monad `143` or testnet `10143`, not an implicit permission for both. The policy denies arbitrary transfers, unrestricted approvals, and unrelated calls.

Native transaction value is not ERC-20 order notional. The adapter must check token amounts, units, approvals, and every operation in a batch. Verify which limits Privy can enforce for the exact Kuru ABI. An unverified policy restriction remains `UNKNOWN` and blocks the corresponding execution claim.

Separate policy administration from the execution credential. The executor must not possess authority to weaken its policy. Check current policy content against the approved version before preparation and submission. Any changed or unreadable binding denies new execution.

### Pause, revoke, and pending exposure

Builder decision Q24 A: distinguish **Stop new entries** from **Halt all swaps**. Stop new entries denies entries and additions in the recorded scope; it allows only existing, explicitly preapproved exit rules. It is not an instruction to close immediately. An immediate-close action needs its own explicit supported instruction and permission. Halt all swaps denies every new swap in scope, including exits. Monitoring and reconciliation continue in both modes.

Every stop records trigger, affected position/deployment or agent-wallet/network scope, denied actions and remaining permitted actions. User controls must expose the selected scope; do not silently widen or narrow it. A position loss stop affects that position, a deployment/trial stop affects that deployment, and an aggregate agent-wallet stop affects that agent's positions. An agent/deployment stop works before any position exists and leaves other agents unchanged. An explicit Stop all agents command identifies each affected agent/wallet rather than treating the account overview as a shared wallet. Stopped positions may remain open.

| Trigger | Accepted action boundary |
|---|---|
| User selects Stop new entries | Deny entries/additions in the selected scope; existing approved exit rules may continue. |
| User selects Halt all swaps | Deny all swaps in the selected scope, including exits. |
| Adopted trial stopping point | Stop entries/additions for that deployment; allow existing approved exit rules. Trial completion does not mean all positions are closed. |
| Position or aggregate wallet loss stop | Stop entries/additions in the affected scope; allow existing approved exit rules. No automatic immediate liquidation or guaranteed realized-loss ceiling follows. |
| Entry allocation or buy allowance exhausted | Deny affected entries/additions; preserve exit reservations. |
| Required exit allowance, action capacity or gas exhausted | Deny the affected swap; retain residual exposure and explain the missing capacity. |
| Authority expired or revoked | Deny every new swap covered by that authority, including exits. |
| Required operational checks fail | Deny affected swaps until the checks pass; retain any separately adopted stops. |

Revocation requests owner-authorized signer removal and records the verified result. A local stop is not proof of Privy revocation. No exit can bypass revoked authority or failed operational checks.

Revocation cannot undo a broadcast transaction. The initial Flow adapter permits no resting-order action. Show pending transactions and residual positions until reconciled or closed. A later owner action requires its own authorization. Never report all exposure closed merely because the signer is gone.

## 13. Failure and degraded-service behavior

| Failure | Required product behavior |
|---|---|
| Input lacks necessary meaning | Return `NEEDS_CLARIFICATION` and name the missing fields. |
| Requested feature or action is unsupported | Return `UNSUPPORTED`. Do not invent an approximation. |
| Historical data is incomplete | Return `UNRESOLVED` or restrict the research window. Record the restriction. |
| X is unavailable | Stop any social-dependent hypothesis. A separately declared onchain-only run may continue; preserve its distinct lineage. |
| Historical X engagement is unavailable | Exclude the engagement feature. Do not use current counts as historical values. |
| Nansen is unavailable | Return `UNRESOLVED` for any label/cohort-dependent hypothesis. A separately declared raw-data hypothesis may continue; do not preserve the original validation status after dropping its essential feature. |
| Envio is delayed or incomplete | Stop the affected historical claim. Use RPC only as a stated cross-check, not as silent replacement for a complete index. |
| QuickNode is unavailable before submission | Test the public Monad RPC health check. Continue only after required reads and risk checks pass. Report the provider change. |
| Selected submission transport is unavailable | Prevent new submission. Preserve the intent and its expiry. Do not bypass Privy. |
| Kuru order-book updates have a gap | Mark local depth stale. Resynchronize before research or authorization continues. |
| Risk check fails | Return a risk denial with the exact failed rule. |
| User refuses delegation | Keep the deployment inactive. Preserve the research result without executing. |
| Privy policy denies the action | Record the denied intent, policy identity, and failed restriction when available. Do not weaken the policy or mutate the intent. |
| Privy signer or policy cannot be verified | Stop new execution. Do not substitute a local wallet key. |
| Submission times out or loses its acknowledgement | Record `SUBMISSION_UNKNOWN`. Reconcile the existing reference before any retry. |
| Worker restarts or another worker claims the deployment | Recover durable state and acquire an exclusive claim before evaluating another action. |
| Mandate expires or user revokes | Stop new execution. Show pending transactions and orders until they reconcile or close. |
| Transaction reverts | Show the failure and trace when available. Do not present it as execution proof. |
| Transaction is only proposed | Show the current state. Wait for the chosen confirmation state before marking settlement complete. |

## 14. User experience

Customer navigation uses Research, Agents, Positions and Funds. These are destinations, not compulsory stages. An existing user can inspect positions or funds directly. Research can finish without a strategy, wallet or trading permission.

Research contains request/scope, necessary clarification, adopted budget, progress, evidence and the saved conclusion. Show plain-language rules when supported meaning exists. Optional historical testing belongs to that strategy's review. Agents contains rule review, setup, activation and current operation. Positions and Funds expose the same owner-bound records used by contextual conversation.

Carry forward the checked v0.12.2 interactions: a clear next action in empty states, compact agent summaries with expandable rules, consequential activation terms visible, exact position-specific sale status, stops before a first position, and separate pending/confirmed/closed records. Funding, selling, stopping and withdrawing must state their different effects. The prototype's personal wallet is the connected source/destination; it does not establish another pooled Edge OS wallet or a production custody implementation.

Reviewer scenario selectors, simulated clocks/receipts and participant notes are test tools. Keep them outside customer navigation. Use a short demo notice for authored data. The real MOE report and separate example strategies must retain distinct identities; the report produced no selected strategy. Prototype layout is an implementation reference, not a fixed pixel design or proof of comprehension.

The interface must expose:

- assumptions;
- evidence source and time;
- missing information;
- variants tested;
- failed gates;
- degraded providers;
- the exact mandate awaiting approval and the actions it permits;
- the current signer, policy, expiry, pending exposure, and stop reason;
- owner controls for pause and signer removal;
- the difference between strategy evidence and transaction proof.

The user must understand a rejection without reading the architecture.

### Optional test on past prices

The existing prototype includes this interaction under an exact supported example strategy. Review and adopt the historical period, starting capital, trade size and cost assumptions before showing a result. Lead with simulated gain/loss, trade count, largest fall in account value and a balance chart; keep trades and calculation details accessible. Explain unavailable data or unsupported behavior and preserve the user's work. Let the user inspect, revise or save the result, or independently review live permission where operationally qualified. A favorable test grants no authority; an unfavorable or unavailable test creates no compulsory ban on live operation.

The current result is authored and labeled “Example result. No simulation has run.” Production must replace that example with a reproducible simulator that replays the supported rules, tracks cash/holdings and declared costs, preserves missing information and saves the exact revision, dataset and assumptions. Pool-price effect research, simulated account performance and real transactions remain different records. The [draft build brief](../../EDGE_OS_BUILD_BRIEF.md#5-narrow-historical-simulator) proposes the first bounded implementation; no simulator or realistic Kuru fill model is established by this documentation.

### Accepted live user journey and display

Builder direction, 2026-10-03: present one "Live trading" flow. Show agent state, evidence status and execution permissions independently. "Running" with "Limited live observations; edge remains unproven" is a valid presentation. Presentation labels do not define a new ordered confidence score or override the accepted evidence gates.

1. **Review the idea and rules.** Preserve the request, clarify stage-required meaning and show the exact supported strategy interpretation. An observational report can remain research-only.
2. **Choose the next action.** Offer historical testing where feasible, forward observation without capital, or live trading. Explain limitations without forcing the user through a backtest or paper-trading sequence.
3. **Review live settings and approve.** Permit either an optional trial with an agreed stopping point or ongoing operation within the approved mandate. Explain that both use real money and show evidence, permissions and possible loss before activation.
4. **Inspect the result.** Show actions, actual costs, gains/losses where accounting permits, failures, remaining exposure and findings. Favorable observations do not automatically become a validated edge.
5. **Choose what happens next.** Offer "Continue trading", "Review and adjust limits", "Revise strategy" and "Pause trading". Continuation follows the [live-trading authorization rules](#live-trading-optional-trials-and-forward-learning), including review of any changed trial stop. A changed strategy creates a new immutable revision for approval.

Avoid "Graduate", "Unlock live" or automatic green validation after a trial. Keep pause, owner revocation and remaining exposure understandable. The interaction prototype must cover continuation within current authority and continuation requiring revised permission, without simulating those cases as actual wallet proof.

### Accepted independent status display and one frontend prototype

Builder decisions, 2026-10-03, Q19 A and follow-up: use a persistent compact status summary with expandable evidence. Carry forward the accepted live journey; no new interaction-prototype phase is introduced. One builder-owned frontend prototype contains all interaction and comprehension checks, using the existing assignment in the shared probe plan. Its execution approval remains separate.

| Independent record | Required visible content |
|---|---|
| Agent state | Running, paused, recovering or stopped, with a specific reason and pending work. |
| Evidence status | Findings for the declared claim, including unproven/limited observations, failed tests and assumptions; never infer support from Running. |
| Execution permission | Active scope, consumed/reserved allowances, expiry, permitted next actions and residual exposure; absence/expiry is explicit. |

Use the real unresolved MOE report for useful research completion: no selected deployable revision or permission, all four variants and contrary evidence retained. Use labeled authored fixtures for direct live start, optional live trial, favorable but limited observations, continuation within current permission and continuation requiring changed permission. Fixtures are not actual wallet actions or research support.

Within the same prototype, test field-level clarification/change display, budget/variant visibility, understandable failures, evidence/source inspection, live settings review, multiple positions/adopted additions, scoped stops/removal exposure, queue delays, continuation/renewal and cost/capital-flow explanation. Users can review live settings once supported executable meaning exists without passing historical inference. Actual activation still requires operational eligibility and permission. Removing a trial stop requires review; a purpose label cannot reset allowances. The scoped plan uses accepted Q28–Q31 behavior with authored examples and labels the selected inventory-based direction separately from its unqualified enforcement.

The [single interaction prototype plan](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#one-frontend-interaction-prototype) owns its exact question, artifact scope, tasks and verdict criteria. Test with an active trader and a technically strong teammate when available; record comprehension failures and unavailable-user limitations. Prototype findings, execution approval, full specification/build-brief approval and implementation tickets remain separate.


### Accepted account views and contextual conversation

Builder-approved closing amendment, 2026-10-03. Provide direct account/position views and contextual agent conversation over the same durable position, allowance and action records. Neither channel owns a second ledger or permission model. Use the [accepted accounting rules](#accepted-activation-positions-and-agent-wallet-accounting) and [model/execution boundary](../../adr/0005-model-and-execution-authority-boundary.md). This accepts intended interaction behavior, not implementation, manual-close capability, wallet enforcement or prototype execution.

**Direct account inspection.** Show multiple positions with agent/deployment and strategy filters. Each position identifies its wallet/network, market/assets, attributed quantity, weighted average acquisition cost, realized result, estimated unrealized result and mark/update time where qualified. Show pending actions, residual holdings, permission/stop state and consumed/reserved allowances. Each agent-wallet summary separates holdings, currently available funds, reservations, remaining financial authority and native MON gas. The account overview combines labeled records without pooling balances or permission. Unknown costs/marks stay unknown; deposits/transfers remain capital flows. Expand a position to its exact strategy revision, acquisitions/additions/exits, recorded decision evidence, intents and receipts. Opening account records requires no conversation.

**Account questions and exact context.** Support questions such as "What positions are open?", "Why did this agent buy?", "How much can it still spend?", "What is waiting, and why?" and "What did this position gain or lose after costs?" Answers identify account/network scope, record update time and links to the relevant positions, recorded decisions, allowance records and receipts. Explain stale, missing or unreconciled records. Read-only questions create no financial action. Explain recorded decisions and supporting inputs without claiming to expose private model reasoning.

"Ask about this position" attaches that exact position record. Keep a visible context label and a link back to the position, including position identity, agent/deployment, strategy revision, wallet/network and market/asset identity. Show changed context before using a different record. A token ticker alone is insufficient: when several positions hold MOE, clarify which position and quantity a request concerns. An ambiguous "pause it" also needs its position/deployment/wallet scope and intended stop effect resolved. Ask only for missing meaning needed for that request.

**One action preview and action record.** For a consequential user request through either channel, use the same preview: exact target/context, requested operation and quantity, current data/time, expected asset movement, applicable permissions/reservations/limits, costs or unknowns, remaining exposure and whether future entries remain active. A quote is an estimate. Recheck current operational eligibility, authority and the target agent-wallet reservations before admission/submission; a stale preview cannot grant authority. Show required changed permission or unsupported capability explicitly. Routine automation under existing adopted authority does not gain a new per-trade-signature requirement.

Create one action identity and show proposed, queued, submitted, confirmed, reverted, denied or outcome-unknown states with reasons and update times. Both channels read the same action history and reconciled position state. Conversation, a preview, submission acknowledgement or a refresh cannot claim completed liquidation. Repeated requests must find/resolve the existing action rather than silently create a second economic action. Retain reservations for unknown outcomes. After a confirmed partial exit, show the remaining attributable quantity and updated accounting in both views. These are required behavior; synchronization and duplicate prevention still require implementation qualification.

**Separate stop and close behavior.** Use explicit controls for Stop new entries, Halt all swaps and Request position close, with position/deployment/wallet scope. Stopping entries allows only existing explicitly approved exits under active authority; it does not instruct immediate liquidation. Halting swaps blocks exits as well. A supported close requests a sale of the selected quantity; it does not silently stop future entries or prevent strategy re-entry. Explain that consequence in the shared preview. Revocation/expiry cannot undo a broadcast transaction. No close bypasses revoked authority, unqualified exit capacity or failed operational checks, and no exit is guaranteed. Unsupported manual/partial close remains visibly unsupported; a labeled authored fixture can test the interaction without claiming that capability works.

**Layout and evidence basis.** Prototype leads the existing experiment using its logic/state walkthrough branch. Impeccable in Operate mode supports readable account tables, persistent exact context, consistent action previews, expandable detail and clear pending/empty/missing/denied states. Keep the selected record visible beside conversation on wide screens; on narrow screens preserve its context and return link when switching views. The five priority tasks and effort limits remain in the [single frontend packet](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#one-frontend-interaction-prototype); there is no second prototype or visual-variation exercise.

BUILDER-ONLY REFERENCE: `docs/research/EDGE_OS_COMPETITOR_UX_AND_ACCOUNT_CONTROL_2026-10-03.md` and `docs/research/assets/competitor-ux-2026-10-03/README.md` in the private workspace. The controller read both and inspected seven selected captures for this amendment. Portable lessons and limits are recorded here so teammates do not need private account images:

| Inspected capture/reference | Adopted interaction lesson and evidence limit |
|---|---|
| `almanak-strategy-chat.png`, `keel-editor-chat.png` | Keep an inspectable record beside contextual conversation. Correct position attachment, generated changes and record synchronization were not tested in those apps. |
| `horizon-activity.png`, `minara-trade.png` | Direct position/activity inspection, filters and distinct equity/available-funds labels. Their accounts were empty; perpetuals and mandatory paper stages are outside this scope. |
| `keel-account-authority.png` | Explain scope, expiry, revocation and residual holdings. The displayed provider claims are not enforcement proof or Edge OS policy. |
| `gt-demo-deals-private.png`, `gt-demo-detail-private.png` | Expand position-to-action history and separate Stop from Close. These are demo records; actual controls, onchain outcomes and synchronization were not exercised. |

Original screenshots remain private, including account/strategy identifiers. Use authored sanitized account fixtures and the recorded MOE extract in the prototype. Do not copy private captures into shared artifacts. UI observations provide references; accepted Edge OS contracts determine behavior.

OpenBB's documented [linked dashboards and contextual agents](https://docs.openbb.co/workspace) supply an additional layout reference. Keep charts, tables and conversation bound to the same investigation/market/data period, with changes distinguishable from the saved result. Lead with the research question, conclusion, reasons and next action rather than require users to assemble a terminal. This is a documentation-based lesson, not an inspected OpenBB screen or an expansion of the existing five-task prototype. See the [shared comparison](../../research/OPENBB_RESEARCH_REUSE_AND_PRODUCT_DIFFERENCES_2026-10-04.md#frontend-lesson).

## 15. LP proof

The LP proof starts only after the spot path works.

It accepts a concrete thesis, loose intuition or bounded request within one declared pool universe. It produces an LP `EdgeSpec`, a typed LP `StrategySpec` and a simulation decision. The shared input states do not require broad LP search.

The proof declares the pool model, assets, data period, observation/action timing, allocation or range rules when applicable, and intended add/remove/rebalance/collect behavior. It accounts for fee accrual, inventory exposure, impermanent loss, gas and rebalancing costs, with a declared comparison such as holding the same initial assets or an unchanged liquidity position. Unavailable position, fee or price history leaves the affected claim unresolved; point-in-time rules apply as they do for spot.

The user sees the interpreted rules, evidence, assumptions, comparison, cost breakdown and reason for the decision. It must not present gross fee revenue as net benefit or reuse a spot fill model as an LP simulator. Source-backed data or clearly labeled fixtures may test mechanics; a fixture does not establish an LP edge or user demand.

It can end at `EDGE_REJECTED`, `UNRESOLVED`, or `READY_FOR_PAPER_TEST` only when the corresponding evidence gate is met. A live LP action is optional. The team adds it only after it verifies the venue contract, action semantics, receipt and risk boundary, and obtains separate approval for its adapter and execution mandate. The Kuru spot proof supplies no automatic LP qualification.

The LP proof exists to show that the runtime supports another financial action domain. It must not weaken the complete meme-spot path.

## 16. Team ownership

### Builder, quant and agent systems

Own:

- `PromptInterpretation`, `ResearchBudget`, `ResearchLedger`, `EdgeSpec`, `ResearchEvidencePackage`, `StrategySpec`, and `ValidationDecision` semantics;
- feature definitions and point-in-time rules;
- hypothesis generation;
- compiler and deterministic evaluator;
- false-edge tests;
- risk policy;
- mandate semantics, stop rules, and typed agent handoffs;
- reference JSON fixtures.

### Frontend teammate, interface implementation and judge experience

Own:

- input and clarification flow;
- evidence, source, timestamp, observation-versus-interpretation, contradiction and coverage views;
- research-ledger views;
- rejection, unresolved, risk-denied, mandate-approval, and receipt states;
- delegation, pause, revoke, recovery, pending-order, and fill views;
- degraded-provider states;
- demo-safe fixture playback;
- visual design and project graphic.

### Builder, platform, Monad and deployment

Own:

- application API and persistence;
- authorized bounded provider collection, quality/provenance records, budget enforcement and data reconciliation;
- Kuru data and execution adapter;
- Envio ingestion and indexed records;
- QuickNode integration, public-RPC fallback, and provider-health checks;
- official X API forward collector when access is available;
- Privy user-owned wallet setup, restricted signer consent, policy checks, and owner removal;
- backend secret isolation and separation of policy administration from execution;
- durable deployment workers, exclusive claims, capital reservations, and idempotent intent handling;
- restart reconciliation of pending transactions, orders, and fills;
- receipt storage and explorer links;
- deployment, monitoring, and recovery.

The builder owns the whole backend and all prototypes. The tokenization teammate implements separately accepted extension tickets after utility, rights, economics and interfaces are approved. This ownership does not activate an extension or delegate backend/product decisions.

### Integration rule

The builder publishes versioned JSON schemas and fixtures before teammate implementation depends on backend output. The frontend uses the accepted interfaces and examples, not private course archives or probe internals.

Freeze the written [research acceptance fixtures](../../EDGE_OS_RESEARCH_CONTRACTS.md#7-reference-acceptance-fixtures) in the build brief. They cover complete and vague hypotheses, unknown mechanisms, transfer-versus-purchase mistakes, future labels, incomplete buckets, provider loss, omitted contradictions and budget/authority breaches. These are proposed fixture cases, not implemented or passing tests.

## 17. Acceptance checks

### Scoped experiments before full-product planning

Read [EDGE_OS_SCOPED_PROBE_PLAN.md](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md) before assigning, approving or running either probe. It controls their frozen inputs, owners, pass/narrow/reject conditions, evidence, time budgets and stop conditions.

- Probe A asks whether one bounded spot investigation preserves meaning and trial history, produces an inspectable typed strategy or useful unresolved result, and rejects a known-invalid attractive case. The builder owns it.
- Probe B asks whether the exact approved Monad–Kuru action works through a restricted Privy delegation and whether denial, recovery and owner removal behave as required. The builder owns it. Reuse the Assensus pattern without treating its old network/configuration as proof of this path.

The probes may run independently once each has the necessary approval. The builder also owns any result-state interaction prototype. Teammates implement accepted UI or platform behavior through assigned tickets after the builder provides the required fixtures, interfaces or mockups. UI work cannot count as quant or chain evidence.

Report each probe's verdict separately. A compiler-only pass cannot pass execution. A receipt cannot pass research. A blocked adapter or unavailable data must remain unresolved; it cannot be converted into a full Compass prototype pass. LP remains in the product scope, but LP simulation/execution, tokenization, new markets and production UI are outside these first two experiments.

Current decision: Probe A is `ACCEPTED AND CLOSED — BOUNDED RESEARCH PROCESS ONLY`; its strategy result is `UNRESOLVED`. Probe B remains `NOT_STARTED`. The single frontend interaction prototype is built at v0.12.2. Scoped source/state checks and independent repair review pass. The builder reports completing the short walkthrough and finding it fine; this is assisted general feedback, not recorded task-by-task or unfamiliar-trader comprehension evidence. Historical human task verdicts remain REVISE/UNRESOLVED. Fresh post-repair automated browser confirmation, full keyboard traversal, screen-reader and physical-phone checks remain limited or absent as recorded in the findings. Explicit bounded closure and production scope acceptance remain separate decisions. Probe A closure accepts only its documented claim, not the full acceptance list or complete design.

Stop each experiment when its question is answered or its approved budget expires. Return findings to the design decision. Use Wayfinder only if dependent, unresolved product decisions remain too broad for one focused session. Its map should resolve core build blockers; optional-token economics need not block these experiments.

### Agent add-ons acceptance checks

These are authored requirements, unrun. They qualify the accepted catalog without changing closed probe evidence or claiming prediction accuracy:

1. Enabling a catalog entry affects only the selected user's agent. Cross-user and cross-agent requests cannot read records, use credentials or alter selections outside their scope.
2. A skill and MCP tool produce a source-linked research/account answer through the actual pinned runtime. Calculations match deterministic reference fixtures; the skill cannot invent a supported operation or omit contrary results.
3. Unknown entries, endpoints, executable uploads and non-selected tools are denied by the backend. Skill text or tool output cannot grant shell access, signer access or expanded authority.
4. Connection failures and disconnects preserve findings, pending actions and accounting. Required missing inputs remain explicit; unrelated tasks need not stop.
5. Secrets remain absent from model packets, frontend responses, errors and evidence exports. Access/cost information is visible before enabling; provider charges follow the existing approved budget contract.
6. Run records retain exact add-on/configuration identities. An update cannot silently change an active run or adopted strategy meaning. Test restart behavior and stale selections against the frozen lifecycle rules.

### Full dangerous-claim prototype checks

The dangerous-claim prototype passes only when:

1. The system classifies all three input states.
2. Missing assumptions produce clarification or unsupported output.
3. Every candidate appears in the `ResearchLedger`.
4. The compiler emits a typed canonical `StrategySpec` or a structured rejection.
5. The evaluator prevents future-information access.
6. The evaluator applies costs, spread, depth, slippage, latency, liquidity, and capacity assumptions that the data supports.
7. One attractive false edge fails for a visible reason.
8. The same specification meaning drives historical, paper, and execution-intent modes. Order type, side, size, price or limit semantics, timing, costs, and fill assumptions must agree.
9. The LLM cannot access credentials or submit transactions directly. Only the deterministic execution service can authorize policy-scoped actions.
10. The risk engine denies an invalid or excessive intent.
11. The product completes an onchain-only run when X is unavailable.
12. At most one controlled survivor reaches paper testing.
13. The system rejects an execution adapter request when its order semantics differ from the canonical `StrategySpec`.
14. One mandate-authorized Kuru intent produces an inspectable Monad receipt and applicable decoded Kuru event. If blocked, record the exact verified adapter blocker and return a limited or unresolved verdict rather than a full prototype pass; obtain approval before relying on a narrower product claim.
15. A non-technical viewer can explain why the result passed, failed, or remained unresolved.
16. Zero survivors still produce a useful report.
17. Each `EdgeSpec` answers the mechanism questions with cited evidence or visible uncertainty; an attractive result cannot manufacture a causal explanation.
18. Each research package binds the edge version, budget and ledger, preserves contrary evidence, and separates observed facts from inference.
19. Features respect actual availability, including label/cohort timing and processing delay. Unreconstructable historical agent context is not claimed as backtest coverage.
20. Removing a hypothesis-essential provider input stops that hypothesis or creates a separately declared replacement, never an equivalent silent fallback.
21. Request/compute/cost breaches and unsupported authority requests are stopped and recorded. Agents cannot promote their own evidence into execution permission.

Compiler, revision and tool-contract regression checks:

| Case | Expected result |
|---|---|
| A used component or numerical policy changes while expression text stays the same | A different semantic identity is required. Existing evidence and authority cannot silently transfer to that revision. |
| Two edits are published concurrently | Each successful publication returns its own immutable identity. Validation and deployment consume the requested revision, not whichever is latest. |
| Publication acknowledgement or revision identity is missing | Preserve the uncertain operation and reconcile it. Grant no new eligibility or authority; do not substitute a later fetch. |
| An unresolved draft is saved, or compilation succeeds without later evidence | Preserve the draft/compiled artifact and findings, with paper/live eligibility and authority ungranted. |
| Invalid units, non-finite values, out-of-range parameters, incompatible types or static cross-field constraints arrive through a tool or stored expression | Return a positioned or field-specific rejection before data access or financial effects. State-dependent checks may read current state but must pass before effects. Generator sample ranges do not define input acceptance. |
| A simulated and proposed live configuration differ in strategy semantics, costs or sizing | Do not claim parity or promote the altered configuration under the old evidence. Record the discrepancy and required revalidation. |
| A provider response exposes credentials or private request data | UI, model and public receipt output contains a redacted error and safe diagnostic reference. |
| A mutation outcome is uncertain and authentication refresh succeeds | Reconcile the original attempt before another submission; refreshing authentication grants neither a new intent nor extra authority. |
| A synchronization or authority guard raises an unexpected error | Deny the affected transition and record the error; do not proceed with unknown state. |
| An LP specification is passed to the spot simulator or Kuru spot order adapter | Reject the domain mismatch. No spot order or fill result can satisfy the LP proof. |
| Hermes returns an unsupported conclusion, omits contrary evidence or exceeds its declared budget | Stop or return the package for correction under the research contract. Model agreement grants no validation or execution authority. |
| Jev returns an unknown label, stale input references or a decision outside the approved strategy contract | Record abstention or a structured rejection. Create no executable intent. With Jev disabled, the declared deterministic path remains testable. |
| Clarification supplies a supported missing field | Link the new value to its answer and interpretation revision. Preserve earlier supplied meaning and restrictions; show changed fields. |
| A required answer is unknown, conflicts with an earlier rule or requests an unsupported action | Ask the specific unresolved question or return unsupported capability. Do not invent a value, silently overwrite meaning or substitute another domain. |
| A no-thesis input retains adopted research settings but has no supported candidate | Preserve configuration separately. Signal/selected strategy remain absent and no readiness or execution permission is granted. |
| A model-confidence or research-priority score is high while a required evidence/capability gate fails | Preserve the score's declared purpose, but block the affected transition. Scores cannot replace deterministic gates. |
| A runner/creator question requests findings rather than trading rules | Route to supported research capabilities and return sourced observations, contrary findings and unknowns. An unsupported extension is explained; no forced strategy or backtest is required. |
| Historical support is absent or unfavorable and the user requests a trial or ongoing live operation | Preserve the evidence status. Check the live-trading contract independently; consent alone grants neither operational readiness nor a passing evidence gate. No compulsory trial is added. |
| A live request lacks supported executable rules, required current data, accounting or verified authority | Deny the affected execution even when the user accepts financial risk; explain the missing capability or repair. |
| New live observations suggest a different hypothesis or strategy | Preserve decision-time evidence and the prior revision. Propose the change for review; create no automatic revision or mandate expansion. |
| User continues after a favorable trial within active permissions | Retain unproven evidence where applicable, strategy identity, consumed allowances, losses and pending exposure. Review a changed trial stop; do not require a signature for a purpose-label change alone. |
| User continues after expiry or requests more authority | Obtain approval and verify the amended/replacement mandate and policy before new actions. Preserve accounting lineage; no automatic allowance reset or expanded signer authority. |

Map the compiler subset to applicable proposed tests T01–T36. Run only the tests for approved behavior and record exclusions; the source review is not passing test evidence. LP proof must expose the domain-specific outputs in section 15 before it is marked complete. The concrete fixtures and implementation plan remain to be approved.

Delegated-execution readiness has a separate gate. It passes only when all checks succeed:

1. Explicit user consent binds the wallet, strategy version, signer, limits, and expiry.
2. One permitted Kuru action succeeds while the user is offline, without another user signature.
3. A protected-field violation fails at the Privy boundary, independently of a risk-engine denial.
4. Persisted risk, policy, intent, transaction and swap/asset/accounting records show what happened.
5. A forced restart after submission reconciles the same economic intent without creating a second swap or substituting a fresh route/transaction.
6. Owner signer removal is verified. A subsequent equivalent request produces no new transaction.
7. Pending transactions and residual asset exposure remain visible after removal; the initial Flow adapter grants no resting-order permission.
8. Policy drift, stale data, ambiguous submission, and missing authority stop new execution.

An adapter blocker is not a passing delegated-execution test. A controlled fixture may prove mechanics, but cannot establish a real trading edge.

Run independent provider-denial probes only in the separately approved, isolated spike environment. Never disable production risk checks to reach Privy. A post-revocation provider probe must distinguish lost signer authority from an earlier local order-count denial.

## 18. Three-minute technical demo contract

Status: `PROVISIONAL; REVISION PENDING PROBE FINDINGS AND BUILDER REVIEW`. The table below is the earlier draft, not a frozen recording script. Revise its object-heavy section and ending after the probes. Follow [the Compass timing](../../../playbooks/HACKATHON_WINNING_COMPASS.md#curated-three-minute-demo): make the main user path the longest uninterrupted segment, show the useful result early, finish working content by 2:55 and retain five seconds of margin. Any unresolved research case and separate execution fixture must remain distinguishable. Optional token behavior belongs only in a separately approved, implemented and tested extension; it does not block these probes.

The [draft build brief](../../EDGE_OS_BUILD_BRIEF.md#9-demo-and-approval) now proposes a findings-led story. Retain this older timing table as a planning reference only; freeze the final script after the actual production and execution evidence exists. Neither version permits authored account or backtest screens to stand in for a working onchain product.

| Time | Content |
|---|---|
| 0:00 to 0:15 | Name the active meme trader and the failed research process. |
| 0:15 to 0:35 | Explain why a prompt-to-bot and an attractive backtest are insufficient. |
| 0:35 to 1:10 | Submit a bounded thesis, intuition, or research request. Show clarification, sources, and the research budget. |
| 1:10 to 1:40 | Show the `EdgeSpec`, `ResearchLedger`, typed `StrategySpec`, and plain-English interpretation. |
| 1:40 to 2:05 | Show the attractive false edge and the control that rejects it. |
| 2:05 to 2:30 | Show the bounded mandate, permitted Kuru action, receipt, and recorded risk or policy denial. Label any controlled fixture. |
| 2:30 to 2:45 | Show revoke and restart evidence. State any pending order. Explain that X is optional. |
| 2:45 to 3:00 | Show the narrow LP compile-and-simulate proof and state the next evidence milestone. |

Keep a replayable local proof for every external service used in the recording. A replay must remain clearly labeled and must not be presented as a live transaction.

## 19. Known unknowns and resolution gates

| Unknown | Current handling | Resolution gate |
|---|---|---|
| Exact Flow deployment, entrypoint and underlying route/program used for the swap proof | Use no address or network assumption in implementation | Verify official deployment and market metadata before the build brief freezes fixtures |
| Whether the complete selected Flow path exists on testnet | Prefer testnet when verified; otherwise use a builder-approved minimum mainnet amount | Resolve before the prototype submits any transaction |
| Exact Kuru calldata restrictions and Privy policy coverage | Keep delegated Monad–Kuru execution `UNPROVED`; reuse Assensus's pattern only | Verify contracts, functions, batch arguments, units, approvals, and policy denial in the approved spike |
| Privy direct submission versus sign-only RPC transport | Keep both as alternatives, not interchangeable retry routes | Select one tested transport before the build brief freezes the adapter |
| Offline execution, restart recovery, and revocation on Monad | Specify the required behavior without claiming completion | Pass the separate delegated-execution gate before presenting an autonomous demo |
| Policy administrator and execution credential separation | Execution cannot weaken its own approved policy | Verify ownership, credential permissions, and content checks before activation |
| Per-agent skills and MCP catalog | Approved MVP direction only; no installed integration or hosted-user isolation proof | Freeze entries/manifests and lifecycle in the build brief; qualify pinned Hermes support, backend tool restrictions, scoped credentials, cross-user isolation and the add-on acceptance checks before enabling entries |
| X developer approval and processor/storage terms | Keep X optional and use onchain-only mode | Resolve before the product stores or sends raw post text |
| Historical point-in-time X engagement | Begin forward snapshots; exclude missing historical metrics | Resolve per feature before backtesting |
| Nansen coverage, flow meaning, label timing and endpoint boundaries | Keep `NANSEN-Q01` `NOT_STARTED`; optional platform capability, potentially essential hypothesis input | Approve token/venue, declared feature, account costs and budget, then qualify exact endpoint, timing and sample reconciliation before use |
| QuickNode quota and event-plan redemption | Use QuickNode as the initial provider without assuming a private quota | Confirm account-level terms and run the required-method smoke test before the build brief freezes the provider contract |
| Target-user demand | Keep the claim unvalidated | Challenge the one-minute explanation with real users before the build brief closes |
| LP execution venue and proof | Keep the first LP path at compile and simulation | Verify before adding a live LP adapter |
| Statistical inference method and calibration | Q15–Q17 policy is accepted; exact dependence-aware method/profile and statistical behavior remain unqualified. Descriptive research can finish and live eligibility is independent. | Resolve STAT-Q01 method version, assumptions, block/sensitivity/failure rules and numerical criteria before formal support claims; qualify dependent/no-effect behavior and the full selection procedure under separate authorization |
| Production compiler encoding, resource bounds and verification | The initial typed language, operator registry, calculation and history/missing/Boolean policies are builder-accepted requirements. Their focused production fixtures remain unrun; Probe A proves only its retained tested subset. | Carry forward accepted behavior. Freeze remaining machine encoding, semantic identity and measured resource bounds in the build brief; run the applicable production fixtures before claiming support. |
| Real-market semantic identity | Probe A compiled synthetic templates with separately recorded MOE/WMON research bindings, not a deployable MOE strategy | Freeze and test venue, assets, ordering, quote/units and revision binding for the first production slice; grant no execution authority from the probe artifact |
| Historical delivery and realistic fill/cost coverage | MOE event history supports reconstructed associations; actual delivery/finality and omitted execution effects remain unknown | Label assumptions and evidence gaps per run. Qualify required live/paper execution inputs before granting the corresponding readiness; this does not require another run to close Probe A |
| Intake classifications and field-level evidence | Rules recorded in section 7 and the research contract; not implemented in production | Freeze schemas, stage requirements and clarification examples in the focused decision session; implement in the first accepted intake ticket |
| Canonical semantic identity and publication contract | Require locked semantics and exact revision consumption; no implementation is claimed | Freeze serialization/hash/manifest and publication/result schemas in the build brief; pass component-change, concurrent-edit and unknown-identity tests |
| LP data and simulation coverage | Keep pool model, fee/position history, comparison and costs explicit or unresolved | Approve one bounded LP proof and qualify its data before claiming research or paper readiness; do not infer demand from simulation |

## 20. Review decision

Current decision, 2026-10-05: the builder approved the specification scope and requested `to-spec` synthesis. The detailed local handoff is ready for review against that approval. Confirm the proposed testing boundary and identify any synthesis errors before ticket decomposition. This is not another broad grilling session. The builder requested local review before any publication.

Any later release cut must name the omitted capability and preserve its deferred status. Do not reinterpret a missing implementation or qualification result as a scope cut. Probe A is closed and its holdout remains unopened. Probe B retains its own pending configuration and approval. Paid services and financial execution require explicit task-level approval.

The single interaction prototype has run and been revised. Its findings preserve the builder's earlier confusion, repairs and later assisted feedback. An unfamiliar trader's attempt and the independent user/teammate product challenge remain unavailable; do not claim demand validation. The builder may accept a bounded closure with those limits. Reopen a specific interaction for an observed defect or misunderstanding, not to improve a critique score.

The build brief explains the accepted scope and still-open engineering choices. It is not a passed implementation or qualification gate. Freeze each relevant machine contract once before dependent tickets. Include the exercised runtime-verification setup in the first runnable production slice. Publish ready implementation tickets only for accepted behavior with resolved dependencies and builder authorization. Independent research/UI work need not wait for unrelated execution proof. This revision starts no implementation, issue publication or Monad–Kuru action.

Review the research contracts alongside the mandate/runtime sections. Approving these written definitions is separate from approving an instantiated Nansen investigation and its paid access. No Nansen qualification result exists yet.

The post-core scope reassessment, BUILDER-ONLY REFERENCE `docs/research/13_EDGE_OS_POST_CORE_SCOPE_AND_DEMO_REASSESSMENT.md` supplies the reasoning for section 5's conditional publication, token and funding extensions. The shared requirements are now recorded in this specification so teammates do not need that private note. Model selection, economics, eligibility and activation remain pending builder approval. Section 5's exclusions remain outside the core. No extension is activated by this amendment.
