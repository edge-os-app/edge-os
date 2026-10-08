# P06 compiler inputs and exercised mapping

Status: implementation contract for P06-NATIVE-01. The accepted Edge OS specification controls behavior. The QT301/QT401 source notes are selected reference evidence, not product rules or a course-parity claim.

## Selected sources and exclusions

- `docs/research/P02_COMPILER_REQUIREMENTS.md` supplies the selected QT301 recursive-tree, parser, primitive-registry and deterministic-evaluation lessons. Its source assessment records that QT301 S15/S16 do not fully consume text or reject every unknown name, arity and empty child.
- The controller's verified QT401 assessment is in the supplied task packet `P06_INPUTS.md`. Generation tags and parameter sampling ranges do not validate a supplied or persisted expression. No private QT archive is a required input.
- `../p02/contract.json`, `../p02/check_contract.py` and its fixtures remain byte-for-byte P02 authority. P06 adds a new version beside them; it does not rewrite the P02 contract.
- The relevant source adaptation is the accepted registry and schedule in `docs/superpowers/specs/2026-09-29-edge-os-hackathon-design.md`, not the course's retained-observation rolling, array alignment, forward fill, float tolerance, or eager mask behavior.

No code is copied from QT301 or QT401. The P06 fixture interpreter is not a general natural-language parser or a market-data adapter. It demonstrates the accepted review/save path. Real trade ordering, amount conversion, completeness, historical availability and pool qualification remain P07/data-route work.

## Versioned machine form

`p06-expression-json/1` uses the P02 expression object shapes and adds:

```json
{"op":"relative_volume","lookback_buckets":2}
```

The operation means `quote_volume[t] / mean(quote_volume[t-n .. t-1])`. Its window excludes the current bucket, includes every previous scheduled bucket, and requires the current quote volume. A zero baseline returns `UNKNOWN` with `ZERO_BASELINE`, whether current volume is zero or positive.

Constants use finite canonical decimal strings. Units are `DIMENSIONLESS`, `PRICE` (bound by the strategy's market), or `QUOTE:<quote_asset_address>`. `price()` returns quote per base; `quote_volume()` returns the declared quote asset. No implicit unit conversion is allowed. `lag`, `sum`, and `mean` preserve their numeric child's unit. `price_return` and `relative_volume` return dimensionless values.

P06 strategy revisions use `schema_version: p06.strategy/1`, `language: edge-strategy/2`, `operator_registry: edge-operators/2`, and `compiler: edge-compiler/2`. The schedule, Kleene Boolean, 50-digit half-even, and canonical JSON meanings retain the accepted P02 component versions. The semantic manifest hash and strategy content hash are stored with each immutable revision. P02 revision bytes and hashes still validate under `../p02/check_contract.py`.

Evaluation observations carry an exact scheduled bucket end and a hash of their network, quote unit and research binding. The schedule must be ordered, unique, five-minute UTC positions. An observation with another bucket or binding is UNKNOWN/rejected; evaluation never aligns by array position alone. A value is usable only when qualified, available by the decision time and finite. A price endpoint must be positive. Missing history never shrinks or fills a window.

## Limits

P06 preserves the accepted 64 KiB strategy input, 2,048 nodes per expression, depth 64, 288 lookback buckets and 256 manifest-entry limits. Evaluation also stops after 1,000,000 deterministic work steps. A step counts a visited expression node or scheduled input observation. The evaluator raises `evaluation_limit` before exceeding that count. These limits apply to this compiler version only.

The worker result records the exact high-cost accepted fixture and its evaluation-step count, host, elapsed time and process peak RSS. The numeric ceilings are deterministic rejection limits; elapsed time and RSS are measured observations, not hardware-independent promises.

## T01–T36 mapping

Each row names the implemented case in `apps/api/tests/test_p06_compiler.py` or `test_p06_api.py`; P02's frozen contract checker remains an additional regression. A stated exclusion is outside P06's compiler boundary.

| Requirement | P06 coverage |
|---|---|
| T01 | `test_canonical_rule_and_manifest_changes_produce_new_identities`; API round-trip keeps exact operand tree. |
| T02 | `read_json` rejects duplicate keys, floats and trailing JSON through the existing P03 boundary; fresh and saved malformed-tree rejection is compared in `test_fresh_and_saved_invalid_rule_have_the_same_compile_rejection`. |
| T03 | `test_decisive_boolean_sibling_cannot_hide_unknown_operator` and `test_bad_arity_alias_unit_and_boolean_coercion_reject_at_compile` visit the full tree and reject malformed arity before evaluation; P02 checker regressions remain additional coverage. |
| T04 | P06 accepts only the declared `args`, `value`, and bucket fields; aliases/macros are unsupported. |
| T05 | Canonical decimal validation, positive lookback checks, and `test_lookback_limit_accepts_288_and_rejects_289_independently`. |
| T06 | Canonical content identity changes when an operand value changes; arrays preserve operand order. |
| T07 | `test_relative_volume_is_a_versioned_typed_strategy_and_binds_quote_asset` and `test_canonical_rule_and_manifest_changes_produce_new_identities`. Dataset identity is evaluation data, not a strategy rewrite. |
| T08 | `test_strategy_byte_limit_accepts_exact_boundary_and_rejects_one_over` and `test_expression_node_and_depth_limits_have_independent_edges`; runtime step limit is tested separately. |
| T09 | `test_unqualified_input_is_unknown_with_its_reason`, missing-position tests and future-time test. No forward fill. |
| T10 | `test_market_binding_mismatch_rejects_before_evaluation` and `test_timestamp_mismatch_is_unknown_and_does_not_align_by_array_position`. Raw provider duplicate resolution is excluded to P07. |
| T11 | `test_price_return_keeps_intermediate_gap_while_using_qualified_endpoints`, complete rolling test, and nested-history test. |
| T12–T14 | Typed checks traverse both operands; exact nine-pair table and missing-reason preservation are in `test_kleene_boolean_table_and_reason_preservation`; hidden unsupported child rejection is tested. |
| T15–T16 | Excluded registry operations (percentile, selector and z-score) return `unsupported_operator`; no operation is compiled. |
| T17 | Non-finite and invalid numeric market values become reasoned UNKNOWN; relative-volume zero baseline is tested for current zero and positive values. |
| T18–T19 | `price_return` endpoints and nested dependency history are tested. Gross/log macros, generated code and dispatcher parity are excluded. |
| T20 | OBV is outside the P06 registry and is rejected as unsupported. |
| T21 | `sum`/`mean` window includes current; `test_rolling_mean_does_not_shrink_around_missing_scheduled_position` covers missing values. Product is unsupported. |
| T22 | `test_relative_volume_and_nested_windows_have_exact_history_offsets` covers nested history. |
| T23 | Hand-worked literals cover 100→110 return = 0.1 and volumes 4,8,20 => 20 / mean(4,8) = 10/3 at 50-digit precision. |
| T24 | Future observations are UNKNOWN and strategy execution permission remains NOT_GRANTED in API review/save test. |
| T25 | Tree/depth/evaluation limits are exercised. External-I/O operators are rejected before evaluation. |
| T26 | Unsupported indicator is shown with `/field_evidence/entry`; quote unit and binding mismatches reject. Source qualification itself is excluded. |
| T27 | `test_user_can_review_save_and_reopen_a_price_volume_rule` verifies adopted parameters, timing, manifest and exact stored content. |
| T28–T29 | No new language model or inference stage is added. Required missing fields remain P02 clarification behavior. |
| T30 | Unsupported indicator and unsupported registry names are rejected with the affected rule field. |
| T31 | Changed strategy bytes change content identity; a registry/compiler semantic version change changes manifest identity. |
| T32 | Supported nested windows use complete scheduled indices; slow multi-input course rollings are excluded. |
| T33 | Fresh and persisted trees use `p06.validate_strategy`; the API test compares the same path/detail for a fresh bad rule and a malformed saved draft. |
| T34 | There is no search/mutation. A changed rule is a distinct canonical content identity and passes whole-tree validation. |
| T35 | Fresh and saved malformed trees are checked before publication; P02-looking syntax cannot bypass the P06 manifest/version checks. |
| T36 | Parser, expansion and evaluation have bounded inputs; no macros or cycles are accepted. |

## Research-contract fixture mapping

The exact numeric examples below use independent literals and run in the named tests. Fixture families that require raw event ingestion, data providers, research claims or execution are explicit exclusions.

| Fixture | P06 disposition |
|---|---|
| TL-01 | The fixture proposal and saved rule pass the same P06 validator. A manual expression editor is not part of this journey. |
| TL-02 | Fresh and stored rule rejection is tested; registry, arity, units and parameter bounds share `p06.validate_strategy`. |
| SH-01 | Executed: 100, missing, 110 across two scheduled intervals returns exactly 0.1 and retains the intermediate gap. |
| SH-02 | Executed: three-value complete rolling mean with a missing middle position returns UNKNOWN. |
| SH-03 | Executed: a future endpoint is UNKNOWN; the earlier schedule cannot substitute. |
| SH-04 | Executed through separate return, window and nested warm-up assertions; positions remain scheduled. |
| BL-01 | Executed: all nine AND/OR pairs. NOT preserves UNKNOWN in evaluator code; API cases exercise Boolean roots. |
| BL-02 | Executed: determinate sibling output retains missing-price/volume reason. No readiness is inferred from truth. |
| BL-03 | Executed: unsupported child stays invalid under a decisive sibling. No simplifier exists. |
| BL-04 | Executed in the full truth table and `not` evaluation path. |
| CC-01–05 | Excluded: bucket construction, event ordering, aggregation and complete-empty classification belong to P07 source adapters. P06 requires already scheduled qualified observations. |
| CC-06 | Existing P03 API flow exercises explicit proposed-setting adoption; P06 does not change adoption records. |
| CC-07 | Excluded: parameter search and experiment ledgers are outside P06. |
| CC-08 | Executed for decimal rule values and 50-significant-digit relative-volume arithmetic. Raw token amounts/decimals are P07 source-adapter work. |
| CC-09 | Executed: strict `gt` and inclusive `gte` differ at the exact threshold; changing content/manifest changes identity. |
| OB-01 | Executed: explicit price/quote units, finite decimal literals and unit rejection. |
| OB-02 | Executed for scheduled lag history, missing observations and no Boolean coercion in validator. |
| OB-03 | Executed for current-inclusive sum/mean, endpoint returns, previous-only relative-volume baseline, nested history and gaps. |
| OB-04 | Excluded: raw trade quote legs, deduplication and conflicting trade IDs are P07. |
| OB-05 | Executed: qualified empty quote-volume value is zero; incomplete/missing input is UNKNOWN; both zero-baseline cases are UNKNOWN/ZERO_BASELINE. |
| OB-06–08 | Excluded: pool identity qualification, Envio/QuickNode agreement, data coverage and sample feasibility belong to P07/research. P06 binds each evaluation to the exact supplied market identity. |
| OB-09–10 | P06 records no support/readiness transition and no permission. API round trip verifies NOT_GRANTED; effect, paper and operational gates belong to their owning tickets. |

The P06 package check validates its machine contract and case index. `apps/api/tests/test_p06_compiler.py`, `test_p06_api.py`, the frozen P02 contract checker, and the mapped P03 path are the executable evidence. A listed exclusion is not a passed provider or market test.
