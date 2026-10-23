# In-app WMON -> MOE execution release for the builder's agent wallet

Task `CLOUD-A2`, builder-approved 2026-10-22. Base `9621433ef52c74c3288e1c994bc6624e8b4b62ec`. Status: **authored,
not registered.** This document and its files grant no trade authority. No network, provider, signer or
credential was used to write them. Builder decision: in-app trading option A. Only the builder trades: first on the
local app, later on the public site.

## Files

| File | Role |
| --- | --- |
| [`release.authored.json`](release.authored.json) | The one release (`actual-inapp-wmon-moe-20261022/1`), its authoring facts and `{"$fill": name}` markers for values that need a recorded read or a later lane. |
| `apps/api/src/edge_os_api/execution/inapp_trade_release.py` | A pure completion step. It checks the fill, the gas rule and the USD ceiling, computes the minimum output, builds the `OperatingRelease` and the `BoundRelease`, and prints the exact registry lines. |
| `apps/api/tests/execution/test_inapp_trade_release.py` | Tests for the authored file and the completion step. |

`operating_release.py` is unchanged. `APPROVED_ACTUAL_RELEASES` and `APPROVED_ACTUAL_BINDINGS` stay empty.

## What the release fixes

| Field | Value | Source |
| --- | --- | --- |
| Chain | `143` (Monad mainnet) | Task facts |
| Wallet | id `bsb2feecuxl81dl5jz4u9xxo`, address `0x91BB52A63c91986813288965e4681FF111De1b63`; also the recipient | Task facts; `scripts/privy_unfunded_proof/actual_packet.py` |
| Signer | key quorum `zu1qjdfqlbcq1ct7sdxendgg` | Same |
| Policy | `c30racyru6duaipj815cvjce`, owner `a5gwmgrsn6903ac09lphyv9a` (held only by the builder), normalized rules SHA-256 `61860d20…0892b` | Same |
| Route | `executeSwap` (`0xce1e7030`) on entrypoint `0xb3e6778480b2E488385E8205eA05E20060B813cb` | Task facts |
| Pair | sell WMON `0x3bd3…433a`, buy MOE `0xd8e0…7777`, 18 decimals each | Task facts; MOE decimals from Probe A (`qualified-actual-demo/QUALIFICATION_GAPS.md`) |
| Quote | `DIRECT_V2_PROGRAM`, pool `0x9719…5aad`, token0 WMON, token1 MOE, direction `0`, program fee `16000` ppm, slippage `100` bps | Task facts |
| Program | `0x023bd3…3e80`, built by the merged `build_program_hex` | Code |
| Input | `10000000000000000000` (10 WMON), allowance the same, value `0` | Authoring choice (see the USD section) |
| Fees | all zero, `is_in_token_fee` false (what `build_calldata_hex` encodes) | Code |
| Deployment | source commit `70bc0c93c073f78697b99848eedefbf5dbe698c7`, entrypoint code `da214086…e1cf`, router `0x2f84fb8982073f39ba47c7fcc29119af074abbcb` with code `9cf6f5c8…c649` | `kuru-deployed-source/SOURCE_IDENTITY.md` (read at block `0x6c1db44`, 2026-10-14) |
| Gas | swap `gas_limit` `700000`, `max_fee_per_gas` `202000000000` (202 gwei), priority `2000000000`, `budget_raw` `141400000000000000` | Task gas rule; fee = 2 x the 100-gwei minimum base fee + 2-gwei priority (`controlled-action-feasibility`, M-GAS; operator rule `2 * base_fee + priority_fee`) |
| Limits | actions, attempts, broadcasts, quote requests and signer requests `1`; observer requests `20`; 4096/16384 bytes; 60 s deadline | The module requires the five `1`s. The other values are authoring choices. |
| Freshness | quote age 30 s, input age 60 s | Authoring choice (same as the accepted synthetic release) |

The WMON and pool code hashes (`1ba3ee06…d187`, `aae0c275…644d`) have no field in the release schema. They are kept
in the authored `facts` for the operator dry run. The step gas limits (wrap `60000`, approve `70000`, swap `700000`,
revoke `70000`) are also kept there.

### `independent_proof_sha256`

The value is the sealed packet SHA-256 `8255d003097fd1a0216a6b64c48637f2ef745c7ebbe73035d0b8929403500528`. The
document file hash is not used. Reasons:

- The packet hash is the identity that the live 19/19 run is bound to. Every row's request hash and idempotency
  key comes from it.
- Code recomputes it. `actual_packet.CODE_OWNED_PACKET_APPROVALS` admits the packet only when its recomputed id
  equals `SEALED_PACKET_SHA256`. A test checks that the release carries that exact value.
- A document file hash changes with any wording edit.

The packet hash is the proof input, not the provider outcome. The builder reported the 19/19 v3 live result on
2026-10-22, but the repository does not record it yet. `UNFUNDED_POLICY_PACKET.md` still says "pending". The four
policy-owned controls therefore cite the packet hash with evidence class `LOCAL_TESTED`, which is the packet's recorded
status. They are not marked `PROVIDER_ACTUAL`. They can move to `PROVIDER_ACTUAL` only after the v3 result is recorded
in the repository (pending step 1 below), with that recorded result's hash as their proof.

## USD ceiling arithmetic (including gas)

Monad charges the full gas limit. The worst case therefore counts the full limit of every step. It includes the
wrap, which a WMON start does not run.

```text
gas      = (60000 + 70000 + 700000 + 70000) x 202 gwei = 900000 x 202e9 wei = 0.1818 MON
input    = 10 WMON                                                        = 10.0000 MON
worst    = 10.1818 MON
at the documented MON price 0.02 USD (operator-trade/trade.example.json, an unapproved example; it agrees with
the M-GAS figure, where 0.02 MON is about USD 0.0005, so MON is about USD 0.025):
worst    = 10.1818 x 0.02 = USD 0.203636  <=  USD 2.00
```

The ceiling is still met at any MON price up to `2.00 / 10.1818 = USD 0.19643`. `complete_release` refuses
`USD_CEILING_EXCEEDED` above the ceiling. It also refuses a ceiling above `2.00`. The builder must confirm the current
MON price before the run. If the price is above 0.1964, the input must become smaller, and the release gets a new
hash.

The 10 WMON input is within the Privy R2 approve cap of 70 WMON. A MON start is not possible today. Its wrap value
(10 MON = `10**19` wei) is above `2**53-1`, so the installed `PrivySignerClient` refuses it (see
`operator-trade/OPERATOR_TRADE.md`). The release therefore assumes a WMON start.

## Gas rule

The rule is `gas_limit >= ceil(eth_estimateGas x 1.2)`, computed in integers as `(estimate x 6 + 4) // 5`.

- `complete_release` applies the rule to every active step (approve, swap, revoke). It uses the controller's
  recorded dry-run estimates in the fill.
- It also applies the rule to the swap limit against the recorded live estimate `544967`. That estimate needs at
  least `653961`, so the authored `700000` passes. The failed 2026-10-22 limit `400000` is refused.
- The release's `gas.gas_limit` must equal the authored swap step limit.
- `operating_release.py` itself does not read gas estimates. At run time the app's path signs the release's fixed
  `gas_limit` and does not estimate gas again. The check therefore runs once, on the recorded estimate, when the
  release is completed. A state change after that read is not covered (the same limit as in `OPERATOR_TRADE.md`).

## Controls: honest states, and why the release cannot be admitted yet

`check_release` admits an ACTUAL release only if each of its 12 controls is `ENFORCED`, carries evidence class
`PROVIDER_ACTUAL` and has a proof hash. This release keeps the states that the repository records. No control is
relaxed, and no control claims a provider proof that the repository does not hold. A test checks that.

| # | Control | State / evidence | Proof |
| --- | --- | --- | --- |
| 1 | `chain` | `ENFORCED` / `LOCAL_TESTED` | packet `8255d003…` (proof input) |
| 2 | `wallet_signer_binding` | `ENFORCED` / `LOCAL_TESTED` | packet (proof input) |
| 3 | `entrypoint_method` | `ENFORCED` / `LOCAL_TESTED` | packet (proof input) |
| 4 | `input_output_assets` | `UNKNOWN` / `NOT_RUN` | none |
| 5 | `raw_input` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 6 | `recipient` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 7 | `minimum_output` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 8 | `fees` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 9 | `approvals` | `ENFORCED` / `LOCAL_TESTED` | packet (proof input) |
| 10 | `gas_action_capacity` | `UNSET` / `NOT_RUN` | none |
| 11 | `expiry_freshness` | `ENFORCED` / `DOCUMENTED` | none |
| 12 | `opaque_program` | `UNKNOWN` / `NOT_RUN` | none |

Even with the registry lines added, this release is refused with `EXECUTION_CONTROL_UNQUALIFIED`. All 12 controls
need a recorded provider-actual proof first: controls 1-3 and 9 from the recorded v3 live result, and controls 4-8 and
10-12 from new evidence. Each needs a new proof artifact, which changes the release
hash. A test shows the exact refusal. Another test shows that a copy with every control proven, plus the registry
entry, admits its exact hash and refuses any changed control. That copy is a hypothetical in the test only. It is not
in the authored file.

## Pending builder and controller steps, in order

1. **Record the v3 live result (controller).** Commit the 19/19 v3 result store, or its summary hash bound to packet
   `8255d003…`, and update `UNFUNDED_POLICY_PACKET.md`. Then set controls 1-3 and 9 to `PROVIDER_ACTUAL` with that
   recorded hash.
2. **Control evidence (builder decision).** Produce provider-actual proof for controls 4-8 and 10-12, or decide
   otherwise. The module rule cannot be met without one of these. A decision to change the rule is a product decision
   and a separate reviewed change. It is not part of this task.
3. **Dry run (controller).** Run the operator dry run with `"start": "WMON"`, `input_raw`
   `10000000000000000000` and the authored step limits. Record the pool reserves with their block, and record the
   estimate for each of approve, swap and revoke.
4. **Fill (controller).** Write `docs/qualification/inapp-trade/release.fill.json` with exactly these keys:

   | Key | Value |
   | --- | --- |
   | `reserves` | `{"block_number": <int>, "reserve_wmon": "<raw>", "reserve_moe": "<raw>"}` from step 3 |
   | `gas_estimates` | `{"approve": <int>, "swap": <int>, "revoke": <int>}` from step 3 |
   | `quote_endpoint`, `broadcast_endpoint`, `observer_endpoint` | Keyless `https://<host>/rpc` URLs for the `/rpc` relay. Two different endpoints are required for broadcast and observer. The relay belongs to another lane. |
   | `valid_until` | The signing cutoff (RFC 3339 UTC). It is also used as the intent and signer-request expiry. |
   | `mandate_expires_at` | Not before `valid_until`. |
   | `abi_sha256` | SHA-256 of the pinned entrypoint ABI, recorded by the controller |
   | `mutable_router_proof_sha256` | SHA-256 of a current `getRouter()` read proving that the router is still `0x2f84…bbcb` with code `9cf6f5c8…` |

   The minimum output is never supplied by hand. It is computed as
   `floor(floor(x * 984000 * R_moe / (R_wmon * 10**6 + x * 984000)) * 9900 / 10000)`, which is the quote client's own
   floor. **Expect a refusal on an active pool.** Before signing there is no tolerance against the recorded read.
   If the pool moves even one unit against the trade after that read, the app's quote is refused
   (`QUOTE_SLIPPAGE_EXCEEDED`) before signing. The 100 bps protects only on-chain execution. The time between the
   read and the run covers the fill, the hash, approval and the registry commit, so this is the likely outcome. A new
   read then needs a new fill and a new hash. A builder decision could add an explicit tolerance against the
   recorded read. That would be a separate reviewed change, because the quote client compares the live floor with
   the release minimum.
5. **Sign-in (builder).** Sign in to the local app. Confirm the agent wallet `bsb2feecuxl81dl5jz4u9xxo`, publish
   the MOE strategy revision and adopt the `connected-one-action/1` consent. `owner_id`, `agent_id` and
   `consent_adoption_id` exist only after this step. No value is authored for them.
6. **Identity (controller).** Read the identity from the builder's saved records with the same derivation that the
   worker compares:

   ```sh
   cd apps/api && .venv/bin/python - <<'PY'
   import json, os, uuid
   from edge_os_api.core.database import make_engine, make_session_factory
   from edge_os_api.execution import inapp_trade_release as inapp
   authored = json.load(open("../../docs/qualification/inapp-trade/release.authored.json"))
   release = inapp.complete_release(authored, json.load(open("../../docs/qualification/inapp-trade/release.fill.json")))
   with make_session_factory(make_engine(os.environ["EDGE_OS_DATABASE_URL"]))() as session:
       print(json.dumps(inapp.saved_identity_for_release(
           session, uuid.UUID(os.environ["BUILDER_OWNER_ID"]), os.environ["BUILDER_AGENT_ID"], release), indent=2))
   PY
   ```

   It refuses `SAVED_IDENTITY_UNAVAILABLE` until the agent is confirmed and the consent is adopted. It refuses
   `SAVED_IDENTITY_WALLET_MISMATCH` for any wallet other than the release wallet. The comparison is exact and
   case-sensitive, as `BoundRelease` requires. A saved address stored in a different letter case also refuses. That
   is fail-safe, but the stored case has not been checked yet. Put the printed object under
   `identity` in `docs/qualification/inapp-trade/binding.fill.json`. Add the six proof keys and `market_profile`.
   `position_inventory`, `market` and `finality` are required. `derive_approval` also requires `exit_capacity`,
   `valuation` and `cost_model`. Market observation requires `market_profile`. None of these proofs exists yet.
7. **Hashes (controller).**

   ```sh
   cd apps/api && .venv/bin/python -m edge_os_api.execution.inapp_trade_release \
     --authored ../../docs/qualification/inapp-trade/release.authored.json \
     --fill ../../docs/qualification/inapp-trade/release.fill.json \
     --binding-fill ../../docs/qualification/inapp-trade/binding.fill.json
   ```

   The command prints `release_sha256`, `binding_sha256`, `unqualified_controls` and the two `registry_lines`. It
   makes no request.
8. **Registration (builder approval of both exact hashes).** Replace `operating_release.py` lines 20-21 with the
   two printed lines:

   ```python
   APPROVED_ACTUAL_RELEASES: Mapping[str, str] = MappingProxyType({"actual-inapp-wmon-moe-20261022/1": "<RELEASE_SHA256>"})
   APPROVED_ACTUAL_BINDINGS: Mapping[str, str] = MappingProxyType({"<BINDING_SHA256>": "<RELEASE_SHA256>"})
   ```

   In the same change, replace the empty-registry assertion in
   `test_completed_release_validates_with_a_stable_hash_and_refuses_while_unregistered` with this test:

   ```python
   FILL = AUTHORED_PATH.with_name("release.fill.json")
   BINDING_FILL = AUTHORED_PATH.with_name("binding.fill.json")

   def test_registry_carries_exactly_the_approved_inapp_release_and_binding():
       release = inapp.complete_release(authored(), json.loads(FILL.read_text(encoding="utf-8")))
       bound = inapp.bind_release(release, json.loads(BINDING_FILL.read_text(encoding="utf-8")))
       assert release_sha256(release) == "<RELEASE_SHA256>" and bound.sha256 == "<BINDING_SHA256>"
       assert operating_release.APPROVED_ACTUAL_RELEASES == {"actual-inapp-wmon-moe-20261022/1": "<RELEASE_SHA256>"}
       assert operating_release.APPROVED_ACTUAL_BINDINGS == {"<BINDING_SHA256>": "<RELEASE_SHA256>"}
       assert check_release(release, expected_sha256="<RELEASE_SHA256>", now=<a time before valid_until>) == "<RELEASE_SHA256>"
   ```

   The last assertion passes only after steps 1 and 2.

## Worker execution runtime settings

`CLOUD-A4a` adds `apps/api/src/edge_os_api/execution/released_execution_bootstrap.py`. Only the worker process
(`python -m edge_os_api.execution.worker`) calls it, and only in `EDGE_OS_EXECUTION_MODE=controlled`. The API
process never calls it. A call with `role="api"` refuses before it reads a setting, file or key, so the API
never receives a signer.

The settings are worker-only environment values. They are not `Settings` fields, so the API configuration
cannot carry them and `load_settings` ignores them:

| Setting | Required form |
| --- | --- |
| `EDGE_OS_EXECUTION_PRIVY_APP_ID` | 1-128 characters of `[A-Za-z0-9_-]` |
| `EDGE_OS_EXECUTION_PRIVY_APP_SECRET` | non-empty printable ASCII without spaces |
| `EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH` | absolute path to a regular file, owned by the worker's user, with no group or other permission bits; it holds a PEM P-256 private key |
| `EDGE_OS_EXECUTION_SERVER_WALLET_ID` | 1-128 characters of `[A-Za-z0-9_-]`; must equal the binding's `wallet_id` |
| `EDGE_OS_EXECUTION_MONAD_RPC_URL` | `https` URL with a host, no user-info and no fragment |

`EDGE_OS_EXECUTION_MONAD_RPC_URL` is read and validated so a worker without a chain endpoint refuses at startup.
The approved release keeps its own broadcast and observer endpoints, so this value is not written into a request.
Worker egress and health checks that use it belong to the A4b hosted gate.

The worker builds one runtime only when code-owned candidate objects exist for an exact release hash in
`APPROVED_ACTUAL_RELEASES` and an exact binding hash in `APPROVED_ACTUAL_BINDINGS`. The candidate list is
`released_execution_bootstrap.RELEASE_CANDIDATES` and is empty at this ticket. Registration is a reviewed code
change with the two registry lines. The module never writes either registry and never builds a runtime from an
environment value alone. `CONTROLLED_RUNTIMES` in `core.provider_ports` stays empty; the worker passes the one
runtime to the existing ports factory.

The binding must name the configured server wallet and the release wallet, and the release must use the
`DIRECT_V2_PROGRAM` quote, because no worker setting carries a Kuru quote token. When a caller supplies the
saved `owner_id`, `agent_id` and `consent_adoption_id`, the bootstrap also refuses a mismatch. At run time the
runtime compares the request's owner, agent and consent with the binding on every quote, holdings read, market
observation, attempt begin and signer call.

`env` other than `local` is refused in this ticket. Production stays behind the cloud hosted-record-v2 gate.

### Refusal reasons

Every refusal is `ExecutionBootstrapRefused` with one stable code. No message repeats a setting value, path or
key material.

| Code | Meaning |
| --- | --- |
| `EXECUTION_BOOTSTRAP_ROLE_NOT_WORKER` | The caller is the API or another non-worker role. |
| `EXECUTION_BOOTSTRAP_ENV_NOT_LOCAL` | `settings.env` is not `local`. |
| `EXECUTION_BOOTSTRAP_APP_ID_MISSING` / `_INVALID` | The Privy app id is absent, blank or malformed. |
| `EXECUTION_BOOTSTRAP_APP_SECRET_MISSING` / `_INVALID` | The app secret is absent, blank or not printable ASCII without spaces. |
| `EXECUTION_BOOTSTRAP_KEY_PATH_MISSING` / `_INVALID` | The key path is absent, blank, relative, too long or contains NUL. |
| `EXECUTION_BOOTSTRAP_WALLET_ID_MISSING` / `_INVALID` | The server wallet id is absent, blank or malformed. |
| `EXECUTION_BOOTSTRAP_RPC_URL_MISSING` / `_INVALID` | The Monad RPC URL is absent, blank or not the accepted `https` form. |
| `EXECUTION_BOOTSTRAP_KEY_FILE_UNREADABLE` | The key path is missing, not a regular file or unreadable. |
| `EXECUTION_BOOTSTRAP_KEY_FILE_NOT_OWNED` | The key file is owned by another user. |
| `EXECUTION_BOOTSTRAP_KEY_FILE_NOT_OWNER_ONLY` | Group or other permission bits are set. |
| `EXECUTION_BOOTSTRAP_KEY_INVALID` | The file is not a loadable PEM P-256 private key. |
| `EXECUTION_BOOTSTRAP_APPROVAL_SEAM_INCOMPLETE` | Only one synthetic approval map was supplied. |
| `EXECUTION_RELEASE_NOT_APPROVED` | No candidate matches an approved release id and exact hash. An empty registry gives this code. |
| `EXECUTION_BINDING_NOT_APPROVED` | The binding hash is absent from the approved registry. |
| `EXECUTION_BOOTSTRAP_MULTIPLE_RELEASES` | More than one candidate is admitted; a worker composes at most one. |
| `EXECUTION_BOOTSTRAP_IDENTITY_MISMATCH` | A supplied saved owner, agent or consent differs from the binding. |
| `EXECUTION_BOOTSTRAP_WALLET_MISMATCH` | The binding wallet, the configured server wallet and the release wallet do not agree. |
| `EXECUTION_BOOTSTRAP_QUOTE_TOKEN_UNAVAILABLE` | The release needs a Kuru quote token and no worker setting carries one. |
| `EXECUTION_RELEASE_HASH_MISMATCH`, `ACTUAL_EXECUTION_RELEASE_NOT_APPROVED`, `EXECUTION_RELEASE_EXPIRED`, `EXECUTION_CONTROL_UNQUALIFIED`, `ACTUAL_EXECUTION_BINDING_NOT_APPROVED`, `EXECUTION_BINDING_MISMATCH` | The binding's own admission refused with its existing code. |

## What else must exist before the app can run the action

These items are outside this task and are owned by other lanes:

- The `/rpc` relay behind the three endpoints.
- The worker and runtime wiring for the approve, swap and revoke steps. The transaction seam now runs them (see
  "In-app approve, swap and revoke" below), but no mounted runtime passes a step plan yet.
- The signer change for quantities above `2**53-1`, but only if a MON start is wanted.

## In-app approve, swap and revoke (`CLOUD-A6`)

Task `CLOUD-A6`, builder-approved 2026-10-23 (in-app trading T5 option 2). Base
`82290e203982ee710189c4d983edce9a4ddfba9f`. This section describes the transaction seam only. It grants no trade
authority and changes no release hash.

### What the release names

The authored `facts` name `start` `WMON`, `active_steps` `["approve", "swap", "revoke"]` and the step gas limits wrap
`60000`, approve `70000`, swap `700000`, revoke `70000`. `TradeSteps.from_authored` reads exactly these facts. It
uses the module's own checks (`worst_case_usd`), so any other start, order, gas margin or ceiling is refused. The
spender is the route's entrypoint `0xb3e6…13cb`, the contract that the swap calls. Policy rule R2 ("approve to the
Kuru Flow entrypoint") and the operator path (`OPERATOR_TRADE.md`) use the same spender. The
`deployment.router_address` is never approved.

### Order and journal

With a step plan, `OriginalTransactionTransport.submit_original` runs one action as follows:

1. Checks before step 1. The existing release, route, network and expiry refusals run first. Then the input must be
   the release's 18-decimal WMON start (`STEP_INPUT_NOT_RELEASE_START`), because the ceiling values its raw amount
   1:1 as MON wei. The swap gas limit must equal the route's (`STEP_GAS_MISMATCH`). The total of the approve, swap and revoke limits at the fixed
   maximum fee must fit the approved gas reservation (`FEE_EXCEEDS_GAS_RESERVATION`). The input plus the full limit
   of all four release steps at that fee, at the release MON price, must not exceed the USD ceiling
   (`USD_CEILING_EXCEEDED`). This is the release's own ceiling arithmetic above, and it includes the wrap.
2. One route quote and one pending-nonce read `N`. The approve and the swap are prepared and saved (`PREPARED`,
   `APPROVE_PREPARED`) before any signature.
3. Approve: `approve(entrypoint, input_raw)` on the input token, nonce `N`, value 0, gas `70000`.
4. Swap: the unchanged single-swap transaction, nonce `N+1`.
5. Revoke: `approve(entrypoint, 0)`, gas `70000`. It uses nonce `N+2` after the swap's own hash was returned. It uses
   nonce `N+1` after a definite swap refusal, because the swap's nonce is then unused.

Each step goes through the single-swap stages once: sign request saved, recheck, signer, validation of the signed
bytes, `SIGNED`, `BROADCAST_REQUESTED`, recheck, one `eth_sendRawTransaction`. The approve and the swap use the
full single-swap recheck: release admission, stop controls, quote and input age, and intent and mandate expiry. The
revoke only lowers the allowance to zero. Its recheck therefore keeps the release admission but skips the stops and
the expiries. A stop that refused the swap must not leave the approve open. A failed save of any step stage stops
the action before its next call. The approve and revoke save each stage
in their own record (`approve`, `revoke`; journal stages `APPROVE_*`, `REVOKE_*`). The swap keeps the single-swap
envelope at the top level, plus a `swap` record, so `qualify_original` still verifies it. Its receipt does not settle
the action (see "Outcomes and recovery"). The approve and revoke sign with their own request ids, `<attempt_id>:approve` and `<attempt_id>:revoke`.
A Privy policy denial on any step maps to `WALLET_POLICY_REFUSED` through the existing `SignerPolicyDenied` path.
The top-level `reason`, which the action view shows as a definite refusal, is written only when nothing of the
action was sent. A policy-refused approve therefore shows "Refused by the wallet policy.". A refused swap or revoke
keeps its reason in its own record.

### Outcomes and recovery

| Case | Action outcome | Revoke | Allowance (`recovery.allowance.allowance_status`) |
| --- | --- | --- | --- |
| Refused before step 1, or the approve definitely refused | `DEFINITELY_UNSENT` (`APPROVE:<reason>` for the approve) | none | `NOT_APPROVED`, not open |
| Approve unknown (signing or broadcast unknown, error, mismatch, stop after signing, save failure after signing) | `SUBMISSION_POSSIBLE` | `NOT_ATTEMPTED` | `APPROVE_UNKNOWN`, open |
| Swap unknown | `SUBMISSION_POSSIBLE` | `NOT_ATTEMPTED` | `REVOKE_NOT_SENT`, open |
| Swap hash returned, or swap definitely refused (`SWAP:<reason>`, including a stop or an expiry) | `SUBMISSION_POSSIBLE` (the approve was sent) | signed and sent once, unless its release admission refuses it or a save fails | see below |
| Revoke refused or not saved | same | `REFUSED_UNSENT` / `PREPARED` | `REVOKE_NOT_SENT`, open |
| Revoke unknown | same | unknown stage | `REVOKE_UNKNOWN`, open |
| Revoke hash returned | same | `BROADCAST_RETURNED` | `REVOKE_UNCONFIRMED`, open until `read_revoke_receipt` reads its bound status-1 receipt (`CLOSED`) |

No step is resent. The transport refuses a second run with `ACTION_ALREADY_STARTED`. That refusal is
`SUBMISSION_POSSIBLE`, not `DEFINITELY_UNSENT`: the first run of the same action may have sent steps, so its
reservations must not be released. After a crash, the saved attempt
keeps the action's claim, and a later tick makes no call. The recovery case view (`RecoveryCaseView.allowance`)
and the owner projection (`allowance`) report the allowance from the saved records. Liability follows the existing
rule: after the approve was sent, the action stays `SUBMISSION_POSSIBLE`. `read_original_receipt` does not settle an
envelope with `steps`. It returns `SUBMISSION_UNKNOWN` without a read, because the swap receipt carries neither the
approve and revoke gas nor the allowance. A step action therefore stays unknown, with its reservations held, until
a step-aware reading exists or an operator resolves it.

### Not done here (other lanes or a builder decision)

- **Wiring.** `worker.py` and `ControlledRuntime.clients` (`provider_ports.py`) do not pass a step plan yet. The
  mounted path still runs the single swap. The mounted clients would also refuse the steps as they stand. The
  signer requires the top-level stage `SIGN_REQUESTED`, but the approve saves `APPROVE_SIGN_REQUESTED`.
  `original_bytes()` reads the swap's top-level signed bytes. Each approve would end as `SIGNING_UNKNOWN`, with
  its liability kept, and nothing would be signed.
- **Gas reservation.** The worker sets the action's gas cap from the release's `gas.budget_raw`, which is
  `141400000000000000` (the swap alone, 700000 x 202 gwei). Approve, swap and revoke need 840000 x 202 gwei =
  `169680000000000000`. With this release the step path therefore refuses `FEE_EXCEEDS_GAS_RESERVATION` before
  step 1. A release with a larger budget, and a new hash, is needed first.
- **Step-aware settlement.** Settling a step action needs bound receipts for every sent step, with the gas of every
  step charged. It is not built yet. Until then these actions stay unknown (see above).
- **Release limits.** The release fixes `signer_requests` `1` and `broadcasts` `1`, and `operating_release.py`
  requires those values. The mounted signer and broadcast clients also allow one request each. One action with three
  steps makes three signer requests and three broadcasts. Before a runtime can mount this path, the builder must
  decide whether these limits count per step, or change the release rule. Either choice is a reviewed change and
  produces a new release hash.
- **Revoke confirmation.** `read_revoke_receipt` exists, but no worker path calls it yet. The recovery view
  therefore reports a sent revoke as `REVOKE_UNCONFIRMED` (open).
- **Ceiling price.** The USD check uses the release's documented MON price (`0.02`, an unapproved example). The
  builder still confirms the current price before the run (see above).

## Checks

```sh
cd apps/api && .venv/bin/python -m pytest -q tests/execution/test_inapp_trade_release.py \
  tests/execution/test_approve_swap_revoke.py tests/recovery/test_approve_swap_revoke_recovery.py
```

The recovery test needs Docker for its PostgreSQL container.
