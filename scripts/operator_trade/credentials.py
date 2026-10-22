"""Live credentials come only from named environment variables.

The trade file pins public identifiers. The Privy app id, app secret and the agent P-256 key file
are read from ``EDGE_OS_PRIVY_APP_ID``, ``EDGE_OS_PRIVY_APP_SECRET`` and
``EDGE_OS_PRIVY_AGENT_KEY_FILE``. The RPC URL comes from ``EDGE_OS_OPERATOR_RPC_URL``. No value is
printed, journaled or stored in the result.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization

from edge_os_api.execution.privy_signer import PrivySignerClient, make_p256_authorizer

from scripts.operator_trade.errors import OperatorError

ENV_RPC_URL = "EDGE_OS_OPERATOR_RPC_URL"
ENV_APP_ID = "EDGE_OS_PRIVY_APP_ID"
ENV_APP_SECRET = "EDGE_OS_PRIVY_APP_SECRET"
ENV_KEY_FILE = "EDGE_OS_PRIVY_AGENT_KEY_FILE"
REQUIRED_LIVE_ENV = (ENV_RPC_URL, ENV_APP_ID, ENV_APP_SECRET, ENV_KEY_FILE)
REQUEST_EXPIRY_MS = 300_000


@dataclass(frozen=True)
class LiveEnvironment:
    rpc_url: str
    app_id: str
    app_secret: str
    key_file: Path


def load_live_environment(environ: Mapping[str, str]) -> LiveEnvironment:
    missing = [name for name in REQUIRED_LIVE_ENV if not environ.get(name)]
    if missing:
        raise OperatorError("ENV_MISSING", ",".join(missing))
    key_file = Path(environ[ENV_KEY_FILE])
    if not key_file.is_file():
        raise OperatorError("KEY_FILE_UNREADABLE", key_file.name)
    return LiveEnvironment(rpc_url=environ[ENV_RPC_URL], app_id=environ[ENV_APP_ID],
                           app_secret=environ[ENV_APP_SECRET], key_file=key_file)


def load_private_key(path: Path) -> Any:
    try:
        return serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    except Exception as error:  # noqa: BLE001 - the key file text is never copied into an error
        raise OperatorError("KEY_FILE_INVALID", Path(path).name) from error


def build_signer_factory(environment: LiveEnvironment, transport: Any,
                         clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
                         monotonic: Callable[[], float] = time.monotonic) -> Callable[[str, int], PrivySignerClient]:
    authorize = make_p256_authorizer(private_key=load_private_key(environment.key_file))

    def factory(step: str, nonce: int) -> PrivySignerClient:
        return PrivySignerClient(
            app_id=environment.app_id,
            app_secret=environment.app_secret,
            authorize=authorize,
            request_id=f"operator-trade-{uuid.uuid4().hex}",
            request_expiry_ms=clock_ms() + REQUEST_EXPIRY_MS,
            http=transport,
            connect_timeout_seconds=30.0,
            deadline_monotonic=monotonic() + 60.0,
            max_response_bytes=65_536,
        )

    return factory
