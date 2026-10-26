"""The shared Hermes relay folders: the group, the unit wiring, the channel bind prefix and the runbook order.

Static checks only. No Docker, no user creation, no host change.
"""

from __future__ import annotations

import re
from pathlib import Path

import deploy_support as support

HOST = support.REPO / "deploy" / "host"
RESEARCH_UNIT = HOST / "edge-os-research-worker.service"
RELAY_UNIT = HOST / "edge-os-hermes-relay.service"
APP_UNIT = HOST / "edge-os-hermes-app.service"
SOCKET_UNIT = HOST / "edge-os-socket-proxy.service"
RUNBOOK = support.REPO / "deploy" / "coolify" / "RUNBOOK.md"
README = support.REPO / "docs" / "qualification" / "hermes-actual-operation" / "README.md"
LAUNCHER = support.REPO / "scripts" / "hermes_app_mount" / "serve_relay_application.py"
SHARE_GROUP = "edge-os-relay-share"


def _unit(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _line(unit: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for line in unit.splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            settings.setdefault(key, value)
    return settings


def _env(unit: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in unit.splitlines():
        if line.startswith("Environment="):
            key, _, value = line.removeprefix("Environment=").partition("=")
            values[key] = value
    return values


def test_every_host_unit_uses_the_shared_group_and_keeps_its_own_group_for_the_proxy_socket() -> None:
    for path, own in ((RESEARCH_UNIT, "edge-os-research"), (RELAY_UNIT, "edge-os-relay"),
                      (APP_UNIT, "edge-os-research")):
        settings = _line(_unit(path))
        assert settings["Group"] == SHARE_GROUP, path.name
        assert settings["SupplementaryGroups"] == own, path.name
        assert settings["UMask"] == "0077", path.name
        assert settings["ProtectSystem"] == "strict", path.name
        assert settings["ProtectHome"] == "yes", path.name
        assert settings["NoNewPrivileges"] == "yes", path.name
        assert settings["RestrictSUIDSGID"] == "yes", path.name


def test_every_host_unit_names_its_own_docker_config() -> None:
    for path, role in ((RESEARCH_UNIT, "research"), (RELAY_UNIT, "relay"), (APP_UNIT, "research")):
        assert f"Environment=DOCKER_CONFIG=/var/lib/edge-os/{role}/docker-config" in _unit(path), path.name


def test_the_proxy_socket_owner_and_mode_match_the_units_group_access() -> None:
    for role in ("research", "relay"):
        assert f"install -d -m 0750 -o \"$EDGE_OS_PROXY_{role.upper()}_UID\" -g \"$EDGE_OS_{role.upper()}_GID\"" in _unit(SOCKET_UNIT)
    proxy = support.compose_model(str(support.HOST_PROXY_COMPOSE))
    for name, role in (("socket-proxy-research", "RESEARCH"), ("socket-proxy-relay", "RELAY")):
        service = proxy["services"][name]
        assert support.command_option(service, "proxysocketendpointfilemode") == "0660"
        assert f"${{EDGE_OS_{role}_GID:?" in service["user"]


def test_the_app_unit_runs_the_launcher_on_loopback_with_the_handoff_from_its_env_file() -> None:
    settings = _line(_unit(APP_UNIT))
    assert settings["User"] == "edge-os-research"
    assert settings["WorkingDirectory"] == "/opt/edge-os"
    assert settings["EnvironmentFile"] == "/etc/edge-os/hermes-app.env"
    assert settings["ConditionPathExists"] == "/etc/edge-os/hermes-app.enabled"
    start = settings["ExecStart"]
    assert "serve_relay_application.py" in start
    for argument in ("--handoff-path ${EDGE_OS_HANDOFF_PATH}", "--handoff-sha256 ${EDGE_OS_HANDOFF_SHA256}",
                     "--run-id ${EDGE_OS_RUN_ID}", "--port 8011"):
        assert argument in start
    assert _env(_unit(APP_UNIT))["DOCKER_HOST"] == "unix:///run/edge-os/research/docker.sock"
    assert re.search(r'^HOST = "127\.0\.0\.1"$', LAUNCHER.read_text(encoding="utf-8"), re.MULTILINE)


def test_the_app_writes_only_its_own_evidence_the_channel_and_the_shared_grant_folders() -> None:
    settings = _line(_unit(APP_UNIT))
    paths = settings["ReadWritePaths"].split()
    assert paths == ["/var/lib/edge-os/research", "/var/lib/edge-os/channel", "/var/lib/edge-os/relay"]
    relay = _line(_unit(RELAY_UNIT))
    assert relay["ReadWritePaths"].split() == ["/var/lib/edge-os/relay", "/var/lib/edge-os/channel"]


def test_the_relay_containers_never_get_a_supplementary_group_flag() -> None:
    supervisor = support.RELAY_SUPERVISOR.read_text(encoding="utf-8")
    assert "--group-add" not in supervisor


def test_the_research_proxy_allows_only_the_channel_root_and_never_the_relay_tree() -> None:
    proxy = support.compose_model(str(support.HOST_PROXY_COMPOSE))
    research = support.command_option(proxy["services"]["socket-proxy-research"], "allowbindmountfrom")
    assert research == "/opt/edge-os,/var/lib/edge-os/research,/var/lib/edge-os/channel"
    for source in ("/var/lib/edge-os/relay", "/var/lib/edge-os/relay/run-1/relay/grants",
                   "/etc/edge-os/relay"):
        assert not _covered(source, research.split(",")), source
    relay = support.command_option(proxy["services"]["socket-proxy-relay"], "allowbindmountfrom")
    assert relay == "/opt/edge-os,/var/lib/edge-os,/etc/edge-os/relay"


def _covered(source: str, prefixes: list[str]) -> bool:
    path = Path(source)
    return any(path == Path(prefix) or Path(prefix) in path.parents for prefix in prefixes)


def test_the_job_runner_does_not_name_any_relay_private_path() -> None:
    text = support.GUARDED_RUNNER.read_text(encoding="utf-8")
    for name in ("admission-key", "admission_key", "provider-key", "grants", "revocations", "/relay/"):
        assert name not in text, name


def test_the_runbook_creates_the_group_folders_and_start_order() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for expected in (
        "groupadd --system edge-os-relay-share",
        "install -d -m 0750 -o edge-os-relay -g edge-os-relay-share /var/lib/edge-os/relay",
        "install -d -m 2770 -o root -g edge-os-relay-share /var/lib/edge-os/channel",
        "install -d -m 2750 -o edge-os-research -g edge-os-research /var/lib/edge-os/research",
        "install -d -m 0700 -o edge-os-relay -g edge-os-relay /var/lib/edge-os/relay/docker-config",
        "install -d -m 0700 -o edge-os-research -g edge-os-research /var/lib/edge-os/research/docker-config",
        "chown root:edge-os-relay-share /etc/edge-os/relay/provider-ca.pem",
        "hermes-app.env",
        "8011",
        "sudo -g edge-os-relay-share -u edge-os-research test -r /etc/edge-os/relay/provider-key",
        "sudo -g edge-os-relay-share -u edge-os-research test -r "
        "/var/lib/edge-os/relay/run-1/relay/relay-config.json",
        "sudo -g edge-os-relay-share -u edge-os-research test -r "
        "/var/lib/edge-os/relay/run-1/relay/provider-config.json",
        "sudo -g edge-os-relay-share -u edge-os-research test -w /var/lib/edge-os/relay/run-1/relay/state",
        "sudo -g edge-os-relay-share -u edge-os-research test -r "
        "/var/lib/edge-os/relay/run-1/relay/secrets/admission-key",
        "sudo -g edge-os-relay-share -u edge-os-research test -w /var/lib/edge-os/relay/run-1/relay/grants",
        "runuser -g edge-os-relay-share -u edge-os-research",
        "/var/lib/edge-os/relay/run-1/relay/relay-config.json "
        "/var/lib/edge-os/relay/run-1/relay/provider-config.json",
        "`channel.path` must name a new child folder under it",
        "`RestrictSUIDSGID=yes`, which denies a `chmod`/`mkdir` mode argument with S_ISGID",
        "`ReadWritePaths=/var/lib/edge-os/relay` is a stable",
    ):
        assert expected in text, expected
    assert "a denial from it is the stronger proof" not in text
    assert "The plain user holds neither" not in text
    copy = text.index("printed handoff line")
    app = text.index("start edge-os-hermes-app.service")
    assert copy < app


def test_the_readme_path_table_names_the_shared_owners_groups_and_modes() -> None:
    text = README.read_text(encoding="utf-8")
    for expected in (
        "edge-os-relay-share",
        "/var/lib/edge-os/channel",
        "<run root>/relay/grants/<attempt>.json",
        "0640",
        "0770",
        "0750",
        "0440",
    ):
        assert expected in text, expected
