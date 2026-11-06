"""Prove that the worker's only default route is the declared egress gateway.

Coolify attaches its own resource network to every container in the Compose application. A higher Compose
`priority` on the declared network keeps that extra network off the default route, but only the running
container can prove it. This module reads Linux `/proc/net/route`; the worker refuses controlled mode before
it reads a key, and the worker healthcheck runs the same check on every probe.

The route table is Linux-only. Destination `00000000` is a default route and its gateway is written as
little-endian hexadecimal (`0100CB0A` is `10.203.0.1`). An unreadable table is a refusal, not a pass.
"""
from __future__ import annotations

from pathlib import Path

from edge_os_api.execution.released_execution_bootstrap import ExecutionBootstrapRefused

ROUTE_TABLE = "/proc/net/route"
DEFAULT_DESTINATION = "00000000"
# The `egress` bridge is 10.203.0.0/28, so its gateway is 10.203.0.1. `hostdb` is 10.203.0.16/28 (10.203.0.17).
EGRESS_GATEWAY = "10.203.0.1"
ROUTE_UNREADABLE = "EXECUTION_BOOTSTRAP_ROUTE_UNREADABLE"
ROUTE_UNEXPECTED = "EXECUTION_BOOTSTRAP_ROUTE_UNEXPECTED"


def _ipv4(gateway_hex: str) -> str | None:
    """Decode one /proc/net/route gateway field (little-endian hexadecimal), or None when it is not a word."""
    try:
        raw = int(gateway_hex, 16)
    except (TypeError, ValueError):
        return None
    if raw < 0 or raw > 0xFFFFFFFF:
        return None
    return ".".join(str((raw >> (8 * octet)) & 0xFF) for octet in range(4))


def default_gateways(route_text: str) -> tuple[str, ...]:
    """Every IPv4 default gateway in a /proc/net/route table, in file order."""
    gateways = []
    for line in route_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 3 or fields[1] != DEFAULT_DESTINATION:
            continue
        gateway = _ipv4(fields[2])
        if gateway is not None:
            gateways.append(gateway)
    return tuple(gateways)


def unexpected_default_gateways(route_text: str, expected: str = EGRESS_GATEWAY) -> tuple[str, ...]:
    """Default gateways other than the declared one. Any entry means the container has another route out."""
    return tuple(gateway for gateway in default_gateways(route_text) if gateway != expected)


def default_route_is_declared(route_text: str, expected: str = EGRESS_GATEWAY) -> bool:
    """True only when at least one default route exists and every default route uses the declared gateway."""
    return bool(default_gateways(route_text)) and not unexpected_default_gateways(route_text, expected)


def read_route_table(path: str = ROUTE_TABLE) -> str:
    return Path(path).read_text(encoding="ascii")


def require_declared_egress_default(route_text: str | None = None, expected: str = EGRESS_GATEWAY) -> None:
    """Refuse with a stable code unless the only default route is the declared egress gateway."""
    if route_text is None:
        try:
            route_text = read_route_table()
        except OSError:
            raise ExecutionBootstrapRefused(ROUTE_UNREADABLE) from None
    if not default_route_is_declared(route_text, expected):
        raise ExecutionBootstrapRefused(ROUTE_UNEXPECTED)
