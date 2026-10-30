"""Operating releases: the frozen, server-owned bounds of one research run (#58 RESEARCH-RUNTIME-LOCAL).

A release names exactly what one bounded run may do: the provider endpoints and credential slots, the P07 market
profile (network, pool, assets, units, orientation, window), the scan, the corroboration sample and fixed request,
byte, time and credit limits. Nothing here performs I/O or reads a credential.

Two kinds exist. A `STAND_IN` release points only at loopback or `.invalid` hosts and is served by a recording or an
owned loopback server; it is refused in production. An `ACTUAL` release points at real provider hosts and is usable
only when `APPROVED_RELEASES` records its exact SHA-256. Exactly one actual release is approved; no setting, environment
value, file or request can add or change one. See
`docs/qualification/research-provider-composition/CONTRACT.md` and, for the registered release,
`MOE_HISTORY_ACTUAL_RELEASE.md` beside it.

A history part may name one frozen forward-history recorder handoff for saved-payload binding; admission validates it
here, before any credential read (`research/history_payload_binding.py`, `PAYLOAD_BINDING.md`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

from edge_os_api.nansen_research.http_transport import NANSEN_ORIGIN
from edge_os_api.records import contract_adapter as record_contract

RELEASE_VERSION = "edge-os.research-operating-release/1"
SOURCE_VERSION = "envio-hypersync/1"
RPC_METHODS = ("eth_chainId", "eth_getTransactionReceipt")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
# Approved ACTUAL release id -> its exact release SHA-256. Exactly one release is approved below. Adding, changing or
# removing an entry is a reviewed code change that cites the builder's recorded approval of that exact release.
APPROVED_RELEASES: Mapping[str, str] = {
    "actual-moe-history2h-nansen-20261022/1":
        "45c8cfbf5d61eb519ee3140e02e50b2b7091669dc28cbef224bdc6a0e77ca877",
}
# The reserved `HistoryRelease.provider_facts` key of an optional frozen recorder handoff: {handoff_json, handoff_sha256}.
BINDING_FACT = "forward_history_binding"

ReleaseKind = Literal["STAND_IN", "ACTUAL"]


class ReleaseRefused(RuntimeError):
    """The release cannot be used. Raised before any credential read or provider request."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class HistoryRelease:
    source_id: str
    title: str
    envio_endpoint: str
    envio_credential_slot: str
    quicknode_host: str
    quicknode_credential_slot: str
    profile: Mapping[str, Any]
    scan: Mapping[str, int]
    corroboration_sample_size: int
    provider_facts: Mapping[str, Any]
    limits: Mapping[str, int]
    client_bounds: Mapping[str, int]  # whole seconds and bytes: canonical JSON forbids floats
    rpc_methods: tuple[str, ...] = RPC_METHODS
    source_version: str = SOURCE_VERSION
    time_basis: Mapping[str, str] = field(default_factory=lambda: {"event_time": "BLOCK_TIMESTAMP",
                                                                   "collection_time": "APPLICATION_CLOCK"})
    required_coverage: str = "COMPLETE_SCAN"


@dataclass(frozen=True)
class NansenRelease:
    endpoint: str
    credential_slot: str
    token_address: str
    token_symbol: str
    window: Mapping[str, str]
    operations: tuple[str, ...]
    holder_query: Mapping[str, Any]
    flow_query: Mapping[str, Any]
    limits: Mapping[str, Any]
    deadline_seconds: int
    compute_seconds: int
    client_bounds: Mapping[str, int]  # per call: connect_timeout_seconds, max_request_bytes, max_response_bytes


@dataclass(frozen=True)
class OperatingRelease:
    release_id: str
    kind: ReleaseKind
    history: HistoryRelease | None = None
    nansen: NansenRelease | None = None


def release_content(release: OperatingRelease) -> dict[str, Any]:
    """The canonical JSON form that the SHA-256 covers."""
    return {"schema_version": RELEASE_VERSION, **_plain(asdict(release))}


def release_sha256(release: OperatingRelease) -> str:
    return hashlib.sha256(record_contract.canonical_bytes(release_content(release))).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def endpoint_host(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        raise ReleaseRefused("operating_release_invalid", "an endpoint is not a URL") from None
    if not parts.hostname or parts.scheme not in ("http", "https"):
        raise ReleaseRefused("operating_release_invalid", "an endpoint must be an http or https URL with a host")
    return parts.hostname


def _check_host(kind: ReleaseKind, url_or_host: str, *, is_host: bool = False) -> None:
    host = url_or_host if is_host else endpoint_host(url_or_host)
    scheme = None if is_host else urlsplit(url_or_host).scheme
    local = host in LOOPBACK_HOSTS or host.endswith(".invalid")
    if kind == "STAND_IN" and not local:
        raise ReleaseRefused("stand_in_endpoint_not_local",
                             "a stand-in release may name only loopback or .invalid hosts")
    if kind == "ACTUAL" and (local or (scheme is not None and scheme != "https")):
        raise ReleaseRefused("operating_release_invalid", "an actual release needs https provider hosts")


def _check_history(kind: ReleaseKind, history: HistoryRelease) -> None:
    _check_host(kind, history.envio_endpoint)
    _check_host(kind, history.quicknode_host, is_host=True)
    if tuple(history.rpc_methods) != RPC_METHODS or history.source_version != SOURCE_VERSION:
        raise ReleaseRefused("operating_release_invalid", "the release names another RPC method set or source version")
    limits = history.limits
    needed = {"provider_requests", "compute_seconds", "max_pages", "max_rows", "max_bytes", "deadline_seconds"}
    if set(limits) != needed or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in limits.values()):
        raise ReleaseRefused("operating_release_invalid", "the release limits must be positive whole numbers")
    if limits["max_pages"] + 1 + history.corroboration_sample_size > limits["provider_requests"]:
        raise ReleaseRefused("operating_release_invalid",
                             "the request limit must cover the pages, one chain read and every sampled receipt")
    bounds = {"deadline_seconds", "connect_timeout_seconds", "max_response_bytes", "max_request_bytes",
              "max_blocks_per_page"}
    if set(history.client_bounds) != bounds or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in history.client_bounds.values()):
        raise ReleaseRefused("operating_release_invalid", "the release client bounds must be positive whole numbers")
    if history.client_bounds["max_response_bytes"] > limits["max_bytes"]:
        raise ReleaseRefused("operating_release_invalid", "one reply cannot exceed the collection byte limit")
    # The optional frozen recorder handoff (`provider_facts["forward_history_binding"]`). Its bytes are part of the
    # release content, so they enter the release SHA-256; a release without it keeps its hash.
    from edge_os_api.research import history_payload_binding  # deferred: that module imports this one

    history_payload_binding.check_definition(kind, history)


def _check_nansen(kind: ReleaseKind, nansen: NansenRelease, nansen_network: bool) -> None:
    _check_host(kind, nansen.endpoint)
    if kind == "STAND_IN" and nansen_network:
        raise ReleaseRefused("stand_in_endpoint_not_local", "a stand-in Nansen part cannot use the network transport")
    if kind == "ACTUAL" and nansen.endpoint != NANSEN_ORIGIN:
        raise ReleaseRefused("operating_release_invalid", f"an actual Nansen part must name {NANSEN_ORIGIN}")
    bounds = nansen.client_bounds
    if set(bounds) != {"connect_timeout_seconds", "max_request_bytes", "max_response_bytes"} or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in bounds.values()):
        raise ReleaseRefused("operating_release_invalid", "the Nansen client bounds must be positive whole numbers")
    max_bytes = nansen.limits.get("max_bytes")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or bounds["max_response_bytes"] > max_bytes:
        raise ReleaseRefused("operating_release_invalid", "one Nansen reply cannot exceed the report byte limit")


def check_release(release: OperatingRelease, *, network_transport: bool = False, nansen_network: bool = False) -> str:
    """Validate a release before any credential read or request. Returns its SHA-256.

    `network_transport` says whether the history transport is the accepted network `StdlibHttpTransport`;
    `nansen_network` whether the Nansen factory is the accepted network `NansenHttpTransport` with no test connector."""
    if release.kind not in ("STAND_IN", "ACTUAL"):  # the type hint is not enforced at runtime: fail closed
        raise ReleaseRefused("operating_release_invalid", "a release kind must be STAND_IN or ACTUAL")
    if release.history is None and release.nansen is None:
        raise ReleaseRefused("operating_release_invalid", "the release names no history source and no Nansen report")
    if release.history is not None:
        _check_history(release.kind, release.history)
    if release.nansen is not None:
        _check_nansen(release.kind, release.nansen, nansen_network)
    digest = release_sha256(release)
    if release.kind == "ACTUAL":
        if APPROVED_RELEASES.get(release.release_id) != digest:
            raise ReleaseRefused("operating_release_not_approved",
                                 "no recorded approval matches this exact actual release")
        if release.history is not None and not network_transport:
            raise ReleaseRefused("actual_release_needs_network_transport",
                                 "actual history needs the accepted network transport, not a recording")
        if release.nansen is not None and not nansen_network:
            raise ReleaseRefused("actual_nansen_transport_missing",
                                 "an actual Nansen part needs the accepted Nansen network transport")
    return digest
