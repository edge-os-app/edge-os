# Edge OS frontend interaction result

Date: 2026-10-03. Artifact: BUILDER-ONLY REFERENCE `prototypes/edge-os/frontend-interaction/index.html` in the surrounding workspace, not application code. Current version v0.12.2, revised 2026-10-05. The wallet amendment and retained defects have been repaired and checked within the scope recorded below. Earlier versions and feedback remain historical evidence. See the [latest builder feedback and handoff](#builder-walkthrough-and-build-handoff-2026-10-05); task-level human comprehension and explicit bounded closure remain open.

## Experiment and evidence boundary

Can a trader understand the research result, account state and financial permission, then choose an appropriate next action? This implements the accepted five-task frontend scope. It does not approve a product specification change or production implementation.

Recorded evidence is the closed Probe A MOE investigation, C2-moe-investigation-04. All four variants remain unresolved, none is a supported candidate, and the holdout remains unopened. Account balances, adopted rules, positions, action receipts, permission changes and chat replies are authored fictional fixtures. No profitable strategy, live deployment, actual Hermes conversation or independently enforced inventory authority is established. Q31 inventory enforcement remains unqualified.

## Human comprehension findings

Participant B1 is the builder. No target trader or teammate has participated. B1 has seen the experiment brief and construction updates; this is not a blind target-user study.

| Task | Verdict | First answer and observed evidence | Changes and remaining questions |
| --- | --- | --- | --- |
| 1. Understand research | REVISE | v0.1.0, B1, free-play task requested through session question: “What did this investigation establish, and what would you do next?” First answer verbatim: “I do not understand, check the pic”. Safari inspection showed Continuation mid-page, with task navigation off screen. | v0.2.1 keeps task navigation visible and returns to the top on task changes. This established a navigation problem. B1 then explicitly said the screen wording was not understandable, so navigation alone did not resolve the problem. Research comprehension remains unresolved. See the language revision below. |
| 2. Review live permission | UNRESOLVED | No first answer recorded. | Direct ongoing and optional trial fixtures are available. Need participant explanation of authority and qualifications. |
| 3. Inspect positions directly and through conversation | UNRESOLVED | No first answer recorded. | Need participant attempt with exact position context and ambiguous half-close clarification. |
| 4. Understand stops and pending actions | UNRESOLVED | No first answer recorded. | Need participant distinction between entry stops, retained exits, close requests, unknown results and residual holdings. |
| 5. Understand continuation | UNRESOLVED | No first answer recorded. | Need participant explanation of extension versus new authority and preserved accounting. |

Do not convert missing answers into passes. No trader or teammate feedback is inferred from builder or browser checks. A navigation-assisted repeat is separate evidence from B1's first answer.

## Browser and source checks

These checks concern controls and presentation, not human comprehension.

- v0.1.0 loaded in Safari and Chrome from the local loopback server. Desktop screenshots and native accessibility state showed usable task buttons, account tables and simulated conversation controls. Selecting a position attached its exact fixture context. The conversation could scroll out of view; v0.2.0 made the desktop conversation column stay visible and focused it on attachment.
- Both inline scripts parsed after construction and after the v0.2.0 corrections. One construction syntax error was fixed before browser review.
- An independent finish reviewer found four source defects. v0.2.0 corrected trial-stop persistence, residual exit capacity checks, activation guards after expiry/removal, and the fixture per-action buy cap's consistency. The reviewer returned PASS for those four corrections only. This was source review, not browser or human evidence.
- Impeccable detection returned no findings in its single bounded run. This does not prove accessibility or comprehension.
- The initial Safari direct-file attempt reached a native file confirmation dialog and did not complete. Loopback loading succeeded. Chrome subsequently opened the v0.2.1 file directly at its file URL and rendered Research and Positions without a server or dependencies.
- Safari rendered v0.2.1 Research after a task click; its accessibility scroll value returned to zero. The screenshot showed the selected task and first-attempt prompt. This verifies the rendered navigation reset, not comprehension or every sticky-scroll state.
- Pure-model executable assertions passed for exact position context, read-only questions, ambiguous half-close clarification, queued/unknown holdings, same-action resend, partial-close accounting, time-only renewal and the expired-start guard. Confirmed partial close retained 500 MOE and basis 20 WMON; consumed buy allowance stayed 80 WMON. These are model checks, not browser interaction or execution qualification.
- A narrow-screen browser check was attempted through native Chrome DevTools. Repeated foreground/tab changes prevented completing it; no narrow-layout verdict is asserted. Browser traversal of the complete corrected action path also remains unverified.
- Both inline scripts parse in v0.2.1. No dependencies were installed and no production tests were added.

## References that shaped the interaction

The accepted scoped packet, accepted design decisions and research/accounting contracts govern the experiment. Actual Probe A findings govern MOE content. The competitor findings, including GT follow-up and Clawpump observations, and the curated “Start with these references” screenshots informed:

- Keel and Almanak: a readable record beside contextual conversation.
- Minara and Horizon: direct account and position views, visible account context and allowances.
- GT: expandable action history and pending-action details.
- Clawpump: separate trading capital, gas and compute funding.

Displayed competitor results and enforcement claims were not verified. No private wallet identifiers, balances or strategy details were copied. Website research was not repeated.

## Accepted findings and proposed changes

Accepted input decisions remain the five tasks and their evidence/accounting boundaries. The observed builder navigation failure is an experiment finding, not an accepted new specification. Sticky task navigation and task-change scroll reset are prototype fixes proposed for review. The four corrected source defects are builder implementation findings within existing contracts.

Smallest follow-up: repeat the research task after the rendered navigation fix, complete the narrow-layout and corrected-action browser checks, obtain first answers for the other four tasks, and have one target trader attempt the same tasks before claiming target-user comprehension. The frontend teammate should implement accepted flows only after those findings are reviewed. No prototype code should be promoted into production.

## Authorized work and limits

One standalone inline HTML/CSS/JavaScript artifact uses in-memory state, a separate state model, guided walkthroughs, free play, reset controls and readable state panels. This session used the approved bounded work window; exact active minutes were not independently measured. No paid model call, external runtime integration, wallet action, transaction, commit, push, issue or production change was made.

## Next neutral participant tasks

The research repeat was requested after navigation assistance. B1 could not answer and asked for rephrasing. Questions are paused while the explanation is rewritten. Keep the first answer above. Future B1 answers after this explanation are assisted repeats, not blind first attempts. For a new participant, use these tasks one at a time before coaching:

1. Research: What does this page tell you about the trading idea? What would you choose to do next? You can say you cannot tell.
2. Trading permission: Load the example before trading starts. What are you allowing the trading bot to do? What still needs to be checked?
3. Positions: Look at the two open trades. Find why P-101 was opened. Then type: Close half my MOE. What happens?
4. Stops: Stop the bot from buying more, while allowing its existing selling rules. Request a sale. What tokens are still held, and is anything waiting?
5. Continue trading: Compare continuing with the current limits, giving the bot more time, and letting it spend more. What changes in each case?

## Source links and artifact identity

- [Approved scope packet](EDGE_OS_SCOPED_PROBE_PLAN.md)
- [Actual Probe A findings](EDGE_OS_PROBE_A_RESULT.md)
- [Accepted product decisions](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md)
- [Research and accounting contracts](../EDGE_OS_RESEARCH_CONTRACTS.md)
- Competitor observations: BUILDER-ONLY REFERENCE `docs/research/EDGE_OS_COMPETITOR_UX_AND_ACCOUNT_CONTROL_2026-10-03.md`.
- Curated screenshot index: BUILDER-ONLY REFERENCE `docs/research/assets/competitor-ux-2026-10-03/README.md`. Private screenshots are not shared implementation inputs. This report preserves the relevant observations and their limits.

SHA-256 for historical v0.3.1 HTML: `ac3695f42762ee80faf3302088ec97d31341b638757dc88e042b4e892d571eb6`.

## Language revision after builder feedback

B1, after the v0.2.1 navigation fix, said verbatim: "I do not understand those things on the prototype screen and so I cannot answer your questions, can you repharase". This is direct evidence of a wording problem across the screen. It does not establish which individual accounting concepts B1 misunderstood. The earlier navigation-only explanation was incomplete. Task 1 remains REVISE; no other task receives an invented comprehension verdict.

v0.3.0 rewrites primary screen labels, study explanations, all four test labels, table headings, trading-permission terms, action controls, account labels and neutral prompts. It defines research data, validation data, holdout, rule matches, comparison examples, MOE, WMON and gas. Account examples are prominently called made up. The study's exact counts, returns, cost assumptions, limitations and unopened holdout are retained. The state model is byte-for-byte unchanged from v0.2.1.

Browser evidence: Safari rendered v0.3.0, including the new study heading, all four test labels and the definitions control. A screenshot confirmed the rewritten landing view and controls are readable on the reviewed desktop. Both inline scripts parse. Narrow-screen review remains unverified. No human comprehension pass is claimed for this rewrite.

The user requested explanation, so the next builder response will follow plain-language help. Record it separately as an assisted repeat. Do not compare it to a blind first answer or erase either original response. These wording changes are prototype proposals within existing accepted decisions; they do not approve specification changes or production work.

## Specific terminology feedback and v0.3.1

On 2026-10-04, B1 supplied a crop of the v0.3.0 glossary and said: "these terms need to be more intuitive to the user". The crop contains Research data, Validation data, Holdout, rule match, comparison example and the MOE/WMON/MON/computing-credit explanation. This is terminology feedback, not an answer about the study's result. Preserve it separately from the original first answer and broader language feedback.

v0.3.1 replaces the primary glossary with three purposes: explore the idea with past prices, check again on later prices, and keep a final check unopened. The two study groups are described as times with the required price rise and times without it. A 2% versus 0.5% rise illustrates a rule requiring more than 1%; these are explicitly explanatory examples, not additional research outcomes. The table caption explains 13 / 21 and the positive/negative comparison signs. Funds for token buying, MON transaction fees, and AI/computing credits are listed separately by use. Technical source terms remain available in detailed provenance.

Both inline scripts parse. The state model is unchanged. Safari opened v0.3.1 in a new tab, preserving the previous tab, and expanded the revised explanation. Accessibility state confirmed all three study steps and separate funding labels. A desktop screenshot showed readable study steps and the concrete comparison example. A subsequent scroll attempt failed with noWindowsAvailable; no additional screenshot or narrow-screen verdict is claimed. The effect on human understanding remains unresolved. Task 1 stays REVISE, tasks 2–5 stay UNRESOLVED.

These labels remain prototype proposals. They preserve the accepted experiment and evidence boundaries; they are not accepted specification changes.

## Research-page purpose remains unclear

On 2026-10-04, B1 supplied the v0.3.1 Research landing screenshot and asked: "so what is this page supposed to tell me". This is a request for explanation, not an answer demonstrating comprehension. Task 1 remains REVISE. No first answer is replaced and no pass is inferred.

The controller explained that the page should communicate the study result and the next research choice: four versions of buying after a MOE price rise were examined, evidence was insufficient to choose a strategy, later average results were negative under assumed costs, and the user can keep the report or propose a separately approved fresh test. The report grants no trading permission. Subsequent B1 understanding follows this help and must be recorded as assisted evidence.

Builder observation from the supplied screenshot: experiment instructions and three status boxes occupy much of the landing view before the research explanation. Proposed follow-up is to make the research result, its reasons and the next research choice lead the page, with review instructions secondary. This is a proposed presentation change, not an accepted specification change or an implemented fix.

## Builder-approved five-issue revision, 2026-10-04

The builder accepted the controller's refined layout recommendation and requested all five review issues be fixed in one pass, with Unslop applied throughout the prototype text. This is local revision approval for the existing throwaway prototype. No revised artifact or new comprehension result is established by this record.

Approved layout: the report leads with its question, conclusion, reasons and useful next actions. Contextual conversation sits beside it on desktop and can collapse. On mobile, Ask about this report opens conversation with the report context and a return path. The report must remain understandable without asking the agent to explain its purpose.

The revision must address:

1. Research hierarchy: move walkthrough instructions, participant notes, resets and scenario controls into secondary reviewer tools. Keep study completion, evidence and permission separately understandable without dominating the first view.
2. Plain language across all five tasks: replace internal planning/accounting terms with accurate everyday explanations. Name the affected object, quantity, current state and next action. Unknown values and uncertain outcomes remain explicit; clear wording cannot become false certainty. Keep exact IDs and accounting details expandable.
3. Research conversation and follow-up: add clearly labeled scripted replies about the MOE report. Explain insufficient samples, contrary results, illustrative costs and what a proposed fresh study would need. Show a follow-up proposal beside the action; it does not execute research, open the holdout, create a selected strategy or grant trading permission.
4. Local feedback and focus: target selection reveals the shared close preview immediately. Chat submission preserves useful keyboard focus. Queue/denial/stop confirmations appear at the relevant action, and sticky elements do not hide focused headings. No duplicate economic action or premature holding change.
5. Mobile: compact navigation, stack permission labels and values, preserve selected context and make conversation reachable without reading the entire account record first. Keep consequential settings and stop effects inspectable.

Verify desktop and narrow mobile together, plus keyboard operation and the existing fixture behaviors. Preserve the exact v0.3.1 identity above and earlier responses/reviews. Record the revised version/hash, browser observations and remaining defects after the agent makes changes. Task 1 remains REVISE and tasks 2–5 remain UNRESOLVED until new participant evidence is recorded. Any builder repeat is assisted; a new trader's first attempt is separate. This approval changes no production behavior, Probe A evidence, Probe B authority, paid-call permission or publishing permission.


## Focused revision v0.4.0, 2026-10-04

Artifact SHA-256: `f9d4bcba11bc403243de92c41073070a0aa49b63a23227db4b6ee84be7ebf9ab`. The earlier v0.3.1 hash and all participant feedback above remain historical evidence. This version revises the existing single inline HTML in the private workspace. No production implementation or specification change was accepted by this edit.

The supplied controller critique, BUILDER-ONLY REFERENCE `.impeccable/critique/2026-10-04T08-02-01Z__prototypes-edge-os-frontend-interaction-index-html.md`, and the builder's five-issue approval governed this pass. Prototype's logic/state branch preserved the experiment. Impeccable Operate guided the layout, progressive detail and focus. Karpathy Guidelines limited changes to the existing artifact. Unslop and No AI Slop guided screen copy. Existing Keel/Almanak contextual conversation, Minara/Horizon account views, GT action disclosures and Clawpump funding distinctions remain the layout references. No competitor website research or archive scan was repeated.

### Implemented changes

1. Research starts with the study question, conclusion, reasons and three choices: keep the report, inspect a proposed study, or ask about the report. Instructions, walkthroughs, notes, resets and simulated outcomes are under Review tools. The prototype label is brief. Study completion, evidence and permission remain separately stated.
2. Primary text across all five tasks names the trade, action or permission concerned. Costs, missing prices, unknown transaction results and incomplete gain/loss calculations remain explicit. Exact rule, market, transaction and accounting details expand where needed. Fictional accounts remain labeled.
3. A separate report record supplies scripted research replies. Starter questions concern the actual MOE result, samples and costs; more questions cover the unopened final-check data, permission and a fresh study. Desktop conversation can collapse. Mobile opens conversation with report or exact trade context and return controls. Suggest another study shows a concrete proposal beside the action, with dates, market checks, sample support and budget still requiring agreement. It runs no research.
4. Selecting a close target immediately shows and focuses the same preview used by direct controls. Preview, queue, stop and renewal feedback appears beside the relevant action. Sale confirmation reads the current shared action record rather than an old queue message. Chat submission clears its input and preserves composer focus. Focused headings remain below the sticky navigation.
5. Narrow navigation uses one expandable Page control with ordinary buttons. Permission labels stack above values. Both report and position conversation are reachable directly. Consequential sale and permission settings remain visible before confirmation.

The four MOE variants, contrary findings, exact sample/return figures, cost assumptions, missing data, unopened holdout and unresolved selection remain. Account questions create no financial action. Two same-token positions, exact context, shared action identities, waiting holdings, scoped stops and cumulative accounting remain. Favorable backtests and trial graduation are not prerequisites. The MOE report selects no deployable strategy. No actual Hermes conversation, deployment or independently enforced Q31 inventory permission is established.

### Browser evidence, separate from comprehension

Participant role for these checks: controller/builder-side tool operator. Evidence origin: local Safari screenshots and native accessibility state, plus source checks. These are not trader responses.

The first batched round covered desktop layout, research replies/proposal, permission terms, account context, ambiguous close, queue/unknown holdings, stop behavior and renewal. Chrome viewport control failed to accept 390 and repeatedly lost its window; the attempted 390 × 844 emulation is not evidence. Safari then provided the compact layout after leaving full screen and zooming the same local page.

Observed defects were fixed together: research feedback leaking into account chat; reply focus scrolling away from context; stale queued/1,000-MOE confirmation after a sale had changed; awkward fall-through outcome copy. The compact Page control was changed to an expandable button list. One confirmation round followed, including the narrow checks below and a restored desktop view. No further visual polishing followed.

| Check | Actual result and limit |
| --- | --- |
| Desktop | Safari rendered the leading question, conclusion, reasons and actions with report conversation beside them. Collapsing and reopening conversation worked. Review tools were secondary. Source and native accessibility state identified v0.4.0. |
| Narrow layout | Review tools reported **413 × 523 CSS pixels** in Safari at 150% zoom. Screenshots showed compact Page navigation, permission labels above values, report/trade conversation context and return controls, and stacked sale settings. This is a narrow desktop-browser layout check, not a physical phone, touch or virtual-keyboard test. |
| Research proposal and replies | Suggest another study displayed its concrete, unrun proposal. The report-specific result and cost questions returned scripted content from the report record. The final-check data stayed unopened. Report/account messages no longer shared a feedback slot. |
| Keyboard and focus | Enter submitted an account question. A second question was pasted and submitted without selecting the input again, confirming useful composer focus. Clarification selection focused the exact sale preview; its heading was visible below sticky navigation on desktop and narrow layout. Tab showed a visible focus outline. A complete keyboard-only traversal and assistive-technology audit were not performed; Safari's default Tab behavior skipped some buttons. |
| Exact context and questions | Ask about P-101 carried P-101, Agent A, DEMO-W1 and Monad 143, with exact strategy/market identity expandable. Why did you open this? read DEC-01; How much can you still spend? read the same 10 WMON remaining allowance and 30 WMON available trading funds as the direct account record. Questions created no new trade. |
| Ambiguous close | Close half my MOE produced two trade choices and no sale. Selecting P-101 revealed a 500-MOE preview immediately. Confirmation created ACT-100. It remained the same action in wallet history. |
| Waiting sale and outcomes | ACT-100 queued behind unknown ACT-090 while P-101 retained 1,000 MOE. Sending before resolving the blocker was denied. Resolving the original buy as failed released 10 WMON but retained its attempt and MON fee. A sent sale with unknown result still showed 1,000 MOE. Confirmation then showed ACT-100 Confirmed, 500 MOE remaining and 17.80 WMON returned after trading fees. Buy spending remained 80 WMON. The obsolete queued/1,000-MOE panel no longer appeared. |
| Stops | Stop new buys retained the eligible sale path and tokens. Halt all swaps blocked a new sale preview. Manual-sale preview stated future buying may recur only within current rules and limits; stopping buys blocked that continuation. Already-sent actions remained in history. |
| Continuation and renewal | Optional trial continuation was blocked by its adopted stopping point. An approved, simulated checked time extension kept 80 spent, 10 reserved and 10 remaining. Increasing the shared limit to 150, after exact approval and a separate simulated wallet-rule check, left 60 remaining. Trial stops, holdings, loss records and history remained. Bot limits did not rise with the wallet limit. |
| Source checks | Both inline scripts passed `node --check`. A temporary Node comparison matched the v0.3.1 financial fields, positions and action identities over 20 existing transitions, including partial close, resend, renewal, trial stop and expired-start denial. The report record and scripted research events were added separately. No test files or dependencies were added. |

### Comprehension verdicts after this revision

No new participant answer had arrived when this section was saved. B1's earlier first answers and requests for explanation remain above. Browser checks cannot replace those answers.

| Task | Current human verdict | Evidence and next attempt |
| --- | --- | --- |
| 1. Understand research | REVISE | Earlier B1 feedback established a clarity problem. Revised attempt pending; no new answer and no inferred pass. |
| 2. Review live permission | UNRESOLVED | No participant answer. Request one assisted B1 attempt after Task 1. |
| 3. Inspect positions and conversation | UNRESOLVED | Browser behavior checked; no participant explanation or first answer. |
| 4. Stops and pending actions | UNRESOLVED | Browser behavior checked; no participant interpretation of holdings or stop effects. |
| 5. Continuation | UNRESOLVED | Accounting behavior checked; no participant interpretation of current versus changed permission. |

All further B1 responses are **assisted repeats**, because earlier explanations and review updates were seen. Record each answer verbatim before coaching, with artifact v0.4.0 and the hash above, task, role B1/builder and assistance origin. Ask one neutral question at a time. Keep any trader or teammate attempt separate. No such participant has been invented or recorded.

### Remaining limits and smallest follow-up

No further blocking layout defect was observed in the confirmation round. The compact mobile menu may require horizontal or vertical scrolling when open on a very short viewport; wide research/position tables retain horizontal scrolling. Physical phone behavior, virtual keyboard effects, complete keyboard traversal and screen-reader behavior remain unchecked. Browser tooling failures are review limits, not evidence that the prototype failed its interaction tasks.

The smallest next step is an assisted builder attempt on Research, then the other four tasks one at a time. Before teammate implementation, review the answers and obtain one target trader's separate attempt. Fix only misunderstandings that those attempts reveal. A brief physical-phone check can close the touch/keyboard gap. No new study, favorable strategy, production flow or accounting change is approved by the follow-up proposal.

Accepted inputs remain the existing product decisions and contracts. The five prototype revisions implement the builder's local revision approval. Their transfer into application UI, and the proposed fresh study's exact terms, remain proposals for separate review. No prototype code was promoted, committed or published. No paid call, external runtime integration, wallet action or financial transaction occurred. Active working minutes were not independently measured; browser-control retries were recorded rather than treated as successful checks.

Assisted repeat requested for B1, Task 1, v0.4.0: "On the revised Research page, what does the study tell you about the trading idea, and what would you choose to do next? Reply here in chat. You can say what is still unclear." Safari was left on fresh Research with no scripted replies and Review tools closed. Answer pending; no new verdict recorded.


## Four-finding controller repair v0.5.0, 2026-10-04

Artifact SHA-256: `2ea3e327e8206521788bed11585ea14cd7de8e8a1a203e7d25024bb913be668e`. The v0.4.0 hash, all earlier versions, first answers, assistance records and controller evidence above remain historical evidence. A local v0.4.0 recovery copy was retained outside the repository before editing. Only the existing single HTML and this findings report were changed for this repair.

The builder authorized four corrections: a consistent simulated UTC clock and expiry boundary, separate time-only and limit-only proposals, feedback attached to its page/action, and a simpler permission review. Prototype's logic/state branch governed the existing five tasks. Impeccable Operate supported hierarchy, expandable detail, narrow layout and focus. Karpathy Guidelines, Unslop and No AI Slop supported the focused implementation and ordinary language. No new framework, test infrastructure, production application or specification change was introduced.

### Correction to the earlier browser evidence

The v0.4.0 checks did not establish consistent time or isolated permission changes. Source inspection found that every reducer event advanced the displayed clock, the expiry string was not checked against it, and both renewal proposal types extended expiry. The shared feedback slots and screen-reader announcement could also carry an account result onto Research. The four controller findings remain valid failures of that version. Its financial comparison over 20 transitions did not cover these properties and must not be read as evidence that they worked.

### Changes in this version

- All active examples begin at **2026-10-04 11:59 UTC**, before their adopted 12:00 UTC end. One in-memory UTC clock supplies current time, action/reply timestamps and expiry checks. Recorded fixture prices and previous action times are separately labeled. Pages, questions, proposals and approvals leave time fixed. Review tools provides explicit minute/day advances and a move-to-end-time control.
- At or after the adopted end, permission becomes expired. New sale previews, queue confirmations, submissions, retries and continuation cannot create new swaps. A queued request, unknown transaction, holdings and exit reservations remain. Checking already-sent transaction results still works. Existing previews update their permission checks when time or stops change. A before-start example cannot start after its end.
- Review more time proposes only an end time. Review a 150 WMON buy limit proposes only the shared buy limit. Both show current/proposed values and unchanged terms. Proposals and cancellation leave adopted permission unchanged. Exact simulated approval followed by a separate simulated wallet-rule check is required to adopt the proposed terms. A proposal whose end time has passed is rejected at verification; the screen explains the need to cancel it and review more time. It never silently extends a spending proposal.
- The 100-to-150 example preserves 80 WMON spent and 10 reserved, leaving 60 unused shared allowance. Wallet cash remains 120 WMON; individual bot limits remain 70 and 30. Stops, losses, holdings and pending actions are kept. More time adds no allowance.
- Feedback is stored by page and action. Navigation and resets clear the global announcement. Shared action history and participant notes remain separate records. Proposal approval/check/cancel controls and their feedback are together. After a completed check or cancellation, focus returns to the local continuation result. Purpose-selection feedback sits beside that selection.
- Permission review leads with the agents' rules, shared and per-buy limits, end time and stopping behavior. Wallet funds and unused spending permission are separate. Complete adopted settings, gas, accounting and technical identities remain inspectable in expandable detail before confirmation. A primary Review before trading starts control opens the before-start example. Its account conversation is also reachable on a narrow screen.

The real MOE report and its scripted report record are byte-for-byte unchanged from v0.4.0. All four variants, contrary findings, sample/data/cost limitations, unresolved evidence, absent selected strategy and unopened holdout remain. Accounts, authority and transaction outcomes remain fictional. These checks establish no favorable candidate, actual Hermes reply, real deployment or independently enforced Q31 inventory permission. Backtesting and trial graduation remain optional.

### Actual checks, separate from human comprehension

Evidence origin: native Safari accessibility state and rendered screenshots of the local HTML, plus local source/syntax checks. Operator role: controller checking the builder-owned prototype. These are **browser observations, not participant answers**.

One first batched browser pass covered desktop, narrow layout, keyboard submission and the required state cases. It found an enabled queue button in a preview opened before expiry and a stale global announcement after Reset all. Both were repaired together, along with local wording and focus adjustments. One confirmation pass followed. No further visual polishing followed.

| Check | Observed result |
| --- | --- |
| Just before, at and after expiry | Active at 11:59 UTC, expired at 12:00, still expired at 12:01. Reading pages and scripted account questions left the clock at 11:59. An existing sale preview showed expired permission and a disabled queue button after advancing to 12:00. |
| Queued sale at expiry | ACT-100 retained its queued state and P-101 retained 1,000 MOE. Submission was blocked at 12:00 and 12:01. ACT-090 remained unknown with its reservation until an explicit simulated failed-result check released that buy reservation. Expiry itself released nothing. |
| Already-sent result after expiry | A submitted sale with unknown result still showed 1,000 MOE. Expiry blocked further sending while preserving the transaction. Its later simulated confirmation showed ACT-100 Confirmed, 500 MOE remaining, 20 WMON remaining cost basis and 17.80 WMON returned. Buy spending remained 80; the additional tracked realized loss was 2.20 WMON and MON fees stayed separate. |
| Time-only proposal | Displayed unchanged buy limits and a later proposed end. Approval alone left current terms unchanged. The separate simulated check adopted the end time and retained 80 spent, 10 reserved, 10 unused allowance, wallet cash, losses, holdings, unknown ACT-090 and stops. |
| Limit-only proposal | Displayed 100 / 150 WMON and the same current/proposed end time. After approval and simulated checking, it showed 60 unused shared allowance with 80 spent and 10 reserved. Wallet funds and individual bot limits did not increase. |
| Expired or elapsed proposal | A limit-only proposal after expiry retained the expired end. Even after approval, verification declined it and kept the adopted limit at 100. A time proposal was also approved, then the clock advanced past its proposed end; verification declined it and left permission expired. |
| Cancellation | Cancelled both proposal types. Current end time, buy limit, active/expired state, stops and accounting stayed unchanged. No added permission appeared. |
| Stops and continuation | Stop new buys allowed an eligible sale while authority remained active. Active Halt all swaps blocked its sale preview. A wallet buy stop survived both checked permission changes. An adopted trial stop blocked continuation and stayed adopted through an elapsed renewal proposal. |
| Same-token clarification and shared records | Close half my MOE asked which of two positions and created no action. P-101 selection immediately showed the 500-MOE preview. Queueing created ACT-100, seen through conversation and direct wallet history. Pending and confirmed holdings came from the same records. |
| Cross-page feedback | After questions, stops, queued/submitted/unknown/confirmed sales and renewal actions, returning to Research showed its report context without those account confirmations. Reset all also cleared the obsolete announcement. Shared transaction history remained available on account pages. |
| Before-start review | Desktop showed the direct before-start entry, inactive permission, primary rules/limits/end/stop sections and a disabled start until acknowledgement. Complete terms expanded before confirmation. The first pass also acknowledged terms and displayed a fictional ongoing start; no favorable-backtest gate appeared. |
| Narrow layout | Safari reported **413 × 523 CSS pixels** at 150% zoom. Permission labels stacked above values, complete terms could expand, account conversation opened with DEMO-W1/Monad context and a return control. Compact Page navigation worked. This is a narrow desktop-browser check, not a physical phone or virtual-keyboard test. Restored desktop was **1512 × 859 CSS pixels**. |
| Keyboard/focus | Enter submitted a question; a second question was entered and submitted without selecting the composer again. Neither advanced time. Preview headings and local continuation feedback stayed below sticky navigation. Tab was exercised, but Safari's default keyboard navigation still skips some controls; a complete keyboard-only or screen-reader audit was not performed. |
| Source checks | Both inline scripts passed `node --check`. A temporary manual reducer exercise printed the clock/permission/accounting states for reads, expiry, queued/sent sales, separate proposals, cancellation, elapsed verification and reconciliation. The MOE Report block compared equal to v0.4.0. No external request API, dependency or persistent store was added. Local note records remain outside reset state; no fake participant response was entered to test notes. |

Safari changed to another tab during the fullscreen transition. The review recovered the exact local v0.5.0 tab by its title, URL and version and completed the confirmation cases. Another older prototype tab remained untouched. This interruption is not evidence of a prototype state failure.

### Human verdicts and assisted repeat

No new comprehension answer arrived during this repair. The earlier v0.4.0 Task 1 prompt was unanswered; the builder instead requested this repair. Do not count that request as a comprehension attempt.

| Task | Verdict | Participant evidence and next step |
| --- | --- | --- |
| 1. Understand research | REVISE | Earlier B1/builder wording and navigation failures remain. Request an assisted repeat on v0.5.0; first answer pending. |
| 2. Review live permission | UNRESOLVED | No participant answer. Ask after Task 1, using the accessible before-start example. |
| 3. Positions and conversation | UNRESOLVED | Browser cases worked; no human explanation recorded. |
| 4. Stops and pending actions | UNRESOLVED | Browser cases worked; no human interpretation recorded. |
| 5. Continuation | UNRESOLVED | Browser cases worked; no human explanation of time versus spending recorded. |

Record future B1 answers verbatim as **assisted repeats**, with this version/hash, role and assistance origin, before coaching. Ask one neutral task at a time. Keep any target trader or teammate's first attempt separate. Missing trader participation leaves target-user comprehension unresolved.

### Remaining problems and smallest follow-up

No further blocking defect in these four repair cases was observed in the confirmation pass. Human clarity is still unproved. Full keyboard traversal, screen-reader behavior, physical-phone touch and virtual-keyboard layout remain unchecked. Wide research/position tables still scroll horizontally; very short screens require vertical scrolling to inspect all terms. Financial eligibility, real data freshness, policy binding and execution remain authored assumptions rather than qualification evidence. A higher shared wallet limit still does not raise an individual agent's limit.

The smallest next step is the five assisted builder attempts, one at a time, then one target trader's separate attempt before implementation. Revise only the misunderstandings those attempts reveal. A brief physical-phone and keyboard check can close the remaining device-access gaps. No new specification change is accepted here; the controller repair applies already accepted time, approval and cumulative-accounting requirements. Production transfer and any new study remain separately authorized work.

No paid calls, external runtime integration, wallet actions, financial transactions, commits, pushes, issues or publication occurred. Active minutes were not independently measured; no timing claim is made.

Assisted repeat requested for B1, Task 1, v0.5.0: "On the Research page, what does the study tell you, and what would you choose to do next? Reply here in chat. You can say what is still unclear." Safari is on Research with no scripted replies and Review tools closed. First answer pending. Record it before coaching.


## Customer and Reviewer separation, v0.6.0, 2026-10-04

Artifact: the existing single-file prototype, SHA-256 `edfd792fcc503bcbe679478401fcf5f2c3563e1d66b901d612c09e0997a994c2`. Previous v0.5.0 hash: `2ea3e327e8206521788bed11585ea14cd7de8e8a1a203e7d25024bb913be668e`. Earlier versions, failures, assisted-attempt records and checks above remain evidence; this revision does not replace them.

### Builder feedback and revision question

Evidence origin: the builder's direct session feedback about the preceding page, participant B1, builder role, already assisted through earlier explanations and revisions:

> The pages contain so much detail that I cannot tell what customers will see versus what exists for testing. This is unresolved comprehension feedback. An explanation in chat does not fix the page.

This is an observed overload and presentation failure, not an answer to the pending v0.5.0 Task 1 prompt. That prompt remains unanswered. The current revision asks: can a beginner understand what happened, what the agent may do and what their next action changes without reading testing instructions or technical records? A controller inspection cannot answer that human question.

### Changes to the authorized experiment

Customer view now opens by default. Research, Permission, Open trades, Stop trading and Trading settings are independent pages, without numbered stages. A brief notice discloses fictional accounts, fixed example replies and no real money movement.

Reviewer view holds the five comprehension tasks, guided steps, resets, scenario loading, simulated clock, transaction outcomes, changed-permission verification, participant notes, saved attempts, viewport dimensions and detailed records. Switching views preserves the current account, actions, conversation and proposal. Scenario loading and resets intentionally restore fixtures. Notes remain in local memory; reloading clears them.

Research leads with the question, MOE/WMON market and September 25–30 period, unresolved conclusion, reasons, limits and next choices. The four numeric variants, contrary observations, missing data, delay assumptions, cost assumptions and sources remain in labeled details. Run identifiers, dataset hash and recorded computing usage are reviewer details. A concrete fresh-data study proposal appears beside its action and runs nothing. Research and its conversation display the same market and period. Replies remain labeled examples.

The other customer pages lead with rules and consequential limits, identifiable agent trades, pending holdings, separate stop and sale choices, and four continuation choices. Wallet funds, buy permission, MON fees and AI credits remain separate. Unknown prices and costs remain unknown. Complete permission terms can be inspected before approval. Conversation and confirmations use agent names; exact trade, rule and action references remain inspectable. The financial reducer and all four numeric MOE variants compare byte-for-byte equal to v0.5.0. Only account-answer wording and page presentation changed; no financial transition was added.

Skills used: Prototype logic/state, Impeccable Operate, Unslop, No AI Slop and Karpathy Guidelines. The user's customer/reviewer separation overrides default prototype instructions to expose all test controls in the main experience. No new plan, framework, dependency or production transfer was created.

### Actual browser checks, separate from comprehension

Evidence origin: native Safari screenshots and accessibility state of the local prototype, plus source comparison and syntax checks. Operator: controller. No invented participant response was entered or saved.

The first inspection batch covered desktop and narrow Customer/Reviewer views, report actions, permission review, same-token clarification, sale preview, stop and renewal cases. It found internal IDs in customer responses, redundant technical status, a history link that did not expand its record, and a reviewer reset focus target on hidden customer content. Those were repaired together. A confirmation pass covered the repaired presentation and the financial cases below. That pass exposed duplicated words in some generated feedback and raw IDs in the accessible announcement; these received a small copy correction and an affected-feedback check. No additional visual polishing followed.

| Check | Actual observation |
| --- | --- |
| Default and separation | Reload opened v0.6.0 Customer view. Customer accessibility content contained no simulated-time, scenario, transaction-outcome or participant-recording controls. Reviewer exposed those controls and the five tasks. The prototype notice stayed available. |
| Desktop and narrow layout | Desktop reviewer read 1512 × 859 CSS pixels. Narrow reviewer read 413 × 523 at 150% Safari zoom. Customer permission labels and values stacked, complete terms expanded, conversation opened with account context and a return control. Reviewer controls wrapped and its sections stacked. This is a narrow desktop browser check, not a physical phone test. |
| Report and conversation | Same MOE market and dates appeared in both. Suggested questions produced labeled example replies. Two consecutive typed questions submitted with Enter without reselecting the composer. Back to report worked at narrow width. Four variants and data-source details expanded; the proposal stated that nothing runs and final-check data stay unopened. |
| Before-start permission | Reviewer loaded the before-start example; Customer showed not-started permission, trading rules, 100 total / 30 per-buy limits, end time and stop effects. Full terms expanded before acknowledgement. Start was disabled until acknowledgement, then started only the fictional account. Existing fixture spending and holdings were retained. |
| Same-token request | “Close half my MOE” asked which agent's trade. It created no sale. Choosing Agent A immediately opened the 500-MOE preview with its exact underlying context. Approving requested one waiting sale; 1,000 MOE remained held. Direct and conversational controls still used the same model action identity. |
| Pending sale and history | The corrected recorded-action button opened the existing action history. An earlier unknown buy blocked the new sale. Reviewer checked that buy as failed, sent the queued sale and made its result unknown. Holdings stayed at 1,000 MOE until confirmation. |
| Expiry and result checking | Active example began at 11:59 UTC. At 12:00 permission became expired and an original-transaction retry was blocked without clearing holdings/reservations. A previously sent sale could still be confirmed: 500 MOE remained, 17.80 WMON returned, total buy spending stayed 80. At 12:01 permission remained expired and the 250-MOE sale request was disabled. Reading and questions did not advance time. |
| Separate proposals and cancellation | Limit-only showed 100 / 150 with the same end. Time-only showed a later end with the same current buy limit. Cancelling left adopted terms unchanged. Approval alone left current terms in force until the Reviewer check. An expired limit-only proposal failed verification and did not activate permission. |
| Higher spending and preserved stops | With 80 spent and 10 reserved, a checked 150 limit showed 60 unused permission, the same wallet funds, 1,000 / 600 MOE holdings, -10 WMON known result and Agent A's buy stop. A later time-only proposal kept 150 / 150; cancelling preserved it. Individual agent limits remained separate. |
| Stop versus sale | Stop new buys preserved holdings and existing eligible sales. Stop all buying and selling disabled the sale request while retaining 1,000 MOE. Customer, Reviewer records and returned Customer page agreed on the stop. Sale and stop explanations retained possible re-entry under active rules and permission. |
| Page-local feedback | After approval, questions, pending and confirmed sale actions, stops and continuation, returning to Research showed only its report/conversation context. Shared account history remained available. View switches did not reset state. |
| Focus and feedback | Choosing the ambiguous target revealed the preview; conversation returned to its record; keyboard submission preserved composer focus. Visible focused headings stayed below compact sticky navigation. Reviewer reset now focuses its own tools. Internal identities remain in expanded records rather than customer confirmations. Full keyboard traversal and screen-reader operation were not audited. |
| Source checks | Both inline scripts passed `node --check`. Financial transition code and all four numeric variant rows compared equal to v0.5.0. No external runtime, dependency, persistent storage or wallet connection was added. |

### Human findings and remaining work

| Task | Verdict | Participant evidence at v0.6.0 |
| --- | --- | --- |
| 1. Understand research | REVISE | Earlier B1 failures and current overload feedback remain. Revised-page assisted answer pending. |
| 2. Review permission | UNRESOLVED | No human task answer recorded. |
| 3. Inspect trades and ask questions | UNRESOLVED | No human task answer recorded. |
| 4. Stops and pending sales | UNRESOLVED | No human task answer recorded. |
| 5. Continue or change permission | UNRESOLVED | No human task answer recorded. |

No separate trader or teammate participated. No comprehension task passes from browser checks. B1's next answers must be recorded verbatim as assisted repeats before coaching, with this version/hash and role. A trader's first attempt is separate evidence.

No blocking defect was observed in the exercised state cases after correction. The revised beginner experience remains unproved. Complete keyboard-only navigation, screen-reader use, physical-phone touch/virtual-keyboard layout and participant-note entry/export were not checked in this revision. Expanded research tables still require horizontal scrolling at narrow widths. Fixed replies support only their existing questions and request patterns; arbitrary natural-language trading requests are not established. The before-start fixture deliberately retains existing account history and spending; whether a beginner interprets that correctly also needs human evidence.

The smallest next step is one assisted comprehension attempt at a time, beginning with Research, then a separate target trader's first attempt. Make only the changes supported by those misunderstandings before teammate implementation. Current presentation changes apply the builder's authorized prototype revision; no proposed specification change has been accepted. Probe A remains closed and Probe B unchanged. Real execution and Q31 inventory enforcement remain unqualified.

The revised customer report was reopened in Safari with empty example conversation and details closed. Pending B1 assisted Task 1 question: “Looking only at the Research page, what do you think happened, and what would you do next?” Reply is to be recorded before explanation. No paid call, live AI, wallet connection, financial action, dependency, commit or publication occurred. Active work minutes were not independently measured.


## Builder-approved five-controller repair, 2026-10-05

The builder explicitly approved all five findings from the v0.6.0 controller critique, BUILDER-ONLY REFERENCE `.impeccable/critique/2026-10-04T21-50-01Z__prototypes-edge-os-frontend-interaction-index-html.md`, and selected a fresh first-activation example. Approval covers local repairs and bounded browser verification of the existing single-file experiment. It grants no model/provider call, wallet action, production implementation, commit, push, merge or publication.

Approved repairs: restore compact independent status; bind conversation entries, drafts and return links to their named context; expose guided-step outcomes and task-specific scenario controls; separate empty first activation from existing-account continuation; return useful keyboard focus after cancelling a sale preview. Preserve real MOE evidence, prior feedback, five tasks and Customer/Reviewer separation. Advancing a step does not count as comprehension. This paragraph records the repair approval; completion and evidence follow separately.

## Five-controller repair result, v0.7.0, 2026-10-05

Artifact SHA-256: `68de60af412dc404a7703c7bae9671a194730307d1a6de5dd260a4c575547351`. The retained v0.6.0 artifact hash is `edfd792fcc503bcbe679478401fcf5f2c3563e1d66b901d612c09e0997a994c2`. The critique fingerprint matched the artifact before editing. Earlier failures, feedback, review findings and assisted-attempt records above remain unchanged. No participant answered the pending v0.6.0 research question; a repair request is not a comprehension answer.

### What changed

1. A compact summary is visible across Customer and Reviewer pages. Agent operation uses the current account, selected trade or chosen stop scope. It names pending-result or stop reasons. Evidence and permission remain independent, with permission expiry and unused shared buy permission. Expandable detail explains why the real unresolved MOE report neither grants authority nor prohibits every other strategy. The fictional account's rules remain separately labeled.
2. Every conversation entry selects report, account, shared settings or exact trade context. Drafts and conversation feedback are separate by context, including Agent A versus Agent B. View switching retains the same draft. Report questions stay in report conversation. Back to trade selects the attached trade on Open trades, including a return from Settings. Settings-specific suggested questions explain time-only and spending-only changes.
3. Reviewer steps show their actual outcome nearby, with the affected holdings, spending and permission or report boundary. Each available step and the latest outcome have a View this step in Customer view control that retains the scenario and selected record. Scenario controls are grouped under the current task. The clock and detailed records are expandable. Research has no transaction simulations in its current task controls. Participant notes and saved attempts remain reviewer-only. Step progression creates no comprehension verdict.
4. Load first activation and the permission walkthrough explicitly load a funded wallet with 120 WMON and 0.8 MON, zero consumed/reserved trading allowance, no agent positions, actions or previous trading results. Proposed limits and rules appear before approval. First activation does not create a trade. Load existing account remains separate and retains its 80 spent, 10 reserved, two MOE positions, unknown buy, losses and history. Ordinary page/view navigation loads neither scenario.
5. Cancelling a sale preview returns focus to that trade's half-sale or full-sale review button. Cancellation confirms unchanged holdings and no new request. The sale result panel no longer implies that a cancelled preview created a recorded sale. Keyboard navigation can continue from the restored trigger.

Prototype logic/state led the repair. Impeccable Operate supported hierarchy, scope, compact navigation and focus. Karpathy Guidelines constrained changes to the requested paths; Unslop and No AI Slop were applied to new and affected visible text. All four real MOE numeric variants, contrary findings and unopened final-check data remain available. No new study or production strategy was created.

### Checks performed, separate from participant comprehension

Evidence origin: controller-operated native Safari screenshots and accessibility state, inline-script syntax checks and temporary manual pure-model checks. There was one batched first inspection covering desktop and narrow layout, one batch of fixes, then a confirmation pass. The first inspection found page focus scrolling past the summary, retained expanded mobile navigation, stale trade-attachment feedback in settings conversation, internal question keys used as visible labels, and misleading zero-reservation/cancelled-sale wording. These were corrected together. No further UI edit followed the confirmation pass.

| Check | Actual evidence |
| --- | --- |
| Visible status and scope | Desktop confirmation showed operation, evidence and permission together above the report. Research displayed the real unselected MOE result separately from the fictional account's active permission. Trade selection scoped operation to Agent A or B; wallet stops and expired authority displayed their reasons. Supporting detail explained the independence of the report and the authored account permission. |
| Report/account/settings draft separation | An unsent report draft was absent from the trade and settings composers and returned when Research reopened. A trade draft stayed in the same trade context during view changes. Asking about shared settings selected its own context and empty composer rather than retaining the trade draft. Settings replies no longer displayed earlier trade-attachment feedback. |
| Exact trade and per-trade drafts | Agent A's draft did not appear when Agent B was attached. Agent B's draft survived Customer/Reviewer switching. From Settings, Back to trade reopened Agent B's exact record and retained its draft. Exact wallet/network/agent/rule references remained available in requested details. |
| Named suggested replies | Settings questions displayed their ordinary question label and explained more time, more spending and unchanged accounting. Asking a question did not change market time or submit a trade. Report replies remained in report context. |
| First activation | The before-start customer page showed proposed terms, not-granted permission, 0 spent, 0 set aside, no pending buy, 70 remaining for Agent A and 30 for Agent B. Approval activated only the example. Reviewer records afterward still showed no holdings/actions/results, 0 spent/reserved and 100 unused shared permission. |
| Existing-account separation | Only explicit scenario controls or starting/resetting a walkthrough changed examples. Loading the existing account restored 1,000/600 MOE, 80 spent, 10 reserved, the unknown original buy and -10 WMON known result. Page and view switches retained the current example. |
| Guided outcomes and keyboard navigation | Starting the permission walkthrough and loading its first step displayed its actual empty-account outcome. A step-view button opened that scenario's customer page. In the position walkthrough, Option-Tab and Enter from the outcome opened Customer conversation for the exact attached trade. Narrow confirmation showed visible focus on its conversation heading and closed compact navigation. Steps did not create participant answers or passes. |
| Cancellation by keyboard | Cancelling the half-sale preview returned to its review trigger. Option-Tab then Enter opened the full 1,000-MOE preview. Cancelling it returned to its full-sale trigger. This exercised continued keyboard navigation rather than only observing source code. |
| Same-token clarification | In narrow Customer conversation, Close half my MOE asked which of two trades and created no sale. Selecting Agent A immediately showed the same 500-MOE preview used by direct controls. |
| Pending holdings and reservations | A 500-MOE request created one queued sale while 1,000 MOE remained held and the unknown original buy retained its 10-WMON reservation. Explicitly checking that original buy as failed released its reservation; sending the sale and making its result unknown still retained holdings and required sale capacity. |
| Expiry and reconciliation | At 12:00 UTC, permission expired and the same-transaction retry was blocked. A previously sent unknown sale could still be confirmed, leaving 500 MOE and returning 17.80 WMON while cumulative buy spending stayed 80. At 12:01 permission remained expired. A limit-only approved proposal with the expired end was rejected by the simulated permission check. |
| Stops and renewal | A buy stop retained eligible selling rules and holdings. Existing-account wallet buy stops survived a checked 150-WMON limit, which showed 80 spent, 10 reserved and 60 unused permission. A later time-only proposal kept 150/150 and a later end; cancelling retained adopted terms. First-pass and pure-model checks retained losses, reservations, pending actions and individual agent limits. |
| Desktop and narrow layout | Desktop was restored to 1512 × 859 CSS pixels. Narrow Reviewer reported 413 × 523 at 150% Safari zoom. Customer permission terms stacked, conversation kept visible context and a return path, reviewer tools stacked, and task navigation closed after selecting a page or viewing a step. This was a narrow desktop-browser check, not a physical phone. |
| Lightweight checks | Both inline scripts passed node --check. A temporary pure-model comparison matched v0.6.0 financial projections after 19 scoped stop, sale, expiry, reconciliation, renewal and continuation events. The fresh fixture had no previous trading, and all four MOE numeric variant rows compared equal. No framework, dependency or persistent store was added. |

Safari changed active surface during initial inspection, and one confirmation capture reported an OS screen-capture failure. The controller re-read the current local tab and completed affected checks. These tool failures are recorded as review interruptions, not prototype failures. Another old prototype tab and unrelated user tabs were left untouched. No private account information was copied into the fixture or findings.

### Comprehension verdicts and remaining limitations

| Task | Verdict | Evidence |
| --- | --- | --- |
| 1. Understand research | REVISE | Earlier B1 wording, navigation and overload failures remain. No new human answer. |
| 2. Review permission | UNRESOLVED | Fresh fixture verified mechanically; no human explanation of its authority or limits. |
| 3. Inspect trades and conversation | UNRESOLVED | Context and action mechanics checked; no participant task answer. |
| 4. Stops and pending sales | UNRESOLVED | Browser/model checks do not establish participant understanding. |
| 5. Continue or change permission | UNRESOLVED | No human explanation of time, spending or preserved accounting. |

B1 is the builder and has received previous explanations. The next attempts remain assisted repeats and must be recorded verbatim before coaching. No separate trader or teammate participated. Full keyboard-only traversal, a screen-reader audit, physical-phone touch/virtual-keyboard layout and participant-note export were not verified in this pass. Wide detail tables still scroll horizontally. The compact summary remains on each page above its content; scrolling to a specific record can move it out of the viewport. The scripted conversation supports only the existing question and request patterns, not arbitrary language understanding.

No further blocking defect was observed in the exercised repairs during confirmation. The experiment's beginner-comprehension question is still unanswered. The smallest follow-up is the five assisted builder tasks, one at a time, followed by a separate trader's first attempt. Do not turn the completed repairs or step counts into passing verdicts. Real execution, independently enforced inventory authority and financial safety remain unqualified. The fixes apply existing accepted behavior and the approved fresh fixture; they accept no production specification change. Probe A stays closed and Probe B unchanged.

The revised customer Research page is open in Safari with empty draft and example conversation. Next B1 assisted question: "Looking only at the Research page, what do you think happened, and what would you do next?" Record the answer with v0.7.0/hash and role before explaining. No real model, wallet or financial call, commit, push, merge or publication occurred. Active minutes were not independently measured.


## Research/account transition repair approval, 2026-10-05

The builder authorized a focused local repair of the existing five-task prototype, including explicit real-report versus fictional-account context, account entry, agent/position ownership, empty first activation and Customer/Reviewer separation. The builder also explicitly authorized two isolated read-only Impeccable critique agents after implementation. This grants no production, external model, wallet, financial or publication authority. The request identifies continuing transition confusion; it is not an answer to the pending assisted research task.

The current findings report controls executed prototype history. Stale status remains elsewhere: the specification introduction and Compass workflow still describe the frontend as unstarted; the older frontend packet paragraph names v0.3.1 while its current repair paragraph names v0.7.0; the workspace handoff also says unstarted. These are historical/status inconsistencies, not a withdrawal of the builder's explicit local authorization. No accepted product decision, closed Probe A evidence or Probe B scope changed in this repair.

## Research/account transition repair result, v0.8.1, 2026-10-05

Final artifact SHA-256: `76d5f57b5de4ac02ab17be4012b7103a8c5ab0a05e9dfb13be46c1de367c250c`. Independently critiqued first-build v0.8.0 SHA-256: `66c775caed53613d28d74cd9c75487076d54fb506b43d29dca9ca42398efeb7c`. Earlier v0.7.0 hash and all prior feedback, failures, assistance and human verdicts remain above. Local recovery copies of v0.7.0 and assessed v0.8.0 were retained outside the repository.

### What changed and why

Research now has a report-only status and conversation. Agent activity and wallet permission no longer appear above the real MOE investigation. Its question, market/period, unresolved conclusion, reasons, limitations and study choices remain. The report selected no strategy. Separate trading rules still require their own execution checks and adopted permission; this report does not prohibit every other strategy.

Explore an example trading account opens an explicit two-choice entry. Before trading starts uses the empty funded fixture; Already trading uses the existing account with two MOE positions, spending and an unknown buy. Both are identified as fictional and unrelated to the recorded investigation. Once an account is loaded, its identity stays in sticky customer navigation. Returning to Research and re-entering the account preserves the loaded records. Ordinary page and Customer/Reviewer switches do not load a different fixture. Only explicit example choices, reviewer loads or resets do so. An account reset retains the report conversation/proposal record.

Agent A's existing price-rise rule and Agent B's existing price-fall reversal rule are introduced in permission review and expandable account explanation. The positions table says which agent holds each quantity. No extra qualified strategy behavior was invented. Account-wide, exact trade and shared-settings conversation remain distinct; exact references and full histories remain expandable. Reviewer still owns time/scenario/transaction simulation, walkthroughs, debug records and participant notes.

The independent inspection found stale preview guidance, premature requested wording, a nonexistent current-trade reference in the empty fixture and repeated notices. One correction batch replaced guidance after cancellation, used selected for review before confirmation, removed Agent B's existing-trade wording at first activation, consolidated account identity and labeled a retained trade conversation on Settings. Before-start conversation no longer suggests asking why a purchase occurred. The desktop conversation uses one panel scroll rather than a nested message-log scroll; submission reveals its focused composer. No further UI edit followed the confirmation pass.

Prototype logic/state governed the experiment. Impeccable Operate supported context and hierarchy; Karpathy and Ponytail lite constrained this to existing helpers and one file. The simpler repair reused navigation, scenario loading and conversation records instead of adding an onboarding system. No AI Slop and Unslop reviewed the new and affected customer text. Existing contextual-record lessons from Keel/Almanak, direct account lessons from Minara/Horizon, GT's expandable history and Clawpump's separate capital/compute funding remain references. The current pass inspected the screenshot index and the Almanak strategy-chat and Horizon activity captures for context and ownership. No website research or archive scan was repeated. Vendor results and enforcement claims remain unverified.

### Browser and regression evidence

Evidence origin: controller-operated native Safari screenshots/accessibility trees, independent native Safari/Chrome assessments, syntax checks and a temporary runnable pure-state check. These are builder-side checks, not participant comprehension. One post-build inspection batch covered desktop and narrow views, then findings were corrected together and one confirmation round followed. Native focus changed during concurrent review-tab creation and once before reload; fresh local-tab state recovered the checks. These are tool interruptions, not prototype failures.

| Check | Actual result and limits |
| --- | --- |
| Research/account boundary | Reloaded Customer Research showed only the real investigation status, MOE market/period, unresolved result and contextual report conversation. Account entry explained separate fictional records. Account sale/stop/renewal feedback did not appear on return to Research. Four variants still expanded with the original numeric rows. |
| Fresh versus existing | First activation displayed 120 WMON funded cash, 0 spent/reserved, no agent trades or pending actions and proposed terms. After simulated activation Reviewer records still had no holdings/actions/previous results and 100 unused permission. An explicit existing-account load restored 1,000/600 MOE, 80 spent and 10 reserved. First activation and ordinary navigation never imported those existing positions. |
| State and context preservation | Research re-entry retained the loaded account after a checked extension and partial sale: 80 spent, 500/600 MOE, stops and adopted end time. Report conversation remained in report context. An unsent trade draft survived Customer/Reviewer switching and was absent from account/settings/report composers. Settings-specific Ask selected settings; Back to trade returned the attached Agent A record. |
| Ownership and same-token request | Agent descriptions were inspectable and table rows named the holding agent. Close half my MOE created a target choice, no sale. Agent A selection opened the shared 500-MOE preview immediately. Final wording says selected for review. Direct and conversational controls still use the same action contract. |
| Cancellation and focus | Cancelling half-sale returned to its trigger. Option-Tab then Enter opened the full 1,000-MOE preview. Cancelling it retained holdings and no sale request. Stale preview guidance was replaced with the scoped cancellation result. Retained trade conversation on Settings had an explicit scope notice and return link. |
| Pending sale, stops and expiry | A 500-MOE sale request retained 1,000 MOE and the earlier buy's 10-WMON reservation. A wallet buy stop retained eligible exits. Checking the earlier buy as failed released its reservation; sending and losing the sale acknowledgement retained holdings. At 12:00 permission expired and retry was blocked. Reconciliation of the already-sent sale left 500 MOE and returned 17.80 WMON, with 80 buy spending preserved. A halt separately disabled new sale approval without selling holdings. |
| Renewal and cancellation | A spending-only proposal kept the end time and warned when it had passed. Cancellation changed no adopted terms. A separately approved/checked time extension preserved the 100 limit, consumption, retained holdings and wallet stops. On an explicitly reloaded existing account, a checked 150 limit kept 80 spent/10 reserved, leaving 60 unused permission and unchanged wallet cash. The pure-state check also confirmed time-only limits, cancellation, losses and individual stops. |
| Customer/Reviewer and walkthrough | Customer exposed product controls and no clock, transaction-result or participant-recording controls. Reviewer exposed task-specific tools and records. A current guided step opened Customer conversation for exact Agent A, with visible focused heading at narrow width. Advancing a step saved no participant answer or comprehension pass. |
| Desktop and narrow | Safari first-batch desktop was 1512 × 859 CSS pixels; narrow Reviewer reported 413 × 523 at 150% browser zoom. Confirmation showed stacked permission labels, expandable complete terms, sticky fictional-account identity, report/trade conversation context and return controls, visible focus and closed compact navigation after selection. Desktop was restored to 100% fullscreen. This is not a physical-phone test. |
| Conversation reading | Two consecutive questions submitted with Enter and the composer remained visibly focused. The inner message-log scroll was removed; the outer desktop conversation panel still scrolls for long replies. Scripted replies are labeled examples. Questions left time and financial state unchanged. |
| Lightweight regression | Both final inline scripts passed node --check. The entire Report and pure Model script is byte-for-byte equal to v0.7.0, preserving all four variants, unopened holdout and financial transitions. `/tmp/edge-v08-check.js` passed assertions for fresh activation, read-only time, ambiguity, pending holdings, expiry/reconciliation, stops, separate proposals, cancellation and cumulative accounting. No framework, dependency or persistent store was added. |

### Independent critique and limits

The Impeccable critique snapshot, BUILDER-ONLY REFERENCE `.impeccable/critique/2026-10-05T09-59-08Z__prototypes-edge-os-frontend-interaction-index-html.md`, assesses the exact v0.8.0 bytes named above, before the correction batch. A `/root/context_review_a` assessed design and comprehension; B `/root/context_review_b` ran detector/browser evidence. They had separate prompts and new native tabs, neither saw the other's assessment, and A finished before B output entered controller synthesis. Neither edited project files.

A scored 28/40, with four P2 issues and no P0/P1. B's exact-file detector exited 0 with `[]`, zero findings, no rule locations or false positives. The detector missed interaction confusion; a clean scan is not a passing UX verdict. B also observed mismatched before-start questions and nested conversation scrolling, addressed in the same correction batch. A used Safari 1512 × 859; B used Chrome 1512 × 861. Neither performed narrow review; root supplied it separately. The score belongs to assessed v0.8.0 and was not re-scored for v0.8.1.

The target slug resolved. Ignore file was absent. Native inventory exposed no mutable DOM/script-injection API, so no detector overlay or browser console scan ran. Native screenshots/accessibility provided the fallback; no user-visible overlay is claimed. No critique live server was started. Reviewers closed their own tabs. The parent-owned local static server stays available because the builder requested the revised page. Critique body and assessment-only temp files were cleaned after synthesis; recovery copies and the small runnable check remain outside the repository. Critique trend is 27 → 26 → 28 out of 40 across different artifact versions, not human scores.

### Human verdicts and next attempt

Task 1 remains REVISE; Tasks 2–5 remain UNRESOLVED. No human task answer arrived during this repair. Repair requests and authored reviewer personas are not assisted task answers. B1's earlier failures and overload/transition feedback remain. The unfamiliar trader's first attempt is explicitly pending; no trader or teammate feedback is invented.

Builder B1 has prior explanations, so the next answers are assisted attempts. Record each answer verbatim with task, role, final version/hash and assistance origin before coaching. Next neutral Task 1: On this Research page, what do you think happened, and what would you choose to do next? The answer is pending. Ask later tasks one at a time.

Remaining limits: full keyboard-only traversal, screen-reader behavior, physical-phone touch/virtual keyboard, and participant-note entry/export were not checked. Large details tables still scroll horizontally. Long replies still require conversation-panel scrolling. Scripted requests accept only existing supported phrases; arbitrary chat understanding is not established. Agent B's full trading qualification, real execution and independently enforced Q31 inventory permission remain unproved. No new blocking defect was observed in the exercised confirmation paths, but beginner comprehension remains unresolved.

Smallest follow-up is the five assisted builder attempts, followed by an unfamiliar trader's separate first attempt. Fix only misunderstandings that those attempts establish before accepted-flow implementation. Current changes are local prototype repairs, not accepted specification changes or production code. Probe A remains closed; Probe B remains unchanged. No paid call, live model, wallet action, financial transaction, dependency, commit, push, issue, merge or publication occurred. Active minutes were not independently measured.

## Selected-agent and past-price interaction repair, v0.9.1, 2026-10-05

### Approval and artifact identity

The builder approved one scoped repair of all five issues from the v0.8.1 independent review, both wording defects, selection of one or both agents for first activation, and the small optional Test on past prices interaction inside this same prototype. This approval covers local HTML, browser review and records only. It does not authorize a simulator, production code, provider/model calls, wallet actions, financial transactions or publication.

Baseline v0.8.1 SHA256: `76d5f57b5de4ac02ab17be4012b7103a8c5ab0a05e9dfb13be46c1de367c250c`; it matched the supplied review, with no newer work to replace. Assessed first-build v0.9.0: `acd2a4a9e434446f0ae26378aef2ff14a106ec549466d416b6c29917580a94fd`. Final v0.9.1: `e45247f922ffa30333ce19844f2658d9fcb55bf9e93c7eacebeb47e10217db66`. Artifact remains the private workspace file `prototypes/edge-os/frontend-interaction/index.html`. A recovery copy of v0.8.1 remains outside the repository. Earlier versions, participant words and failure evidence above are preserved.

The supplied v0.8.1 critique, BUILDER-ONLY REFERENCE `.impeccable/critique/2026-10-05T11-27-07Z__prototypes-edge-os-frontend-interaction-index-html.md`, supersedes the earlier limited claim that no blocker was observed. Its target/feedback failures were valid despite earlier happy-path checks. The new inspection included the renderer and UI bindings as well as pure state transitions.

### What changed and why

Customer navigation now has Research, Agents and Positions. Activation, stop choices and account settings are reached from the relevant records. Starting-state selection moved entirely to Reviewer view, alongside time, transaction outcomes, resets, walkthroughs and participant notes. Customer has one short notice: Demo data. No real money moves. Conversation uses example replies. Navigation and view switching do not reset the loaded account.

Each demo agent has complete, separate rules. A buys after a five-minute price rise greater than 1%; B buys after a five-minute fall greater than 1%, a return below -1%. Both check hourly at minute 10 and sell each purchase after 30 minutes when permission/checks allow it. Exact threshold equality does not qualify. A permits a further buy on another matching signal; B does not add to an open position. Individual allocations and cumulative limits, the 30 WMON per-buy limit and 100 WMON shared limit are visible together before approval. These are authored interaction rules, not qualified strategies from the real investigation.

First activation starts with 120 WMON cash, zero consumed/reserved permission, no agent holdings, actions or previous result. Select A, B or both; exact acknowledgement covers only those selected agents. Selection or pre-start purpose changes clear it. Activation creates no fabricated purchase. The separate existing-account fixture retains both MOE positions, 80 spent, 10 reserved, losses and original history.

Sale previews own their position/context and retain it even when another record is selected. Explicit P-102 requests select B's trade context. Confirmation/cancellation returns to the actual preview target. Direct and conversational paths use the same action contract and duplicate guard. Current sale panels derive from current holdings/actions. Prior replies retain their original answer and timestamp, labeled as earlier examples rather than current status. Transaction/stop/expiry updates clear obsolete transient sale instructions. Closed positions show their completed result in the record, retain history and remove sale controls; closing does not stop future entries.

“Requestd” was removed by using a whole status replacement. After activation, the same terms are described as approved, not awaiting approval. Changed approval success messages are cleared; expandable exact references name only approved agents.

The optional past-price flow reviews an exact demo strategy and suggested dates, starting money, trade size and costs before adoption. A offers positive/negative authored examples; B offers a missing price/fee-data state with a recovery step. Results say “Example result. No simulation has run.” The corrected A sequence has three 20 WMON buys including 0.10 WMON buying fee each, using 60 of its 70 cumulative limit. At 0.5% sale fees, positive gross proceeds 21.6/19.6/21.2 give net gains 1.492/-0.498/1.094, total +2.088 and ending 122.088 from 120. Negative gross 19.6/20.1/19 give -0.498/-0.0005/-1.095, total -1.5935 and ending 98.4065 from 100. Intermediate balance-chart points are explicitly illustrative; largest fall is computed from those points, not claimed market observations. Expandable trades and assumptions remain available. Saved results have a retrievable Agents-page list, preserved across navigation until reload. Saving changes neither the real report nor permission.

Positive, negative and unavailable examples grant no authority or universal trading prohibition. An independent permission review remains available; the trader must inspect its selected scope. There is no mandatory favorable backtest, paper-trading or trial graduation. The working simulator remains backend implementation work under an accepted ticket, not code in this artifact.

The real Report object compared byte-for-byte equal to v0.8.1. All four numeric variants, contrary evidence, missing observations, costs, sources, unresolved conclusion, no selected strategy and unopened final-check data remain. Probe A stays closed and Probe B unchanged. Prototype's state/logic branch governs the experiment. Impeccable Operate/harden/onboard/clarify supported existing helpers and context; craft floor was loaded before UI edits. Karpathy, Unslop and No AI Slop constrained the implementation and wording. Existing Keel/Almanak contextual chat, Minara/Horizon direct records, GT expandable history and Clawpump capital/compute separation remain layout references, not financial-enforcement evidence. No website research or archive scan was repeated.

### Browser and regression evidence

Evidence origin: controller-operated native Safari AX/screenshots; isolated read-only review agents using Chrome; temporary Node syntax, state and renderer checks. No human task answer arrived. One inspection batch, one correction batch and one confirmation round were used. Agent A continued the same confirmation round in its isolated tab when native Safari capture/pipe interruptions and user tab changes interrupted root checks.

| Check | Actual result |
|---|---|
| Research and views | Root desktop Research showed report-only scope and no account activity. Customer had no scenario/time/transaction/participant controls. Reviewer had all five tasks, grouped controls, notes and visible step outcomes. A step opened its Customer record without counting comprehension. |
| Exact B request | From A conversation, Close half P-102 selected B in visible context and the 300-MOE preview/reply. Missing B cost/price blocked its request; no financial action was created. |
| Preview selection and cancellation | Preview A then select B then confirm queued A, restored A's record/conversation and retained 1,000 MOE while pending. Root full-sale and A partial-sale confirmations exercised this binding. Cancellation named the original preview target. Root Option-Tab continued from the restored sale trigger to the next button with visible focus. |
| Ambiguous request | A confirmation typed Close half my MOE: two-target clarification, no preview/action before selection. Selecting A produced the same 500-MOE preview used directly. |
| Pending, partial and fully closed | Initial buy uncertainty retained the 10-WMON reservation. Waiting/sent/unknown sales retained holdings. Root resolved the earlier buy as failed, sent the full sale, made it unknown, then confirmed: 0 MOE, Closed, completed -4.20 WMON and no sale controls; cumulative buy consumption remained 80. No current 1,000-MOE or waiting-sale message remained. Independent partial reconciliation retained 500 MOE, basis 20 and realized -2.2; repeated reconciliation did not duplicate proceeds. Historical replies were not rewritten. |
| First activation | Root A-only start and both-agent start, plus independent B-only start, authorized exactly selected agents. Adding B after A-only acknowledgement cleared the checkbox and disabled activation without stale success feedback. Reviewer records after both activation still showed no holdings/actions, zero spent/reserved and no previous result. |
| Stops and expiry | Pure checks covered just before, at and after the adopted end: expiry blocks new sale submissions, not reconciliation of previously sent actions. A UI confirmation retained queued sale/holdings at expiry. Entries-only stop retained eligible exits; wallet halt disabled the sale request without selling. Questions/navigation did not advance the clock. |
| Continuation | Independent UI check showed a limit increase cannot extend an expired end. A time extension remained unusable until simulated approval plus permission verification, preserving 80 spent, 10 reserved, pending work and entry stop. Pure checks retained losses, history and individual limits. A checked 150 limit leaves 60 unused with 80 spent/10 reserved; cash does not increase. Proposal cancellation changes no adopted terms. |
| Nested test | Setup disabled results until adoption; changes to period/start cleared adoption. Corrected positive and negative results/trade totals/chart ending points agreed. Saved result survived Agents → Research → Agents and reopened exact settings/results. B unavailable named missing decision/exit-time price and fee records, preserved rules and offered a useful next step. |
| Desktop and narrow | Root desktop 1512×859 and narrow Safari 413×523 at 150% zoom inspected Customer/Reviewer, stacked permission terms and compact navigation. A's final tab-only Chrome 390×844 confirmation inspected Positions, clarification, preview return/cancel focus and test results with no document overflow; trade details scrolled inside their container. This is not a physical-phone test. |
| Lightweight checks | Both inline scripts passed node --check. `/tmp/edge-v091-check.js` passed identity, duplicate, full sale, selected activation, acknowledgement, expiry, renewal and authored arithmetic checks. `/tmp/edge-v091-render-check.js` passed populated render, exact permission references, saved retrieval, 60-WMON spending and old-approval clearing. No framework or persistent store was added. |

### Independent review and disposition

The archived v0.9.0 critique, BUILDER-ONLY REFERENCE `.impeccable/critique/2026-10-05T12-10-37Z__prototypes-edge-os-frontend-interaction-index-html.md`, fingerprints the assessed bytes before correction. A `/root/v09_review_a` assessed design/comprehension and source/callers; B `/root/v09_review_b` ran detector, code/state checks and browser evidence. Both applied General Review Protocol, review-verification-protocol, code-reviewer and code-review-excellence. No Go-specific review applies. They were isolated, read-only, with no cross-assessment findings before completion; A finished before B detector output entered synthesis.

A scored 24/40. This score is not a final v0.9.1 score. Both found the populated Positions crash and inconsistent 90-versus-70 test consumption. A also found disappearing saves and overbroad exact references; B found stale approval success. The same correction batch fixed all five. A's bounded confirmation of v0.9.1 passed the corrected renderer, save/retrieval, adoption, spending, target binding, focus, ambiguity, stop/expiry/renewal and narrow paths. Root separately confirmed full sale and both-agent activation. No score-chasing second review or cosmetic loop ran.

Run Notes: target slug `prototypes-edge-os-frontend-interaction-index-html`; ignore file absent; assessments independent. B's exact-target CLI detector exited 0 with full JSON `[]`, zero findings/rules/locations/false positives. It missed interaction/code failures. A used an isolated Chrome DevTools tab; B's fresh DevTools request timed out after 300 seconds, so B used its own native Chrome tab and closed it. No working script injection/overlay existed for B's native surface; no reliable user-visible overlay is claimed. Native AX/screenshots and source/model checks were the fallback. No critique live server was started. The existing parent static server stays available for the requested handoff. Critique body temp file was deleted; recovery copies and small runnable checks remain outside the repo. B assessment-only temp files were cleaned after evidence transfer. Trend 27 → 26 → 28 → 23 → 24 out of 40 compares different versions, not participant understanding.

Root's Safari capture failed once with ScreenCaptureKit -3811, then its native pipe closed. REPL reconnect found the user had changed the active page. The controller recovered only its separate local tab and left v0.9.1 Customer Research open. It did not reset the builder's original page. These are tool interruptions, not attributed prototype failures. Independent tab confirmation supplied the affected remaining checks.

### Human verdicts, remaining limits and next task

| Task | Verdict | Evidence origin / first answer |
|---|---|---|
| 1. Understand research | REVISE | Earlier builder B1 assisted wording/overload/transition failures preserved above. No new answer. |
| 2. Review permission | UNRESOLVED | Browser/state evidence only; no participant answer. |
| 3. Positions and conversation | UNRESOLVED | Browser/state evidence only; no participant answer. |
| 4. Stops and pending sales | UNRESOLVED | Browser/state evidence only; no participant answer. |
| 5. Continuation | UNRESOLVED | Browser/state evidence only; no participant answer. |

B1 remains an assisted participant because earlier explanations and revisions have already occurred. The repair request is approval and feedback, not a comprehension answer. No unfamiliar trader or teammate has completed a first attempt. Their first attempt remains explicitly pending and must be recorded separately. Authored personas and clean detector/browser results cannot pass these tasks.

Remaining limitations: no real simulation, market-data qualification, live model, independently enforced inventory permission or execution proof. Conversation supports only scripted questions and request patterns. Saved examples/notes/drafts are memory-only and disappear on reload. Full keyboard-only traversal, screen-reader behavior, physical-phone touch/virtual keyboard, participant-note export and broad unsupported-input behavior were not checked. Long agent terms still require scrolling; closed-position completed result is in its detail record, while the table's result remains an estimate for unsold tokens. No additional material defect was observed in the corrected paths, but these checks do not establish beginner understanding or production readiness. Active working minutes were not independently measured.

The approved interaction addition is now in the packet. These local repairs apply accepted permission/accounting behavior; they are not accepted production specification changes. Linked handoff/workflow and specification introduction now point to actual frontend history, correcting stale unstarted status only. Backend simulator and production build-brief acceptance remain separate.

Smallest follow-up: B1's five assisted attempts, one at a time, then an unfamiliar trader's separate first attempt. Current neutral Task 1: “On the Research page, what do you think happened, and what would you choose to do next?” Answer pending. Record the builder's words verbatim with v0.9.1/hash and assistance origin before explaining. No paid/model/wallet/financial call, dependency, commit, push, merge, issue or publication occurred.

## Focused simplification, v0.10.1, 2026-10-05

The builder approved one simplification pass on the existing experiment, then human review. The inspected baseline still matched v0.9.1 SHA256 `e45247f922ffa30333ce19844f2658d9fcb55bf9e93c7eacebeb47e10217db66`; no newer work was overwritten. Initial v0.10.0 SHA256 `e1c89bec398d02c0c59fe8f8eb8bb6cc3738e48dd440d5d35320f9ec19643f1d`. Final v0.10.1 SHA256 `f78a310a032d0776c72498e70d1b7de2897efc74216c9b6bd82c926f1a7ffc9a`. The corrected browser/reviewer candidate was `f3e3f7942473ea9aa87b13c200a3951d7d8536f84649c24308ff79681afa407c`; final source cleanup removed only the uncalled agentsIntro helper made obsolete by the new Agents disclosure. No caller or rendered behavior changed. Both reviewers checked the exact cleanup: restoring only that helper reproduced their confirmed candidate hash, so their targeted approvals carry forward to the final hash. Private artifact remains `prototypes/edge-os/frontend-interaction/index.html`. Baseline recovery copy is outside the repository.

### Changes

Empty Positions leads with No open positions, the wallet balance and primary Review trading permission. Ask about my account is secondary. Spending, fees and buys/sales remain expandable. The tracked-position view has an Agent selector and an Asset text filter. A nonmatching filter says No matching positions and offers Show all positions; it does not imply holdings vanished. The main Positions destination restores all tracked records by default. View positions for Agent B uses that same view filtered to B, with B's detail selected. Filters never reset financial records. Closed records remain tracked; their table result now shows completed sales rather than an estimate for zero unsold tokens.

Agents lead with name, current permission/activity/holdings status and a short direction-and-exit summary. View strategy rules retains exact price comparisons, interval, hourly schedule, exits, additional-buy policy, allocations and limits. Before activation, Review activation is primary; past-price tests remain optional and account settings secondary. Inactive stop controls are omitted. After activation, account and agent stop/settings paths are available with visible scope. Successful activation clears the earlier selection-change instruction. Supporting accounting says an unselected agent has no permission; expanded current rules use the current shared limit, while the separate authored historical-test example keeps its original test limit.

Activation review retains selected agents and adopted entry/timing/exit/addition rules, wallet/network, shared and individual maximum spending, allocation, per-buy limit, end time and stop/loss consequences before approval. Full rules, current consumption/reservations, free cash, network fees and technical safeguards remain expandable. Selection or a consequential pre-start setting change still invalidates exact acknowledgement. Only selected agents receive authority. Chat remains optional and reads the same position/action records as direct views.

Prototype's existing logic/state experiment, Impeccable Operate/Clarify and craft floor, Karpathy, Unslop and No AI Slop guided the pass. Competitor findings remain layout references for direct records, optional contextual conversation and expandable history. No vendor enforcement claim was adopted, website research repeated, branding work added or broad redesign started.

### Inspection, findings and one correction batch

Root used a new Safari review tab, leaving the builder's existing pages and state untouched. Desktop and narrow layout were inspected in one batch. The root observed obsolete pre-activation selection feedback after activation; the correction clears it.

Two isolated GPT-6.1 Sol/high reviewers followed the applicable project review policy and General Review Protocol with review-verification-protocol, code-reviewer and code-review-excellence. They reviewed the same frozen non-Git candidate against source, callers and the baseline. Neither saw the other's findings before finishing; neither edited files or operated the browser. No critique score or new design decision session was requested or produced.

- `/root/simplify_review_a` found a Major failure: an unmatched Asset filter hid an exact sale preview created in conversation, and Review the sale request did not recover it.
- `/root/simplify_review_b` found a Major target inconsistency: a B filter could display B after an explicit A chat request/cancellation while a generic stop control still used selected A.

The single correction batch makes exact sale events clear filters, makes Review the sale request select/reveal its own target, and makes direct position stop buttons carry their displayed position ID and position scope. It grants no permission, creates no trade and does not alter holdings. Both reviewers confirmed their targeted findings resolved against final v0.10.1 using source/VM checks; root confirmed the exact sequences in Safari. No further polishing loop ran.

### Actual checks

| Check | Evidence and result |
|---|---|
| Empty account | Customer No open positions, 120 WMON balance, primary permission review, secondary account question, collapsed financial/history sections. No simulation or participant controls. Confirmed desktop and narrow. |
| Pre-activation Agents | Both agent summaries and expandable complete rules available. Review activation primary; account settings/test optional; no inactive stop controls. Root selected A, acknowledged, added B, then found acknowledgement cleared and activation disabled. |
| Selected and active review | Main review named A or A+B and showed wallet, limits/allocation, end and stops. Supporting terms and full rules opened. Root activated both in inspection; final narrow confirmation activated A only and showed Active permission/No open positions without old selection feedback. Existing pure checks separately retained B-only exclusion. |
| Direct access and filters | Agent B link showed only B, 600 MOE and B's detail. Asset ZZZ produced No matching positions. Show all positions and main Positions restored both tracked records and cleared filters. Scenario/view/navigation preserved spending, reservations and pending work. |
| Exact preview recovery | Final desktop: attached A conversation, set unmatched Asset XYZ, requested Close half this position; filters cleared and the same 500-MOE A preview was visible. Review the sale request retained that preview. No sale was submitted. |
| Stop identity | Final desktop: filtered B, requested Close half P-101 in account conversation, cancelled, then opened Review stop choices. A was visible/selected and stop scope was This trade. The independent targeted check also forced stale selection/wallet scope and verified the displayed B button selected P-102 with position scope. |
| Activity and scope | Existing A showed pending-buy status; B showed holdings. Review stops for B opened All trades using Agent B's rules. Account stop controls open wallet scope. Pending status/holdings remained intact through navigation. |
| Narrow and keyboard | Safari reported 413×523 CSS pixels at 150% zoom. Empty actions stacked; compact navigation, rule disclosures and selected permission fields were readable. Tab/PageDown and native controls remained usable; focus remained visible. Final desktop restored to 100% fullscreen; original pages were not reset. Not a physical-phone or full keyboard-only test. |
| Focused checks | Both inline scripts passed node --check. The entire first script, containing Report, Agents, ExampleTest and pure Model, compared byte-for-byte equal to v0.9.1. `/tmp/edge-v010-check.js` used the current extracted script and passed identity/duplicate/full sale/selection/acknowledgement/expiry/renewal/example arithmetic checks. Existing `/tmp/edge-v091-render-check.js` re-read the current artifact and passed renderer, saved retrieval, exact approval scope, spending and feedback checks. Reviewer VM checks reproduced and confirmed the two filter regressions. |

The full real MOE result and its numeric variants/contrary findings, unopened holdout, sample/data/cost limitations and no selected candidate are unchanged. Authored tests remain separate. Stops versus sales, pending reservations/holdings, cumulative consumption/loss/history, expiry and renewal use the unchanged state module. Probe A stays closed; Probe B unchanged. No new framework, backend simulator, paid/provider/model call, wallet/financial action, commit, push, merge, issue or publication occurred. The existing local server remains available.

### Human review and closing boundary

Task 1 remains REVISE and Tasks 2–5 remain UNRESOLVED. No new comprehension answer arrived. Earlier builder failures, overload feedback, assistance and all participant words remain above. This repair request is authorization/feedback, not a task answer. Browser, source and VM results cannot pass comprehension.

The revised Customer Research page is the next review entry. B1's attempts remain assisted; record words verbatim with final version/hash before explaining. Ask one neutral question at a time, beginning: On the Research page, what do you think happened, and what would you choose to do next? Answer pending. Then cover activation, positions, stops, continuation and the nested past-price interaction; the optional nested test is not a sixth compulsory product stage.

An unfamiliar trader's separate first attempt remains pending. If no trader is available when the builder tasks finish, record that limitation and ask the builder whether to accept the narrower findings. Do not invent a pass. Recommend closing only after the agreed tasks are understandable, no material target/holdings/permission/action-consequence defect remains, findings/limits are recorded and the builder explicitly accepts the bounded result. Current evidence does not yet meet that human acceptance condition.

Remaining limits: scripted language patterns and memory-only records; no real simulation, execution or independently enforced inventory authority. No full keyboard-only traversal, screen-reader session, physical-phone touch/virtual keyboard or participant-note export verification. Long complete rules and technical histories require scrolling. No material defect remained in the changed paths after the bounded confirmation, but broader behavior and beginner understanding are not established by this pass. This is a local presentation/navigation repair, not production readiness or a new accepted financial/specification policy.

## Approved controller repairs v0.11.0, 2026-10-05

The builder approved all five findings and three smaller corrections from the v0.10.1 controller review, BUILDER-ONLY REFERENCE `.impeccable/critique/2026-10-05T13-32-01Z__prototypes-edge-os-frontend-interaction-index-html.md`, including stacked mobile position rows. This approval covers one local repair batch. It supplies no new comprehension answer or production authority.

Artifact: `prototypes/edge-os/frontend-interaction/index.html`, v0.11.0. SHA-256: `329f7ec8224caf4802d38771c60c4babc457ef63820381e749c648e6b4347c7d`.

The inspected starting artifact was v0.10.1, SHA-256 `f78a310a032d0776c72498e70d1b7de2897efc74216c9b6bd82c926f1a7ffc9a`, matching the controller review. No newer work was overwritten. Earlier failures, participant words, assisted attempts and version records remain above.

### Changes and repair evidence

| Repair | What changed and actual evidence |
|---|---|
| Attached conversation | Ambiguous sale clarification no longer clears the attached trade. Safari: attach A, type Close half my MOE, then click and type Why did you buy this? Header and both identical replies concern A; clarification remains separate and creates no sale. Selecting A creates the same exact 500-MOE preview used directly. Source checks also cover explicit B selection and shared action identity. |
| Funds | Selected activation now adopts only the selected allocation as trading cash. A-only Safari activation shows wallet 120, allocation 70, unallocated 50, allocated cash 70, reserved 0 and free allocated cash 70. Shared remaining permission is 100, A is limited to 70 and unselected B has none. B-only and both-agent source checks give allocations 50 and 120. Existing-account cash remains 40 with 10 reserved, 30 free and 80 unallocated. Sale proceeds update cash without replenishing cumulative permission. |
| Typed starters | Displayed account, trade and settings starter labels use one question map for typed and clicked input. All 12 displayed entries, including duplicate labels in different sections, matched across account, empty and exact-trade contexts in pure checks. Safari separately compared Why did you buy this? and What trades are open? Both inputs produced the same scoped reply without trades or clock advancement. |
| Narrow positions | At 413 × 523 CSS pixels, Safari displayed stacked rows with asset, owner, holdings, result, action status and a full-width opening button. A and B buttons were visible without horizontal scrolling and opened their exact records. Filters, history and the desktop table remain available. Both layouts use the same records and controls, not duplicate actions. |
| Activation focus | Keyboard acknowledgement, Option-Tab and Return activated A only. The disappearing activation control transferred visible focus to Current trading permission, with a demo-only outcome message. Option-Tab and Return then returned to Agents. Actual screen-reader announcement was not tested. |
| Research actions | Keep this report, Review a study proposal and Ask about this report now immediately follow the conclusion and reasons, before the longer explanations. Final desktop AX order and screenshot confirmed report-only scope and contextual report conversation. |
| Sale grouping | Sell this position groups half/all controls and the shared preview. Conversation, stop and settings controls follow in a separate group. Safari cancellation identified A, retained 1,000 MOE, restored visible focus to Review selling half and allowed keyboard continuation to Review selling all. Stops also separate future activity from sale choices. |
| B past-price settings | B setup names its own 20-WMON purchase, assumed 0.10 buying fee, one-open-purchase policy and 30-WMON cumulative limit. A's three-purchase sequence is absent. Safari adoption led to the preserved unavailable result naming missing prices and fees, with strategy and permission review paths retained. |

### Bounded verification and independent review

Root used a new Safari review tab and left the builder's existing tabs and in-memory state untouched. One inspection batch covered desktop 1512 × 859 and narrow 413 × 523 CSS pixels, Customer and Reviewer views, activation, funds, contextual questions, sale clarification and cancellation, stacked positions, the unavailable B test and affected preservation paths. Narrow inspection used a 620-pixel Safari window at 150% zoom; this was not a physical-phone test. Desktop was restored to 100% fullscreen afterward.

Additional Safari preservation checks:

- Requesting A's half sale left 1,000 MOE held, a 500-MOE sale waiting and the original unknown buy visible. View switching preserved that work.
- Moving explicitly to the adopted end made permission expired and prevented sending the waiting sale. Holdings and pending actions remained visible.
- A time-only proposal kept the 100-WMON limit, 80 spent, 10 reserved, 10 unused, both positions and wallet balance. Approval alone retained expired adopted permission. Reviewer verification then adopted the later end without resetting accounting.
- Stopping new buys for A retained its 1,000 MOE, original buy and waiting sale, and explained that eligible sales remain subject to permission and checks.
- Returning to Research showed only the real investigation and report context, without account feedback or Reviewer simulation/recording controls.

Two isolated, read-only GPT-6.1 Sol/high reviewers applied General Review Protocol, review-verification-protocol, code-reviewer and code-review-excellence to the same frozen v0.11.0 bytes. Neither edited files or used the browser; neither received the other's findings before completion. `/root/repair11_a` checked context, every starter, selected funds, reconciliation, expiry, renewal and render callers. `/root/repair11_b` checked source/diff/callers and 19 isolated state/render cases, including focus routing, mobile structure, B settings, stops and partial-sale accounting. Both approved the repair scope with no verified finding. Their structural mobile/focus observations are separate from root's actual Safari evidence.

Both inline scripts passed `node --check`. `/tmp/edge-v011-check.js` passed target identity, duplicate prevention, full sale, selected activation, acknowledgement invalidation, expiry, renewal, authored-result arithmetic, all starter entries and funds checks. `/tmp/edge-v091-render-check.js` read the current artifact and passed populated rendering, exact permission scope, saved-result retrieval, test spending and obsolete approval clearing. Temporary checks and the baseline recovery copy are outside the project; no framework or dependency was added.

No material defect was found in this batch, so no post-review correction or polishing loop was needed. The final confirmation re-ran focused checks, verified the artifact hash and returned Safari to Customer Research. These are behavior and layout checks, not participant evidence. Impeccable Operate with Harden, Adapt, Clarify and Distill, its craft floor, Karpathy, Unslop and No AI Slop guided this scoped pass. No new critique score was sought.

### Evidence boundaries and next participant attempt

The real MOE report, four variants, contrary findings, assumed costs, missing data and unopened holdout remain intact. The study still selects no deployable strategy. Optional authored past-price results remain separate, grant no permission and impose no favorable-result or trial-graduation requirement. Probe A stays closed and Probe B unchanged. No provider/model, wallet, paid, financial, Git or publication action occurred. Accepted financial behavior and the backend simulator ticket are unchanged.

Human verdicts remain Task 1 REVISE and Tasks 2–5 UNRESOLVED. B1 has received prior assistance; the next answer is an assisted attempt and must be recorded verbatim with this version/hash before explanation. No unfamiliar trader has supplied a first attempt. That separate evidence remains pending. This approval is not a comprehension answer.

Next question, asked once after handoff: On the Research page, what do you think happened, and what would you choose to do next? Answer pending. Later questions cover activation, positions, stops, continuation and the nested optional past-price test one at a time.

Remaining limits: scripted supported language, memory-only notes/results/state, no real simulation or independently enforced trading authority. Full keyboard traversal, screen-reader output, physical-phone touch/virtual keyboard and note export remain unchecked. Detailed rules/history still require expansion and scrolling. No material blocker was observed in the affected paths, but beginner understanding and the builder's bounded acceptance remain unresolved. Prior closing criteria still apply.

## Controller review and accepted wallet amendment, 2026-10-05

Current artifact remains v0.11.0, SHA-256 `329f7ec8224caf4802d38771c60c4babc457ef63820381e749c648e6b4347c7d`. The later controller review supersedes the earlier no-material-finding statement for closure, while preserving its narrower repair evidence. Independent design and source/state assessments plus controller browser inspection returned REVISE. Combined heuristic assessment was 29/40, not a participant score or release gate; 39 source/state checks passed and detection returned zero findings. A suspected renewal failure was withdrawn because its synthetic sequence was unreachable through the UI.

| Retained defect | Reproduction and required correction |
|---|---|
| P1, agent stop before first position | Activate A and B with no positions, then try to stop only A. Only wallet-wide controls are available; controls and state handling depend on a position. Stop the agent/deployment independently of position existence and leave B running. |
| P2, sale status under the wrong position | Request A's half-sale, then open B's position. B's sell section shows A's pending sale panel. The panel names A and no wrong-target sale was observed, but its placement is misleading. Bind current status to its position; retain the exact target of any active preview and keep combined history separately labeled. |

The builder subsequently required separately funded user-owned wallets per trading agent and authorized recording the architecture/funding defaults in the shared documents. The [authoritative lifecycle](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#accepted-agent-wallet-ownership-and-funding), [ADR 0007](../adr/0007-separate-user-owned-agent-wallets.md) and updated [single prototype packet](EDGE_OS_SCOPED_PROBE_PLAN.md#one-frontend-interaction-prototype) replace shared-wallet assumptions for the next candidate. Wallet creation, funding, top-ups, owner withdrawal and removal are nested in the existing five tasks. Preserve the real MOE report, authored past-price flow and financial invariants, but revise the fixture wallet ownership and opening balances explicitly. Preserve prior shared-wallet examples as historical evidence, not proof of the new architecture.

Status: `DOCUMENTATION AMENDMENT ACCEPTED; LOCAL REPAIR NOT RUN; CLOSURE PENDING`. This entry records no new browser/state check, independent rescore or participant answer. P1/P2 remain open. Research remains REVISE; Tasks 2–5 remain UNRESOLVED. The forthcoming repair prompt supplies local execution scope when dispatched; this documentation change performs no prototype, provider, wallet, financial or Git action.

Closure requires the two defect paths and adopted wallet interactions to pass targeted prototype checks, preserved regressions, recorded findings/limits and explicit builder acceptance. Ask participant questions before explaining. Builder attempts are assisted; an unfamiliar trader's first attempt remains separate and pending. If such a trader is unavailable, the builder may explicitly accept bounded closure with comprehension limits recorded; do not promote missing answers to passes. Physical-phone, screen-reader and full keyboard limitations remain visible. Stop broad visual iteration after the scoped repair. Actual wallet isolation, funding/withdrawal reconciliation and signing/removal enforcement belong to WAL-Q19–26 and separately approved Probe B qualification, not this HTML result.

## Separate-wallet completion repair v0.12.1, 2026-10-05

Status: `LOCAL FUNCTIONAL CHECKS PASS; INDEPENDENT REPAIR REVIEW PASS; HUMAN COMPREHENSION PENDING`. This supersedes the preceding LOCAL REPAIR NOT RUN status. It does not erase the v0.11 controller failures or any earlier participant answer.

Artifact: `prototypes/edge-os/frontend-interaction/index.html`, v0.12.1. SHA-256: `cb8936dfea747aec9ba170380664a61c331bc8f5ed7b3d33904c60f7a70665a9`.

Starting artifact was v0.11.0, SHA-256 `329f7ec8224caf4802d38771c60c4babc457ef63820381e749c648e6b4347c7d`. The builder authorized the two controller repairs, the accepted separate-wallet lifecycle, Funds, Safari checks and two independent read-only reviews. Prototype's logic/state approach, Impeccable Operate and its craft floor, Karpathy, No AI Slop and Unslop governed this local change. General Review Protocol and its review-verification, code-reviewer and code-review-excellence requirements governed implementation review. No new framework or dependency was added.

### What changed

The old shared account was replaced with separate records for the connected personal wallet and each agent wallet. Each agent has its own cash, native MON, pending commitments, permission, positions, loss/spending history and transaction queue. An agent cannot borrow another wallet's cash, fees or holdings. Several positions can belong to the same agent wallet. The personal wallet funds agents and receives owner withdrawals; there is no extra pooled Edge OS wallet.

Customer navigation retains Research, Agents and Positions and adds Funds. Research remains the recorded investigation. Creation, funding, permission review, positions, stops and withdrawal use ordinary controls; setup outcomes, transfer receipts, time and scenario resets remain in Reviewer view. Wallet addresses are visibly fictional. Transfer approval names the exact source, destination, asset, amount and fee. WMON pays for trades; native MON pays network fees. Combined cash is explicitly an overview, not one withdrawable balance.

Creation assigns one recorded wallet identity. Failed or cancelled setup can resume; an unknown result waits against that same identity. Receipt confirmation credits once. Funding leaves permission, spending, losses and stops unchanged. Owner withdrawals set aside their inputs and fee, block competing submissions from that wallet and preserve pending/unknown records. Removing an agent's permission leaves owner withdrawal and pending result recording available. Capital transfers do not become trading profit.

Agent stops no longer depend on a position. Position-only stops remain available alongside whole-agent stops. A position's sale panel reads only that position's actions. Existing previews retain their original wallet/position when navigation changes. Current holdings and completed results derive from current records; earlier conversation answers remain dated history. A fully sold position shows Closed and no sale controls.

### Authored opening balances

These are new examples, not a migration of the old shared-wallet balances or evidence of real custody.

| Example | Personal wallet | Agent A | Agent B |
|---|---|---|---|
| New user | Connected example: 200 WMON and 5 MON | Strategy draft, no created wallet, cash/fees/consumption/positions zero | Same empty draft state |
| Funded, inactive | 200 WMON and 5 MON opening balance | Ready wallet, 70 WMON and 0.8 MON, no permission/positions/consumption | Ready wallet, 50 WMON and 0.8 MON, no permission/positions/consumption |
| Existing trading | 200 WMON and 5 MON opening balance | 20 WMON, 0.8 MON, 50 WMON consumed, 10 WMON set aside for the initial unknown buy; two MOE positions of 1,000 and 200 tokens | 20 WMON, 0.8 MON, 30 WMON consumed; one 600-MOE position with missing full cost/current price |

A's proposed allocation/total buy limit is 70/70 WMON; B's is 50/30. Each per-buy limit is 30. These separate-wallet terms replace the historical shared 100-WMON ceiling only in the new examples. Explicit Reviewer loading is the only scenario replacement; page/view changes do not reset accounting. The pre-funded example begins at its stated balances and does not invent a funding receipt history.

### Inspection and independent review

Root inspected the candidate through native Safari controls in a separate review tab. The builder's existing prototype tabs were not reset. Desktop was 1512 × 859 CSS pixels; narrow Safari was 413 × 523 at 150% zoom in a 620-pixel window. Root inspected screenshots and accessibility state for both Customer and Reviewer views. This is not a physical-phone test.

Two isolated GPT-6.1 Sol/high agents reviewed frozen v0.12.0, SHA-256 `252e899f5161c80d307d256d4f7220cd1e7c4a566342755936767bb6587bdef0`, without seeing one another's findings before their initial assessments. Neither changed project files. Reviewer A used Impeccable and an isolated Chrome tab; reviewer B used General Review Protocol, source/callers and executable model checks. Both initially returned REVISE.

| Finding | Correction and final disposition |
|---|---|
| A: 0.123456 WMON reviewed as 0.12 while the full amount was recorded | Approval and action/receipt text now preserve the exact quantity. Reviewer A confirmed through browser controls; B confirmed model/render identity. Resolved. |
| A: a token withdrawal selector reset visibly to WMON after navigation | The selected position option is restored from the same draft. B's 0.5-MOE withdrawal survives Positions → Funds. Both confirmed. Resolved. |
| A: B's unavailable test could open A's permission | Test and permission entry carry B explicitly. Browser confirmation opened B-selected review. Resolved. |
| B: position-only stop disappeared during wallet repair | Restored a position-bound stop entry and handler, separate from whole-agent stop. P-101 stop leaves P-103 and B unchanged. Root Safari and both reviewers confirmed. Resolved. |
| B: waiting buy bypassed an eligible sale | Submission now prioritizes eligible exits inside that wallet. An ineligible sale does not block a valid buy; another wallet's queue remains independent. B confirmed. Resolved. |
| B: tiny sale fee could produce negative WMON after withdrawal | Reject sale proceeds below the 0.20-WMON trading fee. Approval shows gross, fee and estimated net separately from MON fees. Holdings/balances stay unchanged on rejection. Both confirmed. Resolved. |

Root also corrected misleading unused-permission wording before activation, the draft wallet status, transfer labels and stale reset announcements in the same batch. No visual redesign or score-driven loop followed. Both reviewers approved the targeted repairs against final v0.12.1 and its exact hash above. A used browser/source/VM confirmation; B passed 123 independent assertions (83 preserved invariants plus 40 repair/transfer checks). These approvals cover the reviewed prototype paths, not runtime security or beginner comprehension.

### Actual functional and browser evidence

| Path | Result and evidence origin |
|---|---|
| Create and fund without starting | Root Safari: review A strategy → create → Reviewer confirmed → empty A wallet → 70-WMON owner transfer. Unknown receipt retained 200 personal WMON with 70 set aside and zero in A. Confirmation yielded 130 personal / 70 A. Separate 0.2-MON transfer funded fees. A still had no trading permission until explicit activation. A's isolated browser repeated the full path. |
| Selected activation and empty-agent stop | Root Safari activated A alone with B unapproved, then explicitly loaded the funded scenario, selected both and stopped A before any position existed. A showed new buys stopped; B remained active with no stop. Model checks cover chat's A-scoped stop review and acknowledgement invalidation. |
| Exact sales and multiple positions | Root opened A's two positions and B's one. Preview A half-sale → open B → return to review retained A. A's request/sent sale retained 1,000 MOE until receipt; B's sale section contained no A sale. Independent checks cover ambiguous same-token clarification and unchanged chat attachment, shared preview identity and duplicate prevention. |
| Closed state and keyboard | Final Safari: cancel A's full-sale preview → focus returned to its half-sale button; Option-Tab reached full-sale and Return reopened it. Request full sale → fail earlier unknown buy → send → confirm showed 0 MOE, Closed, −4.20 WMON completed result and no sell buttons. P-103 and B remained. Earlier activation focus moved to permission review and keyboard navigation continued with a visible focus ring. |
| Owner withdrawal and contention | Final narrow Safari: review A→personal 5 WMON withdrawal, approve, set Unknown. Funds remained 20 with 5 set aside; a new A buy review was disabled with the pending-withdrawal reason. Failure released cash and spent the stated MON fee. After removal, a new owner withdrawal confirmed: A 15 WMON, personal 205; 1,200 MOE stayed held, 50 spent and removed permission stayed. |
| Receipt/retry/recovery | Root's 49 focused assertions and B's 123 independent assertions cover setup identity across failure/unknown, duplicate terminal confirmation, pending input preservation, failed fees, token withdrawal/basis as capital flow, and top-ups in active/stopped/expired/revoked/exhausted/trial/loss-stop states. No double credit or cross-wallet change observed. |
| Expiry and continuation | Final Safari explicitly moved to A's end, showed Expired, reviewed/approved/verified a time-only extension retaining 70 limit, 50 consumed, 20 WMON, positions and losses. Limit-only proposal/cancellation left the adopted terms unchanged. Model checks cover expired limit-only verification denial, current clock checks and preserved stops. Navigation/questions do not move time. |
| Optional past-price flow | Final Safari adopted A settings, viewed the labeled authored result/chart, inspected trades, saved and retrieved it. B retained its missing-data outcome and B-specific permission entry. Both Report and ExampleTest definitions match the v0.11 baseline byte-for-byte; positive/negative example arithmetic checks pass. No test has run and no result grants permission. |
| Narrow and state preservation | Root screenshot/controls confirmed stacked position rows with their opening actions, stacked Funds/withdrawal review terms and accessible Reviewer outcomes at 413 × 523. View/page changes preserved financial state. Reviewer A also inspected 390-pixel Chrome. No sideways scroll was needed to find position opening actions. |
| Focused checks | Both inline scripts pass `node --check`. `node /tmp/edge-wallet-check.js`: 49 passes. `node /tmp/wallet121-review-b.js`: 123 independent passes. Temporary scripts and the recovery baseline stay outside the project. No framework or dependency added. |

### Limits, human verdicts and handoff

Functional/state verdict: PASS for the exercised scripted paths. Independent implementation/design repair verdict: PASS for the bounded changed scope. No material target, balance, permission or action-consequence defect remains in those checks. This does not establish all possible states or production readiness.

Human verdicts remain **Task 1 REVISE; Tasks 2–5 UNRESOLVED**. No new participant answer was received during this repair. The builder's earlier overload/confusion and assisted responses remain above. B1's next answer must be recorded verbatim with v0.12.1/hash before explanation. An unfamiliar trader's separate first attempt is still pending. Authored personas, code assertions, screenshots and reviewer assessments cannot fill that gap.

Remaining limits: supported scripted language only; all data/notes/results are in memory; no real historical simulator, wallet signing, transaction hash/resend, external funding detection or independent permission enforcement. Decimal balances use JavaScript numbers for authored examples, not production currency arithmetic. Reviewer step feedback currently shows the latest action outcome across tasks; it is not a task success record. Full keyboard-only traversal, screen-reader announcements, physical-phone touch/virtual keyboard and note export were not verified. Creation and receipt controls intentionally need Reviewer intervention. Actual custody, signing isolation, inventory authority, queue timing, owner recovery and transfer settlement require WAL-Q19–26/backend qualification and separately authorized Probe B. Probe A stays closed; Probe B is unchanged and unstarted.

Recommend **bounded technical closure for the builder's decision**, with human comprehension explicitly open. Do not claim final experiment acceptance until the builder accepts that narrower result or completes the agreed attempts. No further broad polishing is proposed.

Safari is returned to Customer Research with the new-user example ready. Review sequence: Research → create/fund A → selected activation → direct/contextual positions → stops → owner withdrawal → continuation; inspect the optional past-price example within Agents. Ask one question at a time. First question: **On the Research page, what do you think happened, and what would you choose to do next?** Answer pending; assisted attempt, not a first-time-trader result.

No real provider/model, wallet, financial, paid, Git or publication action occurred. This repair changes local prototype behavior and supporting status records only.

## Controller verification and repair v0.12.2, 2026-10-05

Method: dual-agent review, A: `/root/wallet_v12_clarity`; B: `/root/wallet_v12_defects`, plus controller Safari checks. General Review Protocol governed evidenced defects. Impeccable Operate governed clarity. No AI Slop and Unslop filtered wording.

Reviewed v0.12.1 SHA-256 `cb8936dfea747aec9ba170380664a61c331bc8f5ed7b3d33904c60f7a70665a9`. Repaired v0.12.2 SHA-256 `cd295d6ade0f416a58b0049f8d022518b3979ba5b878fe5383174b0042b81e8d`. The earlier approval remains historical evidence. This later review found additional paths, without invalidating the previously exercised paths.

### Findings and one repair batch

| Finding | Repair and evidence |
|---|---|
| Explicit B permission entry retained selected A after A activation | Entry now selects the named agent and clears acknowledgment. Deliberate multi-selection remains available inside review. A confirmed source and its two relevant executed cases. |
| A never-sent purchase could reserve funds indefinitely after stop or revocation | Funds action history now offers cancellation only for Waiting actions. It releases reservations without spending funds, fees or attempts. Cancelled actions cannot send or settle. Pending and Unknown actions cannot cancel or release reservations. B confirmed the reducer and reachable UI handler. |
| Reviewer continuation could grant first permission through renewal | Both proposal and verification reject agents with no initial permission or no ready wallet. Settings points to first activation. This blocks the reviewer-reachable bypass without relying only on hidden buttons. |
| Reviewer agent switching left a stale position-stop target and false success | Agent switching clears the position target. Rendering validates ownership. The reducer rejects mismatched ownership without announcing success. |
| Sale estimates showed floating-point noise | Estimated proceeds now show 3.6 and 3.4 WMON. Approved token quantity remains exact in the example, including 499.938272 MOE. Production currency arithmetic remains unqualified. |
| A trading receipt claimed consumed limits and stops stayed unchanged | Trading receipt text now says records reflect the result and permission limits have not increased. Transfer-specific unchanged-permission wording remains separate. |

The durable check is BUILDER-ONLY REFERENCE `prototypes/edge-os/frontend-interaction/review-regressions.js`. It uses Node's built-in assertions and VM to execute the real scripts, render functions and registered handlers. No framework or dependency was added.

Red run on v0.12.1: 1/8 passed, seven expected failures. After repair, the cancellation test was corrected to use Customer Funds, where the unsent action control lives, rather than expecting it in Reviewer view. Final command `node prototypes/edge-os/frontend-interaction/review-regressions.js`: 8/8 passed, exit 0. Existing `node /tmp/edge-wallet-check.js`: 49 passed. Existing `node /tmp/wallet121-review-b.js`: 123 assertions passed. B independently repeated all eight new cases. A executed only its two relevant cases; its filtered runner retained an inaccurate 8/8 footer, so that footer is not counted as eight independent executions.

Both reviewers confirmed their assigned repairs on the exact v0.12.2 hash. These are source and executed-state confirmations, not fresh browser confirmations.

### Browser and design evidence

Before repair, the controller used a new Safari tab to inspect Research, creation, a pending then confirmed 70-WMON transfer to A, and A stop/removal with positions and an unknown purchase preserved. Funding left permission unstarted. Confirmed funding changed personal cash from 200 to 130 WMON and A from zero to 70. The controller closed only that temporary tab. The builder's existing tabs and current browsing were preserved.

A inspected initial activation and stop-before-first-position in a separate Chrome tab, then used a hidden in-app tab for selection and sale-preview checks. B used a separate hidden in-app tab for the renewal and stop-target reproductions. Both closed their review tabs. Inline screenshots were inspected but not saved.

After repair, both reviewers attempted a fresh hidden in-app browser confirmation. Both received `Browser is not available: iab`; no tab opened. They did not switch to the builder's active native browsers. Therefore v0.12.2 has no fresh browser/layout confirmation. Source and executed regression evidence are the fallback. Earlier desktop/narrow-layout passes remain tied to their recorded versions.

B ran the required detector once, exit 0, zero findings. It did not detect the state defects. No detector overlay was injected because the available evaluation interface was read-only. No extra server was started.

The independent design scores assessed v0.12.1, not repaired v0.12.2:

| Heuristic | Score |
|---|---:|
| System status | 3/4 |
| Familiar language | 3/4 |
| User control | 3/4 |
| Consistency | 2/4 |
| Error prevention | 3/4 |
| Recognition rather than memory | 3/4 |
| Efficiency | 2/4 |
| Focused presentation | 2/4 |
| Error recovery | 3/4 |
| Contextual help | 3/4 |
| Total | 27/40 |

The composition suits an operating trading product: named owners, direct records, contextual conversation and reviewed transfers. Research leads with its conclusion and reasons. Pending actions remain distinct from confirmed holdings. The score is diagnostic, not an acceptance threshold. No score-driven iteration or v0.12.2 rescore occurred.

One nonblocking clarity observation remains: an active agent can expose eight similarly weighted actions. A beginner may hesitate over the next action; a mobile user may need more scanning. Retain this for participant observation rather than a new redesign. Full keyboard traversal and screen-reader announcements remain unchecked.

Retained competitor evidence supports direct records plus contextual conversation in Keel/Almanak, direct account controls in Minara and separate agent funds/AI credits in Clawpump. BUILDER-ONLY REFERENCES: `docs/research/EDGE_OS_COMPETITOR_UX_AND_ACCOUNT_CONTROL_2026-10-03.md` and `docs/research/EDGE_OS_AGENT_AND_MAIN_WALLET_UX_2026-10-05.md`. These observations do not establish comparative comprehension, synchronization, custody or enforcement. Almanak's documented shared Safe is not Edge OS's accepted wallet architecture.

### Closure decision and remaining evidence

No unresolved blocking finding remains in the checked source/state paths. Recommend bounded technical closure for the builder's decision, with fresh post-repair browser confirmation unavailable and human comprehension explicitly open. Do not describe v0.12.2 as fully usability-tested.

Human verdicts remain **Research REVISE; Tasks 2–5 UNRESOLVED**. No participant answer was supplied or inferred. The next answer must be recorded against v0.12.2 before explanation. The builder's attempt is assisted; an unfamiliar trader's first attempt is still absent.

The participant check remains: identify each wallet's owner; explain why funding does not activate or enlarge permission; distinguish stop, sell and withdraw; explain pending actions after removal; distinguish research, authored simulation and account examples. Source assertions cannot answer those human questions.

After explicit bounded closure, freeze this artifact and carry its accepted behavior and limits into the build brief and tickets. Real wallet creation, signing isolation, ownership recovery, transaction reconciliation, execution and backtesting remain backend qualifications. Probe A evidence and Probe B scope are unchanged. No real money, provider request, Git commit, push, merge or publication occurred.

Questions skipped: zero unresolved blocking findings remain in the checked code paths. One minor action-density observation remains. The builder already approved one repair batch.

## Builder walkthrough and build handoff, 2026-10-05

After being advised to do one short walkthrough, the builder reported: “I have done two and I think it is fine”. “Two” refers to that walkthrough step. This is general assisted feedback after prior explanations. The message supplies no task-by-task answers, independent trader observation or complete browser/accessibility test record. Preserve the earlier task verdicts; do not infer new passes or erase earlier confusion.

The builder subsequently authorized a documentation consolidation and draft build brief for review. The [brief](../EDGE_OS_BUILD_BRIEF.md) carries forward the demonstrated interactions and their limits. This authorization does not itself approve full production scope, spending or real wallet use. Bounded technical closure remains an explicit decision; no new broad prototype iteration is proposed.

No prototype code, authored balances, evidence, test results or artifact hash changed in this consolidation. No browser or regression suite was rerun. Production must implement persistence, actual research/simulation and qualified wallet operations; the scripted HTML supplies an interaction reference only. Carry the missing unfamiliar-trader, full-keyboard, screen-reader and physical-phone checks into relevant work without describing them as completed.
