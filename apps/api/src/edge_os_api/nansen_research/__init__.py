"""Local Nansen research package.

This package collects bounded Nansen Token God Mode holders and flow observations
over a caller-supplied transport and builds a deterministic, source-linked report
with explicit coverage and unknowns. It is a library only. It has no live
transport, reads no credential and environment value, and opens no socket. Lane 2
mounts its output into the authenticated investigation path later.

Interface freeze: ``docs/qualification/nansen-report/INTERFACE_FREEZE.md``.
"""

from __future__ import annotations

from edge_os_api.nansen_research.collector import NansenRun, run_research
from edge_os_api.nansen_research.errors import (
    NansenAuthError,
    NansenBudgetExhausted,
    NansenCancelled,
    NansenContractError,
    NansenError,
    NansenInputError,
    NansenLimitError,
    NansenPaymentRequired,
    NansenProtocolError,
    NansenProviderError,
    NansenRateLimited,
    NansenRequestError,
    NansenTimeout,
    NansenTransportError,
)
from edge_os_api.nansen_research.evidence_extraction import (
    classify_availability,
    expected_bucket_starts,
    extract_flow_evidence,
    extract_holder_evidence,
)
from edge_os_api.nansen_research.models import (
    API_SCHEMA_VERSION,
    CHAIN_ID,
    CONVENTIONS_VERSION,
    ENDPOINT,
    EVIDENCE_SCHEMA,
    NETWORK,
    PROFILE_VERSION,
    PROVIDER,
    PROVIDER_VERSION,
    REPORT_SCHEMA,
    REQUEST_SCHEMA,
    Coverage,
    Finding,
    FlowBucket,
    FlowEvidence,
    FlowQuery,
    HolderEvidence,
    HolderQuery,
    HolderRow,
    Limitation,
    NansenContext,
    NansenEvidence,
    NansenLimits,
    NansenReport,
    NansenRequest,
    ObservationWindow,
    SourceRecord,
)
from edge_os_api.nansen_research.nansen_client import NansenClient, NansenFetch
from edge_os_api.nansen_research.report_builder import build_report
from edge_os_api.nansen_research.serialization import canonical_sha256
from edge_os_api.nansen_research.transport import (
    NansenResponse,
    NansenTransport,
    RecordedNansenTransport,
)

__all__ = [
    "API_SCHEMA_VERSION",
    "CHAIN_ID",
    "CONVENTIONS_VERSION",
    "Coverage",
    "ENDPOINT",
    "EVIDENCE_SCHEMA",
    "Finding",
    "FlowBucket",
    "FlowEvidence",
    "FlowQuery",
    "HolderEvidence",
    "HolderQuery",
    "HolderRow",
    "Limitation",
    "NETWORK",
    "NansenAuthError",
    "NansenBudgetExhausted",
    "NansenCancelled",
    "NansenClient",
    "NansenContext",
    "NansenContractError",
    "NansenError",
    "NansenEvidence",
    "NansenFetch",
    "NansenInputError",
    "NansenLimitError",
    "NansenLimits",
    "NansenPaymentRequired",
    "NansenProtocolError",
    "NansenProviderError",
    "NansenRateLimited",
    "NansenReport",
    "NansenRequest",
    "NansenRequestError",
    "NansenResponse",
    "NansenRun",
    "NansenTimeout",
    "NansenTransport",
    "NansenTransportError",
    "ObservationWindow",
    "PROFILE_VERSION",
    "PROVIDER",
    "PROVIDER_VERSION",
    "REPORT_SCHEMA",
    "REQUEST_SCHEMA",
    "RecordedNansenTransport",
    "SourceRecord",
    "build_report",
    "canonical_sha256",
    "classify_availability",
    "expected_bucket_starts",
    "extract_flow_evidence",
    "extract_holder_evidence",
    "run_research",
]
