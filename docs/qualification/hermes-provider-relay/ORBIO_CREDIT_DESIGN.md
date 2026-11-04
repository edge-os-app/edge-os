# Orbio CREDIT budget and per-call cost limit: design (not implementation)

Task `CLOUD-ORBIO-02-DESIGN`, builder-approved normal cloud session, 2026-10-30. Base `origin/integration/edge-os-mvp` at `275b3992fdc620094586906ac1eada47e7d3b0ad`, branch `cloud/orbio-02-credit-design`.

This note is a design. It approves nothing: no code change, provider, key, request, release, price or spending. Every `file:line` below is at the base commit. Settling a call at a provider-reported cost would change the accepted relay contract E1-COST1 (`CONTRACT.md` A6 E1-COST1, lines 247-252). That is a builder decision (section 3), not a routine implementation choice.

## 0. Sources and their limits

- Repository at the base commit: the files cited below.
- Orbio's public pages (`https://www.orbio.so`, `/developers`, `/llms.txt`, `/protocol/agents.md`, `/api/v1/tools`) were **not read**. In this session `www.orbio.so` did not resolve (`getaddrinfo ENOTFOUND`): the session's network policy does not allow the host. To read them, the host must be added to the session's allowed network domains. The only Orbio facts used here come from the task brief: **one CREDIT is worth USD 1 of usage**, and **tool calls take a `max_cost` argument**. The brief does not say what unit or precision `max_cost` has, what Orbio does when a call would go over it, or what cost a tool reply reports. These stay open (section 5).
- For context only (not in the base, not accepted): branch `origin/cloud/orbio-release-prep` (`446206c`), `docs/qualification/orbio-release/ORBIO_RELEASE_DRAFT.md`, records facts the builder gave from Orbio's documentation on 2026-10-22: chat completions at `api.orbio.so/api/v1/chat/completions`, an `X-Orbio-Balance` reply header, and `GET /api/v1/key` returning the balance. It also lists the open question of whether `usage.cost` on an Orbio reply is Orbio's own charge. This design relies on none of it.
- Vocabulary: `CONTEXT.md:37` lists "AI credits" as a term to avoid (under **Agent wallet**). This note says **CREDIT** only for Orbio's billing unit. The code already uses "credits" for something unrelated: **Nansen credits** (`usage/quota.py:42`, `core/settings.py:120,125`). A CREDIT is never a Nansen credit, and the two never share a field, column or label.

## 1. What exists today

### 1.1 Every cap that bounds model spend

| # | Cap | Scope | Unit | Value at base | Where it is enforced |
|---|---|---|---|---|---|
| C1 | Worst-case turn reservation | per model call (one turn = one attempt) | nano-USD (integer), from `TokenPrice` | `price.nano_usd(max_request_bytes + 64, max_output_tokens)` = (65,600 x 2 + 4,096 x 10) USD per million = **172,160,000 nano-USD (USD 0.17216)** for `hermes-first-call-1` | `scripts/hermes_interpretation/guarded_turn_runner.py:49-51` (margin `INPUT_TOKEN_MARGIN = 64`, `:29`); priced at `scripts/hermes_interpretation/spend_ledger.py:79-83`; record values `apps/api/src/edge_os_api/research/hermes_relay_composition.py:114` (`max_request_bytes` 65536, `max_tokens` 4096) and `:122-123` (prices 2 / 10) |
| C2 | Output-token limit `max_tokens` | per model call | tokens | fixed at the release's 4,096: every check requires **equality**, so it can never be lowered for one call | `guarded_turn_runner.py:46-47` (turn vs policy); `scripts/hermes_interpretation/provider_guard.py:116-118` (wire body, inside the job); `scripts/hermes_interpretation/hermes_turn_job.py:116-117` (Hermes' request); `scripts/hermes_provider_relay/relay_admission.py:167-168` (grant policy vs release); `relay_admission.py:282-283` (ACTUAL body vs release); the relay's own guard on the body under the grant's policy (`relay_service.py:384-387`, through `provider_guard.py:117`); and the build-time check that the release equals the policy (`relay_turn_runner.py:305-308`). The value comes from `hermes_interpreter.py:409-411` (`HermesTurn.max_output_tokens = config.max_output_tokens`) and goes into the job input at `guarded_docker_runner.py:1232-1235` |
| C3 | Owner cap | per owner, all of that owner's studies together | nano-USD, frozen in `usage_local.provider_spend_settings.owner_cap_nano_usd` (`research/provider_spend_tables.py:22`) | **USD 2.00** (`hermes_relay_composition.py:129`) | `research/provider_spend_ledger.py:199-201`, under the settings-row lock (`:106-128`) |
| C4 | Global cap | all owners together: "the one shared USD 2.00 model and data ceiling" | nano-USD, `global_cap_nano_usd` (`provider_spend_tables.py:21`) | **USD 2.00** (`hermes_relay_composition.py:128`) | `provider_spend_ledger.py:202-203` |
| C5 | Single-file ledger cap (SQLite, qualification and tests) | one ledger file | nano-USD (`spend_ledger.py:132-138`) | set by the caller | `spend_ledger.py:216-218` |
| C6 | Provider price ceiling on the wire | per token, provider side | USD per million tokens | `max_price {prompt: 2, completion: 10}` in the routing object (`hermes_relay_composition.py:117`); the snapshot rates must not exceed it (`:189-202`) | enforced by OpenRouter, not by Edge OS; the relay only checks that the body carries the record's routing object (`relay_admission.py:284-285`) |
| C7 | One open liability per study | per saved request (scope `intake:<id>`) | count | at most 1 RESERVED/UNKNOWN reservation per scope | `provider_spend_ledger.py:196-198` (`ScopeBlocked`); the scope comes from `hermes_relay_composition.py:330-335` |
| C8 | Turn count limits | per owner and global | count | 1 unsettled turn per owner, 2 across all owners, 10 new turns per owner per rolling hour | `research/turn_limits.py:21-24`, `:68-85`, `:87-92` |
| C9 | One provider request per turn | per model call | count | at most 1 admitted request per attempt; this is what makes C1 a worst case | `scripts/hermes_interpretation/provider_guard.py:107-108` (`physical_request_count_exceeded`, in the job); `hermes_turn_job.py:20` (`ADMITTED_REQUESTS = 1`) and `:118-119`; in the relay, only the single exclusive start `relay_service.py:397-400` (its guard at `:384-387` is built fresh for each request, so it checks the body's shape, not a count) |
| C10 | Provider-side spend cap (external) | the sponsor's or provider account allocation | provider units (for Orbio: the CREDIT balance) | not set in code | hosted gate `h8_provider_spend_cap` (`apps/api/src/edge_os_api/core/hosted_deployment.py:39`; `docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md` section 6) requires evidence that it exists; Edge OS does not enforce it |

There is **no per-study money cap and no per-grant money cap**. A study's spend is bounded only through C3/C4 (shared with the owner's other studies and, for C4, with every owner), through C7 (one call at a time) and through C1 for each call. The grant (`CONTRACT.md` 3.3, `relay_turn_runner.py:143-150`) carries the policy (`model`, `max_output_tokens`, `max_request_bytes`), an expiry and a MAC. It carries no amount. It does bind `max_output_tokens`, which C2 makes equal to the release's.

Bounds in the same files that are **not** model-spend caps, listed so that none is mistaken for one:

- `EDGE_OS_RESEARCH_BUDGET_*` (`core/settings.py:116-120`: provider requests 16, compute seconds 900, Nansen credits 50 per owner) and `EDGE_OS_USAGE_GLOBAL_*` (`:121-125`: 100,000 / 10,000,000 / 10,000). These are **counts** for investigation jobs (history and Nansen report jobs), not money. They are reserved through `usage/quota.py:192-224` and settled through `:227-257`, built in `research/investigation_jobs.py:140-154`, reserved at `:311-312` and `:408`, and shown by `GET /research/budget` (`main.py:448-451` -> `investigation_jobs.py:167-168` -> `quota.view`, `usage/quota.py:260-282`). Interpretation (model) turns do not use them.
- `cumulative_cap_usd: "0.75"` in `scripts/hermes_interpretation/qualification_identities.py:31`: an identity value of an earlier qualification package, not wired into the application.
- `MAX_USD_CEILING = Decimal("2.00")` in `execution/original_transaction.py:80` and `execution/inapp_trade_release.py:34`, and the `operator_trade` limits: trade notional, not model spend.
- The `hermes_relay_composition.py:16-17` docstring: a ledger cap sees one database only. The shared USD 2.00 ceiling still needs an external reconciliation before the first actual call. That obligation stands unchanged.

### 1.2 Where reservation and settlement happen

1. Turn admission: `TurnLimits.admission` (`turn_limits.py:50-65`) runs around the attempt insert. A refused turn writes no attempt and no reservation.
2. **Reservation**: `GuardedTurnRunner.run_turn` (`guarded_turn_runner.py:43-60`) calls `ledger.reserve` **before** the delegate runs (`:62`). Over a cap, `CapExceeded` returns `PROVIDER_FAILED` / `SpendCapReached` with request count 0 and the delegate is never called (`:52-53`). In the application the ledger is `PostgresSpendLedger.reserve` (`provider_spend_ledger.py:179-211`). It locks the settings row, refuses `ReservationExists` (`:189-191`) and `AttemptNotSaved` (`:192-195`), checks `ScopeBlocked` (`:196-198`), the owner cap (`:199-201`) and the global cap (`:202-203`), then inserts a RESERVED row recording `reserved_nano_usd`, `max_input_tokens` and `max_output_tokens` (`:205-209`; columns `provider_spend_tables.py:40-43`). "Committed" means SETTLED charges plus RESERVED and UNKNOWN reservations (`provider_spend_ledger.py:52-53`).
3. Grant: `RelayTurnRunner.run_turn` (`relay_turn_runner.py:126-155`) requires the ledger state RESERVED, writes one grant exclusively, and returns `UNKNOWN` / `RelayGrantExists` if a grant already exists (`:148-150`).
4. Send-once: the relay writes `started.json` exclusively before sending, and refuses a second start with `already_started` (`relay_service.py:393-401`). On restart it marks every started-but-unfinished attempt `unknown_restart` and never sends it again (`relay_service.py:228-240`, docstring `:17-19`).
5. **Settlement gate (E1-COST1)**: `RelayTurnRunner._cost_equals_charge` (`relay_turn_runner.py:205-222`). The reply's `usage.cost` (validated at `relay_admission.py:327-329`), rounded **up** to a whole nano-USD, must equal `price.nano_usd(prompt_tokens, completion_tokens)` and be at most the held liability. Otherwise the result is withheld as `UNKNOWN` / `RelayCostUnverified` (`:247-248`). An ACTUAL route requires the ledger's own `TokenPrice` (`:298-299`). The composition passes the same instance to both (`hermes_relay_composition.py:362-369`).
6. **Settlement**: `GuardedTurnRunner._account` (`guarded_turn_runner.py:76-97`). A count of 0 with the guard's own 0 calls `release_unsent`. A counted result calls `ledger.settle` with tokens, which charges `price.nano_usd(...)` (`provider_spend_ledger.py:213-225`, `:288-296`). Anything else calls `mark_unknown` and keeps the full reservation. The runner saves `spend_state` and `spend_charge_usd` into `observed` (`:94-96`). For UNKNOWN, `spend_charge_usd` is the **held liability**, not a charge (`:88-90`).
7. Shown per study: `public_attempt` exposes `spend {state, charge_usd}` (`interpretation_workflow.py:142`). `study_model_cost` (`:164-182`) adds up only SETTLED charges (`settled_charge`, `:156-161`), counts every other state as unknown, and returns `settled_usd: None` when nothing settled. The bundle field is `model_cost` (`interpretation_workflow.py:552`, `service.py:307`). The web shows it with `describeAttemptCost` / `describeModelCost` (`apps/web/lib/interpretation.ts:76-86`), rendered at `apps/web/components/InterpretationAttempts.tsx:15`, types `apps/web/lib/types.ts:85,87,147`. Tests: `apps/api/tests/test_study_model_cost.py`, `apps/web/tests/model-cost.test.tsx`.

## 2. Smallest design

Ground rules for all three parts:

- The ledger stays in integer nano-USD. Prices stay `TokenPrice`. The caps stay **USD 2.00 owner and USD 2.00 global**, frozen in the settings row and changed only by `change_caps` (`provider_spend_ledger.py:258-269`). No new cap and no new money table.
- Because 1 CREDIT = USD 1 exactly, 1 nano-CREDIT = 1 nano-USD. Converting is relabelling the same exact decimal string. No float, no rate and no rounding step is added. A different rate later would be a builder decision and a new design, not a setting.
- UNKNOWN is never zero. A call whose cost is not settled shows as unknown, and its held reservation counts as **used** in every remaining-budget figure.

### 2a. Show each study's budget and spend in CREDIT (display only)

There is no per-study cap (section 1.1), so a study's "budget" is the money its owner can still commit. The display says this budget is shared with the owner's other studies and with the global ceiling. A per-study cap would be a new product limit (open question Q1). It is not part of this design.

| File | Change |
|---|---|
| `apps/api/src/edge_os_api/research/provider_spend_ledger.py` | Add a read-only module function `spend_view(session, owner_id) -> dict`. Under no lock it reads the frozen settings row and the owner's and global sums, using the `LIABILITY` expression (`:52-53`) split by state. It returns nano-USD integers: `owner_cap`, `global_cap`, `settled`, `held` (RESERVED + UNKNOWN), `held_calls`, `available = min(owner_cap - owner_liability, global_cap - global_liability)`. It returns `None` when the settings row does not exist yet (the ledger was never used). That means "budget not set", not 0. It writes nothing and does not freeze the settings. |
| `apps/api/src/edge_os_api/research/interpretation_workflow.py` | `study_model_cost` (`:164-182`) also returns `unit: "CREDIT"` and `settled_credit`, the same exact string as `settled_usd`. It adds `held_credit`, the exact sum of the `charge_usd` of attempts whose state is UNKNOWN or RESERVED (the held liability, `guarded_turn_runner.py:88-90`), or `None`. `held_credit` is a lower bound and is labelled so: an attempt saved as `SETTLEMENT_NOT_RECORDED` has no charge (`guarded_turn_runner.py:91-93`) while its ledger row still holds the full reservation. Such an attempt is counted in `unknown_calls`, and the true held amount comes only from `spend_view`. `attempt_state` (`:552`) adds `model_budget` from `spend_view`, formatted with the existing exact-decimal path. Field names keep `usd` where the value is USD: CREDIT is a second label, not a replacement. |
| `apps/api/src/edge_os_api/research/service.py` | `load_bundle` (`:307`) passes `model_budget` through, next to `model_cost`. |
| `apps/web/lib/types.ts`, `apps/web/lib/interpretation.ts`, `apps/web/components/InterpretationAttempts.tsx` | Add `ModelBudget` and `describeCredit(amount)`, which reuses the exact `usd()` parser (`interpretation.ts:62-73`), strips its leading `$` (`:66`, `:72`) and prints `<amount> CREDIT`. Show spend as "spent 0.0074285 CREDIT (USD 0.0074285)". Show the budget as "available 1.8 of 2 CREDIT, shared by all your studies; 0.17216 CREDIT held by 1 call of unknown cost". With unknown calls, total spend reads "at least X CREDIT, N calls unknown", as `describeModelCost` already does (`:81-86`). With nothing settled it reads "unknown", never "0 CREDIT". |

### 2b. Cap `max_tokens` on every call so the worst case fits what remains

Rule: the reservation picks the call's output limit **inside the same locked transaction** that checks the caps, and writes it to the existing `max_output_tokens` column (`provider_spend_tables.py:43`).

```
headroom  = min(owner_cap - owner_liability, global_cap - global_liability)        # nano-USD, under the settings lock
input_max = max_request_bytes + INPUT_TOKEN_MARGIN                                  # unchanged worst-case input
out       = largest n <= release.max_output_tokens with price.nano_usd(input_max, n) <= headroom
refuse (CapExceeded, nothing written) if out < min_output_tokens
reserve price.nano_usd(input_max, out) and record max_output_tokens = out
```

Example with `hermes-first-call-1` prices: input worst case 131,200,000 nano-USD, 10,000 nano-USD per output token. With 150,000,000 nano-USD headroom, `out` = 1,880 and the reservation is 150,000,000. Below 131,200,000 + `min_output_tokens` x 10,000, nothing is reserved and nothing is sent. Today the same headroom would refuse the call outright, because the full 172,160,000 does not fit. This makes the last part of the USD 2.00 usable without raising the worst case. `min_output_tokens` is a release value, not a setting (Q2). It must be at least 1 (the release bound is 1..1,000,000, `relay_admission.py:89`). A value below 1 is refused when the runner is built, so a reservation can never record a limit the relay would refuse.

The value then travels with the call. Each equality check becomes "equal to this call's granted limit, and that limit is at most the release's":

| File | Change |
|---|---|
| `scripts/hermes_interpretation/spend_ledger.py` | `reserve` gains keyword `min_output_tokens: int | None = None`. With `None`, behaviour is byte-for-byte unchanged (an exact reservation, `:205-223`). With a value, it applies the rule above under `begin immediate`. `Reservation` gains `max_output_tokens: int`, which is additive. A new read method `reserved_output_tokens(attempt_id) -> int | None` returns the recorded column, because today only `state()` and `liability_usd()` are exposed. |
| `apps/api/src/edge_os_api/research/provider_spend_ledger.py` | The same keyword and rule in `reserve` (`:179-211`), under the settings lock, with the owner and global headroom, and the same `reserved_output_tokens` reader. |
| `scripts/hermes_interpretation/guarded_turn_runner.py` | Passes `min_output_tokens` from its constructor (default `None`, so existing callers are unchanged). After `reserve` it calls the delegate with `replace(turn, max_output_tokens=reservation.max_output_tokens)`. The check at `:46` stays: the incoming turn must still carry the release's value. |
| `scripts/hermes_interpretation/guarded_docker_runner.py` | The job's guard policy (`plan.policy`, `:384`; written at `:1235`) uses `turn.max_output_tokens`. A turn above the runner policy's value is refused before launch. |
| `scripts/hermes_interpretation/provider_guard.py`, `hermes_turn_job.py` | No logic change. They already compare with the job's policy and the job's `max_output_tokens` (`provider_guard.py:116-118`, `hermes_turn_job.py:116-117`), which now carry the call's value. |
| `scripts/hermes_provider_relay/relay_turn_runner.py` | The grant's policy uses `turn.max_output_tokens` instead of the fixed policy value (`:143-147`, policy at `:145`). Before writing the grant, it checks that the ledger row's `max_output_tokens` equals the turn's. If not, `RelayReservationMissing` with count 0. The build-time check (`:305-308`) is unchanged: the runner's policy stays at the release's value, and only each turn's grant carries the lowered limit. The limit actually granted goes into `observed` as `granted_max_output_tokens`, because the attempt's config identity keeps the release's value (`hermes_interpreter.py:117`). |
| `scripts/hermes_provider_relay/relay_admission.py` | Grant check (`:167-168`): `1 <= policy.max_output_tokens <= release.max_output_tokens` instead of equality. `body_refusal` (`:263`, check at `:282-283`) takes the grant's limit and requires the body's `max_tokens` to equal it. The MAC already covers the grant policy, so the job cannot raise it. |
| `scripts/hermes_provider_relay/relay_service.py` | Passes the grant's limit to `body_refusal` (call at `:389`). Refusal happens before `started.json`, as today. The relay's own guard (`:384-387`) already builds its policy from `grant["policy"]`, so it follows a lowered limit with no change. |
| `apps/api/src/edge_os_api/research/hermes_relay_composition.py` | Passes `min_output_tokens` (from the release definition) to the runner composition (`:362-369`). |
| `docs/qualification/hermes-provider-relay/CONTRACT.md` | A new amendment for the per-call limit. E1-COST1 is unchanged. |

Assumption to state in the amendment: the worst case relies on the provider stopping at `max_tokens`, including reasoning tokens. If a charge passes its reservation, the ledger already records `OVERRUN` (`spend_ledger.py:286-287`, `provider_spend_ledger.py:294-295`). That makes it visible but does not prevent it.

### 2c. Pass `max_cost` on future Orbio tool calls

No Orbio tool client exists at the base. This part fixes the rule a future adapter must follow. It is built only after the decision in section 3 and the open questions Q3-Q5.

- Before the request, reserve `max_cost` in the same shared ledger, so a tool call and a model call draw from one USD 2.00: `max_cost_nano = min(tool_ceiling_nano, headroom)`, rounded **down** to Orbio's accepted precision. If that is below the tool's minimum, refuse (`CapExceeded`), write nothing and send nothing. Send `max_cost` as CREDIT, which is the same decimal as USD.
- Ledger change needed: `PostgresSpendLedger.reserve` reserves only by tokens and only for a saved **interpretation attempt** (`provider_spend_ledger.py:181-195`). A tool call needs `reserve_amount(attempt_id, *, scope, subject_kind, amount_nano)` with its own saved subject row. This is a change for the ledger owner.
- Once started, the call is never resent: one attempt id reserves once (`ReservationExists`), and the adapter writes an exclusive started record before the request, following the relay's rule (`relay_service.py:397-400`).
- Settlement depends on section 3. Under option A, nothing settles a tool call (there is no token price), so it stays UNKNOWN at its full `max_cost` until an operator reconciles. Under option B or C, it settles at the reported cost only within the decided rule.

| File | Change |
|---|---|
| new `apps/api/src/edge_os_api/research/orbio_tool_calls.py` (name to confirm with the tool lane) | Reserve, exclusive start record, one request with `max_cost`, settle or UNKNOWN. |
| `apps/api/src/edge_os_api/research/provider_spend_ledger.py`, `provider_spend_tables.py` + a migration | `reserve_amount` and a subject kind. |
| `CONTRACT.md` or the tool lane's own contract | The `max_cost` rule. |

### 2d. Tests, written first and seen failing (RED) before each change

| Proves | Test (file) | RED at base because |
|---|---|---|
| **A call over budget is refused before sending** | `tests/hermes_interpretation/provider_safeguards/test_spend_ledger.py` and `apps/api/tests/test_provider_spend_ledger.py`: with headroom below `input_max` cost + `min_output_tokens`, `reserve(..., min_output_tokens=m)` raises `CapExceeded` and writes no row and no event. `tests/hermes_interpretation/provider_safeguards/test_guarded_turn_runner.py`: the same through `GuardedTurnRunner`, which returns `SpendCapReached`, count 0, and the fake delegate's call count stays 0. | the keyword does not exist |
| The limit is lowered, not the call refused, when a smaller limit fits | same ledger tests: 150,000,000 nano-USD headroom gives `max_output_tokens == 1880` and reservation `<=` headroom. The row's `max_output_tokens` column holds 1880. Concurrency: two reservations racing for the last headroom never commit more than the cap (PostgreSQL). | the keyword does not exist |
| The relay refuses a raised limit before any start | `tests/hermes_provider_relay/test_relay_admission.py`: a grant whose limit is above the release is refused. A body whose `max_tokens` differs from the grant's limit gets `body_max_tokens_mismatch`. `tests/hermes_provider_relay/test_relay_service_actual.py`: such a body leaves no `started.json` and no provider receipt. | equality with the release only; a lowered limit is refused |
| **A started call is never resent after a restart** | `tests/hermes_provider_relay/test_relay_turn_runner_actual.py`: reserve with a lowered limit, start, kill the host runner, re-run the same attempt with more headroom (a raised cap through `change_caps`). Expect `GuardedTurnRunner` to return the `ReservationExists` refusal (count 0, no new reservation, no new limit), no second grant (`RelayGrantExists` if one exists), and exactly 1 `started.json` and 1 provider receipt. `test_relay_service.py`: a relay restart marks the attempt `unknown_restart` and a re-sent channel request with the lowered limit gets `already_started`. | the lowered limit does not exist; the existing never-resent tests must stay green |
| **UNKNOWN is never shown as zero** | `apps/api/tests/test_study_model_cost.py`: UNKNOWN and RESERVED attempts give `settled_credit: None` when nothing settled, `held_credit` equal to their held liability, and are counted in `unknown_calls`. `spend_view` with no settings row gives `None`. `available` subtracts held liability. `apps/web/tests/model-cost.test.tsx`: an all-unknown study renders "unknown", never "0 CREDIT". A mixed study renders "at least ... CREDIT". | the CREDIT fields and `spend_view` do not exist |
| E1-COST1 unchanged | the existing `test_relay_turn_runner_actual.py` cost cases (`CONTRACT.md:251`: equal cost settles at 0.0074285; 0.0012, 0.02, 0.0074284, 0.0074285001, 0.06 stay UNKNOWN) stay green, plus one case with a lowered limit. | regression guard |
| `max_cost` (when 2c is built) | the adapter test: `max_cost` sent equals `min(ceiling, headroom)` rounded down; below the minimum the fake transport receives nothing; a missing or unparseable reported cost is UNKNOWN at `max_cost`; a restart after the start record sends nothing. | no adapter |

## 3. Decision for the builder: how a call settles

**Option A: keep E1-COST1.** A call settles only when the reported cost, rounded up to a nano-USD, equals the token-priced charge (`relay_turn_runner.py:205-222`).
- Risk: if Orbio's `usage.cost` includes a markup, a model price override, a cache discount or any fee, or is OpenRouter's upstream figure, then **every** model call is UNKNOWN. Each one holds its full reservation (up to USD 0.17216, or less with 2b). The USD 2.00 is then used up after about 11 full-size calls, and studies show only "unknown" spend. An UNKNOWN call also keeps its study's scope blocked (`spend_ledger.py:239`, `provider_spend_ledger.py:228`, C7), so each study is stuck after one mismatched call until an operator reconciles it. The roughly 11 calls are therefore spread over roughly 11 studies, one each. Nothing is ever undercounted. Tool calls, which have no token price, can never settle and stay held at `max_cost`.
- Change: none to settlement.

**Option B: extend E1-COST1 to settle at the Orbio-reported cost** (rounded up to a nano-USD, at most the held reservation).
- Risk: the ledger trusts a number from the provider. If `usage.cost` is not Orbio's own charge (open in the release draft), the ledger records **less** than Orbio deducts, and real spend can pass the USD 2.00 without any local cap noticing. It also changes both accepted ledgers (`spend_ledger.py`, `provider_spend_ledger.py`: a `settle_reported` path), the `GuardedTurnRunner` settlement and a contract amendment. That is ledger-owner work.

**Option C: settle at the higher of the reported cost and the token-priced charge, only after evidence.** Not before a qualifying paid call shows balance-before minus balance-after equal to `usage.cost` exactly.
- Risk: it still trusts the provider when its figure is above the token charge. But the charge is never below the known price, so an undercount needs Orbio to report less than it deducts **and** charge more than its listed price. It needs the same ledger work as B, plus one approved paid observation.

**Recommendation: A now, C later.** Keep E1-COST1 unchanged for model calls until a builder-approved paid call proves `usage.cost` equals Orbio's balance change. Then adopt C as a reviewed contract amendment, not B. B's failure mode is silent overspend past the shared ceiling, while A's and C's is visible held liability. Parts 2a and 2b do not depend on this decision and can proceed under A. Part 2c's settlement does depend on it.

## 4. Overlap with CLOUD-ORBIO-01 (`cloud/orbio-01-route`)

That branch is **not on the remote** at the time of writing (`git fetch origin cloud/orbio-01-route`: "couldn't find remote ref"), so its file list was not checked. The overlap below is inferred from its task (changing the relay route) and from the files the earlier route branches touched (`origin/cloud/orbio-02-release-destination` and `origin/cloud/orbio-release-prep`: `relay_admission.py`, `relay_supervisor.py`, `egress_gateway.py`, `CONTRACT.md`, `tests/hermes_provider_relay/*`). Before starting, compare it with the merged branch's real diff.

| Part | Files | Overlap | Order |
|---|---|---|---|
| 2a display | `provider_spend_ledger.py` (new read function only), `interpretation_workflow.py`, `service.py`, web files, their tests | none expected | can start now |
| 2b per-call limit, ledger and runner | `spend_ledger.py`, `provider_spend_ledger.py` (`reserve`), `guarded_turn_runner.py`, `guarded_docker_runner.py` | none expected | can start now |
| 2b per-call limit, relay side | `relay_admission.py` (`:167-168`, `:263`, `:282-283`), `relay_service.py`, `relay_turn_runner.py`, `hermes_relay_composition.py`, `CONTRACT.md`, `tests/hermes_provider_relay/*` | **yes**: the same files a route change edits (release record, body checks, composition, contract amendments) | **wait for CLOUD-ORBIO-01 to merge**, then rebase |
| 2c `max_cost` | new adapter, ledger `reserve_amount`, migration, contract | contract only | wait for section 3 and Q3-Q5; the contract text waits for CLOUD-ORBIO-01 |

The ledger half of 2b is harmless alone, because the default `min_output_tokens=None` changes nothing. It should still merge together with the relay half, so that no released path reserves a lowered limit that the relay then refuses.

## 5. Open questions

- Q1: Is a study's budget the owner's shared USD 2.00 (this design), or does the builder want a per-study cap? A per-study cap is a new product limit.
- Q2: `min_output_tokens` for `hermes-first-call-1`: below what output limit is a call not worth making? It belongs in the release definition.
- Q3: Orbio `max_cost`: its unit (assumed CREDIT), precision, whether it bounds the whole call including fees, and what Orbio does when it would be exceeded (refuse before work, or stop and charge the partial cost).
- Q4: What cost a tool reply reports, and whether a cost lookup or the balance (`X-Orbio-Balance`, `GET /api/v1/key`, per the unaccepted release draft) can reconcile it.
- Q5: Read Orbio's public pages once `www.orbio.so` is allowed in the session's network settings, and replace section 0's brief-only facts with dated quotes.
- Q6: Vocabulary: add **CREDIT** (Orbio's unit, USD 1 of usage, never Nansen credits, never "AI credits") to `CONTEXT.md`? That is a glossary decision for the builder.
