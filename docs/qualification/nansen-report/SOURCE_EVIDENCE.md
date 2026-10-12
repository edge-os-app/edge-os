# Nansen endpoint source evidence

Recorded 2026-10-12. Public first-party documentation only. No account, API key, request or provider response was used. This is a source assessment, not legal clearance or provider truth.

## Current first-party endpoint facts

Sources: `https://docs.nansen.ai/api/token-god-mode/holders` and `https://docs.nansen.ai/api/token-god-mode/flows` (retrieved 2026-10-12). Both pages embed their OpenAPI 3.1 document with `info.version` `1.0.0` and server `https://api.nansen.ai`.

| Fact | Value |
|---|---|
| Holders operation | `POST /api/v1/tgm/holders` |
| Flows operation | `POST /api/v1/tgm/flows` |
| Server origin | `https://api.nansen.ai` |
| Provider API schema version | `1.0.0` |
| Holders chain enum | `arbitrum, arc, avalanche, base, bitcoin, bnb, ethereum, hyperevm, injective, iotaevm, linea, mantle, mantra, monad, near, optimism, plasma, polygon, robinhood, sei, solana, sonic, starknet, sui, ton, tron` |
| Flows chain enum | same set plus `hyperliquid`, without `bitcoin` |
| Holders `label_type` enum | `whale, public_figure, smart_money, all_holders, exchange`; default `all_holders` |
| Flows `label` enum | `whale, public_figure, smart_money, top_100_holders, exchange`; default `top_100_holders` |
| Pagination | `page` >= 1 (default 1); `per_page` 1..1000 (default 10); response `is_last_page` |
| Holders `value_usd` filter | default `min: 1.0`; set explicitly to override, for example `min: 0` |
| Holders `premium_labels` | default `false`; `true` returns premium labels, costs 150 credits and needs a paid plan |
| Holders `token_amount` | JSON number, "total balance count"; no scaling rule |
| Holders `ownership_percentage` | JSON number, "percentage of total token supply owned"; no numeric supply returned |
| Holders `value_usd` | JSON number or null; a no-price warning accompanies all-null values |
| Flows bucket fields | `date` (inclusive start), `bucket_end` (exclusive end), `is_complete`, `price_usd`, `token_amount`, `value_usd`, `holders_count`, `total_inflows_count`, `total_outflows_count`, `total_inflows_dex`, `total_outflows_dex`, `total_inflows_cex`, `total_outflows_cex` |
| Flows `price_usd` | "Daily median token price in USD. For the current day, uses the latest spot price." |
| Flows DEX/CEX fields | populated only when `label=exchange`, else null with a warning |
| Flows range | hourly buckets for ranges of seven days or less, else daily buckets; `date.to` is an inclusive cutoff |
| Credit headers | `X-Nansen-Credits-Cost` (quoted), `X-Nansen-Credits-Used` (deducted), `X-Nansen-Credits-Remaining` |
| Request id header | `X-Request-Id` on every response |
| Error envelope | `{error, message, code, status, request_id, doc_url}` with a stable `code`; `401` unauthenticated, `402` payment, `403` forbidden/insufficient credits, `429` rate limit |
| Auth | `apikey` header; `X402Payment` and `MppPayment` are alternative payment schemes and are not used |

## Accepted D01 portable input

Profile `docs/qualification/nansen/D01_DESCRIPTIVE_INPUT_PROFILE.md` version `nansen-descriptive-reviewed/1`, conventions `d01-conventions/1`, checker `docs/qualification/nansen/check_d01_profile.py`.

D01 frozen public sources (captured 2026-10-07), SHA-256 as recorded in that profile:

| Source | SHA-256 |
|---|---|
| Current holders | `549fa87bbd9333252df8ce1fe43bd207e94fffcbd424bf80c8989e02d285adf5` |
| Flows | `906f8ba06c17248632798ac87ad81a9640dd4a807b75c41687b1782ef7bccd79` |
| Credits | `e0f7c34c6c150de682f3c96ebc09a4e24939770b120554a2ef5455cba3fc6775` |
| Coverage | `ebc0e83a02b7f6205d54668d6294e95b0192565f055ad9c3ddf4bd596370123b` |
| Historical holders | `87af5f2edec92253d8c0f0b431f5633143d67af028d1ad32f797dfbafcc44cce` |
| Redistribution | `8256159894b2c098d752c65c6efa2ef85641bedf1e7da02bc3e5434752739324` |
| API terms | `bac795cbce25f6d89346672b2c51c171ea7a0e98aa9e299939de0efb3426d6f3` |

The current retrieval confirms the same paths, fields, defaults and credit headers. It does not change any D01 limit. The D01 binding limits stay in force:

- Holder result partial (top 100); unknown units and supply denominator.
- Default minimum-USD filtering can omit unpriced rows. An empty filtered response does not prove zero holders.
- Fractional or negative count fields are not event counts. Null DEX/CEX amounts stay unknown.
- Bucket coverage excludes missing or incomplete intervals. Daily median or current spot is not hourly historical known-price data.
- No qualified concentration percentage, historical cohort, premium label, identity attribution or profitable edge.

## Rights status

D02's derived explanations and source attribution are within scope. Optional raw export, training or premium uses stay outside scope. Data-use rights for raw inventory display and hosted-model use remain unresolved. This package stores no raw provider response; tests use authored synthetic data only.
