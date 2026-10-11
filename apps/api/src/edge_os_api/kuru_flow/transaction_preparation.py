"""Prepare one validated immutable unsigned transaction candidate.

The public entry point accepts a supplied quote/build response and an explicit
approved configuration. It returns an immutable unsigned candidate, or a
specific ``BLOCKED`` or ``UNKNOWN`` result. It never loads a secret, constructs a
live client, signs, broadcasts or spends.

The candidate identity is the application canonical SHA-256 of the normalized
candidate. It is not an Ethereum transaction hash; that requires Keccak of the
encoded signed transaction and is outside this offline stage. No SHA3-256 is
substituted for Ethereum Keccak anywhere in this package.
"""

from __future__ import annotations

from typing import Any, Mapping

from edge_os_api.kuru_flow.flow_calldata import CalldataDecodeError, decode_flow_call
from edge_os_api.kuru_flow.quote_schema import ParsedQuote, parse_quote_response
from edge_os_api.kuru_flow.restriction_validation import UNKNOWN_ONLY_REASONS, validate_candidate
from edge_os_api.kuru_flow.types import (
    R_CALLDATA_MISSING,
    R_SCHEMA_UNSUPPORTED,
    ApprovedAdapterConfiguration,
    DecodedFlowCall,
    PreparationOutcome,
    QuoteSchemaVariant,
    ResponseProvenance,
    StrictModel,
    UnsignedTransactionCandidate,
    candidate_identity,
)


class PreparationResult(StrictModel):
    """The outcome of one offline preparation attempt."""

    outcome: PreparationOutcome
    provenance: ResponseProvenance
    schema_variant: QuoteSchemaVariant | None = None
    reasons: list[str] = []
    candidate: UnsignedTransactionCandidate | None = None


def _dedupe(reasons: list[str]) -> list[str]:
    seen: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.append(reason)
    return seen


def _build_candidate(
    parsed: ParsedQuote, call: DecodedFlowCall, config: ApprovedAdapterConfiguration
) -> UnsignedTransactionCandidate:
    data_hex = parsed.calldata_hex or ""
    value_raw = parsed.value_raw or "0"
    payload: dict[str, Any] = {
        "chain_id": config.chain_id,
        "to": config.entrypoint_address,
        "value_raw": value_raw,
        "data_hex": data_hex,
        "selector": call.selector,
        "method": call.method,
        "intent": call.intent.model_dump(mode="json"),
        "fees": call.fees.model_dump(mode="json"),
        "program_hex": call.program_hex,
        "receiver": call.receiver,
    }
    return UnsignedTransactionCandidate(
        candidate_hash=candidate_identity(payload),
        chain_id=config.chain_id,
        to=config.entrypoint_address,
        value_raw=value_raw,
        data_hex=data_hex,
        selector=call.selector,
        method=call.method,
        intent=call.intent,
        fees=call.fees,
        program_hex=call.program_hex,
        receiver=call.receiver,
        response_provenance=parsed.provenance,
        schema_variant=parsed.variant or QuoteSchemaVariant.TRANSACTION_CALLDATA,
    )


def prepare_unsigned_transaction(
    *,
    quote_response: Mapping[str, Any],
    provenance: ResponseProvenance,
    config: ApprovedAdapterConfiguration,
    now: str | None = None,
    quote_age_seconds: int | None = None,
    input_age_seconds: int | None = None,
) -> PreparationResult:
    """Prepare one offline candidate or return a specific blocked/unknown result."""
    parsed = parse_quote_response(quote_response, provenance)

    schema_reasons = list(parsed.reasons)
    if not schema_reasons:
        if parsed.variant is None or parsed.variant.value not in config.supported_schema_variants:
            schema_reasons.append(R_SCHEMA_UNSUPPORTED)
        elif parsed.calldata_hex is None:
            schema_reasons.append(R_CALLDATA_MISSING)
    if schema_reasons:
        return PreparationResult(
            outcome=PreparationOutcome.BLOCKED,
            provenance=provenance,
            schema_variant=parsed.variant,
            reasons=_dedupe(schema_reasons),
        )

    try:
        call = decode_flow_call(data_hex=parsed.calldata_hex or "", method=config.method)
    except CalldataDecodeError as error:
        return PreparationResult(
            outcome=PreparationOutcome.BLOCKED,
            provenance=provenance,
            schema_variant=parsed.variant,
            reasons=[error.reason],
        )

    reasons = validate_candidate(
        parsed=parsed,
        call=call,
        config=config,
        quote_age_seconds=quote_age_seconds,
        input_age_seconds=input_age_seconds,
        now=now,
    )
    if not reasons:
        return PreparationResult(
            outcome=PreparationOutcome.ACCEPTED,
            provenance=provenance,
            schema_variant=parsed.variant,
            candidate=_build_candidate(parsed, call, config),
        )
    if set(reasons) <= UNKNOWN_ONLY_REASONS:
        return PreparationResult(
            outcome=PreparationOutcome.UNKNOWN,
            provenance=provenance,
            schema_variant=parsed.variant,
            reasons=list(reasons),
        )
    return PreparationResult(
        outcome=PreparationOutcome.BLOCKED,
        provenance=provenance,
        schema_variant=parsed.variant,
        reasons=list(reasons),
    )
