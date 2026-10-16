# Why Edge OS separates research from execution

A market question starts with uncertain meaning and incomplete evidence. A trading action needs exact rules, current permission, and a recoverable transaction record. Edge OS stores these as connected records with separate authority.

This page follows one Monad spot idea from the browser through research, replay, and one separately approved Kuru action. It explains which records bind the steps and what the user can recover after a failure.

## Approved completed-demo composition

This diagram names the responsibilities and trust boundaries in the approved completed-demo composition. It is an architecture view, not a deployment manifest.

```mermaid
flowchart LR
  Trader[Trader] <-->|"authenticated request and saved response"| Web[Next.js and React browser]
  Web <-->|"owner sign-in"| PrivyIdentity[Privy owner identity]
  Web <-->|"synchronous request and response"| API[FastAPI API]
  API <-->|"records, attempts, and durable jobs"| DB[(PostgreSQL)]

  API -->|"bounded interpretation attempt"| Job["Isolated Hermes job<br/>no provider key or network"]
  Job -->|"signed, bounded grant"| Relay["Credential-bearing relay"]
  Relay -->|"fixed CONNECT tunnel"| Gateway["Keyless egress gateway"]
  Gateway -->|"TLS stays end to end"| OpenRouter[OpenRouter model route]

  DB -->|"claim saved research job"| Research[Research worker]
  Research -->|"bounded source requests"| Sources[External source clients]
  Sources --> Envio[Envio HyperSync]
  Sources --> QuickNode[QuickNode JSON-RPC]
  Sources --> Nansen[Nansen API]
  Research -->|"save coverage, evidence, and report"| DB

  DB -->|"claim saved action job"| Action[Action worker]
  Action -->|"checked route request"| Kuru[Kuru Flow route]
  Action -->|"separate signing request"| Signer["Privy signer<br/>wallet restrictions"]
  Action -->|"one original transaction and receipt check"| Monad[Monad RPC]
  Action -->|"save journal and recovery state"| DB
```

The browser and API handle request-response interactions. A bounded Hermes interpretation is one API-owned attempt. Research collection and action execution are durable jobs: the API stores them in PostgreSQL, separate workers claim them, and each worker saves attempt state before an external effect. The browser can reopen the saved records without repeating collection or a transaction.

| Responsibility | Boundary and role | Source map |
| --- | --- | --- |
| Browser | Next.js 16.3.8 and React 19.3.0 render the research flow, use Privy for owner sign-in, and call the API. | [Web package](../../apps/web/package.json), [Privy setup](../../apps/web/lib/privy-config.ts), [API client](../../apps/web/lib/api.ts) |
| API | FastAPI 0.142.2 verifies the owner, serves authenticated reads and writes, coordinates a bounded interpretation attempt, and creates durable jobs. | [API package](../../apps/api/pyproject.toml), [application factory](../../apps/api/src/edge_os_api/main.py), [owner verification](../../apps/api/src/edge_os_api/core/authentication.py), [settings](../../apps/api/src/edge_os_api/core/settings.py) |
| Durable records | PostgreSQL stores owner-scoped records, lineage, interpretation attempts, job state, reservations, and original action journals. | [Database setup](../../apps/api/src/edge_os_api/core/database.py), [record models](../../apps/api/src/edge_os_api/records/models.py), [migrations](../../apps/api/migrations/) |
| Research worker | Claims frozen investigation jobs, collects declared sources, qualifies history, builds saved reports, and records usage and gaps. | [Investigation worker](../../apps/api/src/edge_os_api/research/investigation_jobs.py), [worker loop](../../apps/api/src/edge_os_api/core/worker_loop.py) |
| Hermes boundary | The isolated model job has no provider key or network. A separate relay holds its provider credential; the keyless gateway restricts egress to the pinned OpenRouter destination. | [Hermes interpreter](../../apps/api/src/edge_os_api/research/hermes_interpreter.py), [relay composition](../../apps/api/src/edge_os_api/research/hermes_relay_composition.py), [relay runner](../../scripts/hermes_provider_relay/relay_turn_runner.py), [egress gateway](../../scripts/hermes_provider_relay/egress_gateway.py) |
| Research source clients | Envio supplies indexed history, QuickNode checks chain identity and sampled receipts, and Nansen supplies a bounded holder and flow report. | [History clients](../../apps/api/src/edge_os_api/research/native_history_collection.py), [QuickNode corroboration](../../apps/api/src/edge_os_api/research_history/quicknode_corroboration.py), [Nansen collector](../../apps/api/src/edge_os_api/nansen_research/collector.py) |
| Action worker | Claims a saved action job, checks current authority and inputs, coordinates reservations, and advances the original transaction through recovery. | [Action worker](../../apps/api/src/edge_os_api/execution/worker.py), [admission](../../apps/api/src/edge_os_api/admission/service.py), [transaction journal](../../apps/api/src/edge_os_api/execution/original_transaction.py) |
| Route, signer, and chain | Kuru provides route data, a separate Privy signer handles the permitted wallet request, and Monad RPC carries the transaction and receipt observation. | [Kuru preparation](../../apps/api/src/edge_os_api/kuru_flow/transaction_preparation.py), [Privy signer](../../apps/api/src/edge_os_api/execution/privy_signer.py), [original transaction path](../../apps/api/src/edge_os_api/execution/original_transaction.py) |

The API uses the Privy app ID and public verification key to check owner tokens. It refuses a Privy app secret and does not load `.env` files automatically. Signing uses a separate execution boundary. That boundary receives no browser login token and cannot administer wallet policy. Research credentials are admitted through a code-owned release before a source client reads them or opens a provider connection; the same release binds the source, endpoint, and limits.

## Follow the research path

```mermaid
sequenceDiagram
  actor Trader
  participant Web as Research UI
  participant API as Owner-scoped API
  participant DB as PostgreSQL
  participant Hermes as Hermes interpreter
  participant Worker as Research worker
  participant Sources as Envio, QuickNode, Nansen
  participant Replay as Hypothetical replay
  Trader->>Web: Submit a market question
  Web->>API: Save original request and restrictions
  API->>DB: Append intake and attempt records
  API->>Hermes: Request bounded interpretation
  Hermes-->>API: Return structured fields
  API->>DB: Save checked interpretation
  Trader->>API: Adopt rules and freeze investigation
  API->>DB: Save declaration and quota reservation
  Worker->>DB: Claim job and commit attempt
  Worker->>Sources: Collect bounded source records
  Sources-->>Worker: Return records, coverage, gaps, and usage
  Worker->>DB: Save dataset and descriptive report
  Trader->>API: Request a delayed replay
  API->>Replay: Check saved revision and dataset
  Replay-->>API: Return complete or unavailable result
  API->>DB: Save exact inputs and result
  Trader->>API: Reopen saved result
  API->>DB: Check owner and saved hashes
  DB-->>Web: Return saved result without recollection
```

The request preserves the trader's original words and restrictions. The interpretation adds candidate fields with their source, uncertainty, and adoption state. A proposal remains pending until the trader adopts it. The router can ask a question, reject an unsupported request, keep an unresolved result, or produce a draft for the compiler.

The API saves a request before it calls Hermes. A saved attempt identifies the prompt, response shape, model configuration, and request. If the worker cannot confirm the attempt result, it keeps the outcome unknown. It does not silently repeat a provider call after restart.

## Compile exact, supported rules

The compiler accepts JSON expression trees over spot price and quote volume. Its supported operators include returns, relative volume, lag, sums, means, comparisons, and Boolean combinations. It checks units, the market, a five-minute schedule, required history, sizing, and finite work. It rejects unsupported operators and arbitrary generated code.

Compilation requires execution permission to remain <code>NOT_GRANTED</code>. Publication compares canonical strategy bytes with the saved draft and expected parent revision. Each immutable revision stores the canonical content, a content hash, and a semantic manifest hash. The manifest fixes the strategy language and calculation meaning.

A research report therefore cannot grant permission to spend. A trader must review and adopt the exact rule revision before it can feed a later workflow.

## Follow each typed record

Each record carries a distinct part of the lineage.

| Record | What it preserves |
| --- | --- |
| <code>IntakeRequest</code> | The original words, restrictions, requested job, and input class. |
| <code>FieldEvidence</code> | Each field's state, origin, source, uncertainty, adoption, and conflicts. |
| Investigation declaration | The hypothesis, rule map, field origins, trial and evaluation identities, source profile, time range, limits, and first-access order. |
| Dataset and research report | Raw evidence, normalized buckets, coverage, gaps, availability, provenance, contrary findings, and source identities. |
| <code>StrategySpec</code> and revision | The typed rule, exact market and timing, canonical content, and semantic manifest. |
| Saved replay | The strategy revision, dataset, run configuration, result, and content hash. |
| Wallet and action records | The owner, agent, wallet, strategy revision, consent terms, attempt identity, reservations, receipt evidence, and recovery state. |

The seven-field research envelope supplies the record type, owner, operation, and creation identity. The database adds lineage and sequence fields. The [P02 contract](../contracts/p02/contract.json) defines the exported shape.

## Freeze the question before collecting outcomes

An investigation declaration binds the original request to its hypothesis and rule map. It also records field origins, trial and evaluation IDs, source profile, time range, and collection limits. It starts before outcome labels are read. The worker stores that order so the report can show what the investigator could see.

A job reserves owner and global request and compute limits before collection. PostgreSQL locks one job against concurrent workers. Before a provider effect, the worker rechecks the frozen source, records <code>ATTEMPT_STARTED</code>, and commits it.

Envio HyperSync supplies indexed swap history. QuickNode checks the Monad chain ID and corroborates a declared sample against transaction receipts. The normalizer converts source records into five-minute buckets with coverage, gaps, availability, and claim-level results. A complete empty bucket has zero volume and no close price.

The saved dataset keeps raw source records beside normalized buckets, query identities, evidence class, qualification, and hashes. A sample does not establish every claim. Missing delivery evidence stays missing. Only complete, overall <code>QUALIFIED</code> history can produce a market binding.

The comparison reads training and descriptive partitions. It does not read validation or holdout outcomes. Its report saves contrary findings, source order, and its dataset and rule identities. A descriptive result does not establish statistical support.

Nansen collects bounded holder and flow records through a separate job. Its deterministic report uses a keyword map to limit which parts of the question its evidence can answer. An address list does not establish unique people, purchases, profit, concentration, or a trading edge. The saved report links the request, evidence, report, hashes, response references, and settlement.

## Read a saved replay as a hypothesis

Each replay binds an exact strategy revision, dataset, market, time window, starting account, and run-configuration ID. It checks hashes, source qualification, coverage, warm-up, protected partitions, and when each observation became available. Reusing the same request key returns the saved result. Different inputs under that key conflict. The app saves explained <code>UNAVAILABLE</code> outcomes as well as complete results.

The demo uses a fixed 300-second delay after each source bucket closes. A decision uses evidence available at that delayed time. A hypothetical fill uses the next delayed historical close and saved fee and slippage assumptions. The result labels each fill as hypothetical. It does not treat a historical close as a current quote.

If the next close is late, unknown, unqualified, or empty, the replay records <code>FILL_UNAVAILABLE</code>. It does not substitute an earlier or later price, extend the window, or retry the fill. The replay omits gas, spread, added price impact, and capacity. Those limits remain visible with the result.

## Keep owner identity separate from wallet authority

Privy sign-in supplies an access token. The API checks its signature, issuer, audience, expiry, and subject, then maps the Privy DID to an internal owner. API reads use that verified owner. A foreign owner's record returns 404. The ordinary API accepts public verification keys and refuses a Privy app secret. Login creates no agent wallet or signing authority.

Wallet setup binds an owner and agent to an exact strategy revision, network, and returned wallet identity. It saves dispatch intent before wallet creation. Binding requires an independent lookup of the exact wallet ID, owner, chain type, and address. If the response is lost and no exact wallet ID is known, recovery stays <code>UNKNOWN</code>. It never selects the newest wallet or repeats creation.

Funding and consent are separate records. Funding credits only confirmed server observations. Consent binds an exact wallet and revision to the allocation, cumulative allowances, gas limit, allowed actions, and expiry. A deposit does not activate trading or reset allowances.

Admission also requires an independently qualified Kuru route and enough exit capacity for an acquisition. Deterministic checks bind the action to the owner, wallet, network, strategy, funds, fresh inputs, and active permission. The current wallet policy must match its approved version before preparation and again before submission. The independent wallet restriction covers the permitted network, contract, signing method, function, and supported argument limits. If enforcement of a required restriction cannot be verified, its state is <code>UNKNOWN</code> and the affected action is denied. Policy administration stays separate from the execution credential. See the [execution authority design](../superpowers/specs/2026-09-29-edge-os-hackathon-design.md#two-enforcement-layers).

The owner reviews this permission separately from the research report. Each agent uses its own wallet. An account summary combines records; it does not combine spending authority.

## Journal one action and recover its original attempt

An action request creates a saved job. The worker checks the exact owner, wallet, strategy, current observation, and permission. The admission service reserves capital, gas, allowances, and attributed inventory under per-wallet locks. The bounded action allows one open or pending position per wallet and network.

The executor validates the supplied Kuru Flow route against the approved network, ERC-20 trading tokens, recipient, input, minimum output, route, fees, allowance, and expiry. Native MON is reserved for gas; it is not a trading leg. Privy signs the original transaction under wallet-specific restrictions. The executor receives no login token and cannot change its policy. It checks the approved policy version before preparing and submitting the transaction.

The transaction engine records preparation, signing intent, signed bytes, and broadcast intent in order. Before signing and broadcast, it checks current stops and expiry. It broadcasts the original signed bytes once. It does not requote, choose a new nonce, or sign again after an uncertain result.

The application reconciles from server-side receipt evidence for the original attempt. An uncertain outcome remains <code>UNKNOWN</code>. Reservations and the exclusive action claim stay in place. The system does not send a replacement transaction. A stop blocks selected unsent work. Removing signer access blocks new submissions. Neither control cancels a broadcast action or sells remaining holdings.

These states give the owner a specific recovery path. Inspect the attempt and its receipt evidence. Reconcile that same attempt before requesting a new action.

The sequence keeps each external effect attached to the saved attempt:

```mermaid
sequenceDiagram
  actor Owner
  participant API as Owner-scoped API
  participant DB as PostgreSQL
  participant Worker as Action worker
  participant Policy as Independent wallet policy
  participant Kuru as Kuru Flow route
  participant Privy as Privy signer
  participant Monad as Monad RPC
  Owner->>API: Fund wallet and approve exact action terms
  API->>DB: Save wallet binding, consent, and action job
  Worker->>DB: Check authority, reserve resources, and save attempt
  Worker->>Policy: Check approved policy version before preparation
  Worker->>Kuru: Request bounded route quote
  Kuru-->>Worker: Return route and calldata
  Worker->>DB: Save validated route and signing intent
  Worker->>Policy: Recheck policy version before submission
  Worker->>Privy: Request permitted signature for original attempt
  Worker->>DB: Save signed bytes, hash, and broadcast intent
  Worker->>Monad: Broadcast original bytes once
  Worker->>Monad: Observe original receipt
  Worker->>DB: Reconcile result, inventory, and reservations
  API-->>Owner: Return action state, receipt references, and holdings
```

If a response is uncertain, the worker checks receipt evidence for that same attempt. It does not sign or broadcast a replacement. Reservations and the exclusive claim stay in place until the original outcome is known or a safe pre-broadcast denial is proved.

## Keep provider spending bounded

Hermes interpretation uses a provider relay. The API records and reserves worst-case model liability before a send. The model job has no provider key or network access. A credential-bearing relay accepts a signed bounded grant and sends through a keyless gateway to a fixed destination. TLS continues from the relay to the provider.

The source runtime accepts only a code-owned release with an approved identity. The application checks that release before it reads a source credential or opens a provider connection. The Hermes release pins the OpenRouter destination, model route, request schema, job image, and price snapshot. Request data and environment settings cannot add a source or alter the approved route. A credential alone activates no provider path.

A valid usage record settles the model reservation. Missing or invalid usage keeps the liability <code>UNKNOWN</code>. A started relay request does not run again after restart. Accepted interpretation text can be reparsed without another provider request.

Research quotas track requests, compute, and Nansen credits in separate units. Unknown usage keeps its reservation. These ledgers do not automatically reconcile outside spending or provider invoices.

## Where to inspect the implementation

| Responsibility | Source |
| --- | --- |
| Browser screens and authenticated requests | [Web components](../../apps/web/components/), [auth](../../apps/web/lib/auth.tsx), [API client](../../apps/web/lib/api.ts) |
| API composition and identity | [Application factory](../../apps/api/src/edge_os_api/main.py), [authentication](../../apps/api/src/edge_os_api/core/authentication.py) |
| Record validation and research lineage | [Record models](../../apps/api/src/edge_os_api/records/models.py), [research service](../../apps/api/src/edge_os_api/research/service.py), [interpretation checks](../../apps/api/src/edge_os_api/research/interpretation_response.py) |
| History, comparison, and Nansen reports | [Investigation jobs](../../apps/api/src/edge_os_api/research/investigation_jobs.py), [history normalization](../../apps/api/src/edge_os_api/research_history/history_normalizer.py), [Nansen reports](../../apps/api/src/edge_os_api/research/nansen_reports.py) |
| Strategy and replay | [Compiler](../../apps/api/src/edge_os_api/strategies/compiler.py), [saved replay](../../apps/api/src/edge_os_api/replay/saved_runs.py), [delayed replay profile](../implementation/DELAYED_HISTORY_REPLAY_PROFILE.md) |
| Wallet and execution records | [Wallet setup](../../apps/api/src/edge_os_api/wallet_setup/service.py), [consent](../../apps/api/src/edge_os_api/consent/service.py), [admission](../../apps/api/src/edge_os_api/admission/service.py), [transaction engine](../../apps/api/src/edge_os_api/execution/original_transaction.py), [recovery](../../apps/api/src/edge_os_api/recovery/service.py) |
| Provider relay and local fixture | [Hermes relay composition](../../apps/api/src/edge_os_api/research/hermes_relay_composition.py), [egress gateway](../../scripts/hermes_provider_relay/egress_gateway.py), [local runbook](../../deploy/local/RUNBOOK.md) |

The [P02 record contract](../contracts/p02/contract.json), [P06 compiler profile](../implementation/P06_COMPILER_PROFILE.md), [separate-wallet decision](../adr/0007-separate-user-owned-agent-wallets.md), and [execution boundary decision](../adr/0005-model-and-execution-authority-boundary.md) define the versioned interfaces and authority limits.
