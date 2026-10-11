# Kuru Flow adapter profile (isolated offline stage)

Owned package: `apps/api/src/edge_os_api/kuru_flow/`. This profile records the isolated, offline Kuru Flow adapter for P20 issue #19 under the builder's 2026-10-11 continuation. It is a preparation stage. It is not API/UI/SQL wiring, not production admission, not a provider call, not signing or execution.

Status: **offline adapter implemented and locally tested; provider, network and deployed behavior unqualified.** The adapter proves only that the stated relationships hold in this checkout over authored and documented fixtures. It proves no live schema, no deployed bytecode identity, no provider policy behavior and no financial safety.

## Responsibility

The package accepts a supplied quote/build response plus an explicit approved configuration, and returns a validated immutable unsigned transaction candidate, or a specific `BLOCKED` or `UNKNOWN` result. It never loads a secret, constructs a live client, signs, broadcasts or spends. The package is disabled and unreferenced by application composition.

## Files

| File | Responsibility |
|---|---|
| `types.py` | Strict shared models: approved configuration, decoded intent and fees, frozen candidate, provenance, outcome and reason codes. |
| `quote_schema.py` | Parse and freeze the supported quote/build response schema; retain the documented shape conflict. |
| `flow_calldata.py` | Bounded decoder for the exact entrypoint calldata (two documented layouts). Not a general ABI codec. |
| `restriction_validation.py` | Validate a decoded candidate against the approved configuration; exact-value and bound checks. |
| `transaction_preparation.py` | Public entry: prepare one immutable unsigned candidate or a blocked/unknown result. |
| `receipt_observation.py` | Normalize supplied receipt/observation fixtures without inventing effects. |

Names describe responsibility. Ticket numbers are not module names.

## Public interface

- `prepare_unsigned_transaction(*, quote_response, provenance, config, now=None, quote_age_seconds=None, input_age_seconds=None) -> PreparationResult`
- `parse_quote_response(mapping, provenance) -> ParsedQuote`
- `decode_flow_call(*, data_hex, method) -> DecodedFlowCall`
- `validate_candidate(*, parsed, call, config, quote_age_seconds=None, input_age_seconds=None, now=None) -> tuple[str, ...]`
- `normalize_observation(*, observation, expected_candidate_hash, expected_chain_id, expected_wallet, expected_tx_hash=None) -> ObservationVerdict`

`prepare_unsigned_transaction` returns `ACCEPTED` with an immutable `UnsignedTransactionCandidate`, or `BLOCKED`/`UNKNOWN` with ordered, de-duplicated reason codes. A malformed declaration raises `AdapterError`.

## Frozen quote schema

The supported schema is the K2 Monad-guide `TRANSACTION_CALLDATA` shape: top-level `type`, `status`, `output`, `minOut`, `transaction { to, calldata, value }` and `gasPrices`. `calldata` has no `0x` prefix and is normalized. The K3 Kuru OpenAPI `BUILD_RESPONSE` shape (`path`, `buildResponse`) is recognized but its inner schema stays `UNKNOWN`; it is unsupported and never becomes transaction bytes. A response carrying both shapes is ambiguous and rejected. A `RECORDED` response requires `_provenance` capture metadata; the package invents no recorded response.

## Exact-candidate validation

The adapter decodes the supplied calldata using the approved method layout and checks the decoded fields against the adopted values:

- network and chain id; entrypoint `to`; selector; method;
- input and output asset addresses; exact raw input; minimum received at or below the quote estimate;
- fee bound `feeBps + referrerFeeBps <= 10000`, exact fee values, fee-collector and referrer addresses, input/output fee mode;
- native versus ERC-20 value; the separate ERC-20 allowance requirement;
- exact route `program` bytes; the explicit receiver when the method encodes one;
- quote and input freshness, and local intent and mandate expiry;
- a conflicting declared decoded summary.

Booleans, floats, malformed or empty identities, non-canonical or out-of-range quantities, invalid hex, unknown selectors, truncated or inconsistent ABI fields and non-canonical words are rejected. Unsupported decoding stays blocked.

## Ethereum hash boundary

This environment has no Ethereum Keccak-256 and no installed Keccak library. The adapter computes no Ethereum hash. The approved function selector is supplied as a source-backed constant and checked by equality; a real selector requires Keccak and is unqualified. The candidate identity is the application canonical SHA-256 (`candidate_hash`), which is a local application identity, not an Ethereum transaction hash. SHA3-256 is never substituted for Keccak. A dependency for Keccak (for example `eth-hash`) is a needed future input, not written here.

## Observation boundary

`normalize_observation` binds one observation to the original expected action and candidate identity. A missing receipt, a lost acknowledgement, a timeout, a pending result, a reverted result, a network, wallet or transaction mismatch and unknown actual deltas stay unknown or rejected. A success status alone is not proof of all asset effects: without reconciled deltas the effects stay unproven. The normalizer never retries, replaces a route, produces a second action or builds a durable queue.

## Wiring seam

The accepted P23 local submission carries identities and a `payload_hash`, not full chain bytes (`execution/transport.py`). A future live stage must carry the exact unsigned candidate bytes and later the signed bytes and their locally derived Keccak transaction hash. That wiring is not part of this stage and is not changed here.

## Evidence classification

All results here are `LOCAL_TESTED` at most, over authored and documented fixtures. They are not provider enforcement and not live wallet inventory. Provider and chain results stay `NOT_RUN`.

## Boundaries

- Local fixture work only. No provider, route, request, wallet, funding, signing, broadcast or payment.
- No dependency, lockfile, migration, shared configuration, route or composition change.
- Full P20 issue #19 stays OPEN and unqualified beyond this offline preparation.
