"""Typed startup configuration. Errors name fields and never print values."""

from __future__ import annotations

import functools
import os
import subprocess
from typing import Literal

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

TEST_APP_ID = "edge-os-test-app"
FORBIDDEN_ENV_NAMES = ("EDGE_OS_PRIVY_APP_SECRET", "EDGE_OS_AUTH_DISABLED", "EDGE_OS_DEV_AUTH_BYPASS")


class ConfigError(RuntimeError):
    """Raised at startup. The message lists field names only."""


def parse_public_key(pem: str) -> ec.EllipticCurvePublicKey:
    key = load_pem_public_key(pem.replace("\\n", "\n").encode("utf-8"))
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise ValueError("verification key must be an EC P-256 public key")
    return key


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDGE_OS_", env_file=None, extra="ignore")

    env: Literal["local", "test", "production"]
    database_url: str
    privy_app_id: str
    privy_verification_key: str
    privy_verification_key_previous: str | None = None
    cors_allowed_origins: str
    build_sha: str | None = None

    @field_validator("privy_app_id")
    @classmethod
    def _app_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("privy_verification_key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        try:
            parse_public_key(value)
        except Exception as error:  # noqa: BLE001 - message must not echo key material
            raise ValueError("must load as an EC P-256 public key") from error
        return value

    @field_validator("privy_verification_key_previous")
    @classmethod
    def _previous_key(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None  # the previous key is optional; an empty value means none
        try:
            parse_public_key(value)
        except Exception as error:  # noqa: BLE001
            raise ValueError("must load as an EC P-256 public key") from error
        return value

    @field_validator("database_url")
    @classmethod
    def _db(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError as error:
            raise ValueError("must be a valid database URL") from error
        if url.drivername != "postgresql+psycopg":
            raise ValueError("must start with postgresql+psycopg://")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_allowed_origins.split(",") if item.strip()]

    @property
    def verification_keys(self) -> list[ec.EllipticCurvePublicKey]:
        keys = [parse_public_key(self.privy_verification_key)]
        if self.privy_verification_key_previous:
            keys.append(parse_public_key(self.privy_verification_key_previous))
        return keys

    def validate_rules(self) -> None:
        problems: list[str] = []
        if not self.cors_origins:
            problems.append("cors_allowed_origins: at least one origin is required")
        for origin in self.cors_origins:
            if origin == "*" or "*" in origin:
                problems.append("cors_allowed_origins: wildcard is not allowed")
            elif self.env == "production" and not origin.startswith("https://"):
                problems.append("cors_allowed_origins: production origins must use https")
        url = make_url(self.database_url)
        if self.env == "test":
            if url.host not in {"127.0.0.1", "localhost"}:
                problems.append("database_url: test host must be loopback")
            if not (url.database or "").startswith("edge_os_test_"):
                problems.append("database_url: test database name must start with edge_os_test_")
        if self.env == "production" and self.privy_app_id == TEST_APP_ID:
            problems.append("privy_app_id: the test app id is refused in production")
        if problems:
            raise ConfigError("invalid configuration: " + "; ".join(problems))

    @property
    def docs_enabled(self) -> bool:
        return self.env == "local"

    @functools.cached_property
    def resolved_build_sha(self) -> str:
        """Resolved once per process, so /healthz never spawns a process."""
        if self.build_sha:
            return self.build_sha
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  timeout=5, check=True).stdout.strip() or "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    source = os.environ if environ is None else environ
    forbidden = [name for name in FORBIDDEN_ENV_NAMES if name in source]
    if forbidden:
        raise ConfigError("unsupported configuration present: " + ", ".join(sorted(forbidden)))
    try:
        if environ is None:
            settings = Settings()  # type: ignore[call-arg]
        else:
            settings = Settings.model_validate(
                {k[len("EDGE_OS_"):].lower(): v for k, v in environ.items() if k.startswith("EDGE_OS_")})
    except ValidationError as error:
        fields = sorted({".".join(str(p) for p in item["loc"]) or "settings" for item in error.errors()})
        reasons = "; ".join(f"{'.'.join(str(p) for p in i['loc'])}: {i['type']}" for i in error.errors())
        raise ConfigError(f"invalid configuration fields: {', '.join(fields)} ({reasons})") from None
    settings.validate_rules()
    return settings
