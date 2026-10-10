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
| Fixture sign-in | Existing `tests/p03/fixture-auth.mjs` owner tokens, same as the mapped path |
| Surfaces | Research home, a saved request with an exact rule, a saved P08 declaration, a saved P09 report, a saved P13 replay, Agents/Positions/Funds account views |
| Device | Desktop 1280px and a 390px viewport as available; a physical phone when available |
| Environment | Local repository run by the controller or builder; no live provider, wallet or network |
| Timing | Target five observations where participants are available; preserve actual numbers |

Each participant session must name the exact revision it ran. A notebook or the observation form in section 6 records the session.

## 3. Participant-facing tasks

Present each task as written here. Do not add synonyms, definitions or hints before the first answer. Let the participant say "I cannot tell" freely.

### Task T1: Understand a saved research result

Open the Research home, then open one saved request whose outcome is UNRESOLVED.

Question: "This page holds a saved research item. What does it tell you about the trading idea, and what would you want to do next? You can say you cannot tell."

### Task T2: Read the exact rule

Open the same request and show its compiled rule review.

Question: "This rule will be saved exactly as written. What does the rule say, and what numbers would it act on? You can say you cannot tell."

### Task T3: Tell evidence from permission

From Research, open Agents and then Funds.

Question: "Without doing anything, what does this page let you see, and what does it not let you or the agent do yet? You can say you cannot tell."

### Task T4: Understand saved records after reopen

Open a saved P09 report, then a saved P13 replay, and let the participant reopen one.

Question: "This record was saved earlier. What happens when you reopen it, and what does the page say did not run again? You can say you cannot tell."

### Task T5: Distinguish pending from confirmed

From Positions and Funds, show one pending or unknown action beside a confirmed one.

Question: "Show me which item is finished and which one is still waiting, and what that means for the tokens held. You can say you cannot tell."

## 4. Expected answers for the controller

This section is for the builder and controller only. It must not reach the participant before the corresponding first answer. It states what the interface is documented to show, per the accepted sources, so the conductor can judge a first answer without coaching.

### T1 expected

The saved request shows an outcome, a no-thesis or investigation state, and its saved identity. Unsupported or unscripted requests keep their restriction text and show "Not supported yet" or "Could not be interpreted" as a system message, not a verdict on the idea. The page grants no permission. Sources: RequestPage behavior and `tests/p03/e2e.spec.mjs` unsupported and unscripted tests.

### T2 expected

The rule review renders the exact compiled rule with its thresholds and groupings, the immutable content hash, and provenance rows for the exact values. The saved revision reopens with the same text after restart. Sources: RulesReview, `tests/p03/provenance.spec.mjs`, `tests/p03/reopen.spec.mjs`, `docs/implementation/P06_COMPILER_PROFILE.md`.

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