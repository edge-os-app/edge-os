# Local Privy policy-proof driver contract

Task `P21-UNFUNDED-SPECIMEN-DRIVER-L1-20261016-LOCAL-v1`, issue #20 P21 and #58. Base `b8c52b692afdd44afb34ed9969ef330d8c800aa9`.

Status `LOCAL`. Provider proof `UNQUALIFIED`. Every result from this unit is `SYNTHETIC_FIXTURE`.

This file is the shared specification for the offline specimen and evidence driver. It does not approve policy fields, a source identity, a wallet or executor design, or any paid or signing operation. A local PASS does not prove Privy enforcement, Kuru deployed-source behavior or demo readiness.

## Files

| Path | Responsibility |
| --- | --- |
| `scripts/privy_unfunded_proof/specimens.py` | Frozen baseline, named mutation table, frozen request bytes and hashes, manifest hash, admission checks and the durable one-use attempt store. |
| `scripts/privy_unfunded_proof/evidence.py` | The single run entry `run_specimen`. Bounded capture before parse, the synthetic reply profile, outcome classification, positive-control gating and stop after `BREACH`. |
| `tests/privy_unfunded_proof/test_specimens_and_evidence.py` | Literal mutation tests, lifecycle tests with injected send, clock and decoder, and redaction tests. |
| `docs/qualification/privy-unfunded-proof/CONTRACT.md` | This contract. |

Import paths are `scripts.privy_unfunded_proof.specimens` and `scripts.privy_unfunded_proof.evidence` from the checkout root. Both reuse `edge_os_api.kuru_flow.flow_calldata.decode_flow_call` without change. The test-only encoder in `apps/api/tests/kuru_flow/_support.py` is not imported. The baseline calldata is an independent frozen literal. No general ABI encoder exists in this unit. A mutation is a named replacement of whole 32-byte words, one program byte, one appended word or one transaction field.

Importing either module makes no network, subprocess or file call. Running either module as a program exits with status 2 and the text `refused: local synthetic driver has no actual runner`. `run_specimen` accepts only `run_mode="SYNTHETIC_FIXTURE"`. Any other mode raises `SpecimenRefused("ACTUAL_RUN_REFUSED")` before any effect.

## Hashes

The environment has no Keccak-256. Every hash in this unit is SHA-256 and every field name says so. `request_sha256` is the hash of the canonical request envelope. `raw_body_sha256` is the hash of the exact reply bytes. `signed_bytes_sha256` is the hash of signed transaction bytes held in memory. `capture_record_sha256` is the hash of the saved sanitized capture record. A sanitized-record hash identifies the saved record, not the bytes that redaction removed. Selectors are authored stand-ins (`0x12345678`, `0x87654321`). The real selector stays `TO_COMPUTE`.

## Frozen request format

Destination `https://api.privy.io/v1/wallets/{wallet_id}/rpc`, HTTP method `POST`. Allowed wallet IDs `synthetic-probe-wallet-a` (address `0x00000000000000000000000000000000000000a1`) and `synthetic-probe-wallet-b` (address `0x00000000000000000000000000000000000000a2`). Allowed RPC operations `eth_signTransaction` and `personal_sign`. The only allowed request header is `privy-request-expiry`. The driver adds no credential. A transport adapter is outside this unit.

Body bytes are `json.dumps(body, sort_keys=True, separators=(",", ":"))` in UTF-8. The canonical envelope is the same encoding of `{"body_sha256": sha256(body bytes), "headers": headers, "http_method": "POST", "url": url}`. `request_sha256` hashes the envelope bytes. Computing it parses no JSON.

The manifest is the canonical JSON list of `[specimen_id, profile, expected, request_sha256 or null]` in table order. `MANIFEST_SHA256` is the frozen literal `8d81f5d0fb60eb10ad6760cb5e600c886e7190e4a1cd27b95685135bd1a6f940`. `run_specimen` refuses a table whose manifest differs with `MANIFEST_MISMATCH`, and refuses a request whose bytes no longer hash to its frozen `request_sha256` with `REQUEST_BYTES_CHANGED`, both before any effect.

Baseline type-2 transaction, all values synthetic:

| Field | Value |
| --- | --- |
| `type` | 2 |
| `chain_id` | 143 |
| `to` | `0xb3e6778480b2E488385E8205eA05E20060B813cb` |
| `value` | 0 |
| `nonce` | 0 |
| `gas_limit` (L) | 300000 |
| `max_fee_per_gas` (F) | 100000000000 |
| `max_priority_fee_per_gas` (P) | 2000000000 |
| `data` | selector `0x12345678`, then the words below |

Calldata words for `executeSwap`, alias ABI `intent` and `fees`:

| Word | Field | Baseline |
| --- | --- | --- |
| 0 | `intent.tokenUserBuys` | `0x...b1` sentinel |
| 1 | `intent.minAmountUserBuys` | 1000000 |
| 2 | `intent.tokenUserSells` | `0x...c1` sentinel |
| 3 | `intent.amountUserSells` | 2000000 |
| 4 | `fees.feeCollectorAddress` | `0x...d1` |
| 5 | `fees.feeBps` | 10 |
| 6 | `fees.referrerAddress` | `0x...e1` |
| 7 | `fees.referrerFeeBps` | 5 |
| 8 | `fees.isInTokenFee` | false |
| 9 | program offset | 320 |
| 10 | program length | 8 |
| 11 | program bytes | `a1b2c3d4e5f60718`, zero padded |

Sentinel addresses select no asset and prove no executable route. The fee values are nonzero so recipient extraction can differ. Native MON stays outside the application route. The `executeSwapWithReceiver` variant has offset 352 and receiver word `0x...a2`.

## Specimen tables

Two profiles exist. Each holds at most 32 wallet-RPC specimens. The table rejects a 33rd. The `raw` profile tests full raw-byte binding. The `decoded` profile tests tuple extraction and holds no full-data guard. Each profile has its own positive control. A result in one profile never qualifies, gates or masks the other.

`raw` profile, 30 specimens:

| ID | Category | Change from baseline | Expected |
| --- | --- | --- | --- |
| `raw.baseline` | positive control | none | `ALLOW` |
| `raw.wrong_chain` | field | `chain_id` 10143 | `POLICY_DENY` |
| `raw.foreign_wallet` | authority | wallet B URL, same body | `AUTHORIZATION_DENY` |
| `raw.wrong_to` | field | `to` `0x...f1` | `POLICY_DENY` |
| `raw.receiver_selector` | field | `executeSwapWithReceiver`, receiver wallet B address | `POLICY_DENY` |
| `raw.program_byte_flip` | field | program byte 3 `d4` to `2b` | `POLICY_DENY` |
| `raw.trailing_word` | field | one appended word `0x...01` | `POLICY_DENY` |
| `raw.data_hex_case` | diagnostic | `data` hex letters uppercase, same bytes | `DIAGNOSTIC` |
| `raw.token_user_sells` | field | `0x...c2` | `POLICY_DENY` |
| `raw.token_user_buys` | field | `0x...b2` | `POLICY_DENY` |
| `raw.amount_user_sells` | field | 2000001 | `POLICY_DENY` |
| `raw.min_amount_user_buys` | field | 999999 | `POLICY_DENY` |
| `raw.fee_collector_address` | field | `0x...d2` | `POLICY_DENY` |
| `raw.fee_bps` | field | 11 | `POLICY_DENY` |
| `raw.referrer_address` | field | `0x...e2` | `POLICY_DENY` |
| `raw.referrer_fee_bps` | field | 6 | `POLICY_DENY` |
| `raw.is_in_token_fee` | field | true | `POLICY_DENY` |
| `raw.native_value` | field | `value` 1 | `POLICY_DENY` |
| `raw.type1_envelope` | envelope | type 1 with `gas_price` F, no type-2 fee fields | `POLICY_DENY` |
| `raw.type0_envelope` | envelope | type 0 with `gas_price` F, no type-2 fee fields | `POLICY_DENY` |
| `raw.type4_envelope` | envelope | type 4 with authorization list | `NOT_RUN` |
| `raw.gas_limit` | field | L+1 | `POLICY_DENY` |
| `raw.max_fee_per_gas` | field | F+1 | `POLICY_DENY` |
| `raw.max_priority_fee_per_gas` | field | P+1 | `POLICY_DENY` |
| `raw.window_at_t` | timing | baseline body observed at T | `POLICY_DENY` |
| `raw.window_after_t` | timing | baseline body observed after T | `POLICY_DENY` |
| `raw.request_expiry` | timing | header `privy-request-expiry: 1792000000000` | `EXPIRY_REFUSAL` |
| `raw.allowance_approve` | operation | `approve(entrypoint, 2000000)` to `0x...c1`, selector `0x095ea7b3` | `POLICY_DENY` |
| `raw.personal_sign` | operation | `personal_sign` of inert text | `POLICY_DENY` |
| `raw.post_removal` | authority | baseline body after owner removal | `AUTHORIZATION_DENY` |

`decoded` profile, 14 specimens, same request bodies as the matching raw rows: `decoded.baseline`, `decoded.program_byte_flip`, `decoded.program_hex_case` (program letters uppercase only, `DIAGNOSTIC`), `decoded.trailing_word`, `decoded.token_user_sells`, `decoded.token_user_buys`, `decoded.amount_user_sells`, `decoded.min_amount_user_buys`, the five fee rows and `decoded.receiver_selector`. Its declared policy paths use only the alias ABI names: `executeSwap.intent.*` and `executeSwap.fees.*`. The public Solidity names `swapIntent` and `feeCollection` are never mixed in.

The trailing-word specimen stays a raw-byte challenge. The accepted decoder refuses trailing words with `INCONSISTENT_ABI`. A local decode refusal is never counted as provider denial, and the driver does not filter the specimen out.

The type-4 specimen needs separately supplied valid owner authority. This unit performs no signing and accepts no authority. It always returns `NOT_RUN` with reason `OWNER_AUTHORITY_ABSENT`, or `SYNTHETIC_AUTHORITY_NOT_PROOF` when a caller supplies any authority object. A synthetic or unrelated signature is never delegation proof.

## Attempt lifecycle

State per specimen: `NOT_SENT`, then `INTENT_SAVED`, then one terminal outcome. A specimen whose intent exists without a valid terminal record is `UNCERTAIN`. A torn or corrupt record is `UNCERTAIN`.

1. Refuse before effect: actual mode, a manifest mismatch, an unknown ID, a `NOT_RUN` specimen, a request whose bytes no longer hash to the frozen value, the stop marker, an existing intent, or a missing positive control.
2. Claim with `os.open(..., O_CREAT | O_EXCL | O_WRONLY)` of `<id>.intent.json`, write, `fsync` the file and the directory. Exactly one claimant wins across threads and processes. A failure here raises `SpecimenRefused("INTENT_NOT_PERSISTED")` and makes no send. The partly persisted file leaves the specimen `INTENT_SAVED` or `UNCERTAIN`. Both states refuse every later attempt with `ATTEMPT_UNCERTAIN`.
3. Call the injected send once. No retry, redirect, alternate endpoint, renewal, policy change or cleanup request exists.
4. Capture, classify and write `<id>.outcome.json` with `O_EXCL`.

The store key is the specimen ID only. A new transport, a new response or a new driver object cannot reset an `INTENT_SAVED` or `UNCERTAIN` specimen. A fresh Python process sees the same files and refuses the same way.

Refusal codes: `ACTUAL_RUN_REFUSED`, `MANIFEST_MISMATCH`, `UNKNOWN_SPECIMEN`, `NOT_RUN`, `REQUEST_BYTES_CHANGED`, `STOPPED_AFTER_BREACH`, `ALREADY_CLAIMED`, `ATTEMPT_UNCERTAIN`, `POSITIVE_CONTROL_NOT_QUALIFIED`, `INTENT_NOT_PERSISTED`. Table admission errors raise `SpecimenTableError` with codes `DUPLICATE_ID`, `MALFORMED_ID`, `UNSUPPORTED_OPERATION`, `UNSUPPORTED_DESTINATION`, `UNSUPPORTED_HEADER`, `OVER_CAP`, `REQUEST_OVER_BOUND`.

## Local bounds

These are local safety bounds, not an actual grant.

| Bound | Value | Exact value | Value plus one |
| --- | --- | --- | --- |
| Request body bytes | 4096 | admitted | `REQUEST_OVER_BOUND` |
| Reply body bytes | 16384 | interpreted | captured as metadata only, `UNKNOWN`, `RESPONSE_OVER_BOUND` |
| Saved record bytes | 4096 | written | `EvidenceOverBound`, nothing written |
| Content type characters | 128, printable ASCII | accepted | `UNKNOWN`, `MALFORMED_METADATA` |
| Specimens per profile | 32 | admitted | `OVER_CAP` |
| Status | integer 100 to 599 | accepted | `UNKNOWN`, `MALFORMED_METADATA` |

## Capture before interpretation

`<id>.capture.json` is written with `O_EXCL` before any JSON parse. It holds `specimen_id`, `profile`, `request_sha256`, `status`, `content_type`, `byte_count`, `raw_body_sha256`, `metadata_valid` and `captured_at`. If this write fails, the outcome is `UNKNOWN` with reason `CAPTURE_FAILED`, the stop marker is written when possible, and the specimen stays `INTENT_SAVED`.

The driver never saves or logs reply bodies, signed bytes, credentials, tokens, authorization signatures or unknown error strings. Exceptions from send or decode are reduced to fixed reason codes and are never re-raised, chained or printed. A success body stays in memory. The driver decodes it with the injected decoder, compares fields, and then saves only public decoded fields and `signed_bytes_sha256`. No memory-zeroization claim is made.

## Outcomes

The synthetic reply profile has `qualification = "SYNTHETIC"`. Constructing any other qualification raises `ProfileUnqualified`. Its error codes are invented for tests: `synthetic_policy_violation`, `synthetic_wallet_not_authorized`, `synthetic_invalid_field`, `synthetic_request_expired`. No actual Privy error profile is registered. The documented `policy_violation` name is context only.

| Outcome | Synthetic rule |
| --- | --- |
| `ALLOW` | Status 200, `application/json`, `data.signed_transaction` hex, decoder succeeds, and wallet, chain, nonce, type, `to`, data, value and every gas field equal the specimen. Hex-text fields compare as the bytes they encode, so letter case alone is not a mismatch. This is a local comparison of decoded bytes, not a provider normalization rule. |
| `POLICY_DENY` | Status 400 with code `synthetic_policy_violation`, and the profile positive control is `ALLOW`. |
| `AUTHORIZATION_DENY` | Status 403 with code `synthetic_wallet_not_authorized`. |
| `SCHEMA_REJECTED` | Status 400 with code `synthetic_invalid_field`. |
| `UNKNOWN` | Send raised, timeout, non-JSON, malformed JSON or envelope, generic 403, unknown code, malformed metadata, over-bound reply, capture failure, decode failure on an expected allow, or `synthetic_request_expired`. The last keeps the saved label `expiry_refusal` and is never policy denial. |
| `BREACH` | Any success envelope where the expectation is a denial, or a decoded signed result whose fields differ from the specimen. `BREACH` writes `STOP.json`. Every later specimen in every profile is refused. |

A `DIAGNOSTIC` specimen records `ALLOW` or `POLICY_DENY` without `BREACH`. It never substitutes for changed-byte denial.

## Coverage map

Tests are in `tests/privy_unfunded_proof/test_specimens_and_evidence.py`.

| Requirement | Test | Remaining actual input |
| --- | --- | --- |
| 1 Freeze before send, intent before callback | `test_intent_is_saved_before_send_and_request_is_frozen` | Actual transport adapter and authority |
| 1 No resend after reconstruction | `test_uncertain_specimen_refused_after_new_store_and_transport` | none |
| 1 Fresh process | `test_fresh_process_refuses_specimen_lost_after_intent` | none |
| 1 Concurrent claims | `test_second_claim_loses`, `test_concurrent_threads_send_once`, `test_concurrent_processes_send_once` | none |
| 1 Persistence failure before effect | `test_intent_persist_failure_makes_no_send` | none |
| 1 Callback failure | `test_send_failure_is_unknown_and_consumed` | none |
| 1 Torn or corrupt state | `test_corrupt_intent_is_uncertain` | none |
| 1 Duplicate claim | `test_terminal_specimen_refused` | none |
| 2 Admission | `test_table_admission_rejects_bad_tables`, `test_changed_request_bytes_refused`, `test_manifest_mismatch_refused` | Actual app, wallet IDs, destinations |
| 2 Bounds | `test_unknown_specimen_refused`, `test_request_bound_exact_and_overflow`, `test_reply_bound_exact_and_overflow`, `test_record_bound_exact_and_overflow`, `test_malformed_metadata_is_unknown`, `test_content_type_exact_bound_is_accepted` | Actual size ceilings |
| 3 Matrix and literal mutations | `test_matrix_ids_and_counts`, `test_baseline_request_is_literal`, `test_receiver_selector_variant`, `test_operation_and_timing_specimens_are_literal`, `test_case_diagnostics_keep_the_same_bytes`, `test_calldata_mutations_change_only_named_field`, `test_transaction_mutations_change_only_named_field`, `test_envelope_variants_declared_separately`, `test_trailing_word_stays_raw_challenge`, `test_decoded_profile_uses_alias_paths` | Actual policy, owners, values |
| 4 Type 4 | `test_type4_is_not_run_without_owner_authority` | Valid owner self-authorization |
| 5 Capture and redaction | `test_capture_saved_before_parse`, `test_canaries_absent_everywhere`, `test_capture_failure_is_unknown_and_stops` | none |
| 6 Classification | `test_generic_and_malformed_replies_are_unknown`, `test_synthetic_codes_classify`, `test_negative_refused_before_positive_control`, `test_profiles_do_not_gate_each_other`, `test_decoded_mismatch_is_breach`, `test_case_only_hex_difference_is_not_mismatch`, `test_decode_failure_on_expected_allow_is_unknown`, `test_stop_after_breach`, `test_personal_sign_success_is_breach`, `test_actual_profile_refused` | Observed provider error shape |
| Actual-run refusal and import safety | `test_actual_mode_refused`, `test_module_run_refused`, `test_import_makes_no_network_or_process_call` | none |

## Future actual inputs

Activation of any actual stage still needs the exact app and supported access route, never-funded probe wallets with builder-controlled owners, independently owned policies, the executor identity and override readback, process separation evidence, actual time and size ceilings, valid type-4 owner authority, an observed and reviewed provider denial format, and a transport adapter under its own lease. The historical uncertain policy POST and the stopped 403 GET stay unresolved and are not retried. Kuru deployed sources stay `NOT_REPRODUCIBLE`. None of these inputs is invented here.

Unresolved public-document conflicts are also future qualification inputs. Observed in rolling documents on 2026-10-16, not as measured API behavior:

- The Tempo guide lists `data` among standard Ethereum transaction policy fields. The create-policy OpenAPI defines the transaction condition field as only `to`, `value` and `chain_id`. Complete-data equality is a candidate that needs schema acceptance and actual positive and negative controls.
- The current policy overview says string comparisons are case-sensitive. The older accepted feasibility note describes case-insensitive signing hex and address comparisons. Neither is a verified current normalization rule. The case diagnostics record the observed result only.
- The `eth_sign7702Authorization` rule example does not prove rejection of an `authorization_list` inside `eth_signTransaction`. Tempo-only expiry and authorization fields do not establish Monad controls. Gas, type, fee and calldata enforcement stay `UNQUALIFIED`.
