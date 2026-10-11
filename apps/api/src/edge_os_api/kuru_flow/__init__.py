"""Isolated offline Kuru Flow adapter.

This package accepts supplied quote/build responses and an explicit approved
configuration and returns a validated immutable unsigned transaction candidate,
or a specific blocked or unknown result. It has no network, wallet, signing,
broadcast or credential code path and is not referenced by application
composition. Live qualification remains closed.
"""

from edge_os_api.kuru_flow.flow_calldata import CalldataDecodeError, decode_flow_call
from edge_os_api.kuru_flow.quote_schema import ParsedQuote, parse_quote_response
from edge_os_api.kuru_flow.receipt_observation import (
    ObservationInput,
    ObservationVerdict,
    normalize_observation,
)
from edge_os_api.kuru_flow.restriction_validation import (
    UNKNOWN_ONLY_REASONS,
    validate_candidate,
)
from edge_os_api.kuru_flow.transaction_preparation import (
    PreparationResult,
    prepare_unsigned_transaction,
)
from edge_os_api.kuru_flow.types import (
    AdapterAsset,
    AdapterError,
    ApprovedAdapterConfiguration,
    ApprovedFeeCollection,
    ApprovedFreshness,
    DecodedFeeCollection,
    DecodedFlowCall,
    DecodedFlowIntent,
    ObservationState,
    PreparationOutcome,
    QuoteSchemaVariant,
    ResponseProvenance,
    UnsignedTransactionCandidate,
)

__all__ = [
    "AdapterAsset",
    "AdapterError",
    "ApprovedAdapterConfiguration",
    "ApprovedFeeCollection",
    "ApprovedFreshness",
    "CalldataDecodeError",
    "DecodedFeeCollection",
    "DecodedFlowCall",
    "DecodedFlowIntent",
    "ObservationInput",
    "ObservationState",
    "ObservationVerdict",
    "ParsedQuote",
    "PreparationOutcome",
    "PreparationResult",
    "QuoteSchemaVariant",
    "ResponseProvenance",
    "UNKNOWN_ONLY_REASONS",
    "UnsignedTransactionCandidate",
    "decode_flow_call",
    "normalize_observation",
    "parse_quote_response",
    "prepare_unsigned_transaction",
    "validate_candidate",
]
