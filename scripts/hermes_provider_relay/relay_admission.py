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
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["CHANNEL_FIELDS", "ProviderDestination", "RelayRelease", "RelaySubject", "channel_refusal", "grant_refusal",
           "issue_grant", "parse_channel_message"]

RELEASE_KINDS = ("AUTHORED",)  # an ACTUAL release needs its own approval packet; nothing here can express one
MAX_REPLY_LIMIT = 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
HOST = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*")
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
