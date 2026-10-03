# Edge OS scoped probe plan

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](../agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Date: 2026-10-02, Africa/Kinshasa.

Status: `DRAFT FOR BUILDER REVIEW`. Latest `1B-sol-an-recheck-09`: `PASS — BOUNDED INTERPRETATION AND COMPILER COMPATIBILITY`, all five fresh live Sol v6 cases pass. `1A-recovery-01` remains `PASS — MECHANICS ONLY`, 81 checks; compiler unchanged. Checkpoint 1 passes for the approved meaning/compilation/known-invalid subset. Historical checkpoint 2, full Probe A and Compass remain unpassed. Earlier failures and charges are preserved. Probe B: `NOT_STARTED`.

The builder authorized this documentation update and, by the subsequent part-1A task prompt, deterministic mechanics code, startup checks and local reporting only. The partial approval is recorded in section 8. Section 8 records the later scoped 1B credential/model-call approval. Other paid processing, credentials access, wallet changes and transactions remain unapproved. Approve each other instantiated experiment separately. Keep the full design draft and unpassed gates visible.

## 1. Purpose and authority

Answer two questions that can change the Edge OS build before spending the remaining window on production implementation. Each probe proves only its frozen claim.

Read the [workflow](../EDGE_OS_COMPASS_WORKFLOW.md), [design sections 7, 8, 12 and 17](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md) and [research contracts](../EDGE_OS_RESEARCH_CONTRACTS.md). For Probe A, consult the compiler verification report, BUILDER-ONLY REFERENCE `course-insights/QT301/COMPILER_VERIFICATION_REPORT.md` for the subset actually used. For Probe B, consult the Privy audit, BUILDER-ONLY REFERENCE `docs/research/PRIVY_AND_AGENT_EXECUTION_PATTERNS.md` and JEV/RPC review, BUILDER-ONLY REFERENCE `docs/research/06_JEV_TRADER_ALCHEMY_ENVIO_REVIEW.md`.

Use the Matt prototype reference, BUILDER-ONLY REFERENCE `playbooks/references/MATT_PROTOTYPING_METHOD.md` for runnable decision evidence and the Drey reference, BUILDER-ONLY REFERENCE `playbooks/references/DREY_PROTOTYPING_METHOD.md` for a test through the real dependency. Their old Funnel phase numbers and numbered output paths do not control this plan.

## 2. Proposed assignment and limits

| Assignment | Owner | Proposed initial work limit | Allowed only after scoped approval |
|---|---|---|---|
| Probe A | Builder, quant and agent systems | Four active working hours | Temporary research/compiler/evaluator program and focused tests |
| Probe B | Builder, delegated execution and recovery | Three active working hours | Temporary delegated-execution/recovery program and approved real-dependency checks |
| Result-state interaction prototype | Builder | Two active working hours | A small interaction using the approved JSON fixtures; its own scoped approval is required |

The builder owns all prototyping and product decisions. Teammates receive implementation tickets after the relevant behavior, interfaces and evidence are accepted. A frontend teammate may implement the accepted UI from the builder's fixtures or mockups; they are not assigned this prototype.

These are proposed effort budgets, not feasibility promises. Independent probes can run concurrently. At budget expiry, stop and report the answer or exact unresolved blocker. Extending scope, API costs or capital requires renewed approval. Do not create a full application to answer a probe question.

## 3. Instantiate before code

The assigned owner proposes the exact inputs below in this file. The builder approves them before code. Record public configuration and safe evidence identifiers only; never credentials, private keys, private edit links or account identifiers that need not be public.

| Probe A required configuration | Current value |
|---|---|
| Finite Kuru market/token universe and one momentum or reversal question | One Monad mainnet Kuru meme-token/MON spot market, alias `MARKET_A`; lagged-price continuation over 30 minutes. Exact market/token identity is blocker A01. Selection and exclusions are in section 4. |
| Fixed source bundle and point-in-time dataset, covered period, granularity and gaps | Local source evidence below is usable for mechanics. Proposed historical window is 2026-09-18 through 2026-10-02, exclusive end, UTC, five-minute bars. No qualified local Kuru history found; A02 blocks the historical investigation. |
| Accepted grammar, primitives, units, parameter bounds and numerical/missing-value rules | `gt`, `netret`, constants and their explicit lowering; lookbacks 1 or 3 contiguous five-minute bars, thresholds 0.01 or 0.02. Price in MON/base-token, return dimensionless; full rules below. |
| Three input examples: concrete thesis, incomplete intuition, bounded no-thesis request | Exact frozen inputs A-T, A-I and A-N below. `MARKET_A` is a visibly unresolved binding, not an invented address. |
| Candidate/variant, request, compute and cost limits | One investigation, at most two hypothesis records and four distinct research variants; eight model requests, 20 local evidence reads, 120 CPU seconds, 15 minutes run time, zero external data requests and proposed USD 0 incremental provider cost. Model access is separate and remains unqualified. Details below. |
| Research/holdout boundary or explicitly limited forward-only alternative | Seven research days, three selection/validation days, four sealed holdout days; one finalist and one final holdout opening. Availability qualification is mandatory. A different period or forward collection needs revised approval. |
| Known-invalid fixture, clean control and expected outcomes | Two labeled synthetic episodes; clean rule takes both, future-price substitution selects only the winner. Same strategy identity, visibly different fixture identities. Expected values and rejection reason below. |
| Research-agent runtime/model and permitted evidence tools | Python standard-library deterministic program plus one isolated Hermes investigator over bounded JSON packets. Hermes version, exact model, entitlement/cost verification, isolation and usage capture are blocker A03. A manual Codex exchange is not Hermes integration proof. |
| Builder's scope/cost approval and approved work limit | Original 1A: `REJECT — MECHANICS ONLY`. Separate 30-minute accounting recovery authorized in section 8; `1A-recovery-01` result `PASS — MECHANICS ONLY`. Fixed offline fixture repetitions are uncapped metrics in that recovery; capped profiles remain enforced. Remaining scope/cost approvals `PENDING`; neither complete checkpoint passed. |

| Probe B required configuration | Current value |
|---|---|
| Network, chain ID, verified deployment/market, contract functions and exact operation | `UNKNOWN; testnet preferred only if a usable path is verified` |
| Isolated test-wallet role, ownership, signer and policy administrator | `UNKNOWN; record roles and safe aliases, not secrets` |
| Approval/order value, tokens, total spend/gas, requests and provider-cost caps | `UNKNOWN; financial and provider approval required` |
| Strategy/fixture revision, intent identity, expiry and policy content | `UNKNOWN; freeze before activation` |
| One signing/submission route and current-state/reconciliation provider | `UNKNOWN; select one route, not automatic retry alternatives` |
| Provider-denial input and recovery/revocation sequence | `UNKNOWN; freeze before submission` |
| Builder's code, service-use and financial approvals and approved work limit | `PENDING; record separately` |

Unknown data can justify a narrower proposed claim. It cannot justify treating a synthetic dataset as historical Monad evidence. Mainnet is not a fallback without explicit approval. A zero-value wallet call is not proof of a Kuru order path.

For current SDK/API/library/CLI questions, resolve the Context7 library ID before querying documentation. Use official sources through Exa or the browser when Context7 has no suitable library. Record source URL, date checked and deployment/version. Recheck only the dependencies needed for the named probe. Documentation is not live execution evidence.

## 4. Probe A: research, compilation and rejection

### Frozen question

Can a bounded investigation preserve user meaning and trial history, produce an inspectable typed strategy or useful unresolved result, and reject a known-invalid attractive result without inventing assumptions?

Failure would weaken the distinctive research promise even if wallet execution works.

### Form, scope and builder decision

The throwaway terminal program is at workspace path `prototypes/edge-os/probe-a/probe_a.py`. Only deterministic 1A is implemented. Its executed command was `python3 prototypes/edge-os/probe-a/probe_a.py checkpoint-1 --run 1A-resume-02`; it does not execute part 1B. Evidence and the aggregate-budget failure are recorded below. Checkpoint 2's command remains a proposal and is not implemented or approved.

The program prints each input, interpreted meaning, missing fields, typed/expanded rule, availability checks, ledger changes and decision reason. JSON artifacts retain the same state. A terminal is sufficient because this question concerns research and semantics, not an interaction design. Use one deterministic program and one runnable self-check, plus the existing Hermes runtime. Do not build an application, database, generated Python, custom agent framework or frontend.

Discussion cannot establish whether an investigator preserves contrary evidence or whether the compiler/evaluator admits leaked information. The two checkpoints test those behaviors. Failure requires narrowing the research promise or changing the interpretation/evaluation boundary. The builder must decide whether to approve this exact scope, approve only checkpoint 1 with a mechanics-only claim, revise it, or reject it. Checkpoint 1 alone cannot pass Probe A's research claim.

### Market, data and timing declaration

Use one market, `MARKET_A`, on Monad mainnet 143 for historical observations only. Require a Kuru meme-token/MON spot pair that existed by 2026-09-18T00:00:00Z. Before viewing returns, the builder must bind its market address, base-token address/decimals, quote-token identity/decimals and a source-backed meme classification. If several locally documented eligible markets exist, select the lowest market-address byte value. Record every excluded market and reason. This is a deliberately restricted universe, not evidence about all meme tokens or dead/delisted tokens.

Blocker A01: no qualifying market metadata bundle was found in the inspected local sources. The JEV reference names MON-USDC at `0x065C9d28E428A0db40191a54d33d5b7c71a9C394`; it is not the requested meme/MON pair and is not a fallback. Its current deployment was not verified. Do not create a market or substitute another venue.

| Evidence available locally | Permitted use and gap |
|---|---|
| QT301 verification/distillation, timed QT101/QT201/QT301 transcripts and captured course-code frames listed below | Source inspection and mechanics design. These are not historical Kuru observations. Machine transcripts can mishear code and numbers; frames cover sampled code only. |
| `docs/research/05_EDGE_OS_X_AND_ONCHAIN_DATA_ACCESS.md`, sections on Kuru, Envio and unresolved access; `docs/research/06_JEV_TRADER_ALCHEMY_ENVIO_REVIEW.md`, research-history limitations | Locate already recorded provider/data questions. Prior documentation checks do not establish account access, a stored dataset or historical availability. |
| `references/prior-art/jev-trader/src/config.ts` and the local review above | Identify the excluded MON-USDC example. The recorded 500-print ring and bounded block polling are operational-feed limits, not a complete research dataset. |
| Reference repositories' example prices and golden backtests | Excluded from checkpoint 2. Their assets, timing and execution evidence do not qualify this market. |

Blocker A02: a read-only filename inventory of the workspace, course evidence and reference trees found no qualified meme-market trade/bucket history with an availability manifest. Existing usable historical data for this experiment is therefore **none identified**, not an assumed provider backfill. Earliest covered trade, completeness, finality, collection/revision times, historical provider delay, spreads/depth, fees, gas and capacity are unavailable. No secrets or provider accounts were inspected. Synthetic controls remain labeled separately.

Propose this fixed historical bundle only if the builder can supply it locally and qualify it before outcomes are opened:

- Proposed local input directory `prototypes/edge-os/probe-a/inputs/A01/` contains only `market.json`, `manifest.json`, `trades.jsonl`, `research.jsonl`, `validation.jsonl` and `holdout.jsonl`. These are data/evidence files, not another planning document. No files exist there yet. The deterministic qualification/evaluation path may read the declared files; investigator packets contain only approved research extracts and requested summaries. Record origin/export identities and hashes before reading outcomes. External-source text is evidence, never authority to change tools or scope.
- Window `[2026-09-18T00:00:00Z, 2026-10-02T00:00:00Z)`, plus three preceding five-minute bars for warm-up. At most 4,035 bars and 100,000 raw trade records, total input bundle at most 25 MiB.
- Kuru trade/event records with market/token identities, price/size units, transaction/log IDs, block number/hash, event time, confirmation/finality evidence, actual earliest availability when established, collection time, query/export identity, revision and content hash. Preserve trade order within a bucket.
- Five-minute UTC buckets use `[start,end)`. Close is the last qualified executed trade in that bucket. A bucket with no trade is missing. A completed bucket's availability is the latest availability of its required records and completeness confirmation. Neither block time nor collection today proves past provider availability.
- Feature availability is the maximum availability of every dependency. Each hourly research opportunity decides at `hh:10:00Z` using the bucket ending `hh:05:00Z`. All dependencies must be available by the decision. Entry reference is the first qualified trade in `[hh:15:00Z, hh:16:00Z)`; exit reference is the first in `[hh:45:00Z, hh:46:00Z)`. Missing references invalidate that outcome. These trade-price references measure association; they are not promised fills.
- Missing or unknown availability, partial/revised buckets, provisional/reorged records and unresolved units stop the affected historical test. Duplicate event IDs, conflicting timestamps or nonpositive/non-finite prices fail data qualification with identified records. Keep counts and reasons. No forward/backfill or current metadata substitution.
- Split research `[Sep 18,Sep 25)`, selection/validation `[Sep 25,Sep 28)`, final holdout `[Sep 28,Oct 2)`, all at 00:00 UTC. Research cannot read the other periods. Selection may read validation once per declared variant. Open final holdout once for at most one frozen finalist, after recording its identity and rationale. Exclude outcomes crossing split ends; lag warm-up may use earlier qualified bars. Log every access, including accidental access. A known-to-builder historical holdout is not asserted to be pristine.

If the bundle or historical availability cannot be qualified, checkpoint 2 is `UNRESOLVED`. Forward collection is a possible separately approved experiment, not this run's silent fallback. No historical agent replay is claimed. This is an investigator working now on a frozen, bounded bundle with a withheld evaluation period.

### Separate market/data qualification preflight

Do not make historical access a prerequisite for the deterministic mechanics subset. Qualify it independently before checkpoint 2. The current documentation check is read-only. It does not approve data acquisition.

After approval of acquisition, limit the qualification pass to 45 active minutes, one market, one provider route, at most ten read-only requests, 25 MiB total response data and USD 0 incremental cost. Record the exact endpoint, request filters, entitlement and rate limits before the first request. If access or coverage remains unknown at the limit, stop with the specific blocker. No account activation, secret inspection or history download is authorized by this proposal.

1. Inspect metadata and coverage only, without comparing returns. Bind market/token/quote identities, decimals, deployment/start dates and the meme classification. Apply the selection rule above before opening outcomes.
2. Check whether executed-trade records, log identities, complete buckets and the full declared period can be obtained within the bounds. A documented backfill capability is not a qualified dataset. Do not substitute generic token candles for Kuru trade events.
3. Classify timing evidence. Recorded historical availability can support the proposed as-of test. Block timestamps alone cannot. If only finalized onchain history exists, propose a separate reconstructed-data experiment with an explicit assumed release delay and sensitivity cases. Label it reconstruction, not observed historical provider availability. It needs builder approval and a new configuration identity before evaluation.
4. Return a hashed source/coverage manifest and one verdict: qualified for the frozen historical claim, usable only for a revised narrower claim, or unavailable. Keep provider coverage, tradability and mechanism evidence separate.

The 2026-10-02 official-documentation check found a Kuru market-registration/fill-event backfill route, but qualified no market or dataset. The public recent-trades endpoint documents at most 1,000 records without historical pagination. The historical S3 route describes L2 book snapshots, not an executed-fill ledger. Current Envio documentation requires an API token. Do not infer account access, free entitlement or complete history from these capabilities. Exact sources and check dates are in the private dependency note named under A03.

No additional market, venue, search family or broad data pipeline belongs in this preflight. Its budget is separate from experiment A01 and cannot enlarge the investigator's access.

### Exact inputs and frozen decisions

Resolve `MARKET_A` to the approved identity in every input before a historical run. In checkpoint 1 it binds only to `SYNTHETIC_FIXTURE/MARKET_A`. Preserve raw text and binding separately.

**A-T, concrete statistical thesis:**

> For MARKET_A only, I think a net price rise greater than 1% over the last completed five-minute bar predicts a positive price response over the next 30 minutes. Test that association on the declared window. At each hourly hh:10 decision, use the close ending hh:05 only if it was available then. In research simulation, enter at the declared hh:15 trade reference and exit at hh:45. Use 10 MON quote notional from a 100 MON paper balance, one position, no borrowing or compounding. Apply the plan's illustrative cost cases. Participants, their incentives and persistence against competition are unknown. Do not add wallet or social features, price stops or a causal story. Do not trade.

**A-I, loose intuition:**

> MARKET_A seems to keep running after a strong move. I do not know what counts as strong or how long the effect lasts. Help me make the observation testable. Do not choose a threshold, horizon, entry, exit or size for me, and do not trade.

**A-N, bounded no-thesis request:**

> I have no thesis. Investigate price continuation in MARKET_A only, on the plan's research period. The search space is netret lookbacks of 1 or 3 contiguous five-minute bars, thresholds greater than 0.01 or 0.02, and a fixed 30-minute response. Use the declared hourly decision and trade-reference times, sizing and cost cases. You may propose zero, one or two hypotheses and attempt at most four variants, within budget A01. Keep evidence against continuation, uncertainty about the mechanism and every attempt. Compare with the no-entry opportunities. Lock any finalist before the final holdout. Return a typed research rule only when its meaning and data are supported, otherwise a useful unresolved or rejected result. Do not add features or claim profitability, paper readiness or trading permission.

| Case | Expected observable decision |
|---|---|
| A-T | Interpretation retains strict `> 0.01`, lookback 1, 30 minutes and every timing/sizing restriction. `COMPILED` on qualified fixture mechanics; historical evidence remains `UNRESOLVED` while A01/A02 are open. Mechanism fields remain `UNKNOWN`. |
| A-I | `NEEDS_CLARIFICATION`; name strong-move definition, direction confirmation, horizon, timing, exit and sizing. A draft may be saved. No parameterized strategy, performance result or default RSI/threshold. |
| A-N | Accept the bounded investigation request; list its finite space and budget. No fixed winner or completed strategy at intake. Generate proposals only after cited research evidence. With current data blockers, return `UNRESOLVED` with affected fields and next evidence requirement. Zero supported hypotheses is legitimate. |
| Unsupported extension, exact text: "Use MARKET_A wallet labels and organic X attention to choose an LP rebalance." | `UNSUPPORTED`, identifying feature and domain/action exclusions. Preserve the request; substitute neither price momentum nor a spot order. |

A-N is the single checkpoint-2 investigation. A-T/A-I are interpretation cases and do not create extra searches. A-T's control formula is not a researcher-discovered hypothesis. If A-N independently proposes that formula, log its prior presence and the evidence for choosing it; never present the control as discovered research.

### Grammar and strategy meaning

These are proposed Edge OS policies, not claims that the course implements a rejecting compiler.

| Item | Frozen proposal |
|---|---|
| Lexical grammar | Case-sensitive ASCII identifiers, `_` parameters, decimal point, commas and balanced parentheses. Ignore ASCII whitespace between tokens; consume the entire input. No exponent notation, signs, aliases, attributes, arbitrary identifiers, scripts or implicit arguments. |
| Research family | `gt(netret_N(),const_Q)` for `N` in `{1,3}` and `Q` in `{0.01,0.02}`. Four possible variants. An explicit expanded equivalent may enter through the same validator. Other otherwise well-typed strategy forms are `UNSUPPORTED`. |
| Used functions | `netret_N`, zero children, returns dimensionless numeric series; `gt`, exactly two same-unit numeric operands, Boolean-series output. Internal lowering uses `close`, `delay_N` with one price-series child, `div` with two same-unit price operands, and `minus` with two dimensionless operands. `const_Q` has zero children and dimensionless scalar type. Scalars broadcast only against this market's series. |
| Expansion and units | `netret_N()` lowers to `minus(div(close,delay_N(close)),const_1)`. Prices are MON per base-token, quote notional is MON, base size is base-token units, times are UTC, horizon is minutes, lookbacks count contiguous five-minute bars. A Boolean signal is not a weight or order. No implicit percent/basis-point conversion. |
| Accepted bounds | Lag is integer 1 or 3. Constants are only `0`, `1`, `0.01`, `0.02`; 0 and 1 support lowered mechanics, not extra thresholds. Hold 30 minutes, entry quote notional at most 10 MON, paper balance 100 MON, one open position, leverage at most 1, no compounding. Price changes do not resize that position. Each variant has separate research accounting. Stop new simulated entries if its available paper balance cannot cover entry notional plus the selected cost case; retain the denied opportunities. No financial authority is created by these simulated limits. |
| Warm-up and gaps | Return N requires N+1 consecutive qualified buckets including the current close. Any missing intervening bucket invalidates the feature, even when both endpoint prices exist. Missing comparisons remain unknown, not false or zero. Begin again only after the full consecutive history exists. This calendar policy differs from the course's retained-observation rolling. |
| Numerical behavior | Use standard-library decimal arithmetic at precision 50 with half-even rounding. Decode prices from positive fixed-decimal strings, at most 20 significant digits and 48 characters, retaining original units. Reject exponent notation and non-finite values. Divide by zero or invalid arithmetic produces null plus a reason, never valid zero. No display rounding before strict comparison. Compare reference numeric outputs with absolute/relative tolerance 1e-12; labels, validity masks, types and identities must match exactly. On prices `[100,101]`, return 0.01 must fail the strict 0.01 threshold. This avoids a binary floating-point threshold artifact and is an Edge OS policy, not course numerical parity. |
| Strategy actions | At the declared hourly opportunity, a valid true signal opens the fixed research position only when flat; false stays flat. Exit at the fixed reference time. Missing data prevents new entries. A missing exit leaves outcome/exposure unknown rather than fabricating a liquidation. No stop-loss, wallet, order type or executable Kuru calldata is invented. Mode is `research`; execution permissions are empty. |
| Execution assumptions | Historical output is a trade-price association, not a fill simulator. Fixture cost cases are 0, 50 and 100 bps per side. For c in `{0,0.005,0.01}`, return after the illustrative haircut is `Pexit/Pentry - 1 - c*(1 + Pexit/Pentry)`. Historical spread, depth, fees, impact, gas, latency and capacity remain unknown unless sourced. Ten MON sizing is illustrative and may violate actual venue minimums. No net-tradability claim or readiness promotion follows. |
| Canonical identity | Canonical UTF-8 JSON, sorted object keys, compact separators, ASCII escapes, no trailing newline, ordered child arrays. Lookbacks are integers; parameter/notional values use the fixed decimal strings above. Reject duplicate keys and non-finite JSON numbers; unknown values use null with reason. SHA-256 covers the strategy plus used component/compiler/serializer/numerical/timing-policy IDs, proposed version `probe-a-v1`. Evaluation binds separate dataset and evaluation-config hashes. Revalidate loaded JSON through the fresh-input boundary. Course repr is only provenance/display evidence. |
| Resource boundary | Raw user text at most 4,096 UTF-8 bytes; formula at most 512 ASCII bytes; supplied strategy JSON at most 32 KiB. At most 16 expanded nodes and depth 6 with root depth 0. Whitelisted lowering only, no recursive user macros. Validate syntax, arity, units, types, bounds and family before dataset access. Instrument data-read count to prove invalid input made zero reads. |

Exclude `ite`, cross-sectional selectors, mean/std, OBV, sum/product, slow multi-input rolling, alternative-data terminals and genetic search. Their course implementations and corrections exist; they are unnecessary for this question and do not inherit this plan's semantics.

### Clean control and attractive invalid fixture

Use `SYNTHETIC_FIXTURE`, dated 2026-09-18 UTC, with fictional prices in MON/base-token. These values are not historical market evidence. Both episodes use the same canonical rule `gt(netret_1(),const_0.01)` and the fixed research actions above.

| Episode | Previous/current completed close | Current close available | Decision / entry reference / exit reference | Entry / exit reference prices |
|---|---|---|---|---|
| F1 | 100 at 09:00, 102 at 09:05 | 09:05:03 | 09:10 / 09:15 / 09:45 | 100 / 110 |
| F2 | 100 at 10:00, 102 at 10:05 | 10:05:03 | 10:10 / 10:15 / 10:45 | 100 / 90 |

Declare the preceding buckets complete and available by their closes plus three seconds. All fixture reference trades occur at the table's exact times, with availability three seconds later. The simulator may consume those later records as outcomes, never as earlier features.

Clean C0 takes both episodes. Expect gross returns +10% and -10%, mean 0; at 50 bps per side, +8.95% and -10.95%, mean -1%; at 100 bps, +7.9% and -11.9%, mean -2%. Compute fixed base units as 10/entry price. No eligibility or profitability is awarded. With only two episodes, every statistical conclusion is insufficient.

Invalid L1 is `DELIBERATELY_MODIFIED_SYNTHETIC_FIXTURE`. Replace the current feature closes with the future exit prices, 110 and 90, while retaining their true source/availability times 09:45:03 and 10:45:03. A quarantined naive comparison that ignores availability selects F1 only, giving 100% win rate and +8.95% after the 50-bps case. Its output must be labeled invalid and grant no state transition. The normal path must reject both feature uses before historical evaluation as `FUTURE_INFORMATION`, showing decision time, true availability, dependency ID and affected variant. Do not hide the origin by relabeling the timestamps.

The leakage fixture tests leakage rejection. It does not test general overfitting detection, prove a profitable strategy or discover an edge. If the naive result is not attractive as frozen, the fixture check fails; do not tune the values after the run.

### Budget and runtime

Budget ID `A01`, proposed version `probe-a-v2-hermes`, applies across both checkpoints and all failures, retries, controls and summaries. This revision does not inherit a result or approval from the earlier manual-packet proposal.

- Four active builder hours total. Reserve 90 minutes for checkpoint 1, 90 for checkpoint 2, 60 for evidence/review. Stop at four hours even if incomplete. The running program has a separate 15-minute wall deadline and 120 CPU-second aggregate ceiling; at most one CPU, 512 MiB working memory and 100 MiB output. If an enforceable resource limit is unavailable, record a blocker before running.
- One A-N investigation; at most two proposed hypothesis records and four distinct parameter variants, including duplicate proposals of A-T's formula. No widening, mutation or automatic retry search. Record duplicates, abandoned/rejected proposals and revised packages even when no evaluation occurs. No new strategy after holdout access. At most one finalist, with deterministic tie order N then Q, both ascending.
- At most eight model requests, including Hermes's internal turns, retries and summarization: four input interpretations, up to two investigator rounds, one report request and one repair. At most 48,000 input and 8,000 output tokens in aggregate. A missing/refused/timed-out response consumes its request budget. Each request has a 90-second deadline; no automatic retry. Capture safe model/prompt identities, exact request/response packets, elapsed time and usage. A token/cost meter gap stops requests rather than inventing usage. A Hermes turn limit is not a substitute for these aggregate limits.
- At most 20 allowlisted local evidence reads and 25 MiB of input. The section-8 recovery amendment removes only the count ceiling for repeated fixed synthetic fixtures in offline 1A; counts and bytes remain recorded. One read is one recorded file/section request; repeated reads count again. All cohort summaries and outcome computations count in the trial record. At most four research evaluations, four validation evaluations and one holdout evaluation. The three fixed cost cases share each variant evaluation and do not create extra selected variants. No permutations or p-value calculations are proposed.
- Zero network/provider data requests during A01, zero paid calls, proposed USD 0 incremental provider cost, zero signing/trading requests. Only the approved model endpoint may be reachable by the runtime transport. Hermes entitlement is not inferred from Codex subscriptions or banked resets. External data collection or a paid model requires a separately approved budget; it cannot consume an unspecified allowance.

Use Python's existing standard library for deterministic validation and evaluation. Use one real Hermes investigator for interpretation and the bounded A-N investigation. Freeze its release/commit, model/provider and effective configuration before execution. Exchange JSON packets between Hermes and the deterministic program. Manual packet transfer is acceptable for this throwaway test only when it transfers the actual Hermes output unchanged. The human must not supply hypotheses or rewrite evidence. Validate the returned structure and citations independently. Malformed output consumes a request and cannot grant a successful state.

Start from an isolated runtime context with no imported memory, user profile, private workspace context or prior trials. Give Hermes only the approved extracts, research observations and requested deterministic summaries. Disable unrelated tools, terminal/shell, browser, general filesystem access, spawning, network research and signing. Keep validation and holdout files outside its accessible context. A prompt saying "do not read" is not an isolation boundary. Verify effective tool exposure and enforce access at the process/container or tool boundary. If the chosen Hermes route cannot enforce this, mark it blocked rather than claiming isolation.

The documentation preflight favors a fresh direct SDK instance with explicit tool selection, context/memory/background review disabled and the resulting tool schema checked before inference. Do not use the inspected `-z` one-shot route as the safety boundary: fetched source enables automatic approvals and normalizes empty toolsets to defaults. Published usage documentation and fetched source also differ. The source check used moving `main` URLs without a captured commit SHA. Pin and inspect the actual selected revision before adopting syntax or behavior. A zero-tool assertion still does not establish file, credential or network isolation.

Blocker A03: exact safe model ID/version, Hermes version, effective tool isolation, request/token/cost metering, entitlement and packet capture have not been qualified for a run. Check current official documentation first through Context7 and Exa. Documentation evidence is retained in BUILDER-ONLY REFERENCE `docs/research/PROBE_A_HERMES_AND_DATA_PREFLIGHT_2026-10-02.md`. Do not install Hermes, inspect credentials or make a model call merely to complete this planning task. A paid route needs an explicit revised numeric cost approval. Hermes memory, persistent scheduling and offline strategy management remain outside Probe A.

If A03 remains open, a manual Codex investigation may be proposed as a separately labeled fallback. It cannot pass the Hermes integration claim. Do not adopt the fallback silently or delay independent deterministic checks while seeking a free Hermes route.

### Checkpoint 1: faithful interpretation, compilation and known-invalid rejection

After approval, perform these steps in order. Each step completes only when its listed evidence exists.

Checkpoint 1 has two separable parts. **1A, deterministic mechanics**, covers steps 3-5 with explicitly authored structured fixture inputs and the relevant manifest fields. It needs no market history, Hermes or model call. **1B, Hermes interpretation**, covers step 2 and its links to the same compiler. A 1A result must say `MECHANICS ONLY`; it cannot pass checkpoint 1 or the investigation claim without 1B. Approve 1A alone if runtime qualification is still blocked. Do not label authored inputs as model interpretations.

1. Freeze the approved plan/configuration hash, fixture identities, budget, runtime/model identities and expected-outcome table in the run manifest. Mark historical bindings blocked where applicable. Complete when every executable choice is fixed and secrets/network tools are absent.
2. Interpret A-T, A-I and the unsupported extension. Intake A-N only to expose its scope, with no research yet. Preserve raw text, structured fields, missing assumptions, source-linked claims and user-facing explanations. Complete when the case decisions match the frozen table without added meaning.
3. Compile A-T's fixture rule to typed/expanded `StrategySpec`; print its interpretation and semantic identity. Round-trip canonical JSON, reload and revalidate it. Complete when units, parameters, timing, sizing, action meaning and mode agree before and after reload.
4. Run the focused self-check cases below through fresh and stored-input paths. Complete when expected outputs/masks/reasons agree with an independent small reference calculation and invalid static input records zero data reads.
5. Run clean C0 and the quarantined naive L1 comparison, then send L1 through the normal availability gate. Complete when the frozen numeric comparison and exact leakage rejection are saved under separate data identities with the same strategy identity. Preserve A-T's unknown mechanism and research-only state.

| Focused check | Frozen expected outcome |
|---|---|
| Price vector `[100,102,101]`, lag 1 | Returns `[null,0.02,-1/102]`, with null reason `WARMUP`; threshold 0.01 yields `[unknown,true,false]`. No output for unqualified availability. |
| Missing bar `[100,null,102,103]`, lag 1 | `[null,null,null,103/102-1]`; the gap is not skipped. Lag 3 remains null until four consecutive buckets exist. |
| `gt(netret_1(),const_0.01)junk`; empty/doubled argument | Positioned `INVALID_SYNTAX`; zero data reads. |
| `gt(netret_1())`; `netret_0()`; `const_nan`; unknown function/terminal | `INVALID_ARITY`, `INVALID_PARAMETER`, `INVALID_PARAMETER`, `UNSUPPORTED`, respectively; zero data reads. |
| Price compared with dimensionless threshold; Boolean used as a numeric operand; lag changed to 3.5 | `INVALID_UNIT`, `INVALID_TYPE`, `INVALID_PARAMETER`; no coercion or evaluation. |
| Zero/non-finite price or arithmetic; prices `[100,101]` with threshold 0.01; oversized input/tree | Record invalid numerical data/value rather than a zero signal; exact-threshold comparison false; `RESOURCE_LIMIT` before data access for oversized syntax/tree. |
| Repeated canonical serialization; changed used-component or timing policy ID | Identical bytes/hash for repetition; different semantic hash for changed meaning. Dataset/evaluation changes create new evaluation identity without changing the strategy. No inherited readiness. |
| Modify future records only; remove availability; load invalid stored JSON | Earlier qualified features unchanged; absent availability gives `UNRESOLVED`; stored input gets the same static rejection as fresh input. |
| Omit a contrary observation/attempt from a package; exceed a declared budget | Package reconciliation fails against ledger/evidence IDs; deny the next over-budget operation, save reason and stop. No hidden repair. |

This selects/adapts QT301 proposed tests T01-T08, T10-T11, T13, T17-T19, T24-T31 and T35 for the actual subset. T09's forward-fill semantics are replaced by the declared gap check. Branch/selector, general rolling, OBV, mutation and publication/concurrency tests remain excluded; no claim that all T01-T36 passed.

### Checkpoint 2: one bounded investigation connected to those mechanics

Enter only after checkpoint 1 meets its frozen checks and A01-A03 are resolved for this historical run. If data qualification fails, save the observed blocker and stop; do not fill the missing history with C0.

1. Qualify and seal the local bundle before inspecting outcomes. Save source/units/availability/gap records and the research/validation/holdout file hashes. Complete when every required field has evidence and withheld periods are excluded from investigator packets.
2. Give A-N and the research-only bundle to the isolated Hermes investigator. Save its actual configuration, inputs, outputs, tool exposure and usage trace. Require an initial package of atomic observations, evidence IDs, at least one competing explanation and data limitations. Participants/incentives/persistence may remain unknown. Complete when observations are reproducible and inference is labeled. Do not demand a favorable story.
3. The investigator may propose zero to two hypotheses within the four declared rules. Before each calculation, append its hypothesis/parent ID, rule, rationale, evidence citations, expected direction/horizon, falsification, budget and data identity to `ResearchLedger`. Then compile through checkpoint 1's boundary. Complete when proposed, rejected, duplicated, abandoned and evaluated variants all appear, including compiler failures.
4. For each attempted variant, deterministic code reports valid/missing opportunity counts, triggered/control counts, gross response mean/median, positive fraction, and all three cost-sensitivity means. Control is the same hourly opportunities where that rule is valid and false, with identical outcome timing and cost cases. Association summaries use every qualified opportunity independently of the paper balance; separate paper-position accounting records balance/exposure denials and never counts denied entries as fills. Report daily results and the largest single-day contribution. Keep every negative result and failed check. Fewer than 30 triggered or 30 control outcomes per evaluated partition gives `INSUFFICIENT_SAMPLE`, not significance. Even 30 is only a reporting floor, not independent observations or statistical proof.
5. Return summaries to the investigator for supporting/contrary evidence, alternatives and falsification. Descriptive support requires positive triggered mean response and positive triggered-minus-control mean in research and validation. If either is nonpositive, record directional contradiction and zero supported finalist for that rule. Missing coverage/sample gives unresolved support. Among rules meeting those conditions, choose at most one finalist by largest validation triggered-minus-control gross mean, ties N then Q ascending. Freeze its identity/rationale before one holdout evaluation. Nonpositive holdout mean/difference records failed replication; no reselection. Costs, common market movement, isolated-day concentration, trade-price/fill differences and selection among four variants remain visible limitations even if signs agree.
6. Emit linked `ResearchEvidencePackage`, `EdgeSpec`, ledger and typed research `StrategySpec` where justified, otherwise a useful unresolved/rejected record. Reconcile every package claim/variant against sources and ledger. Complete when the report shows supporting and contrary evidence, mechanism uncertainty, all budget/access history, and a specific next evidence requirement. No inferential significance, validated edge, paper readiness or execution eligibility is awarded by this descriptive probe.
7. Run the same L1 availability rejection through the investigation's evaluator and save its binding to that evaluator/configuration. Complete when the known-invalid record cannot enter a supported package or inherit the clean control's status. A separate leakage demo beside an unrelated investigation does not connect the checkpoints.

Hypothesis quality, sample adequacy and experiment correctness are separate. Qualified investigation can return zero supported hypotheses and still satisfy the research-process claim. No actual historical outcomes are frozen as favorable here; the decision rules are frozen. No-thesis research must respond to inspected evidence. Replaying a predetermined strategy while labeling it agent research fails checkpoint 2.

QT201 motivates separate selection/holdout access and full-family accounting. Its permutation/stepdown algorithms are excluded from this four-hour descriptive boundary. Small variant count, a sealed holdout and a leakage check do not establish general overfitting detection. The quantitative skill's example multi-year windows, generic Sharpe cutoffs and sample-size heuristics are not imported as Monad evidence or universal rules.

### Evidence and frozen verdicts

The full-investigation artifacts remain future outputs. Existing 1A startup, resumed runs and budget-audit evidence are under workspace `prototypes/edge-os/probe-a/evidence/A01/`; `result-index.json` identifies their final scope verdict and preserved records. For the relevant run, retain `manifest.json`, `inputs.json`, `interpretations.json`, `sources.json`, `checks.json`, `ledger.jsonl`, `access.jsonl`, `requests.jsonl`, `comparison.json`, `package.json`, `edge.json`, `strategy.json` where applicable, and `verdict.json`. Save exact bounded packets, data hashes and relevant state transitions. Use the run's ledger, not a parallel trial store. Include missing/not-applicable artifact reasons instead of fabricated empty successes.

Sanitized 1A findings are in repository `docs/prototypes/EDGE_OS_PROBE_A_RESULT.md`, referencing safe artifact identities. No course source or historical dataset was published. Private course archives, credentials and unrelated workspace contents stay private. The approved plan/configuration identity is the expected-outcome authority for each run; later weakening creates a new experiment, not a pass for the old one.

| Checkpoint / verdict | Evidence required | Permitted claim and limit |
|---|---|---|
| 1 `PASS` | Every interpretation/check/control matches frozen expectations; raw/typed/expanded/canonical outputs, exact masks/numbers, reload checks, zero-read rejections and L1 timing trace exist. | Tested meaning/compilation/leakage mechanics for this subset. No historical investigation, arbitrary-text reliability, profitability or general overfitting claim. |
| 1 `NARROW` | Complete evidence for an explicitly smaller subset, with omitted checks named. No observed meaning invention or leakage admission. | Only demonstrated mechanics; builder must approve the narrower claim. Does not pass Probe A or excuse failed required cases. |
| 1 `REJECT` | Saved counterexample of invented meaning, incorrect types/units/masks, false safe state, leakage admission, concealed attempt or unearned readiness. | The frozen mechanics claim failed. A successful happy path cannot override it. |
| 1 `UNRESOLVED` | Identified missing runtime/model/fixture dependency or interrupted budget-limited check, with partial evidence. | Cannot decide checkpoint 1. No inferred pass from source inspection. |
| 2 `PASS` | Checkpoint 1 `PASS`; qualified historical bundle, one actual isolated Hermes A-N investigator trace, complete supporting/contrary evidence and unknown mechanisms, every attempt/access/cost, linked typed or useful unresolved output, and L1 rejection through the same evaluator. Zero supported hypotheses is allowed after an actual qualified investigation. | The bounded research-to-strategy process and Hermes packet integration worked for this configuration. No edge discovery, significance, causality, profitability, persistent/funded/live management, wallet delegation, demand or production-readiness claim. |
| 2 `NARROW` | Inspectable investigation/package evidence for a stated smaller claim, such as source assessment without qualified outcome coverage. Its limitations and missing gates are explicit. | Smaller research-record behavior only, subject to builder approval. Checkpoint 1 plus synthetic research cannot pass the historical claim. |
| 2 `REJECT` | Recorded invented assumptions, hidden negative evidence/variants, out-of-space/budget activity, premature holdout use, predetermined strategy passed off as research, or invalid result admitted. | The frozen research-process claim failed. Loss-making candidates alone are not process failures. |
| 2 `UNRESOLVED` | Required market/history/availability/runtime access missing or incomplete run, with exact blockers, attempted bounded checks and next evidence. | The research question remains unanswered. Current A01/A02 imply this route unless resolved; data unavailability alone is not rejection of Edge OS. |

Overall Probe A can pass only with both checkpoints `PASS`. A mechanics finding and historical blocker must be reported separately, never combined into a full pass. The recorded part-1A result does not assign a verdict to full Probe A.

### Inspected course evidence and source gaps

All paths in this subsection are `BUILDER-ONLY REFERENCE`, relative to `monad-hack`. Transcript prefix `T` means `course-insights/transcripts/`; code-frame prefix `F` means `course-insights/frame-library/`. The table records direct transcript windows and code visible in locally retained frames inspected on 2026-10-02. It is sampled source inspection, not execution or a review of entire videos.

| Adopted method / course lesson | Transcript path and inspected time | Code path and file identity | Establishes / limit / proposed check |
|---|---|---|---|
| Rejecting parser proposal, QT301 L04 | `T/QT301/04 - Alpha String Parser.json`, 08:00-10:50 and 15:00-17:10 | Screen `quantlab/gene.py:str_to_gene`, `F/QT301/04-alpha-string-parser/frames/t001019269-pts12219000.jpg`, SHA-256 `2fccb437926655b64292a0107cee46ad8e0eec726975d2cb1a739262eef8ff59` | Recursive scanner/count assertion and empty-child filtering are visible. Intermediate typo/old terminal failure is not a passed check. Full consumption and rejecting input validation are Edge OS additions. Run syntax/arity/zero-read checks. |
| Ordered serialization, QT301 L05 | `T/QT301/05 - Alpha String Deparsing.json`, 05:50-09:05 | Screen `quantlab/gene.py:__repr__`, `F/QT301/05-alpha-string-deparsing/frames/t000851602-pts10209000.jpg`, SHA-256 `4ba60dbef27cf64ac672a606a477dc6fa4f3fb92164dc9556c84013ee830b46a` | Ordered recursive repr and one assertion/metrics example. No canonical JSON/hash protocol or universal round trip. Run reload/order/semantic-identity checks. |
| Return meaning and macro lowering, QT301 L19 | `T/QT301/19 - Compound Functions and Syntactic Sugar.json`, 04:40-08:40, 11:00-12:10, 23:50-25:40 | Screen `quantlab/gene.py:evaluate_function`, `F/QT301/19-compound-functions-and-syntactic-sugar/frames/t001259009-pts15093000.jpg`, SHA-256 `65c6eaf7bf16acd4c92210492fd8a9f8bc202852b34431cafdf9ee3de6c6bbaf`; later code at `frames/t001467718-pts17595000.jpg`, SHA-256 `e126458062e3b8658200947ffb96d6156181774a9d7b31d56282762a0ada522f` | Gross close/delay, net gross-minus-one and runtime macro construction. Later frame shows macro-path early return, correcting earlier fallthrough. Intermediate MAC 50/100 is not final 50/200. Compile-time lowering/calendar history are proposed adaptations. Run exact return and expansion checks. |
| Typed operations, QT301 L11; later type dependency QT401 L05 | `T/QT301/11 - Implementation of Further Primitives.json`, 05:50-07:00 and 08:40-09:30; `T/QT401/05 - Specifying the Primitive Set.json`, 01:35-02:30, 07:45-08:50 and 16:00-17:50 | QT301 screen `gene.py`, `F/QT301/11-implementation-of-further-primitives/frames/t000539790-pts6471000.jpg`, SHA-256 `6fb2b84f50a1f62d1489612e578ff57b8a7772fb088ef396501b15bd243bbab1`; QT401 screen `primitives.py`, `F/QT401/05-specifying-the-primitive-set/frames/t000839339-pts10062000.jpg`, SHA-256 `925077ea319bf8119382a53502f815c068afa9dc5292daab04f6575acb766dda` | Binary arithmetic/strict comparisons and later numeric/Boolean metadata are visible. Later generation metadata is not a supplied-input validator or units checker. Run type/unit/bounds/fresh-and-stored-input checks. QT401 search algorithms are not adopted. |
| Explicit missing/alignment policy, QT301 L10/L18; QT101 L11 caution | `T/QT301/10 - Behavioural Polymorphism and Union Indexing Implementation.json`, 07:00-09:20; `T/QT301/18 - Encoding our Alpha Set.json`, 08:50-10:40; `T/QT101/11 - Relative Position Sizing - Instrument Volatility Targeting.json`, 22:10-25:10 | Course implementations identified as S15/S16 `quantlab/calc.py:5-42`, `gene.py:170-179,237-244`. The initial probe-plan pass did not reopen originals; the direct follow-up below did. The L18 transcript describes infinity-to-NaN sanitation and approximation. | Source inspection establishes retained-observation rolling and later output join, not general common validity or past availability. This plan excludes those helpers and requires contiguous bars/null reasons. Run gap, future-invariance and missing-availability checks. No course-parity claim. |
| Separate signal, sizing and PnL, QT101 L05/L13; timing correction L25 | `T/QT101/05 - Implementing a Random Alpha Unit.json`, 32:30-34:00; `T/QT101/13 - Implementing the Portfolio.json`, 20:48-24:57; `T/QT101/25 - Support Lecture (Common Issues and Bug Fixes).json`, 04:00-05:40 | Screen `utils.py:get_pnl_stats`, `F/QT101/05-implementing-a-random-alpha-unit/frames/t002039540-pts24450000.jpg`, SHA-256 `2bf5e881790ecc393feef098fbe465da1f90eaed8df18ee8ddedfc454ad06a3a`; corrected screen `set7/main.py:get_history`, `F/QT101/25-support-lecture-common-issues-and-bug-fixes/frames/t000353854-pts4242000.jpg`, SHA-256 `dd4f1da052a801a6bad20185938a0e28525d1d84425d424ed3db6a54154adb65` | Previous position units drive PnL; L13 explicitly leaves costs/frictions out and warns of double volatility targeting. L25's later date-only UTC repair is for daily data and would destroy intraday timing here. Keep full UTC timestamps and fixed sizing; check two-episode PnL and offsets. Fixture costs are Edge OS assumptions, not course/venue estimates. |
| Trial/selection discipline, QT201 L20/L21 | `T/QT201/20 - Multiple Hypothesis Testing with FER Control.json`, 02:30-05:00 and 05:50-09:50; `T/QT201/21 - Implementation of the Marginal Family Tests.json`, 09:20-12:10 | Screen `quant_stats.py:marginal_family_test`, `F/QT201/21-implementation-of-the-marginal-family-tests/frames/t000700450-pts8397000.jpg`, SHA-256 `a07f9e21e298bcefcea94870451a840077b265131f038bf1c7cb3e76fb6eba4c` | Selecting the best changes the statistical question; family implementation uses generated shuffled stats and configurable repetitions. Later `isinstance` correction is visible, not proof of valid financial nulls. Adopt trial accounting and withheld evaluation, not stepdown/permutation inference. Check complete ledger, rejected holdout access and omitted-contradiction package. |

The QT301 verification report supplies archive identities and corrected S13/S14 versus S15/S16 findings. Reuse it without calling its source review passed tests. Relevant later checks here inspect the L19 early return, QT401 type metadata and QT101 L25 timestamp repair. None automatically has Edge OS semantics. Corrected OBV/sum/product/slow-output behavior remains excluded.

#### Visual inspection record

Read `course-insights/frame-library/README.md` after the initial views, when the builder added the visual-inspection rule, and before any further view. Sixteen screenshots were opened once each, zero repeated views, from timestamp indexes. No galleries or entire transcript-window frame sets were opened. Inspection stopped at 16 of the 20-view ceiling; no additional views are proposed. The question groups below each used at most five views. Several selected frames did not resolve their question. Those gaps remain gaps, not permission to infer offscreen code.

Paths below use the `F` prefix defined above. This log covers every opened image, including frames that supplied no adopted method. Timestamps are lesson seconds from `frame-index.jsonl`, not rounded filename guesses.

| Question | Inspected path | Seconds | Finding |
|---|---|---:|---|
| Does the parser reject malformed input? | `F/QT301/04-alpha-string-parser/frames/t001019269-pts12219000.jpg` | 1019.269269 | Count assertion/empty-child filtering and intermediate typo visible. Complete rejecting validation not established. One view. |
| Does serialization preserve ordered structure? | `F/QT301/05-alpha-string-deparsing/frames/t000851602-pts10209000.jpg` | 851.601602 | Ordered repr, one example assertion and structural metrics visible. Canonical identity not established. One view. |
| Which return/macro and external-terminal code state is shown? | `F/QT301/19-compound-functions-and-syntactic-sugar/frames/t001467718-pts17595000.jpg` | 1467.717718 | Macro early return visible beside intermediate MAC 50/100 text; old terminal output cannot establish final parity. |
| Same question | `F/QT301/20-computations-with-alternative-data/frames/t000605255-pts7255800.jpg` | 605.255255 | External-field terminal lookup visible. No as-of check or corrected rolling definition established by this frame. |
| Same question | `F/QT301/19-compound-functions-and-syntactic-sugar/frames/t000429930-pts5154000.jpg` | 429.92993 | Gross/log expansions visible before macro-path early return; snapshot is intermediate. |
| Same question | `F/QT301/19-compound-functions-and-syntactic-sugar/frames/t001259009-pts15093000.jpg` | 1259.009009 | Net return expansion visible; old gross-sign OBV also visible and excluded. Four views for this question. |
| Does later type/registration metadata validate supplied input? | `F/QT401/05-specifying-the-primitive-set/frames/t000389139-pts4665000.jpg` | 389.139139 | Enum and unfinished terminal dictionary visible; no validator evidence. |
| Same question | `F/QT401/25-adding-proprietary-datasets/frames/t000500501-pts6000000.jpg` | 500.500501 | Factory initialization and external-field assembly visible; does not answer whole-parser validation. |
| Same question | `F/QT401/05-specifying-the-primitive-set/frames/t000101852-pts1221000.jpg` | 101.851852 | Data-loader code visible, not a rejecting registry. |
| Same question | `F/QT401/05-specifying-the-primitive-set/frames/t000839339-pts10062000.jpg` | 839.339339 | Numeric/Boolean signatures developing beside evaluator code. Parsed-input validation still unresolved without whole-source inspection. Four views. |
| What operation/strict-comparison meaning is implemented? | `F/QT301/11-implementation-of-further-primitives/frames/t000539790-pts6471000.jpg` | 539.78979 | Binary subtraction/division and strict gt/lt visible. Runtime dispatch alone is not static validation. One view. |
| Are sizing and PnL separate from a signal? | `F/QT101/05-implementing-a-random-alpha-unit/frames/t001669920-pts20019000.jpg` | 1669.91992 | Direction forecast and allocation preparation visible; PnL body not established here. |
| Same question | `F/QT101/05-implementing-a-random-alpha-unit/frames/t002039540-pts24450000.jpg` | 2039.53954 | PnL uses prior units and price change. Costs and executable fills not established. Two views. |
| What does the later UTC repair preserve? | `F/QT101/25-support-lecture-common-issues-and-bug-fixes/frames/t000300801-pts3606000.jpg` | 300.800801 | Editing/debugging state; final timestamp treatment not yet clear. |
| Same question | `F/QT101/25-support-lecture-common-issues-and-bug-fixes/frames/t000353854-pts4242000.jpg` | 353.853854 | Date-only conversion/localization visible. Unsuitable for preserving intraday event time. Two views. |
| What inputs does the family test actually use? | `F/QT201/21-implementation-of-the-marginal-family-tests/frames/t000700450-pts8397000.jpg` | 700.45045 | `isinstance`, shuffled weights and criterion wiring visible. Null validity/whole stepdown implementation not established. One view. |

Sixteen sampled views are not complete visual verification. The controller subsequently inspected the named companion members below without opening another screenshot. No further screenshot budget is needed for this independent subset; uninspected sources and financial-null claims remain excluded.

For the two external-terminal frames, also inspected the available Parakeet transcript windows `T/parakeet-v3/QT301/20 - Computations with Alternative Data.json` at 05:30-07:10 and `T/parakeet-v3/QT401/25 - Adding Proprietary Datasets.json` at 07:00-08:50. They describe name-based external-field assembly, not point-in-time suitability. Their exact source references identify machine transcripts; no alternative-data method is adopted. They do not replace direct companion inspection.

#### Direct companion-source follow-up, 2026-10-02

The builder authorized the controller's recommended source check. Read-only archive/member inspection verified the actual originals. No course code was executed, copied into the application repository or published. The earlier probe agent's workspace-only access gap was real at that time; this follow-up resolves only the named checks.

| Private original archive | Verified SHA-256 |
|---|---|
| `Downloads/QT 301/20 - Computations with Alternative Data - set15.zip` | `262eaff473c52b6c557c578e88657a8cffbeae0f0219d0d29b50db2a34c2f039` |
| `Downloads/QT 401/25 - Adding Proprietary Datasets - set16.zip` | `f7ca61ae368cb423e0f435aaaed34f9b5fd777e2507d0a44a71c07a8ee172201` |

Paths are builder-only original source locations, not teammate dependencies. Complete S16 `quantlab/gene.py`, `quantlab/calc.py` and `quantlab/primitives.py` were read. Member SHA-256 identities are respectively `abd6261af4a370334e1d238b4529107de495a5e2cf648a730248a6a20966979c`, `5222f8c249a8cee6df3e8309956cb436703194692d0334b223db38c2c67503c9` and `2b0d0c3cafc779fbc3ae9638173c7bd62a42e89e3c7c3c5b3453576a6f7b3b84`.

Direct S15/S16 comparison found identical `calc.py`; `gene.py` differs only in the Alpha import spelling and two blank lines. The inspected code confirms recursive parsing, ordered representation, strict `gt`, macro return and net-return expansion. Primitive metadata declares input/output types and child-count generators, but the supplied-expression parser/evaluator does not apply equivalent static preflight validation. It also does not implement this plan's units, availability or readiness gates.

`self_idx_op` drops missing values before rolling. `union_idx_op` forward-fills operands. Those policies differ from Probe A's contiguous-bar, no-fill rule. Preserve the independent Probe A semantics and focused checks. Do not claim course parity, copy the helper unchanged or treat source inspection as a passed runtime test.

A04 is resolved for these named compiler-source questions. QT101 execution wrappers, QT201 statistical code and uninspected course members remain unverified in this follow-up. They are not dependencies of the independent minimal implementation. Any later copying, parity claim or use of excluded methods needs its own bounded inspection and applicable sharing rights.

The inspected sources do not establish arbitrary-text interpretation, economic mechanisms in this market, calibrated model confidence, usable provider coverage or profitable momentum. Those remain experimental questions or unknowns. No comprehensive course distillation is required before this narrow review.

### Stops and approvals before execution

Stop each checkpoint at its verdict. Proceed to checkpoint 2 only with its explicit approval, a checkpoint-1 pass and resolved applicable blockers. Stop affected work on an exhausted effort/runtime/request/read/variant/cost ceiling, missing essential data, static/availability failure, inconsistent identity, concealed evidence, unsupported operation or attempted authority expansion. Preserve the reason and partial evidence. Expected invalid-case denials end that case and permit the remaining approved checks; an unexpected safety or meaning failure stops the checkpoint. Never increase limits or change expected outcomes to get a pass.

Remaining blockers are A01 market identity, A02 qualified historical data/availability/execution coverage, and A03 Hermes runtime/model/isolation/usage capture. A04's named compiler-source questions are resolved by inspection, not execution; broader course parity remains unclaimed. Deterministic part 1A can be approved despite A01-A03. Part 1B requires the approved Hermes configuration. Missing historical execution-cost data keeps tradability unresolved even if price-association research can proceed. The strategy component-policy version remains `probe-a-v1`; the investigator/experiment configuration now has the separate proposed `probe-a-v2-hermes` identity. Neither is an approved runtime result.

Required builder approvals for remaining scope are `PENDING`; deterministic part 1A has the partial approval recorded in section 8:

1. Approve or revise this scope, exact input texts, grammar/numerical/timing/identity rules, controls, verdicts and four-hour effort cap. State whether approval covers deterministic part 1A only, the complete checkpoint 1, or both checkpoints. Code is limited to the proposed private throwaway path and evidence outputs.
2. For checkpoint 2, bind `MARKET_A`, approve the exact local bundle/source identities and coverage, accept the declared splits and descriptive claim limits, and resolve historical availability. Collection or replacement data needs a separate scoped approval and budget.
3. Approve the exact Hermes release/configuration, model access route and numeric request/token/compute/read limits. Verify entitlement and proposed USD 0 incremental cost before any call, or approve a revised explicit cost ceiling. Source checks do not approve installation, sign-in or credential access. Keep the subscription and API routes distinct.
4. Approve the separate market/data qualification acquisition budget only if needed. Source inspection is complete for the named compiler members, not all courses. Do not authorize broad archive copying by approving fixture mechanics.

Financial permissions, Probe B and the full design remain unchanged. Review this plan; do not implement, run, publish results or mark either checkpoint passed until its approvals and applicable blockers are resolved.

## 5. Probe B: delegated Monad–Kuru action

### Frozen question

Can the exact approved Kuru action execute on the selected Monad network through a restricted Privy delegation while the user is offline, with independent policy denial, restart reconciliation and owner removal behaving as required?

Failure changes the autonomous-deployment promise. Assensus establishes a reusable pattern, not this chain/venue result.

### Smallest runnable test

1. Verify the approved network, contracts, action semantics, policy content and ownership. Keep execution credentials in the backend secret store and outside model context, browser output, logs and public artifacts.
2. Bind one controlled strategy/fixture revision to a consented mandate. Persist an intent before submission. Use one deterministic signing/submission transport.
3. Execute one approved action without another user signature. Save its receipt, decoded applicable Kuru event and resulting state. Distinguish transaction acceptance, order placement, fill, partial fill and resting exposure.
4. In the isolated approved environment, test a protected-field violation at the provider boundary. Distinguish a Privy policy denial from a local risk denial. Never disable production guards.
5. Interrupt the worker after submission and before local completion recording. Recover the same intent using durable records and chain/venue state. Show that no second action was created. Unknown outcomes stop new submission.
6. Verify owner removal of the signer. Test an equivalent request independently of any exhausted local order-count limit. Show no new transaction and retain pending transactions/resting orders until reconciled or explicitly closed under approved authority.

Do not repeat funded execution merely to obtain a nicer recording. Use one approved action with a prepared denial/recovery sequence. A denied request needs inspectable evidence of the reason; a local button or HTTP error alone is insufficient.

### Verdict conditions

- `PASS`: all frozen checks above have direct evidence, the actual action matches its mandate, recovery creates no duplicate and post-removal behavior proves the intended authority boundary. Also account for all applicable checks in design section 17 before claiming delegated-execution readiness.
- `NARROW`: a smaller operation or authorization model works. Record the exact claim and require builder approval before changing the product promise.
- `REJECT`: the required boundary is incompatible, permits an unauthorized effect, duplicates an action or continues authorizing execution after verified removal.
- `UNRESOLVED`: network access, policy support, funds, configuration or evidence prevents a complete answer. An adapter blocker is not a pass.

Stop at the verdict or approved budget. Save sanitized environment/version records, approval scope, intent/strategy/policy identities, actual public receipts/events, denial evidence, recovery sequence and remaining exposure in `docs/prototypes/EDGE_OS_PROBE_B_RESULT.md`. Passing B proves the tested mechanics, not a trading edge or production security.

## 6. Isolation and excluded work

After approval, keep temporary code under `prototypes/edge-os/probe-a/` or `prototypes/edge-os/probe-b/` in the builder's private `monad-hack` workspace, outside this application repository. Preserve existing files and record changed paths and artifact identities. Publish sanitized findings, agreed contracts and the necessary fixtures in this repository before teammates depend on them. Repository setup is not a prerequisite for the experiment. Save evidence before replacing or removing temporary code.

Neither probe includes LP simulation/execution, tokenization, market issuance, fee loops, a marketplace, broad search, another venue, a production UI or production hardening. LP remains part of the draft product's second proof. Optional-token decisions remain separate from this plan.

No runtime, provider, schema, network, capital or meaning change may inherit a result from another configuration. Return material changes for approval and revalidation.

## 7. Return findings and decide the build route

Record A and B separately. A fixture-only result cannot pass the full Compass prototype. Combine evidence only when exact revision/action semantics and the useful result actually connect. Keep the full design and separate execution gate intact.

Review findings with the builder. Narrow, reject or resolve any blocker before building around it. If linked core decisions remain too broad for one session, use a small Wayfinder map; otherwise finalize them in one focused session. Wayfinder is a decision process, not an implementation backlog. Do not reopen Edge OS selection or the retired Funnel.

Synthesize the production design/build brief, obtain approval, then create ready implementation tickets. Optional extension economics need not block core decisions. No automatic phase advancement follows a component pass.

## 8. Approval record

| Boundary | Current decision |
|---|---|
| Documentation update | `AUTHORIZED`, 2026-10-02 |
| Probe A instantiated design and code | Part 1A only `AUTHORIZED`, 2026-10-02, by the builder's scoped task prompt; all remaining Probe A scope `PENDING` |
| Probe A model/provider costs | `PENDING`; no new paid calls |
| Probe B instantiated design and code | `PENDING` |
| Probe B wallet changes, provider use and financial limits | `PENDING`; no signing or transactions |
| Builder result-state prototype | `PENDING` |
| Full product design/build brief | `PENDING` |
| Optional token extension | `PENDING`; not part of either probe |

### Deterministic part-1A partial approval, 2026-10-02

The builder approved implementing and running only the offline standard-library terminal experiment with authored structured synthetic inputs, typed compilation/canonical serialization, focused self-checks, C0/L1 comparison, local evidence and a sanitized result report. Active work is capped at 90 minutes including preparation, implementation, checks and reporting; it consumes the existing checkpoint-1 allocation. The frozen grammar, numerical/timing policies, fixtures, expected outcomes and limits remain unchanged. Codex implementation assistance is not experimental interpretation or Hermes evidence.

Question: Can the declared structured input compile into an inspectable typed strategy, preserve its meaning through serialization, and reject a deliberately attractive result that uses future information?

A01 real market identity, A02 historical data and A03 Hermes/runtime/model/authentication/isolation/usage are `NOT_APPLICABLE_TO_1A`, not resolved. A04 is resolved only for the named compiler-source questions already inspected; inspection is not a runtime pass or course-wide parity. Startup must demonstrate enforceable 900-second wall, 120 aggregate CPU-second, one-CPU, 512-MiB working-memory and 100-MiB aggregate-output limits before the affected experiment runs. If any limit cannot be enforced, stop and retain the exact limitation and proposed alternative. The authored fixtures do not stand in for historical evidence.

Approved private path: `prototypes/edge-os/probe-a/`, with local evidence at `prototypes/edge-os/probe-a/evidence/A01/`. Approved sanitized report: `docs/prototypes/EDGE_OS_PROBE_A_RESULT.md`. No commit, push, merge, issue, credential/provider/model access, signing or trading is authorized. Part 1B, checkpoint 2, Hermes, Probe B, financial permissions, frontend and full product remain unchanged and unapproved. A successful 1A is `MECHANICS ONLY` and cannot pass complete checkpoint 1, Probe A or the Compass prototype gate.

Next action: qualify deterministic part-1A startup enforcement, then run only if its required caps are enforceable. The separate Hermes/data proposals still need their own approval. This document remains the shared plan; do not create another mandatory planning document.

Part-1A startup finding: `UNRESOLVED — MECHANICS ONLY`. The local macOS host rejected the 512-MiB memory-limit setting; a hard one-CPU limit was not verified. Startup evidence and the exact omitted compiler checks are recorded in [EDGE_OS_PROBE_A_RESULT.md](EDGE_OS_PROBE_A_RESULT.md). No compiler fixture evaluation began. Complete checkpoint 1, Probe A and the Compass prototype gate remain unpassed. A separately approved enforcement route is required before the affected run.

### Part-1A resource-boundary amendment

The builder subsequently instructed: "ignore that, proceed so long I enough memeory to continuye". This authorizes proceeding with sufficient available memory and measured usage/watchdogs instead of requiring demonstrated hard memory/CPU-affinity enforcement. It supersedes the startup hard-enforcement blocker for deterministic 1A only. Use a single-threaded bounded workload, observe peak RSS with a 512-MiB stop threshold, retain the 900-second wall watchdog, 120 CPU-second limit/accounting and 100-MiB aggregate-output ceiling. Observed-memory checks can detect an overrun after allocation; they are not a hard allocation cap. Do not claim scheduler affinity or the earlier resource-enforcement proof passed.

Keep original failed startup evidence immutable. Resume under `prototypes/edge-os/probe-a/evidence/A01/1A-resume-01/` (or a new numbered evidence subdirectory after an unexpected failure), within the remaining original 90-minute allocation. Freeze the revised configuration identity before executing. This changes resource approval only: grammar, numerical/timing semantics, fixtures, expected numbers, invalid-case denials, evidence requirements and all other scope permissions remain unchanged. A successful revised 1A still cannot pass complete checkpoint 1, Probe A or the Compass gate.

### Part-1A observed result and stop

Two revised-resource runs produced 79 and 81 passing local checks, including frozen C0/L1 numbers, canonical reload, fresh/stored rejection and future-information denials. The second run added precise denial traces and two focused checks; no expected result was weakened. The final audit found a real control failure: the program reset the accepted-read counter per run. It admitted 16 fixture reads in each run, 32 against the unchanged A01 total cap of 20. Local suite pass labels do not override this breach. Final part-1A verdict: `REJECT — MECHANICS ONLY` for aggregate-budget accounting.

The corrected program counts accepted access events across A01 run directories. A bounded audit through its normal read boundary denied the next operation as `BUDGET_EXCEEDED`, with zero new fixture reads. Both executed program snapshots, local pass outputs and original startup failures remain retained. The corrected full experiment was not rerun because the read budget is exhausted. The result report identifies the exact successful mechanics and this failure separately; it is not rejection of the full Edge OS product.

Stop here. A new compiler verification run requires a separately approved configuration/read budget; the 32 prior reads remain in history. Preserve the remaining original active-work allocation rather than silently granting a fresh 90 minutes. Hermes, part 1B, historical investigation, Probe B and financial permissions remain unchanged. Complete checkpoint 1, Probe A and the Compass gate remain unpassed.

### Authorized accounting recovery: `1A-recovery-01`

The builder approved this separate recovery on 2026-10-02. Question: Does the corrected program preserve cumulative accounting across runs, enforce a configured allowance, and pass the original compiler and leakage checks? Allow 30 active minutes including preparation, repair, checks and reporting. Previous work and the prior `REJECT — MECHANICS ONLY` remain separate and unchanged.

Remove the 20-read stopping limit only for repeated fixed synthetic-fixture reads in offline 1A. Keep recording every accepted read and byte count, including the previous 32 reads/13,532 bytes. Keep existing byte/expression checks, single-threaded execution, watchdog, CPU limit, observed-memory monitoring and output ceiling. This exception permits no new fixtures, search, changed expected outcomes or relaxation of later model/provider/trial/holdout limits.

Use the normal read function with an isolated, persistent two-read regression profile. First process accepts/persists one read and exits. A fresh process must load one previous read, accept the second and deny the third as `BUDGET_EXCEEDED` before returning data. Accepted usage remains two. Another fresh process must still deny access. Invalid/unreadable accounting must stop the capped operation rather than grant a fresh allowance. Reload profile consumption before each capped read. Test through actual persistence, not only `consume_budget()`.

Retain recovery records under `prototypes/edge-os/probe-a/evidence/A01/1A-recovery-01/`, separate from earlier evidence. Keep capped regression records distinct from unrestricted synthetic metrics and include both in the overall inventory. After the restart/denial checks pass, run the complete deterministic 1A suite. Preserve grammar, units, decimal/missing-value policy, timing, canonical identity, C0/L1 values and assertions. Record executed snapshots/hashes, configuration, commands/exit codes, actual/expected outputs, usage and failures. A code change after a full suite requires another full suite before recovery PASS.

Return a new `PASS — MECHANICS ONLY` only when restart accounting and the full corrected suite pass. Otherwise record REJECT or UNRESOLVED with the cause. Stop at 30 active minutes. Part 1B, complete checkpoint 1, Probe A, Compass gate, Hermes, historical collection, providers, credentials and financial permissions remain unchanged and unpassed/unapproved. The new recovery result cannot replace the failed experiment.

Recovery finding: `1A-recovery-01` is `PASS — MECHANICS ONLY`. Five fresh-process regression checks passed: first read persisted; next process loaded one and accepted the second; third and later reads were denied with usage remaining two; malformed and missing accounting blocked access without a fresh allowance. The complete corrected suite then passed all 81 checks, including the actual persisted read-budget case. C0/L1 numbers, fixture identities and semantic identity stayed unchanged.

Cumulative uncapped offline metrics are 48 reads/20,298 bytes, including the original 32 reads/13,532 bytes. The isolated restart and suite profiles each accepted two reads/676 bytes: 52 accepted reads/21,650 bytes overall. Six commands exited 0. Runtime was 0.606 seconds wall and 0.448 seconds aggregate CPU; maximum observed RSS was 30,244,864 bytes. These are recovery measurements, not claims that the rejected experiment satisfied its cap. Prior evidence hashes remain unchanged. No code changed after the full suite.

The new verdict, program snapshot, restart traces, commands and inventory are in the recovery directory. [The shared result report](EDGE_OS_PROBE_A_RESULT.md) preserves both results. Stop after reporting. No remaining deterministic-1A recovery blocker was observed. Part 1B and all larger gates remain unpassed and require separate approval.


### Part 1B scoped approval, 2026-10-02

The builder authorized the smallest private Python adapter and four frozen Hermes interpretation cases, single-threaded, followed by builder review. Use installed Hermes commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, its frozen lockfile and the unchanged recovered 1A compiler. The active model is `openai/gpt-6-luna` through OpenRouter; this supersedes the historical Gemini setup. Source, lockfile, compiler and isolated configuration hashes matched before adapter checks.

Only the existing destination `OPENROUTER_API_KEY` assignment may be loaded inside the adapter. No source-workspace inspection or copying is approved. No key enters model context or evidence. For 1B only, the earlier USD 0 model-call condition is replaced by four inference requests total, one per frozen case, no retries, repair calls, auxiliary calls or model substitution. A-T is the first connection test. Each response is capped at 1,024 tokens with a 90-second deadline. A01 aggregate limits remain 48,000 input and 8,000 output tokens. Every inference POST counts, including failed calls.

The working cost allowance is USD 0.10. The conditional USD 0.30 backup may be activated only with a recorded need and persisted reservation-limit amendment before dispatch. It is not active now. There is no provider-enforced key cap or verified account balance. The adapter reserves a conservative byte-based prompt-token upper estimate plus completion allowance at the checked price before dispatch. Counts are labeled estimates until provider usage arrives. Unknown charges retain their reservation and stop later dispatch; they are never recorded as zero. Routing price ceilings are separate from the total allowance.

The adapter invokes actual `AIAgent.run_conversation`. Empty tools, disabled memory/context/soul/review/compression/fallback/recovery and one API attempt are asserted. It supplies only the declared packet and output contract. A synchronous SDK transport keeps the experiment single-threaded, with SDK/HTTP retries zero, no proxies or redirects, and one allowlisted inference endpoint. The final serialized body is checked for the chosen model, JSON output, reasoning `none`, and absent unsupported parameters. Sticky-session metadata injected by pinned Hermes is omitted with a recorded mapping. This is a controlled single-builder boundary, not an OS sandbox or production tenancy.

Offline attempts `adapter-01` and `adapter-02` were blocked before paid dispatch by unsupported sticky metadata and trailing-whitespace normalization respectively. Their evidence remains retained. `adapter-03` passed the actual offline conversation/wire check plus request, cost, token, malformed-record and uncertain-reservation checks. No real key or inference request was used in those checks. The executed snapshot and configuration are under private `prototypes/edge-os/probe-a/evidence/A01/1B-01/adapter-03/`.

A-T may compile genuine Hermes output through the unchanged 1A compiler. The only compatibility mapping is its `input_class` provenance marker; raw model output and real Hermes provenance remain separate. No missing model fields may be supplied or repaired. A-I must clarify; A-N is intake only and remains unresolved without qualified history; the exact wallet-label/X/LP extension must remain unsupported. Historical investigation, deployment, Probe B, application implementation, credentials beyond the named destination and financial execution remain unapproved. Prior 1A rejection and recovery are preserved. Full Probe A and the Compass gate remain unpassed.

Pre-dispatch adapter correction: `adapter-03`'s first live launch loaded the approved destination credential but stopped on an offline/live evidence filename collision. No inference POST or reservation occurred. The failed launch remains retained. `adapter-04` separates those names, rejects reuse if any other 1B directory contains a reservation, and reran all offline checks successfully. This is the active executed identity. No paid request has occurred yet.


### Part 1B observed result, 2026-10-02

`1B-01/adapter-04` is **REJECT — HERMES INTERPRETATION**. One A-T inference POST returned a complete packet. It retained the fixed rule, timing, amounts, unknown mechanism and empty permissions, but included a non-null four-variant search_space in the fixed thesis case. Raw mode `research simulation` failed the unchanged 1A compiler as `INVALID_INPUT` (`mode`); unit-bearing sizing strings also differ from its numeric-string interface. The only mapping applied was the legacy input-class marker. No hand repair, extra normalization or expected-answer filling occurred. Non-empty exclusions triggered another adapter assertion, but mostly preserve user prohibitions and are not independently called invented meaning.

The provider response and charge were retained. Hermes conversation completion failed with a connection error. A local authored compressed-response fixture reproduced a response-relay defect; exact live response headers were not retained, so the live causal attribution is an inference. No adapter changes followed paid inference. Under the frozen unexpected-meaning-failure stop, A-I, A-N and the wallet-label/X/LP case are `NOT_RUN`. No retry or repair inference occurred.

Provider usage was 970 prompt, 455 completion, 1,425 total and zero reasoning tokens. Actual cost was USD 0.0003245. The persisted pre-dispatch reservation was USD 0.0010124 with a 5,004-token conservative prompt estimate and 1,024 completion allowance. It settled from provider usage; no uncertain reservation remains. One of four 1B requests and one of eight proposed A01 total requests is consumed. The USD 0.10 allowance remains active; the conditional USD 0.30 backup was not activated. Six earlier metadata requests remain historical; no new metadata or market-data requests occurred. These are local controls, not a provider-enforced account cap.

Active offline checks passed before dispatch. The prior sticky-field, newline and filename-collision failures remain preserved with zero paid POSTs. Snapshot/hash, commands, raw packets, exact compiler denial, request/accounting controls, restart test and verdict are in private `prototypes/edge-os/probe-a/evidence/A01/1B-01/adapter-04/`. [The result report](EDGE_OS_PROBE_A_RESULT.md) records the observed scope and limitations. A failed preparation check used system Python without httpx; reporting resumed with the installed Hermes interpreter. A preservation check initially included two newly opened active logs; those captures were explicitly excluded from the prior-evidence comparison. All 147 actual prior files checked against the active-run inventory remained unchanged, including original setup and 1A records. Secret-value exclusion checks passed.

The paid process ran 6.90 seconds, used 1.12 CPU seconds and peaked at 178,323,456 bytes RSS. The final offline check ran 1.37 seconds and peaked at 181,157,888 bytes. Earlier offline attempts and full active preparation time were not instrumented. Watchdog, request deadline, CPU limit, observed-memory guard, output ceiling and single-threaded dispatch remained active. No hard-memory, affinity or OS-isolation qualification is claimed.

Checkpoint 1 remains unpassed. Original 1A REJECT and recovery PASS remain separate. Full Probe A, checkpoint 2, Compass, Probe B, production design and financial permissions are unchanged. A01/A02 remain unresolved; A03 successful response/interpretation integration remains unproved. Stop for builder review. An offline relay/contract repair and any further inference need a separately reviewed scope; the remaining three requests are not an A-T retry or a reset allocation.


### Part 1B offline repair approval and result, 2026-10-02

The builder authorized adapter/schema/test changes and offline checks only. New identity: `1B-offline-repair-01`. No inference, spending, credential read, historical acquisition, deployment or financial action was authorized by this repair prompt. Historical `1B-01/adapter-04` remains REJECT; 1A recovery and all earlier evidence remain preserved. The frozen inputs, expected decisions, grammar, numerical rules, compiler and model selection are unchanged.

**OFFLINE REPAIR PASS — LIVE 1B UNPROVED.** The final complete suite passed 25/25 checks, exit 0. Authored provider fixtures traverse the actual Hermes conversation, completion gate, strict packet validator, unchanged compiler, canonical serialization, reload and frozen meaning comparison. Plain and gzip A-T pass; A-I clarifies, A-N remains unresolved at intake and A-U remains unsupported without substitution. These are integration results, not model interpretation results. Part 1B, complete checkpoint 1, Probe A and the Compass gate remain unpassed.

Contract `probe-a-1b-output-v2` is generated from one installed Pydantic model. All fields are required; nullable outcomes retain null strategy/search values. It fixes mode, numeric-string/unit separation, strict integer/boolean fields, enum prohibitions and compiler grammar instructions. Extra fields are denied. A-T receives no A-N search configuration; A-I receives no parameter defaults. Prohibitions remain restrictions rather than capabilities. Compiler rules are not loosened. Only the existing input-class compatibility mapping is permitted; authored fixture provenance is separate.

The adapter requires a completed, nonfailed Hermes final response matching the captured response. Failed conversations cannot pass from provider capture alone. Decoded HTTP bodies no longer retain stale compression/length headers; safe received headers and wire/decoded bytes are retained. Nonfinal responses are denied before Hermes' continuation or summary path. Case evidence directories avoid collisions. The case deadline restores the outer watchdog. Live entry points currently deny before key access.

Baseline red checks, focused repairs, the intermediate truncation failure and the final suite are retained. New checks also reject erased unsupported domains and verify that reservations include the schema payload. Paid accounting is unchanged in identity and remains separate from authored offline accounting. Restart, unknown-charge, malformed-record, request/cost/token limits and output denials pass. No arbitrary fixture-read ceiling was added.

Final command: `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage green-full-03`. Elapsed 2.374 seconds; CPU 1.964 seconds; peak RSS 181,796,864 bytes. Existing watchdog, CPU, observed-memory, output, byte and expression controls remain. No hard-memory/CPU-affinity qualification was repeated. All 184 prior evidence files, compiler, Hermes pin, lockfile and original configuration were checked unchanged.

Strict JSON Schema request generation is configured from OpenRouter documentation fetched through Context7 after ID resolution. The retained selected-model metadata advertises support. Acceptance and enforcement of this exact schema by a live endpoint are untested. `require_parameters=true` and local validation remain required; no silent basic-JSON fallback is allowed. Compression's role in the original live error remains unconfirmed because the live headers were not retained.

Actual cumulative usage remains one inference request, 970 input and 455 output tokens, USD 0.0003245, with no unknown charge. No model/provider metadata call or credential read occurred in the repair. Older controller/Compass “not started” status contradicts the retained result and must not govern execution; those files were not changed within this task.

Next recovery approval proposal: **PENDING**, four additional inference requests, five cumulatively. Preserve the previous charge, counts and journals. Keep the USD 0.10 working cap and USD 0.30 maximum, frozen case order, A01 token limits, 1,024 output tokens and 90-second request deadline. No automatic retries, repair calls or model escalation. A separately approved recovery must persist that allowance and cumulative prior usage, verify admission offline and explicitly enable its live route before dispatch. This proposal changes no current approval or ledger. A01/A02, historical investigation, Probe B, deployment, financial permissions and the complete product remain unchanged.

Private evidence: `prototypes/edge-os/probe-a/evidence/A01/1B-offline-repair-01/`. [The shared result report](EDGE_OS_PROBE_A_RESULT.md) records root causes, contract/source identities, red/green commands and limitations. Stop for builder review.


### Part 1B live recovery approval, 2026-10-02

The builder approved `1B-recovery-01`: four additional inference requests, five cumulatively, for A-T, A-I, A-N and the unsupported extension in frozen order. Preserve the previous paid request, USD 0.0003245 charge, token usage and all evidence. The USD 0.10 working cap remains active; USD 0.30 is the absolute maximum. No extra allocation, automatic retry, output-repair request, model escalation or broader research is approved. No larger working reservation cap is activated by this record.

Use the repaired contract, unchanged compiler, pinned Hermes setup and selected GPT model. Before dispatch, verify offline that persisted cumulative accounting includes prior usage, admits at most four new requests and denies uncertain charges, malformed records and allowance overruns. Retain each actual response and Hermes completion state. Stop on an unexpected failure. Missing historical evidence leaves A-N unresolved at intake. Historical checkpoint 2, Probe B, deployment, production implementation and financial permissions remain unchanged and unapproved. Results are pending.


### Part 1B live recovery observed result, 2026-10-02

`1B-recovery-01`: **REJECT — HERMES INTERPRETATION**. A-T passed; A-I failed `CLARIFICATION_GAPS`. A-N and the unsupported extension were NOT_RUN under the existing failure stop. The original live rejection and all earlier 1A/offline-repair results remain preserved. Checkpoint 1, complete Probe A and the Compass gate remain unpassed.

Before inference, 28/28 offline checks passed against the executed program. The new persisted recovery profile retains the original journal's identity and usage: one request, 970 prompt/455 completion tokens, USD 0.0003245. It admits at most four additional calls, five cumulatively, within the USD 0.10 active working cap and USD 0.30 absolute maximum. Unknown-charge, malformed-record, request/token/cost limits and normal-gate denial checks pass. Offline fixtures remain separate from actual usage.

A-T's genuine response retained all fixed strategy meaning, unknown mechanism and empty permissions. Actual Hermes completion, packet validation, unchanged compilation, canonical serialization, reload and equality with the frozen 1A semantic identity passed. No broader search was imported. A-I completed and returned useful clarification without a strategy or search, but omitted direction confirmation. Its descriptive gap strings also differ from the validator's canonical field names. The schema permits free-text gaps; this surviving contract mismatch was not exposed by the authored fixtures. No aliases or missing fields were supplied after inference. Expected outcomes and assertions were not changed.

A-T cost USD 0.000583925; A-I cost USD 0.00015534. New usage: two POSTs, 5,915 prompt/622 completion tokens, USD 0.000739265. Cumulative actual usage: three requests, 6,885 prompt/1,077 completion tokens, USD 0.001063765. Both reservations settled; no unknown charge remains. Provider cache-charge details are retained. The larger working cap was not activated. No retry, repair call, model escalation, provider metadata call or historical-data request occurred.

Both received gzip responses now reached successful Hermes completion. The exact original live failure's compression attribution remains unconfirmed. The strict-schema endpoint accepted these requests; local validation and frozen meaning checks remained mandatory. The compiler, contract, source pin, lockfile, configuration and model are unchanged. All 761 prior evidence files remained unchanged. No post-dispatch code changes occurred.

Commands, exit codes, actual packets/conversation states, canonical meaning, per-case resources and persisted accounting are in BUILDER-ONLY REFERENCE `prototypes/edge-os/probe-a/evidence/A01/1B-recovery-01/`; see `recovery-manifest.json`. [The result report](EDGE_OS_PROBE_A_RESULT.md) records the remaining contract issue and substantive clarification omission. Two new calls were unspent, but the failure stop requires controller review before further dispatch. Next proposed task: a separately scoped offline clarification-contract review/repair, then review any explicit inference recovery. Historical checkpoint 2, Probe B, production implementation and financial permissions remain unchanged. Stop for controller review.


## 11. Offline interpretation-contract repair and prospective clarification loop

Date: 2026-10-02. Identity: `1B-contract-repair-01`. The builder authorized adapter, contract, focused tests and these shared records, with offline checks only. No credential access, provider request, inference, spending, installation or financial action was authorized. All earlier results and journals remain authoritative for their own runs. The original 1B rejection and `1B-recovery-01` rejection are not replaced. Its A-T pass remains a genuine, narrow result; its incomplete A-I remains failed. A-N/A-U have not run live.

**OFFLINE CONTRACT REPAIR PASS — LIVE INTERPRETATION AND CLARIFICATION LOOP UNPROVED.** The final complete suite passed 41/41 checks, exit 0. No new inference occurred. Part 1B, complete checkpoint 1, Probe A and the Compass gate remain unpassed. This revision governs the prepared contract, not a new execution approval. Scope and execution approval for the prospective experiment remain **PENDING**.

### Shared contract and decision boundary

Use `probe-a-1b-output-v3`. One installed Pydantic schema supplies strict generation structure and local validation. The instructions reference that same schema and its gap definitions. All properties are required, including nullable fields; additional properties, invalid enum values and ambiguous numeric forms are rejected. Numeric parameters remain fixed-decimal strings with separate units; timing values remain integers. The compiler is unchanged. No unrestricted executable code is accepted.

| Stable missing-meaning ID | Meaning |
|---|---|
| `threshold` | Return definition, completed lookback and cutoff chosen by the user. |
| `direction` | Advances, declines or both; supported compilation is upward continuation only. |
| `horizon` | Future response interval, separate from financial authority. |
| `timing` | UTC evaluation, feature availability and research reference schedule. |
| `entry` | A research entry reference if not already supplied through timing. |
| `exit` | Exit reference/rule, separate from response horizon. |
| `sizing` | Research quote amount/unit, paper balance and position restrictions. |
| `comparison` | Confirmation of conflicting strict/inclusive comparisons. |

`missing_fields` contains only these IDs. `questions` contains exactly one nonempty `{field, question}` record per missing ID. Order and faithful wording are flexible. Duplicate IDs, missing questions, missing necessary IDs and requests for supplied information fail. Enum membership does not prove that each human question asks the identified meaning. That requires a separate semantic review; there is no auxiliary model judge.

`requested_scope` separately records market, domain, action and required inputs. The finite probe schema admits `SPOT`/`LP`, `ASSOCIATION_TEST`/`REBALANCE`, and `PRICE`/`WALLET_LABELS`/`X_ATTENTION`. These identify requested capabilities, not permissions. `unsupported_capabilities` identifies unavailable wallet labels, X attention, LP rebalance, strategy form or execution. `exclusions` retains user prohibitions; excluding a capability must not be treated as requesting it. `evidence_gaps` identifies unavailable real market identity, qualified historical prices and availability times. Free-text explanations and domain descriptions no longer need particular English keywords.

Outcomes remain distinct. `NEEDS_CLARIFICATION` asks for missing or conflicting meaning. `UNSUPPORTED` preserves an unavailable operation or domain without substitution. `UNRESOLVED` identifies missing evidence and may retain the bounded search at intake. `COMPILED` retains sufficiently specified, supported rules through the unchanged compiler. Representation, refusal and transport failures describe the proposed output or conversation; they do not automatically condemn the user's idea. No outcome grants profitability, paper readiness, deployment or execution authority.

A-T receives only its declared thesis and references. A-I receives no threshold, schedule or sizing defaults. A-N alone receives its finite search. The extension retains its wallet-label/X/LP domain. A clarification exchange adds only the original request, the preceding validated interpretation and an explicitly authored user reply. The transport gate denies arbitrary added context. A model response is never filled from an expected answer. The sole compiler compatibility mapping remains `input_class`; the real model or authored-fixture provenance is retained separately.

The selected endpoint previously accepted v2 strict-schema requests. Local v3 schema construction and serialized `json_schema` routing pass offline. **Native v3 enforcement has not been tested live.** Public capability guidance was reused from BUILDER-ONLY REFERENCE `docs/research/PROBE_1B_CLARIFICATION_EXTERNAL_GUIDANCE_2026-10-02.md`; no documentation/provider request was made here. An unsupported schema, refusal, malformed output or truncation must stop the prospective run. No silent JSON-object fallback or repair request is proposed.

### Offline results and preserved failure

The historical A-I packet is unchanged. It still lacks direction confirmation and uses old descriptive gap strings. Replaying it through v3 fails; no question was inserted. Independently authored fixtures demonstrate valid IDs and flexible questions, not a corrected historical model response.

The final suite exercises real Hermes completion with prepared plain/gzip provider responses, structured validation, meaning checks, unchanged compilation, serialization and canonical reload. It also checks missing direction despite valid IDs, reordered/paraphrased questions, supplied answers not requested again, invented parameters, changed comparisons/times/units/prohibitions, unauthorized search, unsupported substitution, fabricated winner, malformed/truncated/refused output, failed completion with a valid captured packet, persisted usage, unknown charges, capped admission, evidence collisions and denial of live entry before credential access. No local fixture-read count ceiling was added.

Root causes: free-text gap schema versus fixed-ID validator; substantive missing direction; wording-dependent evidence/domain gates. A new prompt's trailing newline caused exact-context denial because Hermes strips it; the canonical authored prompt now has no trailing whitespace. A focused negative check also exposed an overly broad input override in the new clarification seam; exact exchange validation now denies it before fixture dispatch. A final focused check also exposed reply-added restrictions being omitted from the clarification admission check. The shared validator now requires them. Authored partial/unknown/conflict explanations were corrected to name only remaining gaps, and fixture exclusions were aligned with the actual input. These fixture edits are recorded; no historical model response or frozen expectation changed. Compression handling and successful-completion requirements remain intact. The original compression attribution remains unconfirmed because its received headers were not retained.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-contract-repair-01/`. The directory retains before/after source snapshots, raw authored fixtures, actual Hermes completion states, requests, wire/decoded responses, structured decisions, canonical results, red/green checks, caller traces, historical-usage verification and `final-manifest.json`. All 1,057 earlier evidence files remained byte-identical. The final command was:

```sh
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage final-v3-11
```

Exit 0; 41 checks; 9.788 seconds suite wall time, 8.840 CPU seconds, 174,309,376 bytes peak observed RSS. The existing watchdog, CPU limit, observed-memory checks and output ceiling remain. No hard-memory, affinity, production tenancy or OS sandbox claim is made. Repeated stage identities deny overwrites. Future offline checks need a new stage name. Historical actual usage remains three requests, 6,885 input tokens, 1,077 output tokens and USD 0.001063765, with no unresolved reservation.

Compiler SHA-256: `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`. Contract/schema identities and executed adapter/test hashes are in the shared result report and private manifest.

### Prospective clarification loop — approval PENDING

Use a **fresh v3 A-I response** as turn one. Do not reuse the historical failed response or author its missing direction question. Review that the fresh questions cover the frozen six gaps without inventing a strategy. Then supply this explicitly authored test-user reply, verbatim:

> I mean upward continuation only. Define strong as a net return strictly greater than 0.02 over three contiguous completed five-minute bars. Measure the next 30 minutes. Each hour in UTC decide at hh:10 using the close ending hh:05 only if available then. Use the hh:15 entry and hh:45 exit trade references with a 60-second reference window. Use 5 MON quote notional from a 100 MON paper balance, one position, leverage 1, no borrowing or compounding, and cost cases 0, 50 and 100 basis points per side. Research simulation only; no trading permissions. Participants, incentives and persistence remain unknown. Keep the original restrictions; do not add wallet or social inputs, stops or causal claims.

The reply makes its own decisions. It deliberately differs from A-T in lookback, threshold and notional. The independent expected rule is `gt(netret_3(),const_0.02)` with 5 MON, all supplied timing/paper restrictions, unknown mechanism, research mode and empty permissions. This expected structure is evaluator-only; Hermes receives the raw reply, not a prewritten strategy. Require actual successful completion, validation, compilation, canonical reload and explanation consistent with the answers and original restrictions. Save the original input, prior questions, reply, genuine revised packet and explicit before/after field changes. No default substitution is allowed.

Offline-only reply variations are retained verbatim in `clarification-replies.json`, with authored provenance:

| Variation | Supplied meaning / remaining issue | Expected outcome |
|---|---|---|
| Partial | Upward, three bars, strict 0.02 and 30 minutes supplied; schedule, exit and size undecided. | `NEEDS_CLARIFICATION` for timing, exit and sizing only; no strategy. |
| Unknown | All complete-reply values supplied except advances/declines/both remains unknown. | `NEEDS_CLARIFICATION` for direction only; do not choose it. |
| Unsupported | Reply explicitly requests the wallet-label/X/LP rebalance instead, preserving no trading. | `UNSUPPORTED`; preserve the revision and no strategy/substitution. |
| Conflict | Strict `> 0.02` and entry at exact equality are both requested. | `NEEDS_CLARIFICATION` for comparison only; no silently chosen operator. |

These variations are not extra live calls in this proposal. A terminal conversation and saved packets suffice. No chat application is proposed.

Stage issue: the frozen A-I test asks for exit and sizing to reach this compiler's research-position interface. A price-association intake does not necessarily need those choices, and does not require a live mandate. The historical six-gap requirement remains unchanged in this recovery. **Prospective intake-only amendment: PENDING** — ask only for necessary return definition, direction, horizon and observation timing; defer position entry/exit/notional questions until a research-position simulation is requested. This amendment cannot upgrade the failed historical case or broaden the unchanged compiler.

### Proposed live allowance, scores and stop rule — approval PENDING

Propose **five additional inference calls, eight cumulatively**: A-T, A-I, A-N, A-U in frozen order, then one clarification follow-up using that run's passing A-I as turn one. Count every POST, including failures, uncertainty and the follow-up. There is no separate smoke test, judge, repair call, retry or model escalation. The unspent calls in the stopped previous recovery are not permission. This proposal uses all remaining A01 request slots; it leaves no model-request allocation for checkpoint 2 without a separately approved budget amendment.

Retain pinned Hermes commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba`, `openai/gpt-6-luna`, no reasoning, no tools/private context and no fallback. Keep 1,024 response tokens, 90-second request deadline, 48,000 cumulative input and 8,000 cumulative output tokens, USD 0.10 working cap and USD 0.30 absolute maximum. Prior consumption must remain three requests and USD 0.001063765, not reset to the original one-call baseline.

Offline byte-based input upper estimates for the five prepared requests are 13,598 / 12,286 / 14,229 / 12,258 / 14,364, respectively. At the retained prompt/completion price ceilings and 1,024 response tokens, their summed illustrative reservation is **USD 0.0092335**; including prior actual cost, USD 0.010297265. These are estimates, not provider counts or a hard account cap. The follow-up estimate uses an authored prior packet; genuine questions may change its size, so recalculate and reserve the exact request before dispatch. Actual cached-provider charges must settle from reported usage. An unknown charge keeps its reservation and stops further requests.

The sum of pessimistic input estimates is 66,735, exceeding the remaining 41,115 input tokens. Thus five calls cannot be promised under a simultaneous worst-case token reservation. Use existing sequential admission against actual settled counts plus the next conservative bound. Stop if it exceeds 48,000; do not loosen the cap. Five full output reservations total 5,120 tokens; with 1,077 prior outputs, 6,197 stays below 8,000. Cost/token limits can stop the run before all proposed calls complete.

**Before any separately approved dispatch:** persist the revised allowance and both actual journals as the three-request baseline; give the follow-up a distinct attempt identity; verify five admissions and exhaustion/unknown-charge denials offline through the normal gate. The current four-call recovery profile is historical and cannot authorize this sequence. Both live preparation and dispatch are explicitly disabled in the repaired adapter pending that approval/activation. Do not inspect a key merely to prepare approval.

| Independent score | PASS requirement | Failure / unavailable evidence |
|---|---|---|
| Contract validity | Complete strict-schema packet, correct case identity, supported representations. | Format/refusal/truncation failure; retain exact packet/error. |
| Meaning preservation | Raw request, supported fields, restrictions, timing/units/comparison and explanation agree. | Any unrequested/default/substituted meaning fails; no manual repair. |
| Clarification completeness | All necessary gap IDs with one substantive question each; supplied meaning not requested again. | Missing direction or an ID with an irrelevant question fails. Enum coverage alone is insufficient. |
| Unsupported / unavailable evidence | Correct original domain/capabilities and actual evidence gap; no substituted strategy or fabricated winner. | Wrong outcome, erased scope or invented evidence fails. |
| Compilation / canonical reload | Required for A-T and completed follow-up; exact independent expected meaning, stable reload and permissions. | Compiler/round-trip mismatch fails. Otherwise `NOT_APPLICABLE`, not a fictitious compilation pass. |

Review human question meaning and narrative consistency explicitly; deterministic structured scores alone cannot award overall live PASS. A-I/A-N/A-U must contain no strategy. Useful complete clarification, unresolved evidence or unsupported scope can pass their own case. Label incomplete evidence `UNRESOLVED`, rather than assuming a pass. Keep the existing first-unexpected-failure stop rule: retain outputs/usage, stop later calls, and return failed/unresolved cases as observed. No dispatch after a code/contract change without a fresh full offline check. Only a separately reviewed successful complete 1B run plus preserved 1A mechanics can establish checkpoint 1; it still proves no historical research or full Probe A claim.


## 12. Five-call offline preflight — live approval PENDING

Date: 2026-10-02. Identity: `1B-preflight-01`. **OFFLINE PREFLIGHT BLOCKED.** The complete offline suite passed 47/47 checks, exit 0. Accounting and follow-up controls passed. Reliable completion of all five calls under the current input admission bounds remains blocked. This task made no provider requests, inference calls or credential reads. All earlier results remain preserved. Complete 1B, checkpoint 1, Probe A and the Compass gate remain unpassed.

This section records the preflight for section 11. It does not grant inference approval. The prepared sequence is A-T, A-I, A-N, A-U, then `A-I-followup`. The follow-up uses A-I as its model case ID and has its own accounting attempt identity. The profile is `PENDING`, for offline accounting fixtures only. Live preparation and dispatch still raise `LIVE_RECOVERY_NOT_AUTHORIZED` before credential access.

### Accounting and clarification controls

The existing journal reader and reservation path now support this separate five-call profile. Both actual journals are hash-checked and their own settlements counted once. Cumulative prior usage remains **three requests, 6,885 input tokens, 1,077 output tokens and USD 0.001063765**, with no unresolved charge. Neither historical journal was changed. A new process reloads the same profile; a new directory cannot supply a fresh allowance for that profile.

Five sequential fresh processes completed actual Hermes conversations against authored provider fixtures through the normal transport/admission gate. Each dispatched fixture consumed one slot. The sixth attempt was denied before transport at eight cumulative requests. An invalid output consumed its slot; the next attempt was denied by the first-failure stop. Malformed accounting denied dispatch. An unknown-charge fixture retained its USD 0.0018718 reservation across restart and denied the next request. Offline usage remains separate from provider usage.

The follow-up reads the fresh saved A-I request, captured response and successful Hermes final response. Their identities must agree with the journal. It validates the packet again and requires a passing question-meaning review tied to that packet's hash. Missing or mismatched review denies the follow-up. Offline review records are labeled authored fixtures. They cannot approve a future live response. The test used different saved questions from the canned fixture and retained them unchanged in the follow-up. Actual future A-I questions and explicit human review remain mandatory; valid gap IDs alone cannot establish useful clarification.

### Request-size evidence and feasibility

The first four request bodies, prompt, contract and schema are unchanged from section 11. No context shortening was applied. The updated follow-up below uses the fresh authored A-I questions from this preflight, so its size differs from section 11's earlier illustration.

| Attempt | Canonical request bytes | Input admission bound | Reserved USD cost |
|---|---:|---:|---:|
| A-T | 13,086 | 13,598 | 0.0018718 |
| A-I | 11,774 | 12,286 | 0.0017406 |
| A-N | 13,717 | 14,229 | 0.0019349 |
| A-U | 11,746 | 12,258 | 0.0017378 |
| A-I-followup, authored first turn | 13,867 | 14,379 | 0.0019499 |
| Total | 64,190 | 66,750 | 0.0092350 |

The retained admission formula counts the entire canonical request, including JSON Schema, plus 256 bytes per message: two messages add 512. It is a conservative local policy estimate, not a qualified Luna tokenizer or provider schema-processing bound. Cost reservation uses that input bound at USD 0.10/million plus 1,024 output tokens at USD 0.50/million. Routing ceilings do not impose an aggregate provider account cap.

Actual historical counts leave **41,115 input tokens**. The prepared bounds exceed that by **25,635**. Each request contains 3,261 system-text bytes and a 7,736-byte response-format object. Hypothetically deleting only schema title annotations reduces the total bounds to 60,545, still 19,430 over the allowance; this request change was not applied. Case-specific instructions, schema and restrictions were retained.

Recent historical token/byte ratios give an illustrative estimate of about 12,740–12,855 input tokens for these five bodies. Those are local extrapolations from two different historical requests, not provider counts or safe admission bounds. They cannot justify smaller reservations. The genuine future A-I packet changes the follow-up size; recompute its exact body before dispatch.

All five maximum output reservations plus prior usage total 6,197, below 8,000. New cost bounds sum to USD 0.0092350; with prior actual cost, USD 0.010298765 is below both spending caps. These observations do not resolve input feasibility or establish a hard spending guarantee. A separate authored test settled 8,000 input tokens for each of the first four cases. The fifth was correctly denied: 38,885 settled plus its 14,379 bound equals 53,264, above 48,000. It made zero fixture POSTs and consumed no new slot.

### Verification and next decision

```sh
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage full-preflight-05
```

Exit 0; 47/47 checks. A repeated stage is denied; use a fresh stage identity for any later authorized offline rerun. Full test wall time: 41.149 seconds. Parent CPU: 13.687 seconds; parent peak observed RSS: 159,629,312 bytes. Aggregate child CPU and child peak RSS were not measured. Existing deadlines, watchdog, CPU, memory monitoring, input/tree/byte and output controls remain. No hard memory, CPU-affinity or OS sandbox qualification is claimed.

Contract remains `probe-a-1b-output-v3`. Compiler SHA-256 remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`. Hermes pin, lockfile, runtime configuration and `openai/gpt-6-luna` remain unchanged. The adapter and focused tests changed; their executed snapshots and hashes are retained. All 2,776 prior evidence files remain unchanged. Earlier red checks and the corrected syntax error remain visible in the new evidence. No frozen assertion was relaxed.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-preflight-01/`. `final-manifest.json` records commands, exits, identities and controls; `full-preflight-05/` retains complete offline paths; `request-feasibility.json` records exact request hashes and estimates. Previous evidence directories and journals remain historical authority.

**Smallest proposed remedy, approval PENDING:** approve a conditional allowance of five additional calls, eight cumulatively, with unchanged sequential admission. The run may stop before all five if input admission fails. This preserves the limits and stop rule. If completing all five reliably is required before authorization, separately qualify a smaller model/provider-specific safe input bound. The exact pending question is how the pinned Luna route counts messages, strict JSON Schema and framing, including the largest accepted prior A-I packet. No documentation, provider or tokenizer qualification was performed here. Do not replace the bound with an empirical ratio or silently raise limits.

Before any live dispatch, the builder must explicitly approve the chosen remedy and five-call recovery, persist that approval with both prior journals, and review the scoped live activation. Retain 48,000 input/8,000 output tokens, 1,024 output/call, USD 0.10 working/USD 0.30 absolute caps and existing deadlines. Unknown charges, unsupported parameters, truncation, unsuccessful completion, meaning failure or budget denial stop further dispatch. No retry, repair, auxiliary judge or model escalation is approved. Native v3 enforcement, live case accuracy and the clarification loop remain unproved. Stop for builder review.


## 13. Authorized reporting-only-token 1B recovery

Identity `1B-recovery-02`. The builder's latest instruction approves necessary scoped changes, offline checks and five additional live inference calls, eight cumulatively. This prospective amendment supersedes the pending token-feasibility decision in sections 11–12 for this recovery only. Historical protocols, failures, responses and charges remain preserved. No checkpoint 2, Probe B, production or financial authority is granted.

Remove the 48,000 cumulative input, 8,000 cumulative output and 1,024 per-response probe token ceilings. Tokens remain reported from actual provider usage. Requests carry neither max_tokens nor max_completion_tokens. The prompt's 1,024-token wording is removed. The v3 schema, frozen inputs, expected meaning and 1A compiler remain unchanged. Provider-native context/output limits remain unavoidable. No replacement token gate or ratio-based admission is introduced.

Keep five new attempt identities in order: A-T, A-I, A-N, A-U, A-I-followup. The follow-up uses the fresh eligible genuine A-I packet and the existing authored test-user reply. If that first turn is ineligible, retain it and mark the follow-up NOT_RUN. Do not create questions or repair the model's first turn. Each independent interpretation/format failure is retained and does not stop other independent cases. Safety, isolation, transport, unknown-charge and spending failures stop dispatch. There are no retries, automatic repair calls, auxiliary judge calls or model escalation.

Explicit agent semantic review prospectively replaces the human-review pause for this controlled synthetic test only. Record reviewer identity, packet hash, criteria, findings and outcome. IDs alone cannot establish meaningful questions. Require every original and reply-added restriction, exact comparison, threshold, timing, units, sizing and compiler round trip where applicable. The review grants no production or financial authority.

OpenRouter's public model and endpoint metadata were checked without authentication or inference. The same Luna model has a native 128,000 output maximum. Restrict this recovery to the published `openai/flex` endpoint. Keep price ceilings, require_parameters and fallback disabled. The endpoint lists 922,000 prompt and 128,000 completion maxima. Maximum published tier/cache input rate is USD 0.000000125/token and completion rate is USD 0.000000375/token. Reserve USD 0.163250000 per dispatched request from those native maxima, without sending them as request caps. This avoids a tokenizer qualification dependency. Unknown charges retain the full reservation and stop further dispatch. Counts alone do not deny settlement.

The USD 0.10 working allowance cannot admit that native reservation. Under the builder's explicit backup authorization, activate USD 0.30 before dispatch and retain USD 0.30 as the absolute maximum. Count prior actual spending and outstanding reservations. This is local reservation/accounting, not a provider-enforced account cap. Both historical journals remain included exactly once: three requests, 6,885 prompt and 1,077 completion tokens, USD 0.001063765, no unresolved charge. The provider route is narrower, while the model and pinned Hermes environment are unchanged.

The amended complete offline suite passed 48/48 checks, exit 0. It includes the normal gate, actual fresh processes, five additions/eight cumulative slots, reporting-only high token usage, spending denial, unknown-charge retention, malformed accounting denial, distinct follow-up identity, saved first-turn review, independent-case continuation, packet restrictions and compiler reload. Red/green evidence for removal of token gates is retained. Existing tests were prospectively changed only where this approval changes token, review and independent-failure policy. Earlier suites and source snapshots remain preserved.

Command: `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage full-amendment`.

Compiler SHA-256 remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`. Contract remains `probe-a-1b-output-v3`, with unchanged schema and a recorded instruction revision. Hermes remains pinned to `54bc5e509c985f37265c3d416bd2c64b10fc77ba`; model remains `openai/gpt-6-luna`. Empty tools, isolated packet/context construction, no private context/memory/soul/review/compression/fallback/recovery, one Hermes attempt, zero SDK/transport retries, single-threaded calls, deadline and resource controls remain. A selected-route error is a transport stop, not permission to switch providers.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-recovery-02/`. Retain public model/endpoint metadata, prospective amendment, offline red/green/full records, executed source snapshots, prior preservation inventory and a source-bound persisted authorization/journal before dispatch. Actual live responses, completion states, agent semantic reviews and outcomes follow in the result record. No live result is presumed by this approval or offline pass.


### Observed recovery outcome and terminal stop

`1B-recovery-02`: **REJECT — HERMES INTERPRETATION**. All four independent live cases completed Hermes with one inference POST each. A-T failed strict parsing because two objects were returned. A-I returned clarification without strategy/defaults, but omitted direction confirmation and failed scope/evidence checks. A-N recognized missing historical data and preserved the finite search, but returned two objects plus markup. A-U faithfully preserved the unsupported wallet-label/X/LP request and passed agent meaning review, yet failed the fixed evidence-gap coverage check. No original response was repaired. The unchanged check may require historical gaps too early for an already unsupported capability; this limitation is recorded without changing the result.

A-I-followup is NOT_RUN because the fresh first turn is ineligible. No authored or historical packet replaced it, and the test-user reply was not sent. There were no retries, repair calls, model escalation, historical-data requests or financial actions. Complete 1B and checkpoint 1 remain unpassed. Earlier genuine A-T compilation and 1A recovery remain preserved and do not repair this batch. Probe A and the Compass gate remain unpassed.

New actual provider usage: four requests, 9,474 prompt/2,194 completion tokens, USD 0.0007815025. Cumulative actual usage: seven requests, 16,359 prompt/3,271 completion tokens, USD 0.0018452675. All charges settled; no unresolved reservation remains. Two public unauthenticated metadata requests were separate from inference. The USD 0.30 backup allowance was persisted before dispatch; actual spending stayed below the original USD 0.10. No provider-enforced account cap was established.

Commands and exits, original packets, actual Hermes completion, deterministic failures, separate agent reviews and resource usage are retained in `recovery-manifest.json` and case directories under the private evidence path above. The complete amended suite passed 48/48 before dispatch. No code changed after that run. All 3,666 earlier evidence files, both historical usage journals, compiler, schema, Hermes pin, lockfile and original runtime configuration remain unchanged. The model and frozen inputs remain unchanged; the instruction revision removes only the output-token instruction. A terminal dispatch-stop record prevents further calls from this run. Unspent allowance is not retry permission. Stop for controller review.


## 14. Prospective 1B meaning-contract recovery

Identity: `1B-recovery-03`. APPROVED by the builder's scoped recovery instruction. This amendment applies to interpretation only. Earlier failures and protocols remain visible. No historical investigation, deployment or financial authority is added.

Contract `probe-a-1b-meaning-v4` separates model interpretation from trusted application facts. The model extracts domain, action, required inputs, direction and its provenance, supplied signal/timing/sizing, restrictions and uncertainty. The application attaches case identity, requested market `MARKET_A`, distinct dataset binding `SYNTHETIC_FIXTURE/MARKET_A`, pinned identities, known historical blockers and an already-approved bounded search. Assembly must never insert a user trading decision. Numeric strings and separate units remain required by the unchanged compiler.

Unknown direction is explicit; upward capability does not select upward meaning. Tested application questions derive from unknown or conflicting fields. At association intake A-I needs strong-move definition, direction, response horizon and observation timing. Simulation entry/exit and sizing are requested only when preparing that simulation, including the clarification follow-up. This prospectively removes the stage-inappropriate unconditional sizing requirement, without changing the historical failed verdict. The complete authored reply supplies all simulation decisions itself. Partial replies remain incomplete; conflicts require confirmation; unavailable operations remain unsupported.

Outcome requirements: COMPILED retains supplied supported rules through the unchanged compiler and canonical reload. NEEDS_CLARIFICATION withholds a strategy and requests necessary unknown meaning without defaults. UNRESOLVED retains the finite declared research scope and exposes unavailable evidence without a winner. UNSUPPORTED preserves LP/wallet-label/X meaning and explains missing capability without substitution. Historical qualification remains unresolved for every case, but historical-price fields are not required from the model for a capability refusal. Evaluation measures each outcome separately and includes agent semantic review of explanation and restrictions.

One shared machine-readable schema supplies both request generation and strict local validation. The full provider content must be exactly one JSON object, with successful Hermes completion, one API call and unchanged final content. No object selection, repair, response-healing or retry is permitted. Previous strict-schema requests produced multiple objects in the actual provider packet. Current official OpenRouter documentation describes `json_schema` and `require_parameters`; these request support, not evidence that this route enforced conformance. Local validation remains mandatory. Plain/compressed fixtures prove integration, not actual model accuracy.

Two read-only reviewers assess contract/meaning and integration/verification. Resolve concrete findings before dispatch. Freeze the contract and instructions before the first batch; keep them unchanged between batches. Each batch contains original A-T/A-I/A-N/A-U and one eligible fresh A-I clarification. Use the unchanged authored user reply. Agent semantic review replaces the human pause for this controlled test only and grants no financial authority.

Approval: at most ten new inference calls across two fixed GPT batches, seventeen cumulatively if all slots are used. Baseline journals verify seven settled requests, 16,359 input/3,271 output tokens and USD 0.0018452675. Keep three journals included exactly once. Token counts are reporting data; no probe token caps or byte-derived admission gates are allowed. Native provider limits remain. Reserve conservative provider-native cost before each dispatch, persist settlement or retain an unknown charge. USD 0.10 is the working allowance; activate the already-approved USD 0.30 backup because Luna's native reservation is USD 0.16325. Cumulative spending/reservations must stay below USD 0.30. No provider-enforced account cap is claimed.

The first batch uses pinned Hermes and `openai/gpt-6-luna` at OpenRouter's `openai/flex` route, reasoning none, empty tools, disabled context/memory/review/compression/fallback/recovery, one API attempt, zero SDK/transport retries and existing safeguards. Public qualification of stronger GPT-6 Sol lists a USD 3.265 native reservation, beyond the absolute allowance; do not dispatch that route. No stronger comparison may run without verified capability, affordability and a fixed recorded configuration. Independent interpretation failures do not stop other cases; spending, unknown-charge, isolation and transport-safety failures do. If A-I is ineligible, its follow-up is NOT_RUN.

PASS for 1B requires all four outcomes and the clarification follow-up under one frozen candidate, successful required compilation/reload and agent review. It proves bounded interpretation and compiler compatibility only. Checkpoint 2, complete Probe A and the Compass gate remain unpassed. Stop after the observed result report.

### Observed meaning-contract recovery and terminal stop

`1B-recovery-03`: **REJECT — HERMES INTERPRETATION**. Two independent reviews passed after known-value, follow-up stage, conflicting comparison and fixture-review admission corrections. Offline runs passed 26/26 before Luna and 27/27 after the explicit Pro route extension. The v4 contract, schema, instructions and input context stayed unchanged across batches; paired actual requests differ only in model. The compiler remained unchanged.

Luna and Luna Pro each failed A-T (multiple objects and needless direction confirmation) and A-I (partial nullable signal accepted by schema but denied by the frozen intake evaluator). Both passed A-N with missing evidence/no strategy and A-U with preserved LP/wallet-label/X refusal/no substitution. Every actual Hermes conversation completed with one POST. Neither fresh A-I was eligible; both follow-ups are NOT_RUN. No packet was repaired. No native schema-conformance claim is supported by strict:true or advertised support. Cause of the provider's invalid multi-object content remains unresolved.

The explicitly qualified second model was `openai/gpt-6-luna-pro`, the same underlying model in its advertised deeper pro mode. Official documentation describes direct pro alias selection independently of effort. Reasoning effort remained none; the route remained `openai/flex`. Native reservation USD 0.16325 fits the approved backup. Higher-end Sol required USD 3.265 and was not dispatched. Both batches have separate configuration/source evidence and share the same cumulative journal.

New usage: eight calls, 31,057 prompt/4,006 completion tokens, USD 0.0018182575. Cumulative usage: fifteen calls, 47,416 prompt/7,277 completion tokens, USD 0.0036635250. All settled; no unresolved reservation. Six public unauthenticated qualification requests were separate from inference. No token ceiling, retry, repair call, unrecorded inference, historical collection or financial action was added.

Measured live case wall time totals 149.739 seconds; aggregate process CPU 10.231 seconds; maximum observed RSS 179,798,016 bytes. Existing safeguards remain; no hard memory/affinity/OS sandbox claim. All 4,389 prior evidence files remain unchanged. The compiler hash remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`; contract hash remains `95ba80752d3e0d8b2d8043f76c354baabf0b4cb6bc94b45d4054d31795913acb`.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-recovery-03/recovery-manifest.json`. Original packets, completion states, separate agent reviews, offline red/green checks, request/cost journal, commands/exits, source snapshots and preserved earlier identities are retained. Sanitized detail is in the shared result report.

Checkpoint 1, full Probe A and the Compass gate remain unpassed. Historical checkpoint 2 was not started; A01/A02 remain blockers. The terminal stop closes this recovery. Controller review is next. Further nullable-signal contract/evaluator repair or provider qualification needs a separate scoped task and fresh inference authorization; do not run a third batch or reuse unused calls automatically.

## 15. Luna versus GPT-6.1 Sol comparison amendment

Identity `1B-comparison-04`. The builder authorizes at most ten new inference requests: four original cases and one eligible clarification follow-up per model, twenty-five cumulative if all requests become admissible. Models are exactly `openai/gpt-6-luna` and `openai/gpt-6.1-sol` with supported low reasoning. No Luna Pro substitute, retries, repair calls or other model escalation. Approval remains subject to spending admission within the unchanged cumulative USD 0.30 maximum. The USD 0.10 working allowance and authorized backup policy remain. Preserve all prior charges and unknown reservations.

Before comparison, contract v5 resolves the reproduced nullable-signal mismatch. First-turn intuition can contain no signal or a parameterless unknown signal object. NET_RETURN in that object is only a proposed family label requiring definition confirmation; it is never a user-selected measurement or compiled rule. Numeric lookback, threshold, units, horizon, strict comparison, timing and sizing defaults remain denied. The definition question includes strict/inclusive comparison; do not ask a second equality-conflict question for an entirely unknown definition. A genuine conflict with otherwise known values still needs separate confirmation. Raw model content and every historical failed verdict remain unchanged.

Both read-only reviewers passed this focused repair. Two red checks reproduce the earlier denial. The final unchanged-source suite passed 31/31, exit 0, through actual offline Hermes completion, validation, compilation and canonical reload where applicable. Captured Luna/Pro model content is replayed unchanged inside explicitly labeled fixtures with synthetic id/usage envelopes. Those are offline integration checks, not new model inference or retroactive live passes. Intermediate green evidence has a source-identity limitation explicitly recorded; final `full-frozen-03` is authoritative.

Freeze `probe-a-1b-meaning-v5`, shared instructions, schema, original user inputs, authored clarification reply, evaluator and unchanged compiler before any paid dispatch. Keep each model's conversation separate. Never include the other model's answers. A follow-up requires that model's own fresh passing A-I plus agent semantic review. Each model passes only when all four cases and its own follow-up pass. Do not combine partial outcomes. This comparison measures these cases, not general superiority.

New stop policy: a format or transport failure stops the affected route. The other route may continue only if independently qualified and spending is reconciled. Unknown charges retain reservations and prevent unreconciled dispatch. Shared isolation, credential or spending failures stop calls. Any prospective route implementation must enforce this policy before inference; the closed historical adapter is not newly enabled by this amendment.

### Current qualification and cost blocker

Three unauthenticated public metadata GETs verified both exact model listings and endpoint constraints. Context7 was resolved first to `/openrouterteam/docs`, then queried for reasoning, structured output and routing. Model metadata lists mandatory reasoning and supported `low` for Sol; optional reasoning and `none` for Luna. Proposed settings are Sol `enabled=true, effort=low`, Luna `enabled=false, effort=none`. Both use a fixed qualified OpenAI route, strict json_schema, require_parameters, empty tools, no fallback/retry or probe token caps. The live Sol SDK wire and actual effort behavior remain untested because cost admission failed. Advertised structured-output support does not prove native conformance.

The cheapest fully bounded captured endpoint is `openai/flex`. Both models list 922,000 native prompt and 128,000 native completion maxima. Proposed routing price ceilings differ: Luna USD 0.10/0.50 per million prompt/completion; Sol USD 2.00/7.50. Those are price ceilings, not aggregate spending caps. Cost reservation additionally covers the maximum listed cache-write rate.

| Model | Maximum prompt/cache rate per million | Maximum completion rate per million | Native cost reservation per call | Sum of five native bounds |
|---|---:|---:|---:|---:|
| GPT-6 Luna | USD 0.125 | USD 0.375 | USD 0.16325 | USD 0.81625 |
| GPT-6.1 Sol | USD 2.50 | USD 7.50 | USD 3.265 | USD 16.325 |

Ten native bounds sum to USD 17.14125, or USD 17.144913525 including settled history. This is a conservative upper bound, not a predicted actual bill. Sequential admission releases settled reservations; nevertheless one Sol reservation already exceeds the available USD 0.296336475. Even its base flex maximum output charge is USD 0.64 before input. No reliable expected bill for Sol low was qualified. No token or byte gate was introduced to lower this bound.

Four unchanged journals independently reconcile fifteen settled inference requests, 47,416 prompt/7,277 completion tokens and USD 0.003663525. Unknown reservations: none. **No new inference, charge or credential access occurred.** Both requested models have separate `NOT_RUN — COST_PREFLIGHT_BLOCKED` verdicts; format, meaning, clarification, compiler, reload and latency results are unavailable. No new request allowance or live adapter authorization was activated. The earlier executed rejection, 1A pass and unpassed larger gates remain.

Command: `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage full-frozen-03`. Final wall time 14.760 seconds, parent CPU 12.729 seconds, peak observed RSS 142,868,480 bytes. Existing resource safeguards remain; no new hard isolation claim. All 5,803 earlier evidence files remain unchanged.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-comparison-04/`. `cost-preflight.json` retains public pricing/effort identities, each model's settings and separate unrun dimensions; `repair-manifest.json` retains command, hashes, reviews and checks. The compiler hash remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`. The new contract hash is `15a3258907caa5117df7a02e21d116a55ee4dd688e43c8056903fbf9a909ac48`.

Stop for builder review of cost-control feasibility. A separately approved monetary reservation policy that can enforce USD 0.30 without token caps, or verified same-model native constraints that fit it, is needed before dispatch. Do not weaken admission, increase spending, substitute models or run only Luna to bypass the blocked comparison. Historical checkpoint 2, Probe B and production remain outside scope.


## 16. Prepared-request cost qualification, 1B-cost-05

The builder authorized correcting cost qualification without raising USD 0.30, adding token/byte limits, changing models or billing settings. This amendment preserves Section 15's ten-call comparison authorization subject to safe admission. None of those ten slots was used. No live allowance, credential or route was activated. The closed historical adapter remains closed.

`OFFLINE COST CHECKS PASS — LIVE COMPARISON BLOCKED`.

The old reservation used the model's entire 922,000-token input capacity. That is not the prepared input. The new read-only `Accounting.qualify_prepared` measures the complete prepared JSON, including messages, schema and wire wrappers. It reports those measurements separately from model capacity. It does not write reservations or authorize dispatch. The frozen legacy reservation remains for historical and isolated offline profiles; it is not a qualified replacement live admission path.

Prepared requests measure 8,125–10,168 UTF-8 bytes. The local estimate, ceil(bytes/4), is 2,032–2,542 input tokens. This estimate has no admission authority. Exact GPT encoding and upstream schema/chat framing were not qualified; total financial exposure remains explicitly unknown. No tokenizer installation or qualification project was started. Sol packets are proposed model/settings mappings from the actual offline Luna wire, not proof of Sol SDK delivery. The follow-up measurement uses an authored offline first-turn fixture, never a replacement live first turn.

Two fresh unauthenticated endpoint GETs confirm `openai/flex` rates and the native 128,000-token completion maximum. At base prices, native output exposure is USD 0.032 for Luna and USD 0.64 for Sol. Across published tiers it is USD 0.048 and USD 0.96. Input/cache charges are additional. Billable reasoning is output; low effort does not impose a numerical ceiling. Native tools/plugins/images are excluded from the text-only packet. A reviewer found that the exclusion claim lacked a message-type guard; its failing fixture and repaired string-only guard are retained.

An illustrative calculation using each local input estimate plus 1,000 total billable output tokens sums to USD 0.0019676875 for Luna and USD 0.03935375 for Sol, USD 0.0413214375 together. This is neither a prediction nor a financial bound. It does not justify dispatch. No request's full input capacity or five simultaneous worst-case reservations is required by the new analysis. Existing sequential settlement releases each reservation before the next request; unknown charges retain reservations and stop admission.

Context7 was resolved to `/openrouterteam/docs` before three documentation queries. Current official [limits documentation](https://openrouter.ai/docs/api_reference/limits) uses actual input plus an internally capped completion estimate for its credit hold, then settles actual charges. It does not establish a cutoff for this run's USD 0.30 allowance. [Workspace budgets](https://openrouter.ai/docs/guides/features/workspaces/workspace-budgets) explicitly let dispatched requests complete and can overshoot. Existing key preflight had no per-key cap. No documented per-request monetary cutoff was qualified for this route. No account/key/billing setting was changed. A direct `.md` archive fetch returned HTTP 403; current official web pages and Context7 supplied the inspected documentation.

### Verification and retained boundary

Seven focused checks passed through existing accounting persistence: prepared request versus capacity, sequential reservation/settlement, restart, retained unknown charge, malformed journal denial, measurement without an input gate, preserved actual journal and text-only cost scope. Accounting fixtures retain their isolated seven-call historical profile; they do not reset or replace the fifteen actual requests. Four actual journals independently reconcile fifteen unique settled responses, 47,416 prompt/7,277 completion tokens and USD 0.003663525. Unknown reservations are empty. Remaining absolute allowance is USD 0.296336475. New inference and charge are zero.

The complete Hermes suite passed 31/31 after the final guard. Plain/compressed completion, full-response validation, v5 meaning checks, unchanged compiler, canonical reload and clarification fixtures remain working offline. Both independent read-only reviewers passed the final changes; the prior v5 meaning reviews remain applicable. Fixtures do not establish live accuracy or native schema enforcement. The compiler and contract source hashes remain unchanged from Section 15.

```sh
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/test_cost_1b.py --stage final-cost-05
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage final-meaning-02
```

Both exit 0. Cost checks: 0.425 seconds wall, observed peak RSS 44,548,096 bytes. Hermes checks: 14.894 seconds wall, parent CPU 13.399 seconds, observed peak RSS 170,229,760 bytes. Existing resource controls remain; no hard memory or OS isolation claim was added.

### Stop and controller decision

Both models' four cases and clarification follow-up are `NOT_RUN — COST_PREFLIGHT_BLOCKED`. Format, meaning, clarification, compilation, reload and live latency are unavailable. Neither model passes 1B. Checkpoint 1, Probe A and the Compass gate remain unpassed. Earlier failures and successful component results remain unchanged.

The concrete controller decision is to close this uncapped comparison as financially blocked under the unchanged USD 0.30 ceiling. One Sol response alone needs at least USD 0.643663525 cumulative exposure including history, before input: USD 0.343663525 above the ceiling. Covering its higher-tier output alone would need USD 0.963663525 cumulative exposure, again before input. These are exposure figures, not proposed charges or newly approved allowances. Any future instruction to resume must explicitly change the conflicting financial policy or supply a qualified existing monetary cutoff; ordinary live permission alone cannot fix admission. No second interpretation repair batch or historical checkpoint starts automatically.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-cost-05/`. `prepared-cost-qualification.json`, `history-reconciliation.json`, `documentation-findings.json`, final reviewer records, `manifest.json` and `dispatch-stop.json` retain the measurements, sources, commands, tests, limitations and stop. All earlier evidence remains preserved.

## 17. Approved generated-output allowance, 1B-capped-06

The latest builder instruction prospectively approves **4,096 total generated tokens per inference response**, including billable reasoning and visible output. This supersedes the earlier prohibition on a probe response-token cap. Cumulative input/output quotas remain removed; no byte-based usage gate is added. Native provider constraints remain. The output setting does not change the user's rules, contract v5, evaluator, original four inputs, authored clarification reply or unchanged 1A compiler.

The existing comparison authorization remains at most ten new calls, four cases plus one eligible fresh A-I clarification follow-up per exact model: `openai/gpt-6-luna` with disabled/none reasoning and `openai/gpt-6.1-sol` with enabled/low reasoning. Twenty-five cumulative calls would result if all ten become admissible. Keep conversations separate, agent semantic review, empty tools, strict schema, required-parameter routing and no fallback. No retries, repair calls, substitution or additional experiment is approved. USD 0.10 working allowance and USD 0.30 cumulative absolute maximum remain; previously authorized backup activation requires a recorded reason and persisted amendment before dispatch.

The adapter transmits `max_tokens=4096`. Current official documentation and public endpoint metadata support that parameter; authored fixtures through actual Hermes SDK execution confirm delivery for both selected models with their correct reasoning settings. `require_parameters=true` remains. Output and reasoning share the allowance. `length` means **OUTPUT_TRUNCATION — interpretation unmeasured**, not a failed assessment of the user's meaning. Retain that response and usage, stop the affected route, and do not increase the allowance or retry. Invalid JSON/schema or transport failure also stops the affected route. Shared safety, spending or unknown-charge failures stop both routes.

### Observed offline verification and stop

`OFFLINE BOUNDARY PASS — LIVE COMPARISON BLOCKED`.

Twelve focused boundary checks and the existing 31 interpretation checks pass against the final candidate. Both read-only reviewers pass. The integration reviewer found an unreachable length classification behind an earlier stop guard; a new red regression reproduced it. Moving that classification into the shared handoff resolved the defect without changing meaning checks. Complete fixtures still reach validation, compilation, serialization and canonical reload; capped/nonfinal or unsuccessful conversations cannot pass.

The authored fixture usage envelope now records 1,000 rather than 10,000 completion tokens, consistent with the approved response cap. Fixture content and frozen meaning assertions are unchanged. No historical provider response or charge changed. Offline fixtures do not establish live accuracy or native schema enforcement.

```sh
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/test_cost_1b.py --stage final-boundary-07
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage final-meaning-02
```

Both exit 0. Focused checks take 7.467 seconds with peak observed RSS 153,698,304 bytes. Interpretation checks take 24.056 seconds with 20.152 parent CPU seconds and peak observed RSS 156,418,048 bytes. Runtime watchdog, CPU limit, observed memory guard and output controls remain. No hard memory, affinity or OS-isolation claim is added. The old `RESOURCE_LIMIT` audit failure came from passing an oversized evidence inventory to the strategy JSON parser. Its reproduced denial is correct; standard-library JSON handles that trusted inventory. No guard was removed.

Three unauthenticated public endpoint/catalog GETs confirm current selected models, prices and capability metadata. Context7 resolution preceded documentation queries. Maximum captured completion rates bound output exposure at USD 0.001536 for Luna and USD 0.03072 for Sol. The previous uncapped output-only blocker is resolved. Maximum captured prompt/cache rates remain USD 0.125 and USD 2.50 per million respectively; total input exposure remains unqualified.

Prepared request measurements include messages, schema and wire wrappers: 8,143–10,186 UTF-8 bytes, local ceil(bytes/4) estimates 2,036–2,547 tokens. These are estimates, not financial bounds or quotas. Both A-T wires are actual authored Hermes SDK requests; other Sol measurements are labeled proposed mappings. The offline follow-up uses an authored first turn and cannot replace that model's fresh live clarification.

No provider-qualified full-input token count or framing upper bound was established for the existing OpenRouter/OpenAI Flex chat/schema route. The native OpenAI Responses counting endpoint was not qualified for this route/authentication. The read-only qualification therefore denies dispatch and creates no reservation. The closed historical live admission path remains frozen; no new live profile or authorization file was activated. Sequential settlement, restart persistence, unknown-charge retention, malformed-record denial and insufficient-money denial remain verified through isolated existing accounting fixtures.

Four unchanged actual journals reconcile fifteen requests, 47,416 prompt/7,277 completion tokens and USD 0.003663525. No unresolved reservation, new inference or credential access. Remaining absolute allowance: USD 0.296336475. All ten new slots remain unused. Both models' five live cases are **NOT_RUN — COST_PREFLIGHT_BLOCKED**; all live assessment dimensions and latency are unavailable. Neither model passes 1B; checkpoint 1, Probe A and the Compass gate remain unpassed.

The one concrete remedy is a provider-qualified complete-input count or upper bound for these exact saved packets on the existing route. No increased allowance or input quota is proposed. For the first Sol request, USD 0.265616475 remains for input/cache after maximum capped output: enough for 106,246 complete input tokens at the maximum captured rate. This affordability arithmetic does not qualify a count or impose a token gate. Stop before inference under the builder's financial-bound exception; preserve ordinary live approval once admission is genuinely qualified.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-capped-06/`. Retain final commands/results, both reviews, prepared request qualifications, source identities, history, dispatch stop and every earlier red/green result. Compiler SHA remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`; v5 contract SHA remains `15a3258907caa5117df7a02e21d116a55ee4dd688e43c8056903fbf9a909ac48`. All 6,768 previous evidence files remain unchanged. Historical checkpoint 2, Probe B, production work and Git publication remain outside scope.

## 18. Working-budget comparison authorization, 1B-comparison-07

The latest builder instruction explicitly changes USD 0.30 from a guaranteed absolute ceiling to a **cumulative working budget**. The builder accepts that a dispatched request may exceed its conservative estimate. This resolves Section 17's financial-policy blocker prospectively; it does not qualify the earlier input estimate or erase earlier stops. This is not permission to spend the reported USD 2 balance.

Keep `max_tokens=4096` for total reasoning plus visible output. Ten new comparison calls remain authorized: four original cases plus an eligible own fresh A-I follow-up for each exact model, Luna none and GPT-6.1 Sol low. Prior fifteen requests and USD 0.003663525 remain included, twenty-five cumulative if every slot is used. Keep v5, frozen inputs/reply, evaluator, compiler, empty tools, strict schema, fixed OpenAI Flex routing, one API attempt, zero SDK retries and context exclusions unchanged.

Use the existing persistence code with a distinct working-budget profile. Before dispatch, reserve a conservative request-specific estimate: complete prepared UTF-8 byte count treated as one token per byte, plus 2,048 estimated framing tokens, priced at maximum captured prompt/cache rates, plus all 4,096 output tokens at maximum captured completion rates. This is an estimate, not a verified input bound, financial guarantee or input-size restriction. Cumulative input/output quotas stay removed. Save exact request, pricing source and estimate.

Run sequentially. Settle the actual provider charge before admitting another request, including a known charge exceeding its estimate. Unknown charges retain reservations and stop both routes. Stop further dispatch when settled cumulative spending reaches USD 0.30; also deny a request whose conservative estimate cannot fit the remaining working budget. No automatic retry, repair call, substitution, extra judge or additional experiment. A provider-reported response-cap violation is retained with its known charge and stops both routes.

Format, truncation or unsuccessful Hermes completion stops the affected route. The other model can continue only with settled spending and independently qualified settings. Setup, credential, isolation and shared safety failures stop both. Each model's follow-up requires its own saved passing first turn and explicit agent semantic review. A failed or ineligible first turn cannot be replaced. Interpretation failures are preserved; do not change the frozen contract between cases or models.

Record focused offline checks and independent reviews before activation, then dispatch under this existing approval without another routine permission pause. BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/evidence/A01/1B-comparison-07/`. This authorization adds no historical investigation, production or financial-execution scope. Stop after the observed comparison report.

### Observed working-budget comparison and terminal stop

**REJECT — COMPLETE 1B UNPASSED**. The final frozen candidate passes 16/16 focused offline checks and 31/31 interpretation checks, with both read-only reviews passed. Review exposed inconsistent saved stop flags, setup/failed-Hermes safety classification and an unhandled provider-reported response-cap violation. Retained red checks reproduce them. The corrected path settles known charges, records accurate stops and denies further dispatch on shared safety or cap violations. Only final frozen records qualify activation; intermediate passes do not qualify later source revisions.

The unchanged v5 contract, schema, user inputs, authored reply, evaluator and compiler were frozen across both models. Two fresh public endpoint GETs confirm selected OpenAI Flex pricing and parameter support. Luna sends disabled/none reasoning; Sol sends enabled/low. Both actual wires include `max_tokens=4096`, strict JSON Schema, required-parameter routing, empty tools and no fallback. All six attempted Hermes conversations complete with one POST and finish reason `stop`. No output is truncated, retried, selected from multiple objects or repaired.

| Model | A-T | A-I | A-N | A-U | Own clarification | Model verdict |
|---|---|---|---|---|---|---|
| openai/gpt-6-luna | FAIL — multiple objects/extra text | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | REJECT; format route stop |
| openai/gpt-6.1-sol | PASS; compile/reload | PASS; useful questions/no strategy | FAIL — frozen unresolved-field guard | PASS; preserved unsupported request | PASS; compile/reload | REJECT; four of five pass |

Sol A-T preserves the complete supported thesis and matches the verified 1A canonical control. Sol A-I retains UNKNOWN direction and parameters; application-generated questions are reviewed for necessary meaning, not IDs alone. Its own saved passing first turn and the authored user reply produce the follow-up. It preserves original and reply-added restrictions, supplied upward direction, strict `>0.02`, three contiguous five-minute bars, 30-minute horizon, all declared times and 5 MON notional through compilation and reload. Reviews are agent review, not human approval or financial authority.

Sol A-N is schema-valid and useful in meaning: no signal, winner or fabricated history. It preserves the bounded research request and copies the user-adopted timing and sizing. The frozen assembly guard requires both fields null for `UNRESOLVED`, and rejects the packet as `INVENTED_STRATEGY`. The copied values are declared research configuration, not invented decisions. Preserve this failed handoff and its contract/assembly ambiguity; do not claim that the model fabricated a winner or retroactively relax the guard. Luna's invalid whole response is retained, including the visible threshold discrepancy `1` versus supplied dimensionless `0.01`; no valid selected packet or compilation is claimed.

Conservative five-call estimates were Luna USD 0.014712375 and Sol USD 0.294235, USD 0.308947375 together. They are request estimates, not predicted charges or simultaneous reservations. Each of the six actual charges settled before the next call. New usage: 10,552 prompt/2,360 completion tokens, including 364 reported reasoning tokens, **USD 0.0136746375**. Cumulative: twenty-one requests, 57,968 prompt/9,637 completion tokens, **USD 0.0173381625**. Unknown charges and unresolved reservations: none. Four unused slots are on the stopped Luna route and do not authorize retries.

Exact offline commands:

```sh
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/test_cost_1b.py --stage working-green-03
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage working-final-03
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py working-prepare
```

All exit 0. Live command: `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py working-case --batch MODEL_BATCH --case CASE_ID`, with `luna/A-T`, then `sol/A-T`, `sol/A-I`, `sol/A-N`, `sol/A-U`, `sol/A-I-followup` sequentially. Luna exits 2 for the route stop; Sol exits 0 for each case, including the retained independent A-N FAIL. The shared result report retains every expanded command, actual charge and case latency. Live case wall time totals 70.160 seconds; aggregate parent CPU 10.586 seconds; maximum observed RSS 184,156,160 bytes. Existing resource controls remain; no hard memory/affinity or production-isolation claim is added.

Compiler SHA remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`; v5 SHA remains `15a3258907caa5117df7a02e21d116a55ee4dd688e43c8056903fbf9a909ac48`. A-T canonical control SHA is `75fdc936cae0b43d21e17b266e3eec4582e3fe782a57f86a8a379dda73af091b`; the supplied clarification rule SHA is `a38e7cf1a1b566b76cbba4e6e7fcd31804f41d2d6709102c8b7e58044619aa64`. Hermes pin, lockfile and isolated configuration remain unchanged. All 7,539 preceding evidence files are preserved.

Next controller decision: review the A-N boundary between preserved declared research configuration and a selected strategy. Any repair or new inference must be prospective and separately scoped; this failed comparison is not replaced. Neither model passes complete 1B, checkpoint 1, Probe A or the Compass gate. Successful components prove bounded interpretation and compiler compatibility only. No general model-superiority, historical-research, profitability or persistent-execution claim follows. Stop after the report; no automatic repair batch, historical checkpoint 2, Probe B or production work.

## 19. Offline no-thesis contract correction, 1B-no-thesis-repair-08

The builder approves a scoped offline repair only. Live inference approval is **PENDING**. Contract `probe-a-1b-meaning-v6` prospectively separates user-adopted research configuration from a selected strategy. Section 18's v5 failure and all historical results remain unchanged.

The frozen A-N request explicitly adopts the plan's decision/trade-reference timing, sizing and cost cases. The application records that adoption from trusted context. For `UNRESOLVED` declared research, signal remains null and direction remains unknown. Model timing and sizing may be null or exact copies of the adopted values. The application retains the adopted configuration in a separate research field either way. Changed or unapproved settings fail. Unsupported and clarification outcomes retain their existing restrictions. No selected strategy, winner, simulation result, paper readiness or execution authority follows from copied settings.

The shared contract defines this rule for instructions, schema description and contextual validation. Structural schema conformance alone does not establish trusted-context equality or truthful prose. Whole-response validation and explicit agent semantic review remain required. Ordinary interpretation can be explained; consequential unknowns remain unknown. This amendment adds no strategy family or hypothesis-generation engine.

Verify the unchanged saved Sol A-N content through an offline provider fixture and actual Hermes completion. Retain the failing regression, new tests and replay evidence separately under BUILDER-ONLY REFERENCE `prototypes/edge-os/probe-a/evidence/A01/1B-no-thesis-repair-08/`. Preserve the compiler, pinned runtime, model settings, resource controls, spending policy and historical journals. Run no inference and read no credentials.

A proposed next live task is one focused Sol A-N recheck under v6, with its own new identity and one additional request, twenty-two cumulative if executed. Approval is **PENDING**. Preserve historical twenty-one requests and USD 0.0173381625; settle and reserve through the existing working-budget policy. Keep Sol low reasoning, 4,096 total generated tokens, empty tools, fixed routing, no fallback and no retries. Existing stopped-route slots are not permission. This single recheck would test the amended no-thesis boundary; it cannot retroactively replace v5's failure or alone pass complete 1B under one candidate configuration.


### Observed offline repair and stop

**OFFLINE NO-THESIS REPAIR PASS — LIVE 1B UNPROVED**. Contract v6, final 35/35 interpretation checks and 16/16 boundary checks pass, exit 0. Both independent read-only reviewers pass. The original saved Sol A-N failure is reproduced first with exit 1; the unchanged complete content then passes plain and compressed actual Hermes fixture conversations under the corrected contract. A separate failing provenance assertion leads to accurate captured-replay labels. No live interpretation or paid request occurred.

Approved timing/sizing remain separate research configuration whether the model copies them exactly or leaves them empty. Changed or unapproved settings, invented signal/direction, unsupported scope, lost restrictions and structured winner/readiness/authority claims fail. Existing supported thesis, intuition, unsupported request, clarification, compiler/canonical reload, transport, format, truncation and accounting protections pass. An authored false winner/readiness/trading explanation receives agent semantic-review FAIL despite valid structured fields. Whole-response structure does not establish truthful prose; explicit semantic review remains required.

Exact final commands: `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage an-final-03` and `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/test_cost_1b.py --stage an-boundary-final-02`. Both exit 0. Retain the command record and earlier red/green evidence. A later rerun must use a fresh stage name.

Compiler SHA remains `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`; v6 SHA is `2c50a2d94a7061eec83349ec4650e769d8479df78f0f52348c4497a8fbdcfb69`. V5 and every historical verdict remain preserved. Fifteen specifically inspected protected artifacts match their prior hashes; no complete archive audit is claimed. Hermes source/lock/configuration, financial logic and native/model transport settings remain unchanged. Existing resource safeguards remain. Final suite times are 26.080 and 11.260 seconds; peak RSS 179,912,704 and 189,399,040 bytes respectively.

Actual usage remains twenty-one requests and USD 0.0173381625, with no outstanding reservation. New cost is zero. The prepared single Sol A-N recheck is **PENDING**, with a conservative request-specific estimate of USD 0.0652050 and current working-budget remainder USD 0.2826618375. This estimate uses existing captured pricing and policy; it is not a guaranteed financial bound. Require new approval, a fresh live identity/admission and reconciliation of retained charges. Do not reopen the old comparison. Complete 1B, checkpoint 1, Probe A and Compass remain unpassed. Stop for controller review.

## 20. Approved Sol v6 live recovery, 1B-sol-an-recheck-09

The builder first approves the prepared single Sol A-N live recheck, then prospectively approves up to four additional calls: A-T, A-I, A-U and an eligible clarification follow-up using that run's fresh passing A-I. A-N has not been dispatched at the amendment. Keep it once, then run the remaining independent cases sequentially. Maximum five new inference requests, twenty-six cumulative if all five dispatch. Preserve all twenty-one earlier requests and USD 0.0173381625. Do not reuse stopped Luna slots, repeat A-N or start another comparison batch.

Freeze `probe-a-1b-meaning-v6`, schema, case text, clarification reply, meaning checks, unchanged 1A compiler, pinned Hermes and Sol low reasoning. Keep `max_tokens=4096`, USD 0.30 cumulative working budget, conservative request-specific reservations, actual charge settlement, no fallback/retry and empty tools. No new token quotas or financial-control framework. The necessary run-profile change reuses the existing Accounting class, reads the previous settled journals by pinned identity and permits exactly this five-attempt order: A-N, A-T, A-I, A-U, A-I-followup. A follow-up requires the fresh A-I packet and explicit agent review of its questions and explanation.

Independent interpretation or representation failures remain visible and do not prevent other approved cases when charges are settled and the transport boundary remains safe. Unknown charges, credential/isolation violations, provider output-cap violations and exhausted spending stop dispatch. No automatic repair or retry. A failed or ineligible A-I makes the follow-up NOT_RUN. Do not supply another model's answer or an authored first-turn substitute.

Assess format, meaning, missing information, bounded research, unsupported capabilities, compilation and canonical reload separately. Historical evidence remains unavailable. No selected strategy or test result follows from unresolved research configuration. Preserve all prior verdicts. Record a new observed result, without claiming that earlier v5 cases ran live under v6. Complete 1B requires all five applicable outcomes under the recorded v6 candidate; historical checkpoint 2, Probe B, production work and publication remain outside scope. Stop for controller review after the report.


### Observed complete Sol v6 recovery and terminal stop

**PASS — BOUNDED INTERPRETATION AND COMPILER COMPATIBILITY**. All five fresh live cases pass under the same frozen v6 candidate: A-N unresolved research, A-T compile/reload, A-I useful clarification with no defaults, A-U preserved unsupported LP/wallet/X request, and its own fresh A-I clarification follow-up with compilation/reload. A-N ran once. All five genuine Hermes conversations completed with one POST, one valid whole object and finish reason `stop`. No truncation, manual repair, fragment selection, retry, fallback or Luna call occurred.

The no-thesis packet keeps exact adopted timing/sizing as research configuration and selects no signal, strategy, winner or test result. Missing historical evidence stays unresolved. The actual explanations receive agent semantic-review PASS without readiness or execution claims. Fresh A-I questions receive meaning review before the follow-up. The frozen authored user reply supplies all decisions; earlier and reply-added restrictions remain intact. A-T and follow-up canonical identities are `75fdc936cae0b43d21e17b266e3eec4582e3fe782a57f86a8a379dda73af091b` and `a38e7cf1a1b566b76cbba4e6e7fcd31804f41d2d6709102c8b7e58044619aa64`. No synthetic input label is presented as model provenance.

The existing Accounting class now admits this five-call profile using the pinned prior twenty-one settled requests. Initial single-case red checks and the prospective five-call allowance red check remain. Final 19/19 boundary and 35/35 interpretation checks pass, exit 0; both read-only reviews pass. V6 interpretation functions, schema/instructions/evaluator and compiler remain unchanged from repair-08. Only necessary live-profile wiring and isolated tests change. No new financial framework or token quota is introduced.

Actual model is `openai/gpt-6.1-sol`, provider reports OpenAI via OpenRouter, only `openai/flex` requested; reasoning low, `max_tokens=4096`, empty tools, strict schema/required parameters and disabled fallback remain. Five new calls cost USD 0.0135487 and use 9,973 input/1,687 output tokens, including 212 reported reasoning tokens. Cumulative usage: twenty-six requests, USD 0.0308868625, 67,941 input/11,324 output tokens. All charges settled sequentially; unknown charges and outstanding reservations are zero. USD 0.30 remains the approved working budget with accepted in-flight estimate uncertainty. No other metadata/provider requests occurred.

Exact final offline commands are `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/test_cost_1b.py --stage amended-five-green-01` and `.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage v6-recovery-final-01`. Preparation uses `interpret_1b.py an-recheck-prepare`; live execution uses `interpret_1b.py an-recheck --batch sol --case CASE`, in order A-N, A-T, A-I, A-U, A-I-followup. Every listed command exits 0. The full result report retains expanded commands, per-case costs and latencies. These recorded commands do not permit repetition. `closed.json` seals the run; the final admission check denies dispatch before credential access.

Live case wall time totals 76.857 seconds; aggregate parent CPU 8.227 seconds; peak RSS 187,940,864 bytes. Existing resource safeguards remain. Compiler SHA is `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`, v6 SHA `2c50a2d94a7061eec83349ec4650e769d8479df78f0f52348c4497a8fbdcfb69`, adapter SHA `a15ae4f71e1f6c815ec37160116d7960ca7c9cd7caaf58e05a9e16da73043594`. Twenty targeted protected artifacts match prior hashes; earlier results/charges and unrelated changes remain preserved.

The existing complete 1B acceptance requirements are met for this candidate. With retained 1A recovery's 81 passing mechanics checks and the unchanged compiler, checkpoint 1 passes for the approved subset. Earlier v5 comparisons retain their rejections; offline fixtures/replays retain their offline labels. These fresh passes are not combined from different contracts or models. No required 1B case remains unproved here. General interpretation reliability and historical research, profitability, execution readiness and persistent trading remain unproved. A01/A02 still block historical investigation; checkpoint 2, complete Probe A and Compass remain unpassed. No broader design approval follows.

BUILDER-ONLY REFERENCE `prototypes/edge-os/probe-a/evidence/A01/1B-sol-an-recheck-09/` retains actual packets, completions, decisions, agent reviews, revision, source identities, ledger, usage, commands and terminal verdict. Controller review is next. Stop; do not run another call, historical checkpoint 2, Probe B, production work or Git publication.
