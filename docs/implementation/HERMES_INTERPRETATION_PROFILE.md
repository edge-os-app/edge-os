# Hermes interpretation profile (P05)

Status: local implementation candidate for P05 (issue 15). It is not wired into the saved Research path yet. It does not approve a real model call, a provider key, hosting, spending, a wallet or a transaction.

Every result below comes from a **local fake provider**. The fake returns authored text. It shows that the adapter, the attempt history and the strict parser work around the real pinned Hermes runtime. It does not show how any real model reads a request.

## What exists

| Part | Path | Job |
|---|---|---|
| Adapter | `apps/api/src/edge_os_api/hermes_interpreter.py` | Builds one request, records the attempt, calls an injected runner, parses the answer whole |
| Strict parser | `apps/api/src/edge_os_api/interpretation_response.py` | Accepts one generated answer whole or rejects it whole |
| Attempt ledger | `apps/api/src/edge_os_api/interpretation_attempts.py` | Append-only attempt history and its rules |
| Container job and runner | `scripts/hermes_interpretation/` | Runs one actual Hermes turn in a no-network container against the fake provider |
| Tests | `apps/api/tests/test_hermes_interpreter.py`, `test_interpretation_response.py`, `test_interpretation_attempts.py`, `tests/hermes_interpretation/` | Unit and real-Hermes tests |
| Authored cases | `apps/api/tests/fixtures/hermes_interpretation/cases/` | 15 cases with literal expectations |

Not done yet, because these are shared paths: service and router calls, settings, schemas, the attempt table and its migration, the web screens, and the verification map. See the shared-wiring request.

## One interpretation, step by step

1. The caller passes the saved intake. The adapter builds the task from the user's words, the restrictions, the job, the input class and the shapes of the fields the model may report. No owner ID, request ID or attempt ID is in it.
2. The ledger records the attempt **before** the call. If that record cannot be written, no call is made.
3. The injected runner runs one turn and returns text, usage, request count and what the runtime reported about itself.
4. The adapter checks the runtime settings, then the parser checks the text.
5. The ledger records the result once. If that record cannot be written, the result is not used.
6. The caller gets one of three results: `Interpreted`, `OutputRejected` or `Unavailable`.

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

The application owns these fields. The model cannot report them: `restrictions`, `market`, `decision_interval_seconds`. The market binding stays the labelled synthetic fixture binding until a qualified market source exists. The interval is the one the compiler supports (300 seconds). Both wait for the user to adopt them.

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

This is a mechanical check. It does not prove that the whole value means what the user meant. It does not check lookback counts, time spans or operators. The compiler checks those later.

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

**Unknown stays unknown.** Usage that the provider did not report is stored as empty, never as zero. A restart closes every unsettled attempt as `INTERRUPTED` with unknown usage. Nothing is replayed. An accepted result that no revision uses yet can be recovered by parsing the saved text again. That makes no model call.

A late result for an `UNKNOWN` or `INTERRUPTED` attempt is **not** settled by this code. That needs a separate reconciliation record and a decision.

## Runtime policy

The adapter accepts an answer only when the runtime reports all of these: no tools, no fallback provider, memory off, streaming off, exactly one provider request, the exact system prompt inside the request, and the exact task as a user message. A runtime that does not report a field fails the check.

Findings from the actual runs:

- **Hermes wraps the system prompt.** The pinned Hermes puts its own identity text before our prompt and host, profile, path and date lines after it. The wire request therefore differs from the prompt we hash. The runner records the hash of the real outgoing system message and the real request. Those include per-job paths and a date, so they differ between runs.
- **Hermes skips token accounting when an answer is cut short.** In both truncation cases Hermes counted no usage, though the provider sent it. The container job therefore reads `usage` from each provider response body at the HTTP boundary. The same hook works for a live client.
- **Hermes tries to continue a cut-off answer.** It sent a second, larger request. The local guard refused it and recorded it. A live route needs an equivalent hard limit on physical requests.
- **A failed call is not counted by Hermes.** A 503 leaves Hermes' API-call counter at zero.

## Local evidence

All of it uses the pinned commit `54bc5e509c985f37265c3d416bd2c64b10fc77ba` (`uv.lock` SHA-256 `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01`) in `python:3.14-slim-trixie` with no network, a read-only root, one read-only input file and one output directory.

- 15 authored cases and 11 multi-step flows ran through actual Hermes: concrete thesis, paraphrase, rough hunch, bounded no-thesis, unsupported extension, follow-up, changed meaning, conflicting reply, restatement, malformed, truncated, ungrounded number, rewritten quote, self-adoption, 503, hang, missing usage, retry, restart, foreign owner, wire isolation, recovery.
- Parser, ledger and adapter have unit tests.
- A mutation sweep changes 32 rules in a throwaway copy; every change is caught.
- No real provider socket, key or account was used.

## What is not proven

- How any real model reads these requests. Quality, cost per request and latency of a real provider are unmeasured.
- Production tenancy, hosting, a provider spending cap, provider-side cancellation, billing.
- The authenticated HTTP path, the PostgreSQL attempt table, restart and reopen of saved attempts, and the screens. Those need the shared wiring.
- That a user understands a question or a proposal.

## Run it

From the repository root. The pinned Hermes checkout must exist at `/Users/degencodebeast/Projects/personal/monad-hack/.tools/hermes-agent`.

```sh
cd apps/api && uv sync --frozen
uv run --frozen pytest tests/test_interpretation_response.py tests/test_interpretation_attempts.py tests/test_hermes_interpreter.py
P05_EVIDENCE_DIR=<private folder> uv run --frozen pytest ../../tests/hermes_interpretation   # needs Docker and network for the image build
```

The container tests build one image from the locked Hermes source and remove exactly that image at the end. Each test container carries the label `edge-os.test.run=<run id>` and is removed by exact name.
