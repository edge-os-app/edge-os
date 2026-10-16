"""Container entrypoint: one ACTUAL pinned-Hermes turn whose one request leaves only through the relay channel.

It reuses the accepted P05 job (`hermes_turn_job`, inside the image), the accepted physical admission and provider
guard, and the accepted reply bounds. The job has no network and no credential: nothing is mounted at /job/credential
and Hermes' client keeps the placeholder key. An admitted request is handed to `ChannelTransport`, which writes it into
this job's own output folder for the relay. A request the relay refused before sending gets a 429 and counts as not
sent; a lost reply raises; a refused reply gets a 502 and its content is dropped.

The host mounts this file, `relay_job_channel.py` and the accepted `provider_transport.py` read-only under /opt/p05job.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, "/opt/p05")
sys.path.insert(0, "/opt/p05guard")
sys.path.insert(0, "/opt/p05job")

import hermes_turn_job as base  # noqa: E402  (the accepted job, inside the image)
from provider_guard import GuardPolicy, LogicalRequest, ProviderRequestGuard  # noqa: E402
from provider_transport import (  # noqa: E402
    HERMES_CLIENT_KEY, ActualProviderUnavailable, PhysicalRequest, TransportRoute, host_request, physical_refusal,
    reply_refusal,
)
from relay_job_channel import ChannelTransport, RelayRefused, RelayReplyRefused  # noqa: E402

CREDENTIAL = Path("/job/credential")
MAX_EVIDENCE = 16
PROVIDERS: list[RelayProvider] = []
NOT_ADMITTED = {"error": {"message": "request not admitted", "type": "request_not_admitted"}}


class RelayProvider(base.FakeProvider):
    """What Hermes' HTTP client calls. Admitted requests go to the relay; no provider runs inside this job."""

    def __init__(self, job: dict[str, Any]) -> None:
        super().__init__(job)
        settings = job["job_settings"]
        self.route = TransportRoute.from_settings(settings["transport"]["route"])
        self.client_url, self.attempt_id = settings["transport"]["client_url"], job["attempt_id"]
        if self.route.kind not in ("AUTHORED", "ACTUAL"):  # either way the job is keyless with no network (A6)
            raise ActualProviderUnavailable("unknown route kind")
        self.guard = ProviderRequestGuard(GuardPolicy(**job["guard"]["policy"]),
                                          LogicalRequest(job["system_prompt"], job["user_message"]), HERMES_CLIENT_KEY)
        self.transport = ChannelTransport(self.route, settings["relay"]["release_id"])
        self.sent: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        PROVIDERS.append(self)

    def __call__(self, request):
        import httpx

        headers = tuple((name.lower(), value) for name, value in request.headers.multi_items())
        physical = PhysicalRequest(request.method, str(request.url), headers, request.content)
        refusal = physical_refusal(physical, self.attempt_id, self.client_url)
        if refusal is None:
            decision = self.guard.admit(request.content, dict(headers))
            refusal = None if decision.admitted else f"guard:{decision.reason}"
        if refusal is not None:
            self.note(refusal)
            return httpx.Response(429, json=NOT_ADMITTED, request=request)
        self.receipt(request.content)
        sent = host_request(physical, self.route, self.attempt_id, None)  # no credential: the relay holds the key
        try:
            reply = self.transport.send(sent)
        except RelayRefused as refused:  # nothing left the relay
            self.note(f"relay:{refused}")
            return httpx.Response(429, json=NOT_ADMITTED, request=request)
        except RelayReplyRefused as refused:
            self.count_sent(sent)
            self.note(str(refused))
            return httpx.Response(502, json={"error": {"message": "reply not admitted", "type": str(refused)}},
                                  request=request)
        except Exception as error:  # noqa: BLE001 - whatever failed, the request may have reached the provider
            self.count_sent(sent)
            self.note(f"reply_lost:{type(error).__name__}")
            raise httpx.ReadError("the provider reply was lost", request=request) from None
        self.count_sent(sent)
        refused = reply_refusal(reply, self.route)
        self.note(refused, reply_status=reply.status, reply_bytes=len(reply.body))
        if refused is not None:
            return httpx.Response(502, json={"error": {"message": "reply not admitted", "type": refused}}, request=request)
        self.remember(reply.status, reply.body)
        return httpx.Response(reply.status, content=reply.body, headers={"content-type": "application/json"},
                              request=request)

    def receipt(self, raw: bytes) -> None:
        """The job's own copy of what it handed over, like the accepted fake provider's (its wire_* fields)."""
        body = json.loads(raw)
        self.requests_seen += 1
        base.write_json(base.OUTPUT / "requests" / f"request-{self.requests_seen}.json", body)
        messages, text = body.get("messages", []), raw.decode("utf-8")
        system = str(messages[0].get("content", "")) if messages else ""
        self.first_receipt = getattr(self, "first_receipt", None) or {
            "forbidden_present": [value for value in self.job["forbidden"] if value in text],
            "system_contains_prompt": bool(messages) and self.job["system_prompt"] in system,
            "user_message_present_verbatim": any(m.get("content") == self.job["user_message"] for m in messages),
            "system_message_sha256": hashlib.sha256(system.encode()).hexdigest() if messages else None,
            "request_sha256": hashlib.sha256(raw).hexdigest(), "tool_count": len(body.get("tools") or [])}

    def count_sent(self, sent) -> None:
        self.admitted += 1
        self.sent.append({"attempt_id": sent.attempt_id, "route_id": sent.route_id, "body_bytes": len(sent.body)})

    def remember(self, status: int, body: bytes) -> None:
        """What the accepted job reads after Hermes returns: the reply's finish reason, content and usage."""
        if status >= 400:
            self.provider_error_sent = True
            return
        try:
            completion = json.loads(body)
            choice = completion["choices"][0]
            self.finish_reason, self.admitted_content = choice.get("finish_reason"), choice["message"].get("content")
            self.sent_usage = completion.get("usage")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            pass

    def note(self, refusal: str | None, **detail: Any) -> None:
        if len(self.evidence) < MAX_EVIDENCE:
            self.evidence.append({"sequence": len(self.evidence) + 1, "refusal": refusal, **detail})


def main() -> int:
    base.OUTPUT.mkdir(parents=True, exist_ok=True)
    job = json.loads(base.INPUT.read_text(encoding="utf-8"))
    base.FakeProvider = RelayProvider
    sandbox = {"network": base.attempt_egress(), "filesystem": base.filesystem_checks(),
               "hermes_home_under_tmp": os.environ.get("HERMES_HOME", "").startswith("/tmp/p05-"),
               "credential_mounted": CREDENTIAL.exists()}
    hermes = base.run_hermes(job)
    provider = PROVIDERS[0] if PROVIDERS else None
    guard, sent = (provider.guard if provider else None), (provider.sent if provider else [])
    route_id = job["job_settings"]["transport"]["route"]["route_id"]
    hermes["observed"].update(
        transport_attempt_id=job["attempt_id"], transport_route_id=route_id, transport_sent=len(sent),
        transport_request_attempt_ids=[record["attempt_id"] for record in sent],
        transport_refusals=sorted({r["refusal"] for r in (provider.evidence if provider else []) if r["refusal"]}))
    base.write_json(base.OUTPUT / "container-result.json", {
        "fixture_label": "LOCAL_RELAY_AUTHORED_NO_JOB_NETWORK", "hermes_source_commit": base.PINNED_HERMES,
        "attempt_id": job["attempt_id"], "sandbox": sandbox, "hermes": hermes,
        "guard": {"admitted_count": guard.admitted_count if guard else 0, "seen_count": guard.seen_count if guard else 0,
                  "credential_injected": False, "evidence": guard.evidence() if guard else []},
        "transport": {"route_id": route_id, "sent": sent, "evidence": provider.evidence if provider else [],
                      "credential_attached": False}})
    return 0 if sandbox["network"]["blocked"] and not sandbox["credential_mounted"] else 3


if __name__ == "__main__":
    sys.exit(main())
