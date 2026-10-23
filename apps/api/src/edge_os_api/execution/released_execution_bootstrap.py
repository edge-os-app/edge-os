"""The controlled execution runtime the worker composes from worker-only settings and one approved release.

Only the worker process builds this runtime. The API process never calls this module, and `role="api"` is
refused before any setting, file or key is read, so the API never receives a signer. The runtime exists only
for a release that `execution.operating_release.APPROVED_ACTUAL_RELEASES` approves and a binding that
`APPROVED_ACTUAL_BINDINGS` approves; both registries are empty today, so the worker refuses with a named reason.
This module never writes either registry and never builds a runtime from an environment value alone.

The five settings are worker-only environment values (not `Settings` fields, so the API configuration cannot
carry them):

- ``EDGE_OS_EXECUTION_PRIVY_APP_ID``
- ``EDGE_OS_EXECUTION_PRIVY_APP_SECRET``
- ``EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH`` (absolute path, regular file, own uid, no group/other bits)
- ``EDGE_OS_EXECUTION_SERVER_WALLET_ID``
- ``EDGE_OS_EXECUTION_MONAD_RPC_URL``

`env != "local"` is refused here. Production execution stays behind the separate hosted-record-v2 gate.
Construction reads the key file only after a release and binding are admitted; it opens no socket and reads no
`.env`, credential slot or agent key. See `docs/qualification/inapp-trade/INAPP_TRADE_RELEASE.md`.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from edge_os_api.core.provider_ports import ControlledRuntime, utc_now
from edge_os_api.core.settings import Settings
from edge_os_api.execution.operating_release import (
    APPROVED_ACTUAL_BINDINGS,
    APPROVED_ACTUAL_RELEASES,
    BoundRelease,
    OperatingRelease,
    ReleaseRefused,
    release_sha256,
)
from edge_os_api.execution.original_transaction import TradeSteps
from edge_os_api.execution.privy_signer import make_p256_authorizer
from edge_os_api.research_history.http_clients import StdlibHttpTransport
from edge_os_api.research_history.http_clients.http_transport import HttpTransport

WORKER_ROLE = "worker"
LOCAL_ENV = "local"
APP_ID_SETTING = "EDGE_OS_EXECUTION_PRIVY_APP_ID"
APP_SECRET_SETTING = "EDGE_OS_EXECUTION_PRIVY_APP_SECRET"
KEY_PATH_SETTING = "EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH"
WALLET_ID_SETTING = "EDGE_OS_EXECUTION_SERVER_WALLET_ID"
RPC_URL_SETTING = "EDGE_OS_EXECUTION_MONAD_RPC_URL"
IDENTITY_KEYS = ("owner_id", "agent_id", "consent_adoption_id")
# The same accepted shape `PrivySignerClient` enforces when it constructs the signer.
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")


class ExecutionBootstrapRefused(RuntimeError):
    """A stable pre-I/O refusal. It carries one code and no setting value, path or key material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class WorkerExecutionSettings:
    """The worker-only values, validated but not used until a release and binding are admitted."""

    privy_app_id: str
    privy_app_secret: str
    authorization_key_path: Path
    server_wallet_id: str
    monad_rpc_url: str


@dataclass(frozen=True)
class ReleaseCandidate:
    """A code-owned release object and its saved-identity binding. Registration stays a reviewed code change."""

    release: OperatingRelease
    binding: BoundRelease
    # The exact step plan reviewed with this release. It never comes from an environment value.
    steps: TradeSteps | None = None


@dataclass(frozen=True)
class WorkerExecutionRuntime:
    """One runtime, keyed by the agent id its binding names."""

    agent_id: str
    runtime: ControlledRuntime

    @property
    def ports(self) -> Mapping[str, ControlledRuntime]:
        return MappingProxyType({self.agent_id: self.runtime})


# Code-owned candidates. A candidate becomes live only when both approved registries name its exact hashes.
# The A2 release objects are added here in the reviewed registration change, never from a setting or environment.
RELEASE_CANDIDATES: tuple[ReleaseCandidate, ...] = ()


def _printable(value: str) -> bool:
    return bool(value) and all("!" <= character <= "~" for character in value)


def _required(source: Mapping[str, str], name: str, missing: str) -> str:
    value = source.get(name)
    if value is None or not value.strip():
        raise ExecutionBootstrapRefused(missing)
    return value


def read_worker_execution_settings(environ: Mapping[str, str] | None = None) -> WorkerExecutionSettings:
    """Read the worker-only values. Every missing or malformed value has its own refusal code."""
    source = os.environ if environ is None else environ
    app_id = _required(source, APP_ID_SETTING, "EXECUTION_BOOTSTRAP_APP_ID_MISSING")
    if _IDENTIFIER.fullmatch(app_id) is None:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_APP_ID_INVALID")
    app_secret = _required(source, APP_SECRET_SETTING, "EXECUTION_BOOTSTRAP_APP_SECRET_MISSING")
    if not _printable(app_secret):
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_APP_SECRET_INVALID")
    raw_path = _required(source, KEY_PATH_SETTING, "EXECUTION_BOOTSTRAP_KEY_PATH_MISSING")
    if not raw_path.startswith("/") or "\x00" in raw_path or len(raw_path) > 4096:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_PATH_INVALID")
    wallet_id = _required(source, WALLET_ID_SETTING, "EXECUTION_BOOTSTRAP_WALLET_ID_MISSING")
    if _IDENTIFIER.fullmatch(wallet_id) is None:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_WALLET_ID_INVALID")
    rpc_url = _required(source, RPC_URL_SETTING, "EXECUTION_BOOTSTRAP_RPC_URL_MISSING")
    parts = urlsplit(rpc_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.fragment):
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_RPC_URL_INVALID")
    return WorkerExecutionSettings(privy_app_id=app_id, privy_app_secret=app_secret,
                                   authorization_key_path=Path(raw_path), server_wallet_id=wallet_id,
                                   monad_rpc_url=rpc_url)


def load_authorization_key(path: Path) -> ec.EllipticCurvePrivateKey:
    """Load the P-256 authorization key only from an owner-only regular file owned by this process's user."""
    try:
        info = path.stat()
    except OSError:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_FILE_UNREADABLE") from None
    if not stat.S_ISREG(info.st_mode):
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_FILE_UNREADABLE")
    if info.st_uid != os.geteuid():
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_FILE_NOT_OWNED")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_FILE_NOT_OWNER_ONLY")
    try:
        raw = path.read_bytes()
    except OSError:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_FILE_UNREADABLE") from None
    try:
        key = load_pem_private_key(raw, password=None)
    except Exception:  # noqa: BLE001 - an unreadable key is refused; its text is not kept
        key = None
    finally:
        del raw
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_KEY_INVALID")
    return key


def _admitted_candidate(candidates: tuple[ReleaseCandidate, ...], approvals: Mapping[str, str],
                        bindings: Mapping[str, str]) -> ReleaseCandidate:
    if not approvals:
        raise ExecutionBootstrapRefused("EXECUTION_RELEASE_NOT_APPROVED")
    if not bindings:
        raise ExecutionBootstrapRefused("EXECUTION_BINDING_NOT_APPROVED")
    admitted = []
    for candidate in candidates:
        digest = release_sha256(candidate.release)
        if (approvals.get(candidate.release.content()["release_id"]) == digest
                and bindings.get(candidate.binding.sha256) == digest):
            admitted.append(candidate)
    if not admitted:
        for candidate in candidates:
            digest = release_sha256(candidate.release)
            if approvals.get(candidate.release.content()["release_id"]) == digest:
                raise ExecutionBootstrapRefused("EXECUTION_BINDING_NOT_APPROVED")
        raise ExecutionBootstrapRefused("EXECUTION_RELEASE_NOT_APPROVED")
    if len(admitted) != 1:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_MULTIPLE_RELEASES")
    return admitted[0]


def _check_identity(binding: BoundRelease, settings: WorkerExecutionSettings,
                    expected: Mapping[str, str] | None) -> dict[str, str]:
    identity, release = binding.identity(), binding.release.content()
    if expected is not None and any(expected.get(key) != identity.get(key) for key in IDENTITY_KEYS):
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_IDENTITY_MISMATCH")
    if identity["wallet_id"] != settings.server_wallet_id or identity["wallet_address"] != release["wallet_address"]:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_WALLET_MISMATCH")
    return identity


def build_worker_execution_runtime(*, role: str, settings: Settings,
                                   candidates: tuple[ReleaseCandidate, ...] | None = None,
                                   environ: Mapping[str, str] | None = None,
                                   approvals: Mapping[str, str] | None = None,
                                   bindings: Mapping[str, str] | None = None,
                                   expected_identity: Mapping[str, str] | None = None,
                                   http: HttpTransport | None = None,
                                   clock: Callable[[], dt.datetime] = utc_now) -> WorkerExecutionRuntime:
    """Build the one controlled runtime, or refuse with a named reason. Reads no key before admission."""
    if role != WORKER_ROLE:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_ROLE_NOT_WORKER")
    if settings.env != LOCAL_ENV:
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_ENV_NOT_LOCAL")
    if (approvals is None) != (bindings is None):
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_APPROVAL_SEAM_INCOMPLETE")
    worker = read_worker_execution_settings(environ)
    approval_map = APPROVED_ACTUAL_RELEASES if approvals is None else approvals
    binding_map = APPROVED_ACTUAL_BINDINGS if bindings is None else bindings
    candidate = _admitted_candidate(RELEASE_CANDIDATES if candidates is None else candidates,
                                    approval_map, binding_map)
    identity = _check_identity(candidate.binding, worker, expected_identity)
    content = candidate.release.content()
    if candidate.steps is not None:
        from edge_os_api.execution.operating_release import release_steps

        steps, route = candidate.steps, content["route"]
        if (release_steps(candidate.release) != steps.order
                or steps.input_asset_id != route["input_asset"]["asset_id"]
                or steps.gas_limits["swap"] != content["gas"]["gas_limit"]):
            raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_STEPS_MISMATCH")
    if content["quote"].get("source") != "DIRECT_V2_PROGRAM":
        # The approved release fixes every endpoint; a quote token has no worker setting, so a token-bearing
        # release cannot be composed here.
        raise ExecutionBootstrapRefused("EXECUTION_BOOTSTRAP_QUOTE_TOKEN_UNAVAILABLE")
    synthetic = binding_map if approvals is not None else None
    try:
        candidate.binding.admit(identity, now=clock(), synthetic_bindings=synthetic)
    except ReleaseRefused as refused:
        raise ExecutionBootstrapRefused(str(refused)) from None
    authorize = make_p256_authorizer(private_key=load_authorization_key(worker.authorization_key_path))

    def signer_access() -> Mapping[str, Any]:
        return {"app_id": worker.privy_app_id, "app_secret": worker.privy_app_secret, "authorize": authorize}

    runtime = ControlledRuntime(binding=candidate.binding, http=StdlibHttpTransport() if http is None else http,
                                quote_token=None, signer_access=signer_access, clock=clock,
                                synthetic_bindings=synthetic, steps=candidate.steps)
    return WorkerExecutionRuntime(agent_id=identity["agent_id"], runtime=runtime)
