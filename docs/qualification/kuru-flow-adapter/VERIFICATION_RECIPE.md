# Owned offline verification recipe and feature-map proposal

Deliverable 7. Prepared 2026-10-11. This is a proposal only. It changes no shared verifier or shared feature-map file.

## Owned executable checks

Run from `apps/api`:

```sh
uv run --frozen pytest tests/kuru_flow -ra
```

Expected literal: `75 passed` (the count rises only with new owned tests). The suite opens no provider socket and requests no shared `pg` fixture, so no shared session fixture starts an instance for this suite.

Static guards inside the suite:

- `test_package_imports_no_network_or_provider_module` - the package imports no `socket`, `ssl`, `http`, `httpx`, `requests`, `urllib`, `aiohttp`, `websockets`, `web3`, `eth_*` or `subprocess`.
- `test_no_sha3_substitution_for_ethereum_keccak` - no package file contains `sha3_`, `keccak_256` or `keccak256`; a `Keccak` note exists.
- `test_application_composition_does_not_reference_the_package` - no application module outside the package imports it.
- `test_candidate_is_frozen_and_immutable` - the candidate and its nested intent and fees reject mutation.
- `test_fixture_manifest_is_intact` - every fixture's canonical SHA-256 matches `fixtures.json`.

From the repository root:

```sh
python3 -B -m compileall -q apps/api/src/edge_os_api/kuru_flow apps/api/tests/kuru_flow
git diff --check 9210bc1d054f1d5623693f787737a7b80563185a HEAD
```

## Fixture identities

| Item | Identity |
|---|---|
| Fixtures schema | `p20-kuru-flow-adapter/1` |
| Fixtures file | `apps/api/tests/kuru_flow/fixtures.json` |
| Fixtures file SHA256 | `5cf658ef759075f02b66cc834d05c103ee88e5dc1ed386abe82914410b5058f8` |
| Labels | `AUTHORED` only; no `DOCUMENTATION`, no `RECORDED` |
| Result vocabulary | `ACCEPTED`, `BLOCKED`, `UNKNOWN`; observation states `CONFIRMED`/`REVERTED`/`PENDING`/`SUBMISSION_UNKNOWN`/`ACKNOWLEDGEMENT_LOST`/`TIMEOUT`/`REJECTED` |

## Failure checks (expected literals)

| Mutation | Expected |
|---|---|
| Wrong selector | `SELECTOR_NOT_ALLOWED` |
| Wrong `to` | `ENTRYPOINT_NOT_ALLOWED` |
| Wrong input raw | `INPUT_NOT_APPROVED` |
| Minimum above quote | `MIN_OUTPUT_INVALID` |
| Wrong program bytes | `PROGRAM_NOT_APPROVED` |
| Fee total above 10000 | `FEE_BOUND_EXCEEDED` |
| Native value below input | `NATIVE_VALUE_INSUFFICIENT` |
| ERC-20 value not zero | `ERC20_VALUE_NOT_ZERO` |
| ERC-20 allowance absent | `ALLOWANCE_UNKNOWN` |
| ERC-20 allowance below input | `ALLOWANCE_NOT_APPROVED` |
| Wrong positive-fee referrer | `BLOCKED` `REFERRER_NOT_ALLOWED`, never `NameError` |
| Nonzero dynamic-program padding | `NON_CANONICAL_PADDING` |
| Float, string or Boolean age | `AdapterError` |
| Observation without the candidate binding | `REJECTED` `OBS_BINDING_MISSING`, effects unproven |
| Quote `status` not `success` | `QUOTE_STATUS_ERROR` |
| Success without reconciled input, output or gas | `CONFIRMED`, effects unproven |
| Truncated or inconsistent ABI | `TRUNCATED_ABI` / `INCONSISTENT_ABI` |
| Non-canonical word | `NON_CANONICAL_WORD` |
| Conflicting declared summary | `CONFLICTING_SUMMARY` |
| `buildResponse` shape | `SCHEMA_UNSUPPORTED` |
| Missing freshness values | `UNKNOWN` outcome |
| Stale quote / expired intent | `STALE_QUOTE` / `INTENT_EXPIRED` |

## Feature-map proposal (this package)

| Feature | UI | API | SQL | Restart | Live | Evidence |
|---|---|---|---|---|---|---|
| Quote/build schema parse and freeze | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `apps/api/tests/kuru_flow/test_quote_schema.py` |
| Bounded entrypoint calldata decode | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `apps/api/tests/kuru_flow/test_flow_calldata.py` |
| Exact-candidate validation | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `apps/api/tests/kuru_flow/test_transaction_preparation.py`, `test_restriction_validation.py` |
| Unsigned candidate preparation | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `apps/api/tests/kuru_flow/test_transaction_preparation.py` |
| Observation normalization | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `apps/api/tests/kuru_flow/test_receipt_observation.py` |
| No-wiring and no-hash-substitution guards | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `apps/api/tests/kuru_flow/test_offline_properties.py` |

Every UI, API, SQL, restart and live row is `NOT_RUN`: this isolated package has no route, no storage, no restart behavior and no live path. The `verify-edge-os` browser/Hermes recipe is also `NOT_RUN` for this no-wiring stage.

## Future live verification (separately enabled)

A live verification step is separate and explicitly enabled. It would run only under a released packet (`LIVE_TEST_PACKET.md`) and would add: a read-only deployed-bytecode identity check; one frozen quote/build capture labelled `RECORDED`; a receipt and asset-delta capture for one controlled swap; and a denial, recovery and removal observation set. This proposal grants no live authority.
