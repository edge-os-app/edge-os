"""Test-only token signing. The key exists in memory (or a run-scoped file) and is never trusted by production."""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from harness import TEST_APP_ID

OWNER_A = "did:privy:test-owner-a"
OWNER_B = "did:privy:test-owner-b"


class TestSigner:
    __test__ = False

    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())

    @property
    def public_pem(self) -> str:
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    @property
    def private_pem(self) -> str:
        return self.private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()

    def claims(self, sub: str = OWNER_A, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {"sub": sub, "sid": "test-session-1", "iss": "privy.io", "aud": TEST_APP_ID,
                                  "iat": now, "exp": now + 3600}
        claims.update(overrides)
        return {k: v for k, v in claims.items() if v is not DROP}

    def token(self, sub: str = OWNER_A, *, headers: dict[str, Any] | None = None, **overrides: Any) -> str:
        return jwt.encode(self.claims(sub, **overrides), self.private_key, algorithm="ES256", headers=headers)


DROP = object()

