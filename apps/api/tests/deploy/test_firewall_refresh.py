"""The refresh unit filters exactly the addresses the worker and PostgreSQL hold on undeclared networks.

The script runs on the host after Docker exists. These tests replace every privileged command with a stub in a
temporary PATH; no daemon, rule, container or network is touched.
"""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import deploy_support as support

SCRIPT = support.REPO / "deploy" / "host" / "edge-os-egress-firewall.sh"
INJECTED_NETWORK = "w2d8bizjdeweqxxoaqcjobqo"
DECLARED = {
    "execution-worker": [("edge-os_private", "10.203.0.100"), ("edge-os_egress", "10.203.0.2")],
    "postgres": [("edge-os_private", "10.203.0.101"), ("edge-os_hostdb", "10.203.0.18")],
}


def stub(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def docker_stub(*, worker: list[tuple[str, ...]], postgres: list[tuple[str, ...]],
                missing: tuple[str, ...] = (), no_containers: bool = False,
                docker_down: bool = False) -> str:
    def rows(pairs: list[tuple[str, ...]]) -> str:
        return " ".join("'" + " ".join(pair) + " '" for pair in pairs)

    worker_ps = "" if "execution-worker" in missing else "echo workerid"
    postgres_ps = "" if "postgres" in missing else "echo postgresid"
    all_ps = "" if no_containers else "echo workerid; echo postgresid"
    return f"""echo "docker $*" >> "$STUB_LOG"
case "$1" in
  info) {("exit 1" if docker_down else "exit 0")} ;;
  ps)
    case "$*" in
      *"com.docker.compose.service=execution-worker"*) {worker_ps} ;;
      *"com.docker.compose.service=postgres"*) {postgres_ps} ;;
      *"--all"*) {all_ps} ;;
      *) exit 0 ;;
    esac ;;
  inspect)
    for a do last=$a; done
    case "$last" in
      workerid) printf '%s\\n' {rows(worker)} ;;
      postgresid) printf '%s\\n' {rows(postgres)} ;;
      *) exit 1 ;;
    esac ;;
esac
exit 0
"""


def run_refresh(tmp_path: Path, *, worker_extra=(), postgres_extra=(), missing=(), no_containers=False,
                docker_down=False):
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")
    stub(binaries, "docker", docker_stub(
        worker=[*DECLARED["execution-worker"], *worker_extra],
        postgres=[*DECLARED["postgres"], *postgres_extra], missing=missing, no_containers=no_containers,
        docker_down=docker_down))
    stub(binaries, "iptables", 'echo "iptables $*" >> "$STUB_LOG"\n'
                               'case " $* " in *" -D "*) exit 1 ;; esac\nexit 0\n')
    stub(binaries, "ipset", 'echo "ipset $*" >> "$STUB_LOG"\nexit 0\n')
    stub(binaries, "conntrack", 'echo "conntrack $*" >> "$STUB_LOG"\n'
                                'echo "0 flow entries have been deleted." >&2\nexit 1\n')
    stub(binaries, "getent", 'echo "1.2.3.4 STREAM api.example"\n')
    stub(binaries, "flock", "exit 0\n")
    config = tmp_path / "egress.env"
    config.write_text(
        'EDGE_OS_EGRESS_HOSTS="api.example"\nEDGE_OS_EGRESS_RELAY_HOSTS=""\nEDGE_OS_EGRESS_PORTS="443"\n'
        'EDGE_OS_COMPOSE_PROJECT="edge-os"\n', encoding="utf-8")
    completed = subprocess.run(
        ["sh", str(SCRIPT), "refresh"], capture_output=True, text=True, timeout=60,
        env={"PATH": f"{binaries}:/usr/bin:/bin", "HOME": str(tmp_path), "EDGE_OS_EGRESS_CONFIG": str(config),
             "EDGE_OS_EGRESS_LOCK": str(tmp_path / "lock"), "STUB_LOG": str(log)})
    return completed, log.read_text(encoding="utf-8")


def test_refresh_drops_only_the_addresses_on_undeclared_networks(tmp_path):
    completed, commands = run_refresh(
        tmp_path, worker_extra=[(INJECTED_NETWORK, "10.0.2.5")],
        postgres_extra=[(INJECTED_NETWORK, "10.0.2.6")])
    assert completed.returncode == 0, completed.stderr
    inbound = commands.split("EDGE_OS_BYPASS_IN", 1)[1]
    for address in ("10.0.2.5", "10.0.2.6"):
        assert f"-s {address} -j DROP" in commands
        assert f"-d {address} -j DROP" in commands
        assert f"-s {address} -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT" in inbound
        assert f"-s {address} -j DROP" in inbound
        assert f"conntrack -D -s {address}" in commands
    for declared in ("10.203.0.100", "10.203.0.2", "10.203.0.101", "10.203.0.18"):
        assert f"-s {declared}" not in commands
    assert "-I DOCKER-USER 1 -j EDGE_OS_BYPASS_" in commands
    assert "-I INPUT 1 -j EDGE_OS_BYPASS_IN_" in commands


def test_refresh_is_a_no_op_before_the_stack_exists(tmp_path):
    completed, commands = run_refresh(tmp_path, no_containers=True)
    assert completed.returncode == 0, completed.stderr
    assert "no containers in compose project edge-os" in completed.stderr
    assert "-I DOCKER-USER 1 -j EDGE_OS_BYPASS_" in commands


def test_refresh_fails_loudly_when_a_protected_container_is_missing(tmp_path):
    completed, _ = run_refresh(tmp_path, missing=("postgres",))
    assert completed.returncode != 0
    assert "cannot find a running postgres container" in completed.stderr


def test_refresh_fails_loudly_on_an_ipv6_address_on_the_extra_network(tmp_path):
    completed, _ = run_refresh(
        tmp_path, worker_extra=[(INJECTED_NETWORK, "10.0.2.5", "fd00::5")])
    assert completed.returncode != 0
    assert "IPv6" in completed.stderr


def test_refresh_fails_loudly_when_the_daemon_is_unreachable(tmp_path):
    completed, _ = run_refresh(tmp_path, docker_down=True)
    assert completed.returncode != 0
    assert "docker daemon is unreachable" in completed.stderr
