# Interpreter strict response format: LOCAL verification

Task `INTERPRETER-OUTPUT-CONTRACT-L1-20261015-LOCAL-v1`. Status: LOCAL source and pure checks only. No provider, key,
account, price, live registry or financial operation was used. Public documentation is not endpoint qualification.

## Responsibility

`apps/api/src/edge_os_api/research/interpreter_output_schema.py` owns the one strict `response_format` the interpreter
sends. One set of Pydantic models (strict, closed, frozen) is its only source:

- `interpretation_response_format()` returns `{"type": "json_schema", "json_schema": {"name": "edge_os_interpretation",
  "strict": true, "schema": ...}}`, a new copy on each call.
- `conforms(decoded)` validates a decoded answer against the same models with strict validation (no coercion). Tests use
  it. It decides nothing about meaning.

The schema shapes model generation. It does not accept anything. `interpretation_response.py` stays the authority for
quoted words, numbers, adoption, conflicts, field ownership, questions and whole-response rejection. Publication and
the compiler keep their semantic outcomes. The prompt, parser and release composition are unchanged.

## What the schema describes

- Top level: exactly the parser's five keys, in `TOP_LEVEL_FIELDS` order. `missing_capability` is `string | null`.
- `field_evidence` items: four closed `anyOf` branches taken from the prompt's `RESPONSE_SHAPE`: stated (`KNOWN`,
  `USER_STATED`, `source_passage`, `value`), proposed (`KNOWN`, `AGENT_PROPOSED`, `adoption: PENDING`, `value`), missing
  (`MISSING`, no other key) and conflicting (`CONFLICTING`, `conflicts`). Absent keys stay absent. There are no nullable
  extras.
- `field_name`: the model-owned P02 `CREATE_STRATEGY` fields (application-owned `restrictions`, `market`,
  `decision_interval_seconds` excluded), derived from the contract adapter.
- `value` (in items, conflict alternatives and options): string, integer, boolean, list of strings, the closed P02
  `nested_shapes` Sizing, CostAssumptions, RiskLimits and NotRequestedInvalidation, or one recursive operator node with
  one closed branch per P02 `operator_signatures` entry (`args` exactly two items).

Model generation constraints. These narrow what the model may generate, not what a stored record may hold:

1. `value` takes only the shapes above, which are the `field_shapes` and `operators` that the prompt (rule 8) already
   gives the model. Any other JSON value is outside the generation grammar. The parser alone would store it as a claim,
   and the compiler would later return `INVALID_INPUT` for it.
2. The grammar tokens `KNOWN`, `MISSING`, `CONFLICTING`, `USER_STATED`, `AGENT_PROPOSED` and `PENDING` are one-value
   enums. The authored `self-adopted-proposal` answer (`adoption: ADOPTED`) is therefore outside the grammar. The parser
   rejects it too (`proposal_must_stay_pending`).
3. JSON numbers with fractions are not representable (`integer` only), matching the P02 strict decoder.

The schema has no numeric bounds, units, thresholds, intervals, string patterns or length limits. A negative constant,
a negative lookback or an ungrounded number still conforms. The parser, publication and compiler decide those.

## Provider strict subset (documentation, 2026-10-16)

Sources: Context7 `/websites/developers_openai_api` and `/openrouterteam/docs`
(guides/features/structured-outputs). The full keyword table was not in Context7, so it was read from the primary page
`https://developers.openai.com/api/docs/guides/structured-outputs` ("Supported schemas").

- Supported types: string, number, boolean, integer, object, array, enum, anyOf. The root must be an object, not
  `anyOf`. Every object needs `additionalProperties: false` and every property in `required`. `$defs` with `$ref`
  and recursion are supported. Arrays support `minItems` and `maxItems`, except on fine-tuned models, where the page
  lists `minItems`, `maxItems`, `pattern`, `format`, `minimum`, `maximum`, `multipleOf` and `patternProperties` as
  unsupported. That exception does not change this task's model string, `openai/gpt-6.1-sol`, which is not a
  fine-tuned model, and it qualifies nothing about that model either.
- Unsupported for all models: `allOf`, `not`, `dependentRequired`, `dependentSchemas`, `if`, `then`, `else`. `const`
  is not listed as a supported keyword, so the schema uses one-value `enum`s.
- Limits: 5,000 object properties, 10 levels of object nesting, 1,000 enum values, 120,000 characters of names and
  enum values.
- OpenRouter forwards `response_format` and says that enforcement varies by provider, and that some providers translate
  the schema or treat it as a hint. `require_parameters: true` routes only to endpoints that list support.

The generated schema uses only `type`, `properties`, `required`, `additionalProperties`, `items`, `anyOf`, `enum`,
`$ref`, `$defs`, `minItems` and `maxItems`, with no titles, descriptions or defaults. A test enforces this.

Open limits:
- Whether the preferred endpoint (`openai/gpt-6.1-sol` at its routed slug) accepts this schema under `strict: true` is
  not proved.
- The 10-level nesting limit is documented for the schema. How it applies to recursive operator trees in generated
  output is not proved.
- Pydantic's schema generator is adapted only to emit one-value `enum`s and to omit titles. Validation equivalence is
  tested through the same models, not through a separate JSON Schema validator. None is installed, and none was added.

## Identity and hash recipe

Canonical bytes are what `hermes_relay_composition.bind_release` hashes:
`json.dumps(interpretation_response_format(), sort_keys=True, separators=(",", ":")).encode()`.

- Canonical bytes: 7,182. SHA256: `cdffe6fd07f14b796cae3f97268148f6ad8893100b8080e1bc652c7d3e9cbc60`. A test freezes
  both values, so any schema change changes the test.
- A later release record sets `response_format_sha256` to this value and its definition supplies the same mapping.
  `bind_release` refuses any other mapping, and `unchanged()` refuses the bound copy changed afterwards (tested).
- Serialized request estimate (concrete-thesis): system prompt 3,749 bytes, task 1,397 bytes, format 7,804 bytes
  (spaced JSON), body about 13.5 KB before routing fields. The synthetic Docker case uses `max_request_bytes` 24,000.
  The operating packet's 65,536 also holds it.

## Local recipe and measured counts

Pure, with the read-only integration interpreter, the candidate's own source first on the path, no bytecode and no
pytest cache, each run under the lane pressure guard:

```
cd apps/api
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<worktree>/apps/api/src <integration>/apps/api/.venv/bin/python -B -m pytest \
  -p no:cacheprovider --basetemp=<private tmp> -q \
  tests/test_interpreter_output_schema.py tests/test_interpretation_response.py tests/test_hermes_interpreter.py
cd ../..
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<worktree>/apps/api/src <same python> -B -m pytest -p no:cacheprovider \
  --basetemp=<private tmp> -q tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py -k "not docker"
```

Measured on the repair candidate's source (worker run; the first candidate 33573f4 measured 279 with 62 new):
- Command 1: 280 passed (63 new, 217 existing).
- Command 2: 18 passed, 4 deselected (the module's Docker cases, one of them new).

The new suite covers:
- the exact identity and copies;
- the strict subset;
- the emitted schema's grammar, against hand-written literals: the 10 model-owned field names, the four item branches and
  their state, origin and adoption tokens, the 14 P02 operators by signature, and `args` with exactly two items. A
  private worker diagnostic (not repository code) truncated or widened copies of the factory result five ways; this
  check refused all five and accepted the unchanged result;
- all 13 authored answers with a `model_response` (10 first, 3 follow-up), with the parser re-run on every accepted
  first case;
- every item state and value shape;
- 21 structural refusals;
- 9 structurally valid answers whose meaning the parser rejects or leaves to the compiler;
- binding and mutation refusal through the real `bind_release` with test-only registry injection;
- empty ordinary registries.

## Pinned-wire case (one synthetic run PASSED; endpoint not run)

`tests/hermes_provider_relay/test_pinned_hermes_actual_shape.py::test_docker_the_application_schema_and_preferred_model_go_on_the_wire_with_no_cache_marker[application-schema]`
uses the existing Docker `shaped` fixture with a SYNTHETIC test-approved record for `openai/gpt-6.1-sol`, this exact
format and `prompt_cache_options = {"mode": "explicit"}`. It checks the one counted relay send:

- exactly the bound fields plus `messages`;
- two string-content messages (`system` containing the application prompt, `user` the canonical task);
- no cache key other than the top-level `prompt_cache_options`, at any depth;
- the guard-admitted body hash;
- one reservation, settled at the token charge.

Worker result (runtime stage 1, candidate `33573f4`, which has the same schema module, wire test, job, scripts and
locks as later candidates of this repair): `1 passed` under the pressure guard. The run used the worker's own clone and
source and the receipted image `sha256:2d28b6d6...81f0` with in-image job `38be9722...`, which equals the candidate job.
It recorded a 15,245-byte body, format SHA256 `cdffe6fd...cbc60`, roles `system` and `user`, and no cache markers. This
is the worker's evidence only. Each original reviewer runs the same node on the final candidate as its own check.

Process notes kept from that run and earlier stages:
- The first image check of runtime stage 1 exited 1 (`No such image`) while the engine woke from Resource Saver. A
  later read-only check confirmed the image. This continuation is a recorded process deviation, and it does not prove
  the Resource Saver cause.
- The source1 origin import ran without the guard. The worker's skill reading was incomplete before the candidate was
  written, and most behavior tests were written after the module. Later reading does not make that order compliant.

This is synthetic serialization proof for this exact model string, transport and Hermes pin. Actual endpoint schema
acceptance, cache behavior, billing and account checks are NOT RUN. The result does not extend to another model family.
