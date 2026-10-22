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

With `online=True` it builds the E1 topology instead (CONTRACT A6): a labelled ordinary bridge network with no published
port, a keyless egress gateway on it, and the relay with `--network none` whose only way out is the gateway's Unix
socket. The socket lives in a labelled tmpfs Docker volume (mode 0700, owned by the one non-root user both containers
run as) mounted into the relay and the gateway only, never on the host file system. For an AUTHORED release a TLS
stand-in for `openrouter.ai` (test CA) runs on that bridge and the gateway uses the test resolution to its address. An
ACTUAL release needs its approved record (`relay_admission.load_actual_release`), the record's CA bundle and a key file
readable by its owner only; it runs no stand-in and no test resolution. The gateway admits only the destination host
and port of the release in force: the approved record's own for ACTUAL, the stand-in's for AUTHORED.

It never reads a real credential in this candidate: the caller passes a synthetic key file.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from egress_gateway import AllowedTarget
from relay_admission import ActualRelease, ProviderDestination, RelayRelease, load_actual_release
from relay_turn_runner import RelayEndpoint

__all__ = ["RelaySupervisor", "make_provider_tls"]

HERE = Path(__file__).resolve().parent
SUPPORT = (HERE.parent / "hermes_job_support", HERE.parent / "hermes_interpretation")
LABEL = "edge-os.hermes-relay"
PYTHON = "/usr/local/bin/python"
PROVIDER_HOST, PROVIDER_PORT, PROVIDER_PATH = "localhost", 8443, "/v1/chat/completions"
# AUTHORED online only: the destination the TLS stand-in plays. ACTUAL uses its approved record's destination.
STAND_IN = ProviderDestination("openrouter.ai", 443, "/api/v1/chat/completions")
GATEWAY_SOCKET = "gateway.sock"
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
    online: bool = False  # the E1 topology: keyless gateway on its own bridge, relay with no network (CONTRACT A6)
    actual: ActualRelease | None = None  # ACTUAL only from an approved record; implies online
    release_record: Path | None = None  # the record file `actual` was loaded from
    ca_bundle_file: Path | None = None  # the record's CA bundle
    names: dict[str, str] = field(init=False)
    provider_id: str | None = field(init=False, default=None)  # the exact provider whose namespace the relay joins

    def __post_init__(self) -> None:
        if self.actual is not None:
            if self.actual.release != self.release or self.release_record is None or self.ca_bundle_file is None:
                raise ValueError("an ACTUAL supervisor needs its approved record, the record file and its CA bundle")
            record = self.release_record.read_bytes()
            if hashlib.sha256(record).hexdigest() != self.actual.record_sha256:
                raise ValueError("the release record file is not the approved record")
            if load_actual_release(record, self.actual.record_sha256) != self.actual:  # the gateway's target is its own
                raise ValueError("the ACTUAL release is not the one its approved record file gives")
            if hashlib.sha256(self.ca_bundle_file.read_bytes()).hexdigest() != self.actual.ca_bundle_sha256:
                raise ValueError("the CA bundle file does not have the record's hash")
            if stat.S_IMODE(self.provider_key_file.stat().st_mode) & 0o077:
                raise ValueError("the provider key file must be readable by its owner only")
            self.online = True
        elif self.release.kind != "AUTHORED":
            raise ValueError("an ACTUAL release is supervised only with its approved release record")
        AllowedTarget(self.destination().host, self.destination().port)  # refused here, before any Docker resource
        self.names = {"relay": f"relay-{self.run_id}", "provider": f"relay-provider-{self.run_id}",
                      "gateway": f"relay-gateway-{self.run_id}", "egress": f"relay-egress-{self.run_id}"}

    # --- folders ---------------------------------------------------------------------------------------------------

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def destination(self) -> ProviderDestination:
        """Where the relay sends: the approved record's destination (ACTUAL), the stand-in or the loopback provider."""
        if self.actual is not None:
            return self.actual.destination
        return STAND_IN if self.online else ProviderDestination(PROVIDER_HOST, PROVIDER_PORT, PROVIDER_PATH)

    def endpoint(self, channel_root: str) -> RelayEndpoint:
        return RelayEndpoint(self.path("grants"), self.path("revocations"), self.path("state"),
                             self.path("secrets", "admission-key"), channel_root)

    def _prepare(self) -> None:
        for folder in ("grants", "revocations", "state", "secrets", "tls", "provider/scripts", "provider/receipts",
                       "gateway/receipts"):
            self.path(*folder.split("/")).mkdir(parents=True, exist_ok=True, mode=0o700)
        key = self.path("secrets", "admission-key")
        if not key.exists():
            key.write_bytes(secrets.token_bytes(32))
            key.chmod(0o400)
        if self.actual is None and not self.path("tls", "server.pem").exists():  # a throwaway test CA, never ACTUAL
            make_provider_tls(self.path("tls"), (self.destination().host,))
        for root in self.channel_roots.values():
            root.mkdir(parents=True, exist_ok=True)
        destination = self.destination()
        if self.online:
            target = {"gateway_socket": f"/relay/egress/{GATEWAY_SOCKET}", "egress_probes": []}  # it has no network
            provider = {"bind": "0.0.0.0", "port": destination.port, "path": destination.path}
        else:
            target = {"egress_probes": [{"host": PROVIDER_HOST, "port": PROVIDER_PORT}]}  # the positive control
            provider = {"bind": "127.0.0.1", "port": PROVIDER_PORT, "path": PROVIDER_PATH}
        release = ({"release_record": {"path": "/relay/release/record.json", "sha256": self.actual.record_sha256}}
                   if self.actual is not None else {"release": self.release.settings(), "destination": vars(destination)})
        relay_config = {
            **release, **target,
            "channel_roots": {name: f"/relay/channels/{name}" for name in self.channel_roots},
            "paths": {"provider_key": "/relay/secrets/provider-key", "admission_key": "/relay/secrets/admission-key",
                      "provider_ca": "/relay/tls/ca.pem", "grants": "/relay/grants", "revocations": "/relay/revocations",
                      "state": "/relay/state"},
            "poll_seconds": self.poll_seconds}
        provider_config = {**provider, "cert": "/provider/tls/server.pem", "key": "/provider/tls/server.key",
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

    def _start_provider(self, network: str = "none") -> None:
        argv = [*self._common(self.names["provider"], network),
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

    def _egress_volume(self, target: str) -> list[str]:
        return ["--mount", f"type=volume,src={self.names['egress']},dst={target}"]

    def _start_gateway(self, test_resolution: str | None) -> None:
        allowed = AllowedTarget(self.destination().host, self.destination().port)  # the gateway's only target
        config = {"socket": f"/egress/{GATEWAY_SOCKET}", "receipts": "/gateway/receipts",
                  "destination": {"host": allowed.host, "port": allowed.port},
                  **({"test_resolution": test_resolution} if test_resolution is not None else {})}
        self.path("gateway-config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
        docker(*self._common(self.names["gateway"], self.names["egress"]), *self._egress_volume("/egress"),
               *self._mount(self.path("gateway", "receipts"), "/gateway/receipts", writable=True),
               *self._mount(HERE / "egress_gateway.py", "/gateway/egress_gateway.py"),
               *self._mount(self.path("gateway-config.json"), "/gateway/config.json"),
               self.image, "-B", "/gateway/egress_gateway.py", "/gateway/config.json")
        self._wait(lambda: self.path("gateway", "receipts", "ready").exists(), "gateway")

    def _start_online(self) -> None:
        """Bridge and socket volume first, then (AUTHORED) the stand-in, then the gateway, then the relay."""
        label = f"{LABEL}={self.run_id}"
        docker("network", "create", "--driver", "bridge", "--label", label, self.names["egress"])
        docker("volume", "create", "--driver", "local", "--opt", "type=tmpfs", "--opt", "device=tmpfs", "--opt",
               f"o=uid={os.getuid()},gid={os.getgid()},mode=0700,size=1m", "--label", label, self.names["egress"])
        test_resolution = None
        if self.actual is None:
            self._start_provider(self.names["egress"])
            test_resolution = docker("inspect", "--format",
                                     f"{{{{(index .NetworkSettings.Networks \"{self.names['egress']}\").IPAddress}}}}",
                                     self.names["provider"]).stdout.strip()
        self._start_gateway(test_resolution)
        self.start_relay()

    def start_relay(self) -> None:
        ca = self.ca_bundle_file if self.actual is not None else self.path("tls", "ca.pem")
        mounts = [*self._mount(HERE, "/relay/code"), *self._mount(SUPPORT[0], "/relay/support/job"),
                  *self._mount(SUPPORT[1], "/relay/support/interpretation"),
                  *self._mount(self.path("relay-config.json"), "/relay/config.json"),
                  *self._mount(self.provider_key_file, "/relay/secrets/provider-key"),
                  *self._mount(self.path("secrets", "admission-key"), "/relay/secrets/admission-key"),
                  *self._mount(ca, "/relay/tls/ca.pem"),
                  *self._mount(self.path("grants"), "/relay/grants"),
                  *self._mount(self.path("revocations"), "/relay/revocations"),
                  *self._mount(self.path("state"), "/relay/state", writable=True)]
        for name, root in self.channel_roots.items():
            mounts += self._mount(root, f"/relay/channels/{name}", writable=True)
        if self.online:
            mounts += self._egress_volume("/relay/egress")
            if self.actual is not None:
                mounts += self._mount(self.release_record, "/relay/release/record.json")
            network = "none"
        elif self.provider_id is None:
            raise RuntimeError("no provider was started: the relay has no namespace to join")
        else:
            network = f"container:{self.provider_id}"
        before = self._heartbeat_started()
        docker(*self._common(self.names["relay"], network),
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
        if self.online:
            self._start_online()
            return
        self._start_provider()
        self.start_relay()

    def kill_relay(self) -> None:
        """A relay crash: the process dies at once, its records stay. The container is removed, not restarted."""
        docker("kill", self.names["relay"], check=False)
        docker("rm", "-f", self.names["relay"], check=False)

    def restart_relay(self) -> None:
        self.kill_relay()
        self.start_relay()

    def kill_gateway(self) -> None:
        """A gateway crash: its receipts stay; the relay's records never change because of it."""
        docker("kill", self.names["gateway"], check=False)
        docker("rm", "-f", self.names["gateway"], check=False)

    def restart_gateway(self) -> None:
        self.kill_gateway()
        self.path("gateway", "receipts", "ready").unlink(missing_ok=True)
        self._start_gateway(json.loads(self.path("gateway-config.json").read_text(encoding="utf-8")).get("test_resolution"))

    def roles(self) -> tuple[str, ...]:
        if not self.online:
            return ("relay", "provider")
        return ("relay", "gateway") if self.actual is not None else ("relay", "gateway", "provider")

    def heartbeat(self) -> dict[str, Any]:
        return json.loads(self.path("state", "heartbeat.json").read_text(encoding="utf-8"))

    def inspect(self) -> dict[str, Any]:
        """What Docker and each container's own kernel say: network modes, ports, mounts, namespace, interfaces, routes."""
        seen: dict[str, Any] = {"provider_id": self.provider_id}
        for role in self.roles():
            container = json.loads(docker("inspect", self.names[role]).stdout)[0]
            seen[role] = {"id": container["Id"], "network_mode": container["HostConfig"]["NetworkMode"],
                          "networks": sorted(container["NetworkSettings"]["Networks"]),
                          "ports": container["NetworkSettings"]["Ports"] or {},
                          "port_bindings": container["HostConfig"]["PortBindings"] or {},
                          "mounts": sorted(m["Destination"] for m in container["Mounts"]),
                          "kernel": json.loads(docker("exec", self.names[role], PYTHON, "-B", "-c", KERNEL_VIEW).stdout)}
        return seen

    def logs(self) -> str:
        logs = [docker("logs", self.names[role], check=False) for role in self.roles()]
        return "".join(each.stdout + each.stderr for each in logs)

    def stop(self) -> dict[str, Any]:
        for role in self.roles():
            docker("rm", "-f", self.names[role], check=False)
        if self.online:
            docker("network", "rm", self.names["egress"], check=False)
            docker("volume", "rm", self.names["egress"], check=False)
        label = f"label={LABEL}={self.run_id}"
        left = docker("ps", "-a", "--filter", label, "--format", "{{.Names}}", check=False).stdout.split()
        networks = docker("network", "ls", "--filter", label, "--format", "{{.Name}}", check=False).stdout.split()
        volumes = docker("volume", "ls", "--filter", label, "--format", "{{.Name}}", check=False).stdout.split()
        return {"containers_left": left, "networks_left": networks, "volumes_left": volumes}

    def remove_files(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
