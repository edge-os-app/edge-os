# Uncoached target-trader task guide

Task OC-P40-PREP-20261010-01, issue #47. Prepared 2026-10-10. This guide prepares participant sessions. It does not contact anyone. The builder recruits and conducts all sessions. The worker never contacts a participant.

## 1. Purpose and rules

The release cut requires honest accessibility and comprehension evidence from an unfamiliar target trader where possible. Participant absence stays UNRESOLVED and never becomes demand validation or a PASS.

Rules:

- The builder runs every session. No worker or controller contacts a participant.
- Ask one neutral question at a time. Record the first answer verbatim before any explanation.
- Instructions that coach the answer are separated below and must not reach the participant before the task.
- The current application has no live execution. Every session uses the authored synthetic fixtures in the repository.
- Historical assisted prototype feedback is not new evidence. It stays in [frontend interaction result](../../prototypes/EDGE_OS_FRONTEND_INTERACTION_RESULT.md) as history.
- A participant who cannot answer, or a session that never runs, stays NOT RUN or UNRESOLVED.

## 2. Session prerequisites

| Item | Requirement |
|---|---|
| Candidate revision | Exact committed candidate from the running worktree, recorded in the observation form |
| Fixture sign-in | `scripts/p03/verify_run.py` passes the per-run P03_TOKEN_* values to the browser only through the in-memory child environment (`ui_env`), and deliberately strips token keys from HOLD output and `hold.json`. It does not publish token values in any evidence file, and `tests/p03/fixture-auth.mjs` only injects those in-memory tokens into the page. Evidence is not a manual sign-in credential. No token is exported or collected. |
| Evidence paths | The verifier sets `P03_EVIDENCE_DIR` to `evidence / "ui"`, so the browser writes `ui/ui-results.json`; the seeded `p19-fixtures.json` is at the run root. Record IDs for saved surfaces come from those exact relative paths. |
| Participant session availability BLOCKED | The default verifier stops its processes and removes the run-owned database container, volume and web build at the end of the run. A finished default run is not an available participant session. No supported authorized manual-session setup is supplied for this package. This prerequisite is BLOCKED until the controller or builder supplies one. A live or manual runtime is not invented here. |
| Surfaces | Research home, a saved no-thesis investigation, a saved compiled rule with an exact threshold (for T2), a saved P08 declaration, a saved P09 report, a saved P13 replay, Agents/Positions/Funds account views |
| Device | Desktop 1280px and a 390px viewport as available; a physical phone when available |
| Environment | Local repository run by the controller or builder; no live provider, wallet or network |
| Timing | Target five observations where participants are available; preserve actual numbers |

Each participant session must name the exact revision it ran and the evidence run ID whose record IDs it used. A notebook or the observation form in section 6 records the session.

## 3. Participant-facing tasks

Present each task as written here. Do not add synonyms, definitions or hints before the first answer. Let the participant say "I cannot tell" freely.

### Task T1: Understand a saved research result

Conductor setup: open a saved no-thesis investigation whose outcome is UNRESOLVED. The scripted fixture `no-thesis` in `apps/api/src/edge_os_api/research/fixture_interpreter.py` (scenario `no-thesis`) creates this state; the e2e test `no thesis stays an investigation and shows no study progress` in `tests/p03/e2e.spec.mjs` drives it and asserts no Save-this-revision button. Use that record, not a compiled one.

Question: "This page holds a saved research item. What does it tell you about the trading idea, and what would you want to do next? You can say you cannot tell."

### Task T2: Read the exact rule

Conductor setup: this is a separate record from T1. Rules review renders only for a COMPILED or PUBLISHED outcome with a saved draft. Select a saved compiled rule from the same run set, for example the `grouped-rule` or `tiny-threshold` fixture the e2e tests saved. `tests/p03/provenance.spec.mjs` reopens the negative and positive tiny-threshold records by their saved URL. The conductor records the exact saved revision ID used.

Question: "This rule will be saved exactly as written. What does the rule say, and what numbers would it act on? You can say you cannot tell."

### Task T3: Tell evidence from permission

Conductor setup: open the seeded account records. `scripts/p03/verify_run.py` inserts authored P19 records under the fixture owner. The P19 record IDs are at the run root in `p19-fixtures.json`; the browser run-key observations are in `ui/ui-results.json` (key `p19-context-*`). Open Agents, then Positions, then Funds from the side navigation. Do not open Reviewer or scenario controls; this run has none.

Question: "Without doing anything, what does this page let you see, and what does it not let you or the agent do yet? You can say you cannot tell."

### Task T4: Understand saved records after reopen

Conductor setup: reuse the saved P09 report ID and P13 replay ID from the same evidence run (`ui/ui-results.json` keys `investigation-*` for the declaration/report and `spot-replay-*` for the replay, both saved by the verifier; `tests/p03/reopen.spec.mjs` reopens the saved run IDs, it does not create new ones). Open the report, then the replay, and reopen one of them. Because the default verifier tears the run down afterward, this task requires a live run held open by an authorized participant-session setup; that prerequisite remains BLOCKED in this package.

Question: "This record was saved earlier. What happens when you reopen it, and what does the page say did not run again? You can say you cannot tell."

### Task T5: Distinguish pending from confirmed

Conductor setup: the P19 seed contains ACTION records in `QUEUED`, `SUBMITTED`, `CONFIRMED`, `REVERTED` and `SUBMISSION_UNKNOWN` states (fixture file `apps/api/tests/fixtures/account_views/account-records-v1.json`; `scripts/p03/verify_run.py` seeds them). Open Positions, filter to an agent, and show one pending or unknown action beside a confirmed one. Record which record IDs were shown.

Question: "Show me which item is finished and which one is still waiting, and what that means for the tokens held. You can say you cannot tell."

## 4. Expected answers for the controller

This section is for the builder and controller only. It must not reach the participant before the corresponding first answer. It states what the interface is documented to show, per the accepted sources, so the conductor can judge a first answer without coaching.

### T1 expected

The saved no-thesis request shows an UNRESOLVED outcome, "No study ran", and no Save-this-revision action. It is an investigation, not a compiled rule. Unsupported or unscripted requests keep their restriction text and show "Not supported yet" or "Could not be interpreted" as a system message, not a verdict on the idea. The page grants no permission. Sources: RequestPage behavior and `tests/p03/e2e.spec.mjs` no-thesis, unsupported and unscripted tests.

### T2 expected

The rule review renders the exact compiled rule with its thresholds and groupings, the immutable content hash, and provenance rows for the exact values. Because this record is COMPILED or PUBLISHED, the saved revision reopens with the same text after restart. Sources: RulesReview, `tests/p03/provenance.spec.mjs`, `tests/p03/reopen.spec.mjs`, `docs/implementation/P06_COMPILER_PROFILE.md`.

### T3 expected

Agents, Positions and Funds show authored synthetic records. The build-scope notice says account views are not live wallet data and saving a rule grants no permission. Permission snapshots are immutable examples, not current authority. Sources: Shell notice, AccountViews, `docs/implementation/ACCOUNT_VIEWS_PROFILE.md`, `docs/contracts/account-views/README.md`.

### T4 expected

Reopening a saved P09 report shows the stored report and states no rerun. Reopening a P13 replay loads the exact saved result and says the replay did not run again. Source: `tests/p03/reopen.spec.mjs`.

### T5 expected

Pending, unknown, queued, submitted and confirmed actions are distinct states. A pending action is not a completed sale; holdings stay until confirmation, and unknown results keep their reservation. Sources: PositionRecords/FundRecords and `tests/p03/e2e.spec.mjs` P19 account views; `docs/implementation/ACCOUNT_VIEWS_PROFILE.md`.

## 5. Session flow

1. Record candidate revision and session identity in the observation form.
2. State the session is a research exercise, no real money moves, and the participant may stop anytime.
3. Ask T1 alone. Record the first answer verbatim before any explanation.
4. Only after the first answer, allow a natural explanation and note it as assisted.
5. Repeat one task at a time for T2 to T5.
6. Record assisted or unassisted, failures, and only permitted feedback (see section 7).
7. Do not convert a missing answer, a question back, or a browser check into a PASS.

## 6. Observation form

One form per participant per revision. All fields are required; leave unknown fields as NOT RUN rather than guessing.

```
Participant id:
Role (trader / builder / teammate):
Candidate revision (exact SHA):
Evidence run id (from .scratch/p03/evidence/<run_id>; record IDs from ui/ui-results.json and the run-root p19-fixtures.json):
Record IDs shown per task (T1 no-thesis URL, T2 revision id, T4 report/replay id, T5 action ids):
Date and time:
Device and viewport (desktop 1280 / 390px / physical phone):
Session type (assisted / unassisted):

Task T1 (record first answer verbatim before explaining):
First answer:
Assisted explanation given? yes/no
Observed failure or confusion:

Task T2 (repeat the same flow):
First answer:
Assisted? yes/no
Observed failure or confusion:

Task T3:
First answer:
Assisted? yes/no
Observed failure or confusion:

Task T4:
First answer:
Assisted? yes/no
Observed failure or confusion:

Task T5:
First answer:
Assisted? yes/no
Observed failure or confusion:

Permitted feedback given (section 7):
New defect suspected (to controller evidence, not fixed here):
Verdict per task: NOT RUN / UNRESOLVED / observed answer recorded
```

A verdict of Pass is never derived from this form. Answers are recorded evidence for the release cut's participant check.

## 7. Permitted feedback

After a first answer, the conductor may explain only what the participant explicitly finds unclear. The explanation must preserve every fact the page shows and add no claim the page does not support. It must not label the participant correct or incorrect. Record the assistant's words in the form.

## 8. Missing observations

If no participant is available, keep every task and form NOT RUN. Participant absence remains UNRESOLVED under the release cut. No form is fabricated and no browser assertion becomes a comprehension answer.

## 9. Related limits

Session evidence belongs to the builder and the controller. This guide changes no application behavior, starts no live service, and grants no provider, wallet or financial authority.