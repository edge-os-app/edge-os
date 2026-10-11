# P14 numerical contributor report

- Branch: `quant/p14-replay-accounting`
- Checkout: `/Users/kaluarunsi_1_2/Desktop/edge-os`
- Starting `origin/main` commit: `abeedad498fc5aaf027938e099962aee41f7cee8`
- Assignment: issue #30's authorized numerical-only contributor PR scope.
- Owned changes: pure replay accounting helper, focused replay tests, and new
  P14 proposal/qualification documents only.

The host skill catalog was inspected on 2026-10-11. The repository's suggested
`quantitative-research`, `python-pro`, `python-code-style`,
`python-anti-patterns`, `codebase-design`, `karpathy-guidelines`, and
`ponytail` instructions were not available in this host catalog, so none is
claimed as used. Repository contracts, worked cases, P13 tests, Decimal 50
context, and the small-existing-module convention were applied directly.

Focused baseline and candidate check:

```sh
(cd apps/api && uv run --frozen pytest -q \
  tests/test_proposed_replay_accounting.py tests/test_spot_replay.py)
```

The candidate passes `69` focused numerical/P12 tests (one upstream
FastAPI/Starlette deprecation warning). See [the P14 test matrix](TEST_MATRIX.md)
for the adversarial coverage and retained exclusions. The complete API suite was
also attempted: its pure tests reached
125 passes, but Docker could not create the isolated PostgreSQL volume, leaving
13 harness failures and 255 dependent setup errors. That environment blocker is
outside this pure numerical change; it does not replace the required complete
candidate verification. UI, mapped verifier, independent reviews, and gate
remain separate requirements. P12/1 saved-run behavior was not modified.

`verify-edge-os` was read and applied as the project verification procedure.
Its feature-map and browser/SQL path are inapplicable to this intentionally
unwired numerical proposal; Docker preflight is currently blocked because the
local Docker daemon is unavailable. No P14 application-runtime claim is made.
