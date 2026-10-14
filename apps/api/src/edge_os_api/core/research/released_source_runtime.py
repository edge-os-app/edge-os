"""The composed runtime of one operating release: its transports and credential source (#58 RESEARCH-RUNTIME-LOCAL).

`open_released_runtime` validates the release and refuses a stand-in in production. It reads no credential and makes no
request. The application then uses the runtime in this order, per job: admission (the job's frozen release SHA-256
must equal this runtime's), `prepare_history` / `prepare_nansen` (the only credential reads), and only after the
original attempt is saved, the accepted P07 HTTP clients or the Nansen transport.

The evidence class comes from the release kind and the composed transport, never from a request: a stand-in release is
always `RELEASE_STAND_IN_RESPONSE` with a `SYNTHETIC_FIXTURE` profile; only an approved actual release over the
accepted network transport is `PROVIDER_ACTUAL`. Credentials are kept in memory for one job and are never saved,
returned or logged.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from edge_os_api.core.research.operating_release import (
    HistoryRelease,
    NansenRelease,
    OperatingRelease,
    ReleaseRefused,
    check_release,
    endpoint_host,
)
from edge_os_api.research_history.http_clients import (
    ClientBounds,
    ClientConfigError,
    HttpEnvioQueryClient,
    HttpQuickNodeRpcClient,
    HttpResponse,
    StdlibHttpTransport,
    validate_endpoint,
)
from edge_os_api.research_history.provider_transport import SourceTimeout

STAND_IN_CLASS = "RELEASE_STAND_IN_RESPONSE"
ACTUAL_CLASS = "PROVIDER_ACTUAL"
CLIENTS_LABEL = "P07_HTTP_CLIENTS_OPERATING_RELEASE"
STAND_IN_NOTICE = ("Stand-in responses served to the operating-release composition. Not provider, chain or market "
                   "evidence; no profitability, execution or statistical claim.")
NANSEN_STAND_IN_LABEL = "RELEASE_STAND_IN_NANSEN_TRANSPORT"
NANSEN_STAND_IN_NOTICE = ("Stand-in Nansen-shaped responses served to the operating-release composition. Not provider "
                          "data, not a market fact and not bounty evidence. Address counts are returned records; "
                          "amounts keep their raw text and unresolved units.")


class CredentialUnavailable(Exception):
    """The credential source holds no value for a slot. The message never carries a value."""


class CredentialSource(Protocol):
    def read(self, slot: str) -> str: ...


@dataclass(frozen=True)
class ReleasedSourceRuntime:
    release: OperatingRelease
    release_sha256: str
    credentials: CredentialSource
    http_transport: Callable[[], Any] | None
    nansen_transport: Callable[[NansenRelease, str], Any] | None
    network_transport: bool

    def __post_init__(self) -> None:
        """Every runtime is validated, however it is built: the composed parts must be present, the transport class
        must match `network_transport`, and the digest must be the release's own (review B2)."""
        if self.release.history is not None and self.http_transport is None:
            raise ReleaseRefused("operating_release_invalid", "a history release needs a composed HTTP transport")
        if self.release.nansen is not None and self.nansen_transport is None:
            raise ReleaseRefused("operating_release_invalid", "a Nansen release needs a composed Nansen transport")
        # Constructing a transport performs no I/O; its class decides whether it is the accepted network transport.
        network = self.http_transport is not None and isinstance(self.http_transport(), StdlibHttpTransport)
        if network != self.network_transport:
            raise ReleaseRefused("operating_release_invalid", "the transport class does not match the runtime")
        if check_release(self.release, network_transport=network) != self.release_sha256:
            raise ReleaseRefused("operating_release_invalid", "the runtime digest is not the release's own")

    @property
    def evidence_class(self) -> str:
        return ACTUAL_CLASS if self.release.kind == "ACTUAL" else STAND_IN_CLASS

    @property
    def transport_kind(self) -> str:
        if self.release.kind == "ACTUAL":
            return "PROVIDER_HTTP"
        return "LOOPBACK_HTTP" if self.network_transport else "IN_PROCESS_RECORDING"

    def __repr__(self) -> str:  # never show the credential source
        return f"ReleasedSourceRuntime({self.release.release_id}, {self.release.kind}, {self.release_sha256[:12]})"


def open_released_runtime(settings: Any, release: OperatingRelease, *, credentials: CredentialSource,
                          http_transport: Callable[[], Any] | None = None,
                          nansen_transport: Callable[[NansenRelease, str], Any] | None = None) -> ReleasedSourceRuntime:
    """Validate and compose. No credential read, no request. Raises `ReleaseRefused`."""
    if release.kind == "STAND_IN" and settings.env == "production":
        raise ReleaseRefused("stand_in_refused_in_production", "a stand-in release is local and test only")
    if release.history is not None and http_transport is None:
        raise ReleaseRefused("operating_release_invalid", "a history release needs a composed HTTP transport")
    network = http_transport is not None and isinstance(http_transport(), StdlibHttpTransport)
    digest = check_release(release, network_transport=network)
    return ReleasedSourceRuntime(release, digest, credentials, http_transport, nansen_transport, network)


def release_view(runtime: ReleasedSourceRuntime) -> dict[str, Any]:
    """What a user reviews before declaring: identity, kind, fixed limits and endpoint hosts. Never a credential."""
    view: dict[str, Any] = {"release_id": runtime.release.release_id, "sha256": runtime.release_sha256,
                            "kind": runtime.release.kind, "evidence_class": runtime.evidence_class,
                            "transport_kind": runtime.transport_kind}
    history = runtime.release.history
    if history is not None:
        view["history"] = {"source_id": history.source_id, "source_version": history.source_version,
                           "limits": dict(history.limits), "client_bounds": dict(history.client_bounds),
                           "endpoint_hosts": {"ENVIO_HYPERSYNC": endpoint_host(history.envio_endpoint),
                                              "QUICKNODE_JSON_RPC": history.quicknode_host},
                           "time_basis": dict(history.time_basis), "required_coverage": history.required_coverage}
    nansen = runtime.release.nansen
    if nansen is not None:
        view["nansen"] = {**nansen_request(nansen), "endpoint_host": endpoint_host(nansen.endpoint)}
    return view


# --------------------------------------------------------------------------------------------- history

def history_source(runtime: ReleasedSourceRuntime) -> dict[str, Any]:
    """The release history source in the shape the catalog, the declaration check and the collector already use."""
    history = runtime.release.history
    assert history is not None
    stand_in = runtime.release.kind == "STAND_IN"
    profile = {**history.profile, "evidence_class": "SYNTHETIC_FIXTURE" if stand_in else ACTUAL_CLASS}
    return {"source_id": history.source_id, "title": history.title, "evidence_class": runtime.evidence_class,
            "content_label": "SYNTHETIC_FIXTURE" if stand_in else "PROVIDER_HISTORY",
            "profile": profile, "scan": dict(history.scan), "provider_facts": dict(history.provider_facts),
            "corroboration_sample_size": history.corroboration_sample_size,
            "release": release_view(runtime)}


def _basis(runtime: ReleasedSourceRuntime) -> dict[str, str]:
    served = "STAND_IN" if runtime.release.kind == "STAND_IN" else "PROVIDER"
    declared = "RELEASE_DECLARATION"
    return {"history_pages": f"ENVIO_TRANSPORT_OVER_{served}_RESPONSES", "chain_id": f"CHECKED_AGAINST_{served}_RPC",
            "corroboration": f"COMPUTED_FROM_{served}_RPC", "decimals": declared, "pool_tokens": declared,
            "pool_venue": declared, "fee_transfer_semantics": declared, "finality_at_collection": declared,
            "delivery_records": declared, "feasibility_claim": declared}


class HashingTransport:
    """Wraps the composed `HttpTransport`. Keeps the SHA-256 of every request body and reply body and each reply
    status, index-aligned; never a header, URL or body. A request without a reply has None status and reply hash.

    It also bounds EVERY physical request by the original job deadline (review A F1 / B B3): a request is not sent
    once the job deadline has passed, each sent request's whole-call deadline is at most the job deadline, and a
    reply that arrives after it is treated as incomplete (`SourceTimeout`), so its possible effect stays unknown."""

    def __init__(self, inner: Any, runtime: ReleasedSourceRuntime, job_deadline: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._inner, self._job_deadline, self._clock = inner, job_deadline, clock
        self.label = f"RELEASE_{runtime.transport_kind}_TRANSPORT"
        self.clients_label = CLIENTS_LABEL
        self.evidence_basis = _basis(runtime)
        self.request_sha256: list[str] = []
        self.response_sha256: list[str] = []
        self.response_status: list[int | None] = []

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float,
                deadline: float, max_response_bytes: int, cancel: Callable[[], bool] | None = None) -> HttpResponse:
        if self._clock() >= self._job_deadline:
            raise SourceTimeout("the job deadline passed before the next request; it was not sent")
        self.request_sha256.append(hashlib.sha256(body).hexdigest())
        try:
            reply = self._inner.request(method=method, url=url, headers=headers, body=body, timeout=timeout,
                                        deadline=min(deadline, self._job_deadline),
                                        max_response_bytes=max_response_bytes, cancel=cancel)
        except BaseException:
            self.response_status.append(None)
            self.response_sha256.append(None)
            raise
        self.response_status.append(reply.status)
        self.response_sha256.append(hashlib.sha256(reply.body).hexdigest())
        if self._clock() >= self._job_deadline:
            raise SourceTimeout("the reply arrived after the job deadline")
        return reply

    def facts(self) -> dict[str, Any]:
        return {"request_sha256": list(self.request_sha256), "response_status": list(self.response_status)}


class PreparedHistory:
    """Credentials read for one job. Builds the accepted P07 HTTP clients after the original attempt is saved."""

    def __init__(self, runtime: ReleasedSourceRuntime, bearer: str, quicknode_url: str) -> None:
        self._runtime, self._bearer, self._quicknode_url = runtime, bearer, quicknode_url

    def __repr__(self) -> str:
        return f"PreparedHistory({self._runtime.release.release_id})"

    def clients(self, seconds_left: float, cancelled: Callable[[], bool],
                clock: Callable[[], float] = time.monotonic,
                anchor: float | None = None) -> tuple[Any, Any, HashingTransport]:
        history = self._runtime.release.history
        assert history is not None and self._runtime.http_transport is not None
        fixed = history.client_bounds
        # `seconds_left` must be measured now, from the job's saved deadline (see `investigation_jobs.release_http_clients`).
        # The client bound is at most that time; the transport then bounds each later request by the same anchored
        # deadline, so no admitted call or late reply outlives the job.
        job_deadline = (clock() if anchor is None else anchor) + seconds_left
        deadline = max(0.001, min(float(fixed["deadline_seconds"]), seconds_left))
        bounds = ClientBounds(deadline_seconds=deadline,
                              connect_timeout_seconds=min(float(fixed["connect_timeout_seconds"]), deadline),
                              max_response_bytes=int(fixed["max_response_bytes"]),
                              max_request_bytes=int(fixed["max_request_bytes"]),
                              max_blocks_per_page=int(fixed["max_blocks_per_page"]))
        transport = HashingTransport(self._runtime.http_transport(), self._runtime, job_deadline, clock)
        envio = HttpEnvioQueryClient(endpoint=history.envio_endpoint, bearer_token=self._bearer, transport=transport,
                                     bounds=bounds, clock=clock, cancel=cancelled)
        quicknode = HttpQuickNodeRpcClient(endpoint=self._quicknode_url, transport=transport, bounds=bounds,
                                           allowed_methods=history.rpc_methods, clock=clock, cancel=cancelled)
        return envio, quicknode, transport


def _read(runtime: ReleasedSourceRuntime, slot: str) -> str:
    try:
        value = runtime.credentials.read(slot)
    except Exception:  # noqa: BLE001 - any credential-source failure is one stable refusal; its detail may be secret
        value = ""
    if not isinstance(value, str) or not value.strip():
        raise ReleaseRefused("operating_release_credential_unavailable",
                             "a credential the release needs is not available; nothing was sent")
    return value


def prepare_history(runtime: ReleasedSourceRuntime) -> PreparedHistory:
    """Read the history credentials and check the QuickNode URL host. Raises `ReleaseRefused`; sends nothing."""
    history: HistoryRelease | None = runtime.release.history
    assert history is not None
    bearer = _read(runtime, history.envio_credential_slot)
    quicknode_url = _read(runtime, history.quicknode_credential_slot)
    try:
        parts = urlsplit(quicknode_url)
        host = parts.hostname
    except ValueError:
        host = None
    if host != history.quicknode_host or (runtime.release.kind == "ACTUAL" and parts.scheme != "https"):
        raise ReleaseRefused("operating_release_endpoint_mismatch",
                             "the QuickNode endpoint is not on the release's host; nothing was sent")
    try:  # the accepted client's own endpoint rules, checked before the attempt is saved (review B4)
        validate_endpoint(quicknode_url)
    except ClientConfigError:
        raise ReleaseRefused("operating_release_endpoint_mismatch",
                             "the QuickNode endpoint is not a valid release endpoint; nothing was sent") from None
    return PreparedHistory(runtime, bearer, quicknode_url)


# --------------------------------------------------------------------------------------------- Nansen

def nansen_request(nansen: NansenRelease) -> dict[str, Any]:
    """The one report request the release permits, in the `NansenReportBody` field shape."""
    return {"token_address": nansen.token_address, "token_symbol": nansen.token_symbol, "window": dict(nansen.window),
            "operations": list(nansen.operations), "holder_query": dict(nansen.holder_query),
            "flow_query": dict(nansen.flow_query), "limits": dict(nansen.limits),
            "deadline_seconds": nansen.deadline_seconds, "compute_seconds": nansen.compute_seconds}


def nansen_mismatches(runtime: ReleasedSourceRuntime, body: Mapping[str, Any]) -> list[str]:
    """Body fields that differ from the release's fixed request. The owner cannot widen any of them."""
    nansen = runtime.release.nansen
    assert nansen is not None
    fixed = nansen_request(nansen)
    return [f"/{name}" for name, value in fixed.items() if body.get(name) != value]


def prepare_nansen(runtime: ReleasedSourceRuntime) -> Any:
    """Read the Nansen credential and build the composed transport for one job. Sends nothing."""
    nansen = runtime.release.nansen
    assert nansen is not None and runtime.nansen_transport is not None
    return runtime.nansen_transport(nansen, _read(runtime, nansen.credential_slot))
