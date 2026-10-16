"""Stand-in releases and stand-in providers for the operating-release composition (#58 RESEARCH-RUNTIME-LOCAL).

Everything here is SYNTHETIC and local. A stand-in release is built from one SOURCE-LOCAL native recording
(`native_history_v1.json`) and points only at `.invalid` or loopback hosts. Two stand-in providers serve it:

- `RecordingStandIn`: an in-process `HttpTransport` over the recording.
- `LoopbackStandInProvider`: an owned HTTP server on 127.0.0.1, reached through the accepted `StdlibHttpTransport`.
  It writes one JSON line per request it receives to its own log, so a test or the verifier counts provider requests
  outside the application.

Nansen has the same two kinds: `StandInNansen` (in process) and `LoopbackStandInNansen`, an owned 127.0.0.1 server
reached through the accepted `NansenHttpTransport` and `StdlibHttpTransport`; only an injected connector moves the fixed
`https://api.nansen.ai` origin to the loopback port, so it is never the network factory.

Both check the stand-in credentials, so a request only succeeds when the application read them from the composed
credential source. The credential values are sentinels a leak scan looks for; they are not secrets.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import threading
import time
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from edge_os_api.core.research import provider_composition
from edge_os_api.core.research.operating_release import HistoryRelease, NansenRelease, OperatingRelease
from edge_os_api.core.research.released_source_runtime import (
    CredentialUnavailable,
    NansenHttpFactory,
    ReleasedSourceRuntime,
    open_released_runtime,
)
from edge_os_api.nansen_research import NansenResponse
from edge_os_api.research import history_dataset
from edge_os_api.research_history.http_clients import HttpResponse, StdlibHttpTransport
from edge_os_api.research_history.provider_transport import SourceTimeout

ENVIO_SLOT, QUICKNODE_SLOT, NANSEN_SLOT = "STAND_IN_ENVIO_BEARER", "STAND_IN_QUICKNODE_URL", "STAND_IN_NANSEN_KEY"
BEARER = "stand-in-bearer-SENTINEL-7d41c0"
QUICKNODE_KEY_PATH = "/stand-in-key-SENTINEL-55e0a1/"
NANSEN_KEY = "stand-in-nansen-SENTINEL-2b9c44"
SENTINELS = (BEARER, QUICKNODE_KEY_PATH.strip("/"), NANSEN_KEY)
INVALID_ENVIO = "https://hypersync.stand-in.invalid"
INVALID_QUICKNODE_HOST = "quicknode.stand-in.invalid"
SOURCE_ID = "release-stand-in/1"
TOKEN = "0xd8e004acba279417c04c0633cb5a21ceca207777"


def recording(recording_id: str = "native-syn-qualified/1") -> dict[str, Any]:
    bundle = json.loads(history_dataset.NATIVE_BUNDLE_PATH.read_text(encoding="utf-8"))
    return next(source for source in bundle["sources"] if source["source_id"] == recording_id)


def limits_for(source: Mapping[str, Any]) -> dict[str, int]:
    pages = len(source["envio_pages"])
    return {"provider_requests": pages + 1 + int(source["corroboration_sample_size"]), "compute_seconds": 30,
            "max_pages": pages, "max_rows": 200, "max_bytes": 1_048_576, "deadline_seconds": 600}


def nansen_part(endpoint: str = "https://nansen.stand-in.invalid") -> NansenRelease:
    return NansenRelease(
        endpoint=endpoint, credential_slot=NANSEN_SLOT, token_address=TOKEN, token_symbol="MOE",
        window={"start_utc": "2026-10-06T09:44:14Z", "end_utc": "2026-10-07T09:44:14Z"},
        operations=("holders", "flows"),
        holder_query={"label_type": "all_holders", "aggregate_by_entity": False, "order_field": "token_amount",
                      "value_usd_min": None},
        flow_query={"label": "top_100_holders"},
        limits={"max_requests": 4, "max_pages": 2, "max_bytes": 200000, "max_credits": "12", "per_page": 100},
        deadline_seconds=600, compute_seconds=30,
        client_bounds={"connect_timeout_seconds": 15, "max_request_bytes": 65_536, "max_response_bytes": 200_000})


def stand_in_release(recording_id: str = "native-syn-qualified/1", *, release_id: str = "stand-in-native/1",
                     envio_endpoint: str = INVALID_ENVIO, quicknode_host: str = INVALID_QUICKNODE_HOST,
                     source_id: str = SOURCE_ID, history: bool = True, nansen: bool = True,
                     nansen_endpoint: str = "https://nansen.stand-in.invalid",
                     limits: Mapping[str, int] | None = None) -> OperatingRelease:
    source = recording(recording_id)
    scan = source["scan"]
    part = HistoryRelease(
        source_id=source_id, title=f"Stand-in release over {recording_id} (not provider data)",
        envio_endpoint=envio_endpoint, envio_credential_slot=ENVIO_SLOT, quicknode_host=quicknode_host,
        quicknode_credential_slot=QUICKNODE_SLOT, profile=source["profile"], scan=scan,
        corroboration_sample_size=int(source["corroboration_sample_size"]), provider_facts=source["provider_facts"],
        limits=dict(limits or limits_for(source)),
        client_bounds={"deadline_seconds": 120, "connect_timeout_seconds": 15, "max_response_bytes": 1_048_576,
                       "max_request_bytes": 65_536,
                       "max_blocks_per_page": int(scan["to_block_exclusive"]) - int(scan["from_block"])})
    return OperatingRelease(release_id=release_id, kind="STAND_IN", history=part if history else None,
                            nansen=nansen_part(nansen_endpoint) if nansen else None)


def quicknode_url(host: str = INVALID_QUICKNODE_HOST, scheme: str = "https", port: int | None = None) -> str:
    return f"{scheme}://{host}{'' if port is None else f':{port}'}{QUICKNODE_KEY_PATH}"


class StandInCredentials:
    """The composed credential source. `reads` lists the slots read, in order; values are never listed."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.reads: list[str] = []

    def read(self, slot: str) -> str:
        self.reads.append(slot)
        if slot not in self._values:
            raise CredentialUnavailable(slot)
        return self._values[slot]


def credentials(*, quicknode: str | None = None, missing: tuple[str, ...] = ()) -> StandInCredentials:
    values = {ENVIO_SLOT: BEARER, QUICKNODE_SLOT: quicknode or quicknode_url(), NANSEN_SLOT: NANSEN_KEY}
    return StandInCredentials({key: value for key, value in values.items() if key not in missing})


# ---------------------------------------------------------------------------------------- stand-in replies

class StandInReplies:
    """Answers one HyperSync query or one JSON-RPC call from the recording, statelessly.

    Pages are chosen by the request's `from_block`, so a fresh job or a restarted process reads the same page. A
    recorded `SOURCE_FAILURE` page is an HTTP 503; a `SOURCE_TIMEOUT` page is a timeout. A request without the stand-in
    bearer is a 401, so only a request made with the composed credential succeeds."""

    def __init__(self, source: Mapping[str, Any]) -> None:
        pages = source["envio_pages"]
        starts = [int(source["scan"]["from_block"])]
        for page in pages[:-1]:
            starts.append(int(str(page.get("next_block")), 16) if isinstance(page.get("next_block"), str)
                          else int(page.get("next_block") or -1))
        self._pages = dict(zip(starts, pages))
        self._rpc = source["quicknode"]

    def envio(self, headers: Mapping[str, str], body: bytes) -> tuple[int, Any]:
        if headers.get("authorization") != f"Bearer {BEARER}":
            return 401, {"error": "stand-in: not authorized"}
        page = self._pages.get(int(json.loads(body)["from_block"]))
        if page is None:
            return 200, {"archive_height": None, "next_block": None, "data": []}
        if page.get("fault") == "SOURCE_FAILURE":
            return 503, {"error": "stand-in provider failure"}
        if page.get("fault") == "SOURCE_TIMEOUT":
            raise SourceTimeout("stand-in provider timeout")
        return 200, page

    def rpc(self, body: bytes) -> tuple[int, Any]:
        call = json.loads(body)
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": call.get("id")}
        if call.get("method") == "eth_chainId":
            reply["result"] = self._rpc["eth_chainId"]
        elif call.get("method") == "eth_getTransactionReceipt":
            tx_hash = (call.get("params") or [None])[0]
            if self._rpc.get("rpc_faults", {}).get(tx_hash) == "RPC_FAILED":
                reply["error"] = {"code": -32000, "message": "stand-in RPC failure"}
            else:
                reply["result"] = self._rpc["receipts"].get(tx_hash)
        else:
            reply["error"] = {"code": -32601, "message": "method not found"}
        return 200, reply


class RecordingStandIn:
    """In-process stand-in provider. `transport()` gives a fresh `HttpTransport` per job; `requests` counts every
    request any of them received, outside the application."""

    def __init__(self, recording_id: str = "native-syn-qualified/1", *, envio_endpoint: str = INVALID_ENVIO,
                 quicknode: str | None = None) -> None:
        self.replies = StandInReplies(recording(recording_id))
        self.envio_url = envio_endpoint.rstrip("/") + "/query"
        self.quicknode_url = quicknode or quicknode_url()
        self.requests: list[dict[str, Any]] = []
        self.fault: Any = None  # optional callable(index, request) -> HttpResponse | None, or raises

    def transport(self) -> "RecordingStandInTransport":
        return RecordingStandInTransport(self)


class RecordingStandInTransport:
    def __init__(self, provider: RecordingStandIn) -> None:
        self._provider = provider

    def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float,
                deadline: float, max_response_bytes: int, cancel: Any = None) -> HttpResponse:
        provider = self._provider
        kind = "envio" if url == provider.envio_url else "rpc" if url == provider.quicknode_url else "other"
        provider.requests.append({"kind": kind, "body_sha256": hashlib.sha256(body).hexdigest()})
        if provider.fault is not None:
            injected = provider.fault(len(provider.requests), kind)
            if injected is not None:
                return injected
        if method != "POST" or kind == "other":
            status, payload = 404, {"error": "not found"}
        elif kind == "envio":
            status, payload = provider.replies.envio({k.lower(): v for k, v in headers.items()}, body)
        else:
            status, payload = provider.replies.rpc(body)
        return HttpResponse(status=status, headers={"content-type": "application/json"},
                            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"))


class LoopbackStandInProvider:
    """An owned HTTP server on 127.0.0.1 that serves the recording. Each request appends one JSON line to `log_path`:
    the request kind, whether the stand-in credential was present, and the body SHA-256. Nothing else is kept."""

    def __init__(self, recording_id: str, log_path: Path, *, port: int = 0) -> None:
        replies = StandInReplies(recording(recording_id))
        lock = threading.Lock()
        self.log_path = log_path

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server naming
                body = self.rfile.read(int(self.headers.get("content-length") or 0))
                headers = {key.lower(): value for key, value in self.headers.items()}
                if self.path == "/query":
                    kind, authorized = "envio", headers.get("authorization") == f"Bearer {BEARER}"
                    try:
                        status, payload = replies.envio(headers, body)
                    except SourceTimeout:
                        status, payload = 504, {"error": "stand-in timeout"}
                elif self.path == QUICKNODE_KEY_PATH:
                    kind, authorized = "rpc", True
                    status, payload = replies.rpc(body)
                else:
                    kind, authorized, status, payload = "other", False, 404, {"error": "not found"}
                with lock, open(log_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"kind": kind, "authorized": authorized, "status": status,
                                             "body_sha256": hashlib.sha256(body).hexdigest()}) + "\n")
                data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 - readiness only; not a provider request and not logged
                self.send_response(200 if self.path == "/ready" else 404)
                self.send_header("content-length", "0")
                self.end_headers()

            def log_message(self, *args: Any) -> None:  # requests are logged above, without headers
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def envio_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def quicknode_url(self) -> str:
        return quicknode_url("127.0.0.1", "http", self.port)

    def start(self) -> "LoopbackStandInProvider":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def entries(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------------------- Nansen stand-in

class StandInNansen:
    """In-process stand-in Nansen provider over the authored fixture. A request made without the stand-in key gets a
    401 reply. `requests` counts every request, outside the application; `bounds` keeps the per-job bounds the
    application passed to the factory."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.bounds: list[dict[str, Any]] = []

    def transport(self, release: NansenRelease, key: str, **bounds: Any) -> "StandInNansenTransport":
        self.bounds.append(bounds)
        return StandInNansenTransport(self, release, key)


class StandInNansenTransport:
    def __init__(self, provider: StandInNansen, release: NansenRelease, key: str) -> None:
        self._provider, self._key = provider, key
        self._inner = provider_composition.AuthoredNansenTransport(release.token_address)
        self.response_sha256 = self._inner.response_sha256

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse:
        self._provider.requests.append(operation)
        if self._key != NANSEN_KEY:
            return NansenResponse(status=401, headers={}, body=b'{"error":"stand-in: not authorized"}')
        return self._inner.request(operation, path, body)


class LoopbackStandInNansen:
    """An owned HTTP server on 127.0.0.1 that answers the two pinned Nansen routes from the authored fixture.

    A request without the stand-in key gets a 401. Each request appends one JSON line to `log_path`: the operation,
    whether the stand-in key was present, the status and the body SHA-256; never a header value. `fault`, when set, is
    called with (request index from 1, operation) and may return `{"delay": seconds}` (sleep, then answer),
    `{"drop": True}` (close without a reply) or `{"status", "headers", "body"}` (answer that instead)."""

    ROUTES = {"/api/v1/tgm/holders": "holders", "/api/v1/tgm/flows": "flows"}

    def __init__(self, log_path: Path, *, port: int = 0) -> None:
        lock = threading.Lock()
        self.log_path = log_path
        self.fault: Callable[[int, str], Mapping[str, Any] | None] | None = None
        self.targets: list[tuple[str, str, int | None]] = []
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server naming
                body = self.rfile.read(int(self.headers.get("content-length") or 0))
                operation = provider.ROUTES.get(self.path, "other")
                authorized = self.headers.get("apikey") == NANSEN_KEY
                with lock:
                    index = len(provider.entries()) + 1
                    fault = provider.fault(index, operation) if provider.fault is not None else None
                    dropped = bool(fault and fault.get("drop"))
                    status, headers, data = (0, {}, b"") if dropped else provider._answer(operation, authorized,
                                                                                          body, fault)
                    with open(log_path, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps({"operation": operation, "authorized": authorized, "status": status,
                                                 "body_sha256": hashlib.sha256(body).hexdigest()}) + "\n")
                if fault and fault.get("delay"):
                    time.sleep(float(fault["delay"]))
                if dropped:
                    self.close_connection = True
                    return
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 - readiness only; not a provider request and not logged
                self.send_response(200 if self.path == "/ready" else 404)
                self.send_header("content-length", "0")
                self.end_headers()

            def log_message(self, *args: Any) -> None:  # requests are logged above, without headers
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _answer(operation: str, authorized: bool, body: bytes,
                fault: Mapping[str, Any] | None) -> tuple[int, dict[str, str], bytes]:
        if fault and "status" in fault:
            return int(fault["status"]), dict(fault.get("headers") or {}), bytes(fault.get("body") or b"{}")
        if operation == "other":
            return 404, {"content-type": "application/json"}, b'{"code":"not_found"}'
        if not authorized:
            return 401, {"content-type": "application/json"}, b'{"code":"unauthenticated"}'
        reply = provider_composition.AuthoredNansenTransport(TOKEN).request(operation, "", json.loads(body))
        return reply.status, {"content-type": "application/json", **reply.headers}, reply.body

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def connector(self) -> Callable[..., http.client.HTTPConnection]:
        """Moves the adapter's fixed origin to this server and records each requested target."""
        return nansen_loopback_connector(self.port, self.targets)

    def start(self) -> "LoopbackStandInNansen":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def entries(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line]


def nansen_loopback_connector(port: int, targets: list[tuple[str, str, int | None]] | None = None,
                              ) -> Callable[..., http.client.HTTPConnection]:
    """A test connector for `NansenHttpFactory`: every connection goes to the loopback stand-in on `port`."""
    def connect(scheme: str, host: str, port_: int | None, timeout: float) -> http.client.HTTPConnection:
        if targets is not None:
            targets.append((scheme, host, port_))
        return http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    return connect


# ---------------------------------------------------------------------------------------- runtimes

def recording_runtime(settings: Any, *, recording_id: str = "native-syn-qualified/1",
                      release: OperatingRelease | None = None, creds: StandInCredentials | None = None,
                      provider: RecordingStandIn | None = None, nansen: StandInNansen | None = None,
                      ) -> tuple[ReleasedSourceRuntime, RecordingStandIn, StandInNansen, StandInCredentials]:
    release = release or stand_in_release(recording_id)
    provider = provider or RecordingStandIn(recording_id)
    nansen = nansen or StandInNansen()
    creds = creds or credentials()
    runtime = open_released_runtime(settings, release, credentials=creds,
                                    http_transport=provider.transport if release.history else None,
                                    nansen_transport=nansen.transport if release.nansen else None)
    return runtime, provider, nansen, creds


def loopback_runtime(settings: Any, provider: LoopbackStandInProvider, *, recording_id: str = "native-syn-qualified/1",
                     release_id: str = "stand-in-loopback/1", creds: StandInCredentials | None = None,
                     ) -> tuple[ReleasedSourceRuntime, StandInCredentials]:
    """A stand-in release whose history transport is the accepted network transport, reaching only the loopback
    stand-in provider."""
    return loopback_runtime_at(settings, provider.port, recording_id=recording_id, release_id=release_id, creds=creds)


def loopback_runtime_at(settings: Any, port: int, *, recording_id: str = "native-syn-qualified/1",
                        release_id: str = "stand-in-loopback/1", creds: StandInCredentials | None = None,
                        missing: tuple[str, ...] = (), nansen_port: int | None = None,
                        ) -> tuple[ReleasedSourceRuntime, StandInCredentials]:
    """The same runtime for a stand-in provider already listening on `port` (the verifier runs it as its own process).

    With `nansen_port`, the release also has a Nansen part served by a `LoopbackStandInNansen` on that port through
    the accepted `NansenHttpTransport` and a loopback connector."""
    release = stand_in_release(recording_id, release_id=release_id, envio_endpoint=f"http://127.0.0.1:{port}",
                               quicknode_host="127.0.0.1", nansen=nansen_port is not None,
                               nansen_endpoint=f"http://127.0.0.1:{nansen_port}")
    creds = creds or credentials(quicknode=quicknode_url("127.0.0.1", "http", port), missing=missing)
    nansen = None if nansen_port is None else NansenHttpFactory(connect=nansen_loopback_connector(nansen_port))
    return open_released_runtime(settings, release, credentials=creds, http_transport=StdlibHttpTransport,
                                 nansen_transport=nansen), creds


def nansen_loopback_runtime(settings: Any, provider: LoopbackStandInNansen, *,
                            release_id: str = "stand-in-nansen-loopback/1", creds: StandInCredentials | None = None,
                            ) -> tuple[ReleasedSourceRuntime, StandInCredentials]:
    """A stand-in Nansen-only release over the accepted `NansenHttpTransport`, reaching only the loopback stand-in."""
    release = stand_in_release(release_id=release_id, history=False, nansen_endpoint=f"http://127.0.0.1:{provider.port}")
    creds = creds or credentials()
    return open_released_runtime(settings, release, credentials=creds,
                                 nansen_transport=NansenHttpFactory(connect=provider.connector())), creds
