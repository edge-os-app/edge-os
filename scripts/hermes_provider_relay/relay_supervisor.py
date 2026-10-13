"""Starts, restarts and stops the relay and the AUTHORED provider on their own internal Docker network. LOCAL only.

Constructing a `RelaySupervisor` does nothing. `start()` is the explicit effect: it prepares the private relay folders,
a random admission key, a throwaway test CA and provider certificate, creates one `--internal` network (no route out
of it: only its members can reach each other), starts the provider and then the relay on it by exact name and label,
and waits for the relay's heartbeat. The relay is the only container with the synthetic provider key and the only
member besides the provider; the Hermes job runs elsewhere with no network at all. Every Docker call has a timeout.
`stop()` removes exactly what `start()` made and reports what is left.

This supervisor serves AUTHORED releases only. It never reads a real credential: the caller passes a synthetic key file.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from relay_admission import ProviderDestination, RelayRelease
from relay_turn_runner import RelayEndpoint

__all__ = ["RelaySupervisor", "make_provider_tls"]

HERE = Path(__file__).resolve().parent
SUPPORT = (HERE.parent / "hermes_job_support", HERE.parent / "hermes_interpretation")
LABEL = "edge-os.hermes-relay"
PYTHON = "/usr/local/bin/python"
PROVIDER_HOST, PROVIDER_PORT, PROVIDER_PATH = "authored-provider", 8443, "/v1/chat/completions"
DOCKER_SECONDS = 60
START_SECONDS = 30.0
HARDENING = ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=256m",
             "--memory-swap=256m", "--cpus=1", "--pids-limit=64", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m")


def docker(*args: str, timeout: float = DOCKER_SECONDS, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=check)


def make_provider_tls(folder: Path, hosts: tuple[str, ...]) -> None:
    """A throwaway test CA and a server certificate for `hosts`. The CA key is deleted once the certificate is signed."""
    folder.mkdir(parents=True, exist_ok=True)

    def openssl(*args: str) -> None:
        subprocess.run(["openssl", *args], cwd=folder, capture_output=True, check=True, timeout=60)

    curve = ("-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes")
    openssl("req", "-x509", *curve, "-keyout", "ca.key", "-out", "ca.pem", "-days", "2", "-subj", "/CN=relay-test-ca",
            "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    openssl("req", "-new", *curve, "-keyout", "server.key", "-out", "server.csr", "-subj", f"/CN={hosts[0]}")
    (folder / "server.ext").write_text(
        f"subjectAltName={','.join(f'DNS:{host}' for host in hosts)}\nbasicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nauthorityKeyIdentifier=keyid\n"
        "subjectKeyIdentifier=hash\n", encoding="utf-8")
    openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-out", "server.pem", "-days", "2", "-extfile", "server.ext")
    for name in ("ca.key", "server.csr", "server.ext", "ca.srl"):
        (folder / name).unlink(missing_ok=True)


@dataclass
class RelaySupervisor:
    root: Path  # private folder for the relay's grants, state, keys and the provider's scripts and receipts
    release: RelayRelease
    image: str
    run_id: str
    provider_key_file: Path  # synthetic sentinel only
    channel_roots: dict[str, Path]  # channel root name -> a job's evidence folder
    poll_seconds: float = 0.02
    names: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        if self.release.kind != "AUTHORED":
            raise ValueError("the relay supervisor serves AUTHORED releases only")
        self.names = {"network": f"relay-net-{self.run_id}", "relay": f"relay-{self.run_id}",
                      "provider": f"relay-provider-{self.run_id}"}

    # --- folders ---------------------------------------------------------------------------------------------------

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def endpoint(self, channel_root: str) -> RelayEndpoint:
        return RelayEndpoint(self.path("grants"), self.path("revocations"), self.path("state"),
                             self.path("secrets", "admission-key"), channel_root)

    def _prepare(self) -> None:
        for folder in ("grants", "revocations", "state", "secrets", "tls", "provider/scripts", "provider/receipts"):
            self.path(*folder.split("/")).mkdir(parents=True, exist_ok=True, mode=0o700)
        key = self.path("secrets", "admission-key")
        if not key.exists():
            key.write_bytes(secrets.token_bytes(32))
            key.chmod(0o400)
        if not self.path("tls", "server.pem").exists():
            make_provider_tls(self.path("tls"), (PROVIDER_HOST,))
        for root in self.channel_roots.values():
            root.mkdir(parents=True, exist_ok=True)
        destination = ProviderDestination(PROVIDER_HOST, PROVIDER_PORT, PROVIDER_PATH)
        gateway = docker("network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}",
                         check=False).stdout.strip() or "172.17.0.1"
        own_gateway = docker("network", "inspect", self.names["network"], "--format",
                             "{{(index .IPAM.Config 0).Gateway}}").stdout.strip()  # the Docker host's side of it
        relay_config = {
            "release": self.release.settings(), "destination": vars(destination),
            "channel_roots": {name: f"/relay/channels/{name}" for name in self.channel_roots},
            "paths": {"provider_key": "/relay/secrets/provider-key", "admission_key": "/relay/secrets/admission-key",
                      "provider_ca": "/relay/tls/ca.pem", "grants": "/relay/grants", "revocations": "/relay/revocations",
                      "state": "/relay/state"},
            "poll_seconds": self.poll_seconds,
            "egress_probes": [{"host": PROVIDER_HOST, "port": PROVIDER_PORT, "expect": "reachable"},
                              {"host": "1.1.1.1", "port": 53, "expect": "blocked"},
                              {"host": gateway, "port": 53, "expect": "blocked"},
                              {"host": own_gateway, "port": 53, "expect": "blocked"},
                              {"host": own_gateway, "port": 80, "expect": "blocked"},
                              {"host": "host.docker.internal", "port": 80, "expect": "blocked"}]}
        provider_config = {"bind": "0.0.0.0", "port": PROVIDER_PORT, "path": PROVIDER_PATH,
                           "cert": "/provider/tls/server.pem", "key": "/provider/tls/server.key",
                           "scripts": "/provider/scripts", "receipts": "/provider/receipts",
                           "expected_key_file": "/provider/expected-key"}
        self.path("relay-config.json").write_text(json.dumps(relay_config, indent=1), encoding="utf-8")
        self.path("provider-config.json").write_text(json.dumps(provider_config, indent=1), encoding="utf-8")

    # --- containers ------------------------------------------------------------------------------------------------

    @staticmethod
    def _mount(source: Path, target: str, *, writable: bool = False) -> list[str]:
        return ["--mount", f"type=bind,src={source.resolve()},dst={target}" + ("" if writable else ",readonly")]

    def _common(self, name: str) -> list[str]:
        return ["run", "-d", "--name", name, "--label", f"{LABEL}={self.run_id}", "--network", self.names["network"],
                "--user", f"{os.getuid()}:{os.getgid()}", *HARDENING, "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--entrypoint", PYTHON]

    def _start_provider(self) -> None:
        argv = [*self._common(self.names["provider"]), "--network-alias", PROVIDER_HOST,
                *self._mount(HERE / "authored_provider.py", "/provider/authored_provider.py"),
                *self._mount(self.path("provider-config.json"), "/provider/config.json"),
                *self._mount(self.path("tls", "server.pem"), "/provider/tls/server.pem"),
                *self._mount(self.path("tls", "server.key"), "/provider/tls/server.key"),
                *self._mount(self.provider_key_file, "/provider/expected-key"),
                *self._mount(self.path("provider", "scripts"), "/provider/scripts"),
                *self._mount(self.path("provider", "receipts"), "/provider/receipts", writable=True),
                self.image, "-B", "/provider/authored_provider.py", "/provider/config.json"]
        docker(*argv)
        self._wait(lambda: self.path("provider", "receipts", "ready").exists(), "provider")

    def start_relay(self) -> None:
        mounts = [*self._mount(HERE, "/relay/code"), *self._mount(SUPPORT[0], "/relay/support/job"),
                  *self._mount(SUPPORT[1], "/relay/support/interpretation"),
                  *self._mount(self.path("relay-config.json"), "/relay/config.json"),
                  *self._mount(self.provider_key_file, "/relay/secrets/provider-key"),
                  *self._mount(self.path("secrets", "admission-key"), "/relay/secrets/admission-key"),
                  *self._mount(self.path("tls", "ca.pem"), "/relay/tls/ca.pem"),
                  *self._mount(self.path("grants"), "/relay/grants"),
                  *self._mount(self.path("revocations"), "/relay/revocations"),
                  *self._mount(self.path("state"), "/relay/state", writable=True)]
        for name, root in self.channel_roots.items():
            mounts += self._mount(root, f"/relay/channels/{name}", writable=True)
        before = self._heartbeat_started()
        docker(*self._common(self.names["relay"]), "--env", "RELAY_SUPPORT_PATH=/relay/support/job:/relay/support/interpretation",
               *mounts, self.image, "-B", "/relay/code/relay_service.py", "/relay/config.json")
        self._wait(lambda: (self._heartbeat_started() or 0) > (before or 0), "relay")

    def _heartbeat_started(self) -> float | None:
        try:
            return float(json.loads(self.path("state", "heartbeat.json").read_text(encoding="utf-8"))["started_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _wait(self, ready: Any, what: str) -> None:
        until = time.monotonic() + START_SECONDS
        while not ready():
            if time.monotonic() >= until:
                raise RuntimeError(f"the {what} did not start within {START_SECONDS} s")
            time.sleep(0.1)

    def start(self) -> None:
        docker("network", "create", "--internal", "--label", f"{LABEL}={self.run_id}", self.names["network"])
        self._prepare()
        self._start_provider()
        self.start_relay()

    def kill_relay(self) -> None:
        """A relay crash: the process dies at once, its records stay. The container is removed, not restarted."""
        docker("kill", self.names["relay"], check=False)
        docker("rm", "-f", self.names["relay"], check=False)

    def restart_relay(self) -> None:
        self.kill_relay()
        self.start_relay()

    def heartbeat(self) -> dict[str, Any]:
        return json.loads(self.path("state", "heartbeat.json").read_text(encoding="utf-8"))

    def inspect(self) -> dict[str, Any]:
        """What Docker says about the relay: its networks, mounts and whether the network is internal."""
        relay = json.loads(docker("inspect", self.names["relay"]).stdout)[0]
        network = json.loads(docker("network", "inspect", self.names["network"]).stdout)[0]
        return {"relay_networks": sorted(relay["NetworkSettings"]["Networks"]),
                "relay_ports": relay["NetworkSettings"]["Ports"],
                "relay_mounts": sorted(m["Destination"] for m in relay["Mounts"]),
                "network_internal": network["Internal"],
                "network_members": sorted(c["Name"] for c in network["Containers"].values())}

    def inspect_network(self) -> str:
        return json.dumps(json.loads(docker("network", "inspect", self.names["network"]).stdout)[0])

    def logs(self) -> str:
        logs = [docker("logs", name, check=False) for name in (self.names["relay"], self.names["provider"])]
        return "".join(each.stdout + each.stderr for each in logs)

    def stop(self) -> dict[str, Any]:
        for name in (self.names["relay"], self.names["provider"]):
            docker("rm", "-f", name, check=False)
        docker("network", "rm", self.names["network"], check=False)
        left = docker("ps", "-a", "--filter", f"label={LABEL}={self.run_id}", "--format", "{{.Names}}", check=False).stdout.split()
        networks = docker("network", "ls", "--filter", f"label={LABEL}={self.run_id}", "--format", "{{.Name}}",
                          check=False).stdout.split()
        return {"containers_left": left, "networks_left": networks}

    def remove_files(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
