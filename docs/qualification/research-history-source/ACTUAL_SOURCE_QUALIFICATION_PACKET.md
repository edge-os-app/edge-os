# Actual-source qualification packet for the application journey (proposal)

Status: **PROPOSED, not approved**. Milestone `RELEASE-E2E-L2-20261012-SOURCE-LOCAL` (#58). Nothing here ran against a provider. No credential was read and no account was queried. RG02/RG05 actual-data evidence is NOT_RUN. This packet complements the P07 `docs/qualification/research-history/COLLECTION_PACKET.md`, which owns the source, pool and window proposal. This packet adds what the application journey needs to run an actual collection through the code that SOURCE-LOCAL connected. Values marked *proposed* or *unresolved* need a builder or controller decision.

## 1. What already runs locally (SOURCE-LOCAL)

The investigation worker calls the accepted P07 seams with offline recorded clients:

- `EnvioHypersyncSource` → `collect`;
- `read_chain_id` → `corroborate_records`;
- `normalize`.

It saves the transport provenance with the dataset, settles measured client calls against the job reservation, and drives the saved dataset through report, market adoption, publication and labelled replay. See `docs/implementation/USER_RELEASE_INTEGRATION_PROFILE.md`, section "SOURCE-LOCAL".

An actual run replaces only the two recorded clients with actual clients behind the same protocols:

- `EnvioQueryClient.query(request)`;
- `QuickNodeRpcClient.call(method, params)`.

They plug into the existing guard wrappers `GuardedEnvioClient` and `GuardedQuickNodeClient`. These check cancellation, the deadline and the request budget before every call, count only made calls and never retry. A refusal during receipt corroboration stops the whole corroboration (`STOPPED_<reason>`, with `receipts_fetched`); it is never recorded as RPC failures. An actual client must be wrapped the same way; it cannot replace the wrapper.

## 2. Supported source, network, pool and window

| Item | Value | Status |
|---|---|---|
| Network / chain | Monad mainnet, chain id 143 | from P07 packet |
| History source | Envio HyperSync `https://monad.hypersync.xyz`, provider version label `envio-hypersync/1` | from P07 packet; live response shape unverified |
| Corroboration | QuickNode Monad JSON-RPC: `eth_chainId` once, `eth_getTransactionReceipt` per sample | from P07 packet |
| Pool | nad.fun MOE/WMON `0x97199b34564911936bc850ac45ede785892b5aad` | proposed (P07 packet) |
| Orientation (QUOTE/BASE) | WMON as quote | *unresolved*: builder decision |
| Window | 2026-09-25T00:00Z to 2026-09-27T00:00Z, avoiding the sealed Probe A holdout | proposed (P07 packet) |
| Availability model | `ASSUMED_DELAY` 180 s (delivery not observed) | *unresolved*: builder decision; the local recordings use `OBSERVED_DELIVERY` |
| Decimals, pool tokens, fee semantics, finality | must come from reads; P07 has no `eth_call` reader | *unresolved*: needs a reader or a recorded-declaration decision; the local journey labels them `RECORDED_DECLARATION` |

## 3. Access and coverage assumptions

- **Access:** the Envio token and QuickNode key exist only inside the injected clients, host-side. They never appear in the dataset, logs, evidence, a model input or the repository. Paid access, rights to store raw data and plan limits are *unverified*.
- **Coverage:** the pages must tile the scan (`covers_requested_scan`). A provider `complete` flag alone is not coverage. The expected verdict is `LIMITED`: corroboration is a sample, and P07 needs complete corroboration for `QUALIFIED`. A LIMITED dataset stays unbound and cannot supply a market (`dataset_not_qualified`), so RG05 replay on actual data stays blocked unless the builder accepts a LIMITED representation contract. That representation decision is *unresolved*; P02 has no limited binding state.

## 4. Exact proposed request, usage and time limits

| Bound | Proposed value | Enforced by |
|---|---|---|
| `max_pages` | 16 | job declaration (`HistoryResourceBounds` ≤ 64) and collector |
| `max_rows` / `max_bytes` | 10,000 / 4,194,304 | declaration and collector |
| Corroboration sample | 8 receipts | source catalog entry |
| `provider_requests` (job reservation) | 25 = 16 pages + 1 chain read + 8 receipts | adoption check `resource_bounds_too_small`; `RequestBudget` |
| `compute_seconds` / `deadline_seconds` | 600 / 600 | job reservation; G-N1 correction (`docs/qualification/public-runtime/RUNTIME_GUARDS.md`) |
| Pacing | ≤ 10 HyperSync requests per minute | *not implemented*: must live in the actual client |
| Spend above existing plans | USD 0.00; stop on any quota message | *not enforceable by the application*; provider-side caps unverified |

## 5. Original attempt, retry, stop and cleanup rules (already implemented)

- **One attempt per job:**
  - The job reserves owner and global capacity before any client call.
  - It saves `ATTEMPT_STARTED` before the first call.
  - It is never collected again after a stop: a restart reconciles to `OUTCOME_UNKNOWN` with unknown liability.
- **No retry:** a failed call counts as usage and is not retried. A new job needs a new reservation.
- **Stops:** cancellation, the deadline and the request budget are checked before every call. A refused call is never made.
- **Settlement:** measured client calls settle inside the reservation (`MEASURED_CLIENT_CALLS`). Over the reservation is `INVALID` and stays liability.
- **Cleanup:** the clients hold no files or sockets in the local journey. An actual client must close its connections, and the P05 callback-bound cleanup amendment applies. No zero-overrun promise is made.

## 6. Proof plan for the approved run (all NOT_RUN)

1. The builder approves the bounds above, the orientation and the availability model, and supplies the clients' credentials host-side.
2. Run one job through the mounted application: a declaration with the approved bounds, then a worker pass.
3. Independently recompute the page content hashes and `dataset_revision` from the retained pages. Check `covers_requested_scan`, the gaps, the corroboration entries and the measured calls against provider-side request logs, where available.
4. Save and reopen the report, the dataset and, if QUALIFIED or an approved LIMITED contract exists, the replay. Restart and reopen.
5. Inspect SQL, displayed limits and logs (no credential).
6. Record the verdict as observed: a LIMITED or UNRESOLVED outcome is a valid result, and no favorable result is required.
