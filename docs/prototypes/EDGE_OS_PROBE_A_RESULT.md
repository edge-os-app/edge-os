# Probe A 1B offline repair

`1B-offline-repair-01`: **OFFLINE REPAIR PASS — LIVE 1B UNPROVED**, 2026-10-02.

The complete offline handoff passed 25/25 checks. These inputs and provider responses are authored fixtures. They test integration behavior, not model interpretation accuracy. No inference or provider metadata request was made. No real credential was read. The original `1B-01/adapter-04` rejection remains below. Part 1B, checkpoint 1, Probe A and the Compass gate remain unpassed.

## Defects and repairs

The adapter accepted captured provider content without requiring Hermes completion. The repaired handoff requires `completed=true`, no failed/partial/interrupted state, exactly one API call and a final response that matches the captured content. It validates Hermes' actual `final_response`. A valid captured packet with a failed conversation is denied as `TRANSPORT_FAILURE`.

The response relay returned decoded bytes with a compressed-body header. HTTPX then tried to decode them again. The repaired relay retains the received encoding headers and wire bytes as evidence. It removes encoding, transfer and length headers when it returns decoded bytes; HTTPX sets the correct decoded length. Plain and gzip fixtures now complete the same handoff. The original live headers were not retained. Compression's role in that live failure remains unconfirmed.

A-T received A-N's search configuration. Case packets now include only relevant context. A-I receives no timing, size, threshold or search defaults. A-N alone receives the declared search. A-U retains its wallet-label/X/LP domain and cannot be replaced with a spot strategy.

The earlier prose contract allowed compiler-incompatible representations. `interpretation_contract.py` now defines `probe-a-1b-output-v2`. Its Pydantic model generates the instructions, strict JSON Schema request and local validator. Every field is required; some fields permit null. Extra fields are forbidden. Sizing uses unsigned fixed-decimal strings, with `MON` in `quote_unit`. Times and counts are strict integers; flags are booleans. Mode is `research`. The contract declares the compiler's grammar. Compiler checks still enforce parameter, unit, timing, permission and meaning restrictions. No failed model field is filled or repaired.

Exclusions now use declared enum codes for prohibitions or unsupported operations. Faithful user prohibitions are accepted and grant no capability. Case evidence uses an explicit output directory and case prefix. It cannot overwrite historical live evidence.

The request reservation now includes the complete serialized body, including the schema, plus its framing margin. This is a conservative token estimate, not a provider count. Persisted unknown-charge, malformed-record, cost, token and request-cap denials remain active. Offline accounting stays separate from provider usage.

The full negative test exposed Hermes' length-response continuation and max-iteration summary path. The synchronous dispatcher now rejects a nonfinal response before Hermes can enter that path. The single-request guard remains in place. The 90-second case deadline now restores the remaining outer watchdog rather than cancelling it. Live adapter entry points stop before credential or setup access with `LIVE_RECOVERY_NOT_AUTHORIZED`.

## Offline results

| Check | Expected and actual result |
|---|---|
| Complete A-T, plain and gzip | Hermes completes; packet validates; unchanged compiler compiles; canonical reload and frozen meaning comparison pass. Semantic SHA-256 remains `75fdc936cae0b43d21e17b266e3eec4582e3fe782a57f86a8a379dda73af091b`; canonical size is 1,647 bytes. |
| A-I fixture | `NEEDS_CLARIFICATION`; all six required gaps named; no strategy or search defaults. |
| A-N fixture | `UNRESOLVED`; exact finite space and budget retained; missing historical dataset/availability named; no winner. |
| A-U fixture | `UNSUPPORTED`; wallet-label/X/LP rebalance domain retained; no substituted strategy. |
| Changed comparison or threshold; A-T search expansion | Denied as meaning or scope failure. |
| Unit-bearing or numeric-typed sizing, exponents, nonfinite text, trailing newline, wrong mode | Precise `OUTPUT_FORMAT` denial. |
| Malformed, duplicate-key or truncated packet; missing unit or extra winner field | Denied. Truncation causes no continuation request. |
| Captured valid packet with failed actual Hermes conversation; differing final response | `TRANSPORT_FAILURE`; cannot pass. |
| Invented clarification/research/unsupported strategy; erased domain; expanded variants | Denied. |
| Model, routing, reasoning, output-cap, temperature or tools changes | Denied before fixture dispatch. |
| Persisted accounting | Unknown charge, malformed ledger, fifth request, cost/input limits and excess output denied. No reset to zero. These are authored offline records. |
| Evidence and safeguards | Case paths do not collide; outer watchdog survives; live entry points deny; all 184 historical evidence files remain byte-identical. |

The first baseline run failed all eight defect checks: six assertion failures and two errors, exit 1. Three further contract checks and the watchdog check also failed before repair. An intermediate 24-check run retained its truncation-classification failure. The final 25-check run exited 0. All red and intermediate evidence is retained.

Executed command:

```sh
.tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline --stage green-full-03
```

Run a later offline review with a fresh stage name; existing evidence is not overwritten. Final suite elapsed time was 2.374 seconds, CPU time 1.964 seconds and peak RSS 181,796,864 bytes (173.38 MiB). Controls remain 900-second outer watchdog, 90-second case deadline, 120 CPU seconds, observed 512 MiB RSS guard, 100 MiB output ceiling and 32 KiB request boundary. Dispatch is synchronous. No new hard memory or CPU-affinity qualification is claimed.

Changed private files: `interpret_1b.py`, `interpretation_contract.py`, `test_interpret_1b.py`. Executed adapter SHA-256: `dfd42d412f5c0a215179f2b133a1ed2c2c4738e2ebc90b8ce531e486f1f7e5f6`. The compiler is unchanged: `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`. Hermes remains pinned to `54bc5e509c985f37265c3d416bd2c64b10fc77ba`; lockfile and original runtime-config hashes are unchanged. Model, tool restrictions, isolation configuration and historical approvals are unchanged. The only compiler-interface mapping is the provenance marker; authored offline origin is recorded separately.

## Strict schema and remaining gates

Context7 was used after library-ID resolution. [OpenRouter structured-output documentation](https://github.com/openrouterteam/docs/blob/main/guides/features/structured-outputs.mdx) defines strict `json_schema` requests. The retained Luna catalog advertises `structured_outputs` and `response_format`. The adapter requests that format with `strict=true` and `require_parameters=true`. No basic-JSON fallback is enabled. Offline fixtures do not prove that a live endpoint will accept or enforce this complete schema. Local validation remains mandatory. Pydantic 2.13.4 is already installed; no dependency was installed or updated.

The result report and executed evidence supersede older “not started” statements in the controller handoff and Compass stage table. Those files are outside this repair's write scope and remain unchanged. Older setup amendments in the plan describe historical state; they do not authorize a live recovery.

Actual provider totals remain **one inference request**, 970 prompt tokens, 455 completion tokens and **USD 0.0003245**, with no uncertain reservation. Offline fixture usage is not added to those totals. A01/A02 historical blockers remain. Live model accuracy, live completion and endpoint schema enforcement remain unproved.

Next approval proposal, **PENDING**: four additional inference calls, five cumulatively, one per frozen case. Retain the prior charge and token counts. Keep the USD 0.10 working cap and USD 0.30 maximum, 1,024 output tokens, 90-second deadline, A01 token limits and chosen model. No automatic retries, repair calls or model escalation. Before dispatch, record the new allowance in a persisted recovery journal that retains cumulative prior usage, verify its admission controls offline and explicitly enable the live route under that approval. This task did not activate that configuration or make a paid call.

Private evidence: `prototypes/edge-os/probe-a/evidence/A01/1B-offline-repair-01/`. See `repair-manifest.json`, `source-trace.json`, `contract-evidence.json`, `output-contract.json`, executed snapshots, and `green-full-03/results.json`. Per-case artifacts retain inputs, context, fixtures, serialized requests, wire/decoded responses, received safe headers, completed or failed conversations, decisions and canonical meaning. All records here are offline fixtures, including baseline test journals named `requests.jsonl`; actual provider usage remains in `1B-01/adapter-04/requests.jsonl`.

Stop for builder review. No historical investigation, deployment or financial execution is approved.

---

# Probe A part 1B results

`1B-01/adapter-04`: **REJECT — HERMES INTERPRETATION**, 2026-10-02.

A-T failed. A-I, A-N and the unsupported extension were not run. The plan requires an unexpected meaning or safety failure to stop the checkpoint. No retry, repair inference or remaining-case request followed. Complete checkpoint 1, Probe A and the Compass gate remain unpassed. The earlier 1A rejection and its 81/81 recovery pass remain preserved below.

## Case outcomes

| Case | Expected | Observed |
|---|---|---|
| A-T | Faithful synthetic `COMPILED`; historical evidence unresolved | Provider packet said `COMPILED`, but the deterministic adapter rejected it. It included the four-variant search space with the fixed one-rule thesis. Raw mode `research simulation` failed the unchanged compiler as `INVALID_INPUT`, field `mode`. Notional `10 MON` and balance `100 MON` also differ from its required numeric-string representation. No hand repair was applied. |
| A-I | `NEEDS_CLARIFICATION`, no borrowed defaults | `NOT_RUN` after the stop. |
| A-N | `UNRESOLVED`, finite search/budget preserved, intake only | `NOT_RUN` after the stop. |
| Wallet-label/X/LP extension | `UNSUPPORTED`, original domain preserved | `NOT_RUN` after the stop. |

The saved A-T packet retained strict `> 0.01`, lookback one, the declared timing fields, unknown mechanism, empty permissions and the three illustrative cost cases. Its unit-bearing sizing strings describe the requested amounts; the failure is an interface mismatch, not evidence that the model chose different capital. The adapter additionally required empty A-T exclusions, while the returned exclusions mostly preserve user prohibitions. That assertion is not independently treated as invented strategy meaning. The non-null broader search packet conflicts with the output contract. It was not silently discarded.

The only applied compiler compatibility mapping changed `input_class` from `HERMES_INTERPRETATION` to the legacy authored-synthetic marker. The unchanged raw model packet and real Hermes provenance are retained separately. No missing field, expected answer, sizing value, mode or search field was supplied or repaired. No typed/canonical strategy was earned by this case.

## Adapter and transport failures

The adapter invoked actual `AIAgent.run_conversation`, not a direct completion labeled Hermes. The provider returned a complete, non-truncated response with stop reason `stop`. The adapter saved that response and settled its charge. Hermes then reported a connection error and `completed=false`; successful conversation integration was not established.

A local, explicitly authored compressed-response check reproduced an adapter defect: forwarding original Content-Encoding headers together with already decoded `response.read()` bytes can cause a second decode. Exact live response headers were not retained, so attribution of the live connection error to this defect remains an inference. The experiment stopped without changing the executed adapter after inference.

Three earlier attempts used no inference POST. `adapter-01` blocked injected sticky-session metadata. `adapter-02` blocked the trailing-newline difference introduced by Hermes prompt normalization. `adapter-03` passed offline checks, then its live launch stopped on an offline/live evidence filename collision before SDK dispatch. Those failures and snapshots remain retained. `adapter-04` omitted the metadata with an explicit mapping, used a normalized contract and separate evidence names, checked cross-directory reservations, and passed its offline checks before the one paid dispatch.

## Request and cost accounting

| Metric | Actual |
|---|---:|
| Inference POSTs, including failed requests | 1 of 4 |
| Provider prompt tokens | 970 |
| Provider completion tokens | 455 |
| Provider total tokens | 1,425 |
| Provider reasoning tokens | 0 |
| Actual provider USD cost | 0.0003245 |
| Prompt upper estimate reserved before dispatch | 5,004; estimate, not provider count |
| Conservative USD reservation before dispatch | 0.0010124 |
| Unresolved reservations | 0 |
| Active spending allowance | USD 0.10 |
| Conditional USD 0.30 backup | Not activated |
| Prior read-only provider metadata requests | 6 |
| New provider metadata requests / market-data requests | 0 / 0 |

Actual counts consume the A01 aggregate limits: 970/48,000 input and 455/8,000 output tokens; one of its eight proposed total model requests. The narrower four-request 1B approval controls this task. All offline mock and fault-injected accounting records are explicitly separate and are not provider usage. No provider-enforced aggregate key limit or verified account balance is claimed.

Persisted reservation tests denied a repeat/fifth request, malformed accounting, excessive input/cost and excessive completion usage. A fresh process retained an uncertain reservation and denied further admission. The selected catalog price was checked against the frozen preflight. The final wire packet selected Luna, JSON output, reasoning `none`, 1,024 maximum output tokens and no temperature, tools, fallback, unsupported parameters, proxy or redirect. SDK and HTTP retries were zero; Hermes API attempts were one. No hidden POST was admitted.

## Commands, resources and evidence

From the private workspace, the active commands were:

```sh
/usr/bin/time -l .tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py offline
/usr/bin/time -l .tools/hermes-agent/.venv/bin/python prototypes/edge-os/probe-a/interpret_1b.py case --case A-T
```

They exited 0 and 1 respectively. Exact earlier commands, exit codes and reporting-check failures are retained in `commands.json`. This is an execution record; the persisted state denies repeating the paid case.

The active offline check took 1.37 seconds; its peak RSS was 181,157,888 bytes. The paid case process took 6.90 seconds, used 1.12 CPU seconds and peaked at 178,323,456 bytes. Its inference transaction and case elapsed times are saved separately. The 900-second watchdog, 90-second conversation deadline, 120-second per-process CPU limit, 512-MiB observed-RSS guard and 100-MiB evidence ceiling remained enabled. Network dispatch was synchronous and cases sequential. Earlier offline attempts and full active preparation time were not instrumented; their totals are not invented. There is no hard-memory, affinity, OS-sandbox or production-tenancy claim.

BUILDER-ONLY REFERENCE: `prototypes/edge-os/probe-a/interpret_1b.py` and `prototypes/edge-os/probe-a/evidence/A01/1B-01/adapter-04/`. Evidence includes approval/configuration, executed snapshot/hash, source identities, unchanged input/binding, exact request and response bodies without authorization headers, actual conversation failure, raw model packet, mapping, compiler denial, reservation/settlement journal, offline controls, timing, commands and verdict. Earlier setup artifacts and all 1A evidence remain unchanged. A value scan found no destination key in 1B evidence or runtime files.

Pinned source, lockfile, configuration and compiler hashes matched. No Hermes update, compiler edit, model substitution, historical acquisition, fixture evaluation, strategy trial, screenshot, wallet action, commit, push, merge or issue occurred.

## Remaining blockers and review

The response relay and output-contract compatibility need an offline adapter repair and builder review. A-T's contradictory packet must remain a failed result. The other three interpretation cases have no observed result. Only three inference requests remain unused under this approval; it grants no A-T retry or fresh four-request allocation. Further inference needs a separately reviewed recovery scope and cumulative budget.

A01 market identity and A02 qualified historical data remain unresolved and were not investigated. A03 has local request/accounting evidence, but successful Hermes conversation and interpretation/compiler integration remain unproved. No historical research, profitability, general overfitting detection, execution readiness or full Probe A claim follows. Stop for builder review.

---

# Probe A part 1A results

Recovery `1A-recovery-01`: **PASS — MECHANICS ONLY**, 2026-10-02.

The earlier experiment remains **REJECT — MECHANICS ONLY**. This recovery uses the builder's new approval and a separate 30-minute allowance. It does not replace the rejection or claim compliance with its failed configuration. Part 1B, complete checkpoint 1, Probe A and the Compass gate remain unpassed.

## Accounting repair

Fixed offline synthetic reads now record cumulative counts and bytes without a count ceiling. All 32 earlier reads remain in those totals. Capped profiles use their own persistent accounting logs. The normal `Run.read()` reloads and validates that log before every admission, checks the two-read allowance, persists acceptance, then returns data. A new process or run directory cannot reset profile usage. Invalid or unavailable records deny access instead of assuming zero.

The existing budget helper is reused. The suite's budget check now calls the actual read function and persistence path. No budget framework was added. Profile execution is sequential; concurrent admission is not tested and would need locking.

## Restart and denial checks

Five separate child processes ran. All checks passed and all commands exited 0.

| Process | Actual result |
|---|---|
| First, PID 47027 | Loaded zero from the explicitly empty new profile. Accepted one read and persisted usage one. |
| Second, PID 47379 | Loaded one. Accepted read two. Read three returned `BUDGET_EXCEEDED`, no data, usage still two. |
| Exhausted, PID 47381 | Loaded two. Denied access with `BUDGET_EXCEEDED`, no data, usage still two. |
| Malformed record, PID 47387 | `ACCOUNTING_INVALID`; access stopped during profile initialization. No data or fresh allowance. |
| Missing/unreadable record, PID 47390 | `ACCOUNTING_UNREADABLE`; access stopped during profile initialization. No data or fresh allowance. |

The intentionally bad record is isolated from accepted-usage logs. Its consumption is marked unknown, not reset to zero. Regression records remain separate and are included in the recovery inventory.

## Full mechanics suite

The complete corrected suite ran after all restart checks passed. **81/81 checks passed.** No code changed after that run. All ten requirements are covered:

| Requirement | Recovery outcome |
|---|---|
| Typed compilation and explanation | PASS; Boolean series, explicit units/timing/sizing, unknown mechanism, empty execution permissions. |
| Canonical serialization/reload | PASS; identical 1,647 bytes after revalidation. |
| Contiguous returns, strict threshold, missing values | PASS; no dropping or filling gaps; exact 1% does not pass strict 1%. |
| Syntax/arity/type/unit/parameter rejection | PASS; expected error codes and positioned syntax denials. |
| Zero reads on static failure | PASS; all 40 fresh/stored negative expression cases recorded zero reads. |
| Stable semantic identity | PASS; used policy/component versions retained; changed meaning changes identity. |
| Clean C0 and quarantined naive L1 | PASS; frozen numbers and independent Fraction reference agree. |
| Normal future-information rejection | PASS; both L1 episodes denied with decision, availability, source and dependency traces. |
| Package/ledger reconciliation | PASS; complete package matches attempts; omitted contrary evidence/attempts are denied. |
| Budget enforcement | PASS; actual persisted capped read function accepts two and denies the third; separate fresh-process checks preserve exhaustion. |

C0 at 50 bps per side produced **+8.95% and −10.95%**, mean −1%. Quarantined naive L1 produced **+8.95%** from F1 only. Normal L1 rejected `F1.exit` (09:45:03 availability versus 09:10 decision) and `F2.exit` (10:45:03 versus 10:10), both as `FUTURE_INFORMATION`. Expected invalid-input denials are successful checks, not unexpected failures.

C0/L1 fixture hashes match the earlier manifests. Strategy identity remains `75fdc936cae0b43d21e17b266e3eec4582e3fe782a57f86a8a379dda73af091b`. Grammar, units, numerical policy, timing, serializer and component semantics remain `probe-a-v1`. The new experiment configuration is `probe-a-1a-accounting-recovery-v1`.

## Commands and artifacts

Executed from the private workspace:

```sh
python3 prototypes/edge-os/probe-a/probe_a.py profile-step --run 1A-recovery-01 --stage first
python3 prototypes/edge-os/probe-a/probe_a.py profile-step --run 1A-recovery-01 --stage second
python3 prototypes/edge-os/probe-a/probe_a.py profile-step --run 1A-recovery-01 --stage exhausted
python3 prototypes/edge-os/probe-a/probe_a.py profile-step --run 1A-recovery-01 --stage malformed
python3 prototypes/edge-os/probe-a/probe_a.py profile-step --run 1A-recovery-01 --stage unreadable
python3 prototypes/edge-os/probe-a/probe_a.py checkpoint-1 --run 1A-recovery-01
```

BUILDER-ONLY REFERENCE: recovery evidence is `prototypes/edge-os/probe-a/evidence/A01/1A-recovery-01/`. It contains approval/configuration, executed `program.py.txt`, program hash, restart results and profile logs, regression summary, all mechanics artifacts, exact commands/exit codes, usage, `recovery-verdict.json`, timing and inventory. Current program hash is `ebeb11a454662204726b6607c42913c1aa737c31213cad706e95b84541a3325b`.

All 50 pre-existing evidence files matched their preserved hashes. The earlier authoritative rejection, both local passes and their snapshots remain unchanged. No commit, push, merge or issue was created. No unrelated file was edited.

## Usage and limits

| Usage | Accepted reads | Bytes |
|---|---:|---:|
| Earlier offline history | 32 | 13,532 |
| Recovery full suite | 16 | 6,766 |
| Cumulative offline fixture metrics | 48 | 20,298 |
| Restart capped profile | 2 | 676 |
| Suite capped profile | 2 | 676 |
| Overall history plus recovery | 52 | 21,650 |

Denied operations add no accepted usage. The 20-read exception applies only to fixed offline synthetic repetitions. Later model/provider/trial/holdout limits remain unchanged.

Six recovery commands totalled **0.606 seconds wall**, **0.448 seconds aggregate CPU**. Peak observed RSS was **30,244,864 bytes**, about 28.8 MiB. The 900-second watchdog, 120-second CPU limit, memory monitoring, 100-MiB output ceiling and byte/expression bounds stayed in place. Hard memory or affinity qualification was not retried. Active-work timing includes preparation, repair, checks and reporting; the exact recorded interval and previous-work separation are in `timing.json`.

No unexpected recovery failure occurred. No additional strategy/market fixtures, course or screenshot research, model/provider requests, secrets, dependencies or financial actions were used. There is no remaining blocker for this deterministic recovery result. This does not prove arbitrary-language fidelity, Hermes integration, historical discovery, profitability, general overfitting detection or execution readiness. Stop for builder review before any separately approved next part.

## Earlier experiment: preserved rejection


Date: 2026-10-02. Final verdict: **REJECT — MECHANICS ONLY**, for aggregate read-budget accounting.

The declared compiler and leakage mechanics worked in the retained local checks. The experiment did not satisfy its complete budget boundary: a second run reset its counter and admitted 32 fixture reads across both runs against the unchanged total cap of 20. This was an implementation mistake, not a changed expectation. The local suite pass labels do not establish an overall pass. Full checkpoint 1, Probe A and the Compass gate remain unpassed.

### Approval and method

The builder authorized deterministic 1A, then explicitly waived the hard resource-enforcement blocker while sufficient memory was available. Both approvals are recorded in the [shared plan](EDGE_OS_SCOPED_PROBE_PLAN.md#8-approval-record). The amendment changes resource enforcement only. Grammar, units, decimal rules, timing, C0/L1 values, expected decisions and input/read limits remained frozen.

One private, throwaway standard-library Python program implements a rejecting parser, whitelist lowering/type checks, canonical StrategySpec, deterministic evaluator and one `self_check()`. It uses explicitly authored structured synthetic inputs. Its plain-English output describes those inputs; it is not arbitrary-language interpretation or Hermes evidence. No application or production integration was created.

The first resumed run passed 79 local checks. A second revision added exact static-denial traces, derived displayed sizing from computed units and added two focused checks; it passed 81 local checks. Both executed code snapshots and all outputs are retained. Final artifact review discovered the cross-run budget breach. The program was corrected to consult accepted access events across A01 directories; its normal read boundary then denied another operation. No full corrected run followed.

### Required checks and actual outcomes

| Required check | Actual outcome and evidence |
|---|---|
| 1. Typed compilation and explanation | Boolean-series root, dimensionless return, MON/base-token prices; expanded tree has 8 nodes and depth 4. Explanation retains strict threshold, contiguous five-minute bars, hh:10 decision, hh:15/hh:45 references, 10 MON sizing, 100 MON paper balance, unknown mechanism and empty execution permissions. |
| 2. Serialization/reload/revalidation | Canonical JSON is 1,647 bytes. Reload reproduced identical bytes. Expanded equivalent had the same semantic identity. Altered stored type and duplicate/non-finite JSON were denied. |
| 3. Returns/threshold/missing behavior | `[100,102,101]` produced null, 0.02, approximately −1/102; signals null/true/false. Gaps were not skipped. Lag 3 required four contiguous bars. Exact 1% failed strict `> 1%`. Missing availability stayed unresolved; invalid prices never became valid zero signals. |
| 4. Syntax/arity/types/units/parameters | All 40 fresh/stored negative expression cases were denied with expected codes. Exact syntax positions are in `static-denials.jsonl`. Byte, tree-depth and expanded-node excesses were denied. Sizing bounds and numeric-format/non-finite cases were checked. |
| 5. Zero reads on static failure | Every one of the 40 negative expression cases recorded zero data reads. Supplied stored expressions used the fresh validation boundary. |
| 6. Semantic identity | Repeated bytes/hash stable; changing component/timing version changed the semantic hash. Dataset/config changes changed evaluation identity. All four declared parameter pairs were statically admitted; no strategy search occurred. |
| 7. C0 and naive L1 | Frozen numbers matched, including an independent Fraction calculation using price difference and separately charged entry/exit fees. The naive result remained quarantined and had no authority. |
| 8. FUTURE_INFORMATION | The normal gate rejected both future substitutions with decision time, actual availability, source time, dependency and affected strategy identity. |
| 9. Package/ledger reconciliation | Missing contrary evidence produced `MISSING_CONTRARY_EVIDENCE`; omitted attempts produced `MISSING_ATTEMPT`. Complete package IDs matched all 81 started/completed ledger attempts. |
| 10. Budget denial | The shared budget helper denied operation 3 under an authored two-operation profile. **Aggregate accounting failed:** both full runs independently reset the 20-read counter. Corrective audit of the normal boundary denied the next read at cumulative count 32, accepting zero more records. The corrected full run remains unverified. |

The semantic identity for both observed C0/L1 cases is `75fdc936cae0b43d21e17b266e3eec4582e3fe782a57f86a8a379dda73af091b`. Compiler, serializer, numerical, timing, registry and used-component IDs are `probe-a-v1`. The amended experiment configuration is separately identified as `probe-a-1a-monitored-resume-v1`.

| Fixture | Selected episodes | Gross returns | 50 bps per side | 100 bps per side |
|---|---|---|---|---|
| C0, SYNTHETIC_FIXTURE | F1 and F2 | +10%, −10%; mean 0 | +8.95%, −10.95%; mean −1% | +7.9%, −11.9%; mean −2% |
| L1, DELIBERATELY_MODIFIED_SYNTHETIC_FIXTURE, naive only | F1 | +10%; win fraction 1 | +8.95% | +7.9% |

Normal L1 rejection: `F1.exit` was available at 09:45:03Z versus decision 09:10:00Z; `F2.exit` at 10:45:03Z versus decision 10:10:00Z, both on 2026-09-18. Their original exit source times are retained. C0 and L1 have different dataset identities and the same strategy identity.

### Commands and evidence

Executed from the private `monad-hack` workspace:

```sh
python3 prototypes/edge-os/probe-a/probe_a.py checkpoint-1 --run 1A-resume-02
```

This invokes deterministic 1A only. It refuses to overwrite an existing manifest. Do not rerun it under a fresh identity without a separately approved read-budget configuration.

BUILDER-ONLY REFERENCE: program `prototypes/edge-os/probe-a/probe_a.py`; evidence root `prototypes/edge-os/probe-a/evidence/A01/`. `result-index.json` records the final verdict, immutable startup evidence, both resumed runs and `1A-budget-audit/audit.json`. Each resumed directory retains authored inputs, manifest/configuration, typed/expanded strategy, canonical bytes/hash, deterministic explanation, expected/actual checks, access log, attempt ledger, comparison, package, edge record, usage, terminal output and local verdict. The second additionally retains exact static-denial traces. Executed snapshots are `program.py.txt`; startup code/report are archived locally. Private code/course sources are not published in this repository.

Both local `verdict.json` files say PASS for their local checks. **The cross-run audit and this report are authoritative for the final scope verdict: REJECT.** No failed attempt or startup result was deleted.

### Resources, failures and limitations

Host: macOS 26.5 arm64, Python 3.14.4; reported physical RAM 16 GiB. Both experiment children peaked at 29,425,664 bytes RSS, about 28.1 MiB. The two supervisor runs measured 0.202 seconds total wall time and 0.168 seconds aggregate CPU time. Including the earlier startup qualification, recorded program CPU consumption was about 1.241 seconds. Total fixture input consumed was 13,532 bytes; accepted reads were 32. Local retained evidence remained below 1 MiB, versus the 100-MiB output ceiling.

The parent enforced a 900-second subprocess deadline; the child configured a 120-second CPU limit, a per-file output limit and checked observed RSS between bounded operations. The evidence writer checks aggregate bytes. Workload execution was single-threaded. Hard memory allocation/CPU-affinity enforcement is **not** claimed; observed RSS can detect an overrun after allocation. Earlier scaled wall/CPU/file-size controls worked, but macOS rejected the 512-MiB memory-limit setting. That failure remains recorded and was explicitly superseded by the builder's resource amendment.

Failures: initial hard-limit qualification; the aggregate-read reset admitting 12 excess reads. Corrective denial accepted zero new fixture reads. No compiler check mismatch occurred. The current corrected program has not passed a full new suite; prior suite results apply to the retained executed snapshots.

The resumed work interval is recorded in `result-index.json`; the earlier recorded interval was 342 seconds. Initial source reading before the first persisted clock was not timed, so exact total active work is unavailable. User-wait time is not counted as active work. Reporting uses the original 90-minute allocation; no new allocation is claimed.

A01 market identity, A02 historical data and A03 Hermes/model/authentication/isolation/usage remain **NOT_APPLICABLE_TO_1A**, not resolved. A04 is resolved only for the named compiler-source findings in the plan. No new course source or screenshot was opened; the viewing count remains 16/20. The compiler preserves independently declared no-fill, contiguous-bar semantics rather than copying the course helpers. Raw-language input, model-request logs and historical-source artifacts are not applicable to this authored offline run.

This evidence proves tested synthetic mechanics only. A leakage fixture does not prove general overfitting detection; C0 does not prove profitability. Neither demonstrates historical edge discovery, arbitrary-thesis fidelity, Hermes integration or execution readiness. Independent production acceptance/review is not provided.

### Next separately approved task

Approve a new explicit read-budget/configuration for verification of the corrected deterministic 1A program, within the remaining original active-work allocation. Retain all 32 prior accesses; resetting a directory must not reset the same experiment's budget. Freeze that approval before any further fixture read. Part 1B, checkpoint 2, Probe B and financial permissions remain unchanged. Stop here.
