# The registered actual MOE history plus Nansen release

Status: LOCAL source registration (`RELEASE-2H-L2-20261022`). This change replaces the twenty-minute release
`actual-moe-history-nansen-20261022/1` with one ACTUAL release that holds one two-hour MOE/WMON history part and one
Nansen report part. It approves no provider call, reads no credential at composition and makes no public-rights
determination. The older `NANSEN_ACTUAL_RELEASE.md` describes the superseded Nansen-only milestone.

## The one registered release

The registration adds one definition to `core/research/released_runtime_bootstrap.py` (`RELEASE_DEFINITIONS`) and its
exact SHA-256 to `core/research/operating_release.py` (`APPROVED_RELEASES`). The definition is filed under one id. The
twenty-minute id is removed in the same change.

| Field | Value |
|---|---|
| `release_id` | `actual-moe-history2h-nansen-20261022/1` |
| `kind` | `ACTUAL` |
| `release_sha256` | `45c8cfbf5d61eb519ee3140e02e50b2b7091669dc28cbef224bdc6a0e77ca877` (canonical content, 74,018 bytes) |
| history source | `actual-moe-wmon-fwd2h/1` |
| history window | `2026-10-22T21:40:00Z` to `2026-10-22T23:40:00Z`, fixed from the run |
| scan | `from_block` `115721086`, `to_block_exclusive` `115744931` |
| Nansen token | `MOE`, `0xd8e004acba279417c04c0633cb5a21ceca207777` |
| Nansen window | `2026-10-21T23:40:00Z` to `2026-10-22T23:40:00Z` (the 24 hours ending at the history window end) |

The canonical bytes are the `release_content()` of that definition; `release_sha256` recomputes to the literal above.

## The frozen history anchor A

The history part binds one completed recorder graph. The exact handoff and provenance texts and their hashes are
code-owned inside the release definition, so a changed byte, hash or window refuses at admission. The runtime reads no
run file.

| Artifact | SHA-256 |
|---|---|
| Input `INPUT14_RUN.json` | `3fd63967cb65bc8f028b52d8e34b7dd8769165fc18a43d187a7a23ce0a08abdf` |
| `handoff.json` (anchor `handoff_sha256`) | `b309d2ffacb0455bf99798535398886281076347c30b7ca9b20a78ef622eab88` |
| `transport-receipts.json` (anchor `receipts_sha256`) | `26f4336543285945a93cfa59aa614fb2d9ba58111182bca6d55d3e3bf40e35c3` |
| `provenance.json` (anchor `provenance_sha256`) | `54b731bfe4a1b343d5df0b63b0646a0bc033992e39c2b54f60171428802a4578` |

Run `moe-wmon-fwd2h-actual-20261022a`: status `COMPLETED`, no stop reason, trusted clock, every bucket `DELIVERED`,
42 admitted and 42 resolved provider calls (25 HyperSync and 17 QuickNode), no unknown liability, scan log count 90,
recorder code SHA-256 `d312a52948d50b4ed92b398beffacc8d64741117f4310134ddcacea8165f2072`. The recorder is not rerun
and its folder is not changed. `check_artifacts` admits the graph before registration.

The release declares the run's observed delivery records:

| Bucket start (UTC) | Delivered (UTC) |
|---|---|
| `2026-10-22T21:40:00Z` | `2026-10-22T21:45:32Z` |
| `2026-10-22T21:45:00Z` | `2026-10-22T21:50:32Z` |
| `2026-10-22T21:50:00Z` | `2026-10-22T21:55:32Z` |
| `2026-10-22T21:55:00Z` | `2026-10-22T22:00:32Z` |
| `2026-10-22T22:00:00Z` | `2026-10-22T22:05:32Z` |
| `2026-10-22T22:05:00Z` | `2026-10-22T22:10:32Z` |
| `2026-10-22T22:10:00Z` | `2026-10-22T22:15:32Z` |
| `2026-10-22T22:15:00Z` | `2026-10-22T22:20:32Z` |
| `2026-10-22T22:20:00Z` | `2026-10-22T22:25:32Z` |
| `2026-10-22T22:25:00Z` | `2026-10-22T22:30:32Z` |
| `2026-10-22T22:30:00Z` | `2026-10-22T22:35:32Z` |
| `2026-10-22T22:35:00Z` | `2026-10-22T22:40:32Z` |
| `2026-10-22T22:40:00Z` | `2026-10-22T22:45:32Z` |
| `2026-10-22T22:45:00Z` | `2026-10-22T22:50:32Z` |
| `2026-10-22T22:50:00Z` | `2026-10-22T22:55:32Z` |
| `2026-10-22T22:55:00Z` | `2026-10-22T23:00:32Z` |
| `2026-10-22T23:00:00Z` | `2026-10-22T23:05:32Z` |
| `2026-10-22T23:05:00Z` | `2026-10-22T23:10:32Z` |
| `2026-10-22T23:10:00Z` | `2026-10-22T23:15:37Z` |
| `2026-10-22T23:15:00Z` | `2026-10-22T23:20:32Z` |
| `2026-10-22T23:20:00Z` | `2026-10-22T23:25:33Z` |
| `2026-10-22T23:25:00Z` | `2026-10-22T23:30:34Z` |
| `2026-10-22T23:30:00Z` | `2026-10-22T23:35:33Z` |
| `2026-10-22T23:35:00Z` | `2026-10-22T23:40:33Z` |

The availability model is `OBSERVED_DELIVERY` with basis `SOURCE_DELIVERY_RECORD`. The saved bucket availability times
therefore reproduce the anchored graph, as the payload checker requires.

## Market and token facts

| Field | Value |
|---|---|
| Pool | `0x97199b34564911936bc850ac45ede785892b5aad`, Uniswap-V2-compatible |
| Factory | `0xa25b13127e63ddae6d0b35570ff3d39dbd621001` |
| token0 (QUOTE) | WMON `0x3bd359c1119da7da1d913d1c4d2b7c461115433a`, 18 decimals |
| token1 (BASE) | MOE `0xd8e004acba279417c04c0633cb5a21ceca207777`, 18 decimals |
| V2 `Swap` topic0 | `0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822` |
| P6 source lookup | MonadVision with Sourcify, `https://sourcify-api-monad.blockvision.org/`; MOE source `NOT_VERIFIED` |
| Collected at | `2026-10-22T23:42:12Z`, archive height `115745034` |

Feasibility floors are 1 triggered and 1 control for the declared partition. The qualifier adds a `BASIS` reason to
`SCHEDULE_FEASIBILITY` that names those floors, the counted usable slots and that they are demo floors, not statistical
evidence. The floors and that reason come from the controller decisions recorded for the twenty-minute release and
apply unchanged to the two-hour partition.

Token mechanics is `QUALIFIED_BY_OBSERVATION`. It requires the evidence SHA-256
`5ad3a7c3e11f48e6f32fe2ab9f1edf7bf968962e4854c98d16e70327cfc9e73b` (`MOE_BEHAVIOR_FINDINGS1.md`), basis
`OBSERVED_BEHAVIOR`, a 12-hour window and `source_proof` false. The qualifier shows that basis in every result that
names token mechanics and never labels it plain `QUALIFIED`.

## The page plan for the two-hour window

The page derives partitions and the decision schedule from the source window (`apps/web/lib/history-declaration.ts`).
For this 24-bucket window the existing rule gives TRAINING 12 buckets, VALIDATION 6 and HOLDOUT 6. Comparison reads
only TRAINING, so a predictive declaration with lookback 8 keeps 2 usable decisions; lookback 9 refuses with a clear
maximum. A DESCRIPTIVE declaration reads the whole window and has 22 usable decisions at lookback 1. No server rule
changed.

## Providers, bounds and credentials

| Field | Value |
|---|---|
| HyperSync endpoint / slot | `https://monad.hypersync.xyz` / `HYPERSYNC_API_KEY` |
| QuickNode host / slot | `virulent-necessary-patina.monad-mainnet.quiknode.pro` / `QUICKNODE_API_URL` |
| Nansen endpoint / slot | `https://api.nansen.ai` / `NANSEN_API_KEY` |
| History limits | requests 14, compute 600 s, pages 5, rows 2000, bytes 4194304, deadline 600 s |
| History client bounds | deadline 120 s, connect 15 s, response 2097152 bytes, request 65536 bytes, 10000 blocks per page |
| Corroboration sample | 8 receipts |
| Feasibility floors | `required_triggered` 1 and `required_control` 1 for the declared partition; demo floors, not statistical evidence. Source: controller decision `root/DECISION_B2.md` SHA256 `b3fc7e47a0121c8f510dbe3ff6ece2b7f4ae40409db475302906473179b07af8` |
| Nansen limits | requests 2, pages 1, bytes 2000000, credits `6`, 100 per page; deadline 300 s, compute 300 s |

The two-hour scan is 23,845 blocks. At 10,000 blocks per page it needs 3 pages; 5 pages keep 2 spare pages for an early
HyperSync page end. Fourteen requests cover 5 pages, 1 `eth_chainId` and 8 receipts. Fourteen history requests plus
2 Nansen requests equal the default owner cap of 16; 600 history compute seconds plus 300 Nansen seconds equal the
default 900. The page limit and request ceiling stay below the `HistoryResourceBounds` maxima, and `max_pages` stays
at or below `provider_requests`.

The history transport is the accepted `StdlibHttpTransport`. The Nansen transport is the accepted network factory.
Composition reads no credential and opens no socket.

## Authority provenance

This repository note carries only the sanitized result. The private packet and run files carry the authority.

| Record | SHA-256 |
|---|---|
| Ticket packet `COMMON1.md` | `8919e94a1a4501a7dc1bf306ec8ebe08c8fda9597924154104228fc062f45649` |
| Run completion `RUN_DONE.md` | `28fec7afafbd07cf0c049168a773ea644844d5686fd50bd7929fb40213a2f724` |
| Limits source `OPERATING_PACKET.md` | `docs/qualification/actual-research-demo/OPERATING_PACKET.md` §4.1 |
| Floors decision `DECISION_B2.md` | `b3fc7e47a0121c8f510dbe3ff6ece2b7f4ae40409db475302906473179b07af8` |
| Floors disclosure decision `DECISION_B2_C1.md` | `72a59625de025589217e97473f8769f65fe7cb3b9fdc0ed1f72bad181b00591d` |
| Token-mechanics evidence | `5ad3a7c3e11f48e6f32fe2ab9f1edf7bf968962e4854c98d16e70327cfc9e73b` |
| Checker projection `/1` | `813cc91fd10d16222cdc4622071406bc9bb614f0efdaf74c3ab51ab2bf13acaa` |
| Checker `/2` | `24a4948f83c235339ecf301ac8cc21eee5f02b89e69b024c24244f22b45a6cd9` |

The builder accepted observed behavior as the token-mechanics proof on 2026-10-21. The controller ran the recorder as
operator on 2026-10-22.

## Offline engine check on the anchored run

The run's 24 P3 bodies were replayed through the accepted collector and P07 normalizer (90 records, 5 pages, all 24
buckets `COMPLETE_OCCUPIED`, 90 qualified trades). No network, credential or database was used. This is a check of the
anchored data, not a provider-authenticated collection.

| Check | Result |
|---|---|
| P07 overall | `UNRESOLVED` |
| `HISTORY_COMPLETENESS_AND_ORDER` | `UNRESOLVED`, `NO_CORROBORATION` (the recorder made no swap-receipt sample) |
| `BINDING_IDENTITY` | `LIMITED`, `POOL_TOKENS_SINGLE_READ` and `POOL_VENUE_SINGLE_SOURCE` |
| `EVENT_AND_AMOUNT_MEANING` | `QUALIFIED` by observation |
| `POINT_IN_TIME_AVAILABILITY` | `QUALIFIED` |
| `SCHEDULE_FEASIBILITY` | `QUALIFIED`, declared floors, 22 of 24 usable slots |

The real engine returns `LIMITED_DATA` for a declaration on this dataset because the verdict is not `QUALIFIED`.

With the P07 gate bypassed on the same data, every decision is `FUTURE_INPUT_AVAILABILITY`: a decision at a bucket
boundary uses that bucket, but the observed delivery time is about 32 s after the bucket end. No decision is usable.
The page plan's counts (lookback 1, 2, 3 and 8) are 9, 8, 7 and 2 decisions, but the engine cannot use them.

A sensitivity check that treats each bucket as available at its end (the `SCHEDULE_FEASIBILITY` model) gives:

| Lookback | Decisions | Triggered opportunities | Control opportunities | Observed triggered | Observed control | Outcome |
|---|---|---|---|---|---|---|
| 1 | 9 | 2 | 7 | 0 | 1 | `INSUFFICIENT_DATA` |
| 2 | 8 | 2 | 6 | 0 | 1 | `INSUFFICIENT_DATA` |
| 3 | 7 | 2 | 5 | 0 | 0 | `INSUFFICIENT_DATA` |
| 8 | 2 | 0 | 2 | 0 | 0 | `INSUFFICIENT_DATA` |

The missing outcome references are sparse trades in the one-minute response window, not missing buckets. This run
therefore supports the release binding but does not give a predictive outcome under the current page plan. A schedule
offset, a denser window or a different outcome reference is a separate builder decision. No result is chosen here.
These are the release's known limits.

## Limits and unproved scope

- This registration runs no job and grants no provider, credential, account or spending authority.
- The anchor proves payload and construction binding only. It does not authenticate a provider, prove source rights or
  promote P07.
- One two-hour window and one Nansen 24-hour snapshot are bounded descriptions. They are not complete coverage.
- Public holder display, retention and licence rights for provider data remain unresolved.
- The saved-dataset PASS, restart, replay and the live demo remain unproved until an authorized operator run.

## The two-hour release path preparation (RELEASE-2H phase 1)

Status: local checker change only. It registered no release and ran no recorder.

The release path accepts a 7200 s / 24-bucket anchor:

- `scripts/history_payload_binding.py` takes the accepted shape's bucket count at its bucket check. The `/1` default
  stays 4; the `/2` checker passes 4 for 1200 s and 24 for 7200 s after it validates the window shape.
- Synthetic tests cover a complete 24-bucket `/2` anchor: ACTUAL admission, one approved release, 24 saved buckets in the
  comparison report, a changed bucket or artifact byte refused, and a wrong window refused. The fixture is the
  recorder's own SYNTHETIC 7200 s graph and is never registered as a release.

## D1 disclosure for the checker change

The `/1` and `/2` checker byte hashes changed. A saved dataset whose binding froze the old identities returns
INCOMPLETE `CHECKER_IDENTITY_DIFFERS` and must be collected again after this change ships. The new release admits the
anchored two-hour graph; the removed twenty-minute release and its saved datasets are not reused.
`%0` should plan the recollection with the deploy.
