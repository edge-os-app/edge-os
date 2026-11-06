"""The worker refuses controlled mode when a second default route exists.

Coolify attaches its own resource network to every container. A higher Compose `priority` keeps it off the default
route, but the route is only proved at runtime: the worker reads Linux `/proc/net/route` before it reads a key, and
the compose healthchecks run the same check inside the worker and PostgreSQL containers.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from edge_os_api.execution import network_route
from edge_os_api.execution.released_execution_bootstrap import ExecutionBootstrapRefused
from edge_os_api.execution.worker import build_worker_ports

HEADER = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT"
EGRESS_DEFAULT = "0100CB0A"  # 10.203.0.1, little-endian
HOSTDB_DEFAULT = "1100CB0A"  # 10.203.0.17, little-endian


def row(gateway: str, iface: str = "eth0", destination: str = "00000000") -> str:
    return f"{iface}\t{destination}\t{gateway}\t0003\t0\t0\t0\t00000000\t0\t0\t0"


def table(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


def test_a_default_gateway_is_parsed_little_endian():
    assert network_route.default_gateways(table(row(EGRESS_DEFAULT))) == ("10.203.0.1",)
    assert network_route.default_gateways(table(row(HOSTDB_DEFAULT))) == ("10.203.0.17",)


def test_non_default_routes_are_not_default_gateways():
    text = table(row("0101A8C0", destination="0000A8C0"), row(EGRESS_DEFAULT))
    assert network_route.default_gateways(text) == ("10.203.0.1",)
    assert network_route.default_route_is_declared(text) is True


def test_one_egress_default_route_is_declared():
    assert network_route.default_route_is_declared(table(row(EGRESS_DEFAULT))) is True


def test_a_second_default_route_is_unexpected():
    text = table(row(EGRESS_DEFAULT), row("0200CB0A", iface="eth1"))
    assert network_route.unexpected_default_gateways(text) == ("10.203.0.2",)
    assert network_route.default_route_is_declared(text) is False


def test_a_wrong_default_gateway_is_unexpected():
    text = table(row(HOSTDB_DEFAULT))
    assert network_route.unexpected_default_gateways(text) == ("10.203.0.17",)


def test_no_default_route_is_unexpected():
    assert network_route.default_route_is_declared(HEADER + "\n") is False


def test_an_unreadable_route_table_refuses(monkeypatch):
    def unreadable() -> str:
        raise OSError("no /proc/net/route")

    monkeypatch.setattr(network_route, "read_route_table", unreadable)
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        network_route.require_declared_egress_default()
    assert refused.value.code == "EXECUTION_BOOTSTRAP_ROUTE_UNREADABLE"


def test_the_guard_refuses_an_extra_default_route(monkeypatch):
    monkeypatch.setattr(network_route, "read_route_table",
                        lambda: table(row(EGRESS_DEFAULT), row(HOSTDB_DEFAULT)))
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        network_route.require_declared_egress_default()
    assert refused.value.code == "EXECUTION_BOOTSTRAP_ROUTE_UNEXPECTED"


def test_the_worker_refuses_controlled_mode_before_reading_the_key(monkeypatch):
    """A production worker with the injected network as a second default route never composes a runtime."""
    monkeypatch.setattr(network_route, "read_route_table",
                        lambda: table(row(EGRESS_DEFAULT), row(HOSTDB_DEFAULT)))
    settings = SimpleNamespace(env="production", execution_mode="controlled")
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build_worker_ports(settings, None, environ={})
    assert refused.value.code == "EXECUTION_BOOTSTRAP_ROUTE_UNEXPECTED"


def test_the_worker_continues_past_the_route_guard_when_the_route_is_declared(monkeypatch):
    monkeypatch.setattr(network_route, "read_route_table", lambda: table(row(EGRESS_DEFAULT)))
    settings = SimpleNamespace(env="production", execution_mode="controlled")
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build_worker_ports(settings, None, environ={})
    assert refused.value.code == "EXECUTION_BOOTSTRAP_APP_ID_MISSING"
