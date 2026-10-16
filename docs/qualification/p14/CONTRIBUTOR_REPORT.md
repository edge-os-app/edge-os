# P14 numerical contributor report

- Branch: `quant/p14-replay-accounting`
- Checkout: `/Users/kaluarunsi_1_2/Desktop/edge-os`
- Current rebased `origin/main` base: `c4bc2a405f872ad284639a8de84712f7bc569b0f`
- Original branch-creation base: `abeedad498fc5aaf027938e099962aee41f7cee8`
- Assignment: issue #30's authorized numerical-only contributor PR scope.
- Owned changes: pure replay accounting helper, focused replay tests, and new
  P14 proposal/qualification documents only.

The host skill catalog was inspected on 2026-10-11. The repository's suggested
`quantitative-research`, `python-pro`, `python-code-style`,
`python-anti-patterns`, `codebase-design`, `karpathy-guidelines`, and
`ponytail` instructions were not available in this host catalog, so none is
claimed as used. Repository contracts, worked cases, P13 tests, Decimal 50
context, and the small-existing-module convention were applied directly.

Focused candidate checks:

```sh
(cd apps/api && uv run --frozen pytest -q \
  tests/test_proposed_replay_accounting.py \
  tests/test_proposed_replay_accounting_edges.py \
  tests/test_proposed_market_context.py \
  tests/test_spot_replay.py)
(cd apps/api && uv run --frozen python -m compileall -q src tests)
python3 docs/contracts/p02/check_contract.py
```

The focused set passes `79` tests (one upstream FastAPI/Starlette deprecation
warning); Python compilation and the P02 contract check also pass. It covers
the proposal's source-stamped multi-timeframe completion and decision-time
availability rules, fee-schedule gaps/overlaps, maker/taker and fee-asset
boundary, and spot-versus-derivative settlement metadata. See [the P14 test
matrix](TEST_MATRIX.md) and [venue-context register](VENUE_CONTEXT_BENCHMARKS.md)
for adversarial coverage and retained exclusions.

The full API suite was attempted after the rebase, but cannot complete in this
environment: its session PostgreSQL fixture fails while creating a labelled
Docker volume because the Docker daemon is unavailable. A `--maxfail=1`
reproduction confirms that root cause; it is not a P14 test failure and does
not replace complete candidate verification. `uv sync --frozen` passed.

The web locked install, typecheck and tests also passed (`230` web tests), but
the host has Node `25.5.0`, not the workflow-required Node 24; those successful
web results are supplementary rather than a compliant full-path result.
`tests/p03` installed its locked dependencies and Chromium, but the mapped P03
run was not started because its Docker preflight fails and the required pinned
Hermes checkout is absent. UI, mapped verifier, independent reviews, and gate
remain separate requirements. P12/1 saved-run behavior was not modified.

The current candidate also rejects a non-contiguous five-minute schedule before
any later fill can be applied; it does not silently bridge a missing bucket.
It also rejects an unusable venue/instrument declaration before otherwise valid
context bars can be accepted. It keeps source availability distinct from later
archival retrieval and refuses a completed bar that was not available at its
decision time.

`verify-edge-os` was read and applied as the project verification procedure.
Its feature-map and browser/SQL path are inapplicable to this intentionally
unwired numerical proposal; Docker preflight is currently blocked because the
local Docker daemon is unavailable. No P14 application-runtime claim is made.
