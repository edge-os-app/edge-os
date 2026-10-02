# Edge OS hackathon design

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](../../agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Status: `DRAFT FOR BUILDER REVIEW`

Date: 2026-09-29, Africa/Kinshasa

Last updated: 2026-10-02, Africa/Kinshasa

Revision scope: two-domain product framing, explicit LP research proof, locked strategy semantics, immutable revision publication, shared tool outcomes and regression checks derived from the Keel/GT reviews and amended compiler verification. Existing delegation, recovery and research contracts remain in force. The builder authorized documentation changes, not design approval or implementation. Compass remains Phase 3. Nansen qualification is `NOT_STARTED`; Monad–Kuru delegated execution remains unproved.

2026-10-02 amendment: name the optional Hermes research and Jev assessment roles while keeping their contracts independent of the selected runtime or model. This amendment does not adopt either dependency, start implementation or change execution authority.

2026-10-02 scoped-probe amendment: propose separate research/compiler/rejection and Monad–Kuru delegation probes before final production planning. Their detailed conditions are in [the shared probe plan](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md). Documentation changes are authorized; both probes remain `NOT_STARTED` and await their own approved boundaries. The two-domain product, full acceptance checks and execution-authority limits remain unchanged.

## 1. Purpose

This document defines the smallest complete Edge OS product for Monad Metropolis. It applies the Hackathon Winning Compass to the selected Edge OS idea.

This document does not authorize implementation. The builder must approve or revise the full design before full-product implementation. A narrow experiment may proceed earlier after the builder approves its scoped design and instantiated plan. That approval applies only to the named experiment, not the complete product, paid access or financial execution.

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
10. This document will control product behavior after the builder approves it.

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

For the first spot path, the investigation concerns a finite set of Kuru meme markets. For the LP path, it concerns declared pools and a liquidity-management question. The available venue, data and action vocabulary constrain each investigation separately.

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

> Convert a thesis, intuition, or bounded research request into an inspectable edge hypothesis and typed strategy. Test it under point-in-time and execution constraints. Reject or defer unsupported results. Let the user deploy a strategy under a revocable execution mandate. Permit only actions that pass deterministic checks and the delegated wallet policy.

The shared job applies to spot and LP strategies. The initial LP result is research, compilation and simulation; live LP execution has a separate venue/adapter gate in section 15. The first spot onchain proof permits at most one order placement under a short-lived mandate. Any required cancellation or token approval must have a separate explicit permission and limit.

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

Saving a draft and returning `COMPILED` are separate persistence/compiler outcomes, not research eligibility or execution authority. An incomplete draft can be preserved with its findings. Each later transition requires its own evidence gate; a save, tool success or compiler result cannot grant one of the readiness states above.

## 4. Product explanation

### One sentence

> For meme traders and liquidity providers, Edge OS turns a thesis, intuition or bounded research request into an inspectable hypothesis and typed strategy, tests it, rejects unsupported results, and permits Monad actions only under a user-approved, revocable mandate.

### One minute

Edge OS is for meme traders and liquidity providers who want to investigate an opportunity before risking capital. It accepts a thesis, intuition or bounded research request, records every tested variant, and makes missing assumptions visible. It produces an `EdgeSpec` and compiles supported meaning into an inspectable `StrategySpec`. Spot tests include execution costs and liquidity. LP tests include fees, inventory exposure, impermanent loss and rebalancing costs. Unsupported results are rejected or left unresolved. The first execution proof is one Kuru spot action under a revocable Privy mandate, with deterministic checks and an inspectable receipt. A persistent worker can act within that authority while the user is offline. LP support starts with research, compilation and simulation; live LP actions require a verified adapter. Envio supplies event history, QuickNode supplies current state, and X is optional evidence.

## 5. Product scope

### Product MVP

The product MVP has two action domains:

1. Meme-token spot strategies on Kuru.
2. LP research and strategies over declared Monad pools, with execution conditional on a verified venue and adapter.

Both domains share the research ledger, edge representation, strategy compiler, validation decisions, risk boundary, and receipts. They use separate simulators and action vocabularies.

The LP result required for the second proof is an inspectable research decision and compile-and-simulate path. This does not promise live LP deployment. Spot-first build order is not a change to the two-domain product frame.

### First dangerous-claim prototype

The first prototype supports one domain:

- Monad meme-token spot markets on Kuru.

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
- Broad QT401 formula search.
- Multi-edge portfolio optimization.
- Automated edge-decay management.
- Live LP portfolio management before the spot path is stable.
- Any claim of guaranteed profitability.

## 6. Accepted inputs

### Concrete thesis

The user supplies a causal or statistical claim with enough detail to identify the market or pool, condition, horizon and expected effect. Spot claims may concern continuation or reversal. LP claims may concern whether fee income compensates for declared inventory and operating costs under specified conditions. These are hypotheses, not assumed edges.

Edge OS extracts the claim and asks only for missing information. It must not change the meaning to make compilation easier.

### Loose intuition

The user supplies an observation such as organic attention, wallet activity, accelerating volume or a suspected reversal after a crowded move. An LP observation may concern changing fees, volatility, inventory or rebalancing frequency. The system asks for missing meaning rather than silently turning the observation into an action.

Edge OS converts the observation into one or more explicit hypotheses. Each hypothesis remains a proposal until validation supports it.

### No-thesis bounded request

The user supplies:

- a finite Kuru market universe for spot, or a finite declared pool universe for LP;
- a finite feature set;
- allowed strategy forms;
- allowed horizons;
- a candidate and compute budget;
- a validation plan.

Edge OS can return zero surviving hypotheses. An unbounded request such as "find any profitable edge" is unsupported.

All three input states apply to both product domains. First implementation coverage remains the bounded spot family; LP coverage must be shown by the separate proof rather than inferred from shared field names.

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
- selected Monad network;
- allowed contracts, markets, tokens, functions, and argument limits;
- per-order notional, aggregate capital, approval, gas, exposure, and loss limits;
- maximum order count, start time, and expiry;
- allowed cancellation and emergency-stop behavior;
- signer identity, attached policy identity, version, and content hash;
- approval evidence, lifecycle state, and revocation evidence.

The demo mandate permits one order placement. The build brief must define exact units and any separately permitted approval or cancellation. An empty or unknown limit denies execution.

### Persistent deployment state

Store the mandate, strategy version, validation decision, worker state, last processed data position, capital reservations, open orders, pending transactions, and intent records durably. Model memory and chat history are not execution state.

## 8. System boundaries

### Prompt interpreter

The prompt interpreter classifies the input and extracts meaning. It can ask for clarification. It cannot emit executable code or add silent assumptions.

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

### Strategy compiler

The compiler converts supported meaning into a typed intermediate representation and canonical `StrategySpec`. It uses a whitelist of data fields, operators, actions, and risk fields.

Resolve locked component metadata before evaluation. Check static input shape, domain types, argument counts, parameter ranges, units and cross-field constraints before data access or effects. State-dependent preflight checks may read current venue and portfolio state, but must pass before a financial effect. Revalidate stored/decompressed input through the same boundary as fresh input. The later course registry demonstrates typed generation; it does not establish a rejecting validator for arbitrary supplied expressions. Sample ranges used by a generator are not the compiler's accepted ranges. Use the amended compiler references in section 2 to choose and test the supported subset.

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
| Market identity and venue behavior | Kuru | Market metadata, trades, order-book state, order events, order actions, fills, and venue-linked proof |
| Historical and live contract events | Envio | Filtered backfill, live indexing, decoded Kuru events, reorg handling, and queryable derived records |
| User wallet and delegated signing | Privy | User-owned embedded wallet, explicit signer consent, policy-scoped signing, and owner removal of the signer |
| Current state and reconciliation | QuickNode, initial provider | `eth_call`, gas estimation, receipts, block-state checks, and WebSocket subscriptions. Broadcast only if the verified transport uses signed transactions from Privy |
| Wallet and trader enrichment | Nansen, optional | Labels, holdings, flows, DEX trades, cohorts, and historical enrichment for a declared hypothesis |
| User wallet summary | Zerion, optional | Portfolio, positions, transaction history, and PnL for the user-facing result |
| Pre-execution trace | Tenderly, optional | Simulation, logs, state effects, and revert diagnosis when the result changes authorization |
| Social attention | Official X API, optional | Timestamped posts and forward engagement snapshots for bounded research |

Optional at platform level does not mean dispensable within every hypothesis. A label- or social-dependent test stops when its essential input is unavailable. A separate onchain-only investigation may continue under its own declaration and ledger entry.

The [Nansen qualification plan](../../EDGE_OS_RESEARCH_CONTRACTS.md#8-nansen-qualification-investigation) is `NOT_STARTED`. It first tests coverage, meaning, timing and reproducibility for one builder-selected token/venue. No token, paid access, budget or trading strategy is approved by this revision. Perpl data requires a separate declared hypothesis; perpetual execution and broad search remain deferred.

The first prototype uses Kuru, Envio, QuickNode, and Privy. Envio HyperRPC is read-only and must not be configured as the execution RPC. Use Monad's public RPC as a fallback only after the required method checks pass. Execute the approved test action only within its user-approved mandate. Keep the Privy signing boundary during provider changes. Alchemy remains optional when a measured requirement justifies it.

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

The first family tests short-horizon directional momentum and reversal in a bounded set of Kuru meme markets.

The allowed first-pass feature groups are:

- lagged Kuru returns;
- executed volume and volume acceleration;
- trade-direction or order-flow imbalance when the source supports it;
- spread and order-book depth;
- available liquidity and estimated price impact;
- wallet-flow features when the source and time boundary are valid;
- optional X attention features collected point in time.

The allowed strategy form is a small expression tree over typed features, comparisons, bounded rolling operations, Boolean conditions, and fixed risk actions. General Python generation is outside the trust boundary.

The search can test whether a declared condition predicts continuation or reversal over the allowed horizon. It must account for the number of variants tested. It must reject results that fail the declared statistical, temporal, execution, or complexity gates.

This design does not assert that momentum, reversal, social attention, or wallet behavior creates a real edge. Those are hypotheses.

## 11. Dangerous claim and prototype

### Dangerous claim

> Edge OS can turn a messy market request into inspectable hypotheses and a typed strategy without silently inventing assumptions. It can also reject a plausible false edge before the result reaches capital.

If this claim fails, Edge OS becomes another prompt-to-bot or backtest generator. The team must test this claim before building the full application.

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

The first execution proof is one Kuru spot limit order under a user-approved, short-lived mandate with:

- one verified Kuru market;
- a fixed maximum notional;
- a fixed price guard;
- an expiry or cancellation rule;
- one explicit delegation approval and a restricted signer;
- no second user signature for the permitted order;
- one Monad transaction receipt;
- a link between the receipt, intent, mandate, wallet-policy content, strategy hash, validation decision, and risk-policy version.

Assensus already records a successful restricted Privy signer test on X Layer testnet, followed by removal and rejected repeat. That proves the narrow delegation pattern. It does not prove Monad, Kuru calldata, order limits, unattended operation, or restart safety. Use its inspected implementation as a reference, not its old chain or policy configuration.

Before claiming the delegated path works, prove a permitted order, a protected-field denial, restart reconciliation without duplicate submission, and a denied action after signer removal. Keep the evidence limits in the Privy research note.

Use a Kuru-supported test environment when one exists and supports the complete order path. If the verified route is mainnet-only, use the smallest safe amount that the builder approves. Do not submit a mainnet order during design or prototype planning.

An unfilled order can still prove order placement when the receipt and Kuru state are visible. A filled order adds fill evidence. The demo must not claim that either result proves profitability.

## 12. Authorization and risk design

### Model and research roles

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

The user reviews the strategy, risk limits, policy summary, expiry, and permitted actions. The user explicitly creates or selects a user-owned embedded wallet and approves its restricted signer. Routine actions within that approved mandate need no further signature.

A new strategy version or expanded permission requires a new approved mandate. Deployment readiness is separate from `READY_FOR_BOUNDED_EXECUTION`. A validated strategy with no active mandate has no execution authority.

The execution host can authorize Privy requests. It cannot use the user's wallet private key. Application credentials and the authorization private key remain in the backend secret store. Neither the LLM, browser bundle, logs, nor receipts receive them.

### Two enforcement layers

Deterministic code checks:

- specification hash;
- validation state;
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

Pause stops new intent generation and submission. Revocation also requests owner-authorized signer removal and records the verified result. A local pause is not proof of Privy revocation.

Revocation cannot undo a broadcast transaction or cancel an existing Kuru order. The interface must show pending transactions and remaining orders. Cancellation requires its own permitted action while authority exists, or a separate owner-authorized action after removal. Never report all exposure closed merely because the signer is gone.

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

The primary path has these screens or states:

1. Input and scope.
2. Clarification.
3. Research budget and evidence sources.
4. Research progress and ledger.
5. `EdgeSpec` and supporting evidence.
6. `StrategySpec` and plain-English interpretation.
7. Validation decision.
8. Risk decision.
9. Strategy deployment and mandate approval.
10. Active, paused, recovering, expired, or revoked deployment.
11. Intent, denial, receipt, order, and fill results.

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

### Frontend and judge experience

Own:

- input and clarification flow;
- evidence, source, timestamp, observation-versus-interpretation, contradiction and coverage views;
- research-ledger views;
- rejection, unresolved, risk-denied, mandate-approval, and receipt states;
- delegation, pause, revoke, recovery, pending-order, and fill views;
- degraded-provider states;
- demo-safe fixture playback;
- visual design and project graphic.

### Platform, Monad, and deployment

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

### Integration rule

The builder publishes versioned JSON schemas and fixtures before the frontend and platform require live quant output.

Freeze the written [research acceptance fixtures](../../EDGE_OS_RESEARCH_CONTRACTS.md#7-reference-acceptance-fixtures) in the build brief. They cover complete and vague hypotheses, unknown mechanisms, transfer-versus-purchase mistakes, future labels, incomplete buckets, provider loss, omitted contradictions and budget/authority breaches. These are proposed fixture cases, not implemented or passing tests.

## 17. Acceptance checks

### Scoped experiments before full-product planning

Read [EDGE_OS_SCOPED_PROBE_PLAN.md](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md) before assigning, approving or running either probe. It controls their frozen inputs, owners, pass/narrow/reject conditions, evidence, time budgets and stop conditions.

- Probe A asks whether one bounded spot investigation preserves meaning and trial history, produces an inspectable typed strategy or useful unresolved result, and rejects a known-invalid attractive case. The builder owns it.
- Probe B asks whether the exact approved Monad–Kuru action works through a restricted Privy delegation and whether denial, recovery and owner removal behave as required. The builder owns it. Reuse the Assensus pattern without treating its old network/configuration as proof of this path.

The probes may run independently once each has the necessary approval. The builder also owns any result-state interaction prototype. Teammates implement accepted UI or platform behavior through assigned tickets after the builder provides the required fixtures, interfaces or mockups. UI work cannot count as quant or chain evidence.

Report each probe's verdict separately. A compiler-only pass cannot pass execution. A receipt cannot pass research. A blocked adapter or unavailable data must remain unresolved; it cannot be converted into a full Compass prototype pass. LP remains in the product scope, but LP simulation/execution, tokenization, new markets and production UI are outside these first two experiments.

Stop each experiment when its question is answered or its approved budget expires. Return findings to the design decision. Use Wayfinder only if dependent, unresolved product decisions remain too broad for one focused session. Its map should resolve core build blockers; optional-token economics need not block these experiments.

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

Map the compiler subset to applicable proposed tests T01–T36. Run only the tests for approved behavior and record exclusions; the source review is not passing test evidence. LP proof must expose the domain-specific outputs in section 15 before it is marked complete. The concrete fixtures and implementation plan remain to be approved.

Delegated-execution readiness has a separate gate. It passes only when all checks succeed:

1. Explicit user consent binds the wallet, strategy version, signer, limits, and expiry.
2. One permitted Kuru action succeeds while the user is offline, without another user signature.
3. A protected-field violation fails at the Privy boundary, independently of a risk-engine denial.
4. Persisted risk, policy, intent, transaction, order, and fill records show what happened.
5. A forced restart after submission reconciles the same action without creating a second order.
6. Owner signer removal is verified. A subsequent equivalent request produces no new transaction.
7. Pending transactions and resting orders remain visible after removal.
8. Policy drift, stale data, ambiguous submission, and missing authority stop new execution.

An adapter blocker is not a passing delegated-execution test. A controlled fixture may prove mechanics, but cannot establish a real trading edge.

Run independent provider-denial probes only in the separately approved, isolated spike environment. Never disable production risk checks to reach Privy. A post-revocation provider probe must distinguish lost signer authority from an earlier local order-count denial.

## 18. Three-minute technical demo contract

Status: `PROVISIONAL; REVISION PENDING PROBE FINDINGS AND BUILDER REVIEW`. The table below is the earlier draft, not a frozen recording script. Revise its object-heavy section and ending after the probes. Follow [the Compass timing](../../../playbooks/HACKATHON_WINNING_COMPASS.md#curated-three-minute-demo): make the main user path the longest uninterrupted segment, show the useful result early, finish working content by 2:55 and retain five seconds of margin. Any unresolved research case and separate execution fixture must remain distinguishable. Optional token behavior belongs only in a separately approved, implemented and tested extension; it does not block these probes.

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
| Exact Kuru deployment and market used for the order proof | Use no address or network assumption in implementation | Verify official deployment and market metadata before the build brief freezes fixtures |
| Whether a full Kuru test order path exists on testnet | Prefer testnet when verified; otherwise use a builder-approved minimum mainnet amount | Resolve before the prototype submits any transaction |
| Exact Kuru calldata restrictions and Privy policy coverage | Keep delegated Monad–Kuru execution `UNPROVED`; reuse Assensus's pattern only | Verify contracts, functions, batch arguments, units, approvals, and policy denial in the approved spike |
| Privy direct submission versus sign-only RPC transport | Keep both as alternatives, not interchangeable retry routes | Select one tested transport before the build brief freezes the adapter |
| Offline execution, restart recovery, and revocation on Monad | Specify the required behavior without claiming completion | Pass the separate delegated-execution gate before presenting an autonomous demo |
| Policy administrator and execution credential separation | Execution cannot weaken its own approved policy | Verify ownership, credential permissions, and content checks before activation |
| X developer approval and processor/storage terms | Keep X optional and use onchain-only mode | Resolve before the product stores or sends raw post text |
| Historical point-in-time X engagement | Begin forward snapshots; exclude missing historical metrics | Resolve per feature before backtesting |
| Nansen coverage, flow meaning, label timing and endpoint boundaries | Keep `NANSEN-Q01` `NOT_STARTED`; optional platform capability, potentially essential hypothesis input | Approve token/venue, declared feature, account costs and budget, then qualify exact endpoint, timing and sample reconciliation before use |
| QuickNode quota and event-plan redemption | Use QuickNode as the initial provider without assuming a private quota | Confirm account-level terms and run the required-method smoke test before the build brief freezes the provider contract |
| Target-user demand | Keep the claim unvalidated | Challenge the one-minute explanation with real users before the build brief closes |
| LP execution venue and proof | Keep the first LP path at compile and simulation | Verify before adding a live LP adapter |
| First compiler subset and numerical policies | Later course definitions are identified; Edge OS adoption and acceptance behavior remain proposed | Freeze grammar, types, units, history/missing/branch rules and budgets in the approved narrow plan, then run applicable compiler tests |
| Canonical semantic identity and publication contract | Require locked semantics and exact revision consumption; no implementation is claimed | Freeze serialization/hash/manifest and publication/result schemas in the build brief; pass component-change, concurrent-edit and unknown-identity tests |
| LP data and simulation coverage | Keep pool model, fee/position history, comparison and costs explicit or unresolved | Approve one bounded LP proof and qualify its data before claiming research or paper readiness; do not infer demand from simulation |

## 20. Review decision

Immediate review: approve or revise [the scoped probe plan](../../prototypes/EDGE_OS_SCOPED_PROBE_PLAN.md). The plan records which inputs and permissions must be instantiated before either experiment can start. Approving that plan does not mark this full design approved or advance a completed Compass gate. Paid services and financial execution require their own explicit limits and approval.

The builder must choose one result for this draft:

- `APPROVE`: the design can proceed to the build brief.
- `REVISE`: list the required changes. Implementation planning remains blocked.
- `NARROW`: remove a domain, input state, data source, or proof before the build brief.

After `APPROVE`, run the Compass Phase 4 challenge with one target user and one technically strong builder or teammate. Record what they misunderstand, doubt, or consider unnecessary. Create `docs/EDGE_OS_BUILD_BRIEF.md` only after that challenge. Freeze schemas, fixtures, the first Kuru operation, mandate and policy limits, provider contracts, runtime recovery, team interfaces, and acceptance tests there. This revision does not approve the full design, start implementation, or mark the Monad–Kuru spike complete.

Review the research contracts alongside the mandate/runtime sections. Approving these written definitions is separate from approving an instantiated Nansen investigation and its paid access. No Nansen qualification result exists yet.

The post-core scope reassessment, BUILDER-ONLY REFERENCE `docs/research/13_EDGE_OS_POST_CORE_SCOPE_AND_DEMO_REASSESSMENT.md` proposes gated publication, tokenization and operating-funding extensions. Their classification and economics remain pending builder approval. The exclusions in section 5 remain outside the core; they do not prohibit specifying an optional extension. No extension is activated by this amendment.
