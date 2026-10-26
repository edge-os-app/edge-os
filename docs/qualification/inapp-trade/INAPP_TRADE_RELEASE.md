# In-app WMON -> MOE execution release for the builder's agent wallet

Task `CLOUD-A2`, builder-approved 2026-10-22. Base `9621433ef52c74c3288e1c994bc6624e8b4b62ec`. Status: **authored,
not registered.** This document and its files grant no trade authority. No network, provider, signer or
credential was used to write them. Builder decision: in-app trading option A. Only the builder trades: first on the
local app, later on the public site.

## Files

| File | Role |
| --- | --- |
| [`release.authored.json`](release.authored.json) | The one release (`actual-inapp-wmon-moe-20261022/1`), its authoring facts and `{"$fill": name}` markers for values that need a recorded read or a later lane. |
| `control-proofs/` | The committed raw stores and proof artifacts: `proofs-4` (seven controls), `proofs-5` (control 12) and `stores/` (the Privy and chain records). |
| `v3-live-result/` | The recorded v3 live result: 19 row files and `summary.json` (controls 1-3 and 9). |
| `apps/api/src/edge_os_api/execution/inapp_trade_release.py` | A pure completion step. It checks the fill, the gas rule and the USD ceiling, computes the minimum output, builds the `OperatingRelease` and the `BoundRelease`, and prints the exact registry lines. |
| `apps/api/tests/execution/test_inapp_trade_release.py` | Tests for the authored file, the completion step and the committed evidence. |

`operating_release.py` changed only its release shape and admission (`CLOUD-A6B`, see "Release steps and gas
budget" below). `APPROVED_ACTUAL_RELEASES` and `APPROVED_ACTUAL_BINDINGS` stay empty.

## What the release fixes

| Field | Value | Source |
| --- | --- | --- |
| Chain | `143` (Monad mainnet) | Task facts |
| Wallet | id `bsb2feecuxl81dl5jz4u9xxo`, address `0x91BB52A63c91986813288965e4681FF111De1b63`; also the recipient | Task facts; `scripts/privy_unfunded_proof/actual_packet.py` |
| Signer | key quorum `zu1qjdfqlbcq1ct7sdxendgg` | Same |
| Policy | `c30racyru6duaipj815cvjce`, owner `a5gwmgrsn6903ac09lphyv9a` (held only by the builder), normalized rules SHA-256 `61860d20…0892b` | Same |
| Route | `executeSwap` (`0xce1e7030`) on entrypoint `0xb3e6778480b2E488385E8205eA05E20060B813cb` | Task facts |
| Pair | sell WMON `0x3bd3…433a`, buy MOE `0xd8e0…7777`, 18 decimals each | Task facts; MOE decimals from Probe A (`qualified-actual-demo/QUALIFICATION_GAPS.md`) |
| Quote | `DIRECT_V2_PROGRAM`, pool `0x9719…5aad`, token0 WMON, token1 MOE, direction `0`, program fee `16000` ppm, slippage `100` bps, pre-sign tolerance `50` bps | Task facts; pre-sign tolerance: builder decision 2026-10-23 |
| Program | `0x023bd3…3e80`, built by the merged `build_program_hex` | Code |
| Input | `10000000000000000000` (10 WMON), allowance the same, value `0` | Authoring choice (see the USD section) |
| Fees | all zero, `is_in_token_fee` false (what `build_calldata_hex` encodes) | Code |
| Deployment | source commit `70bc0c93c073f78697b99848eedefbf5dbe698c7`, entrypoint code `da214086…e1cf`, router `0x2f84fb8982073f39ba47c7fcc29119af074abbcb` with code `9cf6f5c8…c649` | `kuru-deployed-source/SOURCE_IDENTITY.md` (read at block `0x6c1db44`, 2026-10-14) |
| Gas | swap `gas_limit` `700000`, `max_fee_per_gas` `202000000000` (202 gwei), priority `2000000000`, `budget_raw` `169680000000000000` (approve + swap + revoke) | Task gas rule; fee = 2 x the 100-gwei minimum base fee + 2-gwei priority (`controlled-action-feasibility`, M-GAS; operator rule `2 * base_fee + priority_fee`); budget: builder decision 2026-10-23 |
| Limits | actions, attempts and quote requests `1`; steps approve, swap, revoke in that order, each with signer requests `1` and broadcasts `1`; observer requests `20`; 4096/16384 bytes; 60 s deadline | The module requires the `1`s and the step order (builder decision 2026-10-23). The other values are authoring choices. |
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

The packet hash is the proof input, not the provider outcome. The v3 live result is now recorded in
[`v3-live-result/`](v3-live-result/): 19 rows, all 19 matched, packet `8255d003…`, 4 `ALLOW` and 15
`POLICY_DENY`. `summary.json` binds every row file by SHA-256:
`c9ceb7bef199930327d671c8f68095bab8a9cf0ddcb7b950d6f4e9ab41cb429b`. Controls 1-3 and 9 therefore cite
that summary hash with evidence class `PROVIDER_ACTUAL`. The packet document
`docs/qualification/privy-unfunded-proof/UNFUNDED_POLICY_PACKET.md` still says "pending (v3)"; it is outside
this task's owned paths, so the controller must update that line. This release document and the committed
store are the record for the release.

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

The gas budget, `169680000000000000` wei (0.16968 MON), is smaller than the 0.1818 MON counted here, because it
leaves out the wrap. Input plus budget is `10.16968 x 0.02 = USD 0.2033936`. Both are inside the ceiling.

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
- The release's `gas.budget_raw` must cover every active step's limit at the fixed maximum fee:
  `(70000 + 700000 + 70000) x 202 gwei = 169680000000000000`. A smaller budget refuses `INAPP_AUTHORED_INVALID`.
- `operating_release.py` itself does not read gas estimates. At run time the app's path signs the release's fixed
  `gas_limit` and does not estimate gas again. The check therefore runs once, on the recorded estimate, when the
  release is completed. A state change after that read is not covered (the same limit as in `OPERATOR_TRADE.md`).

## Controls: the recorded states and the builder decisions

`check_release` admits an ACTUAL release only when its exact hash is in the code-owned
`APPROVED_ACTUAL_RELEASES` registry. That check runs before any control is read. Then every control must be
qualified. A control is qualified in one of two ways:

- `ENFORCED` with the release's own evidence class (`PROVIDER_ACTUAL`) and a proof hash; or
- `DECISION_ACCEPTED` with evidence class `BUILDER_DECISION`, a fixed `decision_reason`, and the exact
  `(control, reason, proof_sha256)` triple in the code-owned `APPROVED_CONTROL_DECISIONS` registry.

A decision is never `ENFORCED` and never `PROVIDER_ACTUAL`. A decision proof relabelled as an `ENFORCED`
provider proof refuses. A release file is data and cannot write the registry, so a release file can never
accept its own decision.

| # | Control | State / evidence | Proof |
| --- | --- | --- | --- |
| 1 | `chain` | `ENFORCED` / `PROVIDER_ACTUAL` | v3 summary `c9ceb7be…` |
| 2 | `wallet_signer_binding` | `ENFORCED` / `PROVIDER_ACTUAL` | v3 summary |
| 3 | `entrypoint_method` | `ENFORCED` / `PROVIDER_ACTUAL` | v3 summary |
| 4 | `input_output_assets` | `DECISION_ACCEPTED` / `BUILDER_DECISION` | `b7c303f6…`, `OUTPUT_TOKEN_NOT_PROVIDER_BOUND` |
| 5 | `raw_input` | `ENFORCED` / `PROVIDER_ACTUAL` | `82c542a7…` |
| 6 | `recipient` | `DECISION_ACCEPTED` / `BUILDER_DECISION` | `4eaa9562…`, `FEE_RECIPIENTS_OBSERVED_NOT_SOURCE_BOUND` |
| 7 | `minimum_output` | `ENFORCED` / `PROVIDER_ACTUAL` | `0dcee961…` |
| 8 | `fees` | `DECISION_ACCEPTED` / `BUILDER_DECISION` | `6232e2a9…`, `FEE_VALUES_NOT_PROVIDER_BOUND` |
| 9 | `approvals` | `ENFORCED` / `PROVIDER_ACTUAL` | v3 summary |
| 10 | `gas_action_capacity` | `ENFORCED` / `PROVIDER_ACTUAL` | `f5a5e82b…` |
| 11 | `expiry_freshness` | `DECISION_ACCEPTED` / `BUILDER_DECISION` | `c638035f…`, `PRIVY_REFUSAL_REASON_NOT_READABLE` |
| 12 | `opaque_program` | `DECISION_ACCEPTED` / `BUILDER_DECISION` | `e231b94d…`, `PROGRAM_BOUND_BY_HOST_AND_TRACE_ONLY` |

### The decision registry

`APPROVED_CONTROL_DECISIONS` holds exactly five entries: `input_output_assets`, `recipient`, `fees`,
`expiry_freshness` and `opaque_program`, with the reasons and hashes above. The registry is a
`frozenset[tuple[str, str, str]]` in `apps/api/src/edge_os_api/execution/operating_release.py`. It is reviewed
code, not release data.

`check_release` and `unqualified_controls` use one shared helper, `control_is_qualified`. A changed control,
reason or proof hash refuses `EXECUTION_CONTROL_UNQUALIFIED`. An unregistered decision refuses the same code.
A `DECISION_ACCEPTED` control in a `SYNTHETIC_FIXTURE` release refuses at construction. A decision with
evidence class `PROVIDER_ACTUAL` refuses at construction. A registered decision proof used on an `ENFORCED`
control refuses.

**Residual limit.** The triple does not bind the release values. A different release file could copy a
registered triple. That copy still needs its own exact hash in `APPROVED_ACTUAL_RELEASES`, which is a second
reviewed code change. Until that registration it refuses `ACTUAL_EXECUTION_RELEASE_NOT_APPROVED`. A test covers
this case. The proof artifact's `authored_binding_sha256` also binds the authored release facts, and the
registering review checks it.

### The committed evidence

- `control-proofs/proofs-4/` holds the seven artifacts built from the stores on 2026-10-23 and 2026-10-26. Their
  bytes and hashes are frozen; `controls.json` is `9182273d…`.
- `control-proofs/proofs-5/` holds the same seven files, byte for byte, plus `opaque_program.proof.json` and its
  `controls.json`. The build command is in `control-proofs/README.md`.
- `control-proofs/stores/` holds the Privy store, its one expiry re-run and the chain store. They are the
  evidence of record. The proofs are only as authentic as those stores.
- `v3-live-result/` holds the 19 v3 rows and `summary.json`. A test recomputes the summary from the rows.

With every control qualified, the authored release still refuses `ACTUAL_EXECUTION_RELEASE_NOT_APPROVED`:
`APPROVED_ACTUAL_RELEASES` and `APPROVED_ACTUAL_BINDINGS` are empty (step 8 is not in this task). One test
registers a test-only copy of the release and shows admission; another changes one decision triple and shows
`EXECUTION_CONTROL_UNQUALIFIED`. No test writes the real registries.

### Control 12 (`opaque_program`)

`control-proofs/proofs-5/opaque_program.proof.json` is a decision artifact, not a provider proof. It carries:

- the host check: `route.approved_program_hex` equals `build_program_hex` for the release input token, pool,
  direction and program fee (`LOCAL_TESTED`, `findings.host_program_check`);
- the provider-actual `chain.swap_trace` at block `115860413`;
- `call_targets`: entrypoint, router, pool, WMON, MOE and fee collector `0xe1c8…3022`;
- `delegate_targets`: pool implementation `0x8115…b4cf`, MOE implementation `0x4f44…6fbd`,
  fee-collector implementation `0xd52c…6dbe` and helper implementation `0x2e14…de50`, each labelled
  "proxy implementation, observed at this block, owner-upgradeable";
- `static_targets`, including the read-only helper `0x71f8…71c7`;
- `touched`: all 11 addresses, each with its frame types and callers;
- `fee_transfers`: `0xe1c8…3022` 0.10 WMON and `0x681c…8998` 0.035 WMON, each within its pinned bound.

Admission checks every `CALL` target. Each must be one of the five release contracts or a pinned fee recipient.
A `DELEGATECALL` or `STATICCALL` frame needs an admitted caller. A `CREATE`, `CREATE2`, `SELFDESTRUCT` or a
non-zero native value refuses. Token movements keep the recipient rules. The reason is
`PROGRAM_BOUND_BY_HOST_AND_TRACE_ONLY`. No provider binds the program bytes; the host check is `LOCAL_TESTED`.

### The v3 summary

`v3-live-result/summary.json` has schema `edge-os.inapp-v3-live-result/1`. It names the packet
`8255d003…`, the attempt `unfunded-policy-proof-3`, the policy and profile, the row and match counts (19/19,
4 `ALLOW`, 15 `POLICY_DENY`), `stop: null`, the first and last completion times, and every row's
`intent_record_sha256`, `capture_record_sha256`, `outcome_record_sha256`, outcome and reason. A test recomputes
the summary from the 57 committed row files and checks the hash.

## Pending builder and controller steps, in order

1. **Record the v3 live result (done, `CONTROL-ADOPT-L1`).** The 19/19 store is committed at
   [`v3-live-result/`](v3-live-result/). Controls 1-3 and 9 cite the summary hash
   `c9ceb7bef199930327d671c8f68095bab8a9cf0ddcb7b950d6f4e9ab41cb429b` with `PROVIDER_ACTUAL`. The controller
   still owns one documentation edit outside this task's paths: `UNFUNDED_POLICY_PACKET.md` still says
   "pending (v3)".
2. **Control evidence (done, `CONTROL-ADOPT-L1`).** Controls 4, 6, 8, 11 and 12 are `DECISION_ACCEPTED` with
   the builder's option A acceptance. The five exact decisions are in `APPROVED_CONTROL_DECISIONS`; the proof
   artifacts are committed. Control 12 uses the host-exact program check plus the provider-actual trace of that
   exact program, and lists every touched address with its frame type and caller.
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
   floor. The release pins `pre_sign_tolerance_bps` = `50`. The app may sign when the live floor is at most 50 bps
   below this recorded minimum, using integer math: it refuses only when
   `floor(output * 9900 / 10000) * 10000 < approved_min_output_raw * 9950`. A live floor 51 bps or more below the
   recorded minimum is refused (`QUOTE_SLIPPAGE_EXCEEDED`) before signing. The on-chain minimum written into the swap stays
   `approved_min_output_raw`; the 100 bps slippage still protects the swap itself. The time between the read and the
   run covers the fill, the hash, approval and the registry commit. A new read needs a new fill and a new hash.
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
| `EXECUTION_BOOTSTRAP_ENV_NOT_ADMITTED` | `settings.env` is neither `local` nor `production` (`EXEC-PROD-L3`). |
| `EXECUTION_BOOTSTRAP_HOSTED_RECORD_REFUSED` / `_HOSTED_RELEASE_MISMATCH` | In `production`: no admitted v2 hosted record, or its `execution_release` is not the admitted candidate's exact release. See `HOSTED_RECORD_V2_RUNBOOK.md`. |
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
- **Gas reservation.** Resolved by `CLOUD-A6B`: the release's `gas.budget_raw` is now `169680000000000000`
  (approve, swap and revoke at 202 gwei). The worker sets the action's gas cap from it.
- **Step-aware settlement.** Settling a step action needs bound receipts for every sent step, with the gas of every
  step charged. It is not built yet. Until then these actions stay unknown (see above).
- **Release limits.** Resolved in the release by `CLOUD-A6B`: the limits count per step (see below). The mounted
  signer and broadcast clients still allow one request each per client. Counting them per step is wiring work.
- **Revoke confirmation.** `read_revoke_receipt` exists, but no worker path calls it yet. The recovery view
  therefore reports a sent revoke as `REVOKE_UNCONFIRMED` (open).
- **Ceiling price.** The USD check uses the release's documented MON price (`0.02`, an unapproved example). The
  builder still confirms the current price before the run (see above).

## Release steps and gas budget (`CLOUD-A6B`)

Task `CLOUD-A6B`, builder-approved 2026-10-23. Base `c0d59cae84560617254720a2f818f0dc07c60344`. This changes the
release content and so its hash. It registers nothing: `APPROVED_ACTUAL_RELEASES` and `APPROVED_ACTUAL_BINDINGS`
stay empty until the builder approves the exact hashes (pending step 8).

### New release content

**SHA-256 of `release.authored.json`: `4648eb16b9f27daa965620c8d39fb926543d7c00564cb3c2c7e6ca3fe1ba5e4d`**
(`sha256sum docs/qualification/inapp-trade/release.authored.json`; a test checks that this document prints it).

The release still carries `{"$fill": name}` markers. Its `release_sha256`, the hash the builder registers, exists
only after the controller's fill (pending steps 3-7), and step 7 prints it. `CONTROL-ADOPT-L1` changed the 12
controls and so this authored hash; the release steps, gas budget and limits did not change. The previous authored
file had `budget_raw` `141400000000000000` and the single-action limits. Any release completed from it has a
different hash.

Two values changed:

```json
"gas": {"gas_limit": 700000, "max_fee_per_gas": 202000000000, "max_priority_fee_per_gas": 2000000000,
  "budget_raw": "169680000000000000"},
"limits": {"actions": 1, "attempts": 1, "quote_requests": 1,
  "observer_requests": 20, "max_request_bytes": 4096, "max_response_bytes": 16384, "deadline_seconds": 60,
  "steps": [{"step": "approve", "signer_requests": 1, "broadcasts": 1},
    {"step": "swap", "signer_requests": 1, "broadcasts": 1},
    {"step": "revoke", "signer_requests": 1, "broadcasts": 1}]}
```

### Builder decisions (2026-10-23)

1. **Limits per step.** The in-app release names three steps, approve, swap and revoke. Each step has
   `signer_requests` `1` and `broadcasts` `1`.
2. **Gas budget.** `gas.budget_raw` covers all three steps: `169680000000000000` wei (0.16968 MON). It stays inside
   the USD 2 ceiling, including gas, at the release's MON price (see "USD ceiling arithmetic").
3. **Revoke after a stop.** The revoke still runs after a stop, an expiry, an agent removal or a consent change,
   because it only lowers the allowance. Its rechecks keep the release admission only. `CLOUD-A6` already behaved
   this way. The test `test_builder_decision_a_stop_agent_removal_or_consent_change_never_blocks_the_revoke` covers
   a lasting stop (`STOPPED_HALT_ALL_SWAPS`), an agent removal (`REMOVAL_REQUESTED`) and a consent change
   (`CONSENT_OR_REVISION_CHANGED`). `test_an_intent_expiring_after_the_approve_still_lets_the_revoke_run` covers an
   expiry.

### Release shape and admission (`operating_release.py`)

`OperatingRelease` admits a release only in one of two `limits` shapes:

| Shape | `limits` keys | Rule |
| --- | --- | --- |
| Single action (unchanged) | `actions`, `attempts`, `broadcasts`, `quote_requests`, `signer_requests`, `observer_requests`, `max_request_bytes`, `max_response_bytes`, `deadline_seconds` | Exactly as before. `actions`, `attempts`, `broadcasts`, `quote_requests` and `signer_requests` are `1`. Its canonical bytes and hash are unchanged. A test pins the synthetic release hash from the base. |
| Steps | the same keys without `broadcasts` and `signer_requests`, plus `steps` | `steps` is exactly `[approve, swap, revoke]` in that order. Each entry has exactly `step`, `signer_requests` `1` and `broadcasts` `1`. `actions`, `attempts` and `quote_requests` are `1`. |

Anything else refuses `EXECUTION_RELEASE_INVALID` before any I/O. Examples: another order, a missing, extra or
repeated step, a count other than the integer `1`, an extra key, or top-level `signer_requests` or `broadcasts` next
to `steps`. `release_steps(release)` returns the named order, or `None` for a single-action release.

### Where the steps are read

- `inapp_trade_release` refuses `INAPP_AUTHORED_INVALID` when any of these holds: the release does not have the
  step shape, its steps differ from `facts.active_steps`, or `gas.budget_raw` is below the sum of the active step
  limits at `max_fee_per_gas`. `TradeSteps.from_authored` uses the same checks.
- `OriginalTransactionTransport` with a bound release runs only what that release names. It needs a step plan
  whose order equals `release_steps`, or no plan when the release is single-action. Otherwise it refuses
  `RELEASE_STEPS_MISMATCH` before the quote, the nonce read or any signature. The step path sends each named step
  at most once, in order. A second run is refused with `ACTION_ALREADY_STARTED`. A step outside the release is
  never prepared.

### Worker step plan wiring (`STEPS-WIRE-L3`)

Task `STEPS-WIRE-L3`, 2026-10-23. This section records how the accepted transport is wired into the bounded worker.
It adds no authority and registers nothing.

- **The plan travels with the admitted release.** `ReleaseCandidate` carries the exact `TradeSteps` reviewed with
  its release. `build_worker_execution_runtime` refuses `EXECUTION_BOOTSTRAP_STEPS_MISMATCH` when the plan's order,
  start asset or swap gas differs from the bound release. The plan never comes from an environment value.
- **The worker passes the plan to both seams.** `ConnectedExecution._original_transport` gives the same plan to
  `ControlledRuntime.clients` and `OriginalTransactionTransport`. The client layer refuses a plan that does not
  match the binding before it mounts any signer or broadcast client.
- **Each client reads its own step.** With a plan, the signer reads the `APPROVE_SIGN_REQUESTED` or
  `REVOKE_SIGN_REQUESTED` record that names the exact prefixed request id. The broadcast client reads the record
  whose stage is `BROADCAST_REQUESTED` for the step that is sending now, then validates its own signed bytes and
  hash. The swap keeps the top-level records, so a single-action release is unchanged.
- **Reconcile never ends an attempt with steps in flight.** While an attempt is `IN_FLIGHT`, a step action is
  reported as `ORIGINAL_IN_FLIGHT`, even after the swap hash exists. A concurrent reconcile therefore cannot end
  the attempt between the swap and the revoke and leave the allowance open but unrevoked.
- **Settlement needs every sent step.** A step action settles only from a bound, final, chain-143 receipt for every
  step that may have been signed or sent. The approve and revoke receipts bind their own signed bytes, token,
  spender and amount. The swap keeps the accepted bound receipt checks. Settlement charges the full gas limit of
  every sent step, not only the swap.
- **Unknown keeps liability.** A missing step hash, a missing receipt, a wrong chain or a receipt outside the
  finalized canonical chain keeps the action `SUBMISSION_UNKNOWN` with its reservations and allowance held. A
  reconcile never signs, re-signs, rebroadcasts or replaces a step.
- **The allowance is always reported.** `allowance_status` derives the state from the saved step records. A
  receipt-proved `CLOSED` or `REVOKE_REVERTED` state is used only when the approve was sent and the revoke broadcast
  returned. Every other reading, including a missing proof, stays open. `read_revoke_receipt` checks the chain id
  `143` and the finalized canonical block before it closes or reports a reverted revoke.

Tests: `tests/execution/test_worker_step_plan.py`, `tests/recovery/test_steps_settlement.py`, and the extended
allowance tests in `tests/execution/test_approve_swap_revoke.py`. All external replies are local doubles.

## Checks

```sh
cd apps/api && .venv/bin/python -m pytest -q tests/execution/test_operating_release.py \
  tests/execution/test_inapp_trade_release.py \
  tests/execution/test_approve_swap_revoke.py tests/recovery/test_approve_swap_revoke_recovery.py
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -m pytest -q tests/privy_unfunded_proof
```

The recovery test needs Docker for its PostgreSQL container.

Rebuild the control 12 artifact from the committed stores (no network). Build into a new directory; the committed
`proofs-5` is the reviewed output.

```sh
PYTHONPATH=apps/api/src:. apps/api/.venv/bin/python -B -s -m scripts.privy_unfunded_proof.control_proofs \
  --authored docs/qualification/inapp-trade/release.authored.json \
  --privy-store docs/qualification/inapp-trade/control-proofs/stores/privy-store-1 \
  --chain-store docs/qualification/inapp-trade/control-proofs/stores/chain-store-1 \
  --with-expiry-rerun --out <new directory>
```

The seven existing artifacts must keep the `proofs-4` hashes in `control-proofs/README.md`.

## A5 server-wallet binding, local only

Task `WALLET-BINDING-L4-20261023`. This section covers the local binding of the release wallet above. It grants no
provider call, signing, trade or production authority. The base is `82290e2`.

### Configuration

- `wallet_provider=privy_server` is local and test only. The existing production rule still refuses every provider
  other than `unavailable`.
- The API uses the private Unix socket in `EDGE_OS_PRIVY_SERVER_SOCKET`. The API holds no Privy app secret.
- The separate lookup process starts with
  `python -m lookup_server <socket_path> --server-wallet-release docs/qualification/inapp-trade/release.authored.json`
  and reads `PRIVY_APP_ID` and `PRIVY_APP_SECRET` only in its own environment.
- `wallet_provider=privy_server` must not set `EDGE_OS_WALLET_LOOKUP_SOCKET`. The existing rule refuses that pair,
  because the browser-owner lookup would replace the server-wallet provider.

### Read and exact match

The lookup process makes one fixed, read-only `GET https://api.privy.io/v1/wallets/{wallet_id}` with the release
wallet id. It accepts a wallet object only when all of these hold:

| Field | Required value |
| --- | --- |
| `id` | release `wallet_id` (`bsb2feecuxl81dl5jz4u9xxo`) |
| `chain_type` | `ethereum` |
| `address` | release `wallet_address`, compared without letter case |
| `policy_ids` | exactly `[release.policy_id]` |
| `owner_id` | release `policy_owner_id` (the builder-owned key quorum) |
| `additional_signers` | exactly `[{"signer_id": release.signer_id, "override_policy_ids": [release.policy_id]}]` |

The allowed optional fields are `created_at`, `entity`, `external_id`, `display_name`, `exported_at` and
`imported_at`, and each must have the documented type. `exported_at` and `imported_at` must be null: an exported
key is outside Privy policy enforcement, and this wallet was created, not imported. A missing identity field, an
extra field, an unknown shape, a non-200 status, a redirect, a timeout or any provider error refuses the lookup.
A refusal is never `WALLET_BOUND`; the setup stays `UNKNOWN`.
The process also answers `lookup_embedded_wallet`; the `bind_server_wallet` operation exists only when it
starts with `--server-wallet-release`.

The `owner_id` = `policy_owner_id` and `additional_signers` =
`[{signer_id, override_policy_ids: [policy_id]}]` mapping follows the recorded creation state in
`ROOT/.scratch/trade-prep-20261021/PRIVY_SETUP1_RECORD.md` and `PRIVY_SETUP1.json`: wallet owner and policy owner
`a5gwmgrsn6903ac09lphyv9a`, policy `c30racyru6duaipj815cvjce`, signer `zu1qjdfqlbcq1ct7sdxendgg` with override
policy `c30racyru6duaipj815cvjce`. The executor signer override is the control that limits the agent signer, so a
missing, empty or different override refuses. The first live read must confirm the mapping. A different live
record is refused; it is not a reason to relax the check.

### Release binding hash

The lookup process computes one SHA-256 over this canonical JSON, with sorted keys and no spaces:

```json
{"chain_id":143,"chain_type":"ethereum","policy_id":"<policy_id>","policy_owner_id":"<policy_owner_id>","release_id":"<release_id>","signer_id":"<signer_id>","wallet_address":"<lowercase address>","wallet_id":"<wallet_id>"}
```

The `WALLET_BOUND` evidence for the server wallet carries `wallet_id`, `owner_id`, `chain_type`, `address` and
`release_binding_sha256`. The fixture and `unavailable` providers keep their previous three evidence fields byte for
byte. A worker path can recompute the hash from the release and compare it before it uses the address.

### Limits

- The provider keeps the verified owner of a created wallet in process memory. A fresh process that starts from a
  retained wallet id has no owner and stays `UNKNOWN`. It never binds on a guessed owner.
- The server-wallet path binds on `dispatch`; a browser completion without an initial create cannot supply the
  owner. This is local single-builder use, not a caller allowlist. A DID allowlist is a later ticket.
- `wallet_setup/recovery.py` is outside this task. Its `RECONCILED` event can bind the same verified wallet without
  `release_binding_sha256`. A worker check must read both `WALLET_BOUND` and `RECONCILED`, or a later authorized
  ticket must add the hash on that path.
- No test makes a network, provider, credential, signing or wallet call. The fake reply shape follows the Privy
  wallet object (`GET /v1/wallets/{id}`) from Context7.
- Production admission needs hosted record schema v2 with `execution_release`. A4/A7 own that work.

### Checks

```sh
cd apps/api && .venv/bin/python -m pytest -q \
  tests/test_privy_server_wallet_binding.py \
  tests/wallet_setup/test_server_wallet_evidence.py \
  tests/execution/test_server_wallet_release_binding.py
```
