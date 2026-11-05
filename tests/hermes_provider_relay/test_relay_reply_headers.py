"""The relay records the two named Orbio reply headers on its saved evidence, bounded, and no other response header.

Decision 5 of the Orbio route ticket. A release records them only when its record names them; the adopted OpenRouter
record does not, so its `finished.json` keeps its shape. No network beyond loopback, no key, no provider.
"""

from __future__ import annotations

import hashlib
import json
import socket
import ssl
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import test_relay_service_actual as service_rig
from test_relay_actual_release import load, record
from test_relay_service_actual import Rig, actual_body, reply
from test_relay_transport import tls  # noqa: F401 - fixture

from conftest import SENTINEL
from relay_admission import ProviderDestination
from relay_transport import SentReply, send_once

BALANCE, IGNORED = "X-Orbio-Balance", "X-Orbio-Ignored-Parameters"
NAMED = [BALANCE, IGNORED]


def answering_server(tls: Path, head: bytes) -> int:  # noqa: F811
    """A loopback TLS server that answers one request with this head and an empty JSON body."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls / "server.pem", tls / "server.key")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        wrapped = context.wrap_socket(connection, server_side=True)
        try:
            received = b""
            while b"\r\n\r\n" not in received:
                received += wrapped.recv(65536)
            wrapped.sendall(head + b"{}")
            wrapped.unwrap()
        except (OSError, ValueError):
            pass
        finally:
            wrapped.close()
            listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]


HEAD = (b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 2\r\nconnection: close\r\n"
        b"x-orbio-balance: 4.25\r\nX-Orbio-Ignored-Parameters: top_k\r\nx-orbio-other: secret\r\nset-cookie: a=b\r\n\r\n")


def sent(tls: Path, port: int, **options: Any) -> SentReply:  # noqa: F811
    return send_once(ProviderDestination("localhost", port, "/v1/chat/completions"), ca_file=str(tls / "ca.pem"),
                     key="k", body=b"{}", deadline=time.time() + 5, max_reply_bytes=1024, **options)


def test_the_transport_returns_only_the_headers_it_was_asked_for(tls: Path) -> None:  # noqa: F811
    assert sent(tls, answering_server(tls, HEAD), reply_headers=tuple(NAMED)).headers == {
        BALANCE: "4.25", IGNORED: "top_k"}


def test_the_transport_returns_no_header_unless_asked(tls: Path) -> None:  # noqa: F811
    assert sent(tls, answering_server(tls, HEAD)).headers == {}


def test_an_absent_header_is_absent_not_empty(tls: Path) -> None:  # noqa: F811
    head = b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 2\r\nconnection: close\r\n\r\n"
    assert sent(tls, answering_server(tls, head), reply_headers=tuple(NAMED)).headers == {}


def test_a_record_may_name_exactly_the_two_headers() -> None:
    assert load(record(recorded_reply_headers=NAMED)).recorded_reply_headers == tuple(NAMED)
    assert load(record()).recorded_reply_headers == ()


@pytest.mark.parametrize("given", [
    [], [BALANCE], [IGNORED, BALANCE], [BALANCE, IGNORED, "X-Orbio-Other"], [BALANCE, "Authorization"],
    ["x-orbio-balance", IGNORED], [BALANCE, BALANCE], None, "X-Orbio-Balance", {BALANCE: IGNORED}])
def test_a_record_naming_any_other_headers_is_refused(given: Any) -> None:
    with pytest.raises(ValueError, match="recorded_reply_headers"):
        load(record(recorded_reply_headers=given))


@pytest.fixture
def named_rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    plain = service_rig.record
    monkeypatch.setattr(service_rig, "record", lambda ca: {**plain(ca), "recorded_reply_headers": NAMED})
    return Rig(tmp_path, monkeypatch)


def answer(rig: Rig, headers: dict[str, str], *, status: int = 200, body: bytes | None = None) -> dict[str, Any]:
    rig.answer = SentReply(status, "application/json", reply() if body is None else body, headers=headers)
    rig.run("a1", actual_body("a1"))
    return rig.record_of("a1", "finished")


def test_the_relay_asks_for_the_records_headers_and_saves_them(named_rig: Rig) -> None:
    finished = answer(named_rig, {BALANCE: "4.25", IGNORED: ""})
    assert named_rig.sends[0]["reply_headers"] == tuple(NAMED)
    assert finished["reply_headers"] == {BALANCE: "4.25", IGNORED: ""} and finished["reply_headers_refused"] == {}


def test_the_headers_are_saved_on_a_refused_reply_too(named_rig: Rig) -> None:
    finished = answer(named_rig, {BALANCE: "4.25"}, status=402, body=b"{}")
    assert finished["outcome"] == "refused_reply" and finished["reply_headers"] == {BALANCE: "4.25"}


def test_the_headers_never_reach_the_job_channel(named_rig: Rig) -> None:
    answer(named_rig, {BALANCE: "4.25"})
    assert "4.25" not in json.dumps(named_rig.channel_reply("a1"))


@pytest.mark.parametrize("value, reason", [
    (f"balance {SENTINEL}", "secret"), ("sk-orbio-abcdef", "secret"), ("9" * 257, "too_long"),
    ("4.25\x07", "not_printable"), ("4.25é", "not_printable")])
def test_a_value_that_is_a_secret_too_long_or_not_printable_is_not_saved(named_rig: Rig, value: str, reason: str) -> None:
    finished = answer(named_rig, {BALANCE: value, IGNORED: "top_k"})
    assert finished["reply_headers"] == {IGNORED: "top_k"} and finished["reply_headers_refused"] == {BALANCE: reason}
    saved = (named_rig.root / "state" / "a1" / "finished.json").read_text()
    assert value not in saved and json.dumps(value)[1:-1] not in saved


def test_a_value_at_the_limit_is_saved(named_rig: Rig) -> None:
    assert answer(named_rig, {BALANCE: "9" * 256})["reply_headers"] == {BALANCE: "9" * 256}


def test_a_header_the_transport_should_not_have_returned_is_not_saved(named_rig: Rig) -> None:
    finished = answer(named_rig, {BALANCE: "4.25", "Set-Cookie": "a=b"})
    assert finished["reply_headers"] == {BALANCE: "4.25"} and "Set-Cookie" not in json.dumps(finished)


def test_a_record_that_names_no_headers_keeps_its_finished_record_and_asks_for_none(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path, monkeypatch)
    finished = answer(rig, {BALANCE: "4.25"})
    assert rig.sends[0]["reply_headers"] == ()
    assert set(finished) == {"attempt_id", "at", "outcome", "refusal", "status", "reply_bytes", "reply_sha256", "usage", "cost",
                             "generation_id", "seconds"}
    assert hashlib.sha256(reply()).hexdigest() == finished["reply_sha256"]
