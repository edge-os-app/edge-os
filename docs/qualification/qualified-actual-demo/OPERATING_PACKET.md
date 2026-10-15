# Qualified actual demo: operating packet (PROPOSED)

Task `QUALIFIED-DATA-PACKET-L4-20261015-LOCAL-v1`. Base `c34bd3959e51696193c1a031652a62fa67829e28`. Status: **PROPOSED. This packet authorizes no operation.** No credential was read and no provider, model, RPC, account or payment request was made to write it. Every actual item is `NOT_RUN`. Status words are defined in [QUALIFICATION_GAPS.md section 1](QUALIFICATION_GAPS.md#1-status-words).

This packet describes one bounded application run for option B of [QUALIFICATION_GAPS.md](QUALIFICATION_GAPS.md): a forward 20-minute MOE/WMON window and one Nansen report. It replaces nothing in the earlier [actual research operating packet](../actual-research-demo/OPERATING_PACKET.md). Its sections 7 to 10 keep their meaning here unless this packet names a different value.

## 1. Preconditions, in order

The run cannot start until every item below holds. Each item needs its own approval or evidence.

1. The builder approves option B and the decisions in [QUALIFICATION_GAPS.md section 7](QUALIFICATION_GAPS.md#7-builder-decisions-once-facts-exist).
2. A separately reviewed forward recorder exists, and the approved [source-fact packet](SOURCE_FACT_PACKET.json) ran with every phase complete. Its outputs fill the `<…>` values below.
3. MOE mechanics qualify under a builder-approved definition. If they do not, `fee_transfer_semantics` is not `QUALIFIED`, the expected verdict is `LIMITED`, and section 7 applies.
4. Lane 2 (application composition) mounts the release with credential delivery, as the earlier packet section 9 items 1 and 2 describe. That work is outside this lease.
5. Owner A's request capacity is at least 66 unconsumed requests before the run (section 5).
6. Data-use rights and retention are decided (section 6).

## 2. Release values

One release holds both parts, so the API and the worker share one SHA-256. `release_id` `actual-qualified-demo/1`, `kind` `ACTUAL`. The SHA-256 is `NOT_COMPUTABLE` until every `<…>` value is filled. After that, `core/research/operating_release.release_sha256(release)` computes it locally with no network. The builder approves that exact value, and lane 2 adds it to `APPROVED_RELEASES`.

### 2.1 History part

| Field | Value | Status |
|---|---|---|
| `source_id` | `actual-moe-wmon-fwd20m/1` | `PROPOSED` |
| `envio_endpoint`, `envio_credential_slot` | `https://monad.hypersync.xyz`, `envio_hypersync_bearer` | As the earlier packet |
| `quicknode_host`, `quicknode_credential_slot` | `<QuickNode host>`, `quicknode_monad_url` | Host `NEEDS_FACT`; publishing it `NEEDS_APPROVAL` |
| `rpc_methods`, `source_version` | `eth_chainId`, `eth_getTransactionReceipt`; `envio-hypersync/1` | `FIXED_BY_CODE` |
| Profile window | `[T0, T0 + 1,200 s)` | `PROPOSED` |
| Profile availability | `{"model": "OBSERVED_DELIVERY", "basis_evidence": "SOURCE_DELIVERY_RECORD"}` | Only when source-fact P3 recorded a delivery for all 4 buckets and D3 is accepted. Otherwise `ASSUMED_DELAY` (the expected verdict is then `LIMITED`). `qualify` never reads `delivery_records`, so this rule is the only guard against a false `QUALIFIED` |
| Profile finality | `depth_blocks` 2, basis `DOCUMENTATION` | As the earlier packet |
| Orientation | `QUOTE_PER_BASE` (WMON per MOE) | `NEEDS_APPROVAL` |
| `scan` | `from_block` `<B_PRE>`, `to_block_exclusive` `<B_POST + 1>` | From source-fact P3 block headers |
| `corroboration_sample_size` | 61 | `PROPOSED` |

`limits` (equal to the declaration's `resource_bounds`):

| Limit | Value | Code ceiling | Reason |
|---|---|---|---|
| `max_pages` | 2 | 64 | About 4,000 blocks at 10,000 per page is 1 page; 1 spare |
| `provider_requests` | 64 | 64 | 2 + 1 + 61 = 64, the `_check_history` minimum |
| `max_rows` | 2,000 | 10,000 | Far above 61; extra rows only lower the verdict |
| `max_bytes` | 4,194,304 | 4,194,304 | Schema maximum |
| `deadline_seconds` | 600 | 3,600 | One saved job deadline |
| `compute_seconds` | 600 | 600 | Equal to the deadline |

`client_bounds`: `deadline_seconds` 120, `connect_timeout_seconds` 15, `max_response_bytes` 2,097,152, `max_request_bytes` 65,536, `max_blocks_per_page` 10,000. These are the earlier packet's values and its rules.

`provider_facts`. Each value is declared only when the named source fact exists. Otherwise the weaker value in the last column is declared, and the expected verdict drops.

| Fact | Declared value | Evidence | Weaker value if evidence is missing |
|---|---|---|---|
| `pool_tokens` | `CORROBORATED_READ` | Source-fact P1 receipt, P1 log, P4 reads agree | `SINGLE_READ` |
| `pool_venue` | `CORROBORATED` | P1 receipt, P1 log, P1 `factory()` agree | `SINGLE_SOURCE` |
| `decimals` | Base and quote: `window_start`, `window_end`, `current` all `READ` | P4 (start) and P5 (end, current) reads | `NOT_READ` for each missing read |
| `fee_transfer_semantics` | `QUALIFIED` | P6 evidence, written finding, decision D5 | Not `QUALIFIED` |
| `finality_at_collection` | `OBSERVED_FINAL` | P5 finalized number ≥ `B_POST + 2` | `FINALIZED_BY_DEPTH` |
| `delivery_records` | One time per bucket start | P3 | Any missing bucket: declare the profile `ASSUMED_DELAY` instead (row above) |
| `feasibility_claim` | QUALIFICATION_GAPS.md section 5.3 claim, floors 1 and 1 | Decision D6 | No floors: `UNDECLARED` |
| `collected_at_utc` | P5 finalized read time | Decision D3 | Undecided: the release cannot be frozen |
| `archive_height` | P5 latest number | P5 | Undecided: the release cannot be frozen |

The synthetic fixture `native-syn-qualified/1` declares strong values without evidence. None of its values may be copied here.

### 2.2 Nansen part

As the earlier packet section 4.2, with these changes:

| Field | Value | Status |
|---|---|---|
| `window` | `from` `T0 − 86,400 s`, `to` `T0 + 1,200 s` (inclusive cutoff, flows only) | `PROPOSED` |
| `limits` | `max_requests` 2, `max_pages` 2, `max_bytes` 2,000,000, `max_credits` `"6"`, `per_page` 100 | Unchanged |
| `deadline_seconds`, `compute_seconds` | 300, 300 | Unchanged |

The holders endpoint returns current holders with no date range. Its result describes the collection time, not the window. The report must say so.

## 3. Request keys and operation sequence

No step retries automatically. A repeated key returns the original job. A new key needs a new approval.

1. Lane 2 freezes the release, records its SHA-256 and mounts it. API and worker both call `server_research_runtime`.
2. Record the SHA-256 from `GET /v1/research/history-sources` from the API and from the worker log. They must be equal.
3. Owner A saves one declaration for `actual-moe-wmon-fwd20m/1`, direction `DESCRIPTIVE`, one `DESCRIPTIVE` partition `[T0, T0 + 1,200 s)`, `resource_bounds` equal to the release limits.
4. Start the history job with `request_key` `actual-qualified-demo-history-1`. The worker calls: page(s), `eth_chainId`, then one receipt per record.
5. Start the Nansen report with `request_key` `actual-qualified-demo-nansen-1` and the exact release request.
6. Read the saved verdict. Continue to step 7 only if it is `QUALIFIED`. Otherwise save a replay attempt for the refusal record and stop (section 7).
7. Only for a `QUALIFIED` dataset: run one hypothetical replay with `request_key` `actual-qualified-demo-replay-1`, inside the dataset window, starting at a scheduled decision point after the strategy warm-up. Under the accepted replay engine every order is expected to be saved as `FILL_UNAVAILABLE` with `LATE_INPUT`, because observed delivery comes after bucket end ([QUALIFICATION_GAPS.md section 5.5](QUALIFICATION_GAPS.md#55-replay-timing-on-an-observed-delivery-dataset)). Any fill that does appear shows the label `simulated fills`.
8. Reopen every result. Restart the API and the worker. Reopen again. Then run the proofs in section 8 and the reconciliation.

## 4. Nansen evidence needed before the run

| Fact | Current evidence | Still needed |
|---|---|---|
| Monad support | Chain coverage marks Monad for Token God Mode; `tgm/holders` and `tgm/flows` accept `monad` (`PUBLIC_DOC`, [chain coverage](https://docs.nansen.ai/getting-started/chain-coverage), read 2026-10-15) | MOE token coverage. Only an actual reply shows it. A reply that shows no MOE coverage is a scope conflict for the builder; no token or chain substitution |
| Holders versus flows | Holders is a current snapshot; flows takes a date range | Nothing more |
| Credits | `tgm/holders` 5, `tgm/flows` 1, holders with premium labels 150, on Free and Pro (`PUBLIC_DOC`, [credits guide](https://docs.nansen.ai/about/credits-and-pricing-guide)). `NansenClient` pins `premium_labels` false | The account's plan and balance (builder statement, no key) |
| Plans and price | Pro USD 69 per month, or USD 49 per month billed annually, 2,000 credits refilled monthly. Free: 100 one-time credits, then a daily top-up to 10 (`PUBLIC_DOC`, [credits guide](https://docs.nansen.ai/about/credits-and-pricing-guide), read 2026-10-15) | Which plan the account has. USD per credit on Pro monthly is 69 / 2,000 = USD 0.0345, so 6 credits ≈ USD 0.207 (`INFERENCE`) |
| Rate limits | Free 15 per second and 300 per minute; Pro 75 and 1,500 (`PUBLIC_DOC`, [rate limits](https://docs.nansen.ai/getting-started/rate-limits.md)) | Nothing for 2 calls |
| Credit headers | Docs list `X-Nansen-Credits-Used` and `X-Nansen-Credits-Remaining` | Whether `X-Nansen-Credits-Cost` and `X-Request-Id`, which `NansenClient.RETAINED_HEADERS` reads, are sent. If absent, the request-id proof uses the saved request hash and the account usage page instead |
| Rights | API terms (published 2026-10-01): licence "solely for your internal business purposes"; "Redistribution of raw, bulk, or aggregated Nansen Data is prohibited without our prior written consent", "except where expressly permitted in our Data Redistribution Guidelines"; attribution "Powered by Nansen" or "Data provided by Nansen"; no cached copies "beyond timeframes specified in the documentation"; delete on termination ([API terms](https://nansen.ai/legal/api), read 2026-10-15). The [Data Redistribution Guidelines](https://docs.nansen.ai/guides/data-redistribution-guidelines) (updated 2025-11-18, read 2026-10-15) list `tgm/flows` as "Allowed", attribution required, and `tgm/holders` "with smart money filter" as "Restricted". They do not list `tgm/holders` without that filter, which is the query here, and state no cache period | Flows: public display with attribution appears permitted. Holders: written consent or a Nansen statement for the unfiltered query, or no public display. The cache timeframe is unknown. A hosted judge page or video counts as display to third parties (`INFERENCE`) |

## 5. Owner, global and money limits

| Resource | History | Nansen | Total | Default owner cap | Needed |
|---|---|---|---|---|---|
| `provider_requests` | 64 | 2 | 66 | 16 | Cap ≥ 66 (`NEEDS_APPROVAL`, settings change outside this lease, before first use) |
| `compute_seconds` | 600 | 300 | 900 | 900 | Fits |
| `nansen_credits` | not reserved | 6 | 6 | 50 | Fits |

Global defaults (100,000 requests, 10,000,000 s, 10,000 credits) fit. Caps freeze at first use; a later change pauses new reservations (`quota_cap_mismatch`). Capacity never renews: available = cap − reserved − consumed − unknown, and a settlement moves used requests to `consumed` for good (`usage/quota.py`). So owner A needs 66 unconsumed requests; if owner A already used capacity, the cap must be that use plus 66. One run then uses it up. A second approved attempt also needs an operator cap change recorded with `python -m edge_os_api.usage.quota set-cap`. The no-repeat rule in section 7 still applies first.

**Money (`PROPOSED` allocation of the recorded USD 2.00 model and data ceiling; this is an input, not spending authority).**

| Item | Proposed ceiling | Basis |
|---|---|---|
| Hermes model calls | USD 0.50 | Separate relay packet; unchanged from the earlier packet |
| QuickNode, source facts and run | USD 0.00 above the plan | 18 + 62 = 80 calls × 30 = 2,400 credits. Build overage is USD 0.62 per million credits ([pricing](https://www.quicknode.com/pricing), read 2026-10-15), so even fully billed this is about USD 0.0015 (`INFERENCE`). Stop on any quota message |
| Envio HyperSync, source facts and run | USD 0.00 above the plan | 9 + 2 = 11 requests. HyperSync limits rate, not monthly volume (`PUBLIC_DOC`, [pricing](https://envio.dev/pricing/hypersync)). Stop on 429 |
| Nansen | 6 credits, at most USD 0.25 equivalent | About USD 0.207 on Pro monthly; Free plan cash cost 0. x402, MPP, premium labels and payment fallbacks stay refused |
| Unallocated reserve | USD 1.25 | Not spent without a new approval |
| **Total** | **USD 2.00** | |

## 6. Rights and retention

| Provider | Published terms (read 2026-10-15) | Decision needed |
|---|---|---|
| Nansen | See section 4. Internal use only; redistribution needs written consent; attribution required; cache limited to documented timeframes | `NEEDS_APPROVAL`: written consent or no public display; retention window |
| Envio | Terms last updated 2025-02-06 describe HyperSync as a read-only API and have no clause on reuse or display of returned data ([terms](https://docs.envio.dev/docs/terms-of-service)) | `NEEDS_FACT`: confirm with Envio if public display matters; retention window |
| QuickNode | [Terms of Use](https://www.quicknode.com/terms), last updated 2025-12-01: section 3, "This license does not include a right to use any of the content and information"; section 7(v) and (viii) bar distributing or making derivative works of the QuickNode Products. No clause addresses reuse or retention of RPC responses | `NEEDS_FACT`: a short question to QuickNode or the account owner on storing and showing RPC results; retention window |

Chain data is public, but provider terms can still limit how a provider's output is stored or shown (`INFERENCE`). The saved datasets keep ids, counts, hashes and ranges in shared evidence. Raw responses stay out of shared documents.

## 7. Stop, failure, `UNKNOWN` and no-repeat rules

The earlier packet's section 7 applies unchanged, including every stop condition and the `UNKNOWN` liability list. These additions apply:

- If the saved overall verdict is not `QUALIFIED`, do not run a replay. Save one replay attempt only to record `DATASET_COVERAGE_UNPROVEN`. Report the verdict and its reasons.
- If the history job records more than 61 records, corroboration is `SAMPLED` and the verdict is `LIMITED`. This is a valid result, not a failure. Do not rerun with a narrower window under the same approval.
- If the source-fact packet stopped in any phase, do not freeze the release with the stronger value for that fact.
- A failed or `UNKNOWN` history or Nansen job is not repeated. A second attempt is a new approval with a new key, a new window and new source facts.
- A replay is a calculation on saved data. It makes no provider call and no trade.
- Every chosen `T0`, including abandoned ones, stays in the private attempt log named in the source-fact packet. A later claim about a qualified window cites that log, so a successful window is never shown without the attempts that failed.

## 8. Required proof

Every row is `NOT_RUN`. The earlier packet's section 8 rows apply to this run. These rows are added or changed:

| Proof | Required observation |
|---|---|
| Source facts | The source-fact outputs, their request and response SHA-256 values and observation times, saved before the release is frozen. Every declared fact in section 2.1 points to one of them |
| Verdict | Saved P07 result with all five claims `QUALIFIED`, or the honest weaker verdict and its reasons |
| Corroboration | `class` `COMPLETE`, `sample_size` = `population_size` ≥ trades, `mismatches` 0 |
| Delivery | One delivery record for each of the 4 buckets; every bucket `available_at` = max(bucket end, delivery time). If any record is missing, the profile declared `ASSUMED_DELAY` |
| Replay | Only for `QUALIFIED`: one saved replay, reopened byte-identical after restart. Expected events are `FILL_UNAVAILABLE` with `LATE_INPUT` (section 3, step 7); any fill is labelled `simulated fills`. Otherwise the saved `DATASET_COVERAGE_UNPROVEN` refusal |
| Nansen | Saved and reopened report, attribution shown, credits `KNOWN` 6 or the documented `UNKNOWN` liability, holders labelled as a collection-time snapshot |
| Other owner | Owner B gets 404 for the declaration, job, dataset, report and replay |
| Reconciliation | For each resource: reserved = consumed + released + unknown. Provider-side counts equal saved client counts |

## 9. Decisions the builder makes, once facts exist

| Id | Decision |
|---|---|
| D1 | Option B, the 20-minute shape and `T0` |
| D2 | The forward recorder as a separately scoped implementation, and the source-fact packet as an operation |
| D3 | The delivery-record reading, and which observed time is `collected_at_utc` |
| D4 | Orientation `QUOTE_PER_BASE` |
| D5 | The definition of qualified MOE mechanics, after P6 evidence |
| D6 | Feasibility floors 1 and 1, with their stated lack of statistical support |
| D7 | Publishing the scan blocks, the pool-creation transaction and the QuickNode host |
| D8 | Owner A request capacity of 66 unconsumed requests, and the recorded cap value that gives it |
| D9 | Nansen display and retention, and Envio and QuickNode retention |
| D10 | The run itself, after D1 to D9, D11 and the preconditions in section 1 |
| D11 | Whether a saved replay with only `FILL_UNAVAILABLE` events meets the demo goal, or a replay design change is requested from its owner ([QUALIFICATION_GAPS.md section 5.5](QUALIFICATION_GAPS.md#55-replay-timing-on-an-observed-delivery-dataset)) |

This packet makes no profit, edge, prize or source-identity claim and does not close #58.
