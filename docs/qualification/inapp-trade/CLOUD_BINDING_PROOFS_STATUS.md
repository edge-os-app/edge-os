# CLOUD-BINDING-PROOFS status

Task `CLOUD-BINDING-PROOFS`, builder-approved normal cloud session, 2026-10-30. Base `275b399`
(`origin/integration/edge-os-mvp`). Branch `cloud/binding-proofs` (normal pushes only; no PR, no main or
integration push). No network, RPC, key, wallet, signer or provider call was made.

**Final SHA:** recorded in the last section (the commit that adds it can not contain its own hash).

## Outcome

- Phase A: [`BINDING_PROOFS.md`](BINDING_PROOFS.md). For all seven items it gives the code that requires them,
  the repository's meaning and the gaps, with file:line.
- The repository defines the **form** of every item and the consumer of the market proof. It defines the
  **content** of none of the six proofs. So no proof builder was written: each would decide a product question
  below. `market_profile` has a defined form but its values name a source that does not exist.
- Phase B builds what is defined (`apps/api/src/edge_os_api/execution/inapp_binding_fill.py`):
  - `plan` / `reads` / `verify-reads`: the exact chain reads at one finalized block, and an offline checker that
    turns the recorded reads into one canonical, hashed artifact (`edge-os.inapp-binding-reads/1`). It fills no
    slot; the proofs would cite it.
  - `fragment`: the step-6 `binding.fill.json` assembler. It hashes the proof artifact files, checks each one names
    its slot and the completed release, binds with `bind_release`, and prints each `*_proof_sha256`, the fill and
    `binding_sha256`. `derive_approval_slots_present` and `market_profile_present` only say which slots are
    filled.
- **Release blocker found.** The worker decides every action from a market observation and ends the job
  `OBSERVATIONS_UNAVAILABLE` without one (`execution/worker.py:380-383, 417-420`). No market source exists in `src`.
  So Q2 blocks the in-app trade even after the other proofs exist.

## Open product questions (builder)

Each has options and a recommendation. The recommendation is not a decision.

### Q1. What does `position_inventory_proof_sha256` prove for a one-entry release?

The repository's meaning is sale permission from attributed inventory (`CAPABILITY_MATRIX.md:38`, EXIT-CAP-Q01),
which is `UNSUPPORTED` at the independent layer. This release has one ENTRY and no EXIT, and
`controlled-action-feasibility/CONTROLLED_ACTION_FEASIBILITY.md:158` says the restriction "does not apply to one controlled qualification action that does not
claim exit coverage". That supports a statement-type proof (A or C) rather than B.

- **A. Start-state host proof (recommended).** Cites the binding reads artifact (WMON >= input, MOE baseline,
  WMON allowance to the entrypoint, native >= gas budget, all at finalized block `B`) and the saved ledger read
  showing no open position for this agent, wallet, network and revision (the worker's own query,
  `worker.py:385-392`). Evidence class `LOCAL_TESTED` host check; it states that the independent layer stays
  `UNSUPPORTED`. Extra input: one PostgreSQL read of `positions` (controller, with the identity read).
- **B. Qualified inventory mechanism (EXIT-CAP-Q01).** Blocks this release until the enforcement design is
  qualified.
- **C. Builder decision artifact.** As the `DECISION_ACCEPTED` controls: reason
  `POSITION_INVENTORY_NOT_INDEPENDENTLY_ENFORCED`, citing the same reads. Needs a reviewed rule for where the
  decision is registered, since the binding has no decision registry.

### Q2. What market source, market proof and `market_profile` does the in-app trade use?

`market_proof_sha256` must equal the source's `provenance.qualification_proof_sha256` (`provider_ports.py:519`);
the profile names `source_id`, `delivery_profile_sha256`, `warmup_buckets` and a collection limit at most 60 s.
"Research history, Nansen context and delayed replay cannot become this feed through a label"
(`CONTROLLED_EXECUTION_RUNTIME.md`).

- **A. A forward pool-reserves source (recommended).** A new `MarketObservationPort` that reads the pinned pool's
  `getReserves()` at the finalized block for each five-minute bucket through the observer relay. The proof
  qualifies its delivery profile (block-bound reads, `finalized`, collection age). A separate implementation
  lane; it also needs the published revision's `warmup_buckets` (step 5).
- **B. Remove the observation requirement for the builder-triggered one-action path.** A reviewed change to the
  worker and `ControlledRuntime`; the market proof would then be a decision artifact. Outside this task's paths.
- **C. Keep the action strategy-triggered but warm up from research history.** Refused by the runtime document;
  listed only to rule it out.

### Q3. What qualifies the finality the binding names?

The runtime reads the RPC `finalized` tag (`current_holdings.py:78`). No document defines the proof.

- **A. Documented rule plus a consistency read (recommended).** Cite Monad's documented finality rule (read
  through Context7 or the official docs when the proof is written), and record at one time:
  `eth_getBlockByNumber("finalized")` → `F`, `eth_getBlockByNumber("latest")` → `L`, and
  a second `eth_getBlockByNumber(hex(F.number))` on the observer relay at least one minute later. The proof shows
  the same hash for `F` both times and `F <= L`. Only the observer relay serves `eth_getBlockByNumber`
  (`RPC_RELAY.md:116`; the broadcast relay refuses it), so a cross-relay check would need a relay change first.
  It does not show irreversibility beyond the cited rule.
- **B. Documented rule only.** Weaker; nothing ties the relays to it.
- **C. A decision artifact `FINALITY_TAG_TRUSTED`.**

### Q4. What does `exit_capacity_proof_sha256` prove when the release grants no exit?

- **A. A no-exit statement (recommended).** States that the release grants no EXIT (`accounting.py:114`,
  `limits.actions` 1, steps approve/swap/revoke), that the MOE stays in the wallet, and that the builder exits by
  owner action outside the app. It claims no exit capacity. Supported by `controlled-action-feasibility/CONTROLLED_ACTION_FEASIBILITY.md:158`
  (this action "does not claim exit coverage").
- **B. Qualify real exit capacity (EXIT-CAP-Q01).** Blocks this release.
- **C. Change `derive_approval` to accept `None` for an entry-only release.** A code change outside this task.

### Q5. What does `valuation_proof_sha256` prove?

- **A. Pool-spot mark at the binding block (recommended).** WMON per MOE from the binding reads' reserves, with
  the 1.6% program fee stated, in `QUOTE_PER_BASE` units; labelled a mark, not a fill or exit price.
- **B. The quote formula output at the release reserves.** Duplicates `approved_min_output_raw`.
- **C. A no-valuation statement**, since the release has no EXIT mark.

### Q6. What does `cost_model_proof_sha256` prove?

- **A. Restate the release's own worst case (recommended).** Input plus all four step limits at
  `max_fee_per_gas`, at the MON price the builder confirms on the day (not the unapproved `0.02`), at most
  USD 2.00, plus the program fee and the observed 1.00% and 0.35% fee transfers. Needs the builder's price input.
- **B. Measured costs.** Needs the receipts, so only after the trade; cannot be in the binding.
- **C. A decision artifact citing `complete_release`'s `USD_CEILING_EXCEEDED` check only.**

## Live chain reads the controller runs later

All reads, in one pass against the observer relay, after the release fill (step 4) and the identity read
(step 6). `B` is the number of the `finalized` block from read 2; every later read names `hex(B)`.

| # | Method | Contract | Call |
| --- | --- | --- | --- |
| 1 | `eth_chainId` | - | expect `0x8f` |
| 2 | `eth_getBlockByNumber` | - | `["finalized", false]` |
| 3 | `eth_call` | WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a` | `decimals()` `0x313ce567` |
| 4 | `eth_call` | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777` | `decimals()` |
| 5 | `eth_call` | WMON | `balanceOf(0x91BB52A63c91986813288965e4681FF111De1b63)` `0x70a08231` |
| 6 | `eth_call` | MOE | `balanceOf(wallet)` |
| 7 | `eth_getBalance` | - | `[wallet, hex(B)]` |
| 8 | `eth_call` | WMON | `allowance(wallet, 0xb3e6778480b2e488385e8205ea05e20060b813cb)` `0xdd62ed3e` |
| 9 | `eth_call` | Pool `0x97199b34564911936bc850ac45ede785892b5aad` | `token0()` `0x0dfe1681` |
| 10 | `eth_call` | Pool | `token1()` `0xd21220a7` |
| 11 | `eth_call` | Pool | `getReserves()` `0x0902f1ac` |

`python -m edge_os_api.execution.inapp_binding_fill plan --authored … --fill …` prints these exact params. Save
them in `edge-os.inapp-binding-reads-records/1` (format in `BINDING_PROOFS.md`), then run `reads`. Additional
reads per option: Q3 A adds `eth_getBlockByNumber("latest", false)` and, at least one minute later,
`eth_getBlockByNumber(hex(F), false)`, both on the observer relay. Q1 A adds one PostgreSQL `positions` read.
Q2 A's source reads the pool's `getReserves()` (`0x0902f1ac` on `0x97199b34564911936bc850ac45ede785892b5aad`) at
the finalized block of every five-minute bucket; those reads belong to that source's own implementation lane and
are not run for the binding. Q4-Q6 option A need no further chain read (Q5 A uses read 11; Q6 A needs the
builder's MON price).

## Commands

```sh
cd apps/api
.venv/bin/python -m edge_os_api.execution.inapp_binding_fill plan \
  --authored ../../docs/qualification/inapp-trade/release.authored.json \
  --fill ../../docs/qualification/inapp-trade/release.fill.json
.venv/bin/python -m edge_os_api.execution.inapp_binding_fill reads --authored … --fill … \
  --records <binding_reads.json> --out <new binding_reads.proof.json>
.venv/bin/python -m edge_os_api.execution.inapp_binding_fill verify-reads --authored … --fill … \
  --records <binding_reads.json> --artifact <binding_reads.proof.json>
.venv/bin/python -m edge_os_api.execution.inapp_binding_fill fragment --authored … --fill … \
  --identity <identity.json> --proof position_inventory=<file> --proof market=<file> --proof finality=<file> \
  [--proof exit_capacity=<file> …] [--market-profile <file>] --out <new binding.fill.json>
```

Every refusal prints `{"status": "REFUSED", "code": …}` and exits 2. `--out` never replaces a file.

## Files

| File | Change |
| --- | --- |
| `docs/qualification/inapp-trade/BINDING_PROOFS.md` | New: Phase A analysis. |
| `docs/qualification/inapp-trade/CLOUD_BINDING_PROOFS_STATUS.md` | New: this file. |
| `apps/api/src/edge_os_api/execution/inapp_binding_fill.py` | New: reads plan and checker, fill assembler, CLI. |
| `apps/api/tests/execution/test_inapp_binding_fill.py` | New: pass and refusal tests with fake records. |

Not changed: `operating_release.py` registries, `release.authored.json`, the sealed control proofs, settings,
`core/hosted_deployment.py`, `hosted_record_tool.py`.

## Tests and reviews

RED first: before the module existed, `tests/execution/test_inapp_binding_fill.py` failed at collection
(`ModuleNotFoundError: edge_os_api.execution.inapp_binding_fill`). The review-regression tests added for candidate
2 were run against the candidate-1 module first: 18 failed, 95 passed.

Final results, reviews and the final SHA are in the "Final candidate" section below.
