"""A hostile job entry for the relay tests: code inside the Hermes job that ignores its own guard. Test support only.

It runs in the same no-network job container as the real relay job, mounted under /opt/p05job. Its actions come from
the input's `provider_script.hostile`:

- `probe_key`: looks for any key file or key-like environment value it could read;
- `probe_egress`: tries to connect to the provider, the relay, a public address and the host;
- `message`: writes one raw channel message (the real attempt, route and release, changed as the test says, with a body
  the guard would admit unless `body_changes` alters it), waits for the relay's reply, then may repeat it (`repeat`).

It writes `hostile-result.json` and no `container-result.json`, so the host never treats its turn as a counted result.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
import time
from pathlib import Path

INPUT, OUTPUT = Path("/job/input.json"), Path("/job/output")
CHANNEL = OUTPUT / "relay-channel"
KEY_PATHS = ("/job/credential", "/relay/secrets/provider-key", "/provider/expected-key", "/relay/secrets/admission-key")


def probe_key() -> dict:
    readable = []
    for path in KEY_PATHS:
        try:
            Path(path).read_bytes()
            readable.append(path)
        except OSError:
            pass
    return {"readable_key_files": readable,
            "key_like_environment": sorted(name for name, value in os.environ.items() if "sk-" in value)}


def probe_egress(targets: list) -> list:
    results = []
    for host, port in targets:
        try:
            socket.create_connection((host, port), timeout=2).close()
            results.append({"host": host, "port": port, "connected": True})
        except OSError as error:
            results.append({"host": host, "port": port, "connected": False, "error": type(error).__name__})
    return results


def wire_body(job: dict, changes: dict) -> bytes:
    body = {"model": job["model"], "max_tokens": job["max_output_tokens"], "session_id": f"p05-{job['attempt_id']}",
            "messages": [{"role": "system", "content": job["system_prompt"]},
                         {"role": "user", "content": job["user_message"]}]}
    body.update(changes)
    return json.dumps(body).encode()


def send(message: dict, wait: float) -> dict | None:
    CHANNEL.mkdir(exist_ok=True)
    (CHANNEL / "reply.json").unlink(missing_ok=True)
    (CHANNEL / ".request.tmp").write_text(json.dumps(message), encoding="utf-8")
    os.replace(CHANNEL / ".request.tmp", CHANNEL / "request.json")
    until = time.monotonic() + wait
    while time.monotonic() < until:
        if (CHANNEL / "reply.json").exists():
            reply = json.loads((CHANNEL / "reply.json").read_text(encoding="utf-8"))
            reply.pop("body_b64", None)
            return reply
        time.sleep(0.05)
    return None


def main() -> int:
    job = json.loads(INPUT.read_text(encoding="utf-8"))
    hostile = job["provider_script"]["hostile"]
    settings = job["job_settings"]
    result: dict = {"attempt_id": job["attempt_id"]}
    if "probe_key" in hostile:
        result["key"] = probe_key()
    if "probe_egress" in hostile:
        result["egress"] = probe_egress(hostile["probe_egress"])
    if "message" in hostile:
        message = {"attempt_id": job["attempt_id"], "route_id": settings["transport"]["route"]["route_id"],
                   "release_id": settings["relay"]["release_id"],
                   "body_b64": base64.b64encode(wire_body(job, hostile.get("body_changes", {}))).decode()}
        message.update(hostile["message"])
        result["replies"] = [send(message, hostile.get("wait", 15))]
        for _ in range(hostile.get("repeat", 0)):
            result["replies"].append(send(message, hostile.get("repeat_wait", 3)))
    (OUTPUT / "hostile-result.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
