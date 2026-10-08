"""Privy access-token verification (P01 verifier profile) and principal derivation.

Application policy, not a provider guarantee: payloads carrying a top-level
`linked_accounts` or `custom_metadata` claim are refused so identity tokens stay out.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DataError, SQLAlchemyError

from .errors import auth_error, service_unavailable
from .models import User

log = logging.getLogger("edge_os.auth")

MAX_TOKEN_CHARS = 4096
LEEWAY_SECONDS = 10
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "sid"]
IDENTITY_CLAIMS = ("linked_accounts", "custom_metadata")
_LOG_INTERVAL = 60.0
_last_logged: dict[str, float] = {}
counters: dict[str, int] = {"auth.signature_failure": 0, "auth.previous_key_accepted": 0}


def count_event(name: str) -> None:
    """Count an operator-facing auth event and log it at most once a minute (name and running total only).

    `auth.signature_failure` shows a spike. `auth.previous_key_accepted` shows when the previous key can go.
    """
    counters[name] += 1
    now = time.monotonic()
    if now - _last_logged.get(name, -_LOG_INTERVAL) >= _LOG_INTERVAL:
        _last_logged[name] = now
        log.warning("%s total=%d", name, counters[name])


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    privy_did: str


class AuthFailure(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class Verifier:
    def __init__(self, app_id: str, keys: list[Any]):
        self.app_id, self.keys = app_id, list(keys)

    def verify(self, token: str) -> dict[str, Any]:
        if not token or len(token) > MAX_TOKEN_CHARS:
            raise AuthFailure(401, "auth_invalid")
        if not self.keys:
            raise AuthFailure(503, "auth_unavailable")
        claims: dict[str, Any] | None = None
        for index, key in enumerate(self.keys):
            try:
                claims = jwt.decode(token, key, algorithms=["ES256"], issuer="privy.io", audience=self.app_id,
                                    options={"require": REQUIRED_CLAIMS}, leeway=LEEWAY_SECONDS)
            except jwt.InvalidSignatureError:
                count_event("auth.signature_failure")
                continue
            except jwt.ExpiredSignatureError:
                raise AuthFailure(401, "auth_expired") from None
            except jwt.InvalidKeyError:
                raise AuthFailure(503, "auth_unavailable") from None
            except jwt.InvalidTokenError:
                raise AuthFailure(401, "auth_invalid") from None
            except Exception as error:  # noqa: BLE001 - attacker chooses the input
                self._log_unexpected(type(error).__name__)
                raise AuthFailure(401, "auth_invalid") from None
            if index > 0:
                count_event("auth.previous_key_accepted")
            break
        if claims is None:
            raise AuthFailure(401, "auth_invalid")
        self._check_claims(claims)
        return claims

    @staticmethod
    def _log_unexpected(name: str) -> None:
        now = time.monotonic()
        if now - _last_logged.get(name, -_LOG_INTERVAL) >= _LOG_INTERVAL:
            _last_logged[name] = now
            log.warning("auth.verifier_error class=%s", name)

    def _check_claims(self, claims: dict[str, Any]) -> None:
        if not (_is_number(claims.get("exp")) and _is_number(claims.get("iat"))):
            raise AuthFailure(401, "auth_invalid")
        aud, sub, sid = claims.get("aud"), claims.get("sub"), claims.get("sid")
        if not isinstance(aud, str) or aud != self.app_id:
            raise AuthFailure(401, "auth_invalid")
        if not (isinstance(sub, str) and sub.startswith("did:privy:") and len(sub) <= 255):
            raise AuthFailure(401, "auth_invalid")
        if not (isinstance(sid, str) and 0 < len(sid) <= 255):
            raise AuthFailure(401, "auth_invalid")
        if any(name in claims for name in IDENTITY_CLAIMS):
            raise AuthFailure(401, "auth_invalid")


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if header is None:
        raise auth_error(401, "auth_required", "An Authorization bearer token is required.")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip() or " " in token.strip():
        raise auth_error(401, "auth_invalid", "The credential is not a valid bearer token.")
    return token.strip()


def require_principal(request: Request) -> Principal:
    """Default-deny dependency: verify the token, then upsert and return the user."""
    token = bearer_token(request)
    verifier: Verifier | None = getattr(request.app.state, "verifier", None)
    if verifier is None or not verifier.keys:
        raise auth_error(503, "auth_unavailable", "Identity verification is unavailable.")
    try:
        claims = verifier.verify(token)
    except AuthFailure as failure:
        detail = {"auth_expired": "The access token expired. Refresh it and retry once.",
                  "auth_unavailable": "Identity verification is unavailable."}.get(
            failure.code, "The credential is not valid for this application.")
        raise auth_error(failure.status, failure.code, detail) from None
    did = claims["sub"]
    try:
        with request.app.state.session_factory() as session:
            session.execute(pg_insert(User).values(id=uuid.uuid4(), privy_did=did)
                            .on_conflict_do_nothing(index_elements=[User.privy_did]))
            user_id = session.execute(select(User.id).where(User.privy_did == did)).scalar_one()
            session.commit()
    except DataError:  # a signed subject the database cannot store (for example U+0000) is a bad credential
        raise auth_error(401, "auth_invalid", "The credential is not valid for this application.") from None
    except SQLAlchemyError:
        raise service_unavailable() from None
    return Principal(user_id=user_id, privy_did=did)
