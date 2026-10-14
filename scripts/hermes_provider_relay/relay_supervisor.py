"""Starts, restarts and stops the relay and the AUTHORED provider in one loopback-only network namespace. LOCAL only.

Constructing a `RelaySupervisor` does nothing. `start()` is the explicit effect: it prepares the private relay folders,
a random admission key, a throwaway test CA and provider certificate, starts the provider with `--network none` (its
namespace has loopback only: no interface, no route, no gateway), listening on 127.0.0.1:8443, and then the relay with
`--network container:<the provider's exact id>`, so the relay shares that namespace and nothing else. No port is
published. Processes, filesystems and mounts stay separate. The relay is the only container with the synthetic provider
key; the Hermes job runs elsewhere with no network at all. Every Docker call has a timeout.

The relay joins the provider by the id recorded at start, never by name. If that provider is gone or replaced, a relay
(re)start fails and nothing runs: the relay is never attached to any other network. `stop()` removes exactly what
`start()` made and reports what is left.

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
PROVIDER_HOST, PROVIDER_PORT, PROVIDER_PATH = "localhost", 8443, "/v1/chat/completions"
DOCKER_SECONDS = 60
START_SECONDS = 30.0
KERNEL_VIEW = (  # run inside a container by `docker exec`: its own namespace, interfaces and routes
    "import json, os; r = lambda p: open(p).read().splitlines() if os.path.exists(p) else []; "
    "n = sorted(i for i in os.listdir('/sys/class/net') if os.path.isdir(f'/sys/class/net/{i}')); "  # not bonding_masters
    "print(json.dumps({'namespace': os.readlink('/proc/self/ns/net'), 'interfaces': n, "
    "'interfaces_up': [i for i in n if int(r(f'/sys/class/net/{i}/flags')[0], 16) & 1], "
    "'ipv4_routes': [l.split()[0] for l in r('/proc/net/route')[1:] if l.strip()], "
    "'ipv6_routes_not_loopback': [l.split()[-1] for l in r('/proc/net/ipv6_route') if l.split()[-1] != 'lo']}))")
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
    provider_id: str | None = field(init=False, default=None)  # the exact provider whose namespace the relay joins

    def __post_init__(self) -> None:
        if self.release.kind != "AUTHORED":
            raise ValueError("the relay supervisor serves AUTHORED releases only")
        self.names = {"relay": f"relay-{self.run_id}", "provider": f"relay-provider-{self.run_id}"}

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
        relay_config = {
            "release": self.release.settings(), "destination": vars(destination),
            "channel_roots": {name: f"/relay/channels/{name}" for name in self.channel_roots},
            "paths": {"provider_key": "/relay/secrets/provider-key", "admission_key": "/relay/secrets/admission-key",
                      "provider_ca": "/relay/tls/ca.pem", "grants": "/relay/grants", "revocations": "/relay/revocations",
                      "state": "/relay/state"},
            "poll_seconds": self.poll_seconds,
            "egress_probes": [{"host": PROVIDER_HOST, "port": PROVIDER_PORT}]}  # the positive control
        provider_config = {"bind": "127.0.0.1", "port": PROVIDER_PORT, "path": PROVIDER_PATH,
                           "cert": "/provider/tls/server.pem", "key": "/provider/tls/server.key",
                           "scripts": "/provider/scripts", "receipts": "/provider/receipts",
                           "expected_key_file": "/provider/expected-key"}
        self.path("relay-config.json").write_text(json.dumps(relay_config, indent=1), encoding="utf-8")
        self.path("provider-config.json").write_text(json.dumps(provider_config, indent=1), encoding="utf-8")

    # --- containers ------------------------------------------------------------------------------------------------

    @staticmethod
    def _mount(source: Path, target: str, *, writable: bool = False) -> list[str]:
        return ["--mount", f"type=bind,src={source.resolve()},dst={target}" + ("" if writable else ",readonly")]

    def _common(self, name: str, network: str) -> list[str]:
        return ["run", "-d", "--name", name, "--label", f"{LABEL}={self.run_id}", "--network", network,
                "--user", f"{os.getuid()}:{os.getgid()}", *HARDENING, "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--entrypoint", PYTHON]

    def _start_provider(self) -> None:
        argv = [*self._common(self.names["provider"], "none"),
                *self._mount(HERE / "authored_provider.py", "/provider/authored_provider.py"),
                *self._mount(self.path("provider-config.json"), "/provider/config.json"),
                *self._mount(self.path("tls", "server.pem"), "/provider/tls/server.pem"),
                *self._mount(self.path("tls", "server.key"), "/provider/tls/server.key"),
                *self._mount(self.provider_key_file, "/provider/expected-key"),
                *self._mount(self.path("provider", "scripts"), "/provider/scripts"),
                *self._mount(self.path("provider", "receipts"), "/provider/receipts", writable=True),
                self.image, "-B", "/provider/authored_provider.py", "/provider/config.json"]
        self.provider_id = docker(*argv).stdout.strip()
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
        if self.provider_id is None:
            raise RuntimeError("no provider was started: the relay has no namespace to join")
        before = self._heartbeat_started()
        docker(*self._common(self.names["relay"], f"container:{self.provider_id}"),
               "--env", "RELAY_SUPPORT_PATH=/relay/support/job:/relay/support/interpretation",
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
        """What Docker and each container's own kernel say: network modes, ports, mounts, namespace, interfaces, routes."""
        seen: dict[str, Any] = {"provider_id": self.provider_id}
        for role in ("relay", "provider"):
            container = json.loads(docker("inspect", self.names[role]).stdout)[0]
            seen[role] = {"id": container["Id"], "network_mode": container["HostConfig"]["NetworkMode"],
                          "networks": sorted(container["NetworkSettings"]["Networks"]),
                          "ports": container["NetworkSettings"]["Ports"] or {},
                          "port_bindings": container["HostConfig"]["PortBindings"] or {},
                          "mounts": sorted(m["Destination"] for m in container["Mounts"]),
                          "kernel": json.loads(docker("exec", self.names[role], PYTHON, "-B", "-c", KERNEL_VIEW).stdout)}
        return seen

    def logs(self) -> str:
        logs = [docker("logs", name, check=False) for name in (self.names["relay"], self.names["provider"])]
        return "".join(each.stdout + each.stderr for each in logs)

    def stop(self) -> dict[str, Any]:
        for name in (self.names["relay"], self.names["provider"]):
            docker("rm", "-f", name, check=False)
        left = docker("ps", "-a", "--filter", f"label={LABEL}={self.run_id}", "--format", "{{.Names}}", check=False).stdout.split()
        networks = docker("network", "ls", "--filter", f"label={LABEL}={self.run_id}", "--format", "{{.Name}}",
                          check=False).stdout.split()
        return {"containers_left": left, "networks_left": networks}

    def remove_files(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
