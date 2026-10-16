# Actual research demo: operating packet (PROPOSED)

Task `ACTUAL-RESEARCH-READINESS-L4-20261014-LOCAL-v1` (#58 Task 6, RG02, RG05, Envio and Nansen). Written on base `012fb1597d061e4d263afc3d8be0538c4298b48f`. Status: **PROPOSED. This packet authorizes no operation.** No credential was read and no provider, model, RPC, account or payment request was made to write it. Every actual item is `NOT_RUN`.

This packet turns the earlier proposals into one internally consistent set of values that the accepted code at `012fb15` can admit. [EVIDENCE_MAP.md](EVIDENCE_MAP.md) binds every value and check to its code symbol and contract.

## 1. Status words

| Word | Meaning |
|---|---|
| `PROPOSED` | This packet's choice. It needs review and the builder's approval before use. |
| `NEEDS_FACT` | A fact nobody has evidenced yet. A value cannot be frozen until it is evidenced. |
| `NEEDS_APPROVAL` | A product or operation decision that belongs to the builder. |
| `FIXED_BY_CODE` | The accepted code at `012fb15` enforces it. A different value is refused. |
| `NOT_RUN` | No actual run produced this evidence. |

## 2. What changed since the earlier proposals

The earlier proposals are [the P07 actual-collection packet](../research-history-clients/ACTUAL_COLLECTION_PACKET.md), [the application collection packet](../research-provider-composition/ACTUAL_APPLICATION_COLLECTION_PACKET.md) and [the Nansen live test packet](../nansen-report/LIVE_TEST_PACKET.md). They stay unchanged as history. Their values below are replaced for this demo run.

| Earlier value | Conflict with accepted code at `012fb15` | Value in this packet |
|---|---|---|
| `max_response_bytes` 8,388,608 per HyperSync page | `operating_release._check_history` refuses a reply cap above `limits.max_bytes`. `HistoryResourceBounds.max_bytes` allows at most 4,194,304. | 2,097,152 per reply. Aggregate 4,194,304. |
| 36 requests, including up to 6 `eth_call` decimals reads and 1 `eth_getCode` | `operating_release.RPC_METHODS` is exactly `eth_chainId` and `eth_getTransactionReceipt`. `HttpQuickNodeRpcClient` gets that allowlist. Other methods are refused. | 13 requests: 4 pages, 1 `eth_chainId`, 8 receipts. No other method. |
| Collection deadline 1,800 s (P07 library recipe) and 600 s (verifier stand-in Nansen jobs) | The application has one clock: the job's saved `deadline_at`. `HistoryResourceBounds.compute_seconds` allows at most 600. Every per-call bound is cut to the time left. | History job: deadline 600 s, compute 600 s. Nansen job: deadline 300 s, compute 300 s. Per-call bounds below. |
| Two-day window, 16 pages | HyperSync requests use `include_all_blocks` and at most `max_blocks_per_page` blocks. Monad documents a 300 ms minimum block time (400 ms before MIP-12). Two days is 432,000 to 576,000 blocks: 44 to 58 pages at 10,000 blocks per page. That exceeds 16 pages, and each page carries every block header. | One hour: 9,000 to 12,000 blocks, 1 or 2 pages. |
| Eight sampled receipts | `quicknode_corroboration` gives class `SAMPLED` when fewer records are compared than exist. P07 `qualify` then adds `CORROBORATION_SAMPLED_ONLY`, so the history claim is `LIMITED`. | The history claim stays `LIMITED`. The overall verdict is `UNRESOLVED` (section 6). |
| "Real `HttpTransport` and Nansen transport: not written"; "that script does not exist"; "No accepted Nansen network transport exists" | Obsolete. `StdlibHttpTransport`, `NansenHttpTransport`, `NansenHttpFactory` and `released_runtime_bootstrap.server_research_runtime` exist at `012fb15` (contract section 12). | No new adapter. The existing release path is used. |

## 3. The question and the smallest dataset

**Question (PROPOSED).** Can the application collect one hour of actual MOE/WMON swap history, corroborate it, qualify it honestly, save it, and reopen it after a restart without a second request? Can it also save one Nansen holder and flow report for MOE? A `LIMITED`, `UNRESOLVED`, empty or failed result is a valid answer. The run tests the evidence path. It makes no claim about a trading edge.

**Why one hour.** It is the smallest window that gives twelve five-minute buckets and fits the request, byte and time limits with margin. Probe A observed every five-minute bucket occupied from the Sep 24 23:45 warm-up to Oct 2 (2,019 of 2,019). Its research partition held 6,279 records from Sep 24 23:45 to Sep 28, about 87 per hour on average. The hour's exact count is `NEEDS_FACT`.

| Field | Value | Status |
|---|---|---|
| Network, chain id | Monad mainnet, 143 | `FIXED_BY_CODE` (`MONAD_CHAIN_ID`) |
| Pool | nad.fun MOE/WMON `0x97199b34564911936bc850ac45ede785892b5aad`, Uniswap-V2-compatible `Swap` | Retained Probe A fact |
| Event topic0 | `0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822` (`Swap(address,uint256,uint256,uint256,uint256,address)`) | Retained Probe A fact (corrected V2 signature) |
| QUOTE token | WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a`, 18 decimals | Retained Probe A fact. Orientation `NEEDS_APPROVAL` |
| BASE token | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`, 18 decimals | Retained Probe A fact |
| Orientation | `QUOTE_PER_BASE` (WMON per MOE), pool-gross | `PROPOSED`, `NEEDS_APPROVAL` |
| Window | `2026-09-25T12:00:00Z` to `2026-09-25T13:00:00Z`, half-open | `PROPOSED` |
| Scan blocks | `from_block` and `to_block_exclusive` that cover the window | `NEEDS_FACT` |
| Availability model | `ASSUMED_DELAY`, 180 s | `PROPOSED` (Probe A precedent), `NEEDS_APPROVAL` |
| Finality | `depth_blocks` 2, basis `DOCUMENTATION` (Monad: finality after 2 slots) | `PROPOSED` |

**Protected data.** The window ends before the Probe A validation partition (Sep 28 to Sep 30) and the sealed holdout (Sep 30 to Oct 2). Neither is read. The new declaration declares no `VALIDATION` or `HOLDOUT` partition inside the window. The declaration schema then requires direction `DESCRIPTIVE` with `DESCRIPTIVE` partitions only (`core/request_schemas.py`). `history_dataset.PROTECTED_ROLES` and `readable_until` therefore leave the whole hour readable. The closed Probe A is not reopened, and its private pages are not reused as this run's evidence.

**Scan blocks.** The release must freeze its block range. The retained Probe A metadata holds block numbers for this hour, but it is private. Two routes exist, and both need approval:

1. Publish a sanitized extract of the two boundary block numbers and timestamps (`NEEDS_APPROVAL`).
2. Approve a separate bounded source-fact read packet. This packet does not widen its RPC methods to get them.

## 4. Frozen release values

One release holds both parts. `server_research_runtime` composes at most one approved release, so a single release keeps the API and the worker on one SHA-256.

`release_id`: `actual-research-demo/1` (`PROPOSED`). `kind`: `ACTUAL`. The SHA-256 is computed by `release_sha256` after every `NEEDS_FACT` is filled. It is not known now.

### 4.1 History part (`HistoryRelease`)

| Field | Value | Status |
|---|---|---|
| `source_id` | `actual-moe-wmon-1h/1`. Must not name a recorded source (`check_release_source`). | `PROPOSED` |
| `envio_endpoint` | `https://monad.hypersync.xyz` (`POST /query`, bearer token) | From the P07 packet |
| `envio_credential_slot` | `envio_hypersync_bearer` (a slot name, not a secret) | `PROPOSED` |
| `quicknode_host` | The host of the builder's QuickNode Monad endpoint | `NEEDS_FACT`. Publishing it in `release_view` is `NEEDS_APPROVAL` |
| `quicknode_credential_slot` | `quicknode_monad_url` (holds the full URL, key in the path) | `PROPOSED` |
| `rpc_methods` | `eth_chainId`, `eth_getTransactionReceipt` | `FIXED_BY_CODE` |
| `source_version` | `envio-hypersync/1` | `FIXED_BY_CODE` |
| `corroboration_sample_size` | 8 | From the P07 packet |
| `required_coverage` | `COMPLETE_SCAN` | `FIXED_BY_CODE` (default) |
| `time_basis` | event `BLOCK_TIMESTAMP`, collection `APPLICATION_CLOCK` | `FIXED_BY_CODE` (default) |

`limits` (must equal the declaration's `resource_bounds` exactly, else `422 release_bounds_mismatch`):

| Limit | Value | Code ceiling | Reason |
|---|---|---|---|
| `max_pages` | 4 | 64 | One hour is 1 or 2 pages at 10,000 blocks. HyperSync can end a page early, so 2 spare pages. |
| `provider_requests` | 13 | 64 | `max_pages` 4 + 1 chain read + 8 receipts = 13. `_check_history` needs at least this sum. |
| `max_rows` | 2,000 | 10,000 | About 23 times the hourly average. |
| `max_bytes` | 4,194,304 | 4,194,304 | The schema maximum. |
| `deadline_seconds` | 600 | 3,600 | One saved job deadline. |
| `compute_seconds` | 600 | 600 | Equal to the deadline, so measured compute cannot exceed the reservation. |

`client_bounds` (per call):

| Bound | Value | Rule |
|---|---|---|
| `deadline_seconds` | 120 | `PreparedHistory.clients` uses `min(120, seconds left before the saved deadline)`. `HashingTransport` also refuses a send after the job deadline and treats a later reply as incomplete. |
| `connect_timeout_seconds` | 15 | Also cut to the per-call deadline. |
| `max_response_bytes` | 2,097,152 | Must be at most `max_bytes`. |
| `max_request_bytes` | 65,536 | A HyperSync query body is under 1 KB. |
| `max_blocks_per_page` | 10,000 | Caps both `to_block` and `max_num_blocks`. |

**Byte estimate (inference, `NEEDS_FACT`).** One block header (`number`, `timestamp`, `hash`) is about 120 bytes of JSON. One log with the selected fields is about 700 bytes. A 10,000-block page is then about 1.2 MB plus about 0.06 MB of logs. The hour is about 1.5 MB in total. If the wire size is larger, the byte cap stops the collection and the dataset is `PARTIAL`. Nothing is retried.

**Pacing.** The application does not pace HyperSync requests. Probe A observed a plan rate of 15 requests per minute. One of its scans stopped on an HTTP error after dispatching faster than that rate. Probe A recorded the precise cause as unknown. This run makes at most 4 HyperSync requests, so the dated rate is not reached. The current plan rate is `NEEDS_FACT`.

`provider_facts` are declarations, labelled `RELEASE_DECLARATION` in the saved evidence basis. P07 does not read them. **The release may declare only what retained evidence supports.** Declaring `QUALIFIED`, `OBSERVED_FINAL` or delivery records without evidence would make a false `QUALIFIED` verdict. The synthetic fixture `native-syn-qualified/1` declares such values. They must never be copied into an actual release.

| Fact | Declared value | Evidence | Effect in P07 `qualify` |
|---|---|---|---|
| `pool_tokens` | `SINGLE_READ` | Probe A RPC reads of the pair's token0 and token1 (dated, not this run). A V2 pair fixes these at creation. | `LIMIT POOL_TOKENS_SINGLE_READ` |
| `pool_venue` | `SINGLE_SOURCE` | Probe A registry and creation receipt (dated) | `LIMIT POOL_VENUE_SINGLE_SOURCE` |
| `decimals` | For `base` and `quote`: `window_start`, `window_end` and `current` all `NOT_READ` | This run cannot read decimals: `eth_call` is not admitted. Probe A read its own window end and its own current time, not this window or this run's time. Declaring those dated reads as `READ` would be false. | `MISSING_EVIDENCE DECIMALS_NOT_READ`, so `EVENT_AND_AMOUNT_MEANING` is `UNRESOLVED` |
| `fee_transfer_semantics` | not `QUALIFIED` | MOE has a reflection design. Fork fees are unqualified. | `LIMIT TOKEN_MECHANICS_UNQUALIFIED` |
| `finality_at_collection` | `FINALIZED_BY_DEPTH` | Inferred, not observed | `ASSUMPTION FINALITY_INFERRED_AT_COLLECTION_ONLY` |
| `delivery_records` | none | Not observed for history | Model is `ASSUMED_DELAY`: `ASSUMPTION` |
| `feasibility_claim` | A well-formed schedule and partition list. Sample floors are `NEEDS_APPROVAL`. | P07 `feasibility` | With no floors it returns `UNDECLARED`: `MISSING_EVIDENCE`, so `UNRESOLVED`. With floors: `FEASIBLE` or `INFEASIBLE`. A malformed claim makes `normalize` raise `AdapterInputError FEASIBILITY_CLAIM_INVALID`. |
| `collected_at_utc`, `archive_height` | A value fixed before the run | `NEEDS_APPROVAL`. Contract section 9 keeps `collected_at_utc` open. The archive-height part is this packet's inference. | See section 9, item 3 |

The entries for `pool_tokens` and `pool_venue` are the honest weaker states. Stronger states, and any decimals read, need evidence from this run or from an approved source-fact packet. That packet would add `eth_call`, which this release refuses.

### 4.2 Nansen part (`NansenRelease`)

| Field | Value | Status |
|---|---|---|
| `endpoint` | `https://api.nansen.ai` | `FIXED_BY_CODE` (`NANSEN_ORIGIN`) |
| `credential_slot` | `nansen_api_key` | `PROPOSED` |
| `token_address`, `token_symbol` | `0xd8e004acba279417c04c0633cb5a21ceca207777`, `MOE` | From the Nansen packet |
| `window` | `2026-10-06T09:44:14Z` to `2026-10-07T09:44:14Z` (flows only; `to` is an inclusive cutoff) | From the Nansen packet. Outside every Probe A partition |
| `operations` | `holders`, `flows` | `FIXED_BY_CODE` allowlist |
| `holder_query` | `label_type` `all_holders`, `aggregate_by_entity` false, `order_field` `token_amount`, `value_usd_min` null | `PROPOSED`. The earlier `min: 0` variant is dropped. It would be a third request. |
| `flow_query` | `label` `top_100_holders` | From the Nansen packet |
| `limits` | `max_requests` 2, `max_pages` 2, `max_bytes` 2,000,000, `max_credits` `"6"`, `per_page` 100 | `PROPOSED` |
| `deadline_seconds`, `compute_seconds` | 300, 300 | `PROPOSED` |
| `client_bounds` | `connect_timeout_seconds` 10, `max_request_bytes` 16,384, `max_response_bytes` 1,000,000 | `PROPOSED`. Reply cap is at most `max_bytes`. |

**Credits.** `NansenClient.OPERATIONS` reserves 5 credits for `holders` and 1 for `flows`. The current Nansen credits page (read 2026-10-14) lists the same costs for Free and Pro, and 150 credits for `holders` with `premium_labels=true`. `NansenClient` pins `premium_labels` false. One report reserves 6 credits.

**Chain coverage.** The current `tgm/holders` and `tgm/flows` request schemas list the chain value `monad`. The chain coverage table marks Token God Mode for Monad. This is chain-level documentation only. MOE token coverage, Monad historical coverage for the flows window and the account's plan rights are `NEEDS_FACT`. A key does not establish them.

**If Nansen does not cover MOE.** A reply that shows no MOE coverage is a requirement conflict with the demo scope. Report it to the builder. Do not substitute another token or chain as demo evidence without the builder's decision.

**Snapshot time.** The holders endpoint returns current holders and takes no date range. The holder result describes the collection time, not the window. The flows endpoint uses the window. The report must say so.

## 5. Owner, global and money limits

Default settings at `012fb15` give each owner 16 provider requests, 900 compute seconds and 50 Nansen credits. The deployed values are frozen at first use (`usage.quota`) and are `NEEDS_FACT` for the actual host.

| Resource | History job | Nansen job | Total | Default owner cap |
|---|---|---|---|---|
| `provider_requests` | 13 | 2 | 15 | 16 |
| `compute_seconds` | 600 | 300 | 900 | 900 |
| `nansen_credits` | not reserved | 6 | 6 | 50 |

Both jobs fit the default owner cap even when both reservations stay `UNKNOWN`. While both reservations stay open or `UNKNOWN`, a second attempt of either job does not fit. A `KNOWN` settlement releases the unused part (`usage/quota.py` `settle`), and a second attempt can then fit. The cap is therefore not the guard against a repeat. The guard is the no-repeat rule in section 7. Raising a cap is a settings change outside this lease and needs approval.

**Money (PROPOSED suballocation of the recorded USD 2.00 combined model and data ceiling).** Current prices and account rights are `NEEDS_FACT` until evidenced.

| Item | Proposed ceiling | Basis |
|---|---|---|
| Hermes model calls | USD 0.50 | Probe A used 28 model calls for USD 0.0814978625 in total. Exact model and price snapshot is a separate packet. |
| Envio HyperSync | USD 0.00 above the existing plan | Stop on any quota message |
| QuickNode | USD 0.00 above the existing plan | Stop on any quota message |
| Nansen | 6 credits, at most USD 0.50 equivalent | USD value of a credit on the account's plan is `NEEDS_FACT`. x402, MPP, premium labels and every payment fallback stay refused. |
| Unallocated reserve | USD 1.00 | Not spent without a new approval |
| **Total** | **USD 2.00** | |

## 6. Expected verdict and replay

With honest declarations (section 4.1), P07 `qualify` cannot return `QUALIFIED` for this run:

- `BINDING_IDENTITY` is `LIMITED` (pool tokens `SINGLE_READ`, venue `SINGLE_SOURCE`).
- `EVENT_AND_AMOUNT_MEANING` is `UNRESOLVED` (no decimals read in this run). Token mechanics are also unqualified.
- `HISTORY_COMPLETENESS_AND_ORDER` is `LIMITED` because 8 of about 87 records are corroborated (`SAMPLED`).
- `POINT_IN_TIME_AVAILABILITY` is `LIMITED` (`ASSUMED_DELAY`).
- `SCHEDULE_FEASIBILITY` is `UNRESOLVED` unless floors are declared.

Complete corroboration is not reachable either. It needs one receipt per record. About 87 receipts plus pages exceed the 64-request schema ceiling. It would also leave the other claims unchanged.

So the expected outcome is a saved `UNRESOLVED` dataset. It becomes `LIMITED` at best only if an approved source-fact packet reads decimals and the builder declares floors. `market_adoption` refuses a dataset that is not `QUALIFIED`. The P13 runtime refuses replay with `DATASET_COVERAGE_UNPROVEN`. Evidence-class compatibility (`PROVIDER_ACTUAL` admitted since contract section 12.5) does not qualify a dataset. **Hypothetical replay runs only if a dataset is actually `QUALIFIED`.** Then every fill is labelled `simulated fills`, and nothing claims statistical support, profit or trading permission.

This conflicts with the approved demo scope, which asks for a saved qualified dataset and a replay. `NEEDS_APPROVAL`: the builder chooses one:

1. Accept a saved `UNRESOLVED` or `LIMITED` dataset and the saved replay refusal as the demo evidence.
2. Approve separate work that produces stronger evidence. This packet does not propose to relax any verdict rule.

## 7. Operation sequence and stop rules

Each step needs the approvals in section 9 first. No step retries automatically.

1. Freeze the release values, compute `release_sha256`, add `RELEASE_DEFINITIONS` and `APPROVED_RELEASES` entries, and compose a `CredentialSource`. These are reviewed code changes in the lane that owns application composition.
2. Start the API and the worker. Both call `server_research_runtime`. Record the release SHA-256 from `GET /v1/research/history-sources`.
3. As owner A, save one declaration for `actual-moe-wmon-1h/1`, with `resource_bounds` equal to the release limits.
4. Start one history job with a fixed `request_key`, `actual-research-demo-history-1`. The API reserves the owner and global limits at this start. A repeated key returns the original job. A new key needs a new approval.
5. Let the worker run. It reads credentials, saves `ATTEMPT_STARTED`, then calls in order: pages, `eth_chainId`, receipts.
6. Start one Nansen report with `request_key` `actual-research-demo-nansen-1` and the exact release request (else `422 release_request_mismatch`).
7. Reopen both results. Restart the API and the worker. Reopen again.
8. Run the proofs in section 8, then cleanup and reconciliation.

**Stop and report (no retry)** on any of:

- any HTTP error, quota or rate message, `401`, `402`, `403` or `429`;
- a chain id other than 143;
- a page that does not tile the scan;
- a credential in any output;
- a reply after the saved deadline;
- any sampled receipt mismatch;
- any request beyond a limit;
- any charge above section 5.

The run keeps its partial result. A failed or `UNKNOWN` run is not repeated. A second attempt is a new approval with a new key and fresh reservations.

**UNKNOWN liability.** These events leave a call's effect unknown:

- a lost reply;
- a cancel during a call;
- a late reply;
- a killed worker;
- a race between the guard and the adapter.

Each one keeps the whole request reservation as unknown liability. For Nansen, the credit reservation is also kept. It is never settled as zero. A killed worker reconciles `OUTCOME_UNKNOWN` and never collects again.

## 8. Required proof

Every item is `NOT_RUN`. Evidence keeps ids, counts, hashes and ranges only. Raw responses and private text stay out of shared documents.

| Proof | Required observation |
|---|---|
| Release identity | Same release SHA-256 in the API source list, the saved declaration, the job and the dataset. Kind `ACTUAL`, transport `PROVIDER_HTTP`, class `PROVIDER_ACTUAL`. |
| Original attempt | One job per key, one reservation, one `ATTEMPT_STARTED`, owner and global ledger rows. |
| Request counts | Saved client calls equal the provider-side counts read independently: HyperSync usage, QuickNode per-method usage and Nansen `X-Request-Id` plus account usage. Whether HyperSync returns request ids is `NEEDS_FACT`. |
| Billing and credits | QuickNode and Envio usage show no charge above plan. Nansen `X-Nansen-Credits-Cost`, `-Used` and `-Remaining` match the `KNOWN` settlement. |
| Provenance and order | Per-request request and reply SHA-256, statuses, endpoint hosts, page digests, query hash, ordering key and gaps, as `HashingTransport.facts` and the dataset save them. |
| Coverage | `release_coverage {required, met}`, bucket counts, corroboration class and sample. `LIMITED` stays `LIMITED`. |
| Verdict and replay | The saved P07 verdict. A replay attempt saved as `DATASET_COVERAGE_UNPROVEN` unless the dataset is `QUALIFIED`. |
| Save, reopen, restart | Reopen in a new browser context, restart the API and the worker, reopen again. Byte-identical rows and hashes. Provider-side counts unchanged by the reopen. |
| Negative, no provider call | A changed release SHA (`409 operating_release_changed`), a missing credential (`UNAVAILABLE operating_release_credential_unavailable`), a production stand-in refusal. These need no provider request. |
| Negative, provider refusal | Optional. A disposable invalid key makes one refused call. It counts toward the limits. `NEEDS_APPROVAL`. |
| Interruption | Already proved locally with stand-ins (contract sections 7 and 12.3). An actual cancel spends requests. `NEEDS_APPROVAL` with its own limits. |
| Other owner | Owner B gets 404 for the job, the dataset and the report. |
| Session | A signed-out or expired session cannot read either result. Depends on the real Privy login proof. |
| Secret scan | The operator counts matches of each key and authorization header in API replies, browser results, logs, database rows and evidence, without printing the key. Every count is 0. |
| Cleanup and reconciliation | Owned processes stopped. Temporary raw artifacts that are not required evidence deleted. For every resource: reserved = consumed + released + unknown. Rotating the data keys afterwards is `NEEDS_APPROVAL`. |

## 9. Separate approvals and remaining decisions

Operation approval is separate from these preparations. None of them is approved by this packet.

1. **Credential delivery** (`NEEDS_APPROVAL`). No default credential source exists. `server_research_runtime` refuses startup without one. The delivery route (host secret store or a file outside the repository) and its code are separate work.
2. **Application mounting** (`NEEDS_APPROVAL`). `RELEASE_DEFINITIONS` and `APPROVED_RELEASES` are empty. Filling them is a reviewed code change citing the builder's approval of the exact SHA-256.
3. **Collection time and archive height** (`NEEDS_APPROVAL`). Contract section 9 keeps `collected_at_utc` open. The archive-height part is this packet's inference. The release fixes `provider_facts` before the run, so `collected_at_utc` and `archive_height` cannot be observed values. The application saves its own `application_collection_time` separately. A declared archive height must be at or above the window's last block plus `depth_blocks`, from evidence. Recording an observed height needs a design change or a separate source-fact packet.
4. **Model run** (`NEEDS_APPROVAL`). Exact Hermes model, current price snapshot and request limits come from the Hermes relay packet. Not in this packet.
5. **Nansen web label** (`NEEDS_APPROVAL`: who fixes it). Under a release, the web Nansen panel still shows a fixed "Authored … replayed" top label. The mount evidence records this as a retained limit. The label must change before an actual Nansen report is shown.
6. **Data-use rights and retention** (`NEEDS_APPROVAL`). Contract section 9 keeps rights and retention open, and the Nansen packet keeps them `UNSET`. Decide the data-use rights and the retention window for saved provider output before the run.
7. **Values marked `NEEDS_FACT`**:
   - scan blocks, QuickNode host, hourly record count and page wire size;
   - HyperSync plan rate and request ids;
   - Nansen token and history coverage, plan rights and credit price;
   - deployed owner and global caps.
8. **Values marked `NEEDS_APPROVAL`**:
   - orientation, availability model and feasibility floors;
   - the demo-scope conflict in section 6;
   - publishing scan blocks or the QuickNode host;
   - a source-fact packet for decimals or stronger binding facts;
   - optional negative and interruption proofs, and key rotation.
9. **Operation approval** for the run itself, after items 1 to 8.

## 10. Dependencies outside this packet

These stay independent. This packet neither resolves nor depends on them for its own correctness:

- Privy: one policy POST has an uncertain outcome, and a later step stopped with HTTP 403. Real login and signer controls remain unproved.
- Kuru: the current router (`getRouter()`) source is `NOT_REPRODUCIBLE` ([deployed source](../kuru-deployed-source/README.md)).
- Hermes: actual model inference through the application is not proved. The online relay is separate work.

This packet makes no source-identity, profit or prize claim, and it does not close #58.
