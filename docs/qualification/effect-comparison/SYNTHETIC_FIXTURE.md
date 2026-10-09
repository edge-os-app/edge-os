# Synthetic effect-comparison fixture

Fixture: `synthetic-effect-comparison/1`, authored at `apps/api/tests/fixtures/effect_comparison/synthetic_effect_comparison_v1.json`.

This fixture is qualified for deterministic logic checks only. It contains two five-minute feature buckets and four synthetic raw trade references. It is not observed market history and cannot qualify a real study or data source. The fixture is static; the API freezes and checks its exact file hash before an evaluation attempt.

The expected cases are:

- four decision opportunities per evaluation use the explicit 300-second decision clock while feature data remains on five-minute buckets;
- the first P08 evaluation's authored P06 price and volume conditions can form a trigger;
- the second evaluation can hold the same price condition TRUE and set a separately authored volume condition FALSE;
- the two exact 15-minute response references are +10% and -10%;
- missing, future, unknown, and unqualified evidence is never relabeled as a qualified control;
- all results remain descriptive and statistically unresolved.

No hidden real-data, source-coverage, wallet, provider, execution-route, fill, or statistical qualification is represented. Real-data mode remains unavailable until P07 history and the relevant source/qualification inputs are independently accepted.
