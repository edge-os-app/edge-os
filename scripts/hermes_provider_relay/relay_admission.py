"""The relay's admission rules, shared by the host and the relay process. Standard library only; no I/O anywhere.

A host turn runner issues one signed grant per attempt after the spend reservation is recorded. The grant names the
owner, saved request, job (run and channel root), attempt, route and release, the guard policy and the logical request,
and an expiry no later than the job's own timeout. The relay admits a job's channel message only when the grant is
signed with the admission key, is for the relay's own release and is still open, and the message names exactly the
grant's attempt, route and release and carries only a bounded body. The relay builds everything else itself.

See `docs/qualification/hermes-provider-relay/CONTRACT.md` sections 3.2 to 3.4.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from egress_gateway import HOST, MAX_TUNNEL_SECONDS

__all__ = ["APPROVED_ACTUAL_RELEASES", "CHANNEL_FIELDS", "ActualRelease", "ActualReleaseUnapproved", "ProviderDestination",
           "RelayRelease", "RelaySubject", "channel_refusal", "grant_refusal", "issue_grant", "load_actual_release",
           "parse_channel_message"]

RELEASE_KINDS = ("AUTHORED", "ACTUAL")  # an ACTUAL release exists only through an approved record (CONTRACT A6)
# SHA256 of approved release records. Every other ACTUAL record fails closed. hermes-first-call-1:
# docs/qualification/hermes-actual-operation/release/hermes_first_call_record.json
# The approved record names its own destination (host, port, path; the TLS server name is its host), routing and CA
# bundle pin: approving its SHA256 approves them. A record naming any other destination is not approved.
APPROVED_ACTUAL_RELEASES: frozenset[str] = frozenset({"3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f"})
ACTUAL_BODY_FIELDS = frozenset({"model", "messages", "stream", "response_format", "provider", "reasoning", "max_tokens",
                                "session_id", "prompt_cache_options"})
REQUIRED_BODY_FIELDS = frozenset({"model", "messages", "stream", "provider", "max_tokens", "session_id"})
RECORD_FIELDS = frozenset({"release_id", "route_id", "kind", "approval", "destination", "ca_bundle_sha256", "model",
                           "provider", "max_tokens", "reasoning", "response_format_sha256", "stream", "allowed_fields",
                           "max_request_bytes", "max_reply_bytes", "timeout_seconds", "price_snapshot_sha256"})
# Optional: a record that names it sends exactly this value (automatic prompt caching off, no breakpoint); a record
# without it keeps the earlier shape, where the body must not carry the field.
PROMPT_CACHE_OPTIONS = {"mode": "explicit"}
# Every routing field this code can check. A record names its routing fields; one outside this set is refused, never
# ignored, and none of these may be left out. A provider with other routing fields needs a reviewed change here.
KNOWN_ROUTING_FIELDS = frozenset({"only", "allow_fallbacks", "require_parameters", "data_collection", "max_price"})
SHA256 = re.compile(r"[0-9a-f]{64}")
_LOADING = threading.local()  # set only inside load_actual_release: the one way to build an ACTUAL release
MAX_REPLY_LIMIT = 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
CLOCK_SKEW_SECONDS = 2.0  # a grant issued this far in the relay's future is still accepted (host and VM clocks)
CHANNEL_FIELDS = frozenset({"attempt_id", "route_id", "release_id", "body_b64"})
GRANT_FIELDS = frozenset({"grant_id", "release_id", "route_id", "run_id", "channel_root", "owner_id", "request_id",
                          "attempt_id", "scope", "policy", "logical", "issued_at", "expires_at", "mac"})


def _identifier(value: Any, label: str) -> None:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be 1-64 letters, digits or ._:-")


def _bounded(value: Any, label: str, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} must be a whole number from {low} to {high}")


@dataclass(frozen=True)
class RelayRelease:
    """The immutable configuration one relay serves: route, model and byte/token bounds."""

    release_id: str
    route_id: str
    kind: str
    model: str
    max_output_tokens: int
    max_request_bytes: int
    max_reply_bytes: int

    def __post_init__(self) -> None:
        _identifier(self.release_id, "release_id")
        _identifier(self.route_id, "route_id")
        if self.kind not in RELEASE_KINDS:
            raise ValueError(f"kind must be one of {RELEASE_KINDS}")
        if self.kind == "ACTUAL" and not getattr(_LOADING, "record", False):
            raise ValueError("an ACTUAL release is built only from an approved release record (load_actual_release)")
        if not isinstance(self.model, str) or not 0 < len(self.model) <= 200:
            raise ValueError("model must be a non-empty name")
        _bounded(self.max_output_tokens, "max_output_tokens", 1, 1_000_000)
        _bounded(self.max_request_bytes, "max_request_bytes", 1, 1024 * 1024)
        _bounded(self.max_reply_bytes, "max_reply_bytes", 1, MAX_REPLY_LIMIT)

    def settings(self) -> dict[str, Any]:
        return {"release_id": self.release_id, "route_id": self.route_id, "kind": self.kind, "model": self.model,
                "max_output_tokens": self.max_output_tokens, "max_request_bytes": self.max_request_bytes,
                "max_reply_bytes": self.max_reply_bytes}

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> RelayRelease:
        return cls(**{name: settings[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class ProviderDestination:
    """Where the relay sends: https, this host and port, this path. Fixed when the relay starts; never from the job."""

    host: str
    port: int
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.host, str) or len(self.host) > 253 or not HOST.fullmatch(self.host):
            raise ValueError("host must be a lower-case DNS name")
        _bounded(self.port, "port", 1, 65_535)
        if (not isinstance(self.path, str) or not self.path.startswith("/") or len(self.path) > 200
                or any(c in self.path for c in "?#% \t\r\n")):
            raise ValueError("path must be an absolute path with no query, fragment or escape")


@dataclass(frozen=True)
class RelaySubject:
    """Who the attempt belongs to: the owner and the saved request, proved by the host before a grant is issued."""

    owner_id: str
    request_id: str


def _canonical(fields: Mapping[str, Any]) -> bytes:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _mac(fields: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical({k: v for k, v in fields.items() if k != "mac"}), hashlib.sha256).hexdigest()


def issue_grant(*, release: RelayRelease, run_id: str, channel_root: str, owner_id: str, request_id: str,
                attempt_id: str, scope: str, policy: Mapping[str, Any], system_prompt: str, user_message: str,
                issued_at: float, timeout_seconds: float, key: bytes) -> dict[str, Any]:
    """One signed grant. Its id is derived from what it grants, so the same grant is never issued twice by mistake."""
    if not math.isfinite(issued_at) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("issued_at and timeout_seconds must be finite, the timeout above 0")
    fields: dict[str, Any] = {
        "release_id": release.release_id, "route_id": release.route_id, "run_id": run_id, "channel_root": channel_root,
        "owner_id": owner_id, "request_id": request_id, "attempt_id": attempt_id, "scope": scope,
        "policy": json.loads(json.dumps(dict(policy), allow_nan=False)),
        "logical": {"system_prompt": system_prompt, "user_message": user_message,
                    "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
                    "user_message_sha256": hashlib.sha256(user_message.encode()).hexdigest()},
        "issued_at": issued_at, "expires_at": issued_at + timeout_seconds}
    fields["grant_id"] = "g-" + hashlib.sha256(_canonical(fields)).hexdigest()[:32]
    fields["mac"] = _mac(fields, key)
    return fields


def grant_refusal(grant: Any, key: bytes, release: RelayRelease, *, now: float) -> str | None:
    """Why this grant admits nothing now, or None. The signature is checked before any field is trusted."""
    if not isinstance(grant, dict) or set(grant) != GRANT_FIELDS:
        return "grant_fields_invalid"
    try:
        expected = _mac(grant, key)
    except (TypeError, ValueError):
        return "grant_fields_invalid"
    if not isinstance(grant["mac"], str) or not hmac.compare_digest(grant["mac"], expected):
        return "grant_signature_invalid"
    if (grant["release_id"], grant["route_id"]) != (release.release_id, release.route_id):
        return "grant_release_mismatch"
    if grant["policy"].get("model") != release.model or grant["policy"].get("max_output_tokens") != release.max_output_tokens:
        return "grant_release_mismatch"
    if now >= grant["expires_at"]:
        return "grant_expired"
    if grant["issued_at"] > now + CLOCK_SKEW_SECONDS:
        return "grant_not_yet_valid"
    return None


def parse_channel_message(raw: bytes) -> dict[str, Any] | None:
    """One JSON object with no repeated key (two readers must never see two different messages), or None."""
    def no_repeats(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key is repeated")
        return dict(pairs)

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_repeats)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def channel_refusal(message: Mapping[str, Any], grant: Mapping[str, Any], release: RelayRelease) -> str | None:
    """Why this job message may not become a provider request under this (already checked) grant, or None."""
    if set(message) - CHANNEL_FIELDS:
        return "channel_field_not_permitted"  # no URL, header, credential, model or retry can come from the job
    if set(message) != CHANNEL_FIELDS:
        return "channel_field_missing"
    if message["attempt_id"] != grant["attempt_id"]:
        return "attempt_mismatch"
    if message["route_id"] != grant["route_id"]:
        return "route_mismatch"
    if message["release_id"] != grant["release_id"]:
        return "release_mismatch"
    encoded = message["body_b64"]
    if not isinstance(encoded, str) or len(encoded) > 4 * (release.max_request_bytes // 3 + 2):
        return "request_too_large" if isinstance(encoded, str) else "body_not_base64"
    try:
        body = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return "body_not_base64"
    if len(body) > release.max_request_bytes or len(body) > grant["policy"].get("max_request_bytes", 0):
        return "request_too_large"
    return None


class ActualReleaseUnapproved(ValueError):
    """The record is well formed but its SHA256 is not an approved ACTUAL release identity."""


def _no_repeats(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("a key is repeated")
    return dict(pairs)


def _strict_json(raw: bytes) -> Any:
    """JSON with no repeated key and no NaN or Infinity; ValueError otherwise."""
    def no_constant(name: str) -> Any:
        raise ValueError(f"{name} is not allowed")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_repeats, parse_constant=no_constant)
    except (UnicodeDecodeError, RecursionError) as error:
        raise ValueError("not strict JSON") from error


def _sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lower-case SHA256")


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


@dataclass(frozen=True)
class ActualRelease:
    """One frozen ACTUAL release record (CONTRACT A6, ONLINE_CONTINUATION.md section 3), loaded by exact SHA256."""

    record_sha256: str
    release: RelayRelease
    destination: ProviderDestination
    ca_bundle_sha256: str
    provider: dict[str, Any]
    reasoning: dict[str, Any] | None
    response_format_sha256: str
    allowed_fields: frozenset[str]
    timeout_seconds: int
    prompt_cache_options: dict[str, Any] | None = None  # PROMPT_CACHE_OPTIONS when the record names it

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.destination.host}{self.destination.path}"

    def body_refusal(self, body: bytes, attempt_id: str) -> str | None:
        """Why this admitted body is not exactly the release's request shape, or None. Checked before any start."""
        try:
            value = _strict_json(body)
        except ValueError:
            return "body_not_json"
        if not isinstance(value, dict):
            return "body_not_json"
        if set(value) - self.allowed_fields:
            return "body_field_not_permitted"
        required = REQUIRED_BODY_FIELDS | ({"reasoning"} if self.reasoning is not None else set()) | (
            {"response_format"} if "response_format" in self.allowed_fields else set()) | (
            {"prompt_cache_options"} if self.prompt_cache_options is not None else set())
        if required - set(value):
            return "body_field_missing"
        if value["model"] != self.release.model:
            return "body_model_mismatch"
        if value["stream"] is not False:
            return "body_stream_not_false"
        if type(value["max_tokens"]) is not int or value["max_tokens"] != self.release.max_output_tokens:  # noqa: E721
            return "body_max_tokens_mismatch"
        if _canonical(value["provider"]) != _canonical(self.provider):
            return "body_routing_mismatch"
        if _canonical(value.get("reasoning")) != _canonical(self.reasoning):
            return "body_reasoning_mismatch"
        if "prompt_cache_options" in value and _canonical(value["prompt_cache_options"]) != _canonical(
                self.prompt_cache_options):
            return "body_cache_options_mismatch"
        if "response_format" in value and hashlib.sha256(
                _canonical(value["response_format"])).hexdigest() != self.response_format_sha256:
            return "body_schema_mismatch"
        if value["session_id"] != f"p05-{attempt_id}":
            return "body_session_mismatch"
        if not isinstance(value["messages"], list) or not value["messages"]:
            return "body_messages_invalid"
        return None

    def reply_check(self, status: int, content_type: str, content_encoding: str,
                    body: bytes) -> tuple[str | None, dict[str, Any]]:
        """(None, usage, cost and generation id) only for a complete counted reply; otherwise (reason, {})."""
        if content_encoding:
            return "reply_encoded_refused", {}  # nothing asked for an encoding; it is never decoded on trust
        if isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300:
            return "reply_status_not_2xx", {}
        if not content_type.startswith("application/json"):
            return "reply_not_json", {}
        try:
            value = _strict_json(body)
        except ValueError:
            return "reply_not_a_json_object", {}
        if not isinstance(value, dict):
            return "reply_not_a_json_object", {}
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            return "reply_choices_invalid", {}
        finish = choices[0].get("finish_reason")
        if finish != "stop":
            return ("reply_truncated" if finish == "length" else "reply_not_final"), {}
        if value.get("model") != self.release.model:
            return "reply_model_mismatch", {}
        usage = value.get("usage")
        keys = ("prompt_tokens", "completion_tokens", "total_tokens")
        if not isinstance(usage, dict) or not all(_whole(usage.get(key)) for key in keys):
            return "reply_usage_invalid", {}
        cost = usage.get("cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            return "reply_cost_invalid", {}
        generation = value.get("id")
        return None, {"usage": {key: usage[key] for key in keys}, "cost": cost,
                      "generation_id": generation if isinstance(generation, str) and len(generation) <= 200 else None}


def load_actual_release(raw: bytes, expected_sha256: str, *, approved: frozenset[str] | None = None) -> ActualRelease:
    """The ACTUAL release in `raw`, only if its bytes have this SHA256 and that SHA256 is approved.

    `approved` defaults to `APPROVED_ACTUAL_RELEASES`, which names only the adopted record: every other ACTUAL release
    fails closed. The destination, routing and CA bundle pin are the approved record's own. A record that names a test
    resolver is never a release.
    """
    sha = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(sha, expected_sha256):
        raise ValueError("the release record bytes do not have the named hash")
    if sha not in (APPROVED_ACTUAL_RELEASES if approved is None else approved):
        raise ActualReleaseUnapproved("this release record is not an approved ACTUAL release")
    value = _strict_json(raw)
    if not isinstance(value, dict) or set(value) - {"prompt_cache_options"} != RECORD_FIELDS:
        raise ValueError("the release record must have exactly the frozen fields")
    if value["kind"] != "ACTUAL" or value["stream"] is not False:
        raise ValueError("the release record must be kind ACTUAL with stream false")
    approval = value["approval"]
    if not isinstance(approval, dict) or set(approval) != {"path", "sha256"} or not isinstance(approval["path"], str):
        raise ValueError("the release record must name its approval packet and hash")
    for label in ("ca_bundle_sha256", "response_format_sha256", "price_snapshot_sha256"):
        _sha256(value[label], label)
    _sha256(approval["sha256"], "approval sha256")
    destination = ProviderDestination(**value["destination"])  # the approved record's own; nothing else is reachable
    routing = value["provider"]
    if not isinstance(routing, dict):
        raise ValueError("routing must be an object")
    if set(routing) - KNOWN_ROUTING_FIELDS:
        raise ValueError(f"unknown routing field refused: {sorted(set(routing) - KNOWN_ROUTING_FIELDS)}")
    if KNOWN_ROUTING_FIELDS - set(routing):
        raise ValueError(f"routing field missing: {sorted(KNOWN_ROUTING_FIELDS - set(routing))}")
    if (not isinstance(routing["only"], list)
            or len(routing["only"]) != 1 or not isinstance(routing["only"][0], str) or routing["allow_fallbacks"] is not False
            or routing["require_parameters"] is not True or not isinstance(routing["max_price"], dict)):
        raise ValueError("routing must name one provider, no fallbacks, required parameters and a price limit")
    fields = value["allowed_fields"]
    if (not isinstance(fields, list) or not set(fields) <= ACTUAL_BODY_FIELDS or not REQUIRED_BODY_FIELDS <= set(fields)
            or len(set(fields)) != len(fields)):
        raise ValueError("allowed_fields must be the frozen request fields")
    reasoning = value["reasoning"]
    if reasoning is not None and not isinstance(reasoning, dict):
        raise ValueError("reasoning must be an object or null")
    cache = value.get("prompt_cache_options")
    if "prompt_cache_options" in value and _canonical(cache) != _canonical(PROMPT_CACHE_OPTIONS):
        raise ValueError('prompt_cache_options must be exactly {"mode": "explicit"}, with no breakpoint or other field')
    if ("prompt_cache_options" in value) != ("prompt_cache_options" in fields):
        raise ValueError("allowed_fields must name prompt_cache_options exactly when the record sets it")
    _bounded(value["timeout_seconds"], "timeout_seconds", 1, int(MAX_TUNNEL_SECONDS))  # the gateway closes at 120 s
    _LOADING.record = True
    try:
        release = RelayRelease(value["release_id"], value["route_id"], "ACTUAL", value["model"], value["max_tokens"],
                               value["max_request_bytes"], value["max_reply_bytes"])
    finally:
        _LOADING.record = False
    return ActualRelease(sha, release, destination, value["ca_bundle_sha256"], routing, reasoning,
                         value["response_format_sha256"], frozenset(fields), value["timeout_seconds"],
                         dict(PROMPT_CACHE_OPTIONS) if "prompt_cache_options" in value else None)
