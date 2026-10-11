"""Validate a decoded Flow candidate against the approved configuration.

Every check compares the exact decoded candidate fields with an adopted value or
an exact bound. A missing or unknown mandatory value is never treated as zero or
as approved. The function returns ordered, de-duplicated reason codes; an empty
tuple means the candidate matched the approved configuration.
"""

from __future__ import annotations

from edge_os_api.kuru_flow.quote_schema import ParsedQuote
from edge_os_api.kuru_flow.types import (
    METHOD_EXECUTE_SWAP_WITH_RECEIVER,
    R_ALLOWANCE_NOT_APPROVED,
    R_ALLOWANCE_UNKNOWN,
    R_ASSET_NOT_ALLOWED,
    R_CONFLICTING_SUMMARY,
    R_ENTRYPOINT_NOT_ALLOWED,
    R_ERC20_VALUE_NOT_ZERO,
    R_EXPIRY_UNKNOWN,
    R_FEE_BOUND_EXCEEDED,
    R_FEE_COLLECTOR_NOT_ALLOWED,
    R_FEE_MODE_MISMATCH,
    R_FEE_NOT_APPROVED,
    R_FRESHNESS_UNKNOWN,
    R_INPUT_FRESHNESS_UNKNOWN,
    R_INPUT_NOT_APPROVED,
    R_INTENT_EXPIRED,
    R_MANDATE_EXPIRED,
    R_METHOD_NOT_ALLOWED,
    R_MIN_OUTPUT_INVALID,
    R_NATIVE_VALUE_INSUFFICIENT,
    R_PROGRAM_NOT_APPROVED,
    R_QUOTE_UNKNOWN,
    R_RECIPIENT_NOT_ALLOWED,
    R_SCHEMA_UNSUPPORTED,
    R_SELECTOR_NOT_ALLOWED,
    R_STALE_INPUT,
    R_STALE_QUOTE,
    R_VALUE_NOT_APPROVED,
    ApprovedAdapterConfiguration,
    DecodedFlowCall,
    dedupe,
    parse_utc,
)

UNKNOWN_ONLY_REASONS: frozenset[str] = frozenset(
    {R_FRESHNESS_UNKNOWN, R_INPUT_FRESHNESS_UNKNOWN, R_EXPIRY_UNKNOWN}
)

_SUMMARY_KEYS = {
    "token_user_sells": "tokenUserSells",
    "amount_user_sells": "amountUserSells",
    "token_user_buys": "tokenUserBuys",
    "min_amount_user_buys": "minAmountUserBuys",
}


def _same_address(left: str, right: str) -> bool:
    return left.lower() == right.lower()


def _validate_conflicting_summary(parsed: ParsedQuote, call: DecodedFlowCall) -> list[str]:
    declared = parsed.declared_intent
    if not isinstance(declared, dict):
        return []
    decoded = {
        "token_user_sells": call.intent.token_user_sells,
        "amount_user_sells": call.intent.amount_user_sells,
        "token_user_buys": call.intent.token_user_buys,
        "min_amount_user_buys": call.intent.min_amount_user_buys,
    }
    for snake, camel in _SUMMARY_KEYS.items():
        if camel not in declared:
            continue
        supplied = declared[camel]
        if snake in ("token_user_sells", "token_user_buys"):
            if not isinstance(supplied, str) or not _same_address(supplied, decoded[snake]):
                return [R_CONFLICTING_SUMMARY]
        else:
            if str(supplied) != decoded[snake]:
                return [R_CONFLICTING_SUMMARY]
    return []


def _validate_value(parsed: ParsedQuote, call: DecodedFlowCall, config: ApprovedAdapterConfiguration) -> list[str]:
    value_raw = parsed.value_raw
    if value_raw is None:
        return [R_VALUE_NOT_APPROVED]
    if config.input_is_native():
        if value_raw != call.intent.amount_user_sells:
            if int(value_raw) < int(call.intent.amount_user_sells):
                return [R_NATIVE_VALUE_INSUFFICIENT]
            return [R_VALUE_NOT_APPROVED]
        return []
    if value_raw != "0":
        return [R_ERC20_VALUE_NOT_ZERO]
    approved_allowance = config.approved_allowance_raw
    if approved_allowance is None:
        return [R_ALLOWANCE_UNKNOWN]
    if int(call.intent.amount_user_sells) > int(approved_allowance):
        return [R_ALLOWANCE_NOT_APPROVED]
    return []


def _validate_fees(call: DecodedFlowCall, config: ApprovedAdapterConfiguration) -> list[str]:
    reasons: list[str] = []
    fees = call.fees
    approved = config.fees
    if fees.fee_total() > 10_000:
        reasons.append(R_FEE_BOUND_EXCEEDED)
    if fees.fee_bps != approved.fee_bps or fees.referrer_fee_bps != approved.referrer_fee_bps:
        reasons.append(R_FEE_NOT_APPROVED)
    if fees.fee_bps > 0 and not _same_address(fees.fee_collector_address, approved.fee_collector_address):
        reasons.append(R_FEE_COLLECTOR_NOT_ALLOWED)
    if fees.referrer_fee_bps > 0 and not _same_address(fees.referrer_address, approved.referrer_address):
        reasons.append(R_REFERRER_NOT_ALLOWED)
    if fees.fee_total() > 0 and fees.is_in_token_fee != approved.is_in_token_fee:
        reasons.append(R_FEE_MODE_MISMATCH)
    return reasons


def _validate_min_output(parsed: ParsedQuote, call: DecodedFlowCall, config: ApprovedAdapterConfiguration) -> list[str]:
    approved_min = config.approved_min_output_raw
    if call.intent.min_amount_user_buys != approved_min:
        return [R_MIN_OUTPUT_INVALID]
    if parsed.reference_output_raw is None:
        return [R_QUOTE_UNKNOWN]
    if int(call.intent.min_amount_user_buys) > int(parsed.reference_output_raw):
        return [R_MIN_OUTPUT_INVALID]
    return []


def _validate_freshness(
    config: ApprovedAdapterConfiguration,
    quote_age_seconds: int | None,
    input_age_seconds: int | None,
    now: str | None,
) -> list[str]:
    reasons: list[str] = []
    freshness = config.freshness
    if freshness.max_quote_age_seconds is None or quote_age_seconds is None:
        reasons.append(R_FRESHNESS_UNKNOWN)
    elif quote_age_seconds > freshness.max_quote_age_seconds:
        reasons.append(R_STALE_QUOTE)
    if freshness.max_input_age_seconds is None or input_age_seconds is None:
        reasons.append(R_INPUT_FRESHNESS_UNKNOWN)
    elif input_age_seconds > freshness.max_input_age_seconds:
        reasons.append(R_STALE_INPUT)
    if now is None or freshness.intent_expires_at is None or freshness.mandate_expires_at is None:
        reasons.append(R_EXPIRY_UNKNOWN)
    else:
        moment = parse_utc(now)
        if moment >= parse_utc(freshness.intent_expires_at):
            reasons.append(R_INTENT_EXPIRED)
        if moment >= parse_utc(freshness.mandate_expires_at):
            reasons.append(R_MANDATE_EXPIRED)
    return reasons


def validate_candidate(
    *,
    parsed: ParsedQuote,
    call: DecodedFlowCall,
    config: ApprovedAdapterConfiguration,
    quote_age_seconds: int | None = None,
    input_age_seconds: int | None = None,
    now: str | None = None,
) -> tuple[str, ...]:
    """Return the ordered, de-duplicated reasons a candidate is not approved."""
    reasons: list[str] = []

    if parsed.variant is None or parsed.variant.value not in config.supported_schema_variants:
        reasons.append(R_SCHEMA_UNSUPPORTED)

    if parsed.to is None or not _same_address(parsed.to, config.entrypoint_address):
        reasons.append(R_ENTRYPOINT_NOT_ALLOWED)
    if call.selector != config.selector:
        reasons.append(R_SELECTOR_NOT_ALLOWED)
    if call.method != config.method:
        reasons.append(R_METHOD_NOT_ALLOWED)

    if not _same_address(call.intent.token_user_sells, config.input_asset.token_address):
        reasons.append(R_ASSET_NOT_ALLOWED)
    if not _same_address(call.intent.token_user_buys, config.output_asset.token_address):
        reasons.append(R_ASSET_NOT_ALLOWED)

    if call.intent.amount_user_sells != config.approved_input_raw:
        reasons.append(R_INPUT_NOT_APPROVED)

    reasons.extend(_validate_min_output(parsed, call, config))
    reasons.extend(_validate_fees(call, config))
    reasons.extend(_validate_value(parsed, call, config))

    if call.program_hex.lower() != config.approved_program_hex.lower():
        reasons.append(R_PROGRAM_NOT_APPROVED)

    if config.method == METHOD_EXECUTE_SWAP_WITH_RECEIVER:
        if call.receiver is None or not _same_address(call.receiver, config.recipient):
            reasons.append(R_RECIPIENT_NOT_ALLOWED)

    reasons.extend(_validate_conflicting_summary(parsed, call))
    reasons.extend(_validate_freshness(config, quote_age_seconds, input_age_seconds, now))

    return tuple(dedupe(reasons))
