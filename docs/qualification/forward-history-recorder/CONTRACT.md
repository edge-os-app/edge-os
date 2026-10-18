# Forward history recorder and payload binding contract

Status: LOCAL implementation contract for task `FORWARD-HISTORY-RECORDER-L4-20261015-LOCAL-v1`, amended by
`HISTORY-TRANSPORT-RECEIPTS-L4-20261015-LOCAL-v1` (transport receipts sidecar). It defines the recorder
(`scripts/forward_history_recorder.py`) and the offline checker (`scripts/history_payload_binding.py`). It
authorizes no provider, credential, chain, account, wallet or recording operation. All tests use synthetic transports,
fake clocks and sentinel credentials.

The versioned ACTUAL successor is defined in
[ACTUAL_HISTORY_PAYLOAD_BINDING.md](../../implementation/ACTUAL_HISTORY_PAYLOAD_BINDING.md). It adds an internally owned
`run_actual_attempt`, `/2` handoff/report and saved-data admission. The `/1` behavior described below remains unchanged;
its artifacts stay synthetic and cannot be promoted. The successor grants no provider operation or release activation.

## Versions and predecessor

| Identity | Value |
|---|---|
| Recorder input | `edge-os.forward-history-input/1` |
| Recorder handoff | `edge-os.forward-history-handoff/1` |
| Canonical payload | `edge-os.forward-history-payload/1` |
| Binding report | `edge-os.history-payload-binding/1` |
| Transport receipts sidecar | `edge-os.forward-history-transport-receipts/1` |
| Creation-event decoder | `retained-v2-pair-created/1` |
| Predecessor read packet | `docs/qualification/qualified-actual-demo/SOURCE_FACT_PACKET.json`, SHA-256 `c4fc01c4d498742cd9a904606135fdb2b27fea448bb254462a79a9f67824312f` |

The predecessor file is not modified. This contract amends its mechanics only where listed below. The predecessor's
unamended digest rule is not reused.

## Mechanical amendments to the predecessor

1. Optional `topic3` keeps its presence. An absent value projects to `{"presence":"ABSENT"}`. An explicit null projects
   to `{"presence":"NULL"}`. A non-null fourth topic is unsupported. The two projections hash differently.
2. Quantities are strictly defined (see canonicalization). The predecessor said only "base-10 integers".
3. P3 omits `to_block`. It uses the literal predecessor filter, `include_all_blocks=true`, `max_num_blocks=10000` and
   the accepted `LOG_FIELD_SELECTION` and `BLOCK_FIELD_SELECTION`. There is no implied end block and no pagination loop.
4. The P3 admission rule is a one-second slot `[due, due+1s)` for every scheduled read. There is no catch-up, grace,
   retry or moved T0. This is a conservative recorder bound frozen by the controller.
5. P6 has no implemented call. Its status stays `EXTERNAL_EVIDENCE_REQUIRED`. A missing P6 destination reference keeps
   an input `NOT_READY` with zero calls.
6. The executable recorder ceiling is P0-P5 only: 17 QuickNode and 9 HyperSync calls, 26 in total. The predecessor's
   29-call total (with P6) and the later application's 64 history plus 2 Nansen reservations are separate allowances.

## Input

The input is one JSON object with exactly these keys. Unknown or missing keys are refused.

| Key | Rule |
|---|---|
| `schema_version`, `predecessor_sha256` | Literal values above. |
| `attempt_id` | `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. One attempt id is executed at most once. |
| `source_id`, `evidence_class` | Text; `SYNTHETIC` or `ACTUAL`. |
| `chain_id` | `143`. |
| `pool`, `token0`, `token1`, `base`, `quote` | 20-byte addresses; `{base, quote} == {token0, token1}`. |
| `swap_topic0`, `selectors` | The predecessor Swap topic and the four predecessor selectors, exactly. |
| `expected_decimals` | `{"token0": int, "token1": int}`. |
| `creation` | `decoder`, `transaction_hash`, `block_number`, `block_hash`, `transaction_index`, `log_index`, `factory`, `topic0`. |
| `t0_utc` | `YYYY-MM-DDTHH:MM:SSZ` on the 300-second grid. |
| `window_seconds`, `bucket_seconds` | `1200` and `300`. |
| `destinations` | `quicknode_host` (host only) and `hypersync_url` (`https://<host>/query`). |
| `credential_slots` | Slot names for `quicknode` and `hypersync`. Values are never in the input. |
| `output_dir` | Absolute, existing, non-symlink directory. |
| `decisions`, `plans`, `p6` | References for D1-D3, both provider plans and the P6 dependency. |

Validation of every value, limit and schedule finishes before any credential read. A missing decision, plan or P6
destination reference returns `NOT_READY`: no attempt directory, no credential read and zero calls.

`python scripts/forward_history_recorder.py plan --input <file>` validates and prints a redacted plan. It reads no
credential and sends nothing. `recover --attempt-dir <dir>` prints a read-only journal summary. The only network entry
is the library function `run_attempt`, which requires an injected transport, clock and credential source. This ticket
authorizes only synthetic injection.

## Creation-event decoder `retained-v2-pair-created/1`

The receipt log must have exactly three topics: the creation topic, token0 and token1. Each token topic is 12 zero bytes
then 20 address bytes. The data is exactly 64 bytes: word 1 is 12 zero bytes then the pool address, and word 2 is an
unsigned 256-bit pair count. Exactly one receipt log may match the expected factory and creation topic. Its
transaction, block, transaction index and log index must equal the input. The token order and pool must equal the input.

The P1 HyperSync query selects the factory and creation topic in `[block, block+1)`. Exactly one log must match. Its
identity fields, three topics and data must equal the receipt event. `topic3` may be absent or null. `removed` is not
requested; a supplied `true` is refused. The `factory()` read must return one ABI address word equal to the emitter.
Any difference, failed P1 call or ambiguous match is a safety stop. No other layout is guessed. The retained private
event that fixed this layout is not published here.

## Schedule and calls

`WE = T0 + 1200`. Bucket `i` is `[T0 + 300i, T0 + 300(i+1))`.

| Phase | Calls (maximum) | Time rule |
|---|---|---|
| P0 | none | Validation and readiness; T0 is journaled before the first call. |
| P1 | `eth_chainId`, creation receipt, creation HyperSync query, pool `factory()`, `eth_getCode` pool/token0/token1 (6 QN, 1 HS) | Any time; chain id must be 143. |
| P2 | `eth_getBlockByNumber("latest", false)` (1 QN) | Admitted in `[T0-120, T0-5)`; complete before `T0-5`; timestamp `< T0`. |
| P3 | HyperSync forward query (8 HS) | First read slot `[end+30, end+31)`; conditional second read slot `[end+120, end+121)`. |
| P4 | decimals token1, token0, then pool `token0()`, `token1()` at `B_START` (4 QN) | After the last P3 slot; before `T0+3600`. |
| P5 | finalized, latest, decimals at `B_END` (token1, token0), current decimals (token1, token0) (6 QN) | At or after `WE+60`; before `WE+3600`. |

The slot bound is enforced again at the durable admission boundary, after pacing and every clock observation. A
call whose admission time is at or after `due+1s` is refused before its journal record. It adds no liability and no
send, and the read is recorded `MISSED`. The reply deadline stays separate.

A second P3 read is made only after a valid first reply proves insufficient coverage. A failed, rejected, missed or
expired first read never allows it. The first read's deadline is the second event. A wake outside a slot records
`MISSED` and continues to the next event. Pacing is at least one monotonic second between admissions to one provider;
it never moves a call into another slot.

Each call's effective deadline is the earliest of 120 seconds, its phase or schedule cutoff and `WE+3600`. The connect
timeout is at most 15 seconds. A call at or after its deadline is refused before admission. A clock that moves
backward (UTC or monotonic) is untrusted: the recorder stops further sends and keeps availability unknown.

The injected cancel callback is checked before every admission and after every decode. Once it returns true, no
further call is admitted, the attempt ends with status `CANCELLED`, and open buckets close `INCOMPLETE`.

## Stops and weak evidence

Safety stops end every provider and leave remaining buckets `INCOMPLETE`:

- HTTP 401, 402, 403 or 429, and any quota, rate, request-limit or payment wording in a reply body, also with status
  200 (for example a JSON-RPC error message `request limit exceeded`). Other RPC errors stay weak.
- A credential echo in a body, header, provider error or transport exception (`CREDENTIAL_INCIDENT`).
- Any failed P1 call or P1 identity difference, an anchor timestamp at or after T0, conflicting block facts, wrong
  decimals or wrong pool token order.
- An excess, unlisted or oversized request, or an aggregate reply budget that cannot fit.

Other failures (timeout, non-2xx, JSON-RPC error, malformed reply) are weak evidence: `NOT_READ` or no delivery, with no
retry. Later independent phases still run. Weak finality is recorded once and never repeated. A missing `B_END` skips
only the two dependent decimals reads.

## Forward pages and coverage

An accepted P3 reply is an object with quantity `archive_height`, positive `next_block`, object `data` with explicit
`blocks` and `logs` arrays and an optional object `rollback_guard`. The page range is `[from_block, next_block)` with
at most 10,000 blocks. It needs exactly one header for each block in the range, nondecreasing timestamps across the
chain and no header later than the reply's receipt time. Every log must be inside the range, match its header's hash,
name the pool and the Swap topic, project cleanly and have a new ordering identity. Every supplied rollback-guard
fact must match the page (the accepted `source_transport._frame` rule): `first_block_number` is the page start,
`block_number` is the page end, and `timestamp` and `hash` are the page-end header's facts. A present
`first_parent_hash` must equal the known header hash of the block before the page start. A malformed guard fact
rejects the page; a contradictory one is the `CONFLICTING_BLOCK_FACT` safety stop. Anything else rejects the page
(no delivery proof). A header that contradicts an earlier fact or the P2 anchor is a safety stop.

The cursor moves to `next_block` after every accepted reply, also an insufficient one. Earlier headers and logs are
kept. The chain starts at `B_ANCHOR` and has no gaps. A bucket is covered when the chain holds a header with timestamp
`>= end`. At first coverage the bucket freezes: reply id, receipt time, record count and payload digest of every log
in the bucket received so far. Later replies never rewrite it. A bucket whose permitted reads end without coverage
closes `INCOMPLETE` with a reason, and later replies do not backfill it.

`B_PRE` is the last header `< T0`; `B_START` the first `>= T0`; `B_END` the last `< WE`; `B_POST` the first `>= WE`.
They must be adjacent. The final scan is `[B_PRE, B_POST+1)`. Every Swap log in the scan counts, including boundary-block
logs outside the window. More than 61 adds `SCAN_LOG_COUNT_EXCEEDS_61` as weaker evidence.

## Bytes, journal and private files

- Request body: at most 65,536 bytes. Reply: at most 2,097,152 bytes, enforced in transport and again on the returned
  bytes. Total replies: at most 67,108,864 bytes, checked before admission.
- The attempt directory `<output_dir>/<attempt_id>` is created exclusively with mode 0700. Files are created
  exclusively with mode 0600 and `O_NOFOLLOW`. An existing attempt directory is refused before any credential read.
- `journal.jsonl` records `ATTEMPT_STARTED` (with T0) before any credential read. Each physical call appends `ADMITTED`
  with `UNKNOWN` liability, request hash and length, phase, slot and deadline, flushed and fsynced before the send.
  `RESOLVED` follows only after the reply body is safely written, or after an oversized reply is refused unsaved.
  Admitted calls equal resolved plus unknown. `recover` treats an unparseable FINAL line as an interrupted append: it
  reports the complete prefix, keeps every uncertain liability, sets `torn_tail` with a notice and leaves the bytes
  unchanged. An unparseable interior line is the stable refusal `JOURNAL_CORRUPT`. Uncertain
  admissions are never refunded or resent. A journal or body write failure stops all sends.
- Credentials are read once each, after validation, through the injected slot reader. Bodies and headers are scanned for
  the full QuickNode URL, its path secret, the bearer token and `Bearer <token>` before anything is saved. An echo saves
  only incident metadata and a body hash.

## Canonical payload `edge-os.forward-history-payload/1`

The projection has exactly twelve fields: `block_number`, `transaction_index`, `log_index`, `block_hash`,
`block_timestamp`, `address`, `topic0`, `topic1`, `topic2`, `topic3`, `data`, `removed`. `transaction_hash` is a
required, validated log identity, kept for audit, but not a payload field.

- Quantities: non-boolean JSON integers, ASCII decimal digits or `0x` plus at most 64 hex digits; nonnegative and at
  most `2^256-1` (at most 78 decimal digits). Booleans, floats, signs, whitespace, empty strings, `0X` and longer or
  larger values are refused with a stable code before any conversion. They become JSON integers.
- Hex: addresses 20 bytes, hashes and topics 32 bytes, Swap data exactly four 32-byte words; validated, then lowercased.
- `removed` must be a JSON boolean. Required fields are never filled. `topic3` is the presence tag above.
- Recorder input takes `block_timestamp` from the matching validated header. Saved exports must carry it.
- Records sort by numeric `(block_number, transaction_index, log_index)`. Duplicate identities are refused.
- Bucket membership is `start <= block_timestamp < end`.
- Bytes are the P02 `canonical_bytes` of the list (sorted keys, compact separators, UTF-8, no trailing newline).

Literal oracle: one record with number 1, transaction and log index 0, timestamp 1800000000, address `0x` plus twenty
`22` bytes, block hash `0x` plus thirty-two `11` bytes, the Swap topic0, zero topic1/topic2, data words `[1,0,0,2]`,
`removed=false` and absent topic3 is 771 bytes with SHA-256
`c7032fb27b3a0b2103c49ab792a402dc9e5c99795b948dab1f3ff297d7fbcccf`. The same record with explicit null topic3 is 769
bytes, `925cef405e3ad73335776bc6ce117a8eacc4ef5d3d9cc547dbe478e04ac3cb82`. The empty list is
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

## Handoff `edge-os.forward-history-handoff/1`

`handoff.json` is written once, exclusively, as canonical JSON; its SHA-256 is computed on the final bytes. It contains
the versions, predecessor, input and recorder-code hashes, attempt and source identity, evidence class, status and stop
reason, network, market and pool token order, window, exact query and field selection, boundaries, scan, scan log count,
retained header facts (in-scan log blocks and boundaries), phase outcomes, P3 reply summaries, facts (bytecode hashes
and lengths of decoded bytes, decimals, finality, archive height, `fee_transfer_semantics=EXTERNAL_EVIDENCE_REQUIRED`),
clock trust, call accounting, a `calls` list and exactly four buckets. Each `calls` entry has the admitted call id,
phase, slot, provider, request SHA-256 and byte count, outcome (`REPLY_RECEIVED`, `OVERSIZED_REFUSED`,
`CREDENTIAL_INCIDENT` or `UNKNOWN`), HTTP status, and the retained reply body SHA-256 and byte count. A credential
incident or an oversized reply keeps no body hash in the handoff.

Each bucket has `start_utc`, `end_utc`, `status` (`DELIVERED` or `INCOMPLETE`), `reply_id`, `received_at_utc` (UTC
seconds rounded up, never earlier than receipt), `received_at_utc_us`, `record_count`, `payload_sha256`, `reply_body_sha256` (the delivering reply's retained body)
and `reason`.
An incomplete bucket has null delivery, count and digest plus a reason; it is never an empty payload.
`delivery_records` holds only delivered buckets. No floats appear. A handoff never contains a release SHA and never
freezes a release; the release is built later from these facts.

## Evidence class

The handoff `evidence_class` is always `SYNTHETIC`. The input's `evidence_class` is kept as
`requested_evidence_class`. The accepted network transport (`StdlibHttpTransport` without a test connector) would be
the future actual route, but the public `HttpTransport` seam cannot show whether a test connector is installed. A
caller's `ACTUAL` string therefore never promotes an injected transport. When `ACTUAL` is requested, `evidence_notice`
starts with `ACTUAL_NOT_ESTABLISHED`. Making `ACTUAL` reachable needs a separately qualified transport-provenance seam.

The transport receipts sidecar below records construction facts only. It does not change this rule: every handoff,
including one made through the recorder-owned stdlib construction or with a requested `ACTUAL`, stays `SYNTHETIC`.

## Transport receipts sidecar `edge-os.forward-history-transport-receipts/1`

After `handoff.json` is written, the recorder writes `transport-receipts.json` in the attempt directory, exclusively,
mode 0600, as canonical JSON (the same `canonical_bytes`). Its keys are exactly:

| Key | Value |
|---|---|
| `schema_version` | `edge-os.forward-history-transport-receipts/1` |
| `attempt_id`, `recorder_code_sha256` | As in the handoff. |
| `handoff_sha256` | SHA-256 of the final `handoff.json` bytes. |
| `evidence_class` | Always `SYNTHETIC`. |
| `transport` | `{construction, implementation, implementation_sha256}`. |
| `receipts` | One entry per admitted call, in admission order. |

Construction comes only from the recorder:

- `owned_stdlib_transport()` builds `StdlibHttpTransport(connect=..., clock=time.monotonic)` with the accepted
  connector captured when the recorder is imported, not from the constructor's current defaults: `OWNED_STDLIB`.
- `local_fixture_transport(connect, clock)` builds `StdlibHttpTransport(connect=..., clock=...)` for fixtures and
  owned loopback checks: `LOCAL_FIXTURE`.
- Every other object is `INJECTED`, with null `implementation` and `implementation_sha256`. This includes a caller's
  own `StdlibHttpTransport(connect=...)`, a subclass, a wrapper and an object that carries an `ACTUAL` or construction
  label.

For `OWNED_STDLIB` and `LOCAL_FIXTURE`, `implementation` is
`edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport` and `implementation_sha256` is the
SHA-256 of that module file, read when the recorder is imported. Input JSON and transport attributes never supply these
facts.

`transport_binding_sha256` is the SHA-256 of the canonical `transport` object. The binding is checked before every
admission, before the journal record. A recorded construction must still have the exact class, the class attributes and
the instance attributes it was created with (compared by identity), and the request method called is the class method
captured at import. An injected object keeps the class and `request` it had at binding. Any change (an instance
`request`, a new connector or clock, a reassigned class or a class-level method patch) is refused with
`ADMISSION_TRANSPORT_SUBSTITUTED`: nothing is sent, no liability is added and every later admission stops. A recorded
construction altered before binding is reported `INJECTED` and never sends.

The binding is checked again after the `ADMITTED` record, at the last point the recorder controls before the send. This
second check covers a change made by a recorder clock reading or by the journal write. If it refuses, the call was
admitted but not sent: its liability stays `UNKNOWN`, its receipt keeps null fields, nothing is resent and the attempt
stops with `ADMISSION_TRANSPORT_SUBSTITUTED`.

Residual scope. The binding compares objects by identity in this process. It does not detect: a change made by the
transport's own connector or clock callbacks while the bound send runs; a changed function `__code__`; a class or module
patched before the recorder is imported; or changes to the module globals that `StdlibHttpTransport` uses. These are
in-process changes by the process owner, which this sidecar does not defend against. All evidence stays `SYNTHETIC`.

Each receipt has exactly `call_id`, `transport_binding_sha256`, `request_sha256`, `outcome`, `status`, `body_sha256`,
`body_bytes`, `received_at_utc_us` and `elapsed_us`. `outcome`, `request_sha256`, `body_sha256` and a received reply's
`status` and `body_bytes` equal the handoff `calls` entry; an incident or oversized reply also keeps its status and byte
count. The receipt clock and returned bytes are captured immediately after the bounded body returns, before decode.
Times are integer microseconds: UTC receipt time and monotonic time since admission. A UTC or monotonic reading earlier
than the admission leaves both null; the clock-reversal stop still applies. A missing reply keeps null status, body and
time fields with `UNKNOWN` outcome and liability. A credential incident never exposes a body digest.

A sidecar write failure is reported as `transport_receipts_status = WRITE_FAILED` in the `run_attempt` result. The
completed handoff is not changed and nothing is resent. A `transport-receipts.json` file from a `WRITE_FAILED` attempt
is not evidence, even when the file is present and complete; the recorder does not delete it. Only a sidecar whose
SHA-256 equals the returned `transport_receipts_sha256` is the attempt's sidecar. An attempt that is interrupted or
refused before its handoff writes no sidecar; an existing attempt directory is never reused.

The sidecar proves only the construction and receipt facts captured within this process. It is not provider
authentication, it does not establish that the bytes came from a provider, and it is no defense against a malicious
process owner. Input, handoff, payload and report versions stay `/1`; `check_saved_export` is unchanged. A later checked
L2 handoff must define any `/2` handoff, report migration, actual-release binding and the explicit rejection of legacy
evidence before any actual classification. A historical `/1` artifact is never upgraded from its label or sidecar.

## Saved-export checker `edge-os.history-payload-binding/1`

`python scripts/history_payload_binding.py --handoff H --export E --expected X --out R` reads bounded files
(handoff 8 MiB, export 64 MiB, expected 64 KiB), refuses duplicate keys, floats and non-finite values, and writes one
exclusive 0600 report. The export is `{dataset_id, owner_id, content_sha256, content, raw_records}`. The trusted
expected file holds `owner_id`, `dataset_id`, `release {release_id, sha256, kind}`, `source_id` and `handoff_sha256`.

1. Refuse an expected file without non-empty `owner_id`, `dataset_id`, `source_id`, `handoff_sha256` and
   `release.{release_id, sha256, kind}`. Then check the handoff bytes' SHA-256, handoff schema and canonicalization
   version.
2. Recompute the content hash with `records.contract_adapter.sha256_hex` and the raw hash with
   `research_history.qualification_engine.raw_sha256` before any normalization; check the raw count.
3. Compare outer and inner owner and dataset ids, each `content.operating_release` field, source id, evidence side,
   chain id, pool, base and quote, the saved `binding_view.token_order` against P02 `[base, quote]` (not pool
   order), window and the query scan with the handoff.
   A value missing on either side is INCOMPLETE, never PASS. The evidence side maps the saved application classes
   exactly: `RECORDED_RESPONSE`, `RECORDED_NATIVE_RESPONSE`, `AUTHORED_HTTP_RESPONSE` and `RELEASE_STAND_IN_RESPONSE`
   are SYNTHETIC; `PROVIDER_ACTUAL` is ACTUAL; any other or malformed label has no side and cannot pass.
4. Project every raw record with its stored `block_timestamp`; require it in scan and equal to the retained header
   fact. Compare the scan log count. For each of exactly four saved buckets, compare the interval, `available_at`
   with `max(bucket_end, received_at_utc)`, the count and the canonical digest of half-open members.
5. Report `PASS`, `MISMATCH` or `INCOMPLETE` per check and bucket. Contradiction gives MISMATCH. Missing evidence gives
   INCOMPLETE. Overall PASS needs every check and bucket to pass.

A PASS proves payload binding only. It does not authenticate the owner, prove database provenance, grant source rights,
promote P07, adopt a market, authorize replay or prove execution timing. Current owner GET excludes raw records;
the later application must compute this binding in process on owner-scoped raw records.

## Verification recipe

From the candidate checkout root, with an existing qualified Python 3.14 environment:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=.:apps/api/src apps/api/.venv/bin/python -m pytest --noconftest -p no:cacheprovider -q tests/test_forward_history_transport_receipts.py tests/test_forward_history_recorder.py tests/test_history_payload_binding.py
```

The suite needs no Docker, database, service, socket or provider. The receipts tests run the real
`StdlibHttpTransport` through `local_fixture_transport` with an in-memory connection.

The owned loopback qualification runs the real recorder wrapper and `StdlibHttpTransport` against an authored
`HTTPServer` on `127.0.0.1` port 0 through `local_fixture_transport`. It is skipped unless enabled:

```sh
EDGE_OS_LOOPBACK_QUALIFICATION=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=.:apps/api/src apps/api/.venv/bin/python -m pytest --noconftest -p no:cacheprovider -q tests/test_forward_history_transport_receipts.py -k loopback
```

A transport object without `request` is outside the declared `HttpTransport` interface and fails while the recorder
binds it, after the attempt journal exists and before any send. The loopback cleanup check also reconnects to the closed
port; another local process could take that ephemeral port first, so a failure of that one probe needs the listener
descriptor and thread checks to judge it.

It checks exact wire bytes against receipt hashes, the 2 MiB cutoff, header and body drip deadlines, redirect
non-following, cancellation between body reads, secret echo in a body or header, one durable admission per wire request,
interrupted no-resume behavior, and that every listener, server thread and handler thread is gone after each test. Its
evidence stays `LOCAL_FIXTURE` and `SYNTHETIC`. It is not provider, DNS or TLS evidence; an actual operation still needs
its own authority.

## Claim limits

Synthetic handoffs stay `SYNTHETIC`. Nothing here proves the HyperSync endpoint's served shape, account rights or
limits, MOE mechanics, market activity or fillability. The resolver and initial TCP connect of the accepted transport
cannot be interrupted by its watchdog; that disclosed limit remains.
