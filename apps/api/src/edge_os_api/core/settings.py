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
    # Optional absolute path of the private Unix socket served by the separate trusted wallet-lookup process
    # (scripts/privy_wallet_lookup). It is not a credential. Only with `wallet_provider=unavailable`: the browser
    # creates and the socket answers one owner-bound lookup. Unset keeps the fixture/unavailable behavior.
    wallet_lookup_socket: str | None = None
    # `fixture` composes the financial journey over authored local provider fixtures: deposit observations,
    # market observations, action quotes, holdings, submission/receipt effects and removal observations, plus a
    # server-owned fixture qualification that lets an adopted INACTIVE consent drive a fixture action. Production
    # refuses it. `unavailable` keeps every provider port fail-closed, so no funded action can run.
    execution_mode: Literal["fixture", "unavailable"] = "unavailable"
    # Fixture mode only: an append-only file that records each authored submission effect outside the
    # application database, so a restarted process reconciles the original action and a verifier counts effects
    # independently. Without it the fixture keeps effects in process memory.
    fixture_effects_path: str | None = None
    # Local and test only: a directory with the AUTHORED original-transaction recordings. Fixture agents carrying
    # the reserved `fx-original` marker then use the recorded original-transaction clients. Production refuses it.
    original_recordings_dir: str | None = None
    # `recorded` serves the authored SYNTHETIC recorded-response history bundle to owner investigation jobs. Production
    # refuses it. `unavailable` refuses every history collection. No setting selects an actual provider source.
    research_history_mode: Literal["recorded", "unavailable"] = "unavailable"
    # Local and test only (#58 RESEARCH-PORTS-LOCAL). `authored_http` runs the native-shaped HTTP source through the
    # accepted P07 HTTP clients over the application's AUTHORED transport; `recorded` keeps the recorded clients.
    # `authored_fixture` runs Nansen report jobs over the AUTHORED Nansen transport. No setting names an endpoint,
    # a credential or a transport; production refuses both local modes.
    research_source_clients: Literal["recorded", "authored_http"] = "recorded"
    nansen_research_mode: Literal["unavailable", "authored_fixture"] = "unavailable"
    # Per-owner research capacity. A job reserves its declared bounds before any adapter effect; unknown usage keeps
    # its whole reservation as liability.
    research_budget_provider_requests: int = Field(default=16, ge=0, le=10000)
    research_budget_compute_seconds: int = Field(default=900, ge=0, le=86400)
    research_budget_nansen_credits: int = Field(default=50, ge=0, le=100000)
    # Global capacity shared by every owner. Owner and global caps are frozen in `usage_local` at first use; a
    # different value here later pauses new reservations (`quota_cap_mismatch`) until an operator records a change.
    usage_global_provider_requests: int = Field(default=100000, ge=0, le=10_000_000)
    usage_global_compute_seconds: int = Field(default=10_000_000, ge=0, le=1_000_000_000)
    usage_global_nansen_credits: int = Field(default=10_000, ge=0, le=10_000_000)
    # Runtime bounds shared by every API process: writes per owner per minute (PostgreSQL windows), research jobs an
    # owner may have waiting or running at once, and the longest single SQL statement.
    write_rate_per_minute: int = Field(default=600, ge=1, le=100_000)
    research_max_active_jobs: int = Field(default=10, ge=1, le=1000)
    database_statement_timeout_ms: int = Field(default=30_000, ge=1000, le=600_000)

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
        if self.env == "production":
            # Names only: no message repeats a configured value, key or token.
            if not (self.build_sha or "").strip():
                problems.append("build_sha: production needs the exact build identity")
            if url.host in {"127.0.0.1", "localhost", None}:
                problems.append("database_url: production needs a hosted database, not a loopback host")
            if url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
                problems.append("database_url: production needs sslmode=require or stricter")
            if self.fixture_effects_path is not None:
                problems.append("fixture_effects_path: fixture effects are refused in production")
        if self.env == "production" and self.interpreter != "fixture":
            problems.append("interpreter: only the fixture interpreter is available in production")
        if self.env == "production" and self.wallet_provider != "unavailable":
            problems.append("wallet_provider: only the unavailable provider is allowed in production")
        if self.wallet_lookup_socket is not None:
            if self.wallet_provider != "unavailable":
                problems.append("wallet_lookup_socket: only with the unavailable wallet provider")
            if not (self.wallet_lookup_socket.startswith("/") and ".." not in self.wallet_lookup_socket.split("/")
                    and len(self.wallet_lookup_socket) <= 100 and "\x00" not in self.wallet_lookup_socket):
                problems.append("wallet_lookup_socket: must be a short absolute path without '..'")
        if self.env == "production" and self.execution_mode != "unavailable":
            problems.append("execution_mode: only the unavailable execution mode is allowed in production")
        if self.env == "production" and self.research_history_mode != "unavailable":
            problems.append("research_history_mode: recorded synthetic history is refused in production")
        if self.env == "production" and self.research_source_clients != "recorded":
            problems.append("research_source_clients: the authored HTTP transport is refused in production")
        if self.env == "production" and self.nansen_research_mode != "unavailable":
            problems.append("nansen_research_mode: the authored Nansen transport is refused in production")
        if self.fixture_effects_path is not None and self.execution_mode != "fixture":
            problems.append("fixture_effects_path: only the fixture execution mode records fixture effects")
        if self.original_recordings_dir is not None and (self.env == "production" or self.execution_mode != "fixture"):
            problems.append("original_recordings_dir: authored original recordings are local fixture mode only")
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
