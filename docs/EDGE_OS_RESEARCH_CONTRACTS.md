# Edge OS research contracts

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Last updated: 2026-10-05, Africa/Kinshasa

Status: `LINKED PRODUCT REQUIREMENTS ACCEPTED; MACHINE SCHEMAS AND QUALIFICATION OPEN`. The builder approved specification scope and requested `to-spec` on 2026-10-05. Explicitly proposed methods, extensions and unresolved technical choices remain proposed. Authored checks remain unrun unless their own evidence says otherwise. No implementation, paid investigation or financial action follows. Nansen qualification is `NOT_STARTED`.

## 1. Purpose and authority

Use this document when defining an `EdgeSpec`, accepting a research-agent result, building research fixtures, qualifying a data source, or deciding whether evidence can enter quantitative evaluation. It defines the detailed research contracts referenced by the [design](superpowers/specs/2026-09-29-edge-os-hackathon-design.md) and [Compass workflow](EDGE_OS_COMPASS_WORKFLOW.md).

The workflow controls stages and approval. The approved design controls settled product behavior and references these detailed definitions. Named proposals and open choices retain that status. On a disagreement, record it for the builder instead of silently replacing an approved decision.

This is a documentation contract, not executable schemas or passing test evidence. The build brief will freeze versioned schemas, units and real fixtures after the existing review gates. Broad search, new execution domains, track selection and bounty selection remain outside this revision.

## 2. Research order and completion boundaries

1. Record the observed behavior or bounded research question. Preserve its source and uncertainty.
2. Create an `EdgeSpec` with explicit mechanism questions. An unexplained anomaly may remain a research hypothesis.
3. Freeze the `ResearchBudget` before inspecting outcomes. Declare sources, universe, feature forms, horizons, periods, comparisons, candidate/parameter limits, request/compute/cost limits and stopping conditions.
4. Collect a `ResearchEvidencePackage` linked to the existing `ResearchLedger`. Preserve failures and negative findings.
5. Check evidence completeness and point-in-time suitability. Stop affected claims when required inputs cannot be qualified.
6. Let deterministic quant code evaluate the declared effect and alternatives. Compile capture rules only within supported meaning and recorded evidence coverage.

These steps describe hypothesis/testing work, not a requirement that every research request yield a formula or backtest. Use the [research-mode definition](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#research-mode-and-observational-investigations) for observational investigations. Executable meaning must be supported and sufficiently specified; its compilation does not imply empirical support. The [live-trading contract](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#live-trading-optional-trials-and-forward-learning) permits user-selected trials or ongoing operation with an unchanged evidence status, including absent or unfavorable historical support.

Each step is complete when its fields and evidence references are present, unknowns are explicit, and its budget/lineage is recorded. Contract completeness means ready for the next review, not profitable, causal, deployable or safe to fund.

For the builder-accepted first production journey, use the [research journey's steps, finished result and failure path](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-first-research-journey) and [accepted initial research inputs](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-initial-research-inputs). The completion boundary, price/volume input scope and [language/history/Boolean policies](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-strategy-language-and-missing-data-policies) are accepted. The [calculation conventions](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-calculation-conventions) are also accepted. The [operator registry](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-initial-operator-registry), [research binding/data route](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-market-binding-and-data-route) and [claim-specific readiness gates](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-claim-specific-support-and-readiness-gates) are also accepted. The [effect outcomes and comparisons](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-effect-outcomes-and-comparisons) are also accepted. The [statistical-support policy](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-statistical-support-policy) is accepted. Exact method profile/qualification, measured resource bounds, and execution qualification remain pending. Product scope was approved on 2026-10-05; that approval does not pass these checks.

### Focused price and volume support checks

The builder accepted price and executed volume as intended initial capability on 2026-10-03. The following focused checks are required before claiming the corresponding support. Both are unrun and builder-owned; this documentation authorizes no collection, prototype or implementation. Freeze the pending definitions before executing either check.

| Check | Required evidence |
|---|---|
| Input qualification | On a declared event sample, verify asset ordering, trade meaning, amount conversion, duplicate handling, bucket completeness and availability against the adopted price/volume definitions. Preserve gross-versus-net limitations and unresolved fields. |
| Compiler support | Authored fixtures verify adopted operations, units, boundary comparisons, parameter handling and missing-data behavior. Label fixtures separately from recorded market research; compilation grants no research or execution readiness. |

These checks qualify a capability; they do not search for an edge, reopen Probe A or establish historical delivery, realistic fills or profitability. An unsuccessful check leaves the affected capability or evidence claim unresolved for the builder's scope decision.

### Typed-language and missing-data acceptance fixtures

Builder accepted the behavior and these focused fixture requirements on 2026-10-03. Status: `AUTHORED REQUIREMENTS; UNRUN`. The [design](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-strategy-language-and-missing-data-policies) owns the policies; these fixtures check them. Use `SYNTHETIC_FIXTURE` identities and preserve the adopted semantics/version. The builder owns execution; none is authorized here. Use the accepted calculation conventions; use the accepted operator registry and freeze resource bounds before implementing the affected checks.

| ID | Authored input | Required result |
|---|---|---|
| TL-01 | A preset and a manually entered expression resolve to the same explicit typed rules and parameters. | Both traverse the same validation/evaluation boundary and have the same semantic result. Presets carry no hidden operands or parameters. |
| TL-02 | Fresh and stored/decompressed expressions contain a wrong argument count, incompatible unit/type, unsupported node or invalid parameter. | The same preflight boundary rejects both representations with the relevant reason; no evaluation or effect occurs. Freeze exact signatures and ranges before running. |
| SH-01 | Scheduled prices are 100, missing, 110. Both endpoint prices have qualified availability by the decision time. Evaluate the two-interval endpoint return. | Return is 10%; retain the intermediate coverage gap. This establishes neither full evidence coverage nor readiness. |
| SH-02 | Use the same three scheduled positions for a three-value rolling aggregate. | UNKNOWN with the missing-position reason. Do not shrink the window to two valid observations or fill it implicitly. |
| SH-03 | A referenced return/lag endpoint is missing or cannot be qualified as available by the decision time. | No qualified numeric result. Preserve missing evidence or the timing blocker; counting earlier valid prices cannot repair the requested lookback. |
| SH-04 | A return spans N scheduled intervals, while a rolling window contains N scheduled values. Include a gap and an extra earlier valid price. | Reference the declared scheduled positions for each operation; the extra earlier price cannot compress the clock. Verify boundary/warm-up dependencies against the frozen operator signatures. |
| BL-01 | All nine pairs of TRUE/FALSE/UNKNOWN for AND and OR; all three NOT inputs. | Match the truth table below; preserve missing reasons even for determinate outputs. |
| BL-02 | FALSE AND UNKNOWN(volume), and TRUE OR UNKNOWN(volume), with recorded missing-source reasons. | FALSE and TRUE respectively; both retain the volume reason. Evidence qualification remains separate, including unresolved hypothesis-essential evidence. Neither output promotes research, paper or execution readiness. |
| BL-03 | FALSE AND a numeric operand; TRUE OR a future-dependent condition. Also test their stored forms and simplified representations. | Reject the invalid type or fail the timing qualification for the whole dependency graph. A decisive sibling cannot remove either defect. |
| BL-04 | NOT UNKNOWN, TRUE AND UNKNOWN, FALSE OR UNKNOWN. | UNKNOWN with preserved reasons; no action trigger. |

| Left | Right | AND | OR |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | TRUE | FALSE | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | TRUE |
| UNKNOWN | FALSE | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

NOT: TRUE → FALSE; FALSE → TRUE; UNKNOWN → UNKNOWN. Reason preservation is tested separately from value correctness. These fixtures qualify the new production capability only; they are not additional Probe A cases, market findings or execution fixtures.

### Calculation-convention acceptance fixtures

Builder accepted these focused fixture requirements on 2026-10-03. Status: `AUTHORED REQUIREMENTS; UNRUN`. The [design's calculation conventions](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-calculation-conventions) are authoritative. Use labeled synthetic events; run these only under a separately authorized implementation/qualification task. They do not amend Probe A or establish market coverage, delivery, fills or profitability.

| ID | Authored input | Required result |
|---|---|---|
| CC-01 | Trades just before 10:00 UTC and exactly at 10:00 UTC. | The first belongs to `[09:55,10:00)` and the second to `[10:00,10:05)`. The earlier bucket close is unavailable before 10:00 regardless of worker polling time. |
| CC-02 | Bucket completes at 10:00; required source evidence arrives at 10:00:07. In another case its historical delivery is unknown. | Earliest qualified use is no earlier than 10:00:07 in the first case. Preserve unknown delivery or a clearly labeled reconstruction assumption in the second; present-day collection is not historical availability proof. |
| CC-03 | Several trades have the same timestamp, arrive in shuffled provider order, and retain block/transaction/log ordering fields. Then omit a required ordering field. | The same chain-ordered trade closes the bucket in every shuffle. Preserve its chain/block/trade identity, timestamp and amounts/size. Missing required ordering evidence blocks close qualification. |
| CC-04 | One completely covered empty bucket and one incomplete event scan. | Neither produces an observed close or silently carried price. Preserve complete-empty versus coverage-unknown reasons. Qualified complete empty coverage establishes zero quote volume; incomplete coverage leaves volume unknown. |
| CC-05 | A large early trade and tiny final trade have different prices. | Last-trade close uses the final qualified trade and exposes its size; it is neither VWAP nor a promised executable fill. |
| CC-06 | A beginner accepts visible proposed values/search ranges; another leaves a consequential value unadopted; an invalid supplied value would fit after clamping. | Record adopted values and origins without demanding that the beginner invent them. Clarify/review the unadopted required value; report the invalid value rather than clamp it. |
| CC-07 | A declared search tests several parameter variants, including a failed and negative variant. | Every attempt/value/outcome remains in the ledger. The final report cannot retain only the best result; adopting a range does not approve unlimited search. |
| CC-08 | Raw integer amounts with differing asset decimals, a recurring decimal ratio and exact half-even tie cases. | Preserve raw inputs; reproduce the declared 50-significant-digit calculation context and half-even rounding without separate 20-digit ingestion quantization. Use the accepted operator registry and frozen machine encoding when running. |
| CC-09 | Calculation values below/equal/above a threshold have identical displayed rounded values; replay with the same convention, then change its version. | Compare calculation values, retain strict/inclusive operator meaning, and reproduce the same-version result. A convention change changes the applicable identity; display rounding cannot change eligibility. Numerical convention alone cannot qualify source prices. |

### Operator, binding and readiness acceptance fixtures

Builder accepted these focused requirements on 2026-10-03. Status: `AUTHORED REQUIREMENTS; UNRUN`. The design's [registry](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-initial-operator-registry), [binding/data route](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-market-binding-and-data-route) and [readiness gates](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-claim-specific-support-and-readiness-gates) own the behavior. Freeze machine encoding/resource bounds and applicable outcome/validation criteria before affected implementation. No collection, execution, prototype or Probe A change is authorized.

| ID | Authored input and required result |
|---|---|
| OB-01 | Typed finite percentage/ratio, quote amount and quote/base price constants preserve explicit representations and units. Reject untyped, non-finite or incompatible-unit thresholds through fresh and stored validation. |
| OB-02 | Lag supported price, volume and derived numeric series, including a missing requested position and an earlier extra valid value. Preserve units and actual scheduled dependencies; reject Boolean-to-numeric coercion. |
| OB-03 | Verify N-value sum/mean includes current, N-interval return uses endpoints, and relative-volume baseline excludes current. Include nested windows and missing values; independently verify warm-up and no window shrinking. |
| OB-04 | Trades of both directions and shuffled duplicate records contain declared quote-asset legs. Sum each qualified quote amount once; never sum both asset legs. Preserve raw amounts/decimals, gross semantics and token-mechanics limitations. A conflicting duplicate requires qualification failure. |
| OB-05 | Complete empty bucket gives volume zero but no observed close. Incomplete scan gives unknown volume. Relative-volume baselines of zero with current zero or positive both give UNKNOWN/ZERO_BASELINE; no epsilon/infinity trigger. |
| OB-06 | Token symbols match but addresses, chain, asset order or WMON/native-MON identity differ. Reject incompatible research binding. A different Kuru route cannot inherit research-pool qualification or execution permission. |
| OB-07 | Envio sample and corroborating receipt disagree, historical decimals are unavailable, or provider delivery/finality is unknown. Preserve exact qualification findings and restrict affected claims; sampled agreement cannot establish complete history or historical delivery. |
| OB-08 | Schedule and partitions cannot meet the declared sample requirements before outcome inspection. Stop qualifying evaluation with an explained feasibility result; descriptive investigation must be declared separately. Never inherit Probe A's numerical floor. |
| OB-09 | An effect passes its declared criteria but fills/costs/capacity remain unknown. Permit support only for that effect claim; capture and applicable paper claims remain unresolved. Check live operational eligibility and permissions independently under the accepted live contract; statistical support is no prerequisite. An illustrative cost haircut cannot become achieved net-return evidence. |
| OB-10 | A compiled or research-supported revision lacks forward delivery/accounting evidence, execution proof or active mandate. Each missing gate remains closed independently. Research/UI task readiness does not require all execution gates, but still requires its own approvals. A controlled execution fixture grants no research support. |

### Effect outcome and control acceptance fixtures

Builder accepted the following requirements on 2026-10-03. Status: `AUTHORED REQUIREMENTS; UNRUN`. The [design's outcome/comparison definitions](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-effect-outcomes-and-comparisons) are authoritative. No evaluation, collection, prototype or change to Probe A is authorized. Freeze and qualify the exact method profile below before formal support-seeking evaluation. Descriptive reporting remains a useful completion when inference is unjustified.

| ID | Authored input and required result |
|---|---|
| OC-01 | Change worker polling frequency while holding the declared decision schedule and five-minute features fixed. Opportunities remain bound to the declared schedule; neither workers nor bucket count silently change frequency/alignment. A late input remains an ineligible opportunity, not a shifted decision. |
| OC-02 | At declared `d`, trades occur inside and exactly at the end of the start/end one-minute windows. Select the first qualified chain-ordered trade inside each half-open window. Exclude the boundary trade belonging outside it. Preserve identities/timestamps and actual elapsed time separately from the 30-minute target. |
| OC-03 | One reference window is empty or unqualified. Keep the missing outcome, scheduled opportunity and exact reason. Do not widen, carry, substitute zero or describe another trade as its fill. |
| OC-04 | TRUE, FALSE, UNKNOWN and determinate FALSE with missing essential evidence occur in the same schedule. Only qualified TRUE/FALSE enter the respective comparison groups. Apply identical outcome rules; retain every excluded opportunity and coverage by group/time. |
| OC-05 | An original price-and-volume rule is FALSE both when price condition fails and when price passes but volume fails. General control retains its qualified FALSE population. The incremental volume comparison separately holds the same price condition TRUE and contrasts qualified volume TRUE/FALSE. Never substitute the general control for the incremental claim. |
| OC-06 | Triggered observations rise during a broad market rise. Preserve the attractive observed response, the control results and the contrast; a positive raw response alone cannot establish the declared comparative support. Apply the accepted claim-specific statistical policy; exact method qualification remains unrun. |
| OC-07 | Response intervals overlap and several observations share the same trades/time period. Preserve actual intervals and repeated dependencies for the accepted dependence-aware validation policy and its required method profile. Raw opportunity count cannot be relabeled as independent sample size. |

### STAT-Q01 method profile and qualification

Status: `REQUIREMENTS ACCEPTED; EXACT PROFILE PENDING; CHECKS UNRUN`. Builder decision, 2026-10-03. The [design's statistical-support policy](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-statistical-support-policy) owns behavior. This section specifies the required profile and qualification evidence, not an executed experiment or chosen library. Builder owns the work. No inference, collection, implementation or prototype run is authorized.

Before formal support claims, freeze one exact profile containing:

| Profile field | Required definition |
|---|---|
| Claim/statistic | Exact primary mean contrast, direction, minimum relevant difference, null/alternative, group qualification and any separate incremental comparison; dataset/configuration identities. |
| Method | Algorithm/version, uncertainty interval and p-value construction, mathematical assumptions, numeric/random-generator conventions, seed/replay rules and computational budget. A name such as bootstrap is insufficient. |
| Dependence | Scheduled-time resampling unit, joint treatment of all opportunity records/comparisons, outcome overlap and longer dependence. Resampling groups independently cannot discard shared time structure. |
| Block policy | Exact block-length selection rule, its permitted input period, elapsed-time mapping, sensitivity lengths and predeclared acceptance/failure criteria. Outcome horizon alone is not proof of a sufficient block length. |
| Feasibility | Minimum usable group and time-block coverage justified for that profile, sparse-resample handling, short-history behavior, missingness/selection assumptions and unsupported/nonstationary conditions. Do not inherit universal counts from Probe A. |
| Selection/confirmation | Frozen comparison family including failed results, Holm nominal 5% procedure, missing/invalid-test policy, finalist ranking/ties, chronological exclusions, one protected holdout test and criterion. Pointwise intervals keep their scope. |
| Qualification criteria | Predeclared dependent/no-effect generators, effect cases, repetitions, error/coverage tolerance with simulation uncertainty, stability checks and independent reference comparisons. Simulation results qualify a method under tested conditions, not every market regime. |

Use all scheduled records, including missing opportunities. Preserve the target population and any observed-outcome restriction. If the adopted method cannot defend its assumptions or meet its own feasibility/stability requirements, report descriptive findings and UNRESOLVED statistical support. Never manufacture p-values or increase resampling repetitions as a substitute for market history. This outcome completes the research job and does not create a live-trading prerequisite.

#### Selected STAT-Q01 candidate for qualification

Status: `CANDIDATE SELECTED; NOT QUALIFIED; OPTIONAL FOR CORE BUILD`. Builder decision, 2026-10-03, Q18 A: select this candidate for qualification, not as an already-qualified method or mandatory core-build dependency. Formal statistical support is unavailable until its checks pass; descriptive research and operationally eligible, user-approved live trading remain possible. Candidate: joint circular stationary bootstrap with centered mean-based inference. Resample contiguous geometric-length blocks of the complete scheduled sequence, jointly across all frozen comparisons; wrap within one partition only. Recompute conditional means and their denominators in each draw. Assume a sufficiently stationary, weakly dependent process and defend the observed-outcome/missingness population; selective missingness is not repaired by resampling.

For each signed contrast and adopted minimum difference, construct centered bootstrap errors and a directional test of whether the contrast exceeds that minimum; use a basic bootstrap interval from the same distribution. These are approximate, not exact finite-sample probabilities. Select the expected block length using the Politis–White plug-in rule with the Patton–Politis–White 2009 correction on the contrast influence series, then use the largest length across the frozen family subject to a schedule-derived overlap floor. Proposed sensitivity: half/double that length with the overlap floor preserved. If an applicable sensitivity is unevaluable or changes the support decision, retain all results and leave support UNRESOLVED.

Before qualification, freeze the influence formula, selector/version, overlap conversion, wrap assumptions, sparse/degenerate-resample rules, comparison-failure handling, minimum coverage, resample/seed/quantile conventions and tolerances. These choices and ST qualification remain unresolved; this candidate cannot grant formal support. Sources supporting method context: [Politis–Romano stationary bootstrap](https://www.tandfonline.com/doi/abs/10.1080/01621459.1994.10476870), [Patton–Politis–White correction](https://public.econ.duke.edu/~ap172/Patton_Politis_White_2009.pdf), [Holm method documentation](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html). The proposed application/sensitivity/fallback policies are Edge OS recommendations, not proved course or market behavior.

| ID | Focused qualification requirement, not executed evidence |
|---|---|
| ST-01 | Verify the primary mean contrast against independent authored calculations. A favorable median after primary failure remains a diagnostic, not a substitute support result. |
| ST-02 | Generate repeated dependent no-effect histories with overlapping outcome intervals. Assess false-support behavior and interval coverage under predeclared tolerances, including simulation uncertainty. Compare a deliberately independence-assuming method so the qualification can detect incorrect statistical behavior. |
| ST-03 | Use declared nonzero-effect examples and sparse groups, short history, missingness and unstable/nonstationary conditions. Check justified detection behavior and required descriptive/UNRESOLVED fallbacks. Seed replay alone does not pass. |
| ST-04 | Vary the frozen block sensitivities on dependent records; preserve groups, shared time structure, missingness and joint comparisons. Verify the profile's stability/failure rule without selecting the most favorable block after results. |
| ST-05 | Correct a complete family containing positive, negative and failed valid comparisons against an independent Holm reference. Preserve family size; ordinary intervals remain pointwise. Missing/invalid p-values follow the frozen failure policy, not silent omission. |
| ST-06 | Test the complete multi-variant selection procedure on repeated no-effect examples, not only individual tests. Include changed horizons/comparators where they belong in the declared family. |
| ST-07 | Outcome windows reach a protected split and display filtering removes missing rows. Timestamp-based exclusions remain identical; no protected label enters earlier selection. Earlier qualified feature warm-up remains allowed. |
| ST-08 | The selected finalist fails or lacks sufficient holdout evidence. Do not test a runner-up under the same holdout. New labels/revisions cannot restore unseen evidence. |
| ST-09 | Formal inference is unjustified. Produce the complete descriptive report with controls, diagnostics, every variant and limitations; statistical support stays UNRESOLVED. No forced backtest, paper stage or incomplete research job follows. |
| ST-10 | An executable strategy has absent or unfavorable support but qualified live inputs, accounting, route/authority and active user-approved permissions. Evaluate operational admission independently for optional trial or direct ongoing operation; preserve the evidence status. Missing an operational requirement still denies that action. Neither consent nor live success clears failed research. |

STAT-Q01 remains a focused qualification dependency for formal statistical claims, not a new broad market investigation, automatic promotion or requirement for all research/UI work. Preserve closed Probe A findings and its unopened holdout.

### Live-wallet accounting acceptance checks

Status: `REQUIREMENTS; NOT EXECUTED`. Accepted behavior is authoritative in the [activation, positions and agent-wallet accounting specification](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-activation-positions-and-agent-wallet-accounting). The builder's 2026-10-05 [separate-wallet amendment](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding) supersedes cross-agent shared-wallet assumptions. Q28–Q30's durable renewal, attempts/spending and weighted cost remain; Q31's inventory-based permission still needs qualification within each wallet. These checks do not reopen Probe A or authorize additional funded Probe B actions. Freeze exact numeric profiles/schemas and qualify enforcement before applicable live admission. Authored prototype checks do not pass these runtime requirements.

| Check | Required scenario and assertion |
|---|---|
| WAL-Q01, explicit activation | Show consequential allocation, limits, permitted actions and expiry. Activation requires their adoption. A large available wallet balance does not become an adopted allocation. |
| WAL-Q02, multiple positions | Maintain several supported strategy/market positions with distinct identities and position limits. Enforce aggregate wallet limits without imposing one open position. |
| WAL-Q03, isolated funds and reservations | A and B have distinct wallets; B's funds cannot back A's allocation, swap or gas. Competing positions within A's wallet cannot double-reserve funds/inventory. Preserve both boundaries through recovery and identical-token holdings. |
| WAL-Q04, durable recovery | Interrupt with open positions, consumed allowances and a pending action. Restore the same records and remaining exposure. Lost acknowledgement cannot release funds or permit a duplicate action. |
| WAL-Q05, accounting separation | Return proceeds, restart and continue after a trial. Distinguish capital, proceeds, cumulative allowances, attempts and actual gas. None of those transitions replenishes consumed allowances. |
| WAL-Q06, asset units | Use different tokens and decimals. Buy input consumes quote allowance; sell input consumes base allowance. Preserve asset-specific amounts and separate native gas. Enforce per-asset limits and qualified common-unit exposure valuation; reject summing unlike raw token amounts. |
| WAL-Q07, temporary recovery | Restore provider health. Resume only after current freshness, reconciliation, accounting and authority pass. Repeat with a retained user/trial/loss stop or expired/revoked authority; recovery cannot clear it or create permission. |
| WAL-Q08, external changes | Change wallet holdings or transaction state outside a deployment. Reconcile external capital flows separately from trading results and all affected reservations before admission; an unexplained discrepancy blocks that action. |
| EXIT-CAP-Q01, permission-model capacity | A favorable fill acquires more inventory than its quote estimate. Under the selected permission model, all attributable acquired inventory must have sufficient preapproved exit authority/capacity. A fixed quantity ceiling requires a qualified acquisition upper bound; an inventory-derived rule requires qualified attribution and enforcement. Both retain operational limits and deny unsupported or uncovered entries/additions. |
| WAL-Q09, reservations and additions | Two adopted additions compete for remaining position/wallet and sell capacity. Admit only those covered atomically. Update size, cost accounting, aggregate limits and exit reservations from reconciled receipts; a repeated signal without adopted addition permission is denied. |
| WAL-Q10, exits and discrepancies | Exercise partial exits and any supported multi-swap exit, fees, failed attempts and acquired-inventory discrepancies. Preserve unsold inventory and approved capacity. Release only demonstrated unused reservations; a breach never expands authority. |
| WAL-Q11, stop scope | Stop one position, one agent/deployment before its first trade, and that agent's wallet. A-only stops leave B unchanged. An explicitly reviewed all-agent stop identifies each affected wallet. Deny scoped entries/additions, permit only existing approved exits where applicable, and distinguish immediate close. Halt-all/expired/revoked authority denies exits; continue monitoring pending actions and residual exposure. |
| WAL-Q12, queue priority | Queue an eligible exit and entry for positions in the same agent wallet. The exit gets priority before submission. An unknown A-wallet outcome does not by itself block B's wallet. A stale, expired, newly stopped or changed-policy payload fails revalidation. No queued action can bypass current checks. |
| WAL-Q13, unknown outcome | Lose acknowledgement while an exit waits. Preserve original references/reservations and show the exit's delay. Reconcile without duplicate action; priority cannot bypass the unresolved transaction. |
| WAL-Q14, measured delay | Measure submission/reconciliation delay under representative contention, confirmation and recovery cases against the adopted strategy's timing requirements. Record an unsuitable verdict when delays defeat the supported path. Concurrent submission requires its own nonce/accounting/recovery qualification. |
| WAL-Q15, renewal | Preserve cumulative consumption, reservations, pending actions, positions and losses. Show additional authority explicitly. Extending expiry changes no allowance. Raising a ceiling from 100 to 150 with 80 consumed and 10 reserved leaves 60 available; incompatible reductions cannot erase obligations. Verify changed policy binding before admission. |
| WAL-Q16, attempts versus spend | A confirmed swap, revert, proved pre-broadcast denial and unknown outcome have distinct attempt/request/spend effects. Reverts consume an attempt and actual gas; trading inputs consume only reconciled actual spend. Unknown outcomes retain reservations. Provider counters cannot replace these ledgers. |
| WAL-Q17, original resend | Qualify byte-identical signed transaction and hash preservation across a bounded resend/restart. Retain every provider request without double-counting the original economic action. Changed bytes/hash or a replacement requires separately defined authority and cannot pass as a resend. A transport without retrievable original signed bytes/hash leaves this claim unqualified. |
| WAL-Q18, weighted cost and flows | Add at different prices, partially exit, add again and fully exit. Preserve every underlying record and weighted average basis; separate realized results, estimated unrealized marks, external flows and gas. Test fee inclusion exactly once, different decimals, missing marks/basis and continued losses after renewal. |
| WAL-Q19, wallet-specific authority | Attempt to prepare and sign a B-wallet action under A's execution identity, including altered wallet/position IDs, same-token holdings and restart. Deterministic ownership checks and independently scoped signing access deny it. A browser label, wallet address or one service credential with unrestricted access cannot establish this boundary. Verify each layer with separately authorized evidence. |
| WAL-Q20, creation recovery | Cancel/fail wallet creation or lose its response. Reconcile and resume the same agent/setup record and wallet identity; no duplicate wallet, automatic funding, signer access or activation follows. Research drafts need no funded wallet. |
| WAL-Q21, funding receipts | Exercise pending, confirmed, failed, duplicate and unknown deposits with exact wallet/network/asset/amount/fees. Credit only reconciled actual amounts once, keep MON separate from WMON, classify funding as a capital flow and expose unsupported/wrong-network assets without silent conversion. |
| WAL-Q22, top-up and shortage | Confirm a top-up while running, stopped, expired, revoked or allowance-exhausted. Funds change only that wallet and never reset consumption or raise allocation/permission. Temporary shortage recovery rechecks adopted recovery rules, reconciliation, freshness and authority; user/trial/loss stops remain. |
| WAL-Q23, owner withdrawal race | Review owner withdrawal with current holdings, fees and pending commitments. Race it with an agent intent; prevent conflicting new work, preserve unknown reservations and reconcile actual capital outflow before affected admission. Do not call a withdrawal a sale, stop or profit. Include external transfers and a concrete owner recovery route without promising reversal of broadcast transactions. |
| WAL-Q24, removal and owner access | Remove A's signer, preserve owner wallet/withdrawal access and pending/residual records, and deny independent new A submissions. B's permission and holdings stay unchanged. Deposits or restarting A cannot restore removed access. |
| WAL-Q25, owner-approved inter-wallet transfer | An agent request to borrow/move funds to another agent wallet is denied. A separately authorized owner transfer identifies both wallets and preserves the debit/credit as capital flows without duplicated funds or transferred spending permission. |
| WAL-Q26, two-channel ownership | Combined account views and conversation read the same agent/wallet/position/action records. A position panel cannot display B's sale as its own; exact active previews remain bound to their original target. Unscoped same-token actions require clarification. Account aggregation creates no pooled spending authority. |

WAL-Q19–26 were added on 2026-10-05 as unrun requirements. WAL-Q01–26 and EXIT-CAP-Q01 require actual qualification; browser fixtures can establish only prototype behavior.

`EXIT-CAP-Q01` and WAL-Q01–18 remain unrun. The initial inventory-based sale-permission direction is selected but its enforcement/capacity is unqualified. A fixed quantity ceiling, if additionally adopted, requires its applicable acquisition bound. Provider nonce/retry behavior and financial enforcement need their own evidence; an authored fixture supplies none. Keep interaction comprehension in the one frontend prototype. These accounting checks are focused qualification requirements, not a broad market investigation or a third prototype phase.

### EXIT-CAP-Q01 permission-model qualification

Status: `Q31 INVENTORY-BASED DIRECTION ACCEPTED; ENFORCEMENT/CAPACITY UNQUALIFIED`. Builder decision, 2026-10-03: qualify the smallest workable enforcement design for preapproved position-inventory-based sales. Attribute confirmed approved acquisitions/additions, adjust qualified exits/balance changes, exclude unrelated transfers and prevent agent-wallet/asset double claims. The 2026-10-05 amendment isolates agents in distinct wallets; position attribution remains required within each wallet. Separate application checks from independent wallet restrictions. An acquisition upper bound remains required when an additionally adopted fixed token ceiling depends on it. Required behavior remains in the [specification](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-allowance-units-and-exit-capacity).

Read-only documentation findings, 2026-10-03. Context7 resolved Privy to `/llmstxt/privy_io_llms_txt`; focused queries covered policy fields, dynamic ledger conditions, approvers and stateful controls. Kuru resolution returned unrelated packages; official public source was used instead. These establish documented/source behavior, not account access or deployed enforcement.

- Privy's [policy schema](https://docs.privy.io/controls/policies/overview) and [template variables](https://docs.privy.io/controls/policies/template-variables) describe request/calldata restrictions and wallet-address substitution. The inspected material did not establish a direct Edge OS position-ledger condition or callback. This bounded lookup does not prove such a mechanism cannot exist.
- [Stateful policies](https://docs.privy.io/controls/policies/stateful-policies) aggregate request values rather than reconciled spending or acquired inventory. They list signing methods, rolling 1–72-hour windows and post-signing updates; concurrent requests may pass before updates. The page also describes collection of matching denied requests. Qualify exact method, denial and retry behavior; these counters are not strict shared-wallet reservations or lifetime position accounting.
- [Key quorums](https://docs.privy.io/controls/key-quorum/overview) can require separate authorization signatures. [Request signatures](https://docs.privy.io/controls/authorization-keys/using-owners/sign/direct-implementation) bind the request; Privy authenticates approval, while an application approver supplies the inventory decision. An [additional alternative signer](https://docs.privy.io/recipes/wallets/conditional-signer-policies) does not itself establish mandatory joint approval. No new approver component is selected here.
- The public [Flow intent definition](https://github.com/Kuru-Labs/Kuru-contracts-flow-public/blob/main/src/entrypoint/KuruFlowEntrypointTypes.sol) exposes input/minimum output, without a maximum-output or Edge OS position identifier. Its [entrypoint](https://github.com/Kuru-Labs/Kuru-contracts-flow-public/blob/main/src/entrypoint/KuruFlowEntrypoint.sol) checks minimum output. This does not prove deployed ABI equivalence, actual route restrictions or token mechanics. Pin the source revision and actual deployment before qualification.

Remaining work, owned by the builder under separate scoped approval:

1. Carry forward the selected inventory-derived direction. Freeze eligible confirmed acquisitions/additions, actual credits/debits, qualified balance adjustments, attribution, cumulative accounting and remaining finite operational limits. Confirm that prior permission covers new attributable receipts without discretionary permission expansion. An additionally adopted fixed ceiling still requires sufficient capacity and its applicable acquisition bound. Do not reopen model selection merely because qualification is unrun.
2. Establish which restrictions the host, any mandatory approver and Privy independently enforce for the exact Flow transaction. Test attempted bypass, missing approval, altered requests, stale ledger and expired/revoked authority. If the candidate needs a new approver/contract architecture or a different trust boundary, return that material choice to the builder before implementation. Never describe application attribution checks as provider verification of inventory.
3. Test unrelated holdings/transfers, two positions in one agent wallet/asset, attempts to use another agent's wallet, approved additions, partial exits, external outflows, supported token-mechanics adjustments, competing reservations, recovery and an acquisition above its quote estimate. No inventory can be attributed/reserved/sold twice. Ambiguous adjustments deny affected actions. Prior permission and remaining capacity must cover the entire intended inventory before entry admission.
4. Qualify the actual entry and exit route, amount/recipient/fee/approval restrictions, token mechanics, supported multi-swap exits and remaining attempt/gas capacity. Preserve raw units and actual receipts. Unsupported mechanics, unenforceable required restrictions or insufficient capacity deny entry/addition; a controlled swap supplies no automatic production qualification.

Return suitable for the exact adopted model, unsupported for that model, or unresolved with the missing input/test. The inventory-derived direction is selected, not qualified. Record the exact enforcement design, layer-specific restrictions and evidence here and in its instantiated mandate. If another approver or authority architecture is required, return alternatives for builder approval before adoption. No guaranteed exit, authority expansion or financial action follows from documentation findings; do not create another competing specification.

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

### Interpretation classification and field-level evidence

Builder direction recorded on 2026-10-03 after acceptance of bounded Probe A. These rules belong in the first production intake/clarification ticket. The full design and executable schemas remain drafts; no change to the closed probe is required.

Classify the starting state by name: concrete thesis, loose intuition or bounded no-thesis request. Record the requested job separately, such as compare launches/participants, investigate an effect, construct/simulate a strategy, observe forward behavior or request live trading under explicit permissions. Record an optional trial or ongoing operating purpose separately from evidence status and permissions; it is not another starting-state category or validation rank. A clear request can still need an unsupported capability or unavailable evidence. Ask for fields needed by that job; a descriptive comparison does not need a trading threshold, position size or compiler expression.

For a no-thesis request, follow the design's [bounded-request intake](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#no-thesis-bounded-request). The agent can propose the research configuration for user adoption; the intake must not require users to design every technical setting themselves. Use the accepted [pool/route binding](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-research-market-binding-and-data-route) and [research completion boundary](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-first-research-journey), preserving the separate requirements for deployment, LP proof and optional extensions.

Each consequential interpreted field carries the following evidence. Exact machine field names and enum spellings are frozen in the build brief, not assumed to match the prototype schema.

| Record | Required meaning |
|---|---|
| Field identity and value | Name the extracted rule or setting, its value, units when relevant and current interpretation revision. An unknown value remains absent, not a guessed default. |
| Source | Point to the original request, exact relevant passage or clarification turn. Application-owned settings also identify their configuration revision and whether the user adopted them. |
| Origin | Distinguish user-stated, user-confirmed, application-configured and agent-inferred/proposed meaning. Evidence labels remain separate from these origin categories. |
| State and uncertainty | Distinguish known, missing and conflicting meaning. Record an unresolved inference and the confirmation it needs when it would change the user's trading choice or research scope. |
| Clarification history | Link the question, answer and resulting revision. Preserve earlier restrictions and show the changed fields. A conflicting answer needs resolution, not silent replacement. |

The interpreter may normalize faithfully stated meaning, such as converting 1% into 0.01. It may explain an inferred interpretation or propose a bounded search. It must not silently choose an unspecified direction, threshold, horizon, sizing rule or execution permission. Ask for decisions that matter to the requested stage, not details already stated or unnecessary deployment fields. A research-only effect investigation need not define live sizing or wallet authority.

Deterministic routing consumes the classification, field evidence, supported-capability registry and data-quality state:

- Missing required meaning returns `NEEDS_CLARIFICATION` with specific questions and no invented values.
- Clear meaning outside the supported grammar, data input or action vocabulary returns `UNSUPPORTED`, naming the missing capability and preserving the original request. A replacement needs user adoption.
- Missing essential evidence returns `UNRESOLVED`, with the claim and dependency identified. User-adopted research settings can remain stored while signal and strategy remain absent.
- A malformed representation of supported meaning reports a generation/compilation failure. It is not automatically an unsupported user idea. Any repair must preserve meaning and record its attempts.
- Supported, sufficiently specified meaning can return `COMPILED` with an explanation for review. Compilation grants no research support, paper readiness or execution authority.

Scores have separate uses. Research-priority scores may help rank several investigations later, with a visible rubric. A numeric strategy signal requires defined inputs, weights or formula, units, availability, missing-data behavior and tests before compiler support. Neither use belongs in the first intake approval gate. A general model-confidence threshold cannot replace semantic checks, evidence gates, risk checks or user authority.

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
| Interpretation binding | Exact interpretation revision and field-evidence references for adopted rules, unresolved inferences and clarification changes; retain the original request. |
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

A requested observational report may finish with sourced findings and claim-specific unknowns without being ready for quantitative review. Label it as a completed research report, not a supported edge. Capture fields and quantitative test proposals may remain absent when they are outside the requested job; explain that absence instead of inventing a strategy.

Store reproducible observations or references in durable project storage. Keep secrets out of the package. An authorized collector holds provider credentials and returns bounded data to the agent; model context, frontend fixtures and logs do not receive API keys.

Research tool access is read-only for this investigation, scoped to approved sources and budgets. External pages, PDFs, posts and API responses are data, not instructions to alter tools, permissions or project policy. Record a timeout or budget breach and stop affected work. This defines a boundary, not a commitment to a particular agent framework or separate permanent processes.

### Observational investigation and forward-learning evidence

Builder-authorized documentation amendment, 2026-10-03. Reuse the evidence package and ledger for these jobs. This defines intended behavior; creator-history tools, wallet accounting and cross-launch coverage remain unqualified extensions. The focused decision session selects any hackathon implementation scope.

For runner/creator investigations:

- Define the launch universe, period and any term such as "runner" before making a repeatability claim. Winner examples can generate hypotheses; comparisons must disclose unsuccessful launches, missing coverage and selection bias.
- Distinguish launch creator, contract deployer and shared factory. Attach evidence and uncertainty to address associations; shared funding or a shared factory alone does not prove common ownership.
- Keep creator fees, token allocations, transfers, realized trading results and unrealized marks distinct. Trading PnL needs qualified cost basis, proceeds, fees and pricing. Missing cost basis remains unknown rather than becoming profit.
- Record observable behavior such as liquidity removal, privileged contract powers or concentrated selling with its timing and source. Separate those observations from a suspected rug or claim about intent.
- Link proposed patterns and competing explanations to supporting and contrary observations. Historical prediction tests use only launch/creator/label information available at the tested time. Current knowledge of eventual winners cannot enter a past signal.
- Explain which claims can be checked descriptively, tested historically, simulated for capture or observed prospectively. Missing historical attention or agent context must not become fabricated backtest coverage.

For forward observation and user-authorized live trading, including optional trials:

- For a prospective investigation or trial, save the objective, linked hypothesis/strategy revision, expected findings, challenging observations and collection plan before observations. Ordinary ongoing operation needs evidence/limitation acknowledgement and execution consent, not an invented trial objective. Link live work to its mandate under the design's [live-trading contract](superpowers/specs/2026-09-29-edge-os-hackathon-design.md#live-trading-optional-trials-and-forward-learning).
- Retain decision-time inputs and availability, eligible/missed opportunities, intents, denials, submissions, fills, failures, positions and measured costs where applicable. Forward observation without capital is not executed-trade evidence.
- Separate observations from explanations and record uncertainty, missingness and accounting limitations. Live success neither clears previous failed tests nor proves causality or repeatable profit.
- Append learning and proposed changes under new lineage. Preserve the prior request, evidence and outcomes; a changed executable strategy requires renewed approval under the mandate contract.
- Preserve strategy and deployment/accounting lineage when a trial continues as ongoing operation. Changing purpose does not reset consumed allowances, historical losses, pending actions or open exposure. Permission changes and review of changed trial stops follow the live-trading contract; no evidence promotion follows from continuation.

Focused acceptance requirements below are authored and **UNRUN**. They add no new experiment approval and do not alter Probe A's closed evidence.

| Case | Required behavior |
|---|---|
| User asks why selected past runners moved | Return supported observations, competing explanations and selection limitations without forced compilation or a causal/profitability claim. |
| Shared factory or transfer-only history is supplied | Preserve uncertain creator attribution and missing trading cost basis; do not manufacture common ownership or PnL. |
| Creator-history pattern is tested at an earlier launch | Exclude later-known launches and labels from the decision-time features; disclose failed-launch coverage. |
| Historical result is negative and a trial or ongoing live operation is requested | Retain the negative result and check live eligibility/permissions independently. Evidence cannot become PASS through consent; a prior trial is not compulsory. |
| A live request lacks required rules or execution safeguards | Deny execution with the precise dependency; preserve the research work. |
| Forward observations suggest changing a running strategy | Save the observations and proposed new revision without overwriting history or expanding the current mandate. |
| A trial becomes ongoing trading under active permissions | Preserve evidence status, strategy identity, accounting and consumed allowances. A purpose change alone needs no new signature; review any changed trial stop. |
| Continuing exceeds or outlasts existing permission | Require approved and verified changed permissions before new actions, preserving prior accounting and exposure. |

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
| Clarification preserves meaning | A reply supplies a missing supported threshold/horizon. Create a linked revision that retains earlier direction, strict comparison and restrictions. An unknown or conflicting answer remains unresolved. |
| Clear unsupported action | An LP rebalance request reaches a spot-only implementation. Preserve the request and name the missing action; do not substitute a spot strategy. |
| Adopted settings without an edge | A no-thesis request includes user-adopted timing/sizing. Retain them as research configuration while selected signal/strategy and execution permissions remain absent. |
| Confidence versus eligibility | A high model score accompanies missing evidence or unsupported meaning. The score cannot promote the result or authorize an action. |

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
| Builder | Mechanism fields, hypotheses, interpretation/field evidence, feature units/definitions, test selection, budgets, falsification, promotion rules and fixtures; also backend collection, provenance, durable records, reconciliation, budget enforcement and secret isolation. |
| Frontend teammate | Show observations, interpretations, missing evidence, comparison, quality/coverage, budget state and rejection reasons separately. Clearly label synthetic replay. |

The tokenization teammate receives separate accepted extension tickets. Token economics and activation do not become approved through research-contract completeness.

Completion of this documentation revision means the definitions, examples, source pointers and unrun qualification plan agree across the design/workflow/handoff. It does not mean passing fixtures, approved schemas, a Nansen integration or a completed Compass gate.

Next action: the builder reviews these contracts with the design and chooses `APPROVE`, `REVISE` or `NARROW`. Preserve the Compass challenge and build-brief gates. Obtain separate approval for account-level access costs and the instantiated Nansen investigation before running it.

## 10. Source interpretation

Robot James supplies the mechanism-first research lens. QT101 to QT401 supply separate measurement, simulation, compiler and bounded-search context. Neither source class independently proves Monad-specific profitability.

The archived Robot James thread, BUILDER-ONLY REFERENCE `course-insights/robot-james/articles/raw/Thread by @therobotjames on Thread Reader App – Thread Reader App.pdf` discusses participants willing or forced to trade at unfavorable prices, competition, simple capture rules and monitoring underlying conditions. The PDF was copied unchanged on 2026-09-30 and read locally; see source manifest, BUILDER-ONLY REFERENCE `course-insights/robot-james/SOURCE_MANIFEST.md#archived-thread`.

These contracts are Edge OS design inferences, not verbatim instructions from James. Preserve source limitations and the review queue in the evidence audit, BUILDER-ONLY REFERENCE `course-insights/robot-james/synthesis/EVIDENCE_AUDIT.md`. Do not import sample thresholds or source-specific time windows as universal implementation requirements.
