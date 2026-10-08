# P06 compiler profile

P06 adds a versioned, deterministic compiler for the accepted price and quote-volume rule subset. Its machine contract is `docs/contracts/p06/contract.json`; worked independent literals are in `fixtures.json`, and the input/exclusion mapping is in `P06_INPUTS.md`.

The compiler accepts the P02 expression shapes and adds `relative_volume(n)`, defined as current scheduled quote volume divided by the mean of the previous `n` scheduled quote-volume buckets. It rejects unsupported operations, wrong arity, undeclared inputs, unit mismatch, malformed parameters, over-limit trees, and persisted strategies that do not match the current manifest. Both authenticated compilation and stored revision retrieval use the same P06 validator. P02 contract files and historical bytes remain unchanged.

Evaluation requires exact scheduled five-minute UTC positions and a market-binding hash. It does not align by array position, fill missing buckets, qualify a market, or adapt provider events. Missing or future observations remain UNKNOWN with reasons; a zero relative-volume baseline is UNKNOWN with `ZERO_BASELINE`. Numeric operations use 50-digit decimal arithmetic with half-even rounding. Compilation and evaluation limits are versioned in the contract.

The API round-trip tests check the public review, save, and reopen flow. Direct PostgreSQL inspection independently checks canonical stored bytes, content hash, and manifest hash. `docs/contracts/p06/check_contract.py` checks the machine form and independent worked literals. `scripts/p03/verify_run.py` adds the mapped UI-to-storage journey; its evidence records the actual run and resource cleanup.

This compiler does not provide provider normalization, complete-window certification, market or pool qualification, research-support claims, strategy search, paper execution, or a permission transition. Those remain owned by their specified later tickets.
