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
PROJECT = "w2d8bizjdeweqxxoaqcjobqo"
def declared(project: str) -> dict[str, list[tuple[str, ...]]]:
    return {
        "execution-worker": [(f"{project}_private", "10.203.0.100"), (f"{project}_egress", "10.203.0.2")],
        "postgres": [(f"{project}_private", "10.203.0.101"), (f"{project}_hostdb", "10.203.0.18")],
    }


def stub(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def docker_stub(*, project: str, bridge_project: str | None, worker: list[tuple[str, ...]],
                postgres: list[tuple[str, ...]], missing: tuple[str, ...] = (),
                no_containers: bool = False, docker_down: bool = False,
                worker_lines: str | None = None, postgres_lines: str | None = None) -> str:
    def rows(pairs: list[tuple[str, ...]]) -> str:
        return " ".join("'" + "|".join((pair + ("", ""))[:3]) + "'" for pair in pairs)

    worker_rows = worker_lines or rows(worker)
    postgres_rows = postgres_lines or rows(postgres)
    worker_ps = "" if no_containers or "execution-worker" in missing else "echo workerid"
    postgres_ps = "" if no_containers or "postgres" in missing else "echo postgresid"
    networks = "" if bridge_project is None else (
        f"printf '%s\\n' 'edgeos-hostdb {bridge_project} ' 'edgeos-egress {bridge_project} ' "
        f"'edgeos-private {bridge_project} '")
    return f"""echo "docker $*" >> "$STUB_LOG"
case "$1" in
  info) {("exit 1" if docker_down else "exit 0")} ;;
  network)
    case "$2" in
      ls) {("" if bridge_project is None else "echo netid")} ;;
      inspect) {networks} ;;
    esac ;;
  ps)
    case "$*" in
      *"com.docker.compose.service=execution-worker"*) {worker_ps} ;;
      *"com.docker.compose.service=postgres"*) {postgres_ps} ;;
    esac ;;
  inspect)
    for a do last=$a; done
    case "$last" in
      workerid) data=$(printf '%s\\n' {worker_rows}) ;;
      postgresid) data=$(printf '%s\\n' {postgres_rows}) ;;
      *) exit 1 ;;
    esac
    case "$*" in *'|'*) ;; *) data=$(printf '%s\\n' "$data" | tr '|' ' ') ;; esac
    printf '%s\\n' "$data" ;;
esac
exit 0
"""


def run_refresh(tmp_path: Path, *, project: str = PROJECT, bridge_project: str | None = PROJECT,
                env_project: str | None = None, worker_extra=(), postgres_extra=(),
                missing=(), no_containers=False, docker_down=False,
                worker_lines: str | None = None, postgres_lines: str | None = None,
                bridge_module_ok: bool = True, bridge_sysctl_ok: bool = True,
                bridge_sysctl_value: str = "1"):
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")
    stub(binaries, "docker", docker_stub(
        project=project, bridge_project=bridge_project,
        worker=[*declared(project)["execution-worker"], *worker_extra],
        postgres=[*declared(project)["postgres"], *postgres_extra], missing=missing,
        no_containers=no_containers, docker_down=docker_down,
        worker_lines=worker_lines, postgres_lines=postgres_lines))
    stub(binaries, "iptables", 'echo "iptables $*" >> "$STUB_LOG"\n'
                               'case " $* " in *" -D "*) exit 1 ;; esac\nexit 0\n')
    stub(binaries, "ipset", 'echo "ipset $*" >> "$STUB_LOG"\nexit 0\n')
    stub(binaries, "conntrack", 'echo "conntrack $*" >> "$STUB_LOG"\n'
                                'echo "0 flow entries have been deleted." >&2\nexit 1\n')
    stub(binaries, "getent", 'echo "1.2.3.4 STREAM api.example"\n')
    stub(binaries, "flock", "exit 0\n")
    stub(binaries, "modprobe", 'echo "modprobe $*" >> "$STUB_LOG"\n'
                              + ("" if bridge_module_ok else
                                 'echo "modprobe: FATAL: Module br_netfilter not found" >&2\n')
                              + ("exit 0\n" if bridge_module_ok else "exit 1\n"))
    stub(binaries, "sysctl", 'echo "sysctl $*" >> "$STUB_LOG"\n'
                            f'case "$1" in\n'
                            f'  -n) echo "{bridge_sysctl_value}"; exit 0 ;;\n'
                            f'  -w) exit {0 if bridge_sysctl_ok else 1} ;;\n'
                            f'esac\nexit 0\n')
    config = tmp_path / "egress.env"
    config.write_text(
        'EDGE_OS_EGRESS_HOSTS="api.example"\nEDGE_OS_EGRESS_RELAY_HOSTS=""\nEDGE_OS_EGRESS_PORTS="443"\n',
        encoding="utf-8")
    environment = {"PATH": f"{binaries}:/usr/bin:/bin", "HOME": str(tmp_path),
                   "EDGE_OS_EGRESS_CONFIG": str(config), "EDGE_OS_EGRESS_LOCK": str(tmp_path / "lock"),
                   "STUB_LOG": str(log)}
    if env_project is not None:
        environment["EDGE_OS_COMPOSE_PROJECT"] = env_project
    completed = subprocess.run(
        ["sh", str(SCRIPT), "refresh"], capture_output=True, text=True, timeout=60, env=environment)
    return completed, log.read_text(encoding="utf-8")


def test_refresh_finds_the_stack_from_the_fixed_bridge_label(tmp_path):
    completed, commands = run_refresh(
        tmp_path, worker_extra=[(PROJECT, "10.0.2.5")],
        postgres_extra=[(PROJECT, "10.0.2.6")])
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


def test_refresh_enables_bridge_filtering_and_drops_the_injected_addresses(tmp_path):
    completed, commands = run_refresh(
        tmp_path, worker_extra=[(PROJECT, "10.0.2.4")],
        postgres_extra=[(PROJECT, "10.0.2.2")])
    assert completed.returncode == 0, completed.stderr
    assert "modprobe br_netfilter" in commands
    assert "sysctl -w net.bridge.bridge-nf-call-iptables=1" in commands
    assert "sysctl -w net.bridge.bridge-nf-call-ip6tables=1" in commands
    for address in ("10.0.2.4", "10.0.2.2"):
        assert f"-s {address} -j DROP" in commands
        assert f"-d {address} -j DROP" in commands


def test_refresh_fails_when_br_netfilter_cannot_load(tmp_path):
    completed, commands = run_refresh(
        tmp_path, bridge_module_ok=False,
        worker_extra=[(PROJECT, "10.0.2.4")], postgres_extra=[(PROJECT, "10.0.2.2")])
    assert completed.returncode != 0
    assert "br_netfilter" in completed.stderr
    assert "same-bridge" in completed.stderr
    assert "-j DROP" not in commands


def test_refresh_fails_when_a_bridge_sysctl_cannot_be_set(tmp_path):
    completed, _ = run_refresh(
        tmp_path, bridge_sysctl_ok=False,
        worker_extra=[(PROJECT, "10.0.2.4")], postgres_extra=[(PROJECT, "10.0.2.2")])
    assert completed.returncode != 0
    assert "same-bridge" in completed.stderr


def test_refresh_fails_when_a_bridge_sysctl_reads_back_disabled(tmp_path):
    completed, _ = run_refresh(
        tmp_path, bridge_sysctl_value="0",
        worker_extra=[(PROJECT, "10.0.2.4")], postgres_extra=[(PROJECT, "10.0.2.2")])
    assert completed.returncode != 0
    assert "same-bridge" in completed.stderr


def test_refresh_accepts_a_matching_explicit_project(tmp_path):
    completed, commands = run_refresh(
        tmp_path, env_project=PROJECT, worker_extra=[(PROJECT, "10.0.2.5")],
        postgres_extra=[(PROJECT, "10.0.2.6")])
    assert completed.returncode == 0, completed.stderr
    assert "-s 10.0.2.5 -j DROP" in commands


def test_refresh_is_a_no_op_only_before_the_fixed_bridges_exist(tmp_path):
    completed, commands = run_refresh(tmp_path, bridge_project=None, no_containers=True)
    assert completed.returncode == 0, completed.stderr
    assert "no fixed bridges" in completed.stderr
    assert "-I DOCKER-USER 1 -j EDGE_OS_BYPASS_" in commands


def test_refresh_fails_when_a_fixed_bridge_lacks_the_project_label(tmp_path):
    completed, _ = run_refresh(tmp_path, bridge_project="")
    assert completed.returncode != 0
    assert "no compose project label" in completed.stderr


def test_refresh_fails_when_the_explicit_project_mismatches_the_bridge(tmp_path):
    completed, _ = run_refresh(tmp_path, env_project="edge-os")
    assert completed.returncode != 0
    assert "does not match the fixed bridge project" in completed.stderr


def test_refresh_fails_when_fixed_bridges_exist_but_a_container_is_missing(tmp_path):
    completed, _ = run_refresh(tmp_path, missing=("postgres",))
    assert completed.returncode != 0
    assert "expected one running postgres container" in completed.stderr


def test_refresh_fails_when_containers_exist_without_the_fixed_bridges(tmp_path):
    completed, _ = run_refresh(tmp_path, bridge_project=None)
    assert completed.returncode != 0
    assert "fixed bridges are absent" in completed.stderr


def test_refresh_fails_when_a_container_is_not_on_its_declared_networks(tmp_path):
    completed, _ = run_refresh(
        tmp_path, worker_extra=[(PROJECT, "10.0.2.5")],
        postgres_extra=[(PROJECT, "10.0.2.6")])
    assert completed.returncode == 0
    binaries = tmp_path / "bin"
    stub(binaries, "docker", docker_stub(
        project=PROJECT, bridge_project=PROJECT,
        worker=[(f"{PROJECT}_private", "10.203.0.100"), (PROJECT, "10.0.2.5")],
        postgres=[*declared(PROJECT)["postgres"], (PROJECT, "10.0.2.6")]))
    config = tmp_path / "egress.env"
    config.write_text('EDGE_OS_EGRESS_HOSTS="api.example"\n', encoding="utf-8")
    completed = subprocess.run(
        ["sh", str(SCRIPT), "refresh"], capture_output=True, text=True, timeout=60,
        env={"PATH": f"{binaries}:/usr/bin:/bin", "HOME": str(tmp_path),
             "EDGE_OS_EGRESS_CONFIG": str(config), "EDGE_OS_EGRESS_LOCK": str(tmp_path / "lock"),
             "STUB_LOG": str(tmp_path / "commands.log")})
    assert completed.returncode != 0
    assert "not on its declared network" in completed.stderr


def test_refresh_fails_loudly_when_the_daemon_is_unreachable(tmp_path):
    completed, _ = run_refresh(tmp_path, docker_down=True)
    assert completed.returncode != 0
    assert "docker daemon is unreachable" in completed.stderr


def test_refresh_fails_loudly_on_an_ipv6_address_on_the_extra_network(tmp_path):
    completed, _ = run_refresh(
        tmp_path, worker_extra=[(PROJECT, "10.0.2.5", "fd00::5")])
    assert completed.returncode != 0
    assert "IPv6" in completed.stderr


def test_refresh_accepts_the_docker29_worker_sample(tmp_path):
    completed, commands = run_refresh(
        tmp_path,
        worker_lines=(f"'{PROJECT}_egress|10.203.0.2|invalid IP' "
                      f"'{PROJECT}_private|10.203.0.69|invalid IP'"))
    assert completed.returncode == 0, completed.stderr
    assert "IPv6" not in completed.stderr
    assert "-j DROP" not in commands


def test_refresh_accepts_the_docker29_postgres_sample(tmp_path):
    completed, commands = run_refresh(
        tmp_path,
        postgres_lines=(f"'{PROJECT}_private|10.203.0.66|invalid IP' "
                        f"'{PROJECT}_hostdb|10.203.0.18|invalid IP' "
                        f"'{PROJECT}|10.0.2.7|invalid IP'"))
    assert completed.returncode == 0, completed.stderr
    assert "IPv6" not in completed.stderr
    assert "-s 10.0.2.7 -j DROP" in commands
    assert "-d 10.0.2.7 -j DROP" in commands
    assert "invalid" not in commands


def test_refresh_treats_invalid_ip_as_no_address_in_both_fields(tmp_path):
    completed, commands = run_refresh(
        tmp_path,
        worker_lines=(f"'{PROJECT}_egress|invalid IP|invalid IP' "
                      f"'{PROJECT}_private|10.203.0.100|invalid IP' "
                      f"'{PROJECT}|invalid IP|invalid IP'"))
    assert completed.returncode == 0, completed.stderr
    assert "-j DROP" not in commands


def test_refresh_accepts_a_two_field_empty_address_line(tmp_path):
    completed, commands = run_refresh(
        tmp_path,
        worker_lines=(f"'{PROJECT}_egress|10.203.0.2' "
                      f"'{PROJECT}_private|10.203.0.100'"))
    assert completed.returncode == 0, completed.stderr
    assert "-j DROP" not in commands


def test_refresh_drops_an_extra_ipv4_with_a_spaced_network_name(tmp_path):
    completed, commands = run_refresh(
        tmp_path,
        worker_lines=(f"'{PROJECT}_egress|10.203.0.2|invalid IP' "
                      f"'{PROJECT}_private|10.203.0.100|invalid IP' "
                      f"'odd name|10.0.2.9|invalid IP'"))
    assert completed.returncode == 0, completed.stderr
    assert "-s 10.0.2.9 -j DROP" in commands
    assert "-d 10.0.2.9 -j DROP" in commands


def test_refresh_refuses_a_real_ipv6_on_a_declared_network(tmp_path):
    completed, _ = run_refresh(
        tmp_path,
        worker_lines=(f"'{PROJECT}_egress|10.203.0.2|invalid IP' "
                      f"'{PROJECT}_private|10.203.0.100|fd00::7'"))
    assert completed.returncode != 0
    assert "IPv6" in completed.stderr
    assert "declared network" in completed.stderr


def test_refresh_refuses_an_ipv4_field_that_is_not_a_dotted_quad(tmp_path):
    completed, commands = run_refresh(tmp_path, worker_extra=[(PROJECT, "10.0.2")])
    assert completed.returncode != 0
    assert "not a dotted quad" in completed.stderr
    assert "-s 10.0.2 -j DROP" not in commands


def test_refresh_refuses_a_malformed_endpoint_line(tmp_path):
    completed, _ = run_refresh(
        tmp_path,
        worker_lines=(f"'{PROJECT}_egress|10.203.0.2|invalid IP' "
                      f"'{PROJECT}_private|10.203.0.100|invalid IP' "
                      f"'{PROJECT}'"))
    assert completed.returncode != 0
    assert "malformed network endpoint line" in completed.stderr


def test_refresh_refuses_a_leading_zero_octet(tmp_path):
    completed, commands = run_refresh(tmp_path, worker_extra=[(PROJECT, "010.0.2.5")])
    assert completed.returncode != 0
    assert "not a dotted quad" in completed.stderr
    assert "-s 010.0.2.5" not in commands
