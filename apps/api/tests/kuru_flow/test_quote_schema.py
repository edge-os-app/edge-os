from __future__ import annotations

import pytest

from edge_os_api.kuru_flow.quote_schema import parse_quote_response
from edge_os_api.kuru_flow.types import (
    R_SCHEMA_AMBIGUOUS,
    R_SCHEMA_UNSUPPORTED,
    AdapterError,
    QuoteSchemaVariant,
    ResponseProvenance,
)

from kuru_flow._support import build_response, encode_execute_swap, transaction_response


def test_transaction_shape_parses_and_normalizes_unprefixed_calldata():
    parsed = parse_quote_response(transaction_response(encode_execute_swap()), ResponseProvenance.AUTHORED)
    assert parsed.variant is QuoteSchemaVariant.TRANSACTION_CALLDATA
    assert parsed.provenance is ResponseProvenance.AUTHORED
    assert parsed.calldata_hex is not None and parsed.calldata_hex.startswith("0x")
    assert parsed.to == transaction_response("0x00")["transaction"]["to"]
    assert parsed.value_raw == "1000000000000000000"
    assert parsed.reference_output_raw == "1500000"
    assert parsed.reasons == []


def test_build_response_shape_is_unsupported_not_invented():
    parsed = parse_quote_response(build_response(), ResponseProvenance.DOCUMENTATION)
    assert parsed.variant is QuoteSchemaVariant.BUILD_RESPONSE
    assert parsed.calldata_hex is None
    assert parsed.reasons == [R_SCHEMA_UNSUPPORTED]


def test_ambiguous_shape_blocked():
    data = transaction_response(encode_execute_swap())
    data["buildResponse"] = {"kind": "x"}
    parsed = parse_quote_response(data, ResponseProvenance.AUTHORED)
    assert parsed.variant is None
    assert parsed.reasons == [R_SCHEMA_AMBIGUOUS]


def test_unrecognized_shape_blocked():
    parsed = parse_quote_response({"foo": 1}, ResponseProvenance.AUTHORED)
    assert parsed.variant is None
    assert parsed.reasons == [R_SCHEMA_UNSUPPORTED]


def test_recorded_without_metadata_raises():
    with pytest.raises(AdapterError) as error:
        parse_quote_response(transaction_response(encode_execute_swap()), ResponseProvenance.RECORDED)
    assert "PROVENANCE_INVALID" in str(error.value)


def test_recorded_with_metadata_is_accepted_as_labelled():
    data = transaction_response(encode_execute_swap())
    data["_provenance"] = {
        "source_url": "https://example.test/quote",
        "captured_at": "2026-10-11T00:00:00Z",
        "sha256": "a" * 64,
    }
    parsed = parse_quote_response(data, ResponseProvenance.RECORDED)
    assert parsed.provenance is ResponseProvenance.RECORDED
    assert parsed.reasons == []
