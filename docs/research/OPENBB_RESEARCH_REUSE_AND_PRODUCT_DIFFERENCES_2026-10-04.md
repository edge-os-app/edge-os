# OpenBB research reuse and Edge OS product differences

Reviewed: 2026-10-04, Africa/Kinshasa.

Status: sourced documentation assessment. The builder authorized recording these findings and recommendations. OpenBB remains an optional reuse candidate, not an adopted dependency, enabled catalog entry or tested integration.

## Evidence boundary

Sources inspected through Context7 and the web: official OpenBB documentation and the public repository README. This pass did not install packages, run indicators, connect an MCP client, inspect a signed-in Workspace or query a data provider. Feature documentation establishes published capability, not compatibility with Edge OS or successful hosted behavior.

The [OpenBB repository](https://github.com/OpenBB-finance/OpenBB) currently redirects to `openbq-org/OpenBB`. The inspected README describes an open-source data platform exposing integrations through Python, REST, MCP and analytical interfaces. Its Workspace description includes data visualization and custom agents. Treat repository ownership, released versions and dependency licenses as version-specific checks before adoption, not permanent assumptions.

## Useful components and patterns

| Candidate | Documented capability | Edge OS use and limitation |
|---|---|---|
| `openbb-technical` | Computes indicators and signals on supplied price data; does not fetch that data. Includes moving averages, RSI, MACD and volume measures. | Could consume qualified bars from our event pipeline and reduce future indicator implementation work. Availability in OpenBB does not add an operator to our compiler or qualify its semantics. |
| Provider and result interfaces | Provider extensions normalize source-specific requests/results; result envelopes can carry provider, warnings and metadata. | Learn the separation between fetching and analysis. Preserve our additional pool/token identity, units, source events, availability and collection evidence; those guarantees do not follow automatically from a common schema. |
| Self-hosted ODP MCP | Exposes installed analytical/data commands as agent tools. | Candidate for selected research tools through the approved catalog. Enforce tool and tenant access in the backend, including any discovery/dispatcher route. Do not expose arbitrary commands or financial authority. |
| Workspace MCP | Connects an external agent to an active Workspace browser session. | Useful for interactive research experiments, but its open/connected-tab requirement makes it unsuitable as the essential dependency for our unattended worker. |
| Linked research views and contextual agents | Workspace links widget parameters and lets agents use dashboard context and return artifacts. | Keep a selected market, date range and dataset revision consistent across charts, tables and report conversation. This is a design reference, not a reason to copy a full configurable terminal. |

Sources: [technical extension](https://docs.openbb.co/odp/python/extensions/data-processing/technical), [Python/REST/MCP integration](https://docs.openbb.co/odp/python/quickstart), [MCP server](https://docs.openbb.co/odp/python/extensions/interface/openbb-mcp), [Workspace MCP requirements](https://docs.openbb.co/agents/workspace-mcp-quickstart), [Workspace concepts](https://docs.openbb.co/workspace), and [response-envelope documentation](https://github.com/OpenBB-finance/openbb-docs/blob/main/content/odp/python/basic_usage/response_model.mdx).

## Product overlap and intended differences

OpenBB already documents financial analysis, customizable dashboards, contextual agents and analytical applications. AI chat, charts and indicators alone do not distinguish Edge OS. [Workspace overview](https://docs.openbb.co/workspace).

| OpenBB's documented emphasis | Edge OS's intended product emphasis |
|---|---|
| Connect data sources and analytical interfaces. | Preserve a trader's request and adopted meaning through an inspectable investigation. |
| Analyze data and produce charts or findings. | Keep every attempted variant, negative result, contrary explanation and unresolved claim in the research record. |
| Connect custom analytical agents. | Compile supported rules into an exact immutable strategy revision with explicit semantic dependencies. |
| Provide extensible research infrastructure and applications. | Link that revision to a user-approved mandate, bounded execution, shared position accounting, recovery and revocation. |

This comparison concerns product emphasis, not exclusive capabilities. OpenBB extensions could implement similar workflows. No ready-made equivalent to Edge OS's complete compiler/mandate/recovery contract was found in the reviewed documentation; this was not an exhaustive code audit. Edge OS's full production workflow is also unproved. Closed Probe A establishes only its accepted bounded interpretation/research-process claim.

The [Edge OS specification](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md) controls required behavior. This note supplies reuse and comparison evidence, not a second editable product contract.

## Keep the current data and strategy boundaries

Envio remains the selected indexed-event/history path. QuickNode remains the current-state and reconciliation path. No ready-made OpenBB adapter was verified for our exact Monad/Kuru market history. An indicator library cannot create missing pool history, historical delivery evidence or achievable fills.

Open-source package access does not make external provider data, hosted Workspace access, hosting or model inference free. Inspect the exact provider's credentials, coverage, terms and costs before enabling a connection. The builder's existing no-new-paid-data preference remains unchanged. [Credential documentation](https://docs.openbb.co/odp/python/user-guide/credentials).

The first accepted compiler slice remains the recorded price/quote-volume operator registry. RSI, MACD and other OpenBB indicators are future candidates only when a selected requirement needs them. Broad screening must not silently expand a declared pool set, feature family or trial budget.

## Qualification if a component is selected

Use a focused implementation check rather than reopening Probe A or starting a broad market investigation:

1. Identify the accepted requirement and compare direct implementation with the smallest useful OpenBB package. Add a dependency only when its saved work justifies its size and integration cost.
2. Pin the actual release and dependencies. The inspected docs contain V4 and V5 routes with breaking changes; do not mix examples or assume a development-branch feature is in the selected release. [V5 migration](https://docs.openbb.co/odp/python/migration-from-v4).
3. Supply qualified data with explicit dates, units and pool identity. Verify alignment, warm-up, empty/missing intervals, zero inputs, availability, precision and threshold-boundary behavior against our accepted conventions. A library's defaults need not match our 50-digit decimal evaluator.
4. Retain a wrapper that preserves source/result metadata and reports unsupported requests. The documented `technical.multi` skips unknown indicator names; an Edge OS request cannot silently drop a requested rule. Chart overlays are visual calculations, separate from data-returning indicator commands. [Technical extension](https://docs.openbb.co/odp/python/extensions/data-processing/technical), [chart indicator behavior](https://docs.openbb.co/odp/python/extensions/infrastructure/openbb-charting/indicators).
5. If exposed to Hermes, qualify the selected tool through the actual runtime with backend ownership checks, scoped secrets and recorded tool/configuration identities. Restrict generic tool dispatch as well as visible tool names. MCP descriptions alone do not enforce permissions.
6. If a calculation becomes part of executable rules, bind its tested semantic version and dependency identity to the strategy revision. Research access or a successful indicator calculation grants no readiness or wallet authority.

No package selection, installation, provider charge, new compiler capability or MCP activation is approved by documenting this route.

## Frontend lesson

Keep the research question, conclusion, reasons and next action visible first. An optional chart, table and contextual conversation should refer to the same exact investigation and data period. Changing a view's filters must not silently rewrite a saved finding or execute another study.

Borrow synchronized context and inspectable evidence. Beginners should not need to assemble a dashboard before receiving a useful answer. This documentation-based reference supplements the signed-in six-competitor UX pass; no OpenBB browser/screenshot review was performed. It does not expand the current five-task frontend prototype or require another visual redesign round.

## Recommendation and next use

Continue the current frontend comprehension tasks and existing core build decisions. At the applicable accepted backend ticket, consider a narrowly selected OpenBB calculation or MCP adapter if it saves work. Freeze any adoption in the build brief and catalog manifest, pass its focused checks, then expose the qualified entry. The core must remain runnable without OpenBB.
