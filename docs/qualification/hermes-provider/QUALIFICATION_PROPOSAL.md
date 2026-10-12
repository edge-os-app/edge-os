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
| Job timeout | A runner parameter. The tests use 60 or 90 seconds. The proposal asks for 60 | One absolute deadline, counted from the moment the turn is planned, covers everything: the setup before the launch and the job wait come out of the job timeout, and a 5-second grace follows. If setup uses the whole job timeout, no job is started and the turn reports that nothing was sent. Stopping the container (every docker command, the wait for the client, every pause) and sealing the evidence all draw on what is left. No command starts after the budget is spent, and none is longer than the time left. A turn that cannot stop its container or seal its evidence in time removes the evidence, or moves what it cannot remove in time to a private quarantine folder, and raises `EvidenceNotSealed` |
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

### 9b. Deadlines and supervised recovery (accepted cleanup rule, 2026-10-12)

The builder-approved rule `docs/planning/P05_PROVIDER_DEADLINE_AND_CLEANUP_RULE_2026-10-12.md` (in the controller workspace; sha256 `cf7c6058480686253861ea4dfe33e09e00410025dd8fdd66e9942c6fd74300d2`) replaces the literal exact-return promise with bounded foreground work plus supervised recovery. The foreground deadline D is made once from the admitted settings, and nothing renews it. The job wait ends early enough for the stop, sealing and the move. Settings are checked before any effect. Every command and wait has a finite bound before it starts, and job-controlled output cannot cause unbounded memory, disk, parsing or cleanup work on the clock.

What the foreground cannot confirm, it contains: the output moves whole into a private quarantine folder, and the turn raises `EvidenceNotSealed` with the full UNKNOWN reservation. Before the job starts, a pending-cleanup record (`pending-cleanup/<turn>.json`, mode 600, no credential and no output) names the container, the label and the turn folder. A clean end deletes it. Any other end marks it pending, with the held folders. A process that dies mid-turn leaves it behind for the next process.

`recover_pending(C)` runs first in every turn, and an operator or scheduler can also call it on its own. One budget C (`recovery_budget_seconds`, default 5 s, finite and above 0) covers every operation in one pass. Ownership of a record is an exclusive file lock (`flock` on `.<record>.lock`). The turn takes it before the record exists and holds it for its whole life, and a recovery pass holds it for one attempt. The kernel drops the lock when its holder dies, in any PID namespace on the same file system, so process IDs decide nothing (they stay in the record for reports). A held lock means a live owner: recovery never touches that record, and it blocks new work unless it is a turn of this very process. A free lock means the owner is gone, after a crash, a restart with the same or another pid, or a turn whose final record write failed: the record blocks new work and is recovered. Recovery reads each record again after taking its lock, never acts on a stale listing, and never writes back a record that vanished meanwhile. Each attempt is recorded durably (its count, its backoff and an in-progress mark) BEFORE any stop or removal. If that record cannot be written, the attempt is not made: the original record stays as it was and keeps blocking, and `pending_cleanup()` reports `admission_failed`. A crash after the record leaves the attempt counted and marked, so its outcome stays visible as unknown. A record whose count has reached 5 counts as exhausted even if writing that state failed. A confirmed recovery whose record cannot be deleted keeps blocking until a later pass clears it. A failed record write removes its own temporary file, so failures never pile up orphan files. Local file systems only: locks on network file systems are not qualified. For each other record of this run whose backoff has passed, recovery verifies the container gone (killing it only if the name and label match). It then removes the leftover output and held folders, including files over 8 MiB, which only the foreground may not free, and deletes the record. If recovery cannot confirm, it records the attempt and doubles the backoff (1 s, 2 s, 4 s, and so on). After 5 attempts it marks the record exhausted, keeps it for intervention and never retries it on its own. The intervention path is `retry_exhausted()`. After a person has dealt with the cause, it returns exhausted records to pending with their history kept. Only a later `recover_pending` that confirms the container gone and the evidence removed clears them; nothing is released by the call itself. While any record of the run is pending or exhausted, new turns start nothing and return `CleanupPending` (no request; that never-sent reservation is released, and earlier UNKNOWN reservations stay). So at most one turn's evidence per runner is ever pending. Recovery never changes the ledger, never touches another run's records, and never kills a container whose label does not match.

Measured, not promised: a host stall inside one system call (an unlink of 0.5 to 1.2 s was seen under load) can still make a turn or a recovery pass end after its budget. Every such overrun is kept as measured evidence, and none is a tolerance. These are local tests only. Who runs recovery on a real host, how often, and the retention and storage bounds there are PROPOSED and NOT_RUN, and need separate production qualification.

## 9a. Known gaps in the local safeguards

- The ledger has no operator path to resolve an UNKNOWN reservation except late usage evidence. A planned "one explicit retry per case" therefore has no mechanism after an UNKNOWN attempt. A later change must add a recorded decision path.
- The ledger uses one flat price per token kind. The provider may charge more for tiers or cache. Recompute from the provider's documents at release.
- If a delegate reports two requests, the runner keeps one reservation as liability. The guard prevents the second request. A host-level count is still needed.
- Credential redaction and the leak scan cover the plain secret and its upper and lower case, URL-encoded, reversed, hex, base64 (aligned and offset), Authorization header and JSON `\u` escape forms, in file contents and file names. A secret that is split, compressed or encrypted is not covered. Evidence that cannot be scanned (over 8 MiB) is moved unread to a private folder and the turn fails closed, and a folder that cannot be cleared stops the turn with `EvidenceNotSealed`. Each turn captures its number, policy and credential value once, at its start. The job reads a private copy of the credential, so a later change to the source file cannot change what the host seals. Named pipes, sockets, devices and links in the evidence are removed and never opened. On every path out of a turn, including an unexpected exception or an interrupt, the host stops the turn's own container and verifies it is gone, then seals the evidence. If either step fails for any reason, the evidence folder is removed and the turn raises `EvidenceNotSealed`. A credential file that is missing, unreadable or empty stops the turn before any job starts.
- A credential file that is missing, unreadable or empty ends the turn with `CredentialUnavailable` before any job starts. The guarded runner still keeps the full reservation, as it does for any exception from the process boundary, so a misconfiguration uses up cap with no spend until a person reconciles it.
- The private copy of the credential sits in a temporary folder and is deleted when the turn ends. A hard kill of the host process can leave it behind.
- The host does not trust the client's exit code: after every client exit it verifies that the container is gone, and stops it if it is not, before any evidence is touched. A stop that runs while Docker is still creating the container can miss it, so absence has to show twice in a row. The stop step keeps the last tenth of the grace (at most half a second) for sealing and removal. Sealing stops a twentieth of the grace (at most a quarter second), and never less than 0.08 s (the step reserve of 0.04 s plus the move reserve of 0.04 s), before the deadline, so that the longest step that cannot be stopped (about 0.002 to 0.016 s measured idle, up to about 0.02 s under heavy load: one search of 8 MiB, one 1 MiB read or write, one batch of 1,024 undone escapes, or one scan for escapes that finds none) still ends in time under host load and removal keeps time. A file larger than 1 MiB that holds the credential is deleted whole instead of rewritten. The timeout is a maximum: the job wait ends by the deadline minus 0.08 s (the step and move reserves), so with a grace below 0.08 s the job gets up to that much less than its timeout, and a budget too small for the reserve starts no job. A negative grace is refused. Removal stops 0.04 s before the deadline, so the one-step move into quarantine fits. The clock is checked between every step of sealing a file, including each credential form. Removal has what is left of the one deadline and never more: once the deadline has passed, it does not start, and no step gets new time. An output is sealed once after the container is proved gone. No large job-written file is freed while the clock runs, because emptying or deleting a file takes time that grows with its size: an over-limit stdout file, a file too large to scan, or an output that holds one is moved in one step to a private `quarantine-*` folder (mode 700), and `purge_quarantine()` frees it between turns. A turn that held anything aside unscanned never reports success: it raises `EvidenceNotSealed` naming the folder, and the reservation stays in full. The job client runs with a file-size limit (`RLIMIT_FSIZE`) of 1 MiB + 1 byte, so a stdout flood cannot fill host disk or stall later disk steps; a client that tries to write past it gets SIGXFSZ (by default it exits) and the stop step verifies the container gone. After sealing, the result file is parsed, checked for the credential and mapped only when the time left covers the worst case for its size, freeing the parsed result included (0.25 s per MiB, about twice the measured worst of 0.06 s per MiB to parse plus as much to free deeply nested lists under load); otherwise, or if the clock passes during the check or by the time the parsed result is freed, the turn ends as UNKNOWN. No value the job chose is hashed before its type is checked: a refusal reason that is not text makes the result unusable, because job-chosen integers can be made to collide and turn a set into quadratic work. Limit: what a real container writes through the output bind mount is not size-limited by the host; such a flood is never freed on the clock, but heavy disk activity can still delay the ledger's commit. If an output cannot be removed in time, the rest is moved in one step to a private `quarantine-*` folder, the turn raises `EvidenceNotSealed` and says so, and `purge_quarantine()` removes those folders between turns. A quarantine folder holds unsealed evidence: it is private (mode 700) but it is on disk until it is purged. Every step of the removal ticks the clock, including the removal of an empty folder. Sealing and removal both work on directory descriptors and never open a link. A file is opened without following links and without blocking, and anything that is not a plain file is removed unread. A folder that a container still running swaps for a link is therefore unlinked as a link, and nothing outside the output is touched. A tree deeper than the process may hold descriptors for is moved, not removed. If the plain walk fails for any reason, such as a path longer than the host limit, the output is moved, never removed without a clock. `purge_quarantine()` has no clock and raises if a folder is left; it is an operator tool, not the supervised path. With a finite deadline the foreground deletes at most 256 entries, because mass deletion can stall one unlink for most of a second; a larger output is moved whole into quarantine for supervised recovery.
- An output with more than 10,000 entries is not sealed: it is removed, or moved to quarantine if removal runs out of time. A file over 8 MiB is moved unread to the private holding folder, and the turn then fails closed. A file is checked for every form of the credential in any case, raw and with JSON escapes undone (the clock is checked every 1,024 escapes); a file with more than 65,536 escapes is treated as holding the credential and removed, so the cost of one file stays bounded. A copy that redaction cannot reach removes the whole file. The authored provider script `input.json` is not sealed.
- The job's stdout goes to a file in the output folder, never into host memory. After the container is gone, on every path, an output larger than 1 MiB is moved whole in one step to the private holding folder and replaced by a one-line note; the turn then fails closed (`EvidenceNotSealed`, naming the folder), because the moved file was not scanned. It is never cut, because a cut could split the credential. An output that fits is sealed with the rest of the output. While the job runs, its stdout can still fill the host disk until the job timeout.
- The guard allows up to 2,500 characters of text around the prompt in the system message and does not check what that text says. The gate accepted this as a documented design. Stronger pinning of the envelope needs a separate decision.
- Sealing a single file of up to 8 MiB reads it whole and runs a few linear passes over it. The clock is checked before and after that work, not inside it.
- The host reads the job's result file through a descriptor without following a link and without blocking, only if it is a plain file of at most 256 KiB (real results are about 6 KiB), and only within the deadline; otherwise the turn ends as UNKNOWN. Sealing removes links, pipes, sockets and devices from the output even when no credential is configured.
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
