"""What the relay's egress self-probe records for one connection attempt. Host loopback only, no Docker.

Each probe records how the attempt ended: connected, refused, unreachable, dns_failure or timeout. A refused connection
means that something at that address answered, so it is never recorded as a blocked path. The Docker tests use these
outcomes with positive controls; only `unreachable` there, with a working control, shows that no route exists.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace

from relay_service import Relay


def probe(*targets: tuple[str, int]) -> list[dict]:
    # `expect` only lets the probe of 5e8059b (which read it) run, so that the RED run failed on the outcome itself
    relay = SimpleNamespace(probes=[{"host": h, "port": p, "expect": "reachable"} for h, p in targets], egress=[])
    Relay.probe(relay)  # the relay's own probe, on a stand-in holding only the probe list
    return relay.egress


def test_a_listening_port_is_recorded_connected() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        [entry] = probe(("127.0.0.1", listener.getsockname()[1]))
    assert entry.get("outcome") == "connected"


def test_a_refused_connection_is_recorded_as_an_answer_not_as_a_blocked_path() -> None:
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
    [entry] = probe(("127.0.0.1", port))  # nothing holds the port now: the host answers with a reset
    assert entry.get("outcome") == "refused"


def test_a_name_that_does_not_resolve_is_recorded_as_a_dns_failure() -> None:
    [entry] = probe(("relay-probe-target.invalid", 443))
    assert entry.get("outcome") == "dns_failure"
