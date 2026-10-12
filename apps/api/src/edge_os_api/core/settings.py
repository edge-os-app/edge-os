"""Typed startup configuration. Errors name fields and never print values."""

from __future__ import annotations

import functools
import os
import subprocess
from typing import Literal

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import Field, ValidationError, field_validator
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
    # `fixture` answers scripted requests only. `hermes_local` runs the pinned Hermes against a local fake provider and
    # needs a runner handed to the application factory. No setting reaches a real provider (decision D7).
    interpreter: Literal["fixture", "hermes_local"] = "fixture"
    # `fixture` uses the authored local wallet-creation fixture. Production refuses it and uses the
    # fail-closed `unavailable` provider, so no real wallet provider is configured yet.
    wallet_provider: Literal["fixture", "unavailable"] = "unavailable"
    # `fixture` composes the financial journey over authored local provider fixtures: deposit observations,
    # market observations, action quotes, holdings, submission/receipt effects and removal observations, plus a
    # server-owned fixture qualification that lets an adopted INACTIVE consent drive a fixture action. Production
    # refuses it. `unavailable` keeps every provider port fail-closed, so no funded action can run.
    execution_mode: Literal["fixture", "unavailable"] = "unavailable"
    # Fixture mode only: an append-only file that records each authored submission effect outside the
    # application database, so a restarted process reconciles the original action and a verifier counts effects
    # independently. Without it the fixture keeps effects in process memory.
    fixture_effects_path: str | None = None
    # `recorded` serves the authored SYNTHETIC recorded-response history bundle to owner investigation jobs. Production
    # refuses it. `unavailable` refuses every history collection. No setting selects an actual provider source.
    research_history_mode: Literal["recorded", "unavailable"] = "unavailable"
    # Per-owner research capacity. A job reserves its declared bounds before any adapter effect; unknown usage keeps
    # its whole reservation as liability.
    research_budget_provider_requests: int = Field(default=16, ge=0, le=10000)
    research_budget_compute_seconds: int = Field(default=900, ge=0, le=86400)
    # Global capacity shared by every owner. Owner and global caps are frozen in `usage_local` at first use; a
    # different value here later pauses reservations (`quota_cap_mismatch`) until an operator records a change.
    usage_global_provider_requests: int = Field(default=100000, ge=0, le=10_000_000)
    usage_global_compute_seconds: int = Field(default=10_000_000, ge=0, le=1_000_000_000)

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
        if self.env == "production" and self.interpreter != "fixture":
            problems.append("interpreter: only the fixture interpreter is available in production")
        if self.env == "production" and self.wallet_provider != "unavailable":
            problems.append("wallet_provider: only the unavailable provider is allowed in production")
        if self.env == "production" and self.execution_mode != "unavailable":
            problems.append("execution_mode: only the unavailable execution mode is allowed in production")
        if self.env == "production" and self.research_history_mode != "unavailable":
            problems.append("research_history_mode: recorded synthetic history is refused in production")
        if self.fixture_effects_path is not None and self.execution_mode != "fixture":
            problems.append("fixture_effects_path: only the fixture execution mode records fixture effects")
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
