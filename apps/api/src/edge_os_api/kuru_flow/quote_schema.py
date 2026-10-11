"""Parse and freeze the supported Kuru Flow quote/build response schema.

Two public shapes are documented and they disagree. ``TRANSACTION_CALLDATA`` is
the Monad-guide shape with ``transaction { to, calldata, value }``. ``BUILD_RESPONSE``
is the Kuru OpenAPI shape with ``path`` and ``buildResponse``. The conflict is
retained: the inner ``buildResponse``/``path`` schema stays unknown and this
module never invents transaction bytes for it. A response that carries both
shapes, or neither, is rejected. A ``RECORDED`` response must carry capture
metadata; this package invents no recorded response.
"""

from __future__ import annotations

from typing import Any, Mapping

from edge_os_api.kuru_flow.types import (
    R_CALLDATA_MISSING,
    R_CALLDATA_NOT_HEX,
    R_PROVENANCE_INVALID,
    R_SCHEMA_AMBIGUOUS,
    R_SCHEMA_UNSUPPORTED,
    AdapterError,
    QuoteSchemaVariant,
    ResponseProvenance,
    StrictModel,
    canonical_raw,
    is_address,
    is_nonempty_hex,
)

_TRANSACTION_KEYS = ("to", "calldata", "value")


class ParsedQuote(StrictModel):
    """A parsed supplier response with its variant, provenance and schema reasons."""

    variant: QuoteSchemaVariant | None = None
    provenance: ResponseProvenance
    reference_output_raw: str | None = None
    min_out_raw: str | None = None
    to: str | None = None
    value_raw: str | None = None
    calldata_hex: str | None = None
    gas_prices: dict | None = None
    declared_intent: dict | None = None
    reasons: list[str] = []


def _normalize_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value if value.startswith("0x") else "0x" + value
    if not is_nonempty_hex(text):
        return None
    return text


def _normalize_raw(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value >= 0 else None
    if isinstance(value, str) and canonical_raw(value):
        return value
    return None


def _require_recorded_metadata(mapping: Mapping[str, Any]) -> None:
    metadata = mapping.get("_provenance")
    if not isinstance(metadata, Mapping):
        raise AdapterError(f"{R_PROVENANCE_INVALID}: a RECORDED response requires _provenance metadata")
    source_url = metadata.get("source_url")
    captured_at = metadata.get("captured_at")
    digest = metadata.get("sha256")
    if not isinstance(source_url, str) or not source_url.strip():
        raise AdapterError(f"{R_PROVENANCE_INVALID}: _provenance.source_url is required")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise AdapterError(f"{R_PROVENANCE_INVALID}: _provenance.captured_at is required")
    if not isinstance(digest, str) or len(digest) != 64:
        raise AdapterError(f"{R_PROVENANCE_INVALID}: _provenance.sha256 must be a 64-character hex digest")


def _parse_transaction_shape(
    mapping: Mapping[str, Any], provenance: ResponseProvenance
) -> ParsedQuote:
    transaction = mapping["transaction"]
    reasons: list[str] = []
    if not isinstance(transaction, Mapping):
        return ParsedQuote(
            variant=QuoteSchemaVariant.TRANSACTION_CALLDATA,
            provenance=provenance,
            reasons=[R_SCHEMA_UNSUPPORTED],
        )
    for key in _TRANSACTION_KEYS:
        if key not in transaction:
            reasons.append(R_SCHEMA_UNSUPPORTED)
    to = transaction.get("to")
    to_address = to if isinstance(to, str) and is_address(to) else None
    if to_address is None:
        reasons.append(R_SCHEMA_UNSUPPORTED)
    value_raw = _normalize_raw(transaction.get("value"))
    if value_raw is None:
        reasons.append(R_SCHEMA_UNSUPPORTED)
    calldata = transaction.get("calldata")
    if calldata is None:
        reasons.append(R_CALLDATA_MISSING)
        calldata_hex = None
    else:
        calldata_hex = _normalize_hex(calldata)
        if calldata_hex is None:
            reasons.append(R_CALLDATA_NOT_HEX)
    return ParsedQuote(
        variant=QuoteSchemaVariant.TRANSACTION_CALLDATA,
        provenance=provenance,
        reference_output_raw=_normalize_raw(mapping.get("output")),
        min_out_raw=_normalize_raw(mapping.get("minOut")),
        to=to_address,
        value_raw=value_raw,
        calldata_hex=calldata_hex,
        gas_prices=mapping.get("gasPrices") if isinstance(mapping.get("gasPrices"), dict) else None,
        declared_intent=mapping.get("intent") if isinstance(mapping.get("intent"), dict) else None,
        reasons=reasons,
    )


def parse_quote_response(
    mapping: Mapping[str, Any], provenance: ResponseProvenance
) -> ParsedQuote:
    """Parse one supplied response and freeze its variant and provenance.

    Raises ``AdapterError`` for a loader defect: a missing provenance label or a
    ``RECORDED`` response without capture metadata.
    """
    if not isinstance(provenance, ResponseProvenance):
        raise AdapterError(f"{R_PROVENANCE_INVALID}: provenance must be a ResponseProvenance")
    if not isinstance(mapping, Mapping):
        raise AdapterError(f"{R_PROVENANCE_INVALID}: the response must be a mapping")
    if provenance is ResponseProvenance.RECORDED:
        _require_recorded_metadata(mapping)

    has_transaction = isinstance(mapping.get("transaction"), Mapping)
    has_build = "buildResponse" in mapping or "path" in mapping

    if has_transaction and has_build:
        return ParsedQuote(variant=None, provenance=provenance, reasons=[R_SCHEMA_AMBIGUOUS])
    if has_transaction:
        return _parse_transaction_shape(mapping, provenance)
    if has_build:
        declared = mapping.get("buildResponse")
        return ParsedQuote(
            variant=QuoteSchemaVariant.BUILD_RESPONSE,
            provenance=provenance,
            reference_output_raw=_normalize_raw(mapping.get("output")),
            min_out_raw=_normalize_raw(mapping.get("minOut")),
            gas_prices=mapping.get("gasPrices") if isinstance(mapping.get("gasPrices"), dict) else None,
            declared_intent=declared if isinstance(declared, dict) else None,
            reasons=[R_SCHEMA_UNSUPPORTED],
        )
    return ParsedQuote(variant=None, provenance=provenance, reasons=[R_SCHEMA_UNSUPPORTED])
