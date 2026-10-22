# The registered actual MOE history plus Nansen release

Status: LOCAL source registration (`MOE-HISTORY-RELEASE-L4-20261021`). This change replaces the Nansen-only
`actual-moe-nansen-demo-20261018/1` with one ACTUAL release that holds one MOE/WMON history part and one Nansen report
part. It approves no provider call, reads no credential at composition and makes no public-rights determination. The
older `NANSEN_ACTUAL_RELEASE.md` describes the superseded Nansen-only milestone.

## The one registered release

The registration adds one definition to `core/research/released_runtime_bootstrap.py` (`RELEASE_DEFINITIONS`) and its
exact SHA-256 to `core/research/operating_release.py` (`APPROVED_RELEASES`). The definition is filed under one id.

| Field | Value |
|---|---|
| `release_id` | `actual-moe-history-nansen-20261022/1` |
| `kind` | `ACTUAL` |
| `release_sha256` | `2d359daca6f9ca131ee6f90ca1efb97a6f12af4aa285104ebd062366648564c5` (canonical content, 34,787 bytes) |
| history source | `actual-moe-wmon-fwd20m/1` |
| history window | `2026-10-22T07:35:00Z` to `2026-10-22T07:55:00Z`, fixed from the run |
| scan | `from_block` `115554031`, `to_block_exclusive` `115558007` |
| Nansen token | `MOE`, `0xd8e004acba279417c04c0633cb5a21ceca207777` |
| Nansen window | `2026-10-21T07:55:00Z` to `2026-10-22T07:55:00Z` (the 24 hours ending at the history window end) |

The canonical bytes are the `release_content()` of that definition; `release_sha256` recomputes to the literal above.

## The frozen history anchor A

The history part binds one completed recorder graph. The exact handoff and provenance texts and their hashes are
code-owned inside the release definition, so a changed byte, hash or window refuses at admission. The runtime reads no
run file.

| Artifact | SHA-256 |
|---|---|
| Input `INPUT13.json` | `e2f77377f4d7e7ab2a9ddca0f5c11a3abe4108465f093e5d039b0c236fdd22e5` |
| `handoff.json` (anchor `handoff_sha256`) | `da8b5bf992471dd5fafd832a8d8473524af72cb3a3013a201d5ea3045390ebee` |
| `transport-receipts.json` (anchor `receipts_sha256`) | `f6ec0710d9dae26ad72ef3dca6f0f78062815a81c6eb96cda409881eea463332` |
| `provenance.json` (anchor `provenance_sha256`) | `fdea4dca865d2b6c1fa6599e818ea20758994d7686ddde0c845c98e3cf2ae5f2` |

Run `moe-wmon-fwd20m-actual-20261022m`: status `COMPLETED`, no stop reason, trusted clock, every bucket `DELIVERED`,
22 admitted and 22 resolved provider calls, no unknown liability, scan log count 14, recorder code SHA-256
`e02f3cac6a4500c3c9359544cb064e86671cc16074428b2a5863e51089f77395`. The recorder is not rerun and its folder is not
changed.

The release declares the run's observed delivery records:

| Bucket start (UTC) | Delivered (UTC) |
|---|---|
| `2026-10-22T07:35:00Z` | `2026-10-22T07:40:36Z` |
| `2026-10-22T07:40:00Z` | `2026-10-22T07:45:33Z` |
| `2026-10-22T07:45:00Z` | `2026-10-22T07:50:35Z` |
| `2026-10-22T07:50:00Z` | `2026-10-22T07:55:33Z` |

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

Feasibility floors are 1 triggered and 1 control for the 20-minute partition. The qualifier adds a `BASIS` reason to `SCHEDULE_FEASIBILITY` that names those floors, the counted usable slots and that they are demo floors, not statistical evidence. The floors and that reason come from the controller decisions above.

Token mechanics is `QUALIFIED_BY_OBSERVATION`. It requires the evidence SHA-256
`5ad3a7c3e11f48e6f32fe2ab9f1edf7bf968962e4854c98d16e70327cfc9e73b` (`MOE_BEHAVIOR_FINDINGS1.md`), basis
`OBSERVED_BEHAVIOR`, a 12-hour window and `source_proof` false. The qualifier shows that basis in every result that
names token mechanics and never labels it plain `QUALIFIED`.

## Providers, bounds and credentials

| Field | Value |
|---|---|
| HyperSync endpoint / slot | `https://monad.hypersync.xyz` / `HYPERSYNC_API_KEY` |
| QuickNode host / slot | `virulent-necessary-patina.monad-mainnet.quiknode.pro` / `QUICKNODE_API_URL` |
| Nansen endpoint / slot | `https://api.nansen.ai` / `NANSEN_API_KEY` |
| History limits | requests 13, compute 600 s, pages 4, rows 2000, bytes 4194304, deadline 600 s (operating packet §4.1) |
| History client bounds | deadline 120 s, connect 15 s, response 2097152 bytes, request 65536 bytes, 10000 blocks per page (operating packet §4.1) |
| Corroboration sample | 8 receipts (operating packet §4.1) |
| Feasibility floors | `required_triggered` 1 and `required_control` 1 for the 20-minute partition; demo floors, not statistical evidence. Source: controller decision `root/DECISION_B2.md` SHA256 `b3fc7e47a0121c8f510dbe3ff6ece2b7f4ae40409db475302906473179b07af8` |
| Nansen limits | requests 2, pages 1, bytes 2000000, credits `6`, 100 per page; deadline 300 s, compute 300 s |

The history transport is the accepted `StdlibHttpTransport`. The Nansen transport is the accepted network factory.
Composition reads no credential and opens no socket.

## Authority provenance

This repository note carries only the sanitized result. The private packet and run files carry the authority.

| Record | SHA-256 |
|---|---|
| Ticket packet `COMMON1.md` | `c18ed897e0bd0a1ce0833302dadb9e191afc9ba402fc777a9aa08629a64f22d3` |
| Limits source `OPERATING_PACKET.md` | `docs/qualification/actual-research-demo/OPERATING_PACKET.md` §4.1 |
| Amendment `AMEND2.md` | `f2a767b50020cad5efc867cd822e4c7592f2fb7a39ad1b755d3716373c8f71ae` |
| Floors decision `DECISION_B2.md` | `b3fc7e47a0121c8f510dbe3ff6ece2b7f4ae40409db475302906473179b07af8` |
| Floors disclosure decision `DECISION_B2_C1.md` | `72a59625de025589217e97473f8769f65fe7cb3b9fdc0ed1f72bad181b00591d` |
| Token-mechanics evidence | `5ad3a7c3e11f48e6f32fe2ab9f1edf7bf968962e4854c98d16e70327cfc9e73b` |

The builder accepted observed behavior as the token-mechanics proof on 2026-10-21. The controller ran the recorder as
operator on 2026-10-22.

## Limits and unproved scope

- This registration runs no job and grants no provider, credential, account or spending authority.
- The anchor proves payload and construction binding only. It does not authenticate a provider, prove source rights or
  promote P07.
- One 20-minute window and one Nansen 24-hour snapshot are bounded descriptions. They are not complete coverage.
- Public holder display, retention and licence rights for provider data remain unresolved.
- The saved-dataset PASS, restart, replay and the live demo remain unproved until an authorized operator run.

## The pending two-hour recorder window (RECORDER-WINDOW-L2)

Status: local recorder and checker change only. It registers no release and runs no recorder.

On 2026-10-22 the builder decided to record one 7200-second MOE/WMON forward-history window for the new attempt. This
decision replaces operating packet decision D1 for that attempt only. The existing 20-minute release
`actual-moe-history-nansen-20261022/1` and its run stay valid and unchanged.

- Window shapes are frozen: 1200 s with 4 buckets (unchanged) and 7200 s with 24 buckets. Both use 300-second buckets.
  No other window or bucket value is accepted.
- P3 may read twice per bucket, so the derived HyperSync ceiling is `1 + 2 * buckets` calls: 9 for 1200 s and 49 for
  7200 s. QuickNode stays at 17. The P4 cutoff keeps `t0 + 3600` for 1200 s and keeps the same post-window margin for
  7200 s.
- `scripts/history_payload_binding_v2.py` derives the bucket count from the window. The four-bucket ceilings and receipt
  caps stay identical, so the 20-minute anchor admits byte-for-byte.
- The scan weaker-evidence bound also follows the shape: 61 Swap logs for 1200 s (unchanged) and 366 for 7200 s. The 366
  value is the 61 bound scaled by six windows, about 4.0x the recorded 36-46 swaps per hour.
- The prepared input `PACKET/root/INPUT14.json` (`moe-wmon-fwd2h-actual-20261022a`, source
  `actual-moe-wmon-fwd2h/1`) passes every input rule with a placeholder T0 only. It is not run.

RELEASE-2H must still:

- add and approve a new release definition and SHA-256 with the run's window, scan, delivery records and limits;
- change or version the pinned four-bucket projection `scripts/history_payload_binding.py` used by saved-export
  comparison;
- update the release history limits for 24 buckets and declare the new observed delivery records;
- rerun release admission and the saved-dataset comparison on the completed two-hour artifacts.

Until then, the two-hour attempt can produce a recorder graph but cannot be registered as a release.
