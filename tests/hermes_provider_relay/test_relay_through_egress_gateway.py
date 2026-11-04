"""E1 in Docker (CONTRACT A6, ONLINE_CONTINUATION.md section 7): ACTUAL pinned Hermes in a no-network job, the relay
with no network at all, the keyless egress gateway on its own bridge, and an AUTHORED TLS stand-in for openrouter.ai
that the gateway reaches by its test resolution. Needs Docker. No real provider, DNS query, key or Internet address.

Three counts that do not trust each other: the relay's start records, the gateway's `opening` receipts (written before
its one connect) and the stand-in's receipts (written before it answers). Clocks: the relay, the gateway and the
stand-in share the Docker VM's wall clock; the host issues grants on its own wall clock (CONTRACT section 5 allowance).
Durations below are host monotonic time; no assertion compares a host time with a VM time.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research.hermes_interpreter import Interpreted, Unavailable
from leak_scan import find_leaks
from relay_harness import EXACT_CHARGE, RESERVATION, Rig, case, provider_receipts, relay_record
from relay_supervisor import HARDENING, HERE, LABEL, PYTHON, SUPPORT, docker
from test_relay_through_pinned_hermes import hostile

from conftest import SENTINEL

SOCKET = "/relay/egress/gateway.sock"
EXPIRES = b"{EXPIRES}"  # replaced inside the relay container by its own clock + 30 s

PROBE = """
import json, socket, sys, time
raw = bytes.fromhex(sys.argv[2]).replace(b'{EXPIRES}', repr(time.time() + 30).encode())
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect(sys.argv[1])
sock.sendall(raw)
answer = b''
try:
    while len(answer) < 2048:
        chunk = sock.recv(2048)
        if not chunk or b'\\r\\n\\r\\n' in answer + chunk:
            answer += chunk
            break
        answer += chunk
except OSError as error:
    answer += ('<' + type(error).__name__ + '>').encode()
print(json.dumps({'answer': answer.decode('latin-1')}))
"""

SCAN = """
import json, os, sys
needle, hits = sys.argv[1].encode(), []
for root in sys.argv[2:]:
    for folder, _, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            try:
                if needle in open(path, 'rb').read(4 * 1024 * 1024):
                    hits.append(path)
            except OSError:
                pass
print(json.dumps({'files': hits, 'environment': [k for k, v in os.environ.items() if needle.decode() in v]}))
"""

STAT = """
import json, os, stat, sys
folder = sys.argv[1]
info = os.stat(folder)
entries = sorted(os.listdir(folder))
sock = os.stat(os.path.join(folder, 'gateway.sock'))
print(json.dumps({'mode': oct(stat.S_IMODE(info.st_mode)), 'uid': info.st_uid, 'entries': entries,
                  'socket': stat.S_ISSOCK(sock.st_mode), 'socket_mode': oct(stat.S_IMODE(sock.st_mode))}))
"""


def root(evidence_root: Path) -> Path:
    return evidence_root / "online"


def gateway_receipts(relay: Any, attempt: str | None = None) -> list[dict[str, Any]]:
    path = relay.path("gateway", "receipts", "tunnels.jsonl")
    lines = path.read_text().splitlines() if path.exists() else []
    return [r for r in map(json.loads, lines) if attempt is None or r.get("attempt_id") == attempt]


def three_counts(relay: Any, attempt: str) -> tuple[int, int, int]:
    """(relay start records, gateway opening receipts, stand-in receipts) for one attempt."""
    openings = [r for r in gateway_receipts(relay, attempt) if r["outcome"] == "opening"]
    return int(relay_record(relay, attempt, "started") is not None), len(openings), len(provider_receipts(relay, attempt))


def stand_in_address(relay: Any) -> str:
    return json.loads(relay.path("gateway-config.json").read_text())["test_resolution"]


def probe(relay: Any, raw: bytes, socket_path: str = SOCKET) -> str:
    """One raw exchange with a gateway socket, from inside the relay container (its own user and mount)."""
    done = docker("exec", relay.names["relay"], PYTHON, "-B", "-c", PROBE, socket_path, raw.hex())
    return json.loads(done.stdout)["answer"]


def head(target: str = "openrouter.ai:443", attempt: str = "e1-probe", *, extra: bytes = b"") -> bytes:
    return (f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nX-Relay-Attempt: {attempt}\r\n".encode()
            + b"X-Relay-Expires: " + EXPIRES + b"\r\n" + extra + b"\r\n")


def wait_for(ready: Any, seconds: float = 60.0) -> None:
    until = time.monotonic() + seconds
    while not ready():
        assert time.monotonic() < until, "not ready in time"
        time.sleep(0.1)


# --- the counted path ------------------------------------------------------------------------------------------------


def test_one_admitted_request_is_one_relay_start_one_gateway_tunnel_and_one_stand_in_receipt(
        online_relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(online_relay, pinned_hermes_image, root(evidence_root), "e1-valid", case())

    result = rig.run_case()

    assert isinstance(result, Interpreted)
    assert three_counts(online_relay, "e1-valid-1") == (1, 1, 1)
    assert rig.spend.committed_usd() == EXACT_CHARGE and rig.saved().settlement.request_count == 1
    [receipt] = provider_receipts(online_relay, "e1-valid-1")
    assert receipt["bearer_matches"] is True and receipt["path"] == "/api/v1/chat/completions"
    opening, closing = gateway_receipts(online_relay, "e1-valid-1")
    assert (opening["outcome"], opening["address"], opening["test_resolution"]) == ("opening", stand_in_address(
        online_relay), True)
    assert closing["outcome"] == "tunnel" and closing["bytes_up"] > 0 and closing["bytes_down"] > 0
    container = rig.container_result("e1-valid-1")
    assert container["sandbox"]["network"]["blocked"] is True and container["sandbox"]["credential_mounted"] is False
    assert find_leaks(root(evidence_root) / "jobs", SENTINEL) == []
    assert find_leaks(online_relay.path("gateway"), SENTINEL) == []


# --- the gateway's own refusals, before any byte leaves --------------------------------------------------------------


@pytest.mark.parametrize("name, raw, reason", [
    ("name", head("openrouter.ai.example:443", "e1-neg-name"), "target_name_not_allowed"),
    ("literal", head("104.18.2.115:443", "e1-neg-literal"), "target_ip_literal"),
    ("port", head("openrouter.ai:80", "e1-neg-port"), "target_port_not_allowed"),
    ("header", head(attempt="e1-neg-header", extra=b"Proxy-Authorization: Basic eA==\r\n"), "header_invalid"),
    ("second", head(attempt="e1-neg-second") + head(attempt="e1-neg-second-b"), "data_before_tunnel"),
    ("early-tls", head(attempt="e1-neg-tls") + b"\x16\x03\x01\x00", "data_before_tunnel"),
    ("expired", head(attempt="e1-neg-expired").replace(EXPIRES, b"1.0"), "expiry_invalid"),
])
def test_the_gateway_refuses_every_other_connect_before_any_byte_leaves(online_relay, name, raw, reason) -> None:
    before = len(gateway_receipts(online_relay))
    assert probe(online_relay, raw) == f"HTTP/1.1 403 Forbidden\r\nX-Refusal: {reason}\r\n\r\n"
    new = gateway_receipts(online_relay)[before:]
    assert [(r["outcome"], r["reason"]) for r in new] == [("refused", reason)]  # receipted; no opening, no connect


def test_an_attempt_is_tunnelled_at_most_once(online_relay) -> None:
    first = probe(online_relay, head(attempt="e1-repeat"))
    second = probe(online_relay, head(attempt="e1-repeat"))
    assert first.startswith("HTTP/1.1 200 Connection Established\r\n\r\n")
    assert second == "HTTP/1.1 403 Forbidden\r\nX-Refusal: attempt_repeated\r\n\r\n"
    assert [r["outcome"] for r in gateway_receipts(online_relay, "e1-repeat")][:1] == ["opening"]
    assert sum(r["outcome"] == "opening" for r in gateway_receipts(online_relay, "e1-repeat")) == 1


def test_a_private_name_answer_is_refused_by_a_dns_mode_gateway_before_any_connect(online_relay) -> None:
    """A second gateway in DNS mode (no test resolution) whose name lookup answers the stand-in's private bridge
    address from its hosts file: no DNS packet is sent, and the gateway must refuse the whole name."""
    name = f"relay-gateway-dns-{online_relay.run_id}"
    receipts = online_relay.path("gateway", "dns-receipts")
    receipts.mkdir(mode=0o700)
    config = online_relay.path("gateway-dns-config.json")
    config.write_text(json.dumps({"socket": "/egress/gateway-dns.sock", "receipts": "/gateway/receipts",
                                   "destination": {"host": "openrouter.ai", "port": 443}}))  # A8: its one target
    mount = online_relay._mount  # noqa: SLF001 - the supervisor's own exact mount form
    try:
        docker(*online_relay._common(name, online_relay.names["egress"]),  # noqa: SLF001
               "--add-host", f"openrouter.ai:{stand_in_address(online_relay)}",
               "--mount", f"type=volume,src={online_relay.names['egress']},dst=/egress",
               *mount(receipts, "/gateway/receipts", writable=True),
               *mount(HERE / "egress_gateway.py", "/gateway/egress_gateway.py"),
               *mount(config, "/gateway/config.json"),
               online_relay.image, "-B", "/gateway/egress_gateway.py", "/gateway/config.json")
        wait_for(lambda: (receipts / "ready").exists())
        answer = probe(online_relay, head(attempt="e1-dns-private"), "/relay/egress/gateway-dns.sock")
        assert answer == "HTTP/1.1 403 Forbidden\r\nX-Refusal: dns_answer_not_global\r\n\r\n"
        [line] = [json.loads(x) for x in (receipts / "tunnels.jsonl").read_text().splitlines()]
        assert (line["outcome"], line["reason"]) == ("refused", "dns_answer_not_global")
    finally:
        docker("rm", "-f", name, check=False)
        docker("exec", online_relay.names["relay"], PYTHON, "-c",
               "import os; os.path.exists('/relay/egress/gateway-dns.sock') and os.unlink('/relay/egress/gateway-dns.sock')",
               check=False)


def test_an_actual_release_never_starts_in_the_pinned_image(online_relay) -> None:
    """The relay process itself, with a well-formed synthetic ACTUAL record: no record is approved, so it exits."""
    folder = online_relay.path("actual-refusal")
    folder.mkdir(mode=0o700)
    record = folder / "record.json"
    record.write_text(json.dumps({"kind": "ACTUAL", "synthetic": True}))
    (folder / "config.json").write_text(json.dumps({
        "release_record": {"path": "/relay/release/record.json", "sha256": hashlib.sha256(record.read_bytes()).hexdigest()},
        "gateway_socket": SOCKET, "channel_roots": {}, "paths": {}}))
    mount = online_relay._mount  # noqa: SLF001
    done = docker("run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", *HARDENING,
                  "--label", f"{LABEL}={online_relay.run_id}", "--entrypoint", PYTHON,
                  "--env", "RELAY_SUPPORT_PATH=/relay/support/job:/relay/support/interpretation",
                  *mount(HERE, "/relay/code"), *mount(SUPPORT[0], "/relay/support/job"),
                  *mount(SUPPORT[1], "/relay/support/interpretation"), *mount(record, "/relay/release/record.json"),
                  *mount(folder / "config.json", "/relay/config.json"),
                  online_relay.image, "-B", "/relay/code/relay_service.py", "/relay/config.json", check=False)
    assert done.returncode != 0 and "not an approved ACTUAL release" in done.stderr


# --- isolation: namespaces, mounts, keys ----------------------------------------------------------------------------


def test_the_relay_has_no_network_the_gateway_holds_no_key_and_only_the_relay_mounts_the_key(online_relay) -> None:
    seen = online_relay.inspect()
    (online_relay.root.parent / "online-inspect.json").write_text(json.dumps(seen, indent=1, sort_keys=True))
    relay, gateway, stand_in = seen["relay"], seen["gateway"], seen["provider"]
    assert relay["network_mode"] == "none"
    assert relay["kernel"]["interfaces_up"] == ["lo"] and relay["kernel"]["ipv4_routes"] == []
    assert relay["kernel"]["ipv6_routes_not_loopback"] == []
    assert gateway["networks"] == [online_relay.names["egress"]] and stand_in["networks"] == [online_relay.names["egress"]]
    for side in (relay, gateway, stand_in):
        assert side["ports"] == {} and side["port_bindings"] == {}
    assert "/relay/secrets/provider-key" in relay["mounts"] and "/relay/egress" in relay["mounts"]
    assert gateway["mounts"] == ["/egress", "/gateway/config.json", "/gateway/egress_gateway.py", "/gateway/receipts"]
    assert "/egress" not in stand_in["mounts"] and "/relay/egress" not in stand_in["mounts"]
    for role in ("relay", "gateway"):
        [container] = json.loads(docker("inspect", online_relay.names[role]).stdout)
        host = container["HostConfig"]
        assert host["ReadonlyRootfs"] is True and host["CapDrop"] == ["ALL"] and host["Privileged"] is False
        assert "no-new-privileges" in " ".join(host["SecurityOpt"] or []) and container["Config"]["User"] not in ("", "0", "root")
        assert not any("docker.sock" in (m.get("Source") or "") for m in container["Mounts"])
    scan = json.loads(docker("exec", online_relay.names["gateway"], PYTHON, "-B", "-c", SCAN, SENTINEL,
                             "/egress", "/gateway", "/tmp").stdout)
    assert scan == {"files": [], "environment": []}


def test_the_socket_volume_is_private_holds_only_the_socket_and_is_shared_by_the_relay_and_gateway_only(
        online_relay) -> None:
    [volume] = json.loads(docker("volume", "inspect", online_relay.names["egress"]).stdout)
    assert volume["Driver"] == "local" and volume["Labels"] == {LABEL: online_relay.run_id}
    assert volume["Options"] == {"type": "tmpfs", "device": "tmpfs",
                                 "o": f"uid={os.getuid()},gid={os.getgid()},mode=0700,size=1m"}
    for role, folder in (("gateway", "/egress"), ("relay", "/relay/egress")):
        seen = json.loads(docker("exec", online_relay.names[role], PYTHON, "-B", "-c", STAT, folder).stdout)
        assert seen == {"mode": "0o700", "uid": os.getuid(), "entries": ["gateway.sock"], "socket": True,
                        "socket_mode": "0o600"}, (role, seen)


def test_a_hostile_job_reaches_neither_the_gateway_nor_the_stand_in_nor_any_name(
        online_relay, pinned_hermes_image, evidence_root) -> None:
    targets = [[online_relay.names["gateway"], 443], [stand_in_address(online_relay), 443], ["openrouter.ai", 443],
               ["1.1.1.1", 53]]
    rig, found = hostile(online_relay, pinned_hermes_image, root(evidence_root), "e1-hostile-probe",
                         {"probe_key": True, "probe_egress": targets})
    assert found["key"] == {"readable_key_files": [], "key_like_environment": []}
    assert [entry["connected"] for entry in found["egress"]] == [False, False, False, False]
    assert three_counts(online_relay, "e1-hostile-probe-1") == (0, 0, 0)


@pytest.mark.parametrize("name, actions, refusal", [
    ("e1-hostile-route", {"message": {"route_id": "other-route"}}, "route_mismatch"),
    ("e1-hostile-release", {"message": {"release_id": "local-relay-2"}}, "release_mismatch"),
    ("e1-hostile-model", {"message": {}, "body_changes": {"model": "other-model/9"}}, "guard:model_not_as_configured"),
    ("e1-hostile-url", {"message": {"url": "https://exfiltrate.invalid/v1"}}, "channel_field_not_permitted"),
    ("e1-hostile-big", {"message": {}, "body_changes": {"padding": "x" * 13_000}}, "request_too_large"),
    ("e1-hostile-session", {"message": {}, "body_changes": {"session_id": "p05-e1-valid-1"}}, "body_attempt_mismatch"),
])
def test_a_hostile_channel_message_is_refused_before_the_gateway_is_contacted(
        online_relay, pinned_hermes_image, evidence_root, name, actions, refusal) -> None:
    rig, found = hostile(online_relay, pinned_hermes_image, root(evidence_root), name, actions)
    assert found["replies"] == [{"attempt_id": f"{name}-1", "outcome": "refused", "refusal": refusal, "before_send": True}]
    assert three_counts(online_relay, f"{name}-1") == (0, 0, 0) and gateway_receipts(online_relay, f"{name}-1") == []


def test_a_duplicate_request_is_sent_once_through_one_tunnel(online_relay, pinned_hermes_image, evidence_root) -> None:
    rig, found = hostile(online_relay, pinned_hermes_image, root(evidence_root), "e1-twice", {"message": {}, "repeat": 2})
    assert found["replies"][0]["outcome"] == "reply" and found["replies"][1:] == [None, None]
    assert three_counts(online_relay, "e1-twice-1") == (1, 1, 1)


# --- replies that may have cost: one request, the full reservation stays --------------------------------------------


@pytest.mark.parametrize("name, script, outcome, refusal", [
    ("e1-lost", {"kind": "lost_reply"}, "lost", None),
    ("e1-oversized", {"kind": "oversized_reply", "bytes": 70_000}, "refused_reply", "reply_too_large"),
    ("e1-redirect", {"kind": "redirect"}, "refused_reply", "reply_redirect_refused"),
    ("e1-encoded", {"kind": "encoded"}, "refused_reply", "reply_encoded_refused"),
    ("e1-provider-error", {"kind": "http_error", "status": 500, "message": "upstream failed"}, "reply", None),
    ("e1-no-usage", {"usage": None}, "reply", None),
])
def test_a_reply_without_a_usable_count_keeps_the_full_reservation(online_relay, pinned_hermes_image, evidence_root,
                                                                     name, script, outcome, refusal) -> None:
    rig = Rig(online_relay, pinned_hermes_image, root(evidence_root), name, {**case(), **script})

    result = rig.run_case()

    attempt = f"{name}-1"
    finished = relay_record(online_relay, attempt, "finished")
    assert isinstance(result, Unavailable) and finished["outcome"] == outcome and finished.get("refusal") == refusal
    assert three_counts(online_relay, attempt) == (1, 1, 1)
    assert rig.spend.state(attempt) == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


# --- faults: gateway down or killed, hung stand-in, relay crash -----------------------------------------------------


def test_with_the_gateway_down_the_started_attempt_is_lost_and_nothing_leaves(online_relay, pinned_hermes_image,
                                                                              evidence_root) -> None:
    rig = Rig(online_relay, pinned_hermes_image, root(evidence_root), "e1-gateway-down", case())
    online_relay.kill_gateway()
    try:
        result = rig.run_case()
    finally:
        online_relay.restart_gateway()
    attempt = "e1-gateway-down-1"
    finished = relay_record(online_relay, attempt, "finished")
    assert isinstance(result, Unavailable) and finished["outcome"] == "lost"
    assert finished["error"] in ("ConnectionRefusedError", "FileNotFoundError")  # a stale socket file or none
    assert three_counts(online_relay, attempt) == (1, 0, 0)
    assert rig.spend.state(attempt) == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_a_gateway_killed_during_a_tunnel_leaves_its_count_and_the_attempt_is_never_tunnelled_again(
        online_relay, pinned_hermes_image, evidence_root) -> None:
    rig = Rig(online_relay, pinned_hermes_image, root(evidence_root), "e1-gateway-killed", {"kind": "hang"},
              timeout_seconds=30)
    attempt = "e1-gateway-killed-1"

    def kill_when_sent() -> None:
        until = time.monotonic() + 60
        while not provider_receipts(online_relay, attempt) and time.monotonic() < until:
            time.sleep(0.1)
        online_relay.kill_gateway()

    killer = threading.Thread(target=kill_when_sent)
    killer.start()
    try:
        result = rig.run_case()
    finally:
        killer.join()
        online_relay.restart_gateway()
    assert isinstance(result, Unavailable) and relay_record(online_relay, attempt, "finished")["outcome"] == "lost"
    assert three_counts(online_relay, attempt) == (1, 1, 1)  # the opening line was fsynced before the connect
    assert probe(online_relay, head(attempt=attempt)) == "HTTP/1.1 403 Forbidden\r\nX-Refusal: attempt_repeated\r\n\r\n"
    assert rig.spend.state(attempt) == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_a_hung_stand_in_is_cut_by_the_relay_before_the_grant_expiry(online_relay, pinned_hermes_image,
                                                                      evidence_root) -> None:
    rig = Rig(online_relay, pinned_hermes_image, root(evidence_root), "e1-hung", {"kind": "hang"}, timeout_seconds=25)
    began = time.monotonic()

    result = rig.run_case()

    attempt = "e1-hung-1"
    assert isinstance(result, Unavailable) and time.monotonic() - began < 25 + 5 + 2 + 5
    wait_for(lambda: relay_record(online_relay, attempt, "finished") is not None, 10)
    assert relay_record(online_relay, attempt, "finished")["outcome"] == "lost"
    assert three_counts(online_relay, attempt) == (1, 1, 1)
    wait_for(lambda: any(r["outcome"] == "tunnel" for r in gateway_receipts(online_relay, attempt)), 10)
    [closing] = [r for r in gateway_receipts(online_relay, attempt) if r["outcome"] == "tunnel"]
    assert closing["close_reason"] == "client_closed"  # the relay's own A5 cut, before the gateway's expiry backstop
    assert rig.spend.state(attempt) == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_a_relay_crash_after_a_possible_request_never_opens_a_second_tunnel(online_relay, pinned_hermes_image,
                                                                            evidence_root) -> None:
    rig = Rig(online_relay, pinned_hermes_image, root(evidence_root), "e1-relay-crash", {"kind": "hang"},
              timeout_seconds=60)
    attempt = "e1-relay-crash-1"

    def crash_when_sent() -> None:
        until = time.monotonic() + 60
        while not provider_receipts(online_relay, attempt) and time.monotonic() < until:
            time.sleep(0.1)
        online_relay.restart_relay()

    crasher = threading.Thread(target=crash_when_sent)
    crasher.start()
    result = rig.run_case()
    crasher.join()
    assert isinstance(result, Unavailable)
    assert relay_record(online_relay, attempt, "finished")["outcome"] == "unknown_restart"
    assert three_counts(online_relay, attempt) == (1, 1, 1)
    assert rig.spend.state(attempt) == "UNKNOWN" and rig.spend.committed_usd() == RESERVATION


def test_no_online_record_receipt_or_log_holds_the_synthetic_key(online_relay, evidence_root) -> None:
    assert find_leaks(root(evidence_root) / "jobs", SENTINEL) == []
    assert find_leaks(online_relay.root, SENTINEL) == []  # relay state, gateway receipts, stand-in receipts, configs
    assert SENTINEL not in online_relay.logs()
