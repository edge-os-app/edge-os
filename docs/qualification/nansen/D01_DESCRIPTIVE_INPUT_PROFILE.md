# D01 descriptive input profile

Version `nansen-descriptive-reviewed/1`, calculation examples `d01-conventions/1`.
This is a local documentary qualification for NANSEN-D01-L2-01. It defines portable constraints and authored controls. It is not an application schema, collector, production adapter, accepted D02 feature, or predictive NANSEN-Q01 result. Gate and builder acceptance remain separate.

The sampled endpoints support a limited current-address inventory and limited provider-category observations. Supply percentages, numeric token scaling, event counts, hourly prices, historical availability, and distribution rights remain unqualified. A completed qualification can contain these unresolved findings.

## Binding and evidence identities

| Item | Bound value |
|---|---|
| Original question | How concentrated are MOE current holdings, and what do qualified basic flow records show? |
| Token | MOE, `0xd8e004acba279417c04c0633cb5a21ceca207777` |
| Network/provider chain | Monad mainnet, chain ID `143`, Nansen chain `monad` |
| Provider and origin | Nansen, `https://api.nansen.ai`, JSON POST |
| Original run/profile | `NANSEN-D01-MOE-2026-10-07-01`, `nansen-descriptive-v1` |
| Linked query variant | `NANSEN-D01-MOE-2026-10-07-01-min0`, parent is the original run |
| Original configuration freeze | `2026-10-07T09:44:14.185231Z` |
| Run closure | `2026-10-07T09:49:34.764186Z`, no further dispatch |
| Request authority | Five attempted authenticated calls and 25 credits, including failures/retries, basic labels only |
| Observed use | Three settled HTTP 200 calls, 15 conservative reserved credits, 11 quoted and 11 deducted credits |
| Ownership | Builder-private documentary custody. No application owner or authorization service was exercised. |
| Decimals | Prior Probe A identity reported 18. This run did not reverify decimals or establish provider balance scaling. |
| Accepted context/base | `6e7efc941a015e72278b3037bfcc314fc5cd6602`, [P02 boundary](../../contracts/P02_FIRST_SLICE_RECORDS.md) and research evidence-package rules |

Responses lack token/network identity echoes. Bind them through each exact request, endpoint, request/body hashes, retained provider request ID, and response hash. That association does not independently authenticate provider data or corroborate chain state.

BUILDER-ONLY REFERENCE: original report `docs/research/NANSEN_MOE_DESCRIPTIVE_INPUT_QUALIFICATION_2026-10-07.md`, SHA-256 `16b75997a354b1ccb2f8de9811b9977b6d7c9932045a945c83a42271d54334a0`.
Frozen directory `prototypes/edge-os/nansen-descriptive-qualification/2026-10-07-moe-01/`, manifest SHA-256 `01e6e960a6225cdded586a55bc88e16b85ae5ba473903f913ae9fcabe2174373`.
These are provenance references, not portable raw fixtures or permission to distribute them.

| Frozen request file | SHA-256 |
|---|---|
| `request-holders.json` | `a4fc094080031c6cb4b88f508b58c77782fd014b734ba4959f7e88cef3bcf6c9` |
| `request-flows.json` | `a2aa25b6e47fa6af6626b71872942dc4172c7bc36f8348364b384424e7a509b2` |
| `request-holders_min0.json` | `c40906132be6019c98a6f26e97c1d61a6a832ac2a27acea0f48ec94fb8d2a1f1` |

## Collection parameters and required fields

Both holder queries use `/api/v1/tgm/holders`, `aggregate_by_entity=false`, `label_type=all_holders`, `premium_labels=false`, page 1, 100 records per page, and `token_amount DESC`. Both bind the exact token and chain above. The original query omits filters. Its documented default is `value_usd.min=1`. The separately frozen min-zero variant adds only `filters.value_usd.min=0`. Keep the empty initial result and populated variant distinct. An empty USD-filtered response does not prove zero holders.

The flow query uses `/api/v1/tgm/flows`, `label=top_100_holders`, page 1, 100 records per page, `date ASC`, and no explicit filters. Its requested window is `2026-10-06T09:44:14Z` through inclusive cutoff `2026-10-07T09:44:14Z`. This was the selected category, not a substitute for all-holder flows. Captured labels include whale, public figure, smart money, top-100 holders, and exchange. There is no all-holder flow label in that schema.

The frozen required holder fields were address, token amount, ownership percentage, and pagination. Usable concentration additionally needs a verified total supply and matching units. Optional holder fields were labels, USD value, inflow/outflow, trailing balance changes, and warnings. Warnings must still accompany the resulting finding.

For limited flow observations, retain category, requested window, bucket start/end, completeness, pagination, warnings, and raw field identities. Every claimed quantity additionally requires its unit and economic meaning. Missing required meaning blocks that claim. Premium, historical membership, and purchase questions remain unsupported rather than silently becoming basic observations.

## Field conventions and claim results

| Field or claim | Verdict | Meaning and permitted use |
|---|---|---|
| Sampled access | Usable | Three local recorded successful responses. Account plan, future entitlement, and independent chain reconciliation are unknown. |
| Holder address inventory | Limited | 100 distinct address records in descending provider balance order. Addresses can be contracts or accounts, not distinct people or beneficial owners. |
| Holder pagination | Limited | Page 1 has `is_last_page=false`. Total holder population and uncollected rows remain unknown. Never normalize this page to 100%. |
| `token_amount` | Unresolved units | Captured current-holder definition is a balance count without a scaling rule. Retain its raw decimal representation. Do not divide by `10^18` or display physical token balances as qualified. |
| `ownership_percentage` | Unresolved | Current schema describes percentage of total supply. It returns no numeric total supply. Historical-holder documentation uses a 0–1 fraction. Arithmetic does not select between them. |
| Concentration | Unresolved | Top-10, top-20, and page raw sums independently match Decimal and exact rational arithmetic. Their physical units and denominator are unqualified. Do not publish either conditional interpretation as concentration. |
| Holder `value_usd` | Unavailable | All 100 values are null, with no-price warnings. Preserve null. Neither zero balances nor zero value follows. |
| Holder inflow/outflow and changes | Unresolved for product quantities | Documentation describes tokens received/sent and trailing changes. No independent scaling or purchase interpretation was qualified here. |
| Basic labels | Limited | Current provider address classifications. Historical classification, common ownership, accuracy, and cohort stability are unknown. Do not add overlapping categories as disjoint groups. |
| Flow category/membership | Limited | Top-100 provider category, with `holders_count=100` in each bucket. Member identities and classification times are absent. No fixed historical cohort follows. |
| Whole-token flows | Unavailable | This selected category is not all holders. There is no qualified all-holder flow output. |
| Flow `token_amount` and `value_usd` | Unresolved for quantitative use | Schema describes aggregate token amount and USD value. Stock time, scaling, membership, and valuation consistency are unqualified. |
| `total_inflows_count`, `total_outflows_count` | Unresolved | Numeric fields include fractional inflows and negative outflows. Their names do not establish event counts, signed token amounts, purchases, or net buying. No sums are qualified. |
| DEX/CEX quantities | Unavailable | All four fields are null in all 24 buckets. Captured schema populates them only for exchange labels. Null remains unavailable, never zero. |
| Flow `price_usd` | Unresolved for requested timing | Positive flow prices conflict with absent holder valuation. Preserve each endpoint's result separately and apply the price rule below. |
| Premium/historical capability | Unavailable in this qualification | Premium was neither requested nor tested. Historical top-holder schema omits Monad. No premium denial or historical access test occurred. |
| Retention/export/hosted-model use | Unresolved | Frozen public terms do not establish the needed account-specific rights. Private retention is not a qualified permanent-retention policy. |

## Time, price, and coverage

F1 correction: frozen `source-flows.bytes`, OpenAPI JSON at line 22, `/components/schemas/TGMFlows/properties/price_usd/description`, states: "Daily median token price in USD. For the current day, uses the latest spot price."

Store bucket time, price time meaning, source availability, and collection time separately. Hourly bucket spacing does not turn this field into an hourly median or close. Latest current-day spot values cannot establish prices available at earlier current-day bucket ends. Daily medians can incorporate later observations. This sample qualifies no hourly-price, contemporaneous-price, execution-price, or historical-decision use. Complete buckets do not resolve price availability.

Bucket starts are inclusive and bucket ends exclusive. The captured schema uses hourly buckets for ranges of seven days or less. For Monad, its lower-cutoff rule aligns to the hour start. There are 25 expected starts in this request, but only 24 unique starts were returned. `2026-10-06T09:00:00Z` is missing. Actual starts run from Oct 6 at 10:00 to Oct 7 at 09:00 UTC. The last bucket ends at 10:00 and is incomplete. The other 23 are complete, totaling 82,800 seconds. This is limited coverage, despite `is_last_page=true`.

Retain missing, duplicate, unexpected, incomplete, and unknown-completeness states. Missing buckets remain missing. Incomplete buckets stay visible and are excluded from complete-history totals. Completeness means request coverage, not finality. Preserve provider revisions and warnings.

Collection intervals are Oct 7 UTC: initial holders 09:44:18.396313–09:44:19.949440, flows 09:44:28.053968–09:44:29.221415, and min-zero holders 09:46:40.313265–09:46:41.466516. Their provider availability, cache age, source block, finality, and update times are unknown. Public coverage guidance about caching is not measured freshness.

F2 correction: null availability produces `unknown`. Availability later than assessment produces `not_yet_available`. With a separately declared age limit, zero through the inclusive age limit is `within_declared_age`; older input is `stale`. Require aware timestamps and a nonnegative integer limit. Age alone never qualifies price method, membership, or historical availability. The frozen classifier is excluded because it incorrectly accepts future timestamps.

## Calculations, costs, and controls

Concentration requires documented total supply, qualified matching balance units, and a declared distinct-address selection. Compute selected balance sum divided by total supply times 100. Preserve the selection and filtered/partial coverage. A page sum is never the denominator. Null balance/supply or unqualified units blocks the calculation. Nonfinite/negative balances, nonpositive supply, and selected balances exceeding supply are invalid. The authored checker exercises this convention with synthetic decimals and exact fractions. It cannot supply the missing MOE denominator.

Keep attempts, conservative reservations, quoted cost, deducted cost, and settlement separate. In this run, basic holders cost five credits per call and flows one. Every attempt reserved five credits before dispatch. The three attempts settled at 5, 1, and 5 credits. All failures and retries would count toward both caps. Prior stopped/unsettled attempts block further dispatch. Unknown settlement retains its reservation. No refunds or automatic retry, payment, upgrade, or alternate paid route are inferred. The run is closed and this checker has no dispatch function.

F3 correction: the original 17 authored controls tested request exhaustion and reservations near the limit. Their request-cap case short-circuited the credit branch. They did not independently test credit-only exhaustion. The gate added a separate one-attempt/21-credit example, correctly denying another five credits. Those are gate-authored evidence, not an original eighteenth control or a provider observation. The new checker independently covers that credit-only case, request exhaustion below the credit cap, exact credit boundary, stopped/unsettled state, future timestamps, valid age boundary, nulls, and supply-based arithmetic. Original controls also cover partial pages, incomplete/missing buckets and access failure; actual provider errors, retries, stale cache and budget exhaustion were not observed.

Run the authored controls from the repository root:

```sh
python3 docs/qualification/nansen/check_d01_profile.py
```

The command uses only Python's standard library. It reads no provider artifacts, credentials, or environment files and performs no network calls. Examples are in the same file. It checks conventions, not a production schema, immutable storage, access rights, all acceptance requirements, or collection enforcement.

## Portable record requirements

Any later adopted record must retain these groups. This inventory is documentary and does not extend P02's closed record types.

| Group | Required information |
|---|---|
| Identity/ownership | Profile/calculation version, original question, package/run/variant IDs, parent lineage, collector authority and owner reference. A future server derives ownership from authenticated identity, not caller input. |
| Source/request | Organization, origin, method/path, exact token/network, full parameters/filter/mode/order/page, source schema version/hash, request body/file hash, provider request ID, response hash, collection interval. |
| Field evidence | Raw field name/decimal representation, qualified or unresolved unit, total-supply evidence, scaling provenance, null meaning, label tier, category/classification time and membership limits. |
| Timing/quality | Exact requested window, bucket start/end/completeness, distinct price time rule, availability and earliest usable time or unknown, cache/update/block/finality metadata or unknown, warnings and returned/uncollected/missing coverage. |
| Costs/rights | Every attempted call and settlement, reserved/quoted/deducted credits separately, request/credit caps, failure and stop state, closure, retention/export/hosted-model permissions and their evidence or unresolved status. |
| Findings | Claim-specific verdict, calculation/version/source references, independent checks, conflicts, exclusions and limitations. Preserve original observations when meaning or query changes. |

Raw holder rows, proprietary response tables, account details and credentials remain outside shared candidates and hosted-model prompts. Generic constraints and independently authored examples are portable. Hashes are provenance, not a redistribution license.

## Acceptance mapping and D02 consequences

| D01 requirement | Result and evidence |
|---|---|
| Frozen identity, question, fields, query/mode/page before calls | Usable documentary evidence in configuration, linked variant, three request identities and attempt timestamps. Schema info version is 1.0.0; hashes distinguish captured definitions. |
| Actual access and token coverage | Usable only for these three samples. Local hashes are consistent. Provider truth, account plan and future access are unresolved. |
| Supply concentration and filtered/partial coverage | Unresolved concentration, limited inventory. Independent exact arithmetic passes; denominator/scaling remains missing. USD exclusions and uncollected pages stay explicit. |
| Units, null meanings and independent calculation | Limited raw arithmetic. Physical balance/count meanings remain unresolved; nulls stay null. Authored concentration convention cannot qualify sample units. |
| Window, buckets, collection/cache/availability/warnings | Limited coverage with one missing and one incomplete bucket. F1 price and F2 future-time rules apply. Availability/cache/finality remain unknown. |
| Label tier, cohort/classification overlap | Limited basic address/category evidence. Premium/historical questions are unavailable here. No common-owner or disjoint-cohort claim. |
| Pagination/retries and request/credit settlement | Usable closed-run documentary accounting, 3 calls/11 settled credits within 5/25. No remaining authority is inferred. F3 separates control coverage. |
| Retention/export/hosted-model rights and key boundary | Unresolved rights. No raw redistribution or hosted-model upload is qualified. Collector-held credentials remain outside this profile. |
| Missing/null/stale/incomplete/partial/budget/access controls | Limited authored-control evidence and observed sample missingness. New runnable controls cover F2/F3 independently. Unperformed live failures remain unperformed. |
| Versioned portable profile, lineage, conventions/examples | This profile plus runnable authored controls. Private raw evidence is referenced by identity, not distributed. No generic application schema was created. |
| Exact verdict and holder-only fallback | A useful holder-only inventory/coverage report is supportable without concentration percentages, subject to approved data-use rights. Numeric token balances need scaling qualification. |

D02 can later adopt an explicit holder-only question about sampled address inventory, provider ordering, labels and partial coverage. It must explain that there is no qualified numeric balance/concentration or whole-token flow summary. Raw inventory display and hosted-model use still need rights. A requested concentration or flow question cannot silently become that narrower report.

D02 remains unassigned and blocked for unsupported claims and unresolved data-use rights. Actual P03 ownership/persistence/reopen and P05 Hermes integration are separate prerequisites. No further observation is required to finish this qualification honestly. Resolving numeric concentration would require bounded, approved supply/unit evidence; historical-price/count claims need separately qualified semantics and availability. This task grants no new calls, D02 implementation, publication, merge, graph change, wallet, or financial authority.

## Frozen public sources

Sources were captured Oct 7, 2026, 09:43:49–09:43:54 UTC. No later documentation, account or API lookup occurred in this review. Original Context7 lookup is historical provenance only; conflicting cached examples did not override captured schemas.

| Source | SHA-256 | Relevant definition |
|---|---|---|
| [Current holders](https://docs.nansen.ai/api/token-god-mode/holders) | `549fa87bbd9333252df8ce1fe43bd207e94fffcbd424bf80c8989e02d285adf5` | Current balances, percentage wording, default USD filter, address mode |
| [Flows](https://docs.nansen.ai/api/token-god-mode/flows) | `906f8ba06c17248632798ac87ad81a9640dd4a807b75c41687b1782ef7bccd79` | Bucket bounds, daily/latest price, label scope, exchange-only quantities |
| [Credits](https://docs.nansen.ai/getting-started/credits) | `e0f7c34c6c150de682f3c96ebc09a4e24939770b120554a2ef5455cba3fc6775` | Captured holder/flow cost definitions |
| [Coverage](https://docs.nansen.ai/api/data-coverage) | `ebc0e83a02b7f6205d54668d6294e95b0192565f055ad9c3ddf4bd596370123b` | Documented caching/revision limits, not measured availability |
| [Historical holders](https://docs.nansen.ai/api/backtesting-data/historical-top-holders) | `87af5f2edec92253d8c0f0b431f5633143d67af028d1ad32f797dfbafcc44cce` | 0–1 fraction and no Monad historical chain support |
| [Redistribution](https://docs.nansen.ai/guides/redistribution-guide) | `8256159894b2c098d752c65c6efa2ef85641bedf1e7da02bc3e5434752739324` | Endpoint-specific guide conditions do not settle all-holder/model-use rights |
| [API terms](https://nansen.ai/legal/api) | `bac795cbce25f6d89346672b2c51c171ea7a0e98aa9e299939de0efb3426d6f3` | Internal license, storage/redistribution/AI restrictions, no account exception established |

The frozen guide lists flows with attribution, but the captured terms and missing account-specific permission still limit product use. Basic all-holder export and hosted-model processing remain unresolved. This is a source assessment, not legal clearance. Probe A and its sealed holdout remain unchanged.
