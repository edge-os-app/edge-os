# Edge OS scoped probe plan

Private source pointers are marked `BUILDER-ONLY REFERENCE`. They are not included in a teammate's clone. Follow the [reference rules](../agents/domain.md#shared-documents-and-private-evidence). Source labels preserve provenance, not new verification.

Date: 2026-10-02, Africa/Kinshasa.

Status: `DRAFT FOR BUILDER REVIEW`. Probe A: `NOT_STARTED`. Probe B: `NOT_STARTED`.

The builder authorized this documentation update, not code, paid processing, credentials access, wallet changes or transactions. Approve each instantiated experiment separately. Keep the full design draft and unpassed gates visible.

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
| Finite Kuru market/token universe and one momentum or reversal question | `UNKNOWN; select before approval` |
| Fixed source bundle and point-in-time dataset, covered period, granularity and gaps | `UNKNOWN; inspect existing permitted data first` |
| Accepted grammar, primitives, units, parameter bounds and numerical/missing-value rules | `UNKNOWN; choose the narrow subset from the verified course evidence` |
| Three input examples: concrete thesis, incomplete intuition, bounded no-thesis request | `UNKNOWN; write exact examples before approval` |
| Candidate/variant, request, compute and cost limits | `UNKNOWN; freeze numeric limits before approval` |
| Research/holdout boundary or explicitly limited forward-only alternative | `UNKNOWN; record before testing` |
| Known-invalid fixture, clean control and expected outcomes | `UNKNOWN; freeze before the run` |
| Research-agent runtime/model and permitted evidence tools | `UNKNOWN; existing evidence bundle first, no unrestricted search` |
| Builder's scope/cost approval and approved work limit | `PENDING` |

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

Can one bounded spot investigation preserve its meaning and trial history, produce an inspectable typed strategy or useful unresolved result, and reject a known-invalid attractive result without inventing missing assumptions?

Failure would weaken the distinctive research promise even if wallet execution works.

### Smallest runnable test

1. Run the frozen input examples through a narrow interpretation path. Show extracted meaning, missing assumptions and unsupported claims.
2. Perform one bounded investigation against the fixed source bundle. Preserve source/availability times, supporting and contrary evidence, mechanism uncertainty and each attempted variant.
3. Emit the proposed `ResearchEvidencePackage`, `EdgeSpec` and ledger, or a specific unresolved result. An unknown economic explanation stays unknown.
4. Compile the supported rule meaning into a typed canonical `StrategySpec`; show its plain-English interpretation and semantic identity. Test invalid units/types and missing meaning for the selected subset.
5. Run the frozen clean control and deliberately invalid case through the evaluator. Declare supported cost/liquidity/timing assumptions and missing coverage. Preserve research and holdout access history.
6. Show a rejection trace and the user's next evidence requirement. Run without X/Nansen. Loss of an input essential to the declared hypothesis must stop that hypothesis, not silently alter it.

The invalid fixture should have a known cause, such as future information leaking into a signal, and an attractive naive result. Freeze that cause and comparison before the run. Label synthetic or modified data. The clean control checks legitimate mechanics; it does not establish a profitable edge. Statistical overfitting rejection is a separate claim unless actually implemented and tested.

### Verdict conditions

- `PASS`: every frozen case behaves as expected; the real bounded investigation and timing record are inspectable; meaning and all attempted variants are preserved; the invalid case is rejected for its known cause; the clean control runs without granting unearned eligibility; zero survivors still produce a useful report.
- `NARROW`: a smaller useful claim has evidence, such as compiler/rejection mechanics on fixtures without sufficient historical or agent-investigation coverage. Name what worked and obtain approval of the narrower product claim before relying on it.
- `REJECT`: observed behavior invents meaning, hides attempted variants, admits the invalid case or cannot produce a useful supported/rejected/unresolved result.
- `UNRESOLVED`: the test cannot answer its frozen question because required data, access or another dependency is unavailable. Record the exact blocker and next bounded check.

Stop at the verdict or approved budget. Save input/output snapshots, dataset/source manifest, versions, trial list, relevant compiler test results and the same-case comparison in `docs/prototypes/EDGE_OS_PROBE_A_RESULT.md`. The result file does not exist until a real run occurs. Passing A grants no execution permission, demand proof or profitability claim.

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
| Probe A instantiated design and code | `PENDING` |
| Probe A model/provider costs | `PENDING`; no new paid calls |
| Probe B instantiated design and code | `PENDING` |
| Probe B wallet changes, provider use and financial limits | `PENDING`; no signing or transactions |
| Builder result-state prototype | `PENDING` |
| Full product design/build brief | `PENDING` |
| Optional token extension | `PENDING`; not part of either probe |

Next action: instantiate the safe input/configuration proposals, then have the builder approve or revise each scoped experiment. Keep A and B unstarted until their applicable approvals are recorded. This document is the shared plan; do not create another mandatory planning document before these tests.
