# Edge OS

**Ask a trading question in plain English. Find out if the idea holds before you risk money. The next step is an agent that trades it only inside limits you sign.**

Edge OS is an operating system for trading edges, used from one agentic trading terminal. It is not a full market terminal. It starts with meme-token traders on Monad. A research agent checks your idea against on-chain history and saves what it found. Rules that hold up can be replayed on past prices. The plan is an agent with its own wallet that trades on Kuru, where a wallet permission you sign decides what it may do. No model chooses a trade.

[Pitch video](https://vimeo.com/1235649955) · [Technical demo](https://vimeo.com/1235648532) · [Live site](https://edgeos.fun)

First built for the Monad hackathon, Onchain Finance & Trading track.

## What works today

Edge OS is a working prototype, not a launched product.

- **Works on an operator-run local setup.** Research on real Envio, QuickNode and Nansen data, rules saved with a hash, and replay on past prices.
- **Sign-in works on the live site.** Research is not available on [edgeos.fun](https://edgeos.fun) yet, and the site cannot connect a wallet or trade.
- **One real trade, outside the app.** A real Kuru swap ran on Monad mainnet on 22 October 2026 from an agent wallet, under an operator script. The transaction is `0xec980ee5a8dbb87d47be7682d3700d97f898a38f3d034d486266736fee3a1118`.
- **Not working yet.** Signed permissions do not work yet, so limits are held in code. No real in-app trade has run.

## The problem

A meme token on Monad jumps hard in five minutes. Do you buy?

Most traders guess. Some hand the guess to a bot that holds their keys. The research behind the guess is spread across a chart, a social feed, a wallet explorer, a notebook and the trading venue. By the time a trade happens, the original question is gone, the evidence against the idea was never written down, and nobody can say why the trade was made.

The tools that try to help make it worse in quieter ways:

- A backtest can look great because it ignores spread, slippage and fees, or because someone tried many variants and kept the best one.
- A model can turn "buy when it pumps" into precise-looking rules that mean something the trader never said.
- A bot that executes a trade does not prove the idea had an edge. It only proves the bot had the keys.

The cost is a trade on a false edge, a round trip, or a wallet emptied by a rule nobody checked.

## What Edge OS does

1. **It checks the idea before you trade it.** You describe a hunch, a thesis or a question about a market. A Hermes research agent asks what it needs to know and proposes a study with a fixed scope and budget. Code then collects the data and saves a report. The report shows supporting evidence, contrary evidence and what is missing. It is allowed to say no.
2. **It turns an idea that holds into exact rules.** Supported rules compile into a strategy revision that cannot change after you save it. You can replay it on past prices and see trades, costs, gains, losses and drawdown, with every assumed fill labelled.
3. **It is designed to trade only inside the limits you approve.** In the plan, each agent gets its own Privy wallet, linked to yours. You approve one strategy revision with its tokens, size, spending limit, expiry and stop rules. The agent trades on Kuru inside that permission, and you can stop it at any time. A good report or a good backtest never grants trading permission by itself.

Edge OS is built on the first principles of quantitative trading. Signals stay separate from position sizing and account results. Every variant tried is kept, so a lucky result cannot hide the failed ones. Strategies compile to a typed language with exact units and rules, so an agent will run what was tested. Formal checks for overfitting and multiple testing are next on the plan.

## A walkthrough

The example below uses the MOE token on Monad. The numbers in it are illustrative. Steps 6 and 7 say what works today and what comes next.

**1. Ask in plain English.** A trader writes: "Buy MOE when it pumps hard on big volume. Never more than 20 WMON a trade, and skip anything that launched less than a week ago." Edge OS keeps those words exactly as written. The agent asks only what it needs, such as what "pumps hard" means and how long to watch after each rise. Nothing it suggests is adopted until the trader chooses it.

![Edge OS asks what "pumps hard" means before it plans the study](docs/assets/readme/1-clarify.jpg)

**2. Review the study plan.** The trader sees the market, time window, question, rule and research budget before any data is read.

![The study plan lists the market, period, conditions and costs before research starts](docs/assets/readme/2-study-plan.jpg)

**3. Run the study.** A research worker pulls swap history from Envio, checks transaction receipts through QuickNode, and adds holder and flow data from Nansen. Every variant tried is recorded, so a failed attempt cannot disappear from the result. The trader can stop the study at any point and keep what is already saved.

![The study shows each step, the credits used and what is saved so far](docs/assets/readme/3-study-progress.jpg)

**4. Read the report.** In this example, the idea does not hold up on later prices. The report says so, shows why, and keeps what still counts in the idea's favor. The trader learns this before placing a trade.

![The report says the idea did not hold up and shows the reasons](docs/assets/readme/4-report.jpg)

**5. Replay the rules.** When an idea does hold, the trader reviews the exact rules beside a plain-English summary, then tests them on past prices with a starting balance, trade size and costs they choose.

![A test on past prices shows simulated trades, gains and the account balance over time](docs/assets/readme/5-replay.jpg)

**6. Go live.** The only real trade so far is the 22 October swap, run by an operator script under limits held in code. Next, the trader creates an agent, funds its wallet, and signs one permission: which strategy revision, which tokens, how much per trade, the total limit, when it expires and when it stops. After that approval, routine trades will run without the trader online. The screen below shows that planned review.

![The planned permission review shows the limits before an agent can trade](docs/assets/readme/6-permission.jpg)

**7. Inspect and stop.** Agents, Positions and Funds list records by agent and wallet. On the live site they show no live wallet data. The app has separate stop and remove controls, each explained before you use it, and a read-only conversation that answers fixed questions from the same records. Selling a position, withdrawing and open chat come next.

![Positions are listed by agent and wallet](docs/assets/readme/7-positions.jpg)

## How each sponsor tool is used

| Tool | What it does in Edge OS | Source |
| --- | --- | --- |
| Envio HyperSync | Supplies Monad swap history for the market and time window in each study. | [History collection](apps/api/src/edge_os_api/research/native_history_collection.py) |
| Nansen | Adds holder and token-flow data to the report. Holder data describes who holds a token. It does not prove that a wallet made money. | [Nansen collector](apps/api/src/edge_os_api/nansen_research/collector.py) |
| Privy | Signs the trader in. It held the agent wallet for the 22 October swap, and each agent will get its own wallet, linked to the owner. In a testnet run, a removed agent signer was refused and the owner could still sign. | [Privy setup](apps/web/lib/privy-config.ts) |
| Kuru | Ran the 22 October spot swap on Monad, under an operator script. In-app trades come next. Edge OS will check each route against the approved permission before signing and save the receipt. | [Trade preparation](apps/api/src/edge_os_api/kuru_flow/transaction_preparation.py) |

## How it works

```mermaid
flowchart LR
  Q[Trader's question] --> H[Hermes research agent]
  H --> P[Study plan the trader approves]
  P --> E[Envio swap history]
  P --> N[Nansen holder data]
  P --> R[QuickNode receipt checks]
  E --> D[Saved dataset]
  N --> D
  R --> D
  D --> RP[Report: yes, no or unresolved]
  RP --> S[Exact strategy revision]
  S --> B[Replay on past prices]
  S --> M[Planned: wallet permission the trader signs]
  M --> A[Agent wallet]
  A --> K[Planned: in-app trades on Kuru]
  K --> L[Receipts and positions]
```

Two more tools do important work outside the sponsor list:

- **Hermes** runs the research agent. It interprets the trader's request and proposes the study, and code writes the report. Hermes runs in a sandbox with no API key and no internet access, and it cannot grant trading permission or submit a transaction. See the [interpreter](apps/api/src/edge_os_api/research/hermes_interpreter.py).
- **QuickNode** confirms the chain and checks a sample of transaction receipts against the Envio history. See the [receipt checks](apps/api/src/edge_os_api/research_history/quicknode_corroboration.py).

The research side and the trading side will meet in one place, the permission the trader signs. Everything left of it can read data and write reports. Until signed permissions work, the limits are held in code.

A few design rules hold the system together. The rules for trades exist in code and local tests. No real in-app trade has run through them yet.

- **The model proposes, code decides.** Hermes proposes the study. A typed rule compiler, a risk check and the wallet's signing policy decide what an agent may do. A model output cannot widen a permission.
- **A saved strategy cannot change.** Each saved revision is fixed. Editing the rules creates a new revision, which the trader must review and adopt.
- **The research market and the trading route are separate.** A study about a pool does not imply that Kuru can trade it. Edge OS checks the route before an agent can use it.
- **An uncertain trade is never retried blindly.** If a transaction's result is unknown, Edge OS keeps the original attempt and checks it against on-chain receipts before anything else is sent.
- **Every wallet is separate.** One agent's pending trade cannot use or block another agent's funds.

The [architecture guide](docs/architecture/README.md) covers services, jobs, records and recovery in more detail.

## Orbio

Orbio is an AI gateway. Its usage unit is CREDIT, and 1 CREDIT is USD 1 of usage. No real call has run through Orbio yet.

Built:

- A [model route to Orbio](apps/api/src/edge_os_api/research/hermes_relay_composition.py) beside OpenRouter. The operator selects one route per release, and there is no default.
- A model budget shown in CREDIT. Each owner has one limit, shared by all of their studies, and the [spend ledger](apps/api/src/edge_os_api/research/provider_spend_ledger.py) refuses a call that could go over it before the call is sent.
- A saved route for each attempt, and the line "Model calls ran through Orbio" near the study's total cost.

Not built yet: X tools, Sign in with Orbio and recurring edge checks.

Next, I run one real study through Orbio and compare its saved cost with Orbio's account page. The three missing parts follow that study.

## Bugs that shaped the design

The rule I kept coming back to: a result is only useful if it cannot quietly lie. These are real bugs from this repository. Each one could have made a result look better or safer than it was.

- **The replay could peek at the answer key.** Each study keeps its last part of the data back as a final check. A replay window could run past that point, and a five-minute bucket ending exactly on the boundary was counted on the wrong side. That leaks future data into the test. Replays now stop before the held-back data, buckets count only the time they cover, and a study with a missing plan protects its whole window. Fixed in [f4fc208](https://github.com/edge-os-app/edge-os/commit/f4fc208) and [8cc0e57](https://github.com/edge-os-app/edge-os/commit/8cc0e57).
- **"Below -2%" was treated as a misreading.** When a trader wrote a negative threshold, the check that every number comes from the trader's own words could not find the minus sign, so a correct interpretation was rejected every time. Hostile model output could also crash the parser and leave the attempt stuck. The check now reads "-2%", "minus 2%" and "negative 2 percent", and bad model output becomes a clean rejection. Fixed in [c2b64bc](https://github.com/edge-os-app/edge-os/commit/c2b64bc).
- **One broken log line could close a half-known trade.** If a swap receipt had one malformed log, the code still added up the valid parts and released the reserved funds. That records a partial amount as the whole trade. Now any malformed log makes the amounts unknown, the reservation stays in place, and expiry is checked again before signing and before sending. Fixed in [dac088a](https://github.com/edge-os-app/edge-os/commit/dac088a) and [74f59ef](https://github.com/edge-os-app/edge-os/commit/74f59ef).
- **`true` matched request 1.** In Python, `True == 1`, so an RPC reply with `"id": true` was accepted as the answer to request 1. The client now requires an integer ID that equals the one it sent. The same fix stopped provider error text from reaching users and made the deadline cover the whole call. Fixed in [9d9d815](https://github.com/edge-os-app/edge-os/commit/9d9d815).

## Roadmap

Edge OS starts with one job done well: short-term momentum and reversal ideas on Monad meme-token spot markets, traded on Kuru.

| Stage | What ships |
| --- | --- |
| Built | Research agent with Envio, QuickNode and Nansen data. Saved reports that can say no. Exact strategy rules with a plain-English summary. Replay on past prices. Agents, Positions and Funds views. The Orbio route and CREDIT limits. |
| Next | Research on the live site. Signed permissions with limits, expiry and stops. Real in-app trades. Agents that run signed rules on Kuru while you are offline. A small catalog of research add-ons you can switch on per agent. Wider data coverage and more strategy templates, guided by trader sessions. |
| Next six months, no launch date set | A second venue and chain after Monad, with Arbitrum, Robinhood Chain and Solana as the targets. Liquidity providers, with the same research, rules and replay for questions about pool fees, inventory and rebalancing. Perp traders on venues such as Hyperliquid, and prediction market traders. These groups get research, simulation and live trades inside signed limits. |
| Later | Strategy creators who publish or license tested strategies, and users who inspect, copy or fund them. |

Edge OS makes no promise of profit and never says an edge is proved. A pass means only that the idea passed its stated tests.

## Run it locally

The [local runbook](deploy/local/RUNBOOK.md) lists the required Python, Node.js and Docker versions, the settings, and the command order. This runbook profile uses test data, not real research data, and has no route to outside services. The API reads environment variables directly and does not load `.env` files.

On 16 October 2026, 2,845 API tests and 253 web tests passed on `main`. Run them yourself:

```bash
cd apps/api && uv run pytest    # API, Python 3.14
cd apps/web && npm test         # web app, Vitest
```

## Project documents

- [Architecture guide](docs/architecture/README.md): how the parts fit together, with links to the code
- [Design decisions](docs/adr/): eight short records of the main technical choices
- [Local runbook](deploy/local/RUNBOOK.md): settings and commands to run Edge OS on your machine

## Team

Edge OS is built by David ([@degencodebeast](https://github.com/degencodebeast)), solo founder.
