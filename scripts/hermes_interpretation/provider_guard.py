"""The provider request guard: decides, before any transport sees a request, whether it may leave. Support code only.

One attempt may send exactly one physical request. The guard admits that request only if it matches the configured
attempt: model, output limit, prompt and task, the fixed envelope fields and the injected credential. It refuses
tools, streaming, fallback routes, SDK or Hermes retries, truncation continuations and iteration summaries. It refuses
before the transport is called, so a refused request does no provider work and costs nothing.

The guard checks what it can see in the request. It cannot see a socket that code opens outside the transport. A live
host must also limit egress to the provider and count requests at that boundary. Evidence keeps hashes, sizes and
header NAMES. It never keeps a body or a header value.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Decision", "GuardPolicy", "LogicalRequest", "ProviderRequestGuard", "guard_handler"]

ENVELOPE_FIELDS = frozenset({"model", "messages", "max_tokens", "session_id"})
SUMMARY_MARKER = "summarizing what you've found and accomplished so far"
CONTINUATION_MARKER = "Continue exactly where you left off"


@dataclass(frozen=True)
class GuardPolicy:
    model: str
    max_output_tokens: int
    max_request_bytes: int
    max_envelope_chars: int
    required_extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LogicalRequest:
    system_prompt: str
    user_message: str


@dataclass(frozen=True)
class Decision:
    admitted: bool
    reason: str | None
    phase: str


class ProviderRequestGuard:
    def __init__(self, policy: GuardPolicy, logical: LogicalRequest, credential: str | None) -> None:
        self._policy, self._logical, self._credential = policy, logical, credential
        self.admitted_count = 0
        self.seen_count = 0
        self._evidence: list[dict[str, Any]] = []
        self._lock = threading.Lock()  # Hermes and the SDK may call the transport from more than one thread

    def evidence(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._evidence]

    def admit(self, raw: bytes, headers: Mapping[str, str]) -> Decision:
        with self._lock:
            return self._admit(raw, headers)

    def _admit(self, raw: bytes, headers: Mapping[str, str]) -> Decision:
        self.seen_count += 1
        parsed = self._parse(raw)
        phase = self._phase(parsed)
        reason = self._refusal(raw, parsed, headers, phase)
        admitted = reason is None
        if admitted:
            self.admitted_count += 1
        self._evidence.append({
            "sequence": self.seen_count, "admitted": admitted, "reason": reason, "phase": phase,
            "request_sha256": hashlib.sha256(raw).hexdigest(), "request_bytes": len(raw),
            "header_names": sorted(name.lower() for name in headers)})
        return Decision(admitted, reason, phase)

    @staticmethod
    def _parse(raw: bytes) -> dict[str, Any] | None:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _phase(self, parsed: dict[str, Any] | None) -> str:
        text = json.dumps(parsed.get("messages")) if parsed else ""
        if SUMMARY_MARKER in text:
            return "iteration_summary"
        if CONTINUATION_MARKER in text:
            return "truncation_continuation"
        return "retry" if self.admitted_count >= 1 else "initial"

    def _refusal(self, raw: bytes, wire: dict[str, Any] | None, headers: Mapping[str, str], phase: str) -> str | None:
        policy = self._policy
        if wire is None:
            return "body_not_a_json_object"
        if self.admitted_count >= 1:
            return "physical_request_count_exceeded"
        lowered = {name.lower(): value for name, value in headers.items()}
        if self._credential is not None and lowered.get("authorization") != f"Bearer {self._credential}":
            return "credential_not_as_injected"
        if len(raw) > policy.max_request_bytes:
            return "request_too_large"
        if wire.get("model") != policy.model:
            return "model_not_as_configured"
        limit = wire.get("max_tokens")
        if isinstance(limit, bool) or limit != policy.max_output_tokens:
            return "output_limit_not_as_configured"
        if set(wire) - ENVELOPE_FIELDS - set(policy.required_extra):
            return "unpermitted_field"
        if any(wire.get(name) != value for name, value in policy.required_extra.items()):
            return "routing_not_as_configured"
        if not isinstance(wire.get("session_id", ""), str):
            return "unpermitted_field"
        return self._messages_refusal(wire.get("messages"))

    def _messages_refusal(self, messages: object) -> str | None:
        shape = (isinstance(messages, list) and len(messages) == 2 and all(isinstance(m, dict) for m in messages)
                 and [m.get("role") for m in messages] == ["system", "user"]
                 and all(isinstance(m.get("content"), str) for m in messages))
        if not shape:
            return "messages_not_as_configured"
        system, user = messages[0]["content"], messages[1]["content"]  # type: ignore[index]
        if user != self._logical.user_message:
            return "task_not_as_configured"
        if self._logical.system_prompt not in system:
            return "prompt_not_as_configured"
        if len(system) - len(self._logical.system_prompt) > self._policy.max_envelope_chars:
            return "envelope_too_large"
        return None


def guard_handler(guard: ProviderRequestGuard, transport: Callable[[bytes, Mapping[str, str]], tuple[int, bytes]]
                  ) -> Callable[[bytes, Mapping[str, str]], tuple[int, bytes]]:
    """Wrap a transport. A refused request gets a 429 and never reaches the transport."""
    def handle(raw: bytes, headers: Mapping[str, str]) -> tuple[int, bytes]:
        decision = guard.admit(raw, headers)
        if not decision.admitted:
            return 429, json.dumps({"error": {"message": "request not admitted", "type": "request_not_admitted"}}).encode()
        return transport(raw, headers)
    return handle
