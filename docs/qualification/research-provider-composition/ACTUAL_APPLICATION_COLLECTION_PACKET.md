# Actual application collection and Nansen qualification packet (PROPOSED)

Status: **PROPOSED; every actual step is NOT_RUN.** Prepared 2026-10-12 for #58 after RESEARCH-PORTS-LOCAL (`RELEASE-E2E-L2-20261012-RESEARCH-PORTS-LOCAL-v1`). This packet authorizes nothing. It lists the values one bounded actual run through the **application** must fix before any request. It extends, and does not replace, the library packets `docs/qualification/research-history-clients/ACTUAL_COLLECTION_PACKET.md` (P07) and `docs/qualification/nansen-report/LIVE_TEST_PACKET.md` (Nansen). Values those packets propose stay proposals here. Every unresolved value is `REQUIRED_DECISION`.

## 1. What the local milestone proves and does not prove

| Proven locally (AUTHORED, no egress) | Not proven |
|---|---|
| The application builds the accepted P07 HTTP client classes per job and drives them through an injected `HttpTransport`, under the job's request, byte, deadline and cancel guard | Any Envio HyperSync or QuickNode response, latency, error body, rate limit or cost |
| The application runs `run_research` through a durable job and saves request, evidence and report with hashes; reopen reads the saved row | Any Nansen response, account plan, rights, coverage or credit charge |
| Owner and global reservations before effect; KNOWN/UNKNOWN settlement for requests and Nansen credits | Real deducted-credit headers and their semantics on the selected plan |
| Restart, other-owner denial, worker death reconciliation, production refusal | DNS/connect containment of the HTTP clients (not exercised: no socket opens) |

## 2. Application composition the actual run needs (none exists yet)

| Item | Value |
|---|---|
| New settings value for HTTP sources (for example `research_source_clients = actual_http`) | `REQUIRED_DECISION`; must stay refused in production until the run is accepted |
| New settings value for Nansen (for example `nansen_research_mode = actual`) | `REQUIRED_DECISION`; same refusal rule |
| Evidence classes for actual replies (`PROVIDER_ACTUAL` for history; a Nansen actual class) | `REQUIRED_DECISION`; authored classes are never relabelled |
| Credential delivery to the composition module only (host secret store, file path outside the repository) | `REQUIRED_DECISION`; never in settings dumps, request bodies, datasets, reports, logs, browser or evidence |
| Real `HttpTransport` and Nansen transport implementations | Not written. A later, separately reviewed change |
| Catalog entry for an actual source (profile, scan, declared facts) | `REQUIRED_DECISION`; built from the P07 packet section 1–3 values |

## 3. History source through the application

| Field | Proposed value | State |
|---|---|---|
| Network and chain id | Monad mainnet, 143 | from the P07 packet; `REQUIRED_DECISION` to confirm |
| Endpoints and operations | HyperSync `POST /query`; QuickNode `eth_chainId`, `eth_getTransactionReceipt` | from the P07 packet |
| Query schema version | `envio-hypersync/1` (P07 transport) | fixed by accepted code |
| Pool, assets, orientation, units | MOE/WMON pool per the P07 packet; orientation | `REQUIRED_DECISION` |
| Window | per the P07 packet (outside the sealed holdout) | `REQUIRED_DECISION` |
| Corroboration sample | 8 receipts, deterministic positions | from the P07 packet |
| Client bounds | per the P07 packet section 4 | `REQUIRED_DECISION` |
| Application declaration bound `provider_requests` | ≤ the packet's total (proposed 36) | `REQUIRED_DECISION` |
| Owner and global caps for the run | `REQUIRED_DECISION` |
| Freshness and availability model | `REQUIRED_DECISION` |
| Data rights and retention | `REQUIRED_DECISION` |

## 4. Nansen report through the application

| Field | Proposed value | State |
|---|---|---|
| Operations | `tgm/holders`, `tgm/flows`, at most one page each | from the Nansen packet |
| Token and window | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`; window per the Nansen packet | `REQUIRED_DECISION` to confirm |
| Question | the user's saved request text, unchanged | fixed by the application |
| Request limit per report | `REQUIRED_DECISION` |
| Credit ceiling per report (`max_credits`) and owner/global `nansen_credits` caps | `REQUIRED_DECISION` |
| Account plan, per-call cost and rights | `REQUIRED_DECISION` |
| Premium labels, x402, MPP or any payment path | refused |

## 5. Proof the actual run must produce (observed under the approved packet, not inferred)

- **Positive history:** one keyed job; reservation, `ATTEMPT_STARTED`, client classes, request and response hashes, measured client calls equal to provider request ids, corroboration class, qualification verdict (LIMITED stays LIMITED), saved dataset reopened after a restart; adoption and replay only if the dataset binds.
- **Positive Nansen:** one keyed report; provider request ids and credit headers matched to the KNOWN settlement; the saved report reopened after a restart with no second call or charge; findings within the D01 limits.
- **Negative:** one provider refusal (for example an expired credential on a disposable key) saved with its stable code and no retry; the configuration refused in production.
- **Interruption:** a cancel between operations stops before the next request; unknown charges keep the full reservation.
- **Leak scan:** no credential, authorization header or provider text in API replies, browser results, logs or evidence.

## 6. Boundaries

No credential, account, provider call, payment, model call, hosting or publication is authorized by this document. Real Hermes tools and model integration stay in their separate pending lane. A run needs one exact released packet with every `REQUIRED_DECISION` filled and recorded builder approval.
