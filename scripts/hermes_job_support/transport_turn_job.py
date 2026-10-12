"""Container entrypoint: one ACTUAL pinned-Hermes turn whose one request goes through an injected provider transport.

It reuses the accepted P05 job (`hermes_turn_job`, inside the image) and the accepted provider guard. Hermes talks to a
placeholder client, which never holds the host's endpoint or credential; Hermes shares this process, so it is not
isolated from the credential copy the transport reads. Each request Hermes sends is checked first as a
physical request, then by the guard; only then is a host request built and handed to the transport. A refused request
gets a 429 and no transport sees it. A reply the route does not allow gets a 502 and its content is dropped, so nothing
from it can be published. The container has no network; in this candidate the only transport is the AUTHORED one.

The host mounts this file, `provider_transport.py` and `authored_transport.py` read-only under /opt/p05job.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, "/opt/p05")
sys.path.insert(0, "/opt/p05guard")
sys.path.insert(0, "/opt/p05job")

import hermes_turn_job as base  # noqa: E402  (the accepted job, inside the image)
from authored_transport import AuthoredTransport  # noqa: E402
from provider_guard import GuardPolicy, LogicalRequest, ProviderRequestGuard  # noqa: E402
from provider_transport import (  # noqa: E402
    HERMES_CLIENT_KEY, ActualProviderUnavailable, PhysicalRequest, TransportRoute, host_request, physical_refusal,
    reply_refusal,
)

CREDENTIAL = Path("/job/credential")
MAX_EVIDENCE = 16  # Hermes sends at most a few requests per turn; more records than this are not kept
PROVIDERS: list[TransportProvider] = []
NOT_ADMITTED = {"error": {"message": "request not admitted", "type": "request_not_admitted"}}


class TransportProvider(base.FakeProvider):
    """What Hermes' HTTP client calls. The accepted fake provider is only the authored provider behind the transport."""

    def __init__(self, job: dict[str, Any]) -> None:
        super().__init__(job)
        settings = job["job_settings"]["transport"]
        self.route, self.client_url = TransportRoute.from_settings(settings["route"]), settings["client_url"]
        self.attempt_id = job["attempt_id"]
        policy = GuardPolicy(**job["guard"]["policy"])
        # Hermes' client must carry the placeholder key and nothing else; the host credential never reaches it.
        self.guard = ProviderRequestGuard(policy, LogicalRequest(job["system_prompt"], job["user_message"]), HERMES_CLIENT_KEY)
        self.credential = CREDENTIAL.read_text(encoding="utf-8").strip() if CREDENTIAL.exists() else None
        if self.route.kind != "AUTHORED":
            raise ActualProviderUnavailable("no actual provider transport exists in this candidate")
        self.transport = AuthoredTransport(self.route, self.play, self.credential, self.script)
        self.sent: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        PROVIDERS.append(self)

    def play(self, request):
        """The authored provider: the accepted fake provider's scripted behavior for one host request.

        `super()`, not `base.FakeProvider`: main() replaces that name with this class, which would call itself.
        """
        return super().__call__(request)

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
        sent = host_request(physical, self.route, self.attempt_id, self.credential)
        self.sent.append({"attempt_id": sent.attempt_id, "route_id": sent.route_id, "body_bytes": len(sent.body)})
        try:
            reply = self.transport.send(sent)
        except Exception as error:  # noqa: BLE001 - whatever failed, the request may have reached the provider
            self.drop_reply()
            self.note(f"reply_lost:{type(error).__name__}")
            raise httpx.ReadError("the provider reply was lost", request=request) from None
        refused = reply_refusal(reply, self.route)
        self.note(refused, reply_status=reply.status, reply_bytes=len(reply.body) if isinstance(reply.body, bytes) else None)
        if refused is not None:
            self.drop_reply()
            return httpx.Response(502, json={"error": {"message": "reply not admitted", "type": refused}}, request=request)
        return httpx.Response(reply.status, content=reply.body, headers={"content-type": "application/json"},
                              request=request)

    def drop_reply(self) -> None:
        """Forget what the authored provider produced, so the job reports no text and no usage from it."""
        self.finish_reason = self.admitted_content = self.sent_usage = None

    def note(self, refusal: str | None, **detail: Any) -> None:
        if len(self.evidence) < MAX_EVIDENCE:
            self.evidence.append({"sequence": len(self.evidence) + 1, "refusal": refusal, **detail})


def main() -> int:
    base.OUTPUT.mkdir(parents=True, exist_ok=True)
    job = json.loads(base.INPUT.read_text(encoding="utf-8"))
    base.FakeProvider = TransportProvider
    sandbox = {"network": base.attempt_egress(), "filesystem": base.filesystem_checks(),
               "hermes_home_under_tmp": os.environ.get("HERMES_HOME", "").startswith("/tmp/p05-")}
    hermes = base.run_hermes(job)
    provider = PROVIDERS[0] if PROVIDERS else None
    guard, sent = (provider.guard if provider else None), (provider.sent if provider else [])
    route_id = job["job_settings"]["transport"]["route"]["route_id"]
    hermes["observed"].update(
        transport_attempt_id=job["attempt_id"], transport_route_id=route_id, transport_sent=len(sent),
        transport_request_attempt_ids=[record["attempt_id"] for record in sent],
        transport_refusals=sorted({r["refusal"] for r in (provider.evidence if provider else []) if r["refusal"]}))
    base.write_json(base.OUTPUT / "container-result.json", {
        "fixture_label": "LOCAL_AUTHORED_TRANSPORT_NO_NETWORK", "hermes_source_commit": base.PINNED_HERMES,
        "attempt_id": job["attempt_id"], "sandbox": sandbox, "hermes": hermes,
        "guard": {"admitted_count": guard.admitted_count if guard else 0, "seen_count": guard.seen_count if guard else 0,
                  "credential_injected": False, "evidence": guard.evidence() if guard else []},
        "transport": {"route_id": route_id, "sent": sent, "evidence": provider.evidence if provider else [],
                      "credential_attached": provider.transport.credential_attached if provider else None}})
    return 0 if sandbox["network"]["blocked"] else 3


if __name__ == "__main__":
    sys.exit(main())
