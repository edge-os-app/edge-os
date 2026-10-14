# Actual research demo: evidence map

Task `ACTUAL-RESEARCH-READINESS-L4-20261014-LOCAL-v1`. Base `012fb1597d061e4d263afc3d8be0538c4298b48f`. Traceability only. This map binds each value and check in [OPERATING_PACKET.md](OPERATING_PACKET.md) to the code at `012fb15` and its contract. It marks no actual item as passed.

Paths below are relative to `apps/api/src/edge_os_api/` unless they start with `docs/`. "Contract" means [the composition contract](../research-provider-composition/CONTRACT.md).

## 1. Release values to code

| Packet value | Code symbol that enforces or uses it | Contract | Refusal when wrong |
|---|---|---|---|
| `kind` `ACTUAL`, exact SHA-256 approved | `core/research/operating_release.py`: `check_release`, `APPROVED_RELEASES`, `release_sha256` | §3 | `operating_release_not_approved` |
| One composed release for API and worker | `core/research/released_runtime_bootstrap.py`: `server_research_runtime`, `RELEASE_DEFINITIONS`; called from `main.py` and `research/investigation_jobs.py` `main` | §12.4 | `operating_release_invalid` (more than one, or wrong id) |
| History over `StdlibHttpTransport` | `operating_release.check_release(network_transport=...)`; `released_source_runtime.open_released_runtime` | §3, §5 | `actual_release_needs_network_transport` |
| Nansen origin `https://api.nansen.ai` | `operating_release._check_nansen`, `nansen_research/http_transport.NANSEN_ORIGIN` | §12.1 | `operating_release_invalid` |
| Nansen network factory | `released_source_runtime.NansenHttpFactory`, `_nansen_network` | §12.2 | `actual_nansen_transport_missing` |
| RPC methods `eth_chainId`, `eth_getTransactionReceipt` | `operating_release.RPC_METHODS`, `_check_history`; `PreparedHistory.clients` passes `allowed_methods` to `HttpQuickNodeRpcClient` | §3 | `operating_release_invalid` |
| `provider_requests` 13 ≥ 4 + 1 + 8 | `operating_release._check_history`; `research/history_dataset.requests_needed` | §3 | `operating_release_invalid` |
| `max_pages` 4 ≤ `provider_requests` 13 | `core/request_schemas.HistoryResourceBounds.pages_fit_requests` | §3 | `422` validation |
| `max_bytes` 4,194,304; `max_rows` 2,000; `compute_seconds` 600; `deadline_seconds` 600 | `HistoryResourceBounds` field ceilings (4,194,304; 10,000; 600; 3,600) | §6 | `422` validation |
| Release limits equal declaration bounds | `research/investigation_adoption.py` (`release_bounds_mismatch`) | §6 | `422 release_bounds_mismatch` |
| `max_response_bytes` 2,097,152 ≤ `max_bytes` | `operating_release._check_history` | §3 | `operating_release_invalid` |
| Per-call deadline ≤ time left | `released_source_runtime.PreparedHistory.clients`, `HashingTransport.request`; `investigation_jobs.release_http_clients` (saved-deadline anchor) | §11 | `SourceTimeout`, unknown liability |
| `max_blocks_per_page` 10,000 | `research_history/http_clients/envio_query_client.py` (`to_block`, `max_num_blocks`, `include_all_blocks`) | P07 packet §4 | client error before send |
| QuickNode URL on `quicknode_host`, `https` | `released_source_runtime.prepare_history`, `validate_endpoint` | §11 (B4) | `operating_release_endpoint_mismatch` |
| Source id not a recorded source | `research/history_dataset.check_release_source` | §11 (B5) | `operating_release_invalid` |
| Nansen bounds: reply ≤ `max_bytes` | `operating_release._check_nansen` | §12.1 | `operating_release_invalid` |
| Nansen request equals release | `released_source_runtime.nansen_mismatches`; `investigation_jobs` | §6 | `422 release_request_mismatch` |
| Nansen 5 + 1 credits; `premium_labels` false | `nansen_research/nansen_client.OPERATIONS`, `ALLOWED_BODY_FIELDS`, `_enforce_budget` | Nansen packet | `CREDIT_LIMIT` |
| Nansen deadline and late reply | `released_source_runtime.ReleasedNansenTransport`, `PreparedNansen.transport` | §12.3 | `NansenTimeout` (`DEADLINE`, `TIMEOUT`) |
| Owner and global reservations | `research/investigation_jobs.caps`, `_settle`, `_finish`; `core/settings` defaults 16 requests, 900 s, 50 credits | §6 | `BUDGET_EXHAUSTED` |
| Evidence class from composition | `released_source_runtime.ReleasedSourceRuntime.evidence_class`, `transport_kind`; `history_source` | §5 | `422 history_source_class_mismatch` |
| Declared facts labelled | `released_source_runtime._basis` (`RELEASE_DECLARATION`); `research/native_history_collection.py` merges `provider_facts` | §3 | none: declarations are accepted as written |
| Protected partitions unread | `research/history_dataset.PROTECTED_ROLES`, `protected_from`, `readable_until`; `research/comparison_runs.py` | §12.5 (protected partitions preserved) | `protected_partition_not_authorized` |

The row "Declared facts labelled" has no refusal. The code passes release `provider_facts` into P07 unchanged. Only review of the release definition stops a false declaration. [OPERATING_PACKET.md section 4.1](OPERATING_PACKET.md#41-history-part-historyrelease) sets the honest values.

## 2. Verdict and replay rules

| Check | Code symbol | Expected result for this packet |
|---|---|---|
| Corroboration class | `research_history/quicknode_corroboration.py` (`COMPLETE` only when every record is compared) | `SAMPLED`, 8 of about 87 |
| Claim verdicts | `docs/qualification/p07/qualification.py` `qualify` (any `LIMIT` or `ASSUMPTION` gives `LIMITED`; any failed or missing check gives `UNRESOLVED`) | `LIMITED` or `UNRESOLVED` |
| Feasibility | `docs/qualification/p07/qualification.py` `feasibility` (`UNDECLARED` without floors) | `UNRESOLVED` unless floors are approved |
| Market adoption | `research/market_adoption.py` (needs `QUALIFIED`, `COMPLETE`, `QUALIFIED_BINDING`) | refused |
| Replay admission | `replay/simulator.py` `ADMITTED_EVIDENCE_CLASSES`, `DATASET_COVERAGE_UNPROVEN` | refused, saved as unsupported |
| Provider class consistency | `replay/history_inputs.py` (`evidence_class_inconsistent`) | passes only for an `ACTUAL` release dataset |
| Fill label | `replay/saved_runs.py` | `simulated fills`, only if a replay runs |

## 3. Packet checks to proof

Every row is `NOT_RUN`. "Local" names the stand-in proof that already passed at `012fb15`, from [MOUNT_SUCCESSOR_EVIDENCE.md](../research-provider-composition/MOUNT_SUCCESSOR_EVIDENCE.md) and contract §7. A local pass is not actual evidence.

| Packet check | Actual proof required | Local proof | Status |
|---|---|---|---|
| Release identity | Same SHA-256 in `GET /v1/research/history-sources`, declaration, job and dataset | `test_nansen_runtime_mount.py` bootstrap tests | `NOT_RUN` |
| Original attempt | One job and reservation per key; one `ATTEMPT_STARTED` | `test_concurrent_starts_keep_one_original_job_per_key…` (history) | `NOT_RUN` |
| Request counts | Saved client calls equal independent provider-side counts | Verifier: saved counts equal the stand-in's own log | `NOT_RUN` |
| Billing and credits | Provider usage; Nansen credit headers equal `KNOWN` settlement | Stand-in 6 credits `KNOWN` | `NOT_RUN` |
| Provenance and order | `transport.request_sha256`, `response_sha256`, `response_status`, `endpoint_hosts`; page digests | `HashingTransport` tests | `NOT_RUN` |
| Coverage | `release_coverage`, bucket counts, corroboration class | Sampled-corroboration fault row | `NOT_RUN` |
| Saved, reopened, restarted | Byte-identical rows after API and worker restart; no new provider count | Verifier restart specs | `NOT_RUN` |
| UNKNOWN liability | Whole reservation unknown on lost reply, late reply, killed worker | Fault matrix rows; `collection_outcome_unknown`, `nansen_outcome_unknown` | `NOT_RUN` |
| No auto retry | One call per step; refusal stops the run | `test_a_refused_first_reply_stops_the_run_once_without_retry` | `NOT_RUN` |
| Negative without a call | `operating_release_changed`, `operating_release_credential_unavailable`, `stand_in_refused_in_production` | Release research tests and verifier missing-key job | `NOT_RUN` |
| Other owner | Owner B 404 | Verifier owner B denial | `NOT_RUN` |
| Session | Signed-out or expired session cannot read | Depends on real Privy login | `NOT_RUN` |
| Secret scan | Zero key and header matches in replies, browser, logs, rows, evidence | Verifier: no stand-in key in any saved row, log or browser result | `NOT_RUN` |
| Cleanup and reconciliation | reserved = consumed + released + unknown, per resource | Ledger tests | `NOT_RUN` |

## 4. Demo and sponsor claims to proof

A claim may be made only when its required proof exists. Until then the claim is `NOT_RUN`.

| Claim | Required actual proof | Current status |
|---|---|---|
| Envio: actual Monad history through the application | Section 3 history rows with an `ACTUAL` release; saved dataset with HyperSync page digests | `NOT_RUN` |
| QuickNode corroboration | Saved `eth_chainId` 143 and 8 receipt results | `NOT_RUN` |
| Qualified dataset | P07 overall `QUALIFIED` | Not expected (`LIMITED` or `UNRESOLVED`). Demo-scope conflict is `NEEDS_APPROVAL` |
| Replay of actual history | Admitted replay on a `QUALIFIED` dataset, fills labelled `simulated fills` | Not expected. Saved refusal is the valid result |
| Nansen: actual report through the application | Saved and reopened report; request ids; credits `KNOWN`; coverage limits stated | `NOT_RUN`. Web label fix outstanding |
| Nansen covers MOE on Monad | Actual reply for MOE | `NEEDS_FACT` (chain-level docs only) |
| Hermes model research | Actual model call through the application | `NOT_RUN` (separate packet) |
| Privy login and signer controls | Real login matrix and signer proofs | `NOT_RUN`. Uncertain policy POST and stopped 403 recorded |
| Kuru controlled action | Actual receipt on a qualified route | `NOT_RUN`. Current router source `NOT_REPRODUCIBLE` |
| Public HTTPS demo | Hosted judge journey | `NOT_RUN` |
| Video | Recorded only after the proofs above | `NOT_RUN` |
| Trading edge, profit, prize, full #58 closure | None claimed | Not claimed |

## 5. Primary documentation read (2026-10-14)

| Fact | Source | Use |
|---|---|---|
| `tgm/holders` and `tgm/flows` accept chain `monad` | Nansen API request schemas (Context7 `/websites/nansen_ai`; docs.nansen.ai Token God Mode pages) | Chain-level coverage only |
| `holders` 5 credits, `flows` 1 credit, `holders` 150 with premium labels | docs.nansen.ai credits page | Matches `NansenClient.OPERATIONS` |
| Holders returns current holders, no date range | docs.nansen.ai holders page | Snapshot-time note |
| Flows `date.to` is an inclusive cutoff; hourly snapshots for ranges up to 7 days | docs.nansen.ai flows page | One page for one day |
| Monad block time 300 ms (mean about 302 ms in September 2026); 400 ms before MIP-12 | docs.monad.xyz | Page and byte arithmetic |
| Monad finality 2 slots | docs.monad.xyz | `depth_blocks` 2 |
