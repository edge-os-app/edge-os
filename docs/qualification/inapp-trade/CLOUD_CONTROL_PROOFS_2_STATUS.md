# CLOUD-CONTROL-PROOFS-2 status

Task `CLOUD-CONTROL-PROOFS-2`, builder-approved normal cloud session, 2026-10-23 ("collect the proofs",
"industry standard please, I should not be blocking"). Repository `edge-os-app/edge-os`, branch
`cloud/control-proofs-2`, created from `cloud/control-proofs` at `229644d` (code reviewed PASS at `3cf11a4`).
Only `cloud/control-proofs-2` was pushed, with normal pushes. There was no main or integration push, no force
push, no PR and no merge. No network, provider, credential, key or VPS was used.

## Result

**Final reviewed SHA: `f9ecbc86e7e9edf50c80bb688742ea9dccbd437e`** (`f9ecbc8`). This status file is the only
commit after it, and it is documentation only.

Both new independent reviewers returned **PASS on the same commit `f9ecbc8`**:

| Review | Verdict at `f9ecbc8` |
| --- | --- |
| Spec (A, B and C met; the evidence proves what it claims) | PASS |
| Standards (no gain to an unpinned address can pass; no secret saved from Privy replies; re-run safety) | PASS |

Earlier round on `2053ea2`: spec PASS, standards FAIL. Both blocking findings were fixed in `f9ecbc8`:

1. **The same earlier store could be re-run more than once**, so a later clean re-run could hide one that
   signed or lost its reply. Fix: the re-run store is fixed at `<earlier store>.expiry-rerun`, and `--store` is
   refused. A second attempt finds that store and is refused. The proof builder now reads the re-run with
   `--with-expiry-rerun`, and rechecks that the earlier expiry capture still hashes to its record and shows a 401.
2. **Trace logs the check could not read were skipped instead of refused.** Examples: an upper-case or
   unprefixed topic, a log wrapped in a list, `topics` given as a dict, `logs` or `calls` given as a dict. A
   skipped log could hide a transfer to an unpinned address. Fix: any of these now refuses the trace. The
   Transfer topic is matched without regard to case.

Commits:
- `2053ea2`: both fixes, their tests and the plan;
- `f9ecbc8`: the standards-review fixes.

## Finding 1 (recipient): resolution

- **Pinned recipients.** `chain_proof.OBSERVED_FEE_RECIPIENTS_PPM` holds:
  - `0xe1c8b73343f5a83ebe165be90470d84b00e33022` at 10000 ppm of the input;
  - `0x681c3f796ae388026634c26025504d7c45248998` at 3500 ppm.

  The bounds are exactly the observed 0.1 and 0.035 WMON. The source named for them is the controller's live
  trace of 2026-10-23.
- **The pins cannot be justified from the repository.** Neither address and neither rate appears in the
  repository, and no nad.fun pair source or ABI is checked in. Both reviewers confirmed this independently.
  Therefore a trace that pays these recipients makes `recipient` **decision_required**
  (`FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND`). The artifact's `findings.fee_transfers` lists each recipient, its
  amount, its ppm bound and its raw bound. `findings.wmon_received_by_pool_raw` gives the pool's WMON gain.
- **Still refused:**
  - any other WMON or MOE gain;
  - a pinned recipient above its bound, counted as its net sum;
  - an MOE gain that is not exactly the output going to the wallet;
  - a wallet WMON change other than exactly minus the input;
  - any log the check cannot read.
- **Still ENFORCED:** a trace that pays only the pool.
- **No chain re-run is needed.** Rebuild the proofs from the saved chain store. One caveat: the stricter log
  parsing refuses a log with no topics, or with a topic that is not a 32-byte hex word. If the saved trace holds
  such a log, the rebuild returns `TRACE_TRANSFERS_INVALID` for that reason. That can only be checked on the
  controller's store.
- **Fee arithmetic.** The plan states the bound `f <= 0.2534%` on the kept 98.65%. The spec reviewer gave a
  simpler reading, added here after the reviewed commit: 0.2534% of the kept amount is exactly 0.25% of the
  gross input. So 1.00% + 0.35% + 0.25% = 1.60%, which is exactly the program fee of 16000 ppm. The plan's
  remark that a coarse search would round 15966 up to 16000 is therefore unnecessary. Neither reading is
  established: the LP fee, which contract pays the recipients, and whether the rates are fixed all need the
  pair source, or the reserves in the controller's store.

## Finding 2 (expiry): resolution

- **The capture now saves error fields.** For an error reply (status 400 or above, bounded JSON) the capture
  saves `error_code` and `error_type` next to `status` and `raw_body_sha256`. Each is kept only when it is letter
  words joined by underscores (at most 64 characters, 24 per word); otherwise it is null. Headers, messages,
  keys and signed bytes are never saved, and a reply below 400 is never parsed for the capture.
- **Which 401s count as expiry.** On the expiry row only, and after the positive-control check, a 401 whose code
  says the request or its authorization signature expired is `UNKNOWN` / `EXPIRY_REFUSAL`. Any other 401 stays
  `UNRECOGNIZED_REPLY` and stops the run.

### Exact one-row re-run command (the builder runs it once)

```sh
PRIVY_APP_ID=... PRIVY_APP_SECRET=... PRIVY_AGENT_KEY_FILE=<agent pem> \
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -B -s -m scripts.privy_unfunded_proof.actual_run \
  --packet control-proofs --confirm-unfunded --rerun-expiry-from <the 2026-10-23 privy store>
```

- **What it sends.** Only `raw.ctl_deny_expired_request`, into the new store
  `<the 2026-10-23 privy store>.expiry-rerun`. Do not pass `--store`. The earlier store is only read.
- **Before running.** First run the existing dry run:
  `actual_run --dry-run --packet control-proofs`. As before, `--confirm-unfunded` needs an independent
  zero-balance read of the wallet.
- **Where the code lands.** The capture `<store>.expiry-rerun/raw.ctl_deny_expired_request.capture.json` holds
  `status`, `error_code` and `error_type`.
- **Rebuilding the proofs.** Use the step 4 command in `CONTROL_PROOFS_PLAN.md` and add `--with-expiry-rerun`.
  The earlier store stays the `--privy-store`.
- **Same request and idempotency key.** The re-run sends the same request and the same idempotency key, so
  Privy may answer with its stored reply.
- **If it is still unresolved.** If the reply's code is not an expiry code, or the body carries only a message
  (so no code is saved), the row stays `UNRECOGNIZED_REPLY` and the run stops. The single re-run slot is then
  spent, and the next step is a builder decision.

## Files

| File | Change |
| --- | --- |
| `scripts/privy_unfunded_proof/chain_proof.py` | `OBSERVED_FEE_RECIPIENTS_PPM` (pinned, with source) |
| `scripts/privy_unfunded_proof/control_proofs.py` | Trace check accepts pinned fees within their bounds and refuses unreadable logs; `recipient` decision when fees are paid; re-run record validation; `merge_expiry_rerun`; `--with-expiry-rerun`; claim and limit texts |
| `scripts/privy_unfunded_proof/actual_profile.py` | `safe_reply_field`, `error_fields`, `is_expiry_refusal` |
| `scripts/privy_unfunded_proof/actual_runner.py` | Capture error fields; 401 expiry classification; `expiry_rerun_store`, `_check_rerun`, `rerun_of` |
| `scripts/privy_unfunded_proof/actual_run.py` | `--rerun-expiry-from` (expiry row only, derived store) |
| `docs/qualification/inapp-trade/CONTROL_PROOFS_PLAN.md` | Both findings, their resolution, the re-run and rebuild commands |
| `docs/qualification/privy-unfunded-proof/ACTUAL_RUNNER.md` | Capture fields and 401 rule |
| `tests/privy_unfunded_proof/test_control_proofs.py`, `_control_support.py` | Recorded live trace shape (`LIVE_FEE_PAYOUTS`), bound and bound+1, unpinned gains, unreadable logs |
| `tests/privy_unfunded_proof/test_control_proof_expiry_rerun.py` | New: 401 codes, capture secrecy, runner verdicts, one re-run per store, command, builder end to end |

Not touched: `actual_packet.py`, so the sealed packet and v3 hashes are unchanged. Also untouched:
`ACTUAL_PROOF_OPERATION_INPUTS.json`, `release.authored.json`, settings and registries.

## Test commands and counts (at `f9ecbc8`)

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -m pytest -q -p no:cacheprovider tests/privy_unfunded_proof
# 495 passed, 1 skipped (the existing skip that needs the private saved live result)
cd apps/api && .venv/bin/python -m pytest -q -p no:cacheprovider tests/execution/test_inapp_trade_release.py tests/operator_trade
# 231 passed, 1 skipped (existing lane-3 skip)
```

Lint was not run as a gate. The repository has no ruff configuration and the venv has no ruff. With default
rules, `uvx ruff` reports style-only items such as import order and unused `noqa`; the base branch already had
109 such items.

## Reviewer notes (non-blocking at `f9ecbc8`), for the builder

- **One re-run per path, not per content.** "One re-run per earlier store" is enforced by the store path. A copy
  of the earlier store in another directory would get its own re-run slot, and the builder could not tell the
  two apart. Preventing that needs an outside ledger.
- **A re-run store is not read unless asked.** Without `--with-expiry-rerun`, an existing `<store>.expiry-rerun`
  is ignored, and expiry stays unproven. With the flag, a BREACH in the re-run makes expiry unproven rather than
  refusing the build.
- **Ambiguous expiry codes.** `request_expiry_exceeded` and `expired_authorization` / `authorization_expired`
  are accepted as expiry codes; each is somewhat ambiguous. The saved code is in the capture, not in the
  `expiry_freshness` findings.
- **Letters-only secrets.** The identifier rule allows letters-only strings up to 64 characters, so a
  letters-only fragment of a secret could fit in theory. That is unlikely for a provider's error code.
- **Positive control age.** The positive control reused by the re-run has no age limit beyond its binding to
  the packet, policy id and policy hash.
- **Fail-closed bounds.** The fee bounds equal the observed amounts exactly, so a recipient paid 1 wei more is
  refused.
- **Capture shape for v3.** Future v3 captures also carry `error_code` / `error_type`, because the runner is
  shared. No validator checks capture keys.
- **Support artifact now written for fee traces.** The `opaque_program` support artifact is now written for
  fee-paying traces, with a limit line saying the recipients are observed, not sourced.

## Open items

1. **Builder:**
   - Run the one-row expiry re-run above.
   - Decide whether to accept `recipient` as decision_required with the observed fee recipients, or supply the
     nad.fun pair source or a fee read that would justify them.
   - The earlier decisions (controls 4, 8, 11, 12) are unchanged.
2. **Controller:**
   - Rebuild the proofs from the saved chain store and the Privy stores, using `--with-expiry-rerun` after the
     re-run.
   - Commit the raw stores with the artifacts.
3. **Adoption:** putting any proof hash into `release.authored.json` changes the release hash. That is a
   separate reviewed change.
