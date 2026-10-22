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
- A document file hash changes with any wording edit. `UNFUNDED_POLICY_PACKET.md` still says the v3 live result is
  "pending". The 19/19 result was reported by the builder on 2026-10-22 and is not yet recorded in the repository.

The same hash is the proof for the four controls owned by the policy.

## USD ceiling arithmetic (including gas)

Monad charges the full gas limit. The worst case therefore counts the full limit of every step. It includes the
wrap, which a WMON start does not run.

```text
gas      = (60000 + 70000 + 700000 + 70000) x 202 gwei = 900000 x 202e9 wei = 0.1818 MON
input    = 10 WMON                                                        = 10.0000 MON
worst    = 10.1818 MON
at the documented MON price 0.02 USD (operator-trade/trade.example.json):
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
`PROVIDER_ACTUAL` and has a proof hash. This release keeps the states that the sealed packet recorded. No control is
relaxed.

| # | Control | State / evidence | Proof |
| --- | --- | --- | --- |
| 1 | `chain` | `ENFORCED` / `PROVIDER_ACTUAL` | packet `8255d003…` |
| 2 | `wallet_signer_binding` | `ENFORCED` / `PROVIDER_ACTUAL` | packet |
| 3 | `entrypoint_method` | `ENFORCED` / `PROVIDER_ACTUAL` | packet |
| 4 | `input_output_assets` | `UNKNOWN` / `NOT_RUN` | none |
| 5 | `raw_input` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 6 | `recipient` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 7 | `minimum_output` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 8 | `fees` | `ENFORCED` / `SOURCE_INSPECTED` | none |
| 9 | `approvals` | `ENFORCED` / `PROVIDER_ACTUAL` | packet |
| 10 | `gas_action_capacity` | `UNSET` / `NOT_RUN` | none |
| 11 | `expiry_freshness` | `ENFORCED` / `DOCUMENTED` | none |
| 12 | `opaque_program` | `UNKNOWN` / `NOT_RUN` | none |

Even with the registry lines added, this release is refused with `EXECUTION_CONTROL_UNQUALIFIED`. The eight
controls 4-8 and 10-12 need provider-actual proof first. Each needs a new proof artifact, which changes the release
hash. A test shows the exact refusal. Another test shows that a copy with every control proven, plus the registry
entry, admits its exact hash and refuses any changed control. That copy is a hypothetical in the test only. It is not
in the authored file.

## Pending builder and controller steps, in order

1. **Control evidence (builder decision).** Produce provider-actual proof for controls 4-8 and 10-12, or decide
   otherwise. The module rule cannot be met without one of these. A decision to change the rule is a product decision
   and a separate reviewed change. It is not part of this task.
2. **Dry run (controller).** Run the operator dry run with `"start": "WMON"`, `input_raw`
   `10000000000000000000` and the authored step limits. Record the pool reserves with their block, and record the
   estimate for each of approve, swap and revoke.
3. **Fill (controller).** Write `docs/qualification/inapp-trade/release.fill.json` with exactly these keys:

   | Key | Value |
   | --- | --- |
   | `reserves` | `{"block_number": <int>, "reserve_wmon": "<raw>", "reserve_moe": "<raw>"}` from step 2 |
   | `gas_estimates` | `{"approve": <int>, "swap": <int>, "revoke": <int>}` from step 2 |
   | `quote_endpoint`, `broadcast_endpoint`, `observer_endpoint` | Keyless `https://<host>/rpc` URLs for the `/rpc` relay. Two different endpoints are required for broadcast and observer. The relay belongs to another lane. |
   | `valid_until` | The signing cutoff (RFC 3339 UTC). It is also used as the intent and signer-request expiry. |
   | `mandate_expires_at` | Not before `valid_until`. |
   | `abi_sha256` | SHA-256 of the pinned entrypoint ABI, recorded by the controller |
   | `mutable_router_proof_sha256` | SHA-256 of a current `getRouter()` read proving that the router is still `0x2f84…bbcb` with code `9cf6f5c8…` |

   The minimum output is never supplied by hand. It is computed as
   `floor(floor(x * 984000 * R_moe / (R_wmon * 10**6 + x * 984000)) * 9900 / 10000)`, which is the quote client's own
   floor. If the pool moves against the trade after the recorded read, the app's quote is refused
   (`QUOTE_SLIPPAGE_EXCEEDED`) before signing. A new read then needs a new fill and a new hash.
4. **Sign-in (builder).** Sign in to the local app. Confirm the agent wallet `bsb2feecuxl81dl5jz4u9xxo`, publish
   the MOE strategy revision and adopt the `connected-one-action/1` consent. `owner_id`, `agent_id` and
   `consent_adoption_id` exist only after this step. No value is authored for them.
5. **Identity (controller).** Read the identity from the builder's saved records with the same derivation that the
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
   `SAVED_IDENTITY_WALLET_MISMATCH` for any wallet other than the release wallet. Put the printed object under
   `identity` in `docs/qualification/inapp-trade/binding.fill.json`. Add the six proof keys and `market_profile`.
   `position_inventory`, `market` and `finality` are required. `derive_approval` also requires `exit_capacity`,
   `valuation` and `cost_model`. Market observation requires `market_profile`. None of these proofs exists yet.
6. **Hashes (controller).**

   ```sh
   cd apps/api && .venv/bin/python -m edge_os_api.execution.inapp_trade_release \
     --authored ../../docs/qualification/inapp-trade/release.authored.json \
     --fill ../../docs/qualification/inapp-trade/release.fill.json \
     --binding-fill ../../docs/qualification/inapp-trade/binding.fill.json
   ```

   The command prints `release_sha256`, `binding_sha256`, `unqualified_controls` and the two `registry_lines`. It
   makes no request.
7. **Registration (builder approval of both exact hashes).** Replace `operating_release.py` lines 20-21 with the
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

   The last assertion passes only after step 1.

## What else must exist before the app can run the action

These items are outside this task and are owned by other lanes:

- A `ControlledRuntime` mount. No application code builds one today.
- The `/rpc` relay behind the three endpoints.
- An exact on-chain approve of 10 WMON to the entrypoint before the swap, and a revoke to 0 after it. The app path
  signs only the swap. It has no approve or revoke step (`OPERATOR_TRADE.md`, "Honest limits").
- The signer change for quantities above `2**53-1`, but only if a MON start is wanted.

## Checks

```sh
cd apps/api && .venv/bin/python -m pytest -q tests/execution/test_inapp_trade_release.py
```
