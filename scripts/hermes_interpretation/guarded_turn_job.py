"""Container entrypoint: one ACTUAL pinned-Hermes turn behind the provider request guard. Controlled provider only.

It reuses the P05 fake-provider job (`hermes_turn_job`, inside the image) and puts the guard in front of the fake
provider. A refused request gets a 429 and never reaches the fake provider. The credential is read from a mounted file
and injected where the live client is built, so the controlled run sends the same header a live run would send. The
container has no network. This proves guard and accounting mechanics. It proves nothing about a real model.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/opt/p05")
sys.path.insert(0, "/opt/p05guard")

import hermes_turn_job as base  # noqa: E402  (the existing job, inside the image)
from provider_guard import GuardPolicy, LogicalRequest, ProviderRequestGuard  # noqa: E402

CREDENTIAL = Path("/job/credential")
GUARDS: list[ProviderRequestGuard] = []


class GuardedProvider(base.FakeProvider):
    """The fake provider behind the guard."""

    def __init__(self, job: dict) -> None:
        super().__init__(job)
        policy = GuardPolicy(**job["guard"]["policy"])
        credential = CREDENTIAL.read_text(encoding="utf-8").strip() if CREDENTIAL.exists() else None
        self.guard = ProviderRequestGuard(policy, LogicalRequest(job["system_prompt"], job["user_message"]), credential)
        GUARDS.append(self.guard)

    def __call__(self, request):
        import httpx

        decision = self.guard.admit(request.content, dict(request.headers))
        if not decision.admitted:
            return httpx.Response(429, json={"error": {"message": "request not admitted", "type": "request_not_admitted"}},
                                  request=request)
        return super().__call__(request)


def inject_credential() -> bool:
    """Every client the job builds carries the mounted credential, as a live client would."""
    import openai

    if not CREDENTIAL.exists():
        return False
    secret, real = CREDENTIAL.read_text(encoding="utf-8").strip(), openai.OpenAI

    def with_credential(*args, **kwargs):
        kwargs["api_key"] = secret
        return real(*args, **kwargs)

    openai.OpenAI = with_credential
    return True


def main() -> int:
    base.OUTPUT.mkdir(parents=True, exist_ok=True)
    job = json.loads(base.INPUT.read_text(encoding="utf-8"))
    base.FakeProvider = GuardedProvider
    injected = inject_credential()
    sandbox = {"network": base.attempt_egress(), "filesystem": base.filesystem_checks(),
               "hermes_home_under_tmp": os.environ.get("HERMES_HOME", "").startswith("/tmp/p05-")}
    hermes = base.run_hermes(job)
    guard = GUARDS[0] if GUARDS else None
    base.write_json(base.OUTPUT / "container-result.json", {
        "fixture_label": "LOCAL_FAKE_PROVIDER_NO_NETWORK", "hermes_source_commit": base.PINNED_HERMES,
        "attempt_id": job["attempt_id"], "sandbox": sandbox, "hermes": hermes,
        "guard": {"admitted_count": guard.admitted_count if guard else 0, "seen_count": guard.seen_count if guard else 0,
                  "credential_injected": injected, "evidence": guard.evidence() if guard else []}})
    return 0 if sandbox["network"]["blocked"] else 3


if __name__ == "__main__":
    sys.exit(main())
