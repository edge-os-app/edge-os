# Edge OS research contracts

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Last updated: 2026-10-02, Africa/Kinshasa

Status: `DRAFT FOR BUILDER REVIEW`. The builder authorized this documentation revision, not implementation, a paid investigation, or the complete product design. Nansen qualification is `NOT_STARTED`.

## 1. Purpose and authority

Use this document when defining an `EdgeSpec`, accepting a research-agent result, building research fixtures, qualifying a data source, or deciding whether evidence can enter quantitative evaluation. It defines the detailed research contracts referenced by the [design](superpowers/specs/2026-09-29-edge-os-hackathon-design.md) and [Compass workflow](EDGE_OS_COMPASS_WORKFLOW.md).

The workflow controls stages and approval. The design controls settled product behavior after builder approval. These contracts remain proposed until reviewed with that design. On a disagreement, record it for the builder instead of silently replacing an approved decision.

This is a documentation contract, not executable schemas or passing test evidence. The build brief will freeze versioned schemas, units and real fixtures after the existing review gates. Broad search, new execution domains, track selection and bounty selection remain outside this revision.

## 2. Research order and completion boundaries

1. Record the observed behavior or bounded research question. Preserve its source and uncertainty.
2. Create an `EdgeSpec` with explicit mechanism questions. An unexplained anomaly may remain a research hypothesis.
3. Freeze the `ResearchBudget` before inspecting outcomes. Declare sources, universe, feature forms, horizons, periods, comparisons, candidate/parameter limits, request/compute/cost limits and stopping conditions.
4. Collect a `ResearchEvidencePackage` linked to the existing `ResearchLedger`. Preserve failures and negative findings.
5. Check evidence completeness and point-in-time suitability. Stop affected claims when required inputs cannot be qualified.
6. Let deterministic quant code evaluate the declared effect and alternatives. Compile capture rules only within supported meaning and recorded evidence coverage.

Each step is complete when its fields and evidence references are present, unknowns are explicit, and its budget/lineage is recorded. Contract completeness means ready for the next review, not profitable, causal, deployable or safe to fund.

## 3. Evidence vocabulary

Use the design's labels for individual claims:

- `VERIFIED FACT`: a cited source or reproducible check supports precisely the stated fact. Documentation verifies the provider's description, not successful live integration.
- `FOUNDER OBSERVATION`: a recorded direct founder experience.
- `DIRECT USER EVIDENCE`: an identified user's recorded event or statement.
- `PRODUCT OR SPONSOR STATEMENT`: a provider's capability, demand or performance statement, with its limits preserved.
- `INFERENCE`: an interpretation derived from referenced observations.
- `HYPOTHESIS`: a claim awaiting the specified test.
- `UNKNOWN`: missing evidence or an unqualified parameter.

Keep evidence label, research conclusion, compilation result, validation decision and execution authority separate. The Robot James library's `AUTHOR_CLAIM`, `DEMONSTRATED` and `INFERENCE` labels describe source provenance; they are not Edge OS deployment states. A model confidence value is not a p-value, calibrated probability, effect size or approval.

## 4. `EdgeSpec`

### Identity and version

Record `edge_id`, `version`, canonical content hash when implemented, parent edge/version, research-run and ledger references, author/generator, creation time, user, domain, market/universe and input class. Attach evidence IDs to each substantive claim. A material change creates a new version and ledger entry; freeze the declared version before evaluating outcomes.

### Mechanism-first fields

| Field | Required answer | Missing-information behavior |
|---|---|---|
| `observed_effect` | What measurable behavior or anomaly starts the investigation? | Ask for an observation or bounded question. |
| `flow_producing_participants` | Which participant/cohort produces the relevant flow, and how is it identified? | Record `UNKNOWN`; do not invent identity or wallet control. |
| `participant_incentive_or_constraint` | Why might participants willingly or necessarily accept unfavorable prices? | Keep the explanation a hypothesis or unknown. |
| `economic_mechanism` | How could this behavior create the proposed benefit? | Separate the observed association from a proposed causal explanation. |
| `persistence_thesis` | Why might faster or better-funded competition leave an opportunity? | Investigate capacity, risk or operational friction; do not assert persistence. |
| `capture_mechanism` | What simple action might capture the effect, and which risks would it accept? | Preserve as proposed meaning, not an execution instruction. |
| `trigger_and_regime` | When should the effect arise, in which market conditions? | Request measurable conditions. |
| `expected_direction_and_horizon` | Which outcome is predicted and over what period? | Require a declared outcome and horizon before its test. |
| `costs_frictions_and_capacity` | Which fees, spread, slippage, impact, latency, liquidity, adverse selection and size limits matter? | Record unmeasured costs; do not claim net tradability. |
| `required_evidence` | Which datasets, fields, resolutions, units and timing boundaries would test the claim? | Mark unavailable dependencies explicitly. |
| `alternative_explanations` | What simpler effect, confounder or substitute explanation could account for it? | Include an explicit review of alternatives. |
| `falsification_conditions` | Which observations or declared test results would weaken or reject it? | Require checkable criteria before outcome analysis. |
| `mechanism_health_observations` | What changes would indicate the explanation is weakening, beyond PnL? | Record proposed measures and unknowns; no automatic decay controller is added. |
| `evidence_and_data_status` | What is supported, inferred, hypothetical or unavailable? | Retain uncertainty and distinguish historical from forward coverage. |

The participant need not be a guaranteed loser or be forced to trade. Hedging, liquidity needs, incentives and voluntary behavior may produce a plausible explanation. That explanation remains a hypothesis until evidence supports it. A repeatable statistical association does not independently establish causation.

An unexplained statistical effect may enter bounded investigation. Missing meaning, timing or essential data produces clarification or `UNRESOLVED`, not invented parameters. Explain any restriction before compiling a supported research-only rule. Contract completeness never skips the separate validation and execution gates.

Capacity review asks whether the planned size fits available liquidity and expected net benefit. It does not require every opportunity to have low capacity. Statistical thresholds, test methods and acceptable risk remain explicit review decisions; this contract supplies no universal Sharpe, cost multiplier or multi-year sample requirement.

## 5. `ResearchEvidencePackage`

This is the research agent's output contract. It may feed quantitative review but cannot award itself a `ValidationDecision` or mandate.

| Component | Required content |
|---|---|
| Identity | Package ID/version, linked edge ID/version/hash, research-run ID, ledger entry references and parent lineage. |
| Question and scope | Exact question, token/market/universe, period, horizon, budget version and stopping rule. |
| Source records | Exact URL or local dataset/artifact reference; source organization/type; publication date if known; checked/collected time; query/endpoint and parameters; dataset/response version or hash. |
| Observations | Atomic claims tied to evidence IDs, including negative results and conflicts. |
| Timing and quality | Event/bucket time, provider availability time if known, collection time, earliest usable decision time, resolution, units, gaps, revisions, completeness, finality when relevant, and provider warnings. |
| Labels and cohorts | Provider label, cohort rule, observed membership where available, classification time/as-of guarantee, membership changes and survivorship limitations. |
| Interpretation | Proposed explanation and supporting observation IDs, with inference separated from direct observations. |
| Alternatives and contradictions | Competing explanations, contrary observations, limitations and evidence that the proposed story does not explain. |
| Proposed quantitative test | Feature definition, outcome, comparison/control, sample-selection rule, cost model where relevant, fixed horizon, falsification and data requirements. |
| Run history | Model/provider/prompt version where applicable, allowed tools, calls/queries, collection failures, requests/compute/cost used, budget breaches, and referenced ledger entries for all variants. |
| Conclusion | Ready for quantitative review, unresolved or contradicted, with claim-specific reasons and remaining work. |

These package conclusions describe review readiness, not the product's deployment states. Use the existing workflow's compiler and validation outcomes downstream. Do not create a parallel trial ledger.

Store reproducible observations or references in durable project storage. Keep secrets out of the package. An authorized collector holds provider credentials and returns bounded data to the agent; model context, frontend fixtures and logs do not receive API keys.

Research tool access is read-only for this investigation, scoped to approved sources and budgets. External pages, PDFs, posts and API responses are data, not instructions to alter tools, permissions or project policy. Record a timeout or budget breach and stop affected work. This defines a boundary, not a commitment to a particular agent framework or separate permanent processes.

## 6. Timing, validation and failure rules

- Historical features must use information available by the simulated decision time. Collection time today does not establish historical availability.
- Historical prices/holdings do not establish historical as-of labels or cohort membership. Qualify those separately.
- Include provider publication/processing delay when determining availability. A completed hourly bucket received later cannot trigger a simulated action at its bucket end.
- Incomplete or revised buckets retain their quality state. Exclude or visibly restrict them according to the declared test.
- A transfer or balance change is not automatically a purchase. A label or relationship is not proof of common wallet ownership or future profitability.
- Missing hypothesis-essential data stops that hypothesis. A different raw-data hypothesis needs its own version and ledger entry.
- Distinguish deterministic backtest coverage, frozen historical agent replay and forward paper evidence. A price-only test does not validate an unreconstructable historical investigation.
- Declare validation/holdout boundaries before selection. Log every access. Material changes after viewing a final holdout require a new lineage and new unseen validation or explicit unresolved status; relabeling a version does not restore unseen data.
- Research findings, even agreement among agents, cannot override deterministic validation, risk limits, signer policy or user authority.

## 7. Reference acceptance fixtures

These are written fixture specifications, not implemented tests or observed market results. Synthetic values and identities must be labeled `SYNTHETIC_FIXTURE` and separated from live-source observations.

| Fixture | Input and expected behavior |
|---|---|
| Complete research hypothesis | A synthetic observed flow with a declared participant, incentive hypothesis, persistence question, comparison, horizon, falsification and internally matching evidence IDs. Accept for quant review; do not declare profitability or causal proof. |
| Vague wallet thesis | "Profitable wallets buy before pumps" with unidentified wallets, timing and cohort rule. Expose missing fields and return clarification or unresolved. |
| Unexplained anomaly | Measurable association with an unknown economic explanation. Allow bounded investigation while keeping mechanism status unknown. |
| Unsupported purchase claim | A transfer-only record described as buying. Fail the purchase interpretation; retain the transfer observation if qualified. |
| Future label leakage | Historical prices combined with labels learned after the decision. Stop the affected backtest; permit a separately declared forward investigation. |
| Incomplete bucket | Current partial flow presented as a completed historical feature. Reject that use or explicitly restrict the analysis. |
| Provider loss | A label-dependent hypothesis loses labels. Return unresolved for that hypothesis; a different venue-only question needs a new declaration. |
| Hidden negative result | An agent omits a contrary result or unreported variant found in the ledger. Fail package review until the record is complete. |
| Budget or authority breach | Excess calls, unrecorded costs, or a request to authorize capital. Stop the research run or deny the unsupported authority request and record the reason. |

Before implementation, the builder reviews these fixtures and freezes machine-checkable schemas in the build brief. The first fixture tests contract behavior; it does not bypass evidence qualification.

### Illustrative acceptable package

This example is entirely `SYNTHETIC_FIXTURE`. Its token, participants, values and observations are invented for contract review. The notation is illustrative, not an approved production schema or a passing test.

| Component | Example content |
|---|---|
| Identity | Package `fixture-package-01`, version `1`; edge `fixture-edge-01`, version `1`; run `fixture-run-01`; ledger `fixture-ledger-01`; no parent. Hash remains unimplemented. |
| Question and scope | For fictional token `TOKEN-A` on fictional venue `VENUE-A`, does qualified cohort balance growth precede the next-hour price response rather than follow a rise? Two synthetic observations, one horizon, no optimization. Budget `fixture-budget-01`: two fixture reads, no external requests or paid credits. |
| Source records | Source `fixture-flow-01`, version `1`, from the in-memory fixture; collected at `2026-09-30T10:05:00Z`. Source `fixture-price-01`, version `1`, contains fictional price observations. No external source URL or real transaction exists. |
| Observations | `obs-01`: cohort balance rises from 100 to 105 fixture units during 09:00–10:00 UTC. `obs-02`: price was already rising during that interval. Neither observation proves a purchase, predictive benefit or causation. |
| Timing and quality | Complete synthetic interval; earliest flow availability 10:05 UTC. A proposed outcome starts at 10:05, not 10:00. Units, interval boundaries and missing execution-cost data are explicit. No blockchain finality claim applies. |
| Labels and cohorts | Fictional membership frozen at 08:00 UTC and included in the fixture. This models an as-of boundary; it does not demonstrate a provider's historical labels. |
| Interpretation | `HYPOTHESIS`: balance growth might contain information beyond preceding momentum. Participant incentive and competition/persistence are `UNKNOWN`. Do not invent an economic explanation. |
| Alternatives and contradictions | `obs-02` supports the competing explanation that the cohort follows an existing price rise. Transfers or custody changes could also explain `obs-01`. |
| Proposed test | Compare the declared balance-change feature with the subsequent one-hour response while accounting for preceding one-hour price movement. The two records test pipeline behavior only; they cannot establish a statistical effect or net tradability. |
| Run history | Two fixture reads, zero external calls, zero paid credits, no model invocation; all variants and negative observations linked to the fixture ledger. |
| Conclusion | Contract review may accept a bounded investigation of the association. The mechanism remains unresolved and no strategy, validation result or execution authority is granted. |

The linked fixture `EdgeSpec` records the measurable balance-change effect, the frozen fictional cohort, the declared timing, `obs-01` and `obs-02`, and the competing momentum explanation. Incentives, persistence, costs, capacity and capture rules remain explicitly unknown. Its proposed falsification question is whether the association disappears when preceding price movement is accounted for. Its proposed health observations track coverage and cohort stability; they are not implemented monitors.

### Deliberately invalid variants

- **Missing evidence:** remove `obs-01`'s source reference while retaining its consequential claim. Package review fails until the claim is sourced or withdrawn.
- **Future information:** change earliest availability to 10:05 but simulate an action at 10:00. Historical use fails the timing check.
- **Invented buying:** rename balance growth to a DEX purchase without a trade record. Reject the buying interpretation; retain only the supported balance change.
- **Hidden contradiction:** omit `obs-02` from the conclusion and ledger-linked review. Package review fails for missing contrary evidence.
- **Budget breach:** use three reads against a declared two-read limit. Stop and record the breach rather than silently increasing the budget.
- **Invented mechanism:** fill unknown incentives with "the cohort always knows future prices." Return the unsupported claim for clarification; do not approve a causal explanation.

These are expected review outcomes, not observed test results. A real implementation must assert them against the frozen schemas and fixtures.

## 8. Nansen qualification investigation

### Status and objective

Investigation ID: `NANSEN-Q01`. Status: `NOT_STARTED`. No token, venue, paid access, request budget or strategy has been selected or approved by this document.

Proposed question for review:

> For one Monad meme token with verified venue and Nansen coverage, does a defined labeled cohort's accumulation precede a positive next-hour price response, or mainly follow an existing rise?

The initial objective is data qualification. It asks whether the inputs can support an honest test. A small qualification sample cannot establish an edge, causality, demand or deployability.

### Decisions required before running

- Builder selects one token/venue from a declared coverage/liquidity rule, not from favorable outcomes, and records address and market identity.
- Builder fixes cohort/label definition, observation window, outcome, comparison, sample period, feature units and intended interpretation.
- Proposed horizon is one hour following information availability, not automatically following bucket end. Compare with the preceding one-hour price movement. Changes are new declared variants.
- Builder approves a numeric request limit and cost/credit ceiling after account access and endpoint cost are known. No paid or authenticated calls are authorized by this documentation update.
- Record whether the first sample is historical qualification or prospective collection. API secrets stay with the authorized collector.

### Bounded procedure and completion criteria

1. **Declare.** Create edge, budget and ledger records with the decisions above. Complete when no executable query or outcome rule depends on an unstated choice.
2. **Qualify access and coverage.** Check the exact official endpoint, Monad/token support, earliest usable period, resolution, units, pagination, latency, rate/cost limits and missing fields. Complete when supported and unsupported requirements are recorded, including access failures.
3. **Qualify interpretation.** Determine whether records represent trades, transfers, balance changes or mixed flows. Use transfer/flow language unless actual buying is evidenced. Complete when feature meaning matches the returned data.
4. **Qualify time and cohorts.** Check historical availability, label timing, membership changes and bucket completeness. If historical classification cannot be established, return historical suitability as unresolved and propose forward collection. Freeze membership where possible or preserve changes; absence of member identities remains a limitation. Complete when each proposed feature has a supported availability boundary or an explicit blocker.
5. **Reconcile.** Cross-check a small declared sample against venue or chain records where those identifiers exist. For aggregate-only results, cross-check reproducible underlying components where available and label what cannot be reconciled. Check address, time, direction, units, duplicates and revisions. Complete when discrepancies are recorded, not hidden.
6. **Assess joining and incremental information.** Determine whether qualified observations join to price/liquidity at the declared resolution, and whether enrichment supplies information missing from raw venue history. Record costs/executable-price limitations. Effect testing is a separately recorded next step, not a required favorable result of qualification.
7. **Report.** Produce a package and qualification report with sources, responses/artifact references, request/cost log, checks and limitations. Allowed qualification conclusions are suitable for the specified historical test, suitable for a specified forward test only, unresolved, or unsuitable. None is an alpha approval.

Create `docs/research/NANSEN_DATA_QUALIFICATION.md` only when an actual authorized investigation produces evidence or an observed access failure. Do not create a completed-results placeholder now. Link its package/run references to `ResearchLedger` when the application storage exists. Until then, a bounded documentary run record must retain the same identity, budget and lineage.

### Documentation constraints, checked 2026-09-30

- Nansen lists Monad support per endpoint family; this is documentation, not tested account/token coverage. [Supported chains](https://docs.nansen.ai/reference/chains).
- Smart Money netflows combine DEX activity and CEX transfers, use rolling windows ending at request time, and retain 30 days without arbitrary older backfill. Do not turn this endpoint into an invented long-range purchase series. [Netflows](https://docs.nansen.ai/api/smart-money/netflows).
- Token God Mode flows use hourly buckets for ranges up to seven days and daily buckets for longer ranges. Completeness describes bucket/window coverage, not permanent finality; DEX/CEX breakdown is limited to the exchange label. Check the exact fields needed for the proposed feature. [Flows](https://docs.nansen.ai/api/token-god-mode/flows).
- Historical holdings are daily snapshots with beta limitations; historical pricing is not an as-of cohort guarantee. [Historical holdings](https://docs.nansen.ai/api/smart-money/historical-holdings).

Use current direct official documentation before implementing requests. The provider audit, BUILDER-ONLY REFERENCE `docs/research/09_EDGE_OS_ORIGINAL_VISION_AND_DATA_ROLE_AUDIT.md#nansen` records conflicting Context7 snippets. No API syntax is frozen here. Missing history may support a forward test, not retrospective use of today's classification.

Perpl data remains conditional on a separately declared hypothesis needing perpetual-market observations. This revision adds neither a Perpl integration nor perpetual execution. Broad QT401 search, marketplaces, strategy tokens and additional execution domains remain deferred.

## 9. Team interfaces and review gate

The builder owns all prototyping. The teammate responsibilities below are implementation responsibilities for accepted tickets, using published findings, contracts and fixtures.

| Owner | Responsibility |
|---|---|
| Builder | Mechanism fields, hypotheses, feature units/definitions, test selection, budgets, falsification, promotion rules and representative fixtures. |
| Platform teammate | Authorized bounded collection, provenance, durable records, reconciliation, budget enforcement and secret isolation. |
| Frontend teammate | Show observations, interpretations, missing evidence, comparison, quality/coverage, budget state and rejection reasons separately. Clearly label synthetic replay. |

Completion of this documentation revision means the definitions, examples, source pointers and unrun qualification plan agree across the design/workflow/handoff. It does not mean passing fixtures, approved schemas, a Nansen integration or a completed Compass gate.

Next action: the builder reviews these contracts with the design and chooses `APPROVE`, `REVISE` or `NARROW`. Preserve the Compass challenge and build-brief gates. Obtain separate approval for account-level access costs and the instantiated Nansen investigation before running it.

## 10. Source interpretation

Robot James supplies the mechanism-first research lens. QT101 to QT401 supply separate measurement, simulation, compiler and bounded-search context. Neither source class independently proves Monad-specific profitability.

The archived Robot James thread, BUILDER-ONLY REFERENCE `course-insights/robot-james/articles/raw/Thread by @therobotjames on Thread Reader App – Thread Reader App.pdf` discusses participants willing or forced to trade at unfavorable prices, competition, simple capture rules and monitoring underlying conditions. The PDF was copied unchanged on 2026-09-30 and read locally; see source manifest, BUILDER-ONLY REFERENCE `course-insights/robot-james/SOURCE_MANIFEST.md#archived-thread`.

These contracts are Edge OS design inferences, not verbatim instructions from James. Preserve source limitations and the review queue in the evidence audit, BUILDER-ONLY REFERENCE `course-insights/robot-james/synthesis/EVIDENCE_AUDIT.md`. Do not import sample thresholds or source-specific time windows as universal implementation requirements.
