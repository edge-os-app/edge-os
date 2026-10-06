# Market terminals and GeckoTerminal integration

Reviewed: 2026-10-05, Africa/Kinshasa.

Status: the builder authorized recording this comparison and integration direction. No chart, API connection or catalog entry has been implemented or qualified. This update authorizes no paid access, prototype expansion or financial action.

## Sources and evidence limits

Official product pages and CoinGecko API documentation were inspected through the web and Context7. This was a documentation assessment, not a signed-in terminal UX review, API response test or execution test. It adds no screenshots to the earlier competitor UX archive. Exact MOE pool coverage, chart behavior, provider terms, account-level limits and costs remain unchecked.

| Reference | Documented or visible capability | Potential Edge OS use |
|---|---|---|
| [GeckoTerminal Monad pools](https://www.geckoterminal.com/monad/pools) | Monad pool discovery with price changes, volume, liquidity and transaction activity. | Market discovery and a contextual pool chart. |
| [DEX Screener Monad](https://dexscreener.com/monad) | Monad market listings; navigation includes new pairs, movers, watchlists, alerts and multiple charts. | References for finding markets and keeping frequently watched markets accessible. |
| [Birdeye Monad data](https://birdeye.so/data-api/blog/detail/birdeye-data-services-now-supports-monad-mainnet) | Documented token/trade data, historical candles, top traders and wallet-transaction streams. | Candidate enrichment for a declared research need. Endpoint availability does not establish deployer identity, complete wallet PnL or rug attribution. |

These are overlapping products and data sources, not evidence that a terminal lacks agents or research. Charting, screening and AI conversation alone do not distinguish Edge OS. Our intended emphasis is preserving the request, recording every research attempt and contrary result, compiling supported rules, optionally simulating them, and connecting an exact revision to bounded agent operation. The complete production path remains unproved. The [specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#market-terminal-and-chart-integration-direction) controls product behavior.

## Two distinct integration options

### Market chart in the interface

Start with an optional "View market chart" link attached to an exact pool in Research or a position's details. Keep the research conclusion and primary account action visible first. If in-app viewing proves useful, GeckoTerminal documents [embedded pool and token charts](https://about.geckoterminal.com/embed-charts); embedding is a separate implementation choice, not required to finish the current prototype.

Show the chain, pool, price denomination and provider. A current external market chart is separate from the frozen dataset behind a saved investigation, a simulated account-value chart and actual account results. Filters or chart updates do not rewrite saved findings. If coverage or loading fails, explain that the chart is unavailable and preserve the report and account controls. A chart conveys neither strategy support nor permission to trade.

Before embedding, check the exact pool, provider terms/attribution, permitted external content, desktop/mobile behavior and an external-link fallback. Do not rebuild a full terminal or add a new mandatory screen just to display a chart.

### Read-only market data for the agent

[CoinGecko's onchain documentation](https://docs.coingecko.com/docs/defi-onchain-analytics) describes pool candles and trades. GeckoTerminal's [public API reference](https://api.geckoterminal.com/docs/index.html) is another documented route. Select the actual route and account plan before relying on authentication, historical access or limits; these routes are not interchangeable service guarantees. This assessment qualifies neither route for Edge OS.

If an accepted task needs the data, expose only selected read-only tools through the existing evidence gateway and approved per-agent catalog. Reuse its ownership checks, secret isolation, provenance and cost controls. Retain provider, endpoint/configuration identity, exact chain/token/pool, denomination, requested period and collection time. A documented API does not itself establish a ready-to-use Hermes MCP connection.

Before using candles in strategy calculations, verify coverage, timestamp/availability meaning, base/quote direction, aggregation, missing intervals and numerical compatibility. The [pool candle documentation](https://docs.coingecko.com/reference/pool-ohlcv-contract-address) says intervals without swaps are skipped by default; enabling `include_empty_intervals` fills them with the previous close and zero volume. That option cannot silently become an observed close under our accepted missing-data rules. Historical access depends on the plan and pool tracking start. Candle availability alone does not establish complete trades, historical delivery or achievable fills.

## Existing boundaries and sequencing

Envio remains the selected event/history path; QuickNode remains the current-state and reconciliation path. Provider comparison or additional data must preserve sealed datasets and closed Probe A evidence. Kuru Flow and Privy remain the separately qualified execution and authority direction. A chart or research connection grants no signing access and replaces neither.

Use a link first. Consider an embed in the applicable accepted frontend ticket, and selected data tools in a backend ticket only when they address a declared need. Record focused checks there rather than reopen Probe A or start another broad prototype. The current five-task interaction experiment, backend simulator work and Probe B retain their existing scopes and status. No integration has been installed or enabled by this documentation change.
