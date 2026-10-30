# Binding proofs for the in-app WMON -> MOE release

Task `CLOUD-BINDING-PROOFS`, builder-approved normal cloud session, 2026-10-30. Base
`275b399` (`origin/integration/edge-os-mvp`). Status: **analysis and offline tooling only.** No network, RPC, key,
wallet, signer or provider was used. Nothing here registers a release or binding or grants trade authority.

[`INAPP_TRADE_RELEASE.md`](INAPP_TRADE_RELEASE.md) step 6 says the binding fill needs `identity`, six proof keys
and `market_profile`. This document says, for each of the seven items, what the code requires, what the
repository says the item must prove, and where it says nothing. Where it says nothing, the content is a product
decision. Those decisions are in [`CLOUD_BINDING_PROOFS_STATUS.md`](CLOUD_BINDING_PROOFS_STATUS.md) with options
and a recommendation.

## Result in one paragraph

The code defines the **form** of every item and the **consumer** of two of them. It defines the **content** of
none. Each proof key is a bare 64-character lowercase hex reference. `BoundRelease` checks only that form
(`operating_release.py:260-261`) and hashes it into the binding (`operating_release.py:269-273`). Only the
market proof is compared with anything at run time: it must equal the `qualification_proof_sha256` that the
market source puts in its provenance (`core/provider_ports.py:519`, `execution/worker.py:101`). No market source
exists in `src` other than the fixture `FixtureMarketObservations` (`core/provider_ports.py:99-108`); the worker's
released runtime is built without a `market_source` (`execution/released_execution_bootstrap.py:284-286`), so
`observe_market` always refuses (`core/provider_ports.py:493-496`). The other five
references are carried into `ControlledApproval` or the binding hash and never read again. So no builder in this
task may say "this file is the position-inventory proof" without a product decision. Phase B therefore builds only
what the repository defines: (1) the step-6 binding-fill assembler and checker, and (2) a checked, hashed set of
recorded chain reads at one finalized block that the proofs would cite. The reads artifact fills no slot.

## Where the binding is built and read

| Step | Code | What it does with the proofs |
| --- | --- | --- |
| Fill shape | `execution/inapp_trade_release.py:30-32` | `BINDING_FILL_FIELDS`: `identity`, the six `*_proof_sha256` keys and `market_profile`, exactly. |
| Binding | `execution/inapp_trade_release.py:191-202` | `bind_release` refuses `INAPP_BINDING_FILL_INVALID` for a missing, extra or non-object field, then builds `BoundRelease`. |
| Form | `execution/operating_release.py:260` | `position_inventory`, `market`, `finality`: required 64-hex (`_hash`). |
| Form | `execution/operating_release.py:261` | `exit_capacity`, `valuation`, `cost_model`: `None` or 64-hex. |
| `market_profile` | `execution/operating_release.py:262-268` | `None`, or exactly `source_id`, `delivery_profile_sha256`, `finality` (`"finalized"`), `warmup_buckets` (int 0-10000), `max_collection_age_seconds` (int, `0 <` x `<=` the release `max_input_age_seconds`, 60 for this release). |
| Hash | `execution/operating_release.py:269-279` | All seven values, the identity and the release hash, canonical JSON, schema `edge-os.controlled-execution-binding/1`, SHA-256. |
| Approval | `execution/connected_identity.py:182-196` | `derive_approval` admits the binding, then returns `OPERATIONAL_QUALIFICATION_UNAVAILABLE` when `position_inventory`, `exit_capacity`, `valuation` or `cost_model` is `None`. It copies those four into `ControlledApproval`. |
| Approval record | `admission/types.py:150-161` | `ControlledApproval` carries the four as required 64-hex fields. |
| Flags | `admission/types.py:179-181`, `connected_identity.py:243-244` | `exit_capacity_qualified`, `valuation_qualified`, `cost_model_qualified` are set `True` only when `controlled is None` (fixture mode). A controlled approval has all three `False`. |
| Admission | `admission/accounting.py:116-122` | The three flags are checked only when `controlled is None`. A controlled approval is never refused on them. Its `EXIT` is refused anyway (`CONTROLLED_ACTION_UNSUPPORTED`, line 114). |
| Market | `core/provider_ports.py:491-537`, `execution/worker.py:98-108` | Needs `market_profile`; the source's provenance must carry `qualification_proof_sha256 == market_proof_sha256` and the profile's `source_id`, `delivery_profile_sha256`, `finality`, `warmup_buckets`; collection age at most `max_collection_age_seconds`. `request.warmup_buckets` comes from the published revision (`worker.py:383`). |
| Finality | `execution/provider_observations.py:56-57` | With a binding, finality is "qualified" when `binding.qualify_original` admits the original. The `finality_proof_sha256` value is not read. The holdings reader (`current_holdings.py:69-109`) and the revoke receipt read use the RPC `finalized` tag. |

Tests that build a binding fill today use placeholders: `tests/execution/test_inapp_trade_release.py:73-77`
(`"6"*64`, `"7"*64`, `"8"*64`, three `None`, `market_profile` `None`) and `tests/execution/_builders.py`. No
test builds a proof artifact.

## The seven items

The release fixes the facts below (`release.authored.json`): chain `143`; wallet
`0x91BB52A63c91986813288965e4681FF111De1b63`; input WMON `0x3bd3…433a` 18 decimals, `approved_input_raw`
`10000000000000000000`; output MOE `0xd8e0…7777` 18 decimals; pool `0x9719…5aad`, token0 WMON, token1 MOE;
entrypoint `0xb3e6…13cb`; steps approve, swap, revoke; `gas.budget_raw` `169680000000000000`; USD 2.00 ceiling,
including gas (`INAPP_TRADE_RELEASE.md`, "USD ceiling arithmetic").

### 1. `identity` — defined, not built here

- **Must prove:** the exact saved owner, agent, wallet, revisions, consent and hashes the worker will compare.
- **Source:** `saved_identity_for_release` (`inapp_trade_release.py:205-217`), from the builder's saved records,
  after sign-in (step 5). It needs PostgreSQL and the builder's records, so the controller reads it later.
- **Form:** exactly `_IDENTITY_FIELDS` (`operating_release.py:236-238`); `wallet_id` and `wallet_address` equal to
  the release, exact case; `network_id` `monad:143`; `content_sha256`/`manifest_sha256` 64-hex;
  `consent_hash`/`review_hash`/`terms_hash` `sha256:<64-hex>` (`operating_release.py:255-259`).
- **Refusals:** `SAVED_IDENTITY_UNAVAILABLE`, `SAVED_IDENTITY_WALLET_MISMATCH` (`inapp_trade_release.py:212,216`);
  `EXECUTION_RELEASE_INVALID` from `BoundRelease` (`operating_release.py:37-39`) for a bad form.
- **This task:** the assembler takes the printed object as a file and passes it to `bind_release` unchanged.

### 2. `position_inventory_proof_sha256` — required; content NOT defined

- **Code:** required 64-hex (`operating_release.py:260`); copied to `ControlledApproval` (`connected_identity.py:194-196`).
  Never read.
- **Repository meaning:** "Sell permission from Edge OS position inventory". The independent layer is
  `UNSUPPORTED`; the host has local capacity arithmetic only (`independent-enforcement/CAPABILITY_MATRIX.md:38`;
  `privy-unfunded-proof/ACTUAL_PROOF_OPERATION_INPUTS.json`, `position_inventory` `UNSUPPORTED`). EXIT-CAP-Q01 is
  "inventory-based direction accepted; enforcement/capacity unqualified" (`EDGE_OS_RESEARCH_CONTRACTS.md:202-220`).
- **Gap:** the meaning is about **sale** authority from attributed inventory. This release permits one ENTRY and no
  EXIT (`accounting.py:114`). Nothing says what an inventory proof for a one-entry release contains: the wallet's
  starting balances, the absence of attributed positions, or a qualified inventory mechanism. The nearest statement
  is `controlled-action-feasibility/CONTROLLED_ACTION_FEASIBILITY.md:158`: the position-inventory restriction "does not apply to one controlled qualification action
  that does not claim exit coverage". It removes the restriction for this action but still does not say what the
  required reference contains. → **Question Q1.**
- **Defined input it would cite:** the checked binding reads (below): WMON, MOE and native balances, token
  decimals and WMON allowance to the entrypoint, all at one finalized block.

### 3. `market_proof_sha256` — required; content NOT defined; consumer defined

- **Code:** required 64-hex. At run time it must equal the market source's
  `provenance.qualification_proof_sha256` (`provider_ports.py:519`, `worker.py:101`). Any mismatch makes market
  observation unavailable (`ProviderUnavailable("current_observations")`, `provider_ports.py:536`).
- **Repository meaning:** "Current inputs require a frozen source, delivery profile, finalized boundary, warmup
  size and collection limit" (`implementation/CONTROLLED_EXECUTION_RUNTIME.md:13`). "Research history, Nansen
  context and delayed replay cannot become this feed through a label" (same file, "Read-only evidence").
- **Gap:** no non-fixture `MarketObservationPort` implementation exists, so nothing emits the provenance this hash must equal.
  The proof's content, and the source it qualifies, are undefined. → **Question Q2** (blocked on a missing component
  as well as on a decision).
- **Consequence:** the worker decides every action from a market observation (`worker.py:380-383`). An unavailable
  observation ends the job `OBSERVATIONS_UNAVAILABLE` before any intent (`worker.py:417-420`). So with today's code
  the in-app action cannot start without a market source, a market proof and a `market_profile`, even when the
  other five proofs exist.

### 4. `finality_proof_sha256` — required; content NOT defined

- **Code:** required 64-hex. Not read. Finality at run time comes from the RPC `finalized` tag
  (`current_holdings.py:78`) and binding admission (`provider_observations.py:56`).
- **Repository meaning:** "an independently qualified finalized boundary" (`CONTROLLED_EXECUTION_RUNTIME.md`,
  "Read-only evidence and recovery"). Every finality reference in `docs/` is a limit, never a definition
  (for example `kuru-flow/DIRECT_ROUTE.md:69`: local tests "do not prove … finality").
- **Gap:** what qualifies the observer's `finalized` tag as final on Monad (a documented chain rule, a recorded
  consistency read, or both) is not stated. → **Question Q3.**

### 5. `exit_capacity_proof_sha256` — optional in the binding, required by `derive_approval`; content NOT defined

- **Code:** `None` or 64-hex; `derive_approval` refuses `None` (`connected_identity.py:190-192`). Not read.
- **Repository meaning:** EXIT-CAP-Q01 (`EDGE_OS_RESEARCH_CONTRACTS.md:178,202-220`): all attributable acquired
  inventory needs preapproved exit capacity; unqualified.
- **Gap:** the release grants no exit. Whether the proof states "no exit authority; the builder exits by hand",
  or must qualify real exit capacity, is undecided. `controlled-action-feasibility/CONTROLLED_ACTION_FEASIBILITY.md:158` supports a statement: this one action
  "does not claim exit coverage". → **Question Q4.**

### 6. `valuation_proof_sha256` — as 5; content NOT defined

- **Code:** as item 5. Not read.
- **Repository meaning:** valuation is used for EXIT marks (`accounting.py:120-124`, `MISSING_VALUATION`). The
  design's weighted-average cost and mark rules (WAL-Q18) are unrun.
- **Gap:** which mark (pool spot at the binding block, the quote formula, or none for a one-entry release) and in
  which unit is undecided. → **Question Q5.**

### 7. `cost_model_proof_sha256` — as 5; content NOT defined

- **Code:** as item 5. Not read.
- **Repository meaning (partial):** the release already defines the cost arithmetic: full gas limit charged, input
  plus all four step limits at `max_fee_per_gas` at the documented MON price, at most USD 2.00
  (`inapp_trade_release.py:104-116`, `complete_release` lines 153-154; `INAPP_TRADE_RELEASE.md` "USD ceiling arithmetic"); program fee `16000` ppm;
  route fees zero; observed fee transfers 1.00% and 0.35% of the input (`control-proofs/proofs-5/opaque_program.proof.json`).
- **Gap:** whether the cost-model proof is a restatement of that arithmetic bound to the release (already enforced
  by `complete_release`), or needs measured costs (receipt gas, realised fee), and whether the unapproved MON
  price `0.02` may stand in it. → **Question Q6.**

### 8. `market_profile` — form defined; values NOT defined

- **Code:** exact five fields (`operating_release.py:264-268`); needed for market observation
  (`provider_ports.py:493`). `warmup_buckets` must equal the published revision's `warmup_buckets`
  (`worker.py:383`, `provider_ports.py:495`).
- **Gap:** `source_id` and `delivery_profile_sha256` name a source and delivery profile that do not exist;
  `warmup_buckets` is known only after the builder publishes the MOE strategy revision (step 5). → **Question Q2.**
- **This task:** the assembler accepts a `market_profile` file and lets `BoundRelease` apply its rules.

## What Phase B builds

Module `apps/api/src/edge_os_api/execution/inapp_binding_fill.py`, next to `inapp_trade_release.py`, because it
uses `complete_release` and `bind_release`. It reads files only and makes no request. Tests:
`apps/api/tests/execution/test_inapp_binding_fill.py`.

### A. Binding reads: input, output, hash, refusals

**Input** (`binding_reads.json`, written by the controller later, never by this module): schema
`edge-os.inapp-binding-reads-records/1`, key `operations`: the eleven records below, in this order. Each record has
exactly the keys of the existing chain store (`scripts/privy_unfunded_proof/chain_proof.py:417-419`): `op_id`, `method`,
`expect` (`"RESULT"`), `params`, `request_sha256`, `status`, `result`, `error`, `at` (RFC 3339 UTC, `Z`).
`request_sha256` is `sha256(json_bytes({"jsonrpc":"2.0","id":1,"method":m,"params":p}))`, the same rule as
`chain_proof.request_sha256`. `B` is the `number` of the `finalized` block read, as a hex quantity.

| # | `op_id` | Method | Params | Check |
| --- | --- | --- | --- | --- |
| 1 | `binding.chain_id` | `eth_chainId` | `[]` | `"0x8f"` |
| 2 | `binding.finalized_block` | `eth_getBlockByNumber` | `["finalized", false]` | `number`, `hash`, `timestamp` well formed |
| 3 | `binding.wmon_decimals` | `eth_call` | `[{"to": WMON, "data": "0x313ce567"}, B]` | `18` (release input decimals) |
| 4 | `binding.moe_decimals` | `eth_call` | `[{"to": MOE, "data": "0x313ce567"}, B]` | `18` (release output decimals) |
| 5 | `binding.wmon_balance` | `eth_call` | `[{"to": WMON, "data": "0x70a08231" + wallet word}, B]` | `>= approved_input_raw` |
| 6 | `binding.moe_balance` | `eth_call` | `[{"to": MOE, "data": "0x70a08231" + wallet word}, B]` | one uint256 word (recorded) |
| 7 | `binding.native_balance` | `eth_getBalance` | `[wallet, B]` | `>= gas.budget_raw` |
| 8 | `binding.wmon_allowance` | `eth_call` | `[{"to": WMON, "data": "0xdd62ed3e" + wallet word + entrypoint word}, B]` | one word (recorded) |
| 9 | `binding.pool_token0` | `eth_call` | `[{"to": POOL, "data": "0x0dfe1681"}, B]` | release `token0_address` |
| 10 | `binding.pool_token1` | `eth_call` | `[{"to": POOL, "data": "0xd21220a7"}, B]` | release `token1_address` |
| 11 | `binding.pool_reserves` | `eth_call` | `[{"to": POOL, "data": "0x0902f1ac"}, B]` | three words; both reserves `> 0` and `< 2**112`; `blockTimestampLast` at most the block timestamp |

Every `to` address and ABI word is lowercase; `eth_getBalance` sends the release `wallet_address` exactly as the
release spells it (checksum case). The wallet word is `"0"*24 + wallet[2:].lower()`, the form
`current_holdings.read_rpc_holdings` sends (`current_holdings.py:96-97`). `python -m
edge_os_api.execution.inapp_binding_fill plan …` prints these exact requests with `B` as `<FINALIZED_BLOCK>`.

**Output** (`edge-os.inapp-binding-reads/1`): `release_sha256`, `reads_sha256` (SHA-256 of the exact records file
bytes), `chain_id`, `block` (`number`, `hash`, `timestamp`, `read_at`: the `at` of the finalized read), `wallet_address`, `findings` (each balance, allowance
and decimals as raw decimal strings or ints; pool address, token0, token1, both reserves), `checks`
(`wmon_balance_covers_input`, `native_balance_covers_gas_budget`, both `true`), `shows`, `does_not_show` and
`fills_slot: null`. The artifact file is canonical JSON (sorted keys, no spaces) and its SHA-256 is the SHA-256 of
those bytes. `verify-reads` rebuilds the artifact from the records and compares bytes.

**Refusals** (stable codes, `BindingFillRefused`):

| Case | Code |
| --- | --- |
| Records file not the schema, missing/extra key, a repeated JSON key or a non-finite number anywhere, an `at` that is not ASCII `YYYY-MM-DDTHH:MM:SSZ`, wrong order, wrong `expect`/`method`, a status that is not one of `RESULT`, `RPC_ERROR`, `REPLY_LOST`, `SKIPPED` | `READS_RECORDS_INVALID` |
| A record's params differ from the plan at `B` (compared as canonical JSON bytes, so `0` is not `false`), or its `request_sha256` is not the hash of its own params (edited record) | `READS_RECORD_MISMATCH` |
| A status other than `RESULT`, a non-null `error`, or a missing result: never read as zero | `READ_UNAVAILABLE` |
| A malformed block, word or `at`; uppercase hex (one chain state has one artifact); `at` times out of order; a block timestamp after its own read or out of range | `READ_MALFORMED` |
| Chain id other than `143` | `READ_WRONG_CHAIN` |
| `B` below the release fill's `reserves.block_number`, or the finalized block older than the release's `max_input_age_seconds` at the time it was read, or a pass longer than that age, or a read at or after the release `valid_until` | `READ_BLOCK_STALE` |
| Token decimals other than the release's | `READ_DECIMALS_MISMATCH` |
| Pool token order other than the release's | `READ_POOL_MISMATCH` |
| WMON balance below `approved_input_raw` | `BALANCE_BELOW_INPUT` |
| Native balance below `gas.budget_raw` | `NATIVE_BELOW_GAS_BUDGET` |
| Artifact bytes differ from the rebuild (edited artifact or records) | `READS_ARTIFACT_MISMATCH` |

**What the reads artifact shows:** the state at block `B` as one observer reported it. **What it does not
show:** that `B` is final (Q3), that the balances are attributable to a position (Q1), that the state holds at
signing, or any market, valuation or cost claim.

### B. Binding fill: input, output, hash, refusals

**Input:** the authored release and its fill (completed with `complete_release`), the identity file (step 6),
zero or more `slot=path` proof artifact files, and an optional `market_profile` file. A slot is one of
`position_inventory`, `market`, `finality`, `exit_capacity`, `valuation`, `cost_model`.

**Each proof artifact** must be canonical JSON, an object with a string `schema`, `proof` equal to its slot, and
`release_sha256` equal to the completed release. The slot hash is the SHA-256 of the exact file bytes, the same
rule as the control proofs (`tests/execution/test_inapp_trade_release.py:645`). This envelope binds a file to its
slot and release; it says nothing about content, which is still Q1-Q6.

**Output:** `proof_sha256` per slot; the exact `binding.fill.json` object (all eight keys, `None` for an absent
optional slot); `binding_sha256` from `bind_release`; `derive_approval_slots_present` and the missing slots;
`market_profile_present`. These say only which slots are filled. They do not say the proofs are adequate
(Q1-Q6) or that market observation can run (no market source exists).

| Case | Code |
| --- | --- |
| Unknown slot, or a slot given twice | `FRAGMENT_SLOT_INVALID` |
| `position_inventory`, `market` or `finality` absent | `FRAGMENT_REQUIRED_PROOF_MISSING` |
| Artifact not bytes, not canonical JSON, or with a repeated key | `PROOF_ARTIFACT_NOT_CANONICAL` |
| Artifact `proof` or `release_sha256` differs, or no `schema` | `PROOF_ARTIFACT_MISMATCH` |
| Identity or profile refused by `BoundRelease` | its own code: `EXECUTION_RELEASE_INVALID`, or `INAPP_BINDING_FILL_INVALID` for a non-object identity |

## Live reads the controller must run later

All are reads; no signature, no send. Run them in one pass against the observer relay, after the release fill
(step 4) and the identity read (step 6), in the order of the table in section A:

1. `eth_chainId` → `0x8f`.
2. `eth_getBlockByNumber("finalized", false)` → block `B`. Every later read names `B` as a hex quantity.
3. WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a`: `decimals()`, `balanceOf(wallet)`,
   `allowance(wallet, 0xb3e6778480b2e488385e8205ea05e20060b813cb)` at `B`.
4. MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`: `decimals()`, `balanceOf(wallet)` at `B`.
5. `eth_getBalance(0x91BB52A63c91986813288965e4681FF111De1b63, B)`.
6. Pool `0x97199b34564911936bc850ac45ede785892b5aad`: `token0()`, `token1()`, `getReserves()` at `B`.

Save each as a record in the format above, then run `python -m edge_os_api.execution.inapp_binding_fill reads`.
Any further read a proof needs depends on the answers to Q1-Q6 and is listed with each option in the status file.
