# CLOUD-CONTROL-PROOFS-3 status

Task `CLOUD-CONTROL-PROOFS-3`, builder-approved normal cloud session, 2026-10-26 (builder: "A, industry
standard"). Repository `edge-os-app/edge-os`. Branch `cloud/control-proofs-3` was created from
`cloud/control-proofs-2` at `82ebfdb`.

Only `cloud/control-proofs-3` was pushed, and only with normal pushes. There was no main or integration push,
no force push, no PR and no merge. No network, provider, credential, key or VPS was used.

## Result

**Final reviewed SHA: `d3cb31a8f397713272650305a4236591c0d5556f`** (`d3cb31a`). This status file is the only
commit after it, and it is documentation only.

Two new independent reviewers both returned **PASS on the same commit, `d3cb31a`**:

| Review | Verdict at `d3cb31a` |
| --- | --- |
| Spec: A, B and C met; every citation and claim proven by the repository | PASS |
| Standards: no case where Privy signed or the evidence is inconsistent can become decision_required; no secret saved; fail-closed; meaningful tests | PASS |

### Review history

Each round used two new reviewers.

| Round | Commit | Spec | Standards | Fixed in the next commit |
| --- | --- | --- | --- | --- |
| 1 | `93c8d3f` | FAIL | FAIL | A claim text said both expiry records cite the positive control (only the re-run does). `completed_at` was unchecked. `content_type_sha256` was not type-checked. |
| 2 | `3103e91` | FAIL | FAIL | One app-check test was described as showing more than it does. The earlier attempt could complete after the re-run reply. The capture-to-record hash had no test of its own. |
| 3 | `5dfa934` | PASS | FAIL | 21 of 59 guard mutations survived. Tests were added for record identity fields, wrong-type values and strict order. |
| 4 | `f3844ad` | PASS | FAIL | Attempt times were compared in milliseconds, but the runner's clock writes microseconds. |
| 5 | `d3cb31a` | PASS | PASS | (none) |

Two earlier commits are also part of the branch:
- `932e3fc` fixed the round-1 spec finding before the round-1 standards verdict arrived.
- In round 1 a reviewer reported "edits it did not make". These were the author's own fix for the round-1 spec finding, saved while the review ran; that fix is commit `932e3fc` and it is intact. From round 2 on, reviewers worked only in scratch copies.

## What changed

`expiry_freshness` is now **decision_required** with reason **`PRIVY_REFUSAL_REASON_NOT_READABLE`**, but only
when all of the following hold. The check is `control_proofs._Privy.refused_unreadably`.

1. **Both attempts are unrecognized 401s.** Both expiry attempts, the earlier one and its one re-run, ended
   `UNKNOWN` / `UNRECOGNIZED_REPLY` with `matches_expectation` false.
   - Each record has exactly the runner's error-reply keys, so neither can hold a signed hash or field reasons.
   - Each record names the sealed packet, policy id, policy hash, reply profile and request hash.
   - Each record's `completed_at` is a UTC time at or after its capture.
2. **The captures match.** Each capture has exactly the runner's capture keys and hashes to its record.
   - Each shows integer status 401, `application/json`, valid metadata, a hex content-type hash, a positive
     byte count, and null `error_code` and `error_type`.
   - Each was captured after the request's frozen expiry.
   - The two captures have the same body hash, byte count and content-type hash.
   - Times are compared in microseconds. The earlier capture comes strictly before the re-run capture, and the
     earlier attempt completed no later than the re-run capture.
   - The re-run capture file hashes to the re-run record.
3. **The positive control is valid** as before. The re-run's `rerun_of` cites the earlier record and the
   positive control by hash.
4. **The expired request differs from a fresh request only in its expiry.** `expiry_request_difference` checks
   this from the sealed packet.
   - The row's only frozen header is `privy-request-expiry: 1792000000000`, which is below the packet's
     `1796083200000`.
   - The transport sends the packet's expiry on every row without a frozen expiry.
   - The fresh twin was never sent.
   - Against the positive control, the transaction differs in `to`, `data` and `gas_limit`; the headers differ
     in the expiry and the idempotency key.

Every other shape stays `PRIVY_RECORD_INVALID`, as before. That includes:
- a signed reply, a 2xx, or a status other than 401;
- a readable code;
- differing body hashes;
- a missing or mismatched positive control;
- a failed `rerun_of` check.

A BREACH outcome still goes through the existing path. So does the recognized expiry-code path
(`EXPIRY_REFUSAL` → `PROVIDER_COVERS_SIGNING_CUTOFF_ONLY`); a reviewer confirmed its output is byte-identical
to the base.

**What the artifact carries:**
- the reply shape (401, media, byte count, body hash, null code and type);
- per attempt, the outcome record hash, capture hash and time;
- the positive control's record hash;
- the request difference;
- `app_expiry_checks`;
- its own claims and limits.

The limits state that Privy did not say why it refused, and that a 401 can also be an authorization failure.
They also state that the same key is the controller's statement, not shown in the records. The re-run reused
the idempotency key, so the second reply may be Privy's stored reply, and no fresh twin was sent.

**App expiry checks.** These are cited by path, line and test, and a test checks that each cited line still
returns its refusal:

| Refusal | Where |
| --- | --- |
| `REQUEST_EXPIRED` | `privy_signer.py:214`, checked at lines 153 and 183 |
| `INTENT_EXPIRED` | `original_transaction.py:603` |
| `INTENT_EXPIRED` | `original_transaction.py:753`; no test isolates it |
| `MANDATE_EXPIRED` | `original_transaction.py:755` |
| `EXECUTION_RELEASE_EXPIRED` | `operating_release.py:223`, with the call order at `provider_ports.py:730` → `operating_release.py:299` |
| `INTENT_EXPIRED` | `service.py:656` |

Each entry states only what its test shows.

## Files

| File | Change |
| --- | --- |
| `scripts/privy_unfunded_proof/control_proofs.py` | `EXPIRY_REASON_DECISION`, `APP_EXPIRY_CHECKS`, `_EXPIRY_UNREADABLE_CLAIMS` / `_LIMITS`, `_epoch_us`, `_Privy._unrecognized_401`, `_Privy.refused_unreadably`, `expiry_request_difference`, `load_expiry_captures`, the `privy_expiry_captures` argument, `main` reads both expiry captures with `--with-expiry-rerun`, `merge_expiry_rerun` refuses a non-object earlier capture |
| `tests/privy_unfunded_proof/test_control_proof_expiry_decision.py` | New. Covers the recorded shape, every refusing branch (about 90 changes), runner stores end to end, the command, and the app-check citations |
| `docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md` | Re-run result, the decision, the gate, the app-check table, control 11 and the rebuild note |

Not touched: `actual_packet.py`, so the sealed packet and its hashes are unchanged. Also not touched:
`release.authored.json`, settings and registries.

## Test commands and counts (at `d3cb31a`)

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -m pytest -q -p no:cacheprovider tests/privy_unfunded_proof
# 610 passed, 1 skipped (the existing skip that needs the private saved live result)
cd apps/api && .venv/bin/python -m pytest -q -p no:cacheprovider \
  "tests/execution/test_privy_signer.py::test_a_stop_before_authorization_sends_nothing" \
  "tests/execution/test_privy_signer.py::test_a_stop_that_arrives_during_authorization_sends_nothing" \
  "tests/execution/test_privy_signer.py::test_a_stop_before_authorization_never_reaches_the_key" \
  "tests/execution/test_privy_signer.py::test_a_stop_during_signing_sends_nothing_and_keeps_the_original_expiry" \
  "tests/execution/test_approve_swap_revoke.py::test_existing_refusals_still_precede_the_steps" \
  "tests/execution/test_saved_attempt_signing.py::test_mandate_expiry_during_quote_preserves_exact_refusal" \
  "tests/execution/test_operating_release.py::test_signer_request_expiry_is_enforced_before_release_expiry"
# 19 passed
```

Two tests could not run here, because they need Docker Postgres:
- `tests/test_original_transaction_journey.py::test_an_authority_change_during_a_stage_save_allows_no_next_effect[SIGN_REQUESTED-expiry-expected0]`
- `tests/execution/test_revalidation.py::test_expired_intent_denies_before_submission`

Both reviewers read them and confirmed that each asserts what its citation claims.

The `apps/api` venv was created with `uv sync --frozen`. Lint was not run as a gate; the repository has no
ruff configuration.

## Rebuild command (controller)

```sh
PYTHONPATH=apps/api/src:. <venv>/bin/python -B -s -m scripts.privy_unfunded_proof.control_proofs \
  --authored docs/qualification/inapp-trade/release.authored.json \
  --privy-store <the 2026-10-23 privy store> --chain-store <the chain store> \
  --with-expiry-rerun --out <new proofs dir>
```

Keep the earlier store as `--privy-store`. The builder reads `<the 2026-10-23 privy store>.expiry-rerun` and the
expiry capture in both stores. With the recorded re-run, `expiry_freshness` is printed under `decision_required`
with `PRIVY_REFUSAL_REASON_NOT_READABLE`. Two outcomes need a closer look:
- If the build instead prints `PRIVY_RECORD_INVALID`, a gate condition fails on the real stores. Check the
  capture keys and times first: the fakes follow the runner's shapes, but the live stores have not been seen
  here.
- If it prints `INPUT_UNREADABLE`, a capture file could not be read.

## Reviewer notes (non-blocking at `d3cb31a`), for the builder

- **The positive control's time is not checked.** Its `completed_at` is not compared with the expiry attempts.
  The positive control is bound only by the re-run's hash citation and its existing checks, so "after the
  positive control signed" rests on the citation, not on times.
- **Test gaps found by mutation, not code bugs:**
  - a record completing 1 µs before its own capture, and the earlier attempt completing 1 µs after the re-run
    capture (the tests use gaps of 100-800 µs);
  - a `captured_at` with 7 fraction digits;
  - an `error_code` of `""`. This is refused today, because the check is `is None`.
- **Equivalent survivors**, which both reviewers judged harmless:
  - the record `reason` check (also enforced by the dispatch and by `_rerun_valid`);
  - the record capture-hash type and hex checks (implied by hash equality);
  - the body-hash type check (a non-string raises, and `main` reports it as INPUT_UNREADABLE);
  - the `is False` dispatch;
  - the dispatch's `"rerun_of" in record`.
- **Library-only failure.** Called directly, `build_control_proofs` raises `TypeError` rather than returning
  unproven for a non-mapping `privy_expiry_captures`, or for a capture value JSON cannot encode. `main` always
  passes dicts read from JSON.
- **No upper time bound.** Times have no upper bound; the builder has no clock. `T24:00:00` is accepted as ISO
  8601.
- **The re-run limit depends on the store path.** The builder cannot tell a copy of the earlier store from the
  original. "One re-run" is enforced by the runner's store path (as noted in CLOUD_CONTROL_PROOFS_2_STATUS).

## Open items

1. **Builder:** decide whether to adopt the `expiry_freshness` decision artifact. The `recipient` decision and
   the earlier decisions (controls 4, 8, 11 and 12) are unchanged.
2. **Controller:** rebuild the proofs with the command above, and commit the raw stores with the artifacts.
3. **Adoption:** putting any proof hash into `release.authored.json` changes the release hash. That is a
   separate reviewed change.
