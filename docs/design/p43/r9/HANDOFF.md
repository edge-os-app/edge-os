# Edge OS · Phase B design handoff · current design (revision 9)

Prepared 2026-10-07.

**How to read this file:**
- **R9**, **R8**, **R7**, **R6** and **R5** below record the latest repair batches, newest first.
- **Part A** is the current design: implement from Part A *as amended by R9, R8, R7, R6 and R5*. Where they differ, the newer section wins.
- **Part B** is historical and kept for traceability only.
- Demo JavaScript in these files isn't production transaction, authority or reconciliation code.
- Impeccable (Operate, Harden, Clarify) and Unslop were not available and did not run. Their principles were applied by hand: field-level errors, grouped consequential terms, one complete summary before approval, honest unsupported states.

## R9 · One permission change at a time (current)

**Decision:** block, not supersede. While a permission change is being checked, a second change can't be approved. The first change keeps its exact terms, approval time and eventual outcome (Applied / Failed / Cancelled / Discarded). Nothing silently replaces it.

**Behavior:**
- The change review shows an alert naming the pending change, with its old → new terms and approval time, and disables **Approve change**. A bullet notes that only one change can be checked at a time.
- **Approval re-check.** The approve handler reads the agent's current record before writing. It refuses if a change is pending, or if the permission's version or status changed since the review opened. It writes nothing and shows a message.
- Once the first change resolves (passed, failed or cancelled by removal), a new change can be reviewed normally.
- Production requirement: the backend must enforce a single pending change per mandate, or an explicit supersede with an audit record. This frontend block doesn't replace that.

**Confirmation (scripted DOM clicks in the preview iframe; Chromium; locally served):**

| Path | Expected | Observed | Source | Standalone |
|---|---|---|---|---|
| Order 1: Add 24 hours approved (checking) → open Raise limit | Blocked; first kept | Alert "…Ends Oct 6, 12:00 → Oct 7, 12:00, approved Oct 5, 11:00…"; Approve disabled; records: Checking (Ends) only | PASS | PASS |
| Order 1 → Pass check → Raise limit | Allowed | Approve enabled; approved | PASS | PASS |
| Order 2: Raise limit approved (checking) → open Add 24 hours | Blocked; first kept | Alert "…Total buy limit 100 WMON → 150 WMON…"; Approve disabled | PASS | PASS |
| Order 2 → Fail check → Add 24 hours | Allowed; failed record kept | Records Failed (limit) and Applied (time); Approve enabled; limit still 100 | PASS | PASS |
| Removal while a change is checking (regression) | Change cancelled | Records Cancelled / Failed / Applied; no check group left; permission Removed | PASS | Not run |
| Handler-level refusal when the button is bypassed | Refuses | Code inspection only: the UI never lets a disabled button fire | UNCHECKED (not exercisable) | UNCHECKED |
| Console / external URLs | 0 / 0 | 0 / 0 | PASS | PASS |

Not re-run in R9: mobile 390, sizing, queue, stale intents, trial, rebinding and failed-activation paths (R5–R8 PASS; this change only touches the change review and its approve handler). Real keyboard, file:// offline, Safari, screen reader and physical phone checks remain UNCHECKED.

## R8 · Checked permission changes and failed approvals (extended by R9)

**Behavior:**
- **Permission change (Add 24 hours / raise total buy limit).** Approving records a change entry: `approvedAt`, the base permission version, and the exact changed terms as old → new.
  - While it's being checked, the current permission stays in force and the change shows as **Permission change · Checking**.
  - If the check passes, the original permission is copied unchanged into `permHist` ("Superseded by a checked change approved <time>"). The new current record keeps the original approval time and adds "last change approved <time>, active <time>". The change entry becomes **Applied**.
  - If the check fails, the change entry becomes **Failed · never active** and the current permission is untouched.
  - If removal or a rule change happens before the check, the entry becomes **Cancelled · never applied** (or **Discarded** if the permission version changed).
- **Failed approval attempt.** A failed activation check, whether from Fail check or a rule needing an unavailable token-age check, keeps the full proposed terms as **Failed approval attempt · <time> · never active**. The agent's permission becomes "Not approved". The attempt is never shown or treated as active.
- **Record order** under Permission and stops: Current → permission changes (newest first) → earlier and failed permission records (newest first). Every entry is a collapsed `<details>`.
- Earlier-record reasons now read "Removed; a new approval was submitted afterwards" and "Replaced by a new approval", so a failed attempt doesn't read as a replacement.

**Confirmation (scripted DOM clicks in the preview iframe; Chromium; locally served):**

| Path | Expected | Observed | Source | Standalone |
|---|---|---|---|---|
| Agent A: Add 24 hours → approve → Pass check | Original kept; change recorded separately | Current v2 ends Oct 6, 12:00 (original approval Unknown · last change approved and active Oct 5, 11:00). "Permission change · Applied" Ends: Oct 5, 12:00 → Oct 6, 12:00. Earlier v1 ends Oct 5, 12:00, "Superseded by a checked change…" | PASS | PASS |
| Agent A: raise limit → approve → Fail check | Failed change kept; current unchanged | "Permission change · Failed": Total buy limit 100 → 150 WMON; current still 100 (22 of 100 left) | PASS | PASS |
| Agent A: change checking → remove permission | Change cancelled, not applied | "Permission change · Cancelled"; no permission-check group left; permission Removed | PASS | Not run |
| Agent C: remove → confirm → new approval (15 / 4 / 6) → Fail check | Failed attempt kept, never active | Permission "Not approved"; "Failed approval attempt · never active" with 15 WMON / 4 attempts; earlier fixture record kept | PASS | PASS |
| Regressions | Unchanged | S-10 queued behind T-0 (standalone); 0 console errors; 0 external URLs | — | PASS |

Not re-run in R8: mobile 390, sizing, stale intents, trial and rebinding paths (R5–R7 PASS; touched code limited to the permission check outcomes and record list). Real keyboard, file:// offline, Safari, screen reader and physical phone checks remain UNCHECKED.

## R7 · Every approval snapshot kept (extended by R8)

**Behavior:**
- Every permission that ends is appended to `permHist`, whether it was removed and then replaced by a new approval, or ended because the agent moved to another revision. Nothing is overwritten.
- Each entry keeps its terms exactly as approved: bound rule revision and cap, approval time, allocation, total buy limit, per-buy, attempts, loss limit, gas, end, purpose, version, and its removal state at the time.
- **Permission and stops** lists one collapsed **Current permission record** first, then one collapsed **Earlier permission record · ended <time> · approved for revision N** per past approval, newest first. A note says how many earlier records are kept.
- The current revision stays a separate row in every record. Missing fixture fields read "Unknown (not in this demo record)".
- End reasons: "Removed, then replaced by a new permission" · "Replaced by a new permission" · "Ended because the agent moved to revision N".
- **Study message:** finishing the last step, whether automatically or with the reviewer's Advance step, replaces "Plan adopted. The study is running…" with "Study finished. The report is saved.". The screen reads **Study finished** with **Open report**.

**Confirmation (scripted DOM clicks in the preview iframe; Chromium; locally served):**

| Path | Expected | Observed | Source | Standalone |
|---|---|---|---|---|
| Agent C fixture permission → remove → confirm → approve A (per-buy 15, attempts 4, loss 6) → pass → remove → confirm → approve B (8 / 2 / 3) | Three records; earlier terms unchanged | Current: 8 WMON / 2 attempts / 3 WMON. Earlier (rev 1, v4): 15 / 4 / 6. Earlier (fixture, v1): 20 WMON, attempts and loss "Unknown". Note "2 earlier records kept". | PASS | Run to approval A: current 15 / 4 plus earlier fixture record, reason "Removed, then replaced by a new permission". PASS. Approval B not replayed. |
| Rebinding an active permission (R6 path) | Ended record kept with rev 2 / cap 20 | R6 PASS; logic now appends to `permHist` | Not re-run in R7 | UNCHECKED |
| Finished study message | No "running" message after finishing | Before: "Plan adopted. The study is running…". After the last Advance step: "Study finished. The report is saved."; heading "Study finished"; Open report present | UNCHECKED (same code) | PASS |
| Console / external URLs | 0 / 0 | 0 / 0 | PASS | PASS |

Not re-run in R7: mobile 390, sizing, queue and stale-intent regressions (code untouched). Real keyboard, file:// offline, Safari, screen reader and physical phone checks remain UNCHECKED.

## R6 · Permission record history and study completion (record display superseded by R7)

**Behavior:**
- At approval, the permission stores a snapshot of the exact rule it was approved for: `boundRule = { id, rev, title, cap }`, plus `approvedAt`.
- Removing permission keeps that record. Applying another revision doesn't touch the snapshot.
- *(Superseded by R7: a single `prevPerm` slot could be overwritten. Every ended permission now goes into the `permHist` list.)*
- The record shows **Approved for rule revision** and **Strategy cap at approval** from the snapshot, and **Agent's current rule revision** on its own row, marked "same as approved" or "different from the approved revision".
- Fixture permissions without these fields read **"Unknown (not in this demo record)"**. Untracked consumption reads "Not tracked in this demo · unknown".
- A finished study's progress screen now reads **Study finished** with "Every step is done and the report is saved" and a primary **Open report** button. It no longer says "Study in progress".

**Confirmation (scripted DOM clicks in the preview iframe; Chromium; locally served):**

| Path | Expected | Observed | Source | Standalone |
|---|---|---|---|---|
| Fixture Agent A record, then removal | Missing history shows unknown; terms kept after removal | Approved, revision and cap at approval read "Unknown (not in this demo record)"; current revision "1 · Buy after a price rise"; after removal the status changes and the other terms stay | PASS | PASS |
| Active Agent D (rev 2, cap 20, per-buy 15) → save rev 3 (cap 12) → apply rev 3 | Previous record keeps rev 2 / cap 20 / 15 / approval time; current shown separately | "Previous permission record · Ended … because the agent moved to revision 3 · Approved for rule revision 2 · Strategy cap at approval 20 WMON · Agent's current rule revision 3 · different from the approved revision · Most per buy 15" | PASS | UNCHECKED (same bundled logic) |
| New permission on rev 3 (cap 12, per-buy 12, attempts 3, loss 6) → remove (Pending) → apply rev 2 | Record keeps rev 3 terms; permission stays removed; no approval path | Record "Approved for rule revision 3 · cap 12 · attempts 3 · loss 6 · Provider removal Pending"; current "2 · different from the approved revision"; no Review new permission | PASS | UNCHECKED |
| Finished study | Completed state with Open report | "Study finished" → Open report opened the saved report | PASS | PASS |
| Regressions | Unchanged | Source: removal stays independent of rebinding; no approval while Pending. Standalone: S-10 queued behind T-0 Unknown. 0 external URLs, 0 console errors. | PASS | PASS |

Not re-run in R6: mobile 390, sizing 30/20/10, stale-intent expiry, trial continuation, and the other R5 regressions (code paths unchanged). Real keyboard, file:// offline, Safari, screen reader and physical phone checks remain UNCHECKED.

## R5 · Current behavior changes (supersede Part A where they differ)

1. **Provider removal is independent of rule revisions.** Each agent stores its provider-removal state separately from its permission status and rule revision.
   - Applying a saved revision to a removed agent leaves permission **Removed** and keeps the removal state (Pending / Unknown / Failed / Confirmed).
   - "Review new permission" appears only after removal is Confirmed.
   - `activationBlock` refuses approval while removal is unresolved, whatever the rule revision. The approve handler re-runs `activationBlock` at the moment of approval, not only when the review renders.
2. **Revision identity.** A new revision number is 1 + the highest number already used in that rule's lineage, so siblings get 3, 4, 5… rather than two "revision 3"s.
   - Rule cards and agent pages show each revision separately. Saved revisions stay immutable.
   - The agent's **Review applying a saved revision** starts with **nothing selected**. It lists every tradable revision in the lineage with its cap, title, parent and save time. Once one is picked, it shows "Exact change" (old → new) and the permission effect.
   - Saving, applying to an agent and granting permission stay three separate steps.
3. **Permission value validation** lives in shared `termErrors`, used by both the review and the approval path.
   - Allocation, total buy limit, per-buy, loss limit, network fee limit and length must be finite and above 0.
   - Attempts and the trial stopping point must be whole numbers, 1 or more.
   - Per-buy can't exceed the total buy limit or the strategy cap.
   - Each error appears beside its field (`aria-invalid`, `aria-describedby`). Approve stays disabled while any error remains.
   - Changing any value clears adoption. No platform numeric bounds were invented.
4. **Permission review layout.** Three groups:
   - **Capital:** allocation vs cumulative total buy limit. Proceeds, restarts and trial continuation don't refill it (spec: allowances aren't replenished).
   - **Attempts, loss and network fees:** an attempt counts once a swap can be broadcast, including reverts; Unknown keeps its attempt and funds reserved (spec Q29). Losses use weighted average cost on completed sales (spec Q30); whether unsold estimates count is **not qualified**.
   - **Duration (+ trial stopping point).**
   - One **Proposed permission · complete** summary follows the groups. It lists all terms, including assets, actions, recipient, restrictions, unqualified checks and, on renewal, what carries over. The per-term source table ("Where each term comes from") is expandable.
   - *(Record display superseded by R7.)* After approval, the agent page has an expandable **Full permission record** with every adopted term. It shows approved / used / reserved / left only where the demo keeps records (total buy limit). Attempts used, loss counted, actual fees and committed allocation read "Not tracked in this demo · unknown". Earlier provider removal is shown.
5. **Unsupported lesson.** "Require a 15-minute gap between buys" is labelled **Unsupported · can't be adopted yet**, with the reason. The "Review lesson as a rule change" button is removed. No minimum-gap operator was added, and neither the checking schedule nor an observation period is offered as a substitute.

### R5 · Finding dispositions and evidence
Environment: design preview iframe (Chromium, served locally); scripted DOM clicks. "Source" = `Edge OS.dc.html`; "Standalone" = `handoff/Edge OS standalone.html`.

| Finding | Expected | Observed | Source | Standalone |
|---|---|---|---|---|
| F1 Removal bypass via revision | Removed agent stays removed after applying a revision; no approval path until Confirmed | Agent D (rev 2, active) → removal Pending → applied revision 4: "Permission stays removed; provider removal is pending"; no Review new permission and no Review trading permission. Unknown: still none. Confirmed: Review new permission appears, rule "Revision 4", per-buy defaults to 10. | PASS | UNCHECKED (same bundled logic; journey not replayed) |
| F2 Duplicate revision 3 | Distinct identities; explicit selection | Two saves from Agent D: "Save revision 3" (cap 12), "Save revision 4" (cap 10). Apply review opened with nothing selected and Apply disabled. Options: "Revision 3 cap 12 WMON… from revision 2", "Revision 4 cap 10 WMON… from revision 2". Selecting 4 showed "Exact change Strategy cap: 20 → 10". | PASS | UNCHECKED |
| F3 Invalid values approved | Reject 0.5 attempts and −1 gas | Field errors "Use a whole number, 1 or more." and "Enter a network fee limit above 0 MON…"; Approve disabled after adoption. Valid values (4 / 6 / 0.2) → Approve enabled; changing loss cleared adoption; approved → checking → active. | PASS | PASS (0.5 / −1 rejected; 0 external URLs; 0 console errors) |
| F4 Terms hard to inspect | Grouped review, full summary, post-approval record | Legends Capital / Attempts, loss and network fees / Duration; summary has 15 rows; Agent C record listed all 14 adopted terms with unknowns as unknown. Mobile 390 review height 3,523 px (was 3,610) with more content. | PASS | Grouping PASS (screenshot 10); record UNCHECKED |
| F5 Unsupported lesson action | No adoption path; explained | Button removed; "Unsupported · can't be adopted yet" note | PASS by template inspection; not clicked through a trial this pass | UNCHECKED |

### R5 · Regressions this pass
| Check | Result |
|---|---|
| Strategy cap 20: permission 30 blocked (field error + "Review rule change"); 10 approved, effective 10 | PASS (source) |
| T-0 Unknown queues S-10 ("queued behind T-0"); Agent B withdrawal W-11 sends independently | PASS (source) |
| Mobile 390 half-sale of 200 → "Sell 100 MOE…"; sheet closed; review visible | PASS (source). Focus landing not observable: the iframe never holds focus. |
| Unsupported launch age blocks rev 1; explicit removal into rev 2; agent created on rev 2 | PASS (source, during F1/F2 setup) |
| Funding (50 WMON, 0.5 MON) left Agent D at "Next: review trading permission" | PASS (source) |
| Stale-intent expiry, trial continuation, stop before first trade, check timestamps | Not re-run in R5 (R4 PASS; code paths untouched) |
| Console errors | None in source or standalone runs |
| Known warning | Before data resolves, the browser may warn about `<polyline points="{{ T.pts }}">` in the hidden past-price chart template. Cosmetic; no broken visible chart observed. |

### R5 · Not performed
- Real keyboard Tab / Shift+Tab / Escape / focus return: the preview iframe never takes real focus. The external steps in Part B §R3.4 still apply.
- file:// offline open of the standalone; it was opened only through the local preview server.
- Safari or other browsers.
- Screen reader, physical phone, beginner comprehension.
- Persistence, real authentication, wallet enforcement, provider revocation, calculation correctness.

### R5 · Still proposals (not adopted)
1. Owner-wallet funding serialization: same source wallet only.
2. Raising the original request's 20-WMON cap: rule changes block a cap above 20, and the permission review's cap message says so.
3. Position-only stop scope: blocks both sales from and additions to that position.

### R5 · Coverage gaps (this is not the complete MVP design)
- Executable LP rules and simulator: not qualified; report only.
- Exposure-limit settings, and price-guard / freshness thresholds: not qualified.
- Attempt / loss / fee consumption tracking in the demo: unknown values only.
- A minimum-gap-between-buys rule operator: not supported.
- Changing the original request's sizing: proposal.
- *(Fixed in R6/R7: a finished study reads "Study finished" with Open report, and the earlier "study is running" message is replaced.)*

---

# Part A · Current design

## A1. Files and how to open
- `source/Edge OS.dc.html`: editable. Needs `source/support.js` and `source/_ds/…` beside it.
- `Edge OS standalone.html`: single file. It has no external `<link>`, `<script>` or `<img>` URLs, and its fonts are inlined.
  - I opened it only inside the design preview iframe (served locally). A file:// open with the network off was not tested.
- The dark bar is **Design review controls**, outside the customer view:
  - frame switch (Desktop / Mobile 390), account, session, data states
  - outcomes: **Hold (default)** or Auto-resolve
  - clock: Advance 1 hour
  - market-chart verification toggle
  - per-item outcomes: Send / Confirm / Fail / Unknown; wallet Ready / Failed / Unknown; permission Pass / Fail; start Succeeds / Fails; record first check; record trial trade; provider removal Confirmed / Failed / Unknown

## A2. Journeys (current behavior)

**Research.** Request → clarification (form or conversation, custom answer in place) → plan with budget → progress → saved report.
- The real MOE report is unchanged: no supported strategy.
- Illustrative token, trading-idea and **LP** reports are labelled as examples.
- Deployer research is unavailable, and the request is preserved.

**Rule adoption.** "Review trading rules" → revision 1, with a numeric `cap` per buy.
- An unsupported required restriction (launch age) keeps the revision non-tradable.
- "Review a change to the rule" can remove it into linked revision 2 (explicit adoption).

**Ordinary rule revision.** "Review rule change" appears on the rule card, under the agent's More actions, and in the permission review when per-buy exceeds the cap.
- Editable: entry rise, minutes, volume multiple, strategy cap (≤ the user's 20-WMON request), exit, schedule, additions.
- Shows Revision N: old → Revision N+1: new for every changed field, plus what's kept and which agents use the old revision.
- Saving creates a linked immutable revision. **No agent moves and no permission changes.**

**Applying a revision to an agent.** "Review applying revision N" is a separate review.
- Blocked while the agent has pending actions.
- If the agent has permission, applying ends it, and a new permission review is required.
- Open positions keep the revision they were opened under (shown on the position as "Opened under").
- Spending, balances, stops and history stay.

**Agent setup.** Create with revision N → wallet setup (waiting / failed-retry / unknown) → fund (waiting / sent / unknown / confirmed; cancellable while unsent) → permission review → checking → starting → start failed / retry → running · waiting for first check → first check recorded.
- The **next useful action** sits directly under the status facts.
- The seven-step tracker is expandable.

**Permission review (complete terms).** Each row is tagged with its source:
- **You choose:** allocation, total buy limit, per-buy, **attempts (no default)**, **loss limit (no default)**, gas limit, length, operating purpose
- **From your rule:** strategy revision, cap, restrictions, evidence
- **Fixed by platform:** wallet and network, assets and actions (fixed-input swaps on one MOE/WMON pool), stopping
- **Provider-enforced · not qualified:** recipient
- **App-checked:** sales limited to attributable inventory
- **Not qualified yet:** price guard and input freshness; exposure limit

Approval is blocked if per-buy exceeds the strategy cap ("Review rule change" is offered), or if attempts, loss or required trial fields are missing. The intro states real execution is unavailable until the thresholds are qualified.

**Optional trial.** Operating purpose is **Ongoing (default)** or **Trial**. Ongoing needs no trial, historical result or graduation.
- A trial requires a learning objective, an expected observation, a challenging observation and a stopping point in completed trades. There's no default and no mandatory duration.
- At the stopping point: new buys are blocked (`sendBlock`), approved exits continue and positions stay open.
- **Review continuing trading** removes only the trial stop, after explicit adoption. It's blocked if permission isn't active, and keeps revision, spending, losses, pending actions and exposure.
- Forward observations and a **proposed lesson (not adopted)** are shown. "Review lesson as a rule change" opens the ordinary revision review.

**Stops and removal.**
- Stop new buys / Stop all trading / position-only stop. Stopping never sells.
- Removal blocks new submissions immediately, cancels any pending permission change and shows the provider outcome (pending / unknown / failed / confirmed, demo).
- **Recovery:** "Review new permission" appears only after removal is **Confirmed**. It lists what stays (balances, positions, spending, reservations, pending actions, stops) and says the old permission is **not restored**. It then goes through checking / starting / failure / retry / running like a first activation.

**Positions and sales.**
- A sale review stores the exact quantity plus a snapshot. Any change to holdings, reservations or authority marks it out of date.
- The mobile conversation closes the sheet, reveals the review and focuses it. The reply quotes the reviewed quantity. Return to this position keeps the review open.

**Wallet submission queue.** One queue per agent wallet. Owner funding from your wallet queues behind earlier owner funding from the same wallet; this is a **proposal pending approval**, never a global block.
- A Sent or Unknown action blocks the next send from that wallet. The queued item shows its blocker, status, time and age, and whether an exit is delayed.
- Once the blocker clears, a stale unsent buy or sale becomes **Expired**: not sent, reservation released, with "Prepare again with current prices", which opens a fresh review.
- Unknown is never failed by time, never releases its reservation and is never duplicated.

**View market chart.** A secondary action on the MOE report and position detail. It shows network, pool, price unit and provider.
- **Unavailable by default:** the exact pool isn't verified, so no link is offered.
- The "Verified (demo)" state shows a button that opens nothing.
- Copy separates current external prices from saved research, simulated balances and account values.

## A3. Production enforcement boundaries
Production must enforce these at admission, server-side, independent of any button:
- buy ≤ min(strategy cap, mandate per-buy); total, allocation, attempts and loss limits; an executable revision (no unsupported required meaning)
- one submission queue per wallet and network; Unknown blocks the next submission until reconciled; no time-based failure; no duplicates; no exit bypass
- recheck at send time: permission status and version, expiry, agent, position and trial stops, balances, reservations, price guard, input freshness
- immutable revisions; agent–revision binding; a changed executable revision requires new authorization
- removal → provider confirmation before a new mandate; nothing restored automatically

## A4. Authoritative data vs demo calculations
**Future API-owned:**
- research request, clarification, plan, progress, report
- rule revision (fields, numeric cap, unsupported list, lineage)
- agent (revision binding, setup, run state, scheduled and recorded checks)
- mandate (all terms, version, purpose, trial fields and progress)
- provider removal status
- actions with status history and queue position
- positions with revision attribution
- prices with times; market-chart destination verification

**Demo-only:**
- effective per-buy, available balances, sale estimates
- queue-blocker search and "minutes since" text
- staleness = any clock advance
- illustrative study, LP and test numbers

## A5. Unresolved configuration (qualification needed; not invented)
| Setting | Source when qualified | Current design state |
|---|---|---|
| Price-guard and input-freshness thresholds | Platform | "Not qualified yet"; execution stated unavailable |
| Queued-intent expiry window | Platform | Demo rule only (any clock advance) |
| Mandate profile numbers (attempts, loss, gas, allocation bounds) | User within platform bounds | User entry, no defaults; bounds undefined |
| Exposure-limit valuation unit and price source | Platform / qualified provider | Shown unavailable |
| Recipient enforcement | Qualified provider | Tagged "Provider-enforced · not qualified" |
| LP rule profile, venue, simulator | Platform | LP report states rules unavailable; no live LP |
| Market-chart pool address and provider page | Platform | Unavailable by default |

## A6. Coverage
| Journey | Status |
|---|---|
| Research entry → report (trading idea) | Designed and exercised |
| Token report, deployer unavailable, test on past prices, memory, add-ons | Designed but unchecked this pass |
| Rule review, restriction-removal revision | Designed and exercised |
| Ordinary rule revision (diff, save, lineage, cap > 20 blocked) | Designed and exercised |
| Apply revision to agent with permission / with pending actions | Designed but unchecked |
| Agent setup → first check | Designed and exercised (R3; not re-run end to end in R4) |
| Complete permission terms, no-default attempts and loss | Designed and exercised |
| Optional trial → stopping point → continue (cancel and adopt) | Designed and exercised (source) |
| Removal → provider confirmed → new permission → start fail / retry → running | Designed and exercised (source; standalone up to the recovery button) |
| Stops, position stop, resume | Designed and exercised (R3) |
| Wallet queue, stale intent expiry and prepare again | Designed and exercised |
| LP report | Designed and exercised (renders); LP rules and live LP not designed (unqualified) |
| Market chart unavailable / verified (demo) | Designed and exercised |
| Exposure-limit editor | Not designed (unqualified) |

## A7. Verification · this pass
All checks were scripted DOM clicks in the preview iframe. Mobile = Mobile 390 frame.

| Check | Result |
|---|---|
| T-0 Unknown queues S-10 (source, standalone) | PASS |
| T-0 stays Unknown after a 1-hour clock advance | PASS |
| After T-0 confirmed: stale S-10 → Expired; Prepare again opens a fresh review that rechecks authority (blocked: permission expired) | PASS |
| Ordinary revision: Save disabled without changes; cap 25 blocked; cap 12 shows 20 → 12; save → revision 3, revision 2 unchanged, "No agent or permission changed" | PASS (lineage text bug found and fixed in this pass; fixed text not re-run) |
| Removal supersedes pending extension; no stale permission-check outcome remains | PASS |
| Stop new buys before the first trade (Agent C) | PASS |
| Mobile: half-sale of 200 → review 100, sheet closed, review visible, Return keeps the review | PASS |
| Market chart on mobile shows Unavailable | PASS |
| Removal recovery offered only after Confirmed (source, standalone) | PASS |
| Trial: blocked without fields; stopping point after 2 trades; cancel keeps the stop; adopt removes it | PASS (source; earlier this pass) |
| New permission: blocked without attempts and loss; check → start fail → retry → running | PASS (source; earlier this pass) |
| Standalone: external URLs 0; console errors 0 | PASS |
| Sizing 30 / 20 / 10 | UNCHECKED this pass (code unchanged since R3 PASS, but the permission review was extended) |
| Apply revision with permission / with pending actions | UNCHECKED |
| Funding alone never activates; check and input timestamps agree | UNCHECKED this pass (R3 PASS) |
| Real keyboard Tab / Shift+Tab / Escape / focus return | UNCHECKED: the preview iframe never holds real focus. Steps are in Part B §R3.4. |
| Human comprehension, accessibility, persistence, wallet isolation, provider enforcement, calculation correctness | Not established |

## A8. Decisions that need approval
1. **Owner funding queue:** should funding from your wallet wait behind an earlier unresolved funding transfer from the same wallet? It currently does, labelled as a proposal.
2. **Raising sizing above the original request:** the revision review blocks a cap above the 20 WMON stated in the research request. Should raising it require a new research request, or a separate "change my request" review?
3. **Position stop scope:** it currently blocks both sales from the position and additions to it.

---

# Part B · Historical repair record (superseded where it differs from Part A)

## Revision 3 record (last verified)

Prepared 2026-10-07. **Revision 3** (§R3) repairs three defects from the latest verification: strategy sizing versus permission, the wallet-wide submission queue, and the mobile conversation-to-review transition. It also makes smaller clarity and contrast repairs and adds an MVP coverage inventory.

- Revisions 2 (§0) and 1 (§1–10) still apply except where §R3 marks them **superseded**.
- No separate findings file was attached this round. Defects were reproduced from the reproduction steps in the request.
- Impeccable (Operate) and Unslop were not available and did not run. Their principles were applied by hand: one prominent next action, plain status text, expandable detail, persistent labels.

**Demo JavaScript in these files isn't production transaction, authority or reconciliation code.** It models screens and states only.

## R3.1 Finding dispositions

| # | Finding | Disposition | Evidence (scripted DOM clicks in the preview iframe) |
|---|---|---|---|
| 1 | Strategy limited to 20 WMON per buy could get a 30-WMON permission | **Fixed.** The rule revision stores a numeric `cap` (20). `activationBlock` rejects `perBuy > cap`, and the permission review explains it inline. No silent edit to the strategy and no auto-revision. A larger amount would need a new rule revision, which this design doesn't offer for sizing ("doesn't offer for sizing yet"). `sendBlock` also refuses any buy above min(cap, permission). The permission review defaults per-buy to min(cap, previous default). | Source, full journey (study → rule rev 1 → Agent D → setup → remove-restriction rev 2 → move agent → fund 40 WMON / 0.5 MON → permission): **30** → alert "Most per buy can’t be more than 20 WMON…", Approve disabled, row "Strategy cap 20 · this permission 30 · effective 20". **20** (default) → row "cap 20 · permission 20 · effective 20", Approve available. **10** → Approve enabled; after approval the agent page showed "Strategy cap per buy 20 WMON (revision 2) · Permission per buy 10 WMON · Effective most per buy 10 WMON". **Existing mandates:** rule changes create new revisions; an agent moves revision only through its own review and only before permission. Verified by code inspection, not by a separate run. |
| 2 | A sale could be sent while Agent A's T-0 was Unknown | **Fixed.** One submission queue per wallet (agent wallet, or your wallet for funding). Any other Sent or Unknown action from the same wallet blocks sending. This applies to buys, sales and withdrawals from the agent wallet, and to funding from your wallet. The guard runs inside `sendBlock`, which both reviewer Send and auto-resolve call. The reviewer offers only "Send" for unsent items (Confirm/Fail/Unknown are no longer possible on something never sent). Unknown never resolves automatically. When the blocker resolves, permission, stops and quantities are rechecked at send time. | Source and standalone: S-10 (500 MOE, P-101) → Send → "Queued, not sent: Agent A’s wallet has purchase T-0 (10 WMON) unknown since 10:45 UTC (15 min)… This exit is delayed until then…". Status "Queued · not sent". About 5 s of auto-resolve: S-10 stayed Waiting, T-0 stayed Unknown. Agent B withdrawal W-11 → Sent (not blocked by A). Source: T-0 Confirm → S-10 Send → Sent. Standalone: T-0 Confirm → Stop all trading → S-10 Send → "Not sent: all trading is stopped". |
| 3 | Mobile: review hidden behind the sheet; reply said "half" for 200 MOE; Return dropped the review | **Fixed.** When a chat request opens a review on mobile, the sheet closes, the review scrolls into view and focus moves to its heading. The reply quotes the reviewed quantity: "Opened a sale review for exactly 100 of the 200 MOE in Agent A · MOE position 2 (DEMO-AGENT-A-001)". **Return to this position** now only closes the sheet (the context is already the current page); the review stays. Cancel is explicit. Ambiguous choices are labelled with exact amounts. | Source and standalone at 390: sheet closed; title "Sell 100 MOE from Agent A · MOE position 2"; inside the scroll area; focus spy recorded `rv-title`. After Return to this position the review was still present. Ambiguous "Sell half my MOE" offered "Sell half: 500 of 1000 · Agent A · position 1", "100 of 200 · Agent A · position 2", "300 of 600 · Agent B · position 1". Choosing Agent B opened "Sell 300 MOE from Agent B · MOE position 1", which correctly blocks: cost and price missing. |
| 4a | Agent's useful action buried | **Fixed.** A "next action" panel sits directly under the status facts, with one title, one sentence and the primary control: wallet setup / retry, add funds, review permission, trading unavailable for this revision, retry start, Stop this agent. The seven-step lifecycle is collapsed by default. Secondary permission actions stay grouped under "Change permission or continue". | Agent D sequence observed: "Next: add funds" → "Next: review trading permission" → "Permission being checked" → "Agent starting (demo)" → "Running (demo) · waiting for first check" → "… waiting for next check" with **Stop this agent**. Screenshot 07. |
| 4b | Placeholder contrast | **Fixed.** `::placeholder { color: var(--color-neutral-700) }` (#645c50). Computed 5.53:1 on --color-bg #f5ead8 and 6.02:1 on neutral-100. The rule is present in the rendered stylesheet. | Safari's computed style for ::placeholder doesn't report a pseudo-element colour, so the ratio was computed from the token value. |
| 4c | Real keyboard behavior in the mobile sheet | **UNCHECKED.** The preview iframe never holds real keyboard focus (`document.hasFocus()` false), so native Tab, Shift+Tab and Escape can't be performed here. | See R3.4 for exact external steps. |

**Superseded by R3:**
- §0.6 "Stale sale" steps: Agent A's T-0 Unknown now queues the withdrawal. Confirm T-0 first.
- §1 Review-tools description: unsent items now have only "Send".
- §3 component note on the agent page's control placement.

## R3.2 Production enforcement boundaries
The UI checks here are design behavior. Production must enforce them server-side at admission, independent of any button:
- **Strategy and mandate:** every buy is ≤ min(strategy revision cap, mandate per-buy), ≤ the remaining mandate limit and ≤ the allocation. The rule revision must be fully executable: no unsupported required conditions.
- **Submission queue:** one queue per agent wallet and network, plus the owner wallet for owner-signed transfers. A Sent or Unknown transaction blocks the next economic submission from that wallet until reconciled. Unknown never times out into Failed. Exits get no bypass. Each wallet is independent.
- **Eligibility is rechecked at send time:** permission status and version, expiry, agent and position stops, balances and reservations.
- **Revisions are immutable:** agent–revision binding and permission review both reference the exact revision id.

## R3.3 Authoritative data vs demo calculations (additions)
- **Future API-owned:** `rule_revision.cap_per_buy` (numeric, per revision); mandate `per_buy`; queue state per wallet (ordered action ids, blocker id, blocker status and time); action status history.
- **Demo-only:** effective per-buy = min(cap, permission); the queue-blocker search over the in-memory action list; "minutes since" text.

## R3.4 Checks this pass
Source = `Edge OS.dc.html` opened in the design preview iframe. Standalone = `handoff/Edge OS standalone.html` opened the same way, which is locally served, not a file:// open.

The standalone has no external `<link>`/`<script>`/`<img>` URLs. Its stylesheet has 8 inlined @font-face rules and no fonts.googleapis or fonts.gstatic references. Full offline behavior (file:// with the network off) was **not** tested.

| Check | Source | Standalone |
|---|---|---|
| 1 Sizing 30 rejected / 20 allowed / 10 effective | PASS | UNCHECKED (journey too long for this pass) |
| Rule → agent → fund → permission → start → first check (rev 2) | PASS (ends "waiting for next check", 11:08 / interval 11:05 / next 11:13) | UNCHECKED |
| 2 Queue blocks manual and auto send; Agent B independent; post-reconcile recheck | PASS | PASS (manual, auto, stop recheck) |
| 3 Mobile chat → review visible, quantity, Return keeps review | PASS | PASS |
| Ambiguous same-token choice | PASS | UNCHECKED |
| 4a Next-action panel | PASS | — |
| Restriction blocks trading (rev 1) | PASS (agent "Trading unavailable for this rule revision") | from revision 2: PASS |
| Stop all trading blocks unsent sale | PASS (previous pass) | PASS |
| Console errors | none | none |
| Native Tab / Shift+Tab / Escape / focus return in the 390 sheet | UNCHECKED | UNCHECKED |
| Focus actually landing (vs focus() calls) | focus() calls observed via spy; real focus can't land in an unfocused iframe | same |

**External keyboard test steps** (any desktop browser, real keyboard):
1. Open `Edge OS standalone.html`. Click **Mobile 390** in the dark bar.
2. Positions → "Agent A · MOE position 2" → press Tab to **Ask about this position** → Enter. Expect focus in the message field.
3. Press Tab repeatedly. Focus should cycle only through the sheet's controls. Shift+Tab from the first control should go to the last.
4. Tab to "Sell half of this position" → Enter. Expect the sheet to close, a review "Sell 100 MOE…" at the top, and focus on its heading. Tab reaches the Half/All radios (arrow keys move between them), then Approve and Cancel.
5. Activate **Cancel · nothing changes**. Expect focus on the page title or the opening control.
6. Reopen the sheet and press Escape. Expect it to close with focus back on **Ask about this position**.

## R3.5 MVP design coverage inventory
"P43" here means the first-release app shell and first Research handoff. Later slices are tracked separately. Passing this repair doesn't make the whole MVP design complete.

| Journey | Status |
|---|---|
| App shell, navigation, sign-in / session states | Designed and exercised |
| Research entry, clarification (form + conversation), unsupported / unavailable, malformed preparation | Designed and exercised |
| Study plan with budget, progress, failure, stop | Designed and exercised (failure via review tools) |
| Real MOE report | Designed; content unchanged |
| Illustrative token report | Designed but unchecked this pass |
| Rule review, revision 1, restriction-removal revision 2, agent re-binding | Designed and exercised |
| **Ordinary post-adoption strategy revision** (change entry, exit, cap or schedule of an adopted rule) | **Not yet designed.** Only the restriction-removal revision exists. Consequence: a 20-WMON cap can't be raised without a new rule from research. |
| Optional past-price test (settings, result, unavailable, saved) | Designed but unchecked this pass |
| **Optional trial / forward observation** (live-flow trial with stopping point) | **Partially modeled.** `purpose:'trial'` and the trial stopping point existed in v0.12.2. This design has no trial selection or trial results screen. |
| Agent creation, wallet setup states, funding, activation, start, first check | Designed and exercised |
| **Complete mandate terms** (recipient, action types, gas, allocation, expiry, per-buy, total) | **Partially modeled.** Per-buy, total, allocation, gas and hours are editable. The recipient and allowed actions are fixed text. There's no editor for slippage, price-impact or cooldown terms; these aren't defined in the accepted extract either. |
| Continuation, extension, raise limit, removal superseding pending change | Designed and exercised |
| **Removal → new permission recovery** | **Not yet designed.** After removal the page says restoring needs a new permission review, but there's no screen for it. Consequence: a removed agent can only be withdrawn from. |
| Provider removal pending / confirmed / failed / unknown | Designed; outcomes exercised only via review tools |
| Agent stop, position-only stop, resume | Designed and exercised |
| Wallet-wide submission queue | Designed and exercised (R3) |
| Positions list / filters / detail / sale states / closed history | Designed and exercised |
| Funds: personal and agent wallets, funding, withdrawal, cancel unsent, unknown | Designed and exercised |
| Memory, add-ons | Designed but unchecked this pass |
| **LP research / rule / simulation (later slice)** | **Not yet designed** beyond the inventory text on Research home |
| External exact-pool chart link | Not yet designed |

**Open product decisions:**
1. Should sizing above a strategy cap route to a rule-revision screen? If yes, it needs the ordinary revision journey above. Until then, users must start a new study to change sizing.
2. Should a queued unsent action expire if its blocker stays Unknown for a long time? It currently waits indefinitely and stays cancellable. Expiring it would need a defined customer message and no auto-retry.
3. Should funding from your wallet be blocked while an earlier funding transfer is Unknown? It currently is (shared owner-wallet queue). If owner transfers shouldn't queue, the restriction is unnecessary friction.
4. The decisions recorded in §10 (research progress auto-advances; position stop blocks both sales and additions) are still open.

## R3.6 Screenshots added
- `07-desktop-agent-next-action-and-caps.jpg`: Agent D next action and caps after the first check.
- `08-mobile-review-from-conversation.jpg`: 390 review opened from conversation, sheet closed.
- `09-desktop-sale-queued-behind-unknown.jpg`: standalone, S-10 queued behind T-0.

Nothing here establishes human comprehension, full accessibility, persistent operation, real wallet isolation, provider revocation or backtest correctness.

---

## Revision 2 record

Prepared 2026-10-06. **Revision 2** (§0, below) fixes the two findings from the focused verification: unsupported restrictions must block trading, and check/data timestamps must agree. Sections 1–10 describe revision 1 and still apply, except where §0 replaces them. Visual system (Organic), navigation and information structure are unchanged.

## 0. Revision 2: restriction enforcement and consistent timestamps

### 0.1 Restriction retained (default)
- The trading-idea request "skip anything that launched less than a week ago" can still be researched on the named MOE pool with launch age unchecked. That only permits the observational study.
- The **Review trading rules** step no longer has a generic "I understand" acknowledgment. Its "Your restriction" row says the condition stays on the rule and that agents can't be activated with this revision.
- Saving creates **revision 1** with the condition stored as an unsupported requirement (`unsupported: ['skip anything…']`).
- **Agents → saved rule (revision 1):** shows "This rule requires a token-age check that is not available. Keep this condition and leave trading unavailable, or review a change to the rule." It offers **Review a change to the rule** (primary) and creating an agent (allowed; wallet setup and funding are harmless).
- **Agent on revision 1:**
  - Permission and stops: "Trading unavailable. …". No **Review trading permission** control is shown.
  - Tracker: "Permission approved by you · **Blocked**".
  - Agent: "Not running".
  - Add funds is still available under More actions. Funding doesn't change eligibility.

### 0.2 Explicit revision
**Review a change to revision 1** shows:
- the original condition in your words
- why trading is unavailable
- what copies across unchanged

There are two radio choices, **neither preselected**: "Keep this condition" or "Remove this condition in revision 2".
- No replacement condition is offered, because Edge OS has no supported way to check token age. The pool doesn't prove token age, and no launch-age tool was invented.
- Choosing removal reveals an exact adoption checkbox: "I adopt revision 2: remove 'skip anything that launched less than a week ago' from this rule." Save stays disabled until it's ticked.

Saving creates a **new linked revision 2** (`prev` = revision 1, `root` kept):
- Revision 1 stays saved and unchanged. Its card says "Revision 2 exists without this condition."
- Revision 2's card says "Changed from revision 1: you removed '…'."
- The research request, its restriction and the unfavorable study evidence are untouched.

An agent already on revision 1 stays on it. **Review moving to revision 2** shows Now / After / Stays the same and needs its own adoption. Only after that does **Review trading permission** appear. The permission review's Rule row then reads "… · revision 2", and its Sizing and restrictions row records the removal.

**Cancel** leaves everything unchanged. The message says "Nothing changed. Revision 1 keeps '…'; trading with it stays unavailable."

### 0.3 Eligibility enforced in handlers, not only on screen
`ruleBlock(rule)` is checked in:
- `activationBlock` (approval)
- the automatic tick: permission check → fails back to Not approved with a history note; starting → doesn't start; first check → not recorded
- reviewer **Pass check**: refuses and records why
- reviewer **Start succeeds**: refuses
- reviewer **Record first check**
- `sendBlock`: an unsent trade isn't sent

Unfavorable evidence alone never blocks. Rules A and B and revision 2 proceed with their evidence attached and no backtest required.

### 0.4 Timestamps from one evaluation record
Each demo check record is `{ t, input, text }`. `input` is the end of the completed five-minute interval read after the assumed 3-minute delay.
- **Price data** reads "Completed five-minute interval ending <input>, read at the <t> check (demo record)", or "Not recorded" if the record has no input time.
- Before the first check, Last check and Price data both read **"No check completed yet"**, and Next check shows the scheduled time.
- The hardcoded "Fresh at its last check (completed 10:05 UTC interval)" is removed. Fixtures A, B and C now carry input 10:05 for their 10:10 check.
- A future first check can't appear completed. The automatic path records it only once the demo clock reaches it. The reviewer button is labelled **"Advance clock to HH:MM UTC and record first check"**; it sets the clock and says so in a status message.
- Next check = check time + rule interval.
- The four ideas stay on separate lines: Agent running (demo), Last check (the decision), Trading results, and "Evidence the rule works: Not established".

### 0.5 Revision and eligibility boundaries (summary)
- Observational research with incomplete data ≠ a tradable rule.
- A rule revision is immutable once adopted. Changes create a new linked revision.
- An agent binds to one revision. Moving it is a separate adopted review, available only while it has no permission.
- Permission review always names the agent's exact revision.
- A rule with unsupported required meaning can't be approved, checked, started, recorded or sent.

### 0.6 Confirmation pass (this revision)
Source = `Edge OS.dc.html` in the design preview. Standalone = `Edge OS standalone.html`. Interaction was scripted DOM clicks in the preview iframe.

| Check | Expected | Observed | Result |
|---|---|---|---|
| A. Retain restriction | Research finishes; rule saved as revision 1; trading unavailable | Source: study finished; rule review had no generic acknowledgment; toast stated trading unavailable; Agent D funded with 30 WMON and 0.5 MON; tracker "Permission approved by you · Blocked"; no Review trading permission control. Standalone: same through wallet ready; Review trading permission absent. | PASS (source, standalone) |
| B. Explicit revision | Original inspectable; change visible; agent and permission bound to revision 2 | Radios unselected; Save disabled until removal chosen and exact checkbox ticked; "Revision 2 saved … Revision 1 is unchanged"; both revisions listed with lineage; move-to-revision review showed Now/After; permission review "Rule: … · revision 2". | PASS (source) · standalone UNCHECKED |
| C. Cancel change | Restriction stays; activation unavailable | "Nothing changed. Revision 1 keeps '…'; trading with it stays unavailable."; still "Trading unavailable". | PASS (source) · standalone UNCHECKED |
| D. Reviewer outcomes on blocked rule | No bypass | Auto-resolve on for about 5 s with a funded blocked agent: stayed "Not running · Not approved" (source and standalone). Manual: no permission-check, start or first-check outcome is offered for the blocked agent, because approval can't be created. The guards in Pass check, Start succeeds and Record first check were only inspected in source, not triggered. | PASS for auto · manual guard UNCHECKED |
| E. First check after clock advance | Times agree | Before: Last check "No check completed yet. First check scheduled 11:08", Price data "No check completed yet". After "Advance clock to 11:08 UTC and record first check": clock 11:08; Last check 11:08, interval ending 11:05; Price data "interval ending 11:05, read at the 11:08 check"; Next check 11:13; Agent "Running (demo) · waiting for next check". | PASS (source) · standalone UNCHECKED |
| Stale sale | Fresh review required | Review "Sell 500 MOE" became out of date after the withdrawal confirmed; Review again → 250; approved exactly 250. | PASS (source) |
| Extension then removal | Stays removed | No permission-check outcome left after removal; permission "Removed …". | PASS (source) |
| Unsent sale after all-trading stop | Not sent | "S-10: Not sent: all trading is stopped for Agent A. It stays unsent." | PASS (source) |
| Unsent sale after removal | Not sent | "S-11: Not sent: Agent A permission is removed." | PASS (source) |
| Console | No errors | No errors in source or standalone during these runs. | PASS |
| Mobile review visibility, focus return | As in revision 1 | Not repeated this pass | UNCHECKED |
| Native Tab / Shift+Tab / Escape in mobile sheet | Real keyboard | The preview iframe doesn't take real keyboard focus. Earlier passes used simulated key events only. | UNCHECKED |

### 0.7 Disposition of the focused verification findings
1. **Unsupported required restriction allowed activation.** Fixed (§0.1–0.3). Evidence: checks A–D.
2. **Hardcoded price-data freshness.** Fixed (§0.4). Evidence: check E.

Earlier repairs were preserved and re-checked where listed above.

### 0.8 Still not established
- Human comprehension
- Full accessibility
- Native keyboard behavior
- Physical phones
- Persistent backend, real wallet enforcement or provider revocation
- Backtest correctness

The skills Impeccable and Unslop were not available and did not run.

---

## Revision 1 record

Prepared 2026-10-06. Revision 1 repaired the findings in `EDGE_OS_CLAUDE_DESIGN_PHASE_B_REVIEW_2026-10-06.md` and added the strategy-to-running-agent lifecycle.

It's a design artifact. Interactions are illustrative. It isn't a backend, wallet, simulator, worker or trading system. No API contract is proposed.

Files:
- `source/Edge OS.dc.html` (editable; needs `source/support.js` and `source/_ds/organic-…/` beside it)
- `Edge OS standalone.html` (offline single file)
- `source/Edge OS Research.dc.html` (Phase A direction board, unchanged)
- `screenshots/` (selected states, see §9)

Impeccable (Operate) and Unslop were not available in this environment and did not run. I applied their principles by hand: familiar controls, plain language, one primary action per panel, keyboard dismissal and focus return, expandable detail.

## 1. Running and navigating

Open `Edge OS standalone.html`, or `source/Edge OS.dc.html` with its dependencies.

**Design review controls** (dark bar on top) sit outside the customer view.
- **Desktop / Mobile 390** switches the frame. Windows under 760px wide always use mobile. Under 1200px wide, the desktop conversation starts closed.
- **Show review tools · N pending outcomes**: the button shows how many outcomes are waiting.
  - **Outcomes** now default to **Hold**. Pending items wait for a manual outcome:
    - per action: Send / Confirm / Fail / Unknown
    - wallet setup: Ready / Failed / Unknown
    - permission check: Pass / Fail
    - agent start: Start succeeds / Start fails
    - Record first check
    - provider removal: Confirmed / Failed / Unknown
  - **Auto-resolve** is optional. It still respects current permission and stops: blocked unsent trades aren't sent.
  - Research study progress always advances on its own. It's task progress, not an outcome.
  - **Clock**: Advance 1 hour. This expires the 12:00 permissions of Agents A and B.
  - **Account**: Returning account or New empty account.
  - **Session** and **Data** states.
  - **Make next preparation fail**.

**Customer destinations:** Research, Agents, Positions, Funds. The sidebar holds them on desktop and bottom tabs on mobile. Breadcrumbs name the record.

**Conversation:**
- Desktop: a right-hand panel, with "Open conversation" to reopen it.
- Mobile: a docked "Ask about …" bar opens a modal sheet. Escape closes it, Tab is contained inside it, and focus returns to the bar.
- Each thread is attached to the record on screen, with an "About" heading, the record's update time and a return link.

### Named screens

| Screen | Path |
|---|---|
| Sign in · Session unavailable · Loading | Review tools → Session |
| Research home | Research |
| Draft · trading idea (meaning, observation period, unsupported launch-age restriction) | "Trading idea" starter → Prepare investigation |
| Draft · token investigation | "Token investigation" starter |
| Draft · wallet question, not available | "Wallet or deployer question" starter |
| Draft · preparation failed | Review tools → Make next preparation fail, then submit |
| Study plan (incl. **volume condition** selector) | Draft → Review the study plan |
| Study progress · running / failed / stopped | Plan → Adopt plan and start study |
| Report · MOE (real, unchanged) | Saved: "What happens after MOE rises in price?" |
| Report · token (illustrative) | Saved: "Did DEMO's launch succeed?" |
| Report · trading idea (illustrative) → **Rule review** | Finish a trading-idea study → Review trading rules |
| Agents list · saved rules (with revision) · empty state | Agents |
| Agent detail · **From rule to running agent** tracker · status · results · wallet · permission and stops · **Activity** | Agents → an agent |
| Wallet setup waiting / failed / unknown | Create an agent with revision N |
| Activation review | New agent → funded → Review trading permission |
| Permission checking → active → agent starting → running · waiting for first check → first check recorded; start failed | After approval, via Review tools |
| Stop review (new buys / all trading) · Resume review (shows remaining authority) | Agent detail → Stop this agent / Review resuming |
| Change permission or continue (grouped): Continue, Add 24 hours, Raise total buy limit, Remove permission | Agent detail → expandable group |
| Removed · provider removal pending / confirmed / failed / unknown (demo) | Remove permission; Review tools for outcomes |
| Test on past prices · settings / authored result / unavailable / saved | Agent detail → Test on past prices |
| Memory · Add-ons | Agent detail tabs |
| Positions list · filters · empty · filtered-empty · loading · error · stale | Positions |
| Position detail · sale review (exact quantity, after-sale quantity) · out-of-date review · **position-only stop** · action timeline | Positions → a position |
| Same-token targeting in conversation | Positions → conversation → "Sell half my MOE" |
| Funds · wallets · funding / withdrawal review · waiting (cancellable) / sent / unknown / confirmed · activity timeline | Funds |

## 2. Design tokens (Organic `styles.css`, unchanged)

- **Color:** `--color-bg #f5ead8`, `--color-surface #ebddc5`, `--color-text #201e1d`, `--color-accent #c67139`, `--color-accent-2 #7a8a5e`. Each role has a 100–900 ramp.
- **Type:** Caprasimo (`--font-heading`) for titles and the wordmark only. Figtree (`--font-body`) for everything else. Tabular numbers.
- **Shape and depth:** radius `--radius-md 16px` and `--radius-lg 28px`; pills for buttons, inputs and tags; `--shadow-sm/md/lg`.

**Adaptations in this design (for the design-system owner):**
- `.btn` uses the body font at 700 weight, with a minimum height of 44px.
- Primary buttons use `accent-700` (hover `accent-800`) with `neutral-100` text, to reach 4.5:1 contrast.
- Secondary text, links and table headers use `neutral-800` or `accent-700`.
- `select.input` uses a Lucide chevron.
- The system's `:focus-visible` ring is kept.
- Reduced motion is respected.

## 3. Component guidance

- **Status facts row.** One fact per cell: Agent run state, Wallet, Permission, Stop, Open positions. Process, result and authority are never merged.
- **Setup tracker ("From rule to running agent").** Seven steps, each marked Done, Now or Later. Each line says what the step completes and what remains. It's open until all seven are done, and labelled as demo states. Active permission alone never reads as "running".
- **Review panel.** Used for sale, transfer, rule, activation, stop, position stop, resume, permission change and removal.
  - It opens at the top of the page that owns the record, scrolls into view and takes focus. Cancelling returns focus to the control that opened it.
  - It shows exact rows, a "does / doesn't do" list, and explicit adoption checkboxes wherever values are proposed.
  - Blockers show as an alert. A stale sale review turns into "Review again with current holdings".
- **Grouped actions.** One prominent action per state, such as Stop on an active agent or the next setup step before activation. Secondary permission changes sit in an expandable group.
- **Action card and timeline.** Each status change is timestamped, for example "Requested 11:00 → Waiting 11:00 → Sent 11:02 → Unknown 11:05". Unsent items can be cancelled. Sent or unknown items stay pending and reserved.
- **Labelled rows** are used instead of tables wherever content must reflow.

## 4. Finding-by-finding disposition

| Finding | Disposition | Evidence (scripted check in the design preview, this revision) |
|---|---|---|
| P1 Sale approval can exceed displayed quantity | **Fixed.** The preview stores the exact quantity plus a snapshot of position quantity, reservations and authority. Display and approval both use the stored quantity. Any change makes the review out of date, disables approval of the old amount and offers "Review again". | Reproduced: 500 MOE withdrawal sent from P-101 (1,000) → half-sale review "Sell 500 MOE" → withdrawal confirmed → review shows "out of date: the position now holds 500 MOE (it held 1000…)" → Review again → "Sell 250 MOE … 250 MOE stay" → approve → toast "exactly 250 MOE". |
| P1 Stale permission change restores authority | **Fixed.** Every permission change bumps a version. A pending change records its base version. Removal cancels the pending change. A check result is applied only if permission is still active at the same version; otherwise it's discarded with a history note. | Approve "Add 24 hours" → Remove permission → the pending check no longer appears in Review tools; permission stays "Removed · blocked in Edge OS · provider removal pending (demo)". |
| P1 Unsent trade advances after all-trading stop | **Fixed.** Before an unsent buy or sale is sent (by reviewer or auto), it's checked against current permission, expiry, agent stop, position stop and free quantity. Blocked items stay Waiting with the reason shown. Sent and unknown items still reconcile. | Sale S-10 Waiting → Stop all trading on Agent A → Review tools Send → "S-10: Not sent: all trading is stopped for Agent A. It stays unsent." Activity shows the reason and "Cancel before sending". |
| P1 Lifecycle error (`reading 'preview'`) | **Fixed.** `componentDidUpdate` now matches the runtime's single-argument contract and tracks the previous screen and preview itself. | No console errors in source or standalone. Focus calls observed (via focus spy): open review → `rv-title`; cancel → the "Review selling half" or "Stop this agent" button that opened it; navigation → `page-title`. Mobile sale review visible inside the scroll area after opening from a scrolled position. |
| P1 Missing rule adoption and correction | **Fixed.** "Save as a rule anyway" is replaced by **Review trading rules**. Every item can be corrected before revision 1 is saved: market (fixed), entry rise, minutes in 5-minute steps, exact volume multiple, amount per buy (capped at the user's 20 WMON), exit (must be chosen), schedule, additional purchases (must be chosen), the retained launch-age restriction (explicit acknowledgment) and evidence. The observation period is shown as not being a sell rule. Rule adoption is separate from wallet setup, funding and permission. The plan now shows and allows changing the volume condition. | Rule review opened with 5% / 15 min / 1.5× / 20 WMON. Approve disabled until exit and additions were chosen. 25 WMON → "Your request limits each trade to 20 WMON." Saved revision 1 → Agents shows rule and "Create an agent with revision 1". |
| P2 Mobile conversation keyboard | **Fixed.** Escape closes the sheet. Tab is contained while the modal sheet is open (`role=dialog`, `aria-modal`). Focus returns to the "Ask about…" bar. | Escape closed the sheet and focus moved to `ask-bar`. Tab containment is implemented but couldn't be exercised here; see §7. |
| Minor: "Selling closes this position" | **Fixed.** Copy now distinguishes a half sale (the rest stays) from selling all (closes it). Neither stops re-entry. The review shows the quantity left after the sale. | Visible in the sale review and on the position page. |
| Minor: five equal permission actions | **Fixed.** Stop is the primary action. The others are grouped under "Change permission or continue". | Agent A overview. |
| Minor: auto-success default | **Fixed.** Outcomes default to Hold. | Review tools shows "Held (default)". |
| Agent-routed sale bypassing authority | **Kept blocked.** Sales are blocked for expired, removed or checking permission, an all-trading stop or a position stop. The page points to owner withdrawal, which stays available after removal. | P-103 sale review after expiry: "trading permission is expired, so an agent sale is blocked…". |

## 5. Added in this revision (per follow-up request)

**Rule revision shown throughout.** The agent's rule revision appears on:
- the rule list ("Create an agent with revision 1")
- the creation toast
- the agent header ("rule revision 1")
- the activation review rows
- the setup tracker

**Lifecycle states, all labelled demo:**
- Not approved
- Permission being checked
- Permission active, agent starting
- Start failed (with Retry start)
- Running, waiting for first check (first check scheduled at a computed time)
- Running, waiting for next check, after the first check is recorded

**Next check timing.** Next check = last check + rule interval (5 minutes or hourly). Expired or removed permission shows "Not running".

**Agent page leads with:**
1. Last check and decision
2. Next check, or a specific hold reason
3. Permission and stop
4. Waiting to reconcile
5. Price data

Below that: Trading results (completed / estimate / evidence) and Activity with timestamped action timelines linked to positions. A detailed record is expandable.

**Position-only stop.** Names its position and lists the unaffected positions and agents. It blocks sales from that position and additions to it.

**Provider removal.** Edge OS blocks new submissions immediately. The provider outcome is a separate demo state: pending, confirmed, failed (retry) or unknown.

**Transfers.** Approved transfers now wait to be sent and can be cancelled until then. Sent or unknown transfers stay pending.

## 6. Corrected state matrix

R = rendered and reachable · X = exercised in this revision's scripted batch · — = not rendered.

| Area/state | Status |
|---|---|
| Research entry, three starter kinds | R |
| Clarification incl. custom answer and conversation answer | R (X in the previous revision) |
| Unsupported restriction kept and explicitly acknowledged | R X |
| Observation period separate from sell rule | R X (rule review) |
| Plan with volume condition | R X |
| Study running / failed / stopped | R X (running) |
| Real MOE report, figures unchanged | R |
| Illustrative token and trading-idea reports | R X (trading idea) |
| Rule review, correction, adoption, revision | R X |
| Optional past-price test / unavailable / saved | R |
| Agent creation with revision; wallet waiting → ready | R X |
| Wallet setup failed / unknown | R |
| Funding waiting / sent / confirmed; cancel unsent; unknown stays pending | R X |
| Activation review with adoption | R X |
| Permission checking → active → starting → running → first check | R X |
| Start failed | R |
| Stop before first trade (Agent C) | R X |
| All-trading stop blocks unsent sale | R X |
| Position-only stop; other position unaffected | R X |
| Resume after expiry shows remaining authority and stays blocked | R X |
| Extension discarded after removal | R X |
| Provider removal pending / confirmed / failed / unknown | R |
| Stale sale review after holdings change | R X |
| Same-token targeting: direct controls and conversation | R X (conversation in previous revision) |
| Withdrawal after removal | R |
| Memory, add-ons | R |
| Empty / loading / error / stale data; session states | R |
| Mobile review visibility; conversation Escape and focus return | R X |
| LP later slice | Inventory text only |

## 7. Checks performed, results and limitations

**Performed** (scripted interaction in the design preview iframe, desktop and Mobile 390 frames; source and offline standalone):
- Every row marked X above: expected outcome matched.
- No console errors in source or standalone after repairs.
- Standalone check: Positions → sale review → cancel. No errors; focus went to the review title on open and back to "Review selling half" on cancel.

**Found and fixed during this batch (one fix pass):**
- A stale review left open from another page blocked the reveal of a newly opened review. Now any change of preview identity reveals and focuses it, and navigation clears unrelated reviews.
- Cancelling focused the page title because the opener wasn't captured. The last clicked button is now the fallback opener.
- Permission timestamps were lowercased in agent summaries.

**Not performed or not provable here:**
- Tab containment inside the mobile sheet. The preview document doesn't take real keyboard focus, so I couldn't press Tab inside it. Implemented, not exercised.
- Native radio arrow-key behavior is browser-provided. Not exercised.
- Full keyboard-only pass, screen readers, physical phones and cross-browser rendering.
- Human comprehension.
- Real wallet isolation, provider enforcement, persistent worker or backend persistence, backtest correctness.

**Remaining gaps:**
- Illustrative study findings don't change with the chosen settings.
- Rules can't yet be revised after adoption. A new revision would need its own review screen.
- No external market chart.
- The LP slice is inventory text only.

## 8. Future backend-owned records vs demo calculations

**Future API-owned** (no endpoint chosen):
- Clarification items and adoption source; plan, budget and usage; progress and partial results; reports
- Rule revisions (immutable; agent binds a revision)
- Agent setup; agent run state (starting / running / failed); scheduled and recorded checks with decisions
- Permission terms, version and check results; provider removal status
- Stops (agent and position)
- Actions with status history and shared action identity between conversation and pages
- Reservations, positions, prices with times
- Memory versions, add-on availability, session

**Demo calculations in the logic class** (display only, replaceable):
- Available = balance − pending reservations
- Remaining buy limit = limit − spent − pending buys
- Sale estimate = quantity × price × 0.995
- Estimate on unsold holdings = quantity × price − cost
- Next scheduled check (next :10 past the hour, or next 5-minute interval + 3 minutes)
- Test arithmetic copied from v0.12.2

None of these override accounting or permission.

**Real recorded research:** the MOE report only. Everything else is labelled Demo, Illustrative example or Authored example result.

**Open contracts needed:**
- Rule-revision schema (entry, exit, schedule, additions, sizing, restrictions, evidence link)
- Permission version and change-base semantics
- Unsent-action send-time eligibility check
- Agent start and first-check records
- Provider-removal outcome codes
- Stale-preview detection (position quantity, reservation and authority snapshot)

## 9. Screenshots

- `01-desktop-agent-starting.jpg`: review tools with pending outcomes, including Agent D start.
- `02-mobile-sale-review.jpg`: sale review revealed at the top on mobile.
- `03-mobile-conversation-sheet.jpg`: modal conversation sheet.
- `04-desktop-funds-pending.jpg`: Funds with pending and timeline states.
- `05-desktop-stop-review-before-first-trade.jpg`: Agent C stop review with no positions.
- `06-desktop-rule-blocked-launch-age.jpg`: standalone, Agent D on revision 1, trading unavailable (revision 2).

## 10. Decisions needing approval

1. Research study progress keeps advancing automatically while outcomes are held. Hold applies to wallet, permission, start, check, transfer and trade outcomes.
2. A position-only stop blocks sales from and additions to that position. The accepted text says it "names the position" but doesn't define the stopped actions.
3. ~~Stop all trading keeps checks running~~: already an accepted requirement (monitoring and reconciliation continue after stops). No decision needed.
