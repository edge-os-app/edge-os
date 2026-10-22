"""The host-side socket proxy: its allow-list must be minimal and must cover every Docker call the runner makes."""

from __future__ import annotations

import re

import pytest

import deploy_support as support

RESEARCH = "socket-proxy-research"
RELAY = "socket-proxy-relay"
VERSION = r"(/v1\.[0-9]+)?"
CONTAINER = r"[A-Za-z0-9][A-Za-z0-9_.-]*"


@pytest.fixture(scope="module")
def proxy():
    return support.compose_model(str(support.HOST_PROXY_COMPOSE))


def _rules(proxy, name):
    return support.command_allow_rules(proxy["services"][name])


def _allowed(rules, method, path):
    return support.allows(rules, method, support.endpoint(method, path)[1])


RESEARCH_READ = VERSION + r"/_ping"
RESEARCH_CONTAINER = VERSION + r"/containers/" + CONTAINER


def test_the_proxy_runs_without_a_network_and_with_the_socket_read_only(proxy):
    for name in (RESEARCH, RELAY):
        service = proxy["services"][name]
        assert service["network_mode"] == "none"
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert "ports" not in service
        assert service["image"].startswith("${EDGE_OS_SOCKET_PROXY_IMAGE:?")
        socket = [mount for mount in support.mounts(service) if mount["target"] == "/var/run/docker.sock"]
        assert len(socket) == 1
        assert socket[0]["read_only"] is True
        assert service["group_add"] == ["${EDGE_OS_DOCKER_GID:?set EDGE_OS_DOCKER_GID to the group of /var/run/docker.sock}"]


def test_each_proxy_writes_an_owner_only_runtime_socket(proxy):
    for name in (RESEARCH, RELAY):
        service = proxy["services"][name]
        assert support.command_option(service, "proxysocketendpoint") == "/run/edge-os/docker.sock"
        assert support.command_option(service, "proxysocketendpointfilemode") == "0660"


def test_every_allow_rule_compiles(proxy):
    for name in (RESEARCH, RELAY):
        for method, patterns in _rules(proxy, name).items():
            assert patterns, method
            for pattern in patterns:
                re.compile(pattern)


def test_the_guarded_runner_uses_only_the_reviewed_verbs():
    text = support.GUARDED_RUNNER.read_text(encoding="utf-8")
    assert support.docker_verbs(text) == {"run", "inspect", "kill", "ps"}
    assert "PinnedHermesImage" not in text
    assert "build" not in support.docker_verbs(text)


def test_the_qualification_builder_stays_out_of_the_production_path():
    text = support.DOCKER_TURN_RUNNER.read_text(encoding="utf-8")
    assert support.docker_verbs(text) == {"build", "image", "rmi", "run", "inspect", "kill", "ps"}
    guarded = support.GUARDED_RUNNER.read_text(encoding="utf-8")
    assert "docker_turn_runner.PinnedHermesImage" not in guarded
    assert "PinnedHermesImage(" not in guarded


def test_the_research_proxy_allows_every_guarded_runner_call(proxy):
    rules = _rules(proxy, RESEARCH)
    required = [
        ("GET", "/_ping"),
        ("HEAD", "/_ping"),
        ("GET", "/v1.47/version"),
        ("GET", "/v1.47/info"),
        ("POST", "/v1.47/containers/create"),
        ("POST", "/v1.47/containers/p05-run-01-01/start"),
        ("POST", "/v1.47/containers/p05-run-01-01/attach"),
        ("POST", "/v1.47/containers/p05-run-01-01/wait"),
        ("POST", "/v1.47/containers/p05-run-01-01/kill"),
        ("GET", "/v1.47/containers/p05-run-01-01/json"),
        ("GET", "/v1.47/containers/p05-run-01-01/logs"),
        ("GET", "/v1.47/containers/json?all=1"),
        ("GET", "/v1.47/images/python:3.14-slim-trixie@sha256:" + "a" * 64 + "/json"),
    ]
    for method, path in required:
        assert _allowed(rules, method, path), f"{method} {path} is denied"


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1.47/containers/p05-run-01-01/exec"),
    ("POST", "/v1.47/build"),
    ("POST", "/v1.47/images/create?fromImage=x"),
    ("DELETE", "/v1.47/images/x"),
    ("POST", "/v1.47/networks/create"),
    ("DELETE", "/v1.47/networks/x"),
    ("POST", "/v1.47/volumes/create"),
    ("DELETE", "/v1.47/volumes/x"),
    ("DELETE", "/v1.47/containers/p05-run-01-01"),
])
def test_the_research_proxy_denies_every_extra_call(proxy, method, path):
    assert not _allowed(_rules(proxy, RESEARCH), method, path)


def test_the_research_proxy_limits_bind_mounts_to_its_two_roots(proxy):
    value = support.command_option(proxy["services"][RESEARCH], "allowbindmountfrom")
    assert value == "/opt/edge-os,/var/lib/edge-os/research"


def test_the_relay_runner_uses_only_the_reviewed_verbs():
    supervisor = support.RELAY_SUPERVISOR.read_text(encoding="utf-8")
    operator = support.RELAY_OPERATOR.read_text(encoding="utf-8")
    supervisor_verbs = support.docker_verbs(supervisor)
    supervisor_verbs.add("run")  # `_common` returns ["run", "-d", ...]
    assert 'return ["run", "-d"' in supervisor
    assert supervisor_verbs == {"run", "inspect", "exec", "logs", "kill", "rm", "ps", "network", "volume"}
    operator_verbs = support.docker_verbs(operator)
    for fragment in ('("rm", "-f")', '("ps", "-a")', '("network", "ls")', '("network", "rm")',
                     '("volume", "ls")', '("volume", "rm")'):
        assert fragment in operator
    assert operator_verbs == {"inspect", "image", "kill", "rm", "volume"}


def test_the_relay_proxy_allows_every_supervisor_and_operator_call(proxy):
    rules = _rules(proxy, RELAY)
    required = [
        ("GET", "/_ping"),
        ("HEAD", "/_ping"),
        ("GET", "/v1.47/version"),
        ("GET", "/v1.47/info"),
        ("POST", "/v1.47/containers/create"),
        ("POST", "/v1.47/containers/relay-run-01/start"),
        ("POST", "/v1.47/containers/relay-run-01/kill"),
        ("DELETE", "/v1.47/containers/relay-run-01"),
        ("GET", "/v1.47/containers/relay-run-01/json"),
        ("GET", "/v1.47/containers/relay-run-01/logs"),
        ("GET", "/v1.47/containers/json?all=1"),
        ("GET", "/v1.47/images/" + "a" * 64 + "/json"),
        ("POST", "/v1.47/networks/create"),
        ("DELETE", "/v1.47/networks/" + "a" * 64),
        ("GET", "/v1.47/networks?filters=x"),
        ("GET", "/v1.47/networks/" + "a" * 64),
        ("POST", "/v1.47/volumes/create"),
        ("DELETE", "/v1.47/volumes/relay-egress-run-01"),
        ("GET", "/v1.47/volumes?filters=x"),
        ("GET", "/v1.47/volumes/relay-egress-run-01"),
        ("POST", "/v1.47/containers/relay-run-01/exec"),
        ("POST", "/v1.47/exec/" + "a" * 64 + "/start"),
        ("GET", "/v1.47/exec/" + "a" * 64 + "/json"),
    ]
    for method, path in required:
        assert _allowed(rules, method, path), f"{method} {path} is denied"


@pytest.mark.parametrize("path", [
    "/v1.47/containers/postgres/exec",
    "/v1.47/containers/edge-os-api-1/exec",
    "/v1.47/containers/edge-os-socket-proxy-research/exec",
])
def test_the_relay_proxy_refuses_exec_into_a_foreign_container(proxy, path):
    assert not _allowed(_rules(proxy, RELAY), "POST", path)


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1.47/build"),
    ("POST", "/v1.47/images/create?fromImage=x"),
    ("POST", "/v1.47/containers/relay-run-01/attach"),
    ("POST", "/v1.47/swarm/init"),
    ("POST", "/v1.47/services/create"),
    ("DELETE", "/v1.47/containers/postgres"),
    ("DELETE", "/v1.47/networks/abc"),
    ("DELETE", "/v1.47/volumes/data"),
])
def test_the_relay_proxy_denies_every_extra_call(proxy, method, path):
    assert not _allowed(_rules(proxy, RELAY), method, path)


def test_the_relay_proxy_limits_bind_mounts_to_the_host_roots(proxy):
    value = support.command_option(proxy["services"][RELAY], "allowbindmountfrom")
    assert value == "/opt/edge-os,/var/lib/edge-os,/etc/edge-os/relay"


def test_the_proxies_are_not_reachable_over_tcp(proxy):
    for name in (RESEARCH, RELAY):
        service = proxy["services"][name]
        assert service["network_mode"] == "none"
        assert support.command_option(service, "listenip") is None
