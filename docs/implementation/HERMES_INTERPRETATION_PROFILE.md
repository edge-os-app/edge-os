# Hermes interpretation profile (P05)

Status: local implementation candidate for P05 (issue 15). The saved Research path uses it when the setting `EDGE_OS_INTERPRETER=hermes_local` is on. The default is still the fixture interpreter. It does not approve a real model call, a provider key, hosting, spending, a wallet or a transaction.

Every result below comes from a **local fake provider**. The fake returns authored text. It shows that the adapter, the attempt history and the strict parser work around the real pinned Hermes runtime. It does not show how any real model reads a request.

## What exists

| Part | Path | Job |
|---|---|---|
| Adapter | `apps/api/src/edge_os_api/research/hermes_interpreter.py` | Builds one request, records the attempt, calls an injected runner, parses the answer whole |
| Strict parser | `apps/api/src/edge_os_api/research/interpretation_response.py` | Accepts one generated answer whole or rejects it whole |
| Attempt ledger | `apps/api/src/edge_os_api/research/interpretation_attempts.py` | Append-only attempt history and its rules |
| Attempt storage | `apps/api/src/edge_os_api/research/attempt_store.py`, migration `0006_interpretation_attempts.py` | Append-only PostgreSQL tables and the claim that proves who runs an attempt |
| Saved Research workflow | `apps/api/src/edge_os_api/research/interpretation_workflow.py` | Saves the request, runs the attempt, publishes the result, retries and recovers |
| Container job, runner and local API | `scripts/hermes_interpretation/` | Runs one actual Hermes turn in a no-network container against the fake provider; `serve_local.py` runs the API this way for verification |
| Tests | `apps/api/tests/test_hermes_interpreter.py`, `test_interpretation_response.py`, `test_interpretation_attempts.py`, `test_interpretation_attempt_store.py`, `test_hermes_research_flow.py`, `test_hermes_research_recovery.py`, `tests/hermes_interpretation/`, `tests/p03/interpreter*.spec.mjs` | Unit, PostgreSQL, HTTP, actual-Hermes and browser tests |
| Authored cases | `apps/api/tests/fixtures/hermes_interpretation/cases/` | 15 cases with literal expectations |

Web screens: `RequestPage`, `QuestionForm`, `Conversation` and `InterpretationAttempts` show the attempts, failures, words box and retry button. The verification map and recipe include a P05 phase.

## One interpretation, step by step

1. The route saves the request as written and commits. Nothing has called a model yet.
2. The adapter takes a claim for the new attempt: a PostgreSQL session lock on a dedicated idle connection. The claim comes before the attempt record, so nobody sees a recorded attempt that has no claim.
3. The adapter builds the task from the user's words, the restrictions, the job, the input class and the shapes of the fields the model may report. No owner ID, request ID or attempt ID is in it.
4. The ledger records the attempt **before** the call and commits. If that record cannot be written, no call is made. No database transaction is open during the call.
5. The injected runner runs one turn and returns text, usage, request count and what the runtime reported about itself.
6. The adapter checks the runtime settings, then the parser checks the text. The ledger records the result once. If that record cannot be written, the result is not used.
7. The workflow publishes an accepted result in one transaction: the revision, its outcome, a draft when the rules compile, and the link from the attempt to the revision.

The adapter makes **one attempt per call**. It never retries, repairs or replays. A retry is a new call that names the attempt it follows.

## The three results

| Result | Meaning | Examples |
|---|---|---|
| `Interpreted` | The answer was accepted whole | A rule read from the user's words; a hunch with questions; a clear idea marked UNSUPPORTED with its missing capability |
| `OutputRejected` | The model produced text that the application will not use | Two objects, a code fence, cut-off text, a quote that is not in the request, a number that the quote does not state |
| `Unavailable` | No usable answer, and not a verdict on the idea | Provider failure, timeout, unknown outcome, attempt or result not recorded |

An unsupported idea is `Interpreted` with `meaning_status: UNSUPPORTED`. A provider failure is `Unavailable`. A malformed answer is `OutputRejected`. These three are never mixed.

## Model response contract

The model returns one JSON object. All keys are required.

| Key | Allowed |
|---|---|
| `meaning_status` | `SUPPORTED` or `UNSUPPORTED` |
| `missing_capability` | `null` when supported; a non-empty name when unsupported |
| `evidence_readiness` | `READY` or `UNRESOLVED` |
| `field_evidence` | Items for the fields the model may report |
| `questions` | Questions about fields that are MISSING or CONFLICTING |

Each evidence item is one of:

- `KNOWN` + `USER_STATED`: needs `source_passage` (the user's exact words) and `value`.
- `KNOWN` + `AGENT_PROPOSED`: needs `adoption: PENDING` and `value`. The model can never adopt.
- `MISSING`: no other key.
- `CONFLICTING`: needs two or more `{value, source_passage}` alternatives from different words.

The application owns these fields. The model cannot report them: `restrictions`, `market`, `decision_interval_seconds`. The market binding stays the labelled synthetic fixture binding until a qualified market source exists. For a no-thesis investigation with no declared market, the application proposes that same labelled synthetic market as a pending item. The user adopts it with the usual "Adopt these settings" question. The model never asks for a market in words, because it cannot set that field. The interval is the one the compiler supports (300 seconds). Both wait for the user to adopt them.

The application derives `source_ref`, `origin` for its own items, `evidence_status` and `interpretation_revision`. The model sets none of them.

### Rejection codes (the whole answer is rejected)

| Code | Cause |
|---|---|
| `invalid_json`, `multiple_objects`, `trailing_content`, `not_an_object` | The text is not exactly one JSON object |
| `duplicate_key`, `invalid_number` | P02 strict rules: repeated key, JSON float, NaN |
| `unaccepted_field`, `missing_field`, `invalid_value` | Wrong shape |
| `reserved_field`, `unknown_field_name`, `duplicate_field` | Wrong field |
| `origin_not_allowed`, `proposal_must_stay_pending`, `adoption_not_allowed`, `source_passage_not_allowed`, `not_allowed_for_state` | The model claimed authority it does not have |
| `source_passage_not_in_request` | The quote is not an exact part of the request (or reply) |
| `ungrounded_number` | A stated number is not in its quote (`1%` must be `"0.01"`, not `"1"`) |
| `conflict_needs_two_alternatives`, `conflict_alternatives_not_distinct` | A conflict that is not two different statements |
| `missing_capability_required`, `missing_capability_not_allowed` | Status and capability disagree |
| `question_*`, `duplicate_question`, `reserved_question_id`, `duplicate_option`, `option_label_omits_value` | A bad question or option |
| `silent_overwrite`, `not_a_conflict` | A follow-up replaced or repeated stated meaning |
| `truncated` | The provider cut the answer short (even if the text parses) |
| `runtime_policy_violation` | The runtime ran outside the approved settings |

### What "grounded" means here

A quote must be an exact substring (no normalization, no empty quote). A number counts as stated when the quote contains it as a digit, as a small number word, with `%` or `percent` (scaled by 100) or with `bps` (scaled by 10,000). A number followed by `%` states only its scaled form. Zero is always allowed. Checked quantities are comparison constants, sizing amounts, fee and slippage rates, and notional limits.

A negative number counts as stated only when the words show its sign: `-2%`, `−2%`, `minus 2%` or `negative 2 percent` state `-0.02`. A sign that the words do not show leaves a negative value ungrounded, and a dash inside a word (`15-minute`) is never a sign. An option label that carries a negative value must show the sign the same way. The prompt says so. This is a mechanical check. It does not prove that the whole value means what the user meant. It does not check lookback counts, time spans or operators. The compiler checks those later.

## Follow-up replies

A reply may be free text. The model lists **only the fields the reply changes or adds**. The application carries every other field forward word for word.

| Earlier state | A reply may |
|---|---|
| Missing | Fill it (quoting the reply), propose it, leave it, or conflict it |
| Stated, chosen or adopted | Restate it (nothing changes) or report a **conflict** (the application keeps the earlier value as one alternative). It may not replace or retract it |
| Pending proposal | Replace it with the user's own words |
| Conflicting | Settle it with the user's own words, or stay conflicting |

Choosing an offered option and adopting the pending settings are deterministic. They call no model.

## Attempt history

Two append-only rows per attempt: a start (before the call) and a settlement (after).

- Start: owner, request, sequence, `retry_of`, purpose, prompt version, system-prompt hash, the **exact task text** and its hash (the ledger refuses a hash that does not match the text), response-shape hash, P02 manifest hash, configuration and its hash, runtime label, and for a follow-up the `answer_ref` of the user's reply. P02's `Clarification` record keeps only a reference string, so the task text in the start row is where a free-text reply is kept.
- Settlement: status, finish time, measured latency, usage, provider request count, response hash and exact text, parse result, error class, what the runtime reported about itself.

| Status | Completion |
|---|---|
| `COMPLETED` | `COMPLETE` |
| `TRUNCATED` | `TRUNCATED` |
| `PROVIDER_FAILED` | `NONE` |
| `TIMED_OUT`, `INTERRUPTED`, `UNKNOWN` | `UNKNOWN` |

Rules the ledger enforces: sequence numbers rise by one; a retry names an earlier attempt of the same owner and request; only one attempt may be open per request; an attempt settles once; hashes must match the saved text; usage is either reported with input and output counts or unknown; a truncated response is never accepted; an attempt links to one revision, and only if it completed and was accepted.

**Unknown stays unknown.** Usage that the provider did not report is stored as empty, never as zero. A restart closes an unsettled attempt as `INTERRUPTED` with unknown usage only when nobody holds its claim. A held claim means the attempt may still run, so it stays open. Nothing is replayed. An accepted result that no revision uses yet can be recovered by parsing the saved text again. That makes no model call.

A late result for an `UNKNOWN` or `INTERRUPTED` attempt is **not** settled by this code. That needs a separate reconciliation record and a decision.

## Runtime policy

The adapter accepts an answer only when the runtime reports all of these: no tools, no fallback provider, memory off, streaming off, exactly one provider request, the exact system prompt inside the request, and the exact task as a user message. A runtime that does not report a field fails the check.

Findings from the actual runs:

- **Hermes wraps the system prompt.** The pinned Hermes puts its own identity text before our prompt and host, profile, path and date lines after it. The wire request therefore differs from the prompt we hash. The runner records the hash of the real outgoing system message and the real request. Those include per-job paths and a date, so they differ between runs.
- **Hermes skips token accounting when an answer is cut short.** In both truncation cases Hermes counted no usage, though the provider sent it. The container job therefore reads `usage` from each provider response body at the HTTP boundary. The same hook works for a live client.
- **Hermes tries to continue a cut-off answer.** It sent a second, larger request. The local guard refused it and recorded it. A live route needs an equivalent hard limit on physical requests.
- **A failed call is not counted by Hermes.** A 503 leaves Hermes' API-call counter at zero.

## Saved Research path

| Situation | What is saved | What the user sees |
|---|---|---|
| Answer accepted | A revision, its outcome, a draft when it compiles, and the attempt link | Questions, or rules to review |
| Unsupported capability named by the model | An `UNSUPPORTED` outcome with the capability | Not supported yet. Not a failure |
| Malformed or truncated output, or a policy violation | A first interpretation gets an `INVALID_INPUT` outcome with finding `malformed_model_output`. A reply saves no outcome. The attempt keeps its reason code | The interpreter's answer was not usable. Retry offered |
| Provider failure | Finding `interpreter_unavailable`, usage unknown | The interpreter did not answer. Retry offered |
| Timeout, crash or unknown outcome | Finding `interpreter_outcome_unknown`, status `TIMED_OUT`, `UNKNOWN` or `INTERRUPTED` | We do not know if it finished. No retry is offered |

The outcome codes reuse the P02 outcome envelope. P05 adds no record type and no schema version. A failed reply keeps the saved meaning and its questions, so the page shows the failure from the attempt list and does not hide the questions behind a new outcome.

**Routes.** `POST /v1/research/requests/{id}/clarifications` takes either a listed `choice_id` (no model call) or the user's `answer_text` (one follow-up attempt). `POST /v1/research/requests/{id}/interpretation-retries` takes `retry_of`, the earlier attempt it follows. A retry is allowed after a provider failure, a cut-off answer or a rejected answer. It is refused while an attempt runs, after an unknown outcome, after a reply went stale, and when nothing is waiting. Another owner gets 404 for every route.

**Tables.** `interpretation_attempts` (exact task text, reply text and hashes, configuration, runtime label, the revision a reply answers), `interpretation_settlements` (status, latency, usage or NULL, request count, response hash and text, parse result, runtime report), `interpretation_attempt_links` (one accepted attempt to one revision, with the questions the answer offered) and `interpretation_late_results`. All four reject UPDATE and DELETE. Foreign keys include the owner. Database checks recompute every hash from the saved text. The public view holds structured values, hashes and sanitized codes. It never holds the generated text.

**Concurrency.** A second attempt for one request is refused while one is open. The unique place (owner, request, sequence) separates simultaneous callers. A process start or restart closes an attempt only when nobody holds its claim. A held claim means the attempt may still run, so it stays open and duplicate work is refused. A crashed worker loses its connection and so its claim.

**Recovery.** Startup recovery, a retry and an answer all run the same three steps first: close attempts that are proved abandoned; publish saved accepted results by parsing their stored text again; save the failure outcome of a first reading that settled as a failure but crashed before its outcome was written (provider failure, rejected output, or an unknown outcome, including an attempt closed as interrupted). None of them makes a model call. Each is safe to repeat: the publication and its link commit together, and the outcome is written only when none exists for that attempt. A saved result is left unpublished when the saved meaning moved on. A failed outcome repair is logged by class name and never blocks an answer or a retry.

**Capacity.** Each running attempt holds one dedicated database connection for its whole provider call. The pool allows 20 connections, so about ten simultaneous attempts leave little room for ordinary reads. When the pool is full the start record or the claim fails, no model is called, and the user gets a 503. This was not load tested.

**Stuck results.** A saved accepted result that cannot be published (a persistent defect, or a parser change after it was saved) is retried on every recovery pass and logged by class name. Other requests are not blocked. The page shows it as "Your request was read, and the answer is not saved yet". It offers no retry. The profile does not yet offer a way out.

**A first request whose latest attempt has no saved outcome.** The outcome is a separate commit after the attempt settles, so a crash or a storage error can leave the latest attempt without one. After a retry the page matches an outcome to an attempt by the outcome's operation ID, which is the attempt ID. An older attempt's outcome never describes a newer attempt. A plain page load does not repair it (it writes nothing). The page words the state from the stored attempt and never from the missing outcome. It never says "Could not be interpreted" for these:

**The saved-requests list uses the same rule.** With the Hermes interpreter each list row carries the stored facts about the request's latest attempt (`reading`: whether an interpretation exists, whether an outcome exists, the latest attempt's status and parse result, whether an outcome was written for that attempt, whether a retry is allowed) and the first finding code of the latest outcome (`outcome_code`). One function (`readingOf`) turns those facts into the page state and the card tag. A card never shows "Could not be interpreted" for a Hermes state. It shows "Saved, not read yet", "Attempt not finished", "Read, not saved yet", "Interpreter did not answer", "Answer not usable" or "Outcome unknown". With the fixture interpreter a row has no `reading`, and "Could not be interpreted" keeps its old meaning there: unscripted text.

**`head.outcome` is the latest saved outcome, not necessarily the latest attempt's.** After a retry it can belong to an earlier attempt. A client must match an outcome to an attempt by the outcome's `operation_id`, which is the attempt ID, as the page does.

| Stored facts | Heading | Action offered |
|---|---|---|
| No attempt | Saved, not read yet | "Read my request now" starts one attempt |
| Attempt with no settlement (the attempt list says "Started, no result saved", never "Running") | An interpreter attempt has not finished. It may be running or stopped; the page cannot tell | "Check the saved request again" (reads only) |
| Accepted answer, no revision | Your request was read, and the answer is not saved yet | "Check the saved request again" |
| Provider failure | The interpreter did not answer | "Try the interpreter again" when the server allows it |
| Rejected or cut-off answer | The interpreter's answer was not usable, with its reason | "Try the interpreter again" when the server allows it |
| Timed out, unknown or interrupted | We do not know if the interpreter finished, with the blocked-retry reason | "Check the saved request again". No retry |

The same page rules for a reply: `REJECTED`, `UNCERTAIN`, `FAILED` and `PENDING_SAVE` (an accepted reply that is not saved yet is shown as read, never as a failure). Browser checks at 1280px and 390px cover the four first-reading states that have an attempt, a failed-then-unknown retry, a saved-requests list whose latest attempt was accepted but not saved (the list response is rewritten), and the default no-thesis request with no declared market through adoption. They produce each state by rewriting the one GET response of a real saved request, then read the page text that the real component draws. They prove the page logic. They do not prove what the API returns in those states; the PostgreSQL recovery tests do that.

**Hostile model output.** Model text is an untrusted claim. A parser that meets a value it cannot handle (a field name that is not text, a non-finite decimal such as `sNaN`, a value nested thousands of levels deep) answers with a rejection (`invalid_value`, `ungrounded_number` or `unparseable_response`) and never raises. Text that PostgreSQL cannot store (a NUL character, a lone surrogate) is kept in an escaped copy, hashed as saved, and rejected as `unstorable_text`. In every case the attempt settles with its measured usage and the user may retry. The adapter also settles the attempt if a parser raises for any other reason.

**Fields the fixture defaulted.** The fixture interpreter proposed sizing, additions, exit and the other strategy defaults itself. On the Hermes path the model proposes them. If it leaves one out, the user answers a text question for that field. This costs one model call per answer and depends on the model. How a real model behaves here is unqualified.

**What the database does not enforce.** The application guards these, as it does for other rules in this repository: the late-result `status` has no value list; a link's revision is not tied by a database rule to the same request or to a `PromptInterpretation`; `runtime_label` allows `LIVE` (the settings refuse the interpreter in production, and no code builds a live release); `records` has no unique key on owner and operation ID. A second outcome for one attempt is prevented by the request row lock plus a check that no outcome exists for that attempt.

**Late results.** A result that arrives after its attempt was closed as unknown is saved as evidence beside it. It never replaces the settlement, becomes a revision, or starts a retry. Nothing in this build delivers one except the adapter itself, when a worker finishes after another process closed its attempt.

**Decisions kept.** The market binding stays the labelled synthetic fixture binding, pending adoption (D1). Unavailability is a saved system outcome with an explicit retry (D2). The exact task and reply text are kept (D3). Attempt storage is application storage (D4). The public bundle never carries generated text (D5). Uncertain records stay unchanged (D6). The fixture interpreter is the default, and no setting reaches a real provider (D7).

## Local evidence

All of it uses the pinned commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba` (`uv.lock` SHA-256 `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01`) in `python:3.14-slim-trixie` with no network, a read-only root, one read-only input file and one output directory.

- 15 authored cases and 11 multi-step flows ran through actual Hermes: concrete thesis, paraphrase, rough hunch, bounded no-thesis, unsupported extension, follow-up, changed meaning, conflicting reply, restatement, malformed, truncated, ungrounded number, rewritten quote, self-adoption, 503, hang, missing usage, retry, restart, foreign owner, wire isolation, recovery.
- Six more HTTP-level flows ran through actual Hermes over authenticated routes and PostgreSQL (`test_pinned_hermes_http.py`).
- Parser, ledger and adapter have unit tests. The attempt tables, the routes, crash recovery, a second process, a dead worker, late results and simultaneous requests have PostgreSQL tests.
- The mapped browser path drives failure, retry, free-text replies, conflict, rejection, unsupported meaning and foreign-owner denial at 1280px and 390px, then restarts and reopens.
- Two mutation sweeps change rules in a throwaway copy. The first covers the parser, ledger and adapter. The second changes 16 rules in the ledger, claim, workflow and fixture-question code. It does not cover claim release on an error path, the failure-outcome repeat guard, ownership checks or the migration constraints.
- No real provider socket, key or account was used.

## What is not proven

- How any real model reads these requests. Quality, cost per request and latency of a real provider are unmeasured.
- Production tenancy, hosting, a provider spending cap, provider-side cancellation, billing.
- That a user understands a question or a proposal. No person used the screens.
- Safari, Firefox, a phone and a screen reader. Only Chromium at 1280px and 390px, axe and a keyboard path ran.
- An unknown outcome has no way forward in this build: no retry is offered. A reconciliation record and a decision are needed first.

## Run it

From the repository root. The pinned Hermes checkout must exist at `/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent`. The full mapped path, with its P05 phase, is in `.agents/skills/verify-edge-os/SKILL.md`.

```sh
cd apps/api && uv sync --frozen
uv run --frozen pytest tests/test_interpretation_response.py tests/test_interpretation_attempts.py tests/test_hermes_interpreter.py tests/test_interpretation_attempt_store.py tests/test_hermes_research_flow.py tests/test_hermes_research_recovery.py
P05_EVIDENCE_DIR=<private folder> uv run --frozen pytest ../../tests/hermes_interpretation   # needs Docker and network for the image build
```

The container tests build one image from the locked Hermes source and remove exactly that image at the end. Each test container carries the label `edge-os.test.run=<run id>` and is removed by exact name.
