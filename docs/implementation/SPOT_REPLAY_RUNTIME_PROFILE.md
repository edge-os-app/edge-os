# P13 spot replay runtime profile

P13 implements a deterministic local calculation seam in `apps/api/src/edge_os_api/spot_replay.py`. It evaluates one accepted P06 spot strategy against one immutable P07 schedule. It consumes the adopted `p12.spot-replay/1` and `p12.essential-evidence/1` terms. It does not alter P02, P06, P07 or P12.

The implementation preserves P06 truth values and reasons. It evaluates entry and exit essential bindings separately. It uses the next scheduled bucket close for a fill, requires that close to be qualified and available, and releases an unavailable fill reservation once. It uses the saved fee and slippage fractions. It retains cash, inventory, fee-inclusive basis, chronological events, metric status and reasons, and open-position marks.

The run preflight checks exact descriptor identities, explicit entry and exit bindings, non-positive scheduled-relative offsets, market and schedule identity, UTC five-minute timing, interval coverage, warm-up position, saved invalidation subset, complete-empty bucket semantics and canonical decimal observations. It rejects unsupported cost assumptions before action. It does not replace missing observations or reasons with defaults.

## Synthetic evidence

The authored WC-01 test uses invented identities, strategy values, prices, capital, fee and zero slippage. The test labels its dataset `SYNTHETIC_FIXTURE`. The literal expectations come from `tests/fixtures/spot_replay/wc01.json`, not from a captured replay result. Passing these tests checks local arithmetic and ordering only.

## Remaining runtime boundary

This feature slice does not yet store or retrieve a replay through an authenticated API. It does not prove idempotency, atomic persistence, cross-owner denial, same-database restart, UI reopening, browser accessibility, real dataset qualification or fill/cost qualification. Those checks require the P09 shared wiring lease and must be recorded in the separate shared-wiring request before any existing shared file changes.

The local focused check is:

```sh
cd apps/api
uv run --frozen pytest tests/test_spot_replay.py -q
```

This command does not complete the P13 issue acceptance criteria.
