# Real-model qualification proposal for prompt `p05-interpretation/4`

Status: PROPOSED. Label: NOT_RUN. This file is not authority and not a budget. It makes no live request and reads no credential. A controller release must name the provider, model, budget, credential route and egress policy first. See `LIVE_RELEASE_CHECKLIST.md`.

It replaces the frozen `REAL_MODEL_PLAN.md` for the current prompt. That file stays unchanged. Its prompt identities are stale.

## 1. What this proposal will and will not show

| Claim | Evidence so far | Status |
|---|---|---|
| A real model keeps the user's meaning | None. Controlled answers only. | NOT_RUN |
| Latency and usage of a real model | None | NOT_RUN |
| The guard, the spend ledger and the saved path hold | Local tests with controlled responses (section 9) | Shown locally |
| A production host can run it safely | Documents only | NOT_RUN |

A controlled answer is a hand-written file. It is not model output. Parser success is not a meaning pass.

## 2. Pinned identities

All values are in `IDENTITIES.json`. A test recomputes them from the code.

| Identity | Value |
|---|---|
| Base commit | `3ab45e7240910433f4bdcd84eae86833dd9f406c` |
| Candidate | The commit that holds this file. The worker result names it after the commit exists. |
| Prompt version | `p05-interpretation/4` |
| System prompt SHA-256 (3,749 characters) | `ea2ae47f810b287b7ad93cd31d7e3e1f0068c4ea4cdc8fe79d8df68fea1ae460` |
| Response shape SHA-256 | `e2b561f4f4ce50b85fe18e148174e8db891b5987f9589f444ad12883dd1fe280` |
| P02 manifest SHA-256 | `e80a9918e14321716f9ce231ada91dc788275b95f0142830d2a7ec4c6f74aff7` |
| Hermes commit | `54bc5e509c985f37265c3d416bd2c64b10fc77ba` |
| Hermes `uv.lock` SHA-256 | `de17d70bc999fb0f8fe50dbf8590ac979f43b5a84cd8320caeac1c695ce63c01` |
| Case manifest SHA-256 | see `IDENTITIES.json` field `case_manifest_sha256` and the value below |
| Guard, ledger, job and runner files | SHA-256 values in `IDENTITIES.json` field `support_files_sha256` |

Case manifest SHA-256: 34a8c4986c321e5b06cda6959219c46de211f58b6b68374641e0a70cd867f666

Each case has a task hash, a text hash and a logical request size in `IDENTITIES.json`. The wire request differs from the logical request. Hermes wraps the system prompt and adds a runtime note that holds a path. So the guard checks structure, not one fixed hash. It checks that the system message holds the prompt verbatim, that the user message equals the task verbatim, that the envelope is small, and that no other field is present.

## 3. Proposed route (pending decisions)

| Item | Proposal | Status |
|---|---|---|
| Gateway | OpenRouter, `https://openrouter.ai/api/v1` | Pending controller decision |
| Model | `openai/gpt-6.1-sol` | Pending. Probe A ran a different prompt on it. That pass does not carry over. |
| Routing | `provider`: `allow_fallbacks: false`, `require_parameters: true`, `data_collection: "deny"`, `max_price` | Pending. Fields exist in the public routing guide (section 4). |
| Reasoning level | low | Pending. Not a recorded decision. |
| Output limit | `max_tokens = 4096`, including reasoning | Pending. Matches the adapter default. |
| Structured output | none. Prompt plus strict parser | As implemented. |
| Hermes settings | no tools, no memory, no context files, no fallback, streaming off, compression off, `api_max_retries=1`, SDK `max_retries=0` | As the container job reports. |
| Credential | None obtained | Secure route and provider-side ceiling need checking at release |

The builder named existing OpenRouter credentials, with tx-odds-hack as a possible location. This task did not read, copy, validate or query them.

## 4. Public documentation checked

Source: Context7 library `/openrouterteam/docs` (OpenRouter public documentation), queried 2026-10-11. This is public documentation access. It is not account access.

- The `provider` object accepts `allow_fallbacks`, `require_parameters`, `data_collection` and `max_price` (a ceiling per million tokens for prompt and completion).
- A key can carry a credit limit. A request on a key at its limit fails with 403. The limit is set through a management key (`PATCH /api/v1/keys/{hash}`). Reading `GET /api/v1/key` shows `limit` and `limit_remaining`. Neither call was made.
- A response carries a `usage` object with token counts and a `cost` field.
- The streaming guide says an aborted stream stops processing and billing on supported providers. It makes no such statement for a non-streaming request. So a killed client may leave a charge.
- Not checked and not claimed: current prices, model availability, rate limits, whether `max_price` rejects or reroutes in every case.

## 5. Request ceilings

| Limit | Value | Basis |
|---|---|---|
| Physical requests per attempt | 1 | Guard refuses every later request |
| Output tokens | 4,096 | Adapter default; guard refuses any other `max_tokens` |
| Request bytes, first reading | 8,448 | Largest controlled wire request 7,754 bytes |
| Request bytes, follow-up | 10,240 | Largest controlled wire request 9,510 bytes |
| System envelope | 2,500 characters over the prompt | Controlled runs stayed under it |
| Job timeout | A runner parameter. The tests use 60 or 90 seconds. The proposal asks for 60 | One absolute deadline covers the job wait plus a 5-second grace. Stopping the container (every docker command, the wait for the client, every pause) and sealing the evidence all draw on what is left. No command starts after the budget is spent, and none is longer than the time left. A turn that cannot stop its container or seal its evidence in time removes the evidence, or moves what it cannot remove in time to a private quarantine folder, and raises `EvidenceNotSealed` |
| Tools, streaming, fallback models | none | Guard refuses the fields |

Input tokens are bounded by request bytes plus 64, because a token covers at least one byte of text. This is an assumption about tokenizers, not a proven ceiling for the chosen model. A bytes/4 estimate is not a ceiling and the ledger does not use it. Probe A's 3,000 input-token bound is not used.

## 6. Spend arithmetic

Prices below are STALE. They are Probe A's last recorded ceilings (prompt USD 2.00, completion USD 7.50 per million tokens). Read the provider's public price list at release and recompute. Do not treat them as current.

| Quantity | Value (stale prices) |
|---|---|
| Worst case, first reading | USD 0.047744 |
| Worst case, follow-up | USD 0.051328 |
| Base batch, 8 first readings and 3 follow-ups | USD 0.535936 |
| With 4 retry slots at the follow-up rate | USD 0.741248 |
| Proposed cumulative cap | USD 0.75, pending controller decision |

The local ledger holds the full reservation for any attempt with unknown usage, unknown outcome or a failed settlement. Known cost plus unknown reservations plus the next reservation must stay within the cap. The cap is a local limit. It does not cap the provider's billing. A provider-side limit needs a dedicated key or prepaid balance that a person sets. Without it, close the real-provider part as UNRESOLVED or accept best-effort local accounting in a recorded decision.

Historical allowances (USD 0.60, USD 2, Probe A) give no current authority.

## 7. Cases and pass conditions

`CASE_MANIFEST.json` holds 11 cases in the five groups. Seven request texts are new. Four also appear in earlier local fixtures (`g1-concrete`, `g2-hunch`, `g3-no-thesis`, `g4-unsupported`). All expected values come from the user's own words.

| Group | Cases | Requests |
|---|---|---|
| Concrete thesis | `g1-concrete`, `g1-paraphrase` | 2 |
| Rough hunch | `g2-hunch`, `g2-conflict` | 2 |
| Bounded no-thesis | `g3-no-thesis`, `g3-no-market` | 2 |
| Unsupported extension | `g4-unsupported`, `g4-mixed` | 2 |
| Follow-up | `g5-fill`, `g5-overwrite-tempt`, `g5-restatement` (replies to the saved `g2-hunch` answer) | 3 |

Base batch: 11 requests. The follow-ups reuse one saved `g2-hunch` answer, so they add no first-turn call. Retry slots: none automatic. The controller may release at most one explicit retry per case, up to 4.

A case passes on meaning when `meaning_check.py` returns no failure. It compares the raw answer with literal expected values and with quotations from the user's own words. It uses no model and no similarity score. Format, meaning, latency and usage are reported as four separate results. Format reliability is a count: accepted, rejected by reason, truncated, unavailable. No quality score is invented.

Known interaction. For `g5-restatement` the prompt tells the model to list nothing. The application rejects an answer that changes no field (`reply_changed_nothing`). The saved meaning stays as it was. The manifest records this as the expected application outcome. It is not a model fault.

## 8. Stop rules (frozen)

Stop the whole batch, with no further request, on the first of:

1. a refused extra request;
2. a truncated answer;
3. unknown usage;
4. a request that differs from the configured request, or an unexpected field;
5. any provider error other than a clean pass or a clean rejection;
6. an unreadable or unsettled ledger;
7. reaching the cumulative cap;
8. the whole-process deadline.

Report to the controller. Do not retry without a recorded release. A kill does not prove that the provider stopped or that nothing was charged.

## 9. What the local tests show

All with controlled responses. No provider, key or network.

- The guard refuses wrong model, wrong output limit, extra fields, changed task, changed prompt, large envelope, large request, wrong credential and every second physical request. A refused request never reaches the transport.
- Actual pinned Hermes in a no-network container: a cut-off answer makes Hermes ask for a continuation. The guard refuses it before the fake provider sees it. The known larger-continuation request (`max_tokens` 8,192) is covered by the same refusal.
- The ledger reserves before the request, charges exact decimal cost, keeps unknown liability, blocks a retry in the same scope, survives a kill and a reopen, and records late evidence once.
- The saved Research path records a refused attempt with request count 0, and no boundary call, when the cap is gone.
- A dummy credential does not appear in logs, saved attempts, evidence files or the ledger.
- All 11 manifest cases run through pinned Hermes with controlled faithful answers, and the meaning checker passes them. Three of those runs (`g2-conflict`, `g3-no-market`, `g4-mixed`) reuse the answer of a sibling case, so the checker's conflict path is proved by unit tests only. The checker fails answers that parse but change the meaning, such as a reversed direction.

Not shown: any real model behavior, real cost or latency, or an upstream billing ceiling.

## 9a. Known gaps in the local safeguards

- The ledger has no operator path to resolve an UNKNOWN reservation except late usage evidence. A planned "one explicit retry per case" therefore has no mechanism after an UNKNOWN attempt. A later change must add a recorded decision path.
- The ledger uses one flat price per token kind. The provider may charge more for tiers or cache. Recompute from the provider's documents at release.
- If a delegate reports two requests, the runner keeps one reservation as liability. The guard prevents the second request. A host-level count is still needed.
- Credential redaction and the leak scan cover the plain secret and its upper and lower case, URL-encoded, reversed, hex, base64 (aligned and offset), Authorization header and JSON `\u` escape forms, in file contents and file names. A secret that is split, compressed or encrypted is not covered. Evidence that cannot be scanned (over 64 MiB) is deleted, and a folder that cannot be cleared stops the turn with `EvidenceNotSealed`. Each turn captures its number, policy and credential value once, at its start. The job reads a private copy of the credential, so a later change to the source file cannot change what the host seals. Named pipes, sockets, devices and links in the evidence are removed and never opened. On every path out of a turn, including an unexpected exception or an interrupt, the host stops the turn's own container and verifies it is gone, then seals the evidence. If either step fails for any reason, the evidence folder is removed and the turn raises `EvidenceNotSealed`. A credential file that is missing, unreadable or empty stops the turn before any job starts.
- A credential file that is missing, unreadable or empty ends the turn with `CredentialUnavailable` before any job starts. The guarded runner still keeps the full reservation, as it does for any exception from the process boundary, so a misconfiguration uses up cap with no spend until a person reconciles it.
- The private copy of the credential sits in a temporary folder and is deleted when the turn ends. A hard kill of the host process can leave it behind.
- The host does not trust the client's exit code: after every client exit it verifies that the container is gone, and stops it if it is not, before any evidence is touched. A stop that runs while Docker is still creating the container can miss it, so absence has to show twice in a row. The stop step keeps the last tenth of the grace (at most half a second) for removing the evidence. Removal has the rest of the budget, and at least 0.1 seconds. If an output is too large to remove in that time, the rest is moved in one step to a private `quarantine-*` folder, the turn raises `EvidenceNotSealed` and says so, and `purge_quarantine()` removes those folders between turns. A quarantine folder holds unsealed evidence: it is private (mode 700) but it is on disk until it is purged. Every step of the removal ticks the clock, including the removal of an empty folder. Sealing and removal both work on directory descriptors and never open a link; a file is opened without following links and without blocking, and anything that is not a plain file is removed unread. Removal so a folder that a container still running swaps for a link while the removal works is unlinked as a link and nothing outside the output is touched. A tree deeper than the process may hold descriptors for is moved, not removed. If the plain walk fails for any reason, such as a path longer than the host limit, the output is moved, never removed without a clock. `purge_quarantine()` has no clock and raises if a folder is left.
- An output with more than 10,000 entries is removed without being scanned, and a file over 64 MiB is deleted. The authored provider script `input.json` is not sealed.
- The host collects the job's stdout in memory with no size limit. A job that prints without end could use the host's memory until the job timeout.
- The guard allows up to 2,500 characters of text around the prompt in the system message and does not check what that text says. The gate accepted this as a documented design. Stronger pinning of the envelope needs a separate decision.
- Sealing a single file of up to 64 MiB reads and writes it whole, which takes about 0.1 seconds. That file operation is outside the clock check, which runs between entries.
- The SDK-retry refusal is proved at guard level only. This Hermes build sent no second request after a 503.

## 10. Evidence to keep per attempt

The wire body hash and size, the exact response text and hash, the attempt rows, measured latency, reported usage, the provider request count, the guard log, the ledger events, the container lifecycle record, and the meaning result. Keep controlled, real-provider and participant evidence in separate folders with separate labels.

## 11. Decisions still open

1. Provider, model, route and reasoning level.
2. The provider-side spending ceiling, or an explicit acceptance of local accounting only.
3. The cumulative cap and the retry slots.
4. The egress policy for a live job.
5. The credential route and who injects it.
6. Whether the live job is a separate ticket with its own reviews.
7. Real-model thresholds for the 20,000-byte answer bound and the 64-character identifier rule.
