# Edge OS scoped probe plan

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](../agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Date: 2026-10-02, Africa/Kinshasa.

Status: `DRAFT FOR BUILDER REVIEW`. Probe A: `1A-recovery-01` is `PASS — MECHANICS ONLY`; earlier aggregate-read result remains `REJECT — MECHANICS ONLY`. Part 1B `1B-01/adapter-04`: `REJECT`; repair `1B-offline-repair-01`: `OFFLINE REPAIR PASS — LIVE 1B UNPROVED`. Checkpoint 1 and full Probe A remain unpassed. Probe B: `NOT_STARTED`.

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
