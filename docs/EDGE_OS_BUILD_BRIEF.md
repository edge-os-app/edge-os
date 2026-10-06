# Edge OS first-release build brief

Status: PRODUCT SCOPE APPROVED; LOCAL HANDOFF FREEZE AND TICKET DRAFT. Updated 2026-10-06. Named technical choices and qualification remain open.

The builder approved specification scope and requested `to-spec` on 2026-10-05. The [canonical specification](superpowers/specs/2026-09-29-edge-os-hackathon-design.md) now includes user stories, test coverage and dependency boundaries. On 2026-10-06 the builder requested freezing the local handoff and drafting its ticket graph. Review the proposed breakdown and testing boundary before publication or implementation dispatch. The research contracts and linked ADRs retain their meanings. Open technical choices block only dependent work.

This brief explains the intended release, user journeys, component responsibilities, implementation dependencies and evidence needed for completion. It does not replace the specification or define a second set of schemas. Accepted product decisions remain accepted. Proposed engineering choices below remain proposals until reviewed. No implementation, issue publication, paid run or financial action is authorized by this document update.

Read sections 1–4 for product scope and journeys, section 5 for historical simulation, section 6 for records and runtime boundaries, and sections 7–10 for verification, decisions, the demo and ticket handoff.

Focused handoff requirements approved, 2026-10-06: the [canonical amendment](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-declaration-and-agent-monitoring-handoff) requires candidate/falsification/trial records before outcomes, actual scheduled strategy evaluation before intents, explicit persistent deployment and per-agent health, reconciled results and evidence checks. New return/account-value/drawdown displays need a versioned calculation profile with independent examples. P02/P06 provide selected portable requirements and fixtures before consumers; task packets require relevant inputs rather than every private source. The proposed graph incorporates these requirements without new ticket IDs or dependency edges. Checks remain unrun; this acceptance does not approve the full graph, its testing boundary, publication or implementation.

## 1. First useful result

An onchain meme trader brings a clear idea, a rough hunch or a bounded market question. Edge OS preserves the request, asks for necessary missing meaning, proposes a bounded investigation and returns a saved answer with supporting and contrary evidence. A completed investigation may have no supported strategy.

Build this complete path first:

**Request → necessary clarification → review question and research budget → qualify data → investigate and evaluate → inspect and save the result.**

The failure path preserves the request and completed work. It distinguishes missing meaning, an unsupported capability, missing evidence, a failed provider/run and an invalid generated representation. It explains the next available action without inventing a strategy or silently retrying a financial operation.

For supported, sufficiently specified rules, offer an optional **Test on past prices**. A user may separately review live trading without a favorable historical result or a compulsory trial. Actual activation requires qualified execution and explicit permission. Research, Agents, Positions and Funds are destinations, not mandatory stages.

### Complete product goal

Edge OS helps onchain traders investigate possible opportunities, define supported rules, test them where feasible and deploy agents under user-approved limits. It then records what those agents did and what the user learned. The first market is Monad meme-token spot trading. LP research, compilation and simulation provide the second domain proof after the spot path works.

Research-first describes implementation order. The intended release and demo include agent deployment and observable operation. A research-only delivery is a narrower release that needs an explicit builder decision.

The first user is a trader with an idea or market question, not necessarily someone who can write a quantitative specification. The agent can suggest settings and explain choices. The user adopts consequential assumptions. The interface must not require the user to understand compiler expressions, statistical terminology or MCP configuration.

For example, a user might ask what happens after a token rises, whether volume changes that pattern, or what deserves investigation in a selected market. Runner, deployer-history and suspected-rug questions fit the broader research mode. Their required data and tools are not automatically part of the first price-and-volume implementation.

### Useful completion without a winning strategy

A finished investigation shows the question, scope, observations, contrary findings, every attempted variant, limitations and available next actions. It can conclude that evidence is insufficient. It can also be a descriptive report without a trading strategy.

The product must distinguish three questions:

| Question | Record or check that answers it |
|---|---|
| What does the evidence support? | Evidence package and claim-specific validation decision |
| Can this exact strategy operate with supported inputs and execution behavior? | Compiler and operational qualification |
| What may this agent do with this wallet? | Active execution mandate and current enforcement checks |

A favorable study answers neither of the last two questions. User consent does not turn an unfavorable study into favorable evidence.

## 2. What the evidence establishes

| Evidence | Established within its scope | Still unproved |
|---|---|---|
| [Closed Probe A](prototypes/EDGE_OS_PROBE_A_RESULT.md#builder-acceptance-and-closure-2026-10-03) | Tested interpretation/clarification, template compilation/reload, bounded reconstructed research, retained contrary results and rejection of known-invalid future inputs | Arbitrary strategy interpretation, production grammar, real-market deployable revision, original historical delivery, realistic fills or profitable alpha |
| [Frontend v0.12.2](prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md#controller-verification-and-repair-v0122-2026-10-05) | Scripted research, past-price interaction, separate wallets, funding, activation, positions, stops, withdrawals and continuation; scoped source/state regression checks | Working simulator, persistent records, real wallet/transaction enforcement, unfamiliar-user comprehension, full accessibility and physical-phone behavior |
| Builder walkthrough | Builder reports the short walkthrough was completed and was fine; this is assisted feedback | No task-by-task answers or unfamiliar trader attempt were supplied; it is not a replacement for them |
| [Probe B](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#5-probe-b-delegated-monadkuru-action) | Intended Flow swap and required authority/recovery proof are specified | Execution has not started; a working unattended trading path is not established |

Keep the real MOE report unresolved, with all four variants and unopened holdout. Its recorded results must not become an invented successful backtest or Agent A/B track record. Do not reuse prototype numerical settings, balances or synthetic identities as production defaults.

Bounded frontend closure remains a separate builder decision. The latest general feedback is recorded in the [findings addendum](prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md#builder-walkthrough-and-build-handoff-2026-10-05). No broad visual iteration is proposed.

## 3. Release scope and dependencies

| Capability | Proposed place in the build | Completion boundary |
|---|---|---|
| Intake and saved research | First complete path | All three starting states, field-level origin/uncertainty, adopted settings, preserved restrictions, all attempts and useful unresolved output |
| Price and executed-volume rules | Initial supported research language | Accepted typed operators, five-minute timing, units, missing-data and decimal policies pass applicable production checks; no arbitrary generated code |
| Narrow spot simulator | After the first research path works; part of this proposed release | Actual deterministic trades, cash, holdings, declared costs, result metrics and saved runs; assumed execution remains labeled |
| Agents, Positions and Funds | Frontend may build against accepted sanitized records; live functions depend on backend qualification | One separately funded user-owned wallet per agent, multiple positions, direct views and contextual conversation over the same records |
| Persistent Kuru Flow operation | Separate qualification work, then affected production tickets | Probe B plus applicable wallet, entry/exit, inventory, funding/withdrawal and recovery checks; one swap alone does not qualify the whole runtime |
| Approved skills/MCP catalog | MVP direction retained; implement after its required research/account tools work | Reviewed instruction skills and allowlisted read-only tools, per-agent selection, scoped access/costs, version provenance and isolation checks |
| LP compilation and simulation | Required second product proof after the spot path works | Its own pool model, fee/inventory/cost comparison and data qualification; not a spot simulator with a different label |
| Market chart link | Small optional integration | Verify the exact pool/network destination; distinguish current market prices from saved research and simulated account value |

The first research delivery is not completion of the whole two-domain product. If the schedule cannot include the simulator, LP proof or execution, return that release cut to the builder and label the delivered scope. Do not silently remove them or imply they work.

Defer broad strategy search, custom code/plugins/MCP endpoints, perpetuals, cross-chain execution and automatic strategy replacement. OpenBB is an optional component candidate, not a dependency. Nansen, wallet/deployer attribution and X require separate qualified inputs; unsupported requests keep their meaning and explain the missing capability. Publication, token utility/rights, issuance and fee-funded operation need their own accepted extension contract. No token task is ready merely because a teammate owns that role.

## 4. Production behavior to carry forward

- **Research:** conclusion, reasons and next choices first; sources, variants and field-level evidence remain inspectable.
- **Agents:** short rule summary and status; exact rules and consequential terms visible before activation. Stopping works before the first position exists.
- **Positions:** direct inspection, exact ownership, dated estimates and pending actions. Sale status stays with its position; closed positions retain history.
- **Funds:** connected personal wallet and distinct agent wallets, without a pooled Edge OS balance. Reviewed transfers identify source/destination, asset, amount, gas and commitments. Qualify actual owner access before use.
- **Conversation:** named record context and return link; the same preview and action identity as direct controls. Read-only questions move no money. Dated replies do not override current records.
- **Presentation:** plain labels, one clear primary action and expandable detail. Evidence, operating state and permission stay separate. Reviewer controls stay outside customer navigation; authored data keeps its demo label.

These choices follow the [accepted account interaction contract](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-account-views-and-contextual-conversation). Competitor observations support record-plus-chat and direct account access; they do not establish equal usability, synchronization or wallet security. No competitor transaction test is required to build our accepted behavior.

### Visual design handoff

Builder decision, 2026-10-06: prepare a scoped customer-design handoff using the v0.12.2 HTML interaction reference and Organic as the starting Claude Design system. The prototype's existing styling is not the approved final design. Establish the app shell, first request/clarification/saved-result journey and reusable component language before the matching frontend implementation. Subsequent UI slices extend that system with their account, simulation, memory/add-on and LP states; do not delay unrelated backend decisions or qualification until every screen is designed. The builder approves actual rendered outputs. Preserve evidence/permission and wallet/action distinctions, accessible controls and explicit fixture labels. Publish reviewed sanitized exports before teammates depend on them. No design upload, generation or production work is performed by recording this decision.

### Research and strategy review

1. The user enters a thesis, loose intuition or bounded question. Preserve the original words and restrictions.
2. The interpreter proposes meaning and identifies its sources. Ask only for missing meaning needed for the requested job.
3. The user reviews the question and proposed research settings, including data scope, variants and cost assumptions. Record adopted settings.
4. The application qualifies data and runs the approved investigation. Show progress and retain partial work if a provider fails.
5. Research presents the conclusion and reasons before detailed calculations. The user can save the report, ask about it or review a further study proposal.
6. When the user requests a strategy, compile sufficiently specified, supported rules. Show exact entry, exit, timing, sizing and failure behavior in understandable language.
7. The user can optionally test that revision on past prices or request live setup. Either action preserves the evidence status.

Saving a report, asking a question or reviewing a proposal starts no paid investigation or financial action by itself. Any action that starts work must identify what will run and the applicable adopted budget. Exact production labels can improve on the prototype wording without changing these effects.

The real MOE report remains a research result with no selected strategy. Separate demonstration strategies have their own identities and origin labels. Navigation cannot imply that MOE's unresolved study generated those strategies.

### Create, fund and activate an agent

1. The user selects supported, reviewed rules and creates a trading agent. Create an empty, user-owned wallet bound to that agent.
2. Show wallet setup progress. Preserve setup identity after cancellation or failure. Reconcile an unknown creation outcome before attempting another creation.
3. Funds offers a reviewed transfer from the connected personal wallet or an agent deposit address and QR code. Identify the network, asset, destination and fees.
4. Show transfer status and confirmed funds. Keep the strategy's trading asset separate from native MON for gas. WMON is not native MON.
5. The user reviews the exact strategy revision, wallet, evidence, allocated capital, limits, expiry and stop behavior together.
6. The user approves the mandate and required delegation. Activate only after current inputs, accounting, route and wallet enforcement are qualified.
7. Agents shows whether the worker is running, waiting, stopped or unable to proceed, with the reason and next available action.

Funding grants no trading permission. A top-up changes confirmed funds, not the allocation, consumed allowance, expiry or an existing stop. Creating a wallet grants no signer access. Initial funding excludes automatic bridging, wrapping, card purchases and gas sponsorship.

The connected personal wallet is the owner's funding source and reviewed withdrawal destination. There is no additional pooled Edge OS trading account. Agent A has no authority over Agent B's wallet.

### Monitor several agents and positions

Each agent may hold multiple supported positions within its own wallet and adopted limits. The rejected one-position restriction must not return through a fixture or simplified implementation.

Agents provides strategy summaries, operating status, wallet balances and applicable actions. Positions supports direct inspection across agents with filters for the exact agent, wallet and strategy. Each position shows holdings, acquisition cost, qualified realized results, dated unrealized estimates and pending actions. Expandable details expose decisions, inputs, intents and receipts.

Conversation answers questions such as "Why did this agent buy?" and "How much can it still spend?" from those same records. Include the account scope, record update time and a link to the relevant view. If two agents hold the same token, clarify an ambiguous action request before preparing it.

A conversational sale and a direct sale use the same action preview, target identity and checks. The user must not need to start a chat to inspect or manage positions. Historical chat replies remain dated explanations, not a replacement for current account state.

### Stop, sell, withdraw and remove permission

| User action | Required effect | What it does not do |
|---|---|---|
| Stop new entries | Deny new purchases and additions in the selected scope. Existing approved exit rules may continue. | It does not immediately sell holdings. |
| Halt all swaps | Deny all new swaps in scope, including exits. Continue monitoring and reconciliation. | It does not undo broadcast transactions. |
| Sell a position | Review and prepare an exact supported sale under current authority and checks. Track submission and outcome. | It does not silently stop future re-entry. |
| Withdraw an asset | Review an owner-controlled transfer with available funds, recipient, fees and pending commitments. | It does not sell that asset or automatically stop the agent. |
| Remove agent permission | Request owner-authorized removal and show whether removal was verified. | It does not close positions, cancel broadcast transactions or remove owner access. |

An agent-specific stop must work before the first trade. A position-specific panel shows only that position's actions. Combined activity belongs in the labeled account overview.

Pending or unknown transfers and swaps retain reservations until reconciliation justifies release. Coordinate owner withdrawals with agent work. The UI must not promise either cancellation of an already broadcast action or indefinite loss of owner access.

### Continue trading and record learning

A trial is optional live trading with a learning objective and an adopted stopping point. Users may start ongoing operation directly. There is no compulsory paper stage, favorable backtest or trial graduation.

Continuation retains the same strategy revision, positions, losses, reservations and consumed allowances. A purpose-label change needs no new financial permission when the existing mandate covers the actions. Removing an adopted trial stop still requires explicit review. Extending time or increasing authority requires a clear comparison of old and proposed terms and the applicable approval.

An expiry extension changes time only. Returned proceeds, restarts and top-ups do not replenish cumulative allowances. A strategy change creates another immutable revision and requires applicable approval before use.

Store forward observations, missed opportunities, decisions, failures, measured costs and proposed lessons in the existing evidence and ledger records. Live success does not erase earlier failures or prove repeatable profitability. Suggested improvements remain proposals until adopted.

## 5. Narrow historical simulator

Start with supported spot rules and a fixed, qualified historical dataset. Freeze an exact strategy revision and adopted test settings: period, initial capital, sizing, entry/exit timing and cost/fill assumptions. Replay only information available under the declared timing model. Preserve missing observations and failed assumptions.

Return a trade list, simulated cash/holdings and account-value series, gain/loss, trade count, largest fall in account value and limitations. Store the inputs and calculation identity with the result so it can be reproduced. Match cash and inventory against small independently calculated examples, including fees, partial exits and missing data. State which sizing/addition behavior the simulator supports; reject unsupported rules rather than silently simplify them.

This is separate from a price-effect comparison and from real execution. The existing chart is an authored example. Course calculation patterns can help, but daily calendars, annualization constants and forward/backward filling cannot be imported over the accepted five-minute and missing-data rules. Realistic Kuru fills, token behavior, routing, gas and capacity require evidence beyond course data.

The [past-price interaction](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#optional-test-on-past-prices) covers settings, results, unavailable tests and next choices. Preserve its separation from live permission.

### Three different calculations

| Experience | What it answers | Required presentation |
|---|---|---|
| Historical effect research | What followed a declared pattern compared with a declared control? | Observed price behavior, comparison, uncertainty and data limitations |
| Test on past prices | Which hypothetical trades occur under these rules, and what happens to simulated cash and holdings? | Simulated results, trade list, account-value chart and adopted fill/cost assumptions |
| Live operation | What did this agent attempt and what happened to its actual wallet and positions? | Reconciled actions, receipts, actual costs and dated estimates |

Keep these identities visible in the UI and saved records. A price chart is not an account-value chart. An authored prototype chart is not a computed backtest.

### First simulation acceptance profile

Before implementation, the assigned ticket must declare the supported entry/exit behavior, sizing, additions and partial-exit cases. It must identify the dataset and the exact strategy revision. It must also define when a signal becomes usable and how a hypothetical fill is selected after that time.

Required checks include insufficient cash, an unavailable price, fees, a partial exit, an open position at the test's end and repeated calculation from saved inputs. Where several positions share one agent's simulated capital, test competing reservations and prevent double spending. A smaller simulator may explicitly reject unsupported behavior; it cannot simplify the user's rules silently.

The UI leads with simulated gain or loss, trade count and largest account-value decline. Show whether open holdings remain and which marks support their value. Keep assumptions and individual trades accessible. Negative or unavailable results preserve the work and explain the next options, including separately qualified live setup.

The courses supply calculation and testing references. They do not supply Monad market coverage or a realistic Flow fill model. License checks and verified extracts are required before copying code into shared implementation work.

## 6. Build order and team handoff

These are proposed slices, not issued tickets or file-by-file plans.

1. **Intake, clarification, saved rules and retrievable result records.** Builder owns the API, storage, interpreter/compiler boundary and deterministic routing. Frontend teammate owns the matching request/review/report path. Use sanitized real MOE evidence for a labeled saved-result example; do not call loading that report a fresh investigation. Include runtime verification with this slice.
2. **Run one supported investigation through that path.** Add qualified history, deterministic feature/outcome evaluation, attempt ledger and evidence-backed report generation. Verify it returns an honest unresolved result when requirements cannot be met. A recorded replay and a newly executed provider/model run must be distinct.
3. **Implement the narrow simulator and connect Test on past prices.** Keep its accounting separate from effect research and real wallets. Publish supported rules, assumptions and reproducible result fixtures before UI integration.
4. **Build qualified account operation.** Builder can investigate Probe B in a fresh session while accepted research/UI work proceeds. Implement wallet setup, funding, permissions, persistent execution, positions and withdrawals only against the relevant qualified contracts. The frontend can use labeled fixtures earlier, without presenting them as live capability.
5. **Complete accepted add-ons, the LP proof and release integration.** Required tools precede catalog exposure. LP retains its separate data/simulation checks. Consider optional token/publication work only under its own accepted scope and remaining capacity.

Frontend and backend can work in parallel against stable shared records and fixtures. The builder owns backend, research, integration, probes and acceptance; teammates own accepted frontend and token-extension tickets. Reconfirm availability before assigning dates. This plan makes no four-day completion promise.

### Contract package before dependent tickets

Publish versioned schemas and sanitized fixtures for the [named records and cases](EDGE_OS_RESEARCH_CONTRACTS.md). First-slice records cover interpretation/clarification, adopted budget, attempts/evidence/result, exact strategy revision where present, ownership, timestamps and failure reasons. Show required, absent and unknown values and allowed transitions, with complete, unclear, unsupported and unresolved examples. Later account records add wallet/position/action/mandate bindings.

Exact wire schemas and canonical encoding remain to be selected under [ADR 0004](adr/0004-immutable-strategy-revision-binding.md). A foundational contract task can produce them; dependent tasks consume the accepted version. Tickets link that version and their own checks rather than copy the spec. Required inputs must be in the repository or issue, not private archives or temporary test files. Publication and issue creation follow the [tracker rules](agents/issue-tracker.md).

### Named records and their build responsibilities

These records remain part of the architecture. Their meanings come from [specification section 7](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#7-core-product-objects) and the [research contracts](EDGE_OS_RESEARCH_CONTRACTS.md). This table maps them to implementation work without inventing final database or API schemas.

| Record | Required meaning and producer | Consumers and authority boundary |
|---|---|---|
| `PromptInterpretation` | Interpreter output with input class, requested job, extracted fields, source passages, uncertainty and clarification history. Application code checks it. | Intake, user review and compiler. Proposed meaning is not adopted permission. |
| `ResearchBudget` | Adopted investigation scope, sources, periods, variants, search bounds, validation access and resource/cost policy. | Research coordinator and tools. It authorizes only the declared research work, never trading. |
| `ResearchLedger` | Durable record of every hypothesis, variant, evaluation, failure, dataset, lineage, holdout access and known usage. | Reports, selection checks and later learning. Failed attempts remain visible. |
| `EdgeSpec` | Versioned proposed effect, mechanism, participants, persistence explanation, capture idea, alternatives, falsification and unknowns. | Investigation and quantitative evaluation. An opportunity description is not proof or an executable strategy. |
| `ResearchEvidencePackage` | Source-linked observations, interpretations, contrary evidence, timing/quality, proposed tests and run history. | Research UI and evaluator. The package cannot award itself validation or capital authority. |
| `StrategySpec` | Compiler-produced supported rules, market identity, entry/exit, timing, sizing, risk fields and locked semantic versions. | Review, simulation and execution. Compilation alone grants no permission or evidence support. |
| `ValidationDecision` | Deterministic, claim-specific findings tied to the exact strategy, data, evaluation settings and costs. Includes failed gates and limitations. | Evidence review and operational admission. User consent cannot change a failed finding to PASS. |
| `ExecutionMandate` | User-approved authority for the exact strategy revision, agent wallet, network, actions, limits, expiry and signer/policy binding. | Risk engine, worker and restricted executor. It grants bounded authority, not profitability. |
| `TradeIntent` | One bounded proposed action with exact ownership, strategy, mandate, market, asset quantities, guards and expiry. | Deterministic admission, queue and executor. An intent is not a transaction or fill. |
| Execution record and receipt | Checks, provider references, submitted transaction identity, confirmed events, actual asset changes and reconciliation status. | Accounting, Positions, Funds, conversation and audit. Submission is not confirmation. |
| Persistent deployment and account records | Agent/wallet ownership, worker progress, stops, positions, balances, reservations, pending actions and cumulative accounting. | Restart recovery and all account views. Chat memory cannot replace these records. |

Research may finish without an `EdgeSpec` suitable for quantitative review, a `StrategySpec` or a mandate. A sufficiently specified user-authored strategy need not acquire an invented research success before compilation or independently qualified live review.

Every consequential interpreted field identifies its value, unit, origin, source and current revision. Distinguish user-stated, user-confirmed, application-configured and agent-proposed values. Store conflicting or missing meaning explicitly. Preserve earlier restrictions when a clarification changes another field.

Saving an incomplete draft returns a draft identity and findings. Publishing a compiled strategy atomically returns its immutable revision, content hash and semantic identity. Consumers use that returned identity. Fetching "latest" afterward cannot bind the preceding write safely. A concurrent edit cannot inherit an earlier validation or mandate.

Canonical serialization, hash algorithm, machine field names and common outcome encoding remain explicit first-slice decisions. The ticket must freeze and test them before dependent code consumes them. This brief does not claim that prose descriptions are executable schemas.

### Hermes integration and hosted research

The proposed first implementation uses the Hermes path already exercised in Probe A as its starting reference. Hermes remains replaceable behind the accepted interpretation and research interfaces. This proposal selects no new provider purchase or untested hosted deployment.

Hermes performs two related jobs:

- Interpret a request, propose structured meaning and ask necessary clarification questions.
- Investigate an adopted question through approved evidence and calculation tools, then return hypotheses and source-linked findings.

The application validates the output contract and meaning. Quantitative code performs calculations and claim-specific checks. Neither model fluency nor agreement between models grants a passing validation decision.

The integration ticket must record and verify:

| Integration choice | Required implementation evidence |
|---|---|
| Runtime and model identity | Pin the Hermes revision, provider/model configuration, interpretation contract and prompt/tool versions. Keep the tested Sol configuration as a baseline candidate, not proof of every future request. |
| Invocation | Submit an authenticated, durable research job with exact input and configuration identities. Separate application progress from provider completion. |
| Tools | Expose only the approved evidence and deterministic calculation operations for the job. Research-record writes remain scoped. Financial tools and signing credentials remain inaccessible. |
| Output | Validate structured output, field evidence and semantic consistency before compiler handoff. Preserve invalid, unsupported and unresolved outcomes separately. |
| Failure handling | Record malformed output, truncation, timeouts, cancellation and provider errors. Preserve completed evidence. Any repair or retry follows the declared policy and records its cost and attempts. |
| Persistence | Save outputs, tool results, model/configuration identities and ledger references in application storage. Reopening a result does not depend on a running chat session. |
| Isolation | Derive ownership from authenticated application identity. Qualify separation of users' jobs, files, memory, credentials, caches, streams and cancellation controls. A session ID alone is not authorization. |
| Cost and resource admission | Record adopted run budgets, measured expected usage, enforceable bounds where required, reservations and actual settlement. Do not treat an estimate as a guaranteed spending ceiling. |

The existing hosted-Hermes assessment recommends fresh tasks in isolated worker processes with narrowly scoped data access. It remains a proposal requiring pinned-runtime qualification. Profiles alone do not establish secure customer isolation. A shared browser session, shared mutable memory or unrestricted host filesystem is not an acceptable tenancy shortcut.

Use the smallest worker arrangement that meets these requirements. A registered agent does not require a permanently running LLM process. Additional replicas or a larger orchestration framework need a measured requirement. Agno AgentOS, LangGraph and separate agent-to-agent services are not mandatory dependencies.

The earlier cost-preflight problems must not become arbitrary production token restrictions. Select settings from actual request sizes, complete-response requirements, provider behavior and the user-approved cost policy. Explicitly explain any enforceable response cap and classify truncation as failure. If a hard monetary ceiling cannot be guaranteed, return the concrete policy choice instead of silently spending or repeatedly applying irrelevant input-capacity bounds.

Inference/API costs, compute credits, provider data charges, native gas and trading capital are separate accounting categories. Open-source agent software does not make hosted inference free. Customer billing, BYOK and subscription access are not selected by this brief. Never assume a personal chat subscription authorizes product inference.

### The deployed agent and persistent worker

A deployed trading agent consists of reviewed rules, its own wallet, an execution mandate and durable operating state. It is not an indefinitely running Hermes conversation.

Builder-approved memory, 2026-10-06: implement the [thin per-agent memory contract and MEM-Q01–05 checks](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-thin-per-agent-memory-contract). Context lives in the selected application store. Qualify isolated task retrieval and provide owner inspection/correction/disable/clear controls. This requirement does not adopt full Hermes feature parity, change financial authority or prove any unrun check.

| Component | Responsibility |
|---|---|
| Authenticated application and API | Own records, access control, user reviews and shared UI/tool contracts. |
| Evidence gateway | Collect and normalize approved data while preserving provenance, units, timing, quality and missingness. |
| Interpreter and investigator | Propose meaning, questions, hypotheses and explanations through Hermes or another qualified implementation. |
| Compiler and evaluator | Reject unsupported meaning, publish immutable rules and perform deterministic research/simulation calculations. |
| Persistent worker | Schedule decisions, maintain progress, recover state and coordinate actions for each agent wallet. |
| Deterministic risk engine | Check exact authority, ownership, limits, data, inventory, reservations and current eligibility. |
| Restricted execution host | Encode the qualified Flow action and request signing only after admission passes. |
| Privy policy and signer | Independently enforce the restrictions qualified for the selected wallet and transaction format. |
| Reconciliation and accounting | Resolve transaction outcomes, update actual balances/positions and retain unknown outcomes without duplication. |

The worker starts in recovery. It checks existing intents and pending transactions before evaluating a new action. It persists an intent, transaction fields and reservations before submission. A lost acknowledgement produces an unknown outcome requiring reconciliation, not a new transaction.

Initially, each agent wallet has one durable submission/reconciliation queue with one unresolved economic transaction. Multiple positions and concurrent monitoring remain supported. Agent A's unknown transaction does not automatically block Agent B's separate wallet. Shared infrastructure failures may affect both.

Eligible exits precede unsent entries/additions. The worker checks authority, expiry, stop scope, freshness, inventory and limits again at submission. Queue priority cannot preempt a broadcast action or bypass an unknown outcome. Qualify actual waiting times for the supported strategy before claiming suitable live timing.

Ordinary permitted actions require no new user signature each time. The chosen transport remains subject to Probe B: Privy submits, or Privy signs and the approved RPC transport broadcasts. There is no local-key fallback. The execution credential cannot weaken its own policy.

Jev-style model assessment is optional. Add it only for an accepted role with defined inputs, labels, abstention and comparison against a simpler baseline. It cannot calculate authoritative account values, override risk or expand the strategy. The cloned JEV Trader app is a reference, not the adopted runtime.

### Data and calculation contract

Envio is the preferred historical event source. QuickNode supplies current-state and reconciliation reads under the selected architecture. Kuru Flow is the intended first spot execution route. Keep those roles distinct and qualify exact endpoints and capabilities during implementation.

Bind research to chain/network, underlying venue, pool, token addresses, base/quote orientation, decimals, event version and conversion rules. Bind execution to its separately qualified route. A pool indexed by Kuru is not necessarily a Kuru order book. Route prices and fills cannot be inferred from research-pool coverage.

The accepted initial research language uses price and executed quote volume from one qualified pool per investigation. It includes typed constants, return, numeric-series lag, rolling sum/mean, relative volume, comparisons and three-valued Boolean combinations. The [operator registry and calculation conventions](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-initial-operator-registry) control exact meaning.

Five-minute UTC buckets use the last qualified executed trade as close. An empty bucket has no observed close. Complete empty trade coverage can establish zero volume; incomplete coverage cannot. Lookbacks use scheduled intervals. Missing values remain missing. Preserve all missing reasons, even when another Boolean operand determines the result. UNKNOWN never triggers a trade.

Use the accepted versioned decimal convention, preserving raw amounts and asset decimals. Compare calculation values before display rounding. Warm-up follows actual expression dependencies. Revalidate stored and compressed inputs through the same compiler boundary as fresh inputs.

Historical event time, collection time and usable information time remain separate. Reconstructed delivery assumptions must stay visible. Frozen features and outcomes cannot consume later information. Preserve all variants and failed comparisons. Formal statistical claims require STAT-Q01 qualification; descriptive research does not.

### Wallet accounting and enforcement

Separate agent wallets reduce cross-agent ambiguity but do not alone prove isolated signing authority. Test owner/agent/wallet binding at the application, executor and selected provider boundaries. Address separation cannot compensate for an overbroad execution credential.

Within each agent wallet, reserve capital atomically across positions and pending actions. Record allocation, cumulative input allowance, consumed amounts, reservations, remaining capacity and native gas separately. The same funds or inventory cannot support two commitments.

The accepted sell-permission direction covers attributable position inventory under prior user-approved rules. Unrelated deposits and other positions' holdings do not become that strategy's sell authority. Qualify the enforcement mechanism and full intended exit capacity before admitting entries or additions. A minimum-output quote is not an upper acquisition bound where a fixed sell ceiling requires one.

Record which restrictions deterministic application code enforces and which Privy independently enforces. Do not claim that the provider reads the application's position ledger. An unenforceable required restriction leaves the affected capability unqualified. A different authorization architecture requires a builder decision.

Count each distinct economic submission once when broadcast becomes possible, including reverts. A qualified resend of the same signed transaction retains its identity. Record provider requests separately. Reverts consume an attempt and actual gas; release unused trading-input reservations only after reconciliation. Unknown outcomes retain reservations.

Use weighted average acquisition cost per position while retaining individual acquisitions, additions and exits. Separate realized results, unrealized estimates and capital flows. Unknown costs or marks cannot become zero or profit. Convert native gas into a reporting unit only with a qualified conversion and count it once.

Renewal preserves accounting history. Resume after a temporary fault only when reconciliation, freshness, authority and accounting checks pass. Recovery cannot clear a user stop, trial stop, loss stop, exhausted limit, expiry or revocation.

### Add-ons and the LP proof

The initial add-on direction is a small reviewed catalog: market-investigation instructions, price-and-volume analysis instructions and approved read-only research/account tools through MCP. Enable entries per agent only after their tools and isolation checks pass. Show purpose, access, version, authentication, costs and disconnect effects. Record versions with each run.

Add-ons grant no wallet authority or new compiler operations. Disabling a research tool does not revoke an execution mandate or undo submitted work. Custom code, arbitrary MCP URLs and a public marketplace remain outside the first catalog. OpenBB is an optional reuse candidate. External market charts are secondary context with exact pool identity, not a replacement for the evidence gateway.

After the spot path works, the LP proof declares one pool model and evaluates fees against inventory exposure, impermanent loss, gas and rebalancing costs. Show the declared comparison and missing history. Reuse research records and revision principles, with separate LP actions and simulation semantics. Live LP execution remains a separately qualified adapter, not a consequence of a successful Flow swap.

## 7. Reusable runtime verification in the first slice

No application startup or verification command exists in the shared checkout at this review. The first runnable slice must supply and exercise the smallest useful setup:

1. Start an isolated development instance with known records and documented configuration. Default verification uses deterministic fixtures and no real funds; live model/provider checks are separately authorized and labeled.
2. Submit a supported request through the actual UI/API path, resolve a necessary clarification and retrieve the saved interpretation/rules/result. Confirm restrictions and revision identity survived persistence and reload. Exercise invalid/unsupported input and a second user's denied access.
3. Inspect the actual stored records and response references, not only a screenshot or an assertion that returned HTTP success. Include failure/restart behavior applicable to that slice.
4. Capture the source revision, command, fixture identities, observed outputs and limitations. Clean up only the instance/data created for the check.
5. Leave concise instructions and a small feature-to-check index so a fresh agent can repeat the path. Update them in the same PR when the path changes. Start with existing test/start commands; do not build a custom control CLI or a large verification framework in advance.

Apply the adopted [implementation/review workflow](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md): tests, runtime checks and evidenced defect review answer different questions. Use Impeccable for clarity and participant attempts for comprehension. Carry full keyboard, screen-reader and physical-phone checks into affected UI tickets. Written procedures, critique scores and clean detectors do not prove runtime behavior or understanding.

### Acceptance evidence by working path

| Working path | Observable completion evidence |
|---|---|
| Intake and clarification | Submit all three starting states. Preserve restrictions and field origins through a fresh clarification. Reject another user's record access. Save and reopen the exact result. |
| Compiler | Supported rules retain strict/inclusive comparisons, units, timing and missing-value behavior through compile/reload. Invalid or future-dependent expressions fail without being hidden by Boolean simplification. |
| Research | Run one approved investigation. Reconcile every variant, source and evaluation with its ledger. Produce a useful unresolved report when the evidence cannot support the claim. |
| Simulation | Reproduce saved trade and account calculations from fixed inputs. Match independent small examples and retain unsupported or missing cases. |
| Wallet lifecycle | Create and recover one wallet identity per agent. Prove cross-agent denial, funding status, withdrawal coordination and retained owner access. |
| Activation and operation | Bind the exact revision, agent wallet and mandate. Observe an allowed action and independent denial. Restart without a duplicate and verify removal blocks new submission. |
| Positions and conversation | Both paths identify the same current record and action target. An ambiguous same-token request asks which position. Pending status never appears as a completed sale. |
| Stops and continuation | Stop one agent before its first trade without affecting another. Preserve pending exposure and accounting through continuation, expiry and renewal. |
| LP proof | Reproduce the declared pool comparison with fee, inventory and cost limitations. Do not report gross fees as net benefit. |

Retain a small interpretation regression set from the probe failures and add new user failures. Include invented assumptions, multiple/invalid objects, unsupported meaning, unresolved adopted settings and clarification binding. A passing model batch is evidence for those cases and that configuration, not universal reliability.

Required test fixtures must be present in a fresh checkout or supplied as approved artifacts. A missing mandatory fixture is a failed verification setup, not a silently skipped passing test. Review the combined application path after integration, not only each worker's isolated changes.

For UI acceptance, record what a participant understood before explaining the screen. Builder-assisted attempts remain assisted. Missing independent comprehension or accessibility evidence remains a stated limit, even when all automated checks pass.

## 8. Decisions before work becomes ready

P01 stack direction accepted, 2026-10-06: use the [canonical application stack](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-application-stack) and [ADR 0008](adr/0008-python-api-postgresql-nextjs-privy-auth.md). Python/FastAPI, PostgreSQL, Next.js and Privy authentication are selected. Preserve the approved visual export using CSS/Tailwind as appropriate. P01 remains responsible for versions, startup/configuration, migrations, verified owner identity and isolated verification; hosting and worker lifecycle require their applicable handoffs. Login is not execution authority.

| Decision or evidence | Needed before | Current handling |
|---|---|---|
| Review the to-spec synthesis and confirm testing boundaries; record bounded frontend closure separately | Ready implementation assignments | Product scope approved 2026-10-05. Local synthesis review and testing-seam confirmation remain open. Prior participant verdicts are unchanged. |
| App startup/deployment, authenticated ownership and persistence profile | First runnable production ticket | Stack selected under the linked P01 decision; no application exists yet. Freeze compatible versions, startup/configuration, database/migration and Privy verification mechanisms, test isolation and the applicable hosting handoff |
| First-slice schemas, canonical revision encoding and shared sanitized fixtures | Dependent frontend/backend tickets | Accepted meanings exist; machine contracts and applicable production checks remain to be delivered |
| Research runtime/model configuration, provider access, measured resource profile and per-run cost policy | New live research runs | Probe settings and costs are historical evidence, not a fresh allowance; propose settings that fit the task without reinstating arbitrary probe caps |
| Exact supported simulation profile and dataset availability | Working backtest ticket | Freeze timing, sizing, costs, missing-data behavior and calculation checks; qualify required coverage |
| Exact Flow route/transport, wallet enforcement and numerical mandate | Affected execution tickets and any real transaction | [Probe B configuration](prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md#probe-b-outstanding-configuration-and-permissions), WAL-Q01–26 and EXIT-CAP-Q01 remain open; not blockers for independent research/UI |

Formal statistical support stays unavailable until STAT-Q01 qualifies; descriptive research can finish without it. Exact add-on manifests and the LP profile are needed before those tickets, not before the first intake path. Resolve routine engineering details in their scoped task. Use a small experiment for uncertain behavior. Return a consequential architecture change to the builder; use Wayfinder only if several dependent choices need separate sessions.

The previous table is a dependency list, not a requirement to settle every integration before any implementation begins. A first-slice technical decision must identify its chosen option, rejected alternative where material, acceptance check and owner. Add an ADR when the choice is costly to reverse, needs explanation and involves a real trade-off. Keep ordinary parameters and ticket details in their existing records.

The proposed Hermes baseline, hosting boundary, exact structured outcomes and canonical revision protocol need explicit decisions before their dependent code is considered ready. This revision expands the handoff but does not pretend to finish those choices. Recheck current provider documentation through Context7 when selecting an SDK, API or hosted configuration.

## 9. Demo and approval

The intended technical demo includes agent deployment and operation. Its proposed sequence is:

1. Present a trader's question and its adopted interpretation. Show why the agent asked a clarification, if one was needed.
2. Open a research result with supporting and contrary evidence. Show a rejected future-information input or another verified failure case.
3. Show supported rules and the optional historical simulation, once the simulator works. Clearly distinguish the real unresolved MOE report from any separate execution strategy.
4. Create or open the separately identified agent and its wallet. Show funding status and review the exact trading permission. Label any previously completed setup or recorded proof.
5. Show the persistent worker operate while the user is not approving each trade. Inspect a qualified Kuru action, its receipt and the resulting position/account changes.
6. Show a denied action and recovery/removal evidence. Explain remaining holdings or pending transactions. Include the second-domain LP result only when its proof is available.

Keep research, optional testing and live consent distinct. For a controlled execution example, state who authored the strategy and whether its profitability remains unproven. Do not fabricate a winner to connect the demo scenes.

Rehearse the actual product within the three-minute technical-video limit recorded in the contest brief. Use concise screens and clearly labeled recorded evidence where allowed. The exact timing is a later recording decision, not a reason to omit required proof. A scripted account, fixture receipt or one manual swap cannot establish persistent delegated operation.

Probe B proves its bounded action, denial, recovery and removal claims only if those checks pass. Production wallet isolation, intended exits and ongoing runtime behavior require their applicable additional checks. If those cannot be completed, bring the narrower release/demo claim to the builder. Do not present execution as optional decoration while still claiming the complete deployment product is delivered.

The [contest brief](research/00_HACKATHON_BRIEF.md) still governs submission requirements, including real Monad work. A research-only delivery or scripted UI must not be presented as satisfying the complete onchain product requirement. No deadline, eligibility or external provider fact was reverified in this consolidation pass.

The builder approved specification scope and requested local review of its synthesis. A later reduction requires an explicit NARROW decision. Bounded frontend closure remains separately recorded. After review and dependent contract decisions, authorize ticket creation and shared publication. Implementation starts on accepted assignments. Paid calls, wallets, transactions and merging retain separate approvals.

## 10. From this brief to accepted implementation

An existing specification already describes Edge OS. Do not create a competing specification after this brief.

1. Review this release scope and identify corrections or explicit cuts. Retain agent deployment as part of the intended complete product.
2. Use `to-spec` to reconcile the existing specification with accepted decisions and this brief. Resolve contradictions and confirm where the behavior will be tested. Synthesize the existing discussion without another broad interview.
3. Accept the specification/build scope or a named independent slice. Keep unresolved execution qualification attached only to dependent work.
4. Use `to-tickets` to propose demonstrable end-to-end slices with owners, blockers, acceptance checks and required evidence. Review the proposed breakdown before publishing it.
5. Implement the first ready path in a fresh session using the adopted executor. Include repeatable startup, known data, real saved-record inspection and failure checks in that work.
6. Use `implement-spec` only when explicitly selected for a bounded accepted ticket batch. Preserve one orchestrator, clear dependencies, shared-contract ownership and combined integration checks.

The first proposed slice is request, interpretation/clarification, supported rules, persistence and reopening the result. It connects the required UI, model adapter, compiler, API and storage boundaries. Its normal tests can use deterministic fixtures. A separately authorized real-model check must establish the actual integration before claiming that path works with Hermes.

Frontend and backend contributors can work concurrently within the agreed slice. Their shared contract must identify exact records and errors. Serialize changes to shared schemas or assign a single owner. A teammate must not infer a contract from a private chat or an unavailable course archive.

Matt's workflow governs accepted-ticket implementation. Compass governs product scope, remaining proof and the release decision. The retained Poteto lesson is repeatable runtime verification by a fresh agent. General Review Protocol checks evidenced defects, Impeccable checks the interface, and participant testing checks understanding. None substitutes for another.

`implement-spec` coordination does not authorize automatic main-branch merges, financial actions or a wider scope. Builder acceptance and the repository's manual merge policy remain in force. Integration-branch progress must refer to actual verified commits; tracker state alone is not completion evidence. Fix concrete review findings and confirm them rather than repeat broad reviews to improve a score.

### Source and maintenance notes

The [specification](superpowers/specs/2026-09-29-edge-os-hackathon-design.md), [research contracts](EDGE_OS_RESEARCH_CONTRACTS.md), [domain vocabulary](../CONTEXT.md), [ADRs](adr/0007-separate-user-owned-agent-wallets.md), [Compass workflow](EDGE_OS_COMPASS_WORKFLOW.md) and [Matt workflow](../playbooks/MATT_POCOCK_PROJECT_WORKFLOW.md) are the shared references. Exact schemas and execution checks belong in their designated contracts and accepted tickets, with links from this brief.

Builder-only context consulted for this expansion includes the Edge OS idea inbox, the external `monad_agentic_strategy_launchpad_synthesis.md`, the hosted-Hermes assessment and the workflow-alignment assessment. These preserve product reasoning and source limitations. Their older mandatory-validation sequence, broad tool ambitions or example model roles do not override later accepted decisions. Publish a sanitized verified extract before making any private source a teammate dependency.

This update changes documentation only. It does not rerun probes, open the MOE holdout, change the prototype, qualify providers, select final machine schemas or publish implementation tickets.
