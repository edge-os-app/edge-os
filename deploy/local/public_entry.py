"""LOCAL rehearsal public entry: the one published loopback port in front of the private API and web services.

`/healthz`, `/readyz` and `/v1/...` go to the API; every other path goes to the web server. The browser therefore
uses one origin. This entry adds no authority: it never reads, adds or checks credentials, and it forwards the
caller's Authorization header unchanged. It is a LOCAL rehearsal component, not a production proxy or TLS endpoint.
Standard library only, so the API image needs no extra package.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import sys
import time
from collections.abc import Iterable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The API refuses bodies above 256 KiB itself; the entry refuses clearly larger ones before contacting it.
MAX_BODY_BYTES = 512 * 1024
# A refused body up to DRAIN_LIMIT_BYTES is read and discarded before the 413, so a client that sends its whole body
# first receives the refusal instead of a connection reset. The discard has one total deadline (not per read); a
# sender that stalls, drips or stops early is disconnected without a reply. A larger declared body is refused at once.
# These are LOCAL rehearsal bounds, not an accepted body size and not production hardening.
DRAIN_LIMIT_BYTES = 8 * 1024 * 1024
DRAIN_SECONDS = 5.0
DRAIN_CHUNK_BYTES = 64 * 1024
# A Content-Length longer than this is refused as invalid before conversion (far above any accepted size).
MAX_LENGTH_DIGITS = 19
# The longest API call (interpreter wait) is 120 s; the entry waits a little longer before reporting a loss.
UPSTREAM_TIMEOUT_SECONDS = 150.0
HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection",
                        "te", "trailer", "transfer-encoding", "upgrade"})
log = logging.getLogger("edge_os_public_entry")


def upstream_for(path: str) -> str:
    """Route by path only: `/healthz`, `/readyz` and `/v1` (and below it) are the API; everything else is web."""
    bare = path.split("?", 1)[0]
    if bare in {"/healthz", "/readyz", "/v1"} or bare.startswith("/v1/"):
        return "api"
    return "web"


def forwardable_headers(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop hop-by-hop headers and every header the Connection header names."""
    pairs = list(items)
    named = {token.strip().lower() for name, value in pairs if name.lower() == "connection"
             for token in value.split(",") if token.strip()}
    return [(name, value) for name, value in pairs if name.lower() not in HOP_BY_HOP | named]


def build_server(host: str, port: int, upstreams: Mapping[str, tuple[str, int]]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "edge-os-local-entry"
        sys_version = ""

        def _reply(self, status: int, payload: dict[str, str], *, close: bool = False) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _drain(self, length: int) -> bool:
            """Read and discard `length` body bytes within DRAIN_SECONDS in total; False on deadline or early end."""
            deadline = time.monotonic() + DRAIN_SECONDS
            previous = self.connection.gettimeout()
            try:
                while length > 0:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return False
                    self.connection.settimeout(left)  # no single read may wait past the total deadline
                    chunk = self.rfile.read1(min(length, DRAIN_CHUNK_BYTES))  # at most one socket read
                    if not chunk:
                        return False
                    length -= len(chunk)
                return True
            except OSError:  # TimeoutError at the deadline, or the sender reset the connection
                return False
            finally:
                self.connection.settimeout(previous)

        def _forward(self) -> None:
            if self.headers.get("Transfer-Encoding"):
                self._reply(411, {"status": "refused", "reason": "length_required"}, close=True)
                return
            declared = self.headers.get("Content-Length") or "0"
            # ASCII digits only (str.isdigit also accepts other scripts) and short enough for int(); else refuse.
            if not (declared.isascii() and declared.isdigit() and len(declared) <= MAX_LENGTH_DIGITS):
                self._reply(400, {"status": "refused", "reason": "invalid_length"}, close=True)
                return
            if int(declared) > MAX_BODY_BYTES:
                if int(declared) <= DRAIN_LIMIT_BYTES and not self._drain(int(declared)):
                    self.close_connection = True  # stalled, dripping or ended early: disconnect, no upstream, no reply
                    return
                self._reply(413, {"status": "refused", "reason": "body_too_large"}, close=True)
                return
            body = self.rfile.read(int(declared)) if int(declared) else None
            name = upstream_for(self.path)
            host_name, upstream_port = upstreams[name]
            connection = http.client.HTTPConnection(host_name, upstream_port, timeout=UPSTREAM_TIMEOUT_SECONDS)
            try:
                connection.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                for header, value in forwardable_headers(self.headers.items()):
                    connection.putheader(header, value)
                connection.endheaders(body)
                response = connection.getresponse()
                payload = response.read()
                status, reason, headers = response.status, response.reason, response.getheaders()
            except (OSError, http.client.HTTPException) as error:
                log.warning("upstream %s unavailable: %s", name, type(error).__name__)
                self._reply(502, {"status": "unavailable", "reason": "upstream_unavailable", "upstream": name})
                return
            finally:
                connection.close()
            self.send_response(status, reason)
            for header, value in forwardable_headers(headers):
                if header.lower() != "content-length":
                    self.send_header(header, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        do_GET = do_POST = do_HEAD = do_OPTIONS = do_PUT = do_PATCH = do_DELETE = _forward

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - BaseHTTPRequestHandler signature
            # Method, path without query and status only: no header, token or query value reaches the log.
            # A malformed request line is refused before `path` (and `command`) exist; log its status only.
            if format.startswith('"%s" %s'):
                path = getattr(self, "path", None)
                if path is None:
                    log.info("malformed request line refused (%s)", args[1] if len(args) > 1 else "")
                else:
                    log.info("%s %s", self.command, path.split("?", 1)[0])

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def _address(value: str) -> tuple[str, int]:
    host, _, port = value.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError("an upstream must be HOST:PORT")
    return host, int(port)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        upstreams = {"api": _address(os.environ["ENTRY_API_UPSTREAM"]),
                     "web": _address(os.environ["ENTRY_WEB_UPSTREAM"])}
        listen = _address(os.environ.get("ENTRY_LISTEN", "0.0.0.0:8080"))
    except (KeyError, ValueError) as error:
        sys.exit(f"edge-os-local-entry: invalid configuration ({type(error).__name__}: ENTRY_* variables)")
    server = build_server(listen[0], listen[1], upstreams)
    log.info("listening on port %d", listen[1])
    server.serve_forever()


if __name__ == "__main__":
    main()
