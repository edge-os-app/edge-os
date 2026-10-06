# P02 compiler requirements and provenance

Status: independently authored, scoped P02 requirements. They adapt source-inspection findings to the accepted Edge OS rules. They are not copied course code, proof of course behavior, a compiler implementation, or runtime qualification.

## Portable provenance

The assigned source extract is `p02-controller-inputs@1`, SHA256 `8090a89af5b7fd89169bbbcefc4b95353e5663e9c63dc026720566a80872dab9`. Its provenance is inspected source and prior verification reports. Those claims are not fresh runtime results. Private source archives and audit files are not required to use this document or the P02 fixtures.

Source claim IDs refer to the extract's prior report. C05-C09 cover parsing, validation, and serialization. C15/C29 cover history and windows. C18-C21 cover typing and Boolean branches. C33 separates signals from complete strategies. C38-C44 cover identity, resources, and typed generation. These are selected evidence pointers. They do not mean that every source claim was reverified.

The supplied extract records the private source audit SHA256 `aced30eac6f977507eca736aeed720dfa9599670e32d5a8d089ba25be3447b60`, verification report SHA256 `71ae49d3a9fc23ac4e4b0e1f46200638460a408905fb5932d7c6fa3d8a4a8413`, and distillation SHA256 `2110382f5c1fe94fff1a41972960da8660fe74bb7dd4f31323e797b717b92365`. Referenced snapshots are QT301 S13 archive `4e9217105b44a6e9e23ed2ae58a6c069d6f030c757ce45d1fb51c4eb1ccf6893`, QT301 S15 archive `262eaff473c52b6c557c578e88657a8cffbeae0f0219d0d29b50db2a34c2f039`, and QT401 S16 archive `f7ca61ae368cb423e0f435aaaed34f9b5fd777e2507d0a44a71c07a8ee172201`. The cited S16 members are `quantlab/primitives.py` SHA256 `2b0d0c3cafc779fbc3ae9638173c7bd62a42e89e3c7c3c5b3453576a6f7b3b84` and `quantlab/gene.py` SHA256 `abd6261af4a370334e1d238b4529107de495a5e2cf648a730248a6a20966979c`. These are supplied prior-verification identities, not fresh archive checks or runtime evidence.

## Requirement and check mapping

| Requirement | Edge OS authority | Adaptation from inspected source | P02 check |
|---|---|---|---|
| Validate every input node, exact arguments, operator, units and range before evaluation | Accepted compiler section and ADR 0001 | Typed node generation does not establish rejection of caller-supplied trees (C05-C09, C18-C21, C44) | `check_contract.py` rejects a wrong unit, hidden Boolean type error, unknown operator, and 289-bucket lookback. It checks the whole tree. |
| Fresh, stored and decompressed rules use the same validator | Accepted compiler section | Parser or generator guarantees do not cover reloaded input (C05-C09) | The contract requires this. P03/P06 verify the application path. |
| Hash exact ordered meaning and pin only used semantics | Specification StrategySpec/publication section, ADR 0004 | A display string is not a canonical byte or hash protocol (C08-C09, C38-C44) | Checks cover stable reload, changed threshold hash, changed manifest hash, duplicate-key rejection, and float rejection. |
| Keep a complete rule separate from a signal | Specification StrategySpec and compiler, ADRs 0002 and 0005 | A typed signal alone lacks entry/exit, sizing and risk restrictions (C33) | The strategy fixture requires entry, exit, invalidation, sizing, costs, limits, action scope, history, and manifest. |
| Preserve scheduled time and data gaps | Accepted five-minute/history policy and calculation fixtures | Do not import compressed valid-observation time, implicit fill, or partial rolling windows (C15/C29) | `return-keeps-gap`, `rolling-requires-every-bucket`, and `SH-01`/`SH-02` cases check these rules. |
| Keep full-tree validation before Boolean simplification and retain reasons | Accepted Kleene Boolean policy | Do not let a decisive sibling erase a type/timing defect or its reason (C18-C21) | Truth-table cases, reason cases, and a hidden invalid branch check this rule. |
| Bound validation separately from generation ranges and production cost | Accepted unresolved compiler/resource work | Typed generation/sample ranges do not qualify hostile-input limits or production runtime (C38-C44) | Contract limits and rejection cases check input bounds. Runtime costs remain unmeasured. |

## Adopted behavior and limits

Use the accepted `edge-operators/1` signatures, five-minute scheduled history, no implicit fill, three-valued Boolean logic, whole-tree rejection, quote-asset volume, and 50-digit half-even decimal policy. Strategy decimals are canonical strings. The contract sets deterministic validation bounds. P06 extends and verifies the compiler operation set. P06 also measures runtime costs. The sample is synthetic. It proves neither a market edge nor deployable trading behavior.

P02 proposes spot rules bound to one Monad research pool, with a separate Kuru Flow fixed-input adapter intent whose exact deployment and route remain unqualified. It uses five-minute decisions, fixed quote sizing, one open position, no additions or partial exits, and a full exit of attributable inventory. LP actions, leverage, shorts, partial exits, scaling in, and unsupported operations remain `UNSUPPORTED`. A requested observation period stays research configuration unless an explicit adopted rule gives it separate meaning.

## Qualification boundary

P02 runs local fixtures and a standard-library checker over in-memory data. It does not run an application, database, model, or provider. P03 checks authenticated owner routing and persisted records against the app. P06 checks compiler operations, fresh and reloaded input, whole-tree rejection, numerical behavior, and resource limits. Real storage checks must establish atomic writes and cross-request idempotency. Concurrency checks must establish publication isolation and lost-acknowledgement recovery.
