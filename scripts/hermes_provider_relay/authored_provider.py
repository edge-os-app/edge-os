"""The AUTHORED provider behind the relay: HTTPS on 127.0.0.1 in the namespace it shares with the relay, a scripted
reply per attempt. Test support.

It is the only destination the relay can reach. For each request it appends a receipt (attempt, path, body hash and
size, header names, whether the bearer equals its expected synthetic key; never a header value or a body) and fsyncs it
BEFORE it answers, so its receipts are an independent count of what reached a provider. The reply comes from
`scripts/<attempt id>.json`, else `scripts/default.json`, in the accepted fake provider's script shape, plus the relay
faults: `lost_reply`, `oversized_reply`, `redirect`, `stream`. Standard library only.

Usage: python authored_provider.py <config.json>
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 1024 * 1024
_RECEIPT_LOCK = threading.Lock()


class AuthoredProvider(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.expected = Path(config["expected_key_file"]).read_text(encoding="utf-8").strip()
        super().__init__((config["bind"], config["port"]), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(config["cert"], config["key"])
        self.socket = context.wrap_socket(self.socket, server_side=True)

    def receipt(self, record: dict[str, Any]) -> None:
        path = Path(self.config["receipts"]) / "receipts.jsonl"
        with _RECEIPT_LOCK, path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def script(self, attempt: str | None) -> dict[str, Any]:
        folder = Path(self.config["scripts"])
        for name in ([f"{attempt}.json"] if attempt and attempt.replace("-", "").isalnum() else []) + ["default.json"]:
            if (folder / name).is_file():
                return json.loads((folder / name).read_text(encoding="utf-8"))
        return {"kind": "http_error", "status": 500, "message": "no authored script"}


class Handler(BaseHTTPRequestHandler):
    server: AuthoredProvider
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:  # no request line or header ever reaches a log
        pass

    def do_POST(self) -> None:  # noqa: N802 - the http.server name
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(min(length, MAX_BODY_BYTES))
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = {}
        session = parsed.get("session_id") if isinstance(parsed, dict) else None
        attempt = session[4:] if isinstance(session, str) and session.startswith("p05-") else None
        bearer = self.headers.get("authorization") or ""
        self.server.receipt({
            "attempt_id": attempt, "path": self.path, "method": "POST", "body_sha256": hashlib.sha256(body).hexdigest(),
            "body_bytes": len(body), "header_names": sorted({name.lower() for name in self.headers.keys()}),
            "bearer_matches": hmac.compare_digest(bearer.encode(), f"Bearer {self.server.expected}".encode()),
            "received_at": time.time()})
        if self.path != self.server.config["path"]:
            return self.reply(404, {"error": {"message": "not found", "type": "not_found"}})
        script = self.server.script(attempt)
        kind = script.get("kind")
        if kind == "hang":
            time.sleep(3600)
        if kind == "lost_reply":  # the provider did its work; the connection drops before any reply byte
            self.close_connection = True
            self.connection.close()
            return None
        if kind == "redirect":
            return self.reply(307, {"error": {"message": "moved"}}, {"location": "https://elsewhere.invalid/v1"})
        if kind == "http_error":
            return self.reply(script["status"], {"error": {"message": script["message"], "type": "server_error"}})
        completion: dict[str, Any] = {
            "id": "authored-completion-1", "object": "chat.completion", "created": 0, "model": parsed.get("model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": script["content"]},
                         "finish_reason": script["finish_reason"]}]}
        if script.get("usage") is not None:
            completion["usage"] = dict(script["usage"])
        if kind == "oversized_reply":
            completion["padding"] = " " * int(script.get("bytes", 2 * MAX_BODY_BYTES))
        content_type = "text/event-stream" if kind == "stream" else "application/json"
        encoding = {"content-encoding": "gzip"} if kind == "encoded" else {}  # declared, never applied: never decoded
        return self.reply(200, completion, {"content-type": content_type, **encoding})

    def reply(self, status: int, value: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        data = json.dumps(value).encode()
        self.send_response(status)
        for name, header in {"content-type": "application/json", **(headers or {})}.items():
            self.send_header(name, header)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> int:
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    server = AuthoredProvider(config)
    (Path(config["receipts"]) / "ready").write_text(str(os.getpid()), encoding="utf-8")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
