"""Forward history recorder behavior through its real entry points with authored synthetic HTTP bytes.

Only the external transport, clocks, credential source and temporary paths are injected. The real QuickNode client,
the recorder schedule, journal, coverage logic and the pure payload projection run unchanged. Every value is a
synthetic fixture. Nothing here is provider, chain or market evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.research_history.http_clients.http_transport import HttpResponse
from edge_os_api.research_history.provider_transport import SourceTimeout
from scripts.forward_history_recorder import (
    AdmissionRefused,
    AttemptExists,
    RecorderInputError,
    hypersync_batches,
    main,
    recover_attempt,
    run_attempt,
    validate_input,
)

T0 = 1_800_000_000
WE = T0 + 1200
POOL = "0x" + "22" * 20
WMON = "0x" + "33" * 20  # token0, quote
MOE = "0x" + "44" * 20  # token1, base
FACTORY = "0x" + "55" * 20
CREATION_TOPIC0 = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
SWAP_TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
CREATION_TX = "0x" + "c1" * 32
CREATION_BLOCK_HASH = "0x" + "c2" * 32
ZERO_WORD = "0x" + "00" * 32
QN_HOST = "qn.example.invalid"
QN_PATH_SECRET = "SENTINEL-QN-PATH-SECRET"
QN_URL = f"https://{QN_HOST}/{QN_PATH_SECRET}/"
HS_URL = "https://hypersync.example.invalid/query"
HS_TOKEN = "SENTINEL-HS-TOKEN-VALUE"
ORACLE_ABSENT_SHA = "c7032fb27b3a0b2103c49ab792a402dc9e5c99795b948dab1f3ff297d7fbcccf"
EMPTY_SHA = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
SECRETS = (QN_PATH_SECRET, HS_TOKEN)


def _word(value: int) -> str:
    return "%064x" % value


def _addr_word(address: str) -> str:
    return "0" * 24 + address[2:]


# Synthetic chain: block 0 precedes T0; block n >= 1 has timestamp T0 + 10 * (n - 1).


def block_ts(number: int) -> int:
    return T0 - 200 if number == 0 else T0 + 10 * (number - 1)


def block_hash(number: int) -> str:
    return "0x" + "11" * 32 if number == 1 else "0x" + "%064x" % (0xB0000 + number)


def head_at(now: float, lag: float) -> int:
    number = 0
    while block_ts(number + 1) <= now - lag:
        number += 1
    return number


ORACLE_SWAP = {"block_number": 1, "transaction_index": 0, "log_index": 0, "address": POOL, "topic0": SWAP_TOPIC0,
               "topic1": ZERO_WORD, "topic2": ZERO_WORD, "data": "0x" + _word(1) + _word(0) + _word(0) + _word(2),
               "transaction_hash": "0x" + "aa" * 32, "removed": False}
BOUNDARY_SWAP = dict(ORACLE_SWAP, block_number=121, transaction_hash="0x" + "ab" * 32)  # B_POST, outside window


class FakeClock:
    def __init__(self, utc: float) -> None:
        self.now = utc
        self.mono = 1000.0
        self.sleep_hook: Callable[[float], float] | None = None

    def utc(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        extra = self.sleep_hook(self.now + seconds) if self.sleep_hook else 0.0
        self.advance(seconds + extra)

    def advance(self, seconds: float) -> None:
        self.now += seconds
        self.mono += seconds


def _rpc(result: Any, call_id: int = 1) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": call_id, "result": result}).encode()


def creation_receipt(**log_changes: Any) -> dict[str, Any]:
    log = {"address": FACTORY, "topics": [CREATION_TOPIC0, "0x" + _addr_word(WMON), "0x" + _addr_word(MOE)],
           "data": "0x" + _addr_word(POOL) + _word(2854), "logIndex": "0x6", "transactionIndex": "0x2",
           "transactionHash": CREATION_TX, "blockNumber": hex(900), "blockHash": CREATION_BLOCK_HASH,
           "removed": False}
    log.update(log_changes)
    other = dict(log, address="0x" + "66" * 20, logIndex="0x5")
    return {"transactionHash": CREATION_TX, "status": "0x1", "blockNumber": hex(900), "blockHash": CREATION_BLOCK_HASH,
            "transactionIndex": "0x2", "logs": [other, log]}


def creation_page(**log_changes: Any) -> dict[str, Any]:
    log = {"block_number": 900, "block_hash": CREATION_BLOCK_HASH, "transaction_hash": CREATION_TX,
           "transaction_index": 2, "log_index": 6, "address": FACTORY, "topic0": CREATION_TOPIC0,
           "topic1": "0x" + _addr_word(WMON), "topic2": "0x" + _addr_word(MOE),
           "data": "0x" + _addr_word(POOL) + _word(2854)}
    log.update(log_changes)
    return {"archive_height": 5000, "next_block": 901,
            "data": [{"blocks": [{"number": 900, "timestamp": T0 - 86_400, "hash": CREATION_BLOCK_HASH}],
                      "logs": [log]}]}


class SyntheticProviders:
    """Authored HTTP bytes for QuickNode JSON-RPC and HyperSync. Records every request that reaches it."""

    def __init__(self, clock: FakeClock, *, lag: float = 1.0, latency: float = 0.25) -> None:
        self.clock = clock
        self.lag = lag
        self.latency = latency
        self.calls: list[dict[str, Any]] = []
        self.swaps = [ORACLE_SWAP, BOUNDARY_SWAP]
        self.overrides: dict[int, Callable[[dict[str, Any]], Any]] = {}
        self.rpc: dict[str, Any] = {}
        self.journal_seen: list[bool] = []
        self.journal_path: Path | None = None

    def request(self, *, method: str, url: str, headers: Any, body: bytes, timeout: float, deadline: float,
                max_response_bytes: int, cancel: Any = None) -> HttpResponse:
        call = {"url": url, "body": json.loads(body), "index": len(self.calls), "headers": dict(headers),
                "timeout": timeout, "deadline": deadline, "max_response_bytes": max_response_bytes}
        call["provider"] = "quicknode" if url == QN_URL else "hypersync"
        call["what"] = call["body"].get("method") or f"query:{call['body'].get('from_block')}"
        self.calls.append(call)
        if self.journal_path is not None:
            lines = self.journal_path.read_text().splitlines()
            self.journal_seen.append(json.loads(lines[-1])["event"] == "ADMITTED")
        self.clock.advance(self.latency)
        override = self.overrides.get(len(self.calls))
        if override is not None:
            produced = override(call)
            if produced is not None:
                return produced
        if call["provider"] == "quicknode":
            return HttpResponse(200, {"content-type": "application/json"}, _rpc(self._rpc(call["body"]),
                                                                                  call["body"]["id"]))
        return HttpResponse(200, {"content-type": "application/json"}, json.dumps(self._query(call["body"])).encode())

    def _rpc(self, body: dict[str, Any]) -> Any:
        method, params = body["method"], body["params"]
        if method in self.rpc:
            return self.rpc[method](params) if callable(self.rpc[method]) else self.rpc[method]
        if method == "eth_chainId":
            return "0x8f"
        if method == "eth_getTransactionReceipt":
            return creation_receipt()
        if method == "eth_getCode":
            return "0x6080604052"
        if method == "eth_getBlockByNumber":
            number = head_at(self.clock.now, self.lag)
            if params[0] == "finalized":
                number = max(0, number - 1)
            return {"number": hex(number), "timestamp": hex(block_ts(number)), "hash": block_hash(number)}
        if method == "eth_call":
            data = params[0]["data"]
            if data == "0xc45a0155":
                return "0x" + _addr_word(FACTORY)
            if data == "0x313ce567":
                return "0x" + _word(18)
            if data == "0x0dfe1681":
                return "0x" + _addr_word(WMON)
            if data == "0xd21220a7":
                return "0x" + _addr_word(MOE)
        raise AssertionError(f"unexpected rpc {method}")

    def _query(self, body: dict[str, Any]) -> dict[str, Any]:
        if body["logs"][0]["address"] == [FACTORY]:
            return creation_page()
        start = body["from_block"]
        head = head_at(self.clock.now, self.lag)
        stop = max(start, head) + 1 if head >= start else start + 1
        blocks = [{"number": n, "timestamp": block_ts(n), "hash": block_hash(n)} for n in range(start, stop)]
        logs = []
        for swap in self.swaps:
            if start <= swap["block_number"] < stop:
                log = dict(swap)
                log["block_hash"] = block_hash(swap["block_number"])
                logs.append(log)
        return {"archive_height": head, "next_block": stop, "data": [{"blocks": blocks, "logs": logs}]}


def recorder_input(tmp_path: Path, **changes: Any) -> dict[str, Any]:
    value = {
        "schema_version": "edge-os.forward-history-input/1",
        "predecessor_sha256": "c4fc01c4d498742cd9a904606135fdb2b27fea448bb254462a79a9f67824312f",
        "attempt_id": "synthetic-attempt-1", "source_id": "forward-synthetic-1", "evidence_class": "SYNTHETIC",
        "chain_id": 143, "pool": POOL, "token0": WMON, "token1": MOE, "base": MOE, "quote": WMON,
        "swap_topic0": SWAP_TOPIC0,
        "selectors": {"decimals": "0x313ce567", "token0": "0x0dfe1681", "token1": "0xd21220a7",
                      "factory": "0xc45a0155"},
        "expected_decimals": {"token0": 18, "token1": 18},
        "creation": {"decoder": "retained-v2-pair-created/1", "transaction_hash": CREATION_TX,
                     "block_number": 900, "block_hash": CREATION_BLOCK_HASH, "transaction_index": 2,
                     "log_index": 6, "factory": FACTORY, "topic0": CREATION_TOPIC0},
        "t0_utc": "2027-01-15T08:00:00Z", "window_seconds": 1200, "bucket_seconds": 300,
        "destinations": {"quicknode_host": QN_HOST, "hypersync_url": HS_URL},
        "credential_slots": {"quicknode": "quicknode_monad_url", "hypersync": "envio_hypersync_bearer"},
        "output_dir": str(tmp_path / "attempts"),
        "decisions": {"D1": "decision-ref-d1", "D2": "decision-ref-d2", "D3": "decision-ref-d3"},
        "plans": {"quicknode": "plan-ref-qn", "hypersync": "plan-ref-hs"},
        "p6": {"status": "EXTERNAL_EVIDENCE_REQUIRED", "destination_ref": "p6-destination-ref",
               "evidence_refs": []},
    }
    for key, item in changes.items():
        value[key] = item
    (tmp_path / "attempts").mkdir(exist_ok=True)
    return value


class Credentials:
    def __init__(self, quicknode: str = QN_URL) -> None:
        self.reads: list[str] = []
        self.values = {"quicknode_monad_url": quicknode, "envio_hypersync_bearer": HS_TOKEN}

    def __call__(self, slot: str) -> str:
        self.reads.append(slot)
        return self.values[slot]


def run(tmp_path: Path, *, start: float = T0 - 600, lag: float = 1.0, latency: float = 0.25,
        configure: Callable[[SyntheticProviders, FakeClock], None] | None = None,
        credentials: Credentials | None = None, **input_changes: Any) -> tuple[dict, SyntheticProviders, Path]:
    clock = FakeClock(start)
    providers = SyntheticProviders(clock, lag=lag, latency=latency)
    if configure:
        configure(providers, clock)
    result = run_attempt(recorder_input(tmp_path, **input_changes), transport=providers, clock=clock,
                         credentials=credentials or Credentials())
    return result, providers, tmp_path / "attempts" / "synthetic-attempt-1"


def sequence(providers: SyntheticProviders) -> list[str]:
    return [f"{call['provider']}:{call['what']}" for call in providers.calls]


def count(providers: SyntheticProviders, provider: str) -> int:
    return sum(1 for call in providers.calls if call["provider"] == provider)


def handoff_of(result: dict[str, Any]) -> dict[str, Any]:
    body = Path(result["handoff_path"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == result["handoff_sha256"]
    return json.loads(body)


def all_bytes(directory: Path) -> bytes:
    return b"".join(path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file())


# Success transcript and counts


def test_first_covering_reads_use_17_quicknode_and_5_hypersync_calls_in_packet_order(tmp_path: Path) -> None:
    result, providers, attempt = run(tmp_path)
    assert result["status"] == "COMPLETED"
    assert sequence(providers) == [
        "quicknode:eth_chainId", "quicknode:eth_getTransactionReceipt", "hypersync:query:900",
        "quicknode:eth_call", "quicknode:eth_getCode", "quicknode:eth_getCode", "quicknode:eth_getCode",
        "quicknode:eth_getBlockByNumber",
        "hypersync:query:0", "hypersync:query:34", "hypersync:query:64", "hypersync:query:94",
        "quicknode:eth_call", "quicknode:eth_call", "quicknode:eth_call", "quicknode:eth_call",
        "quicknode:eth_getBlockByNumber", "quicknode:eth_getBlockByNumber",
        "quicknode:eth_call", "quicknode:eth_call", "quicknode:eth_call", "quicknode:eth_call"]
    assert (count(providers, "quicknode"), count(providers, "hypersync")) == (17, 5)
    p4 = [call["body"]["params"] for call in providers.calls[12:16]]
    assert [(p[0]["to"], p[0]["data"], p[1]) for p in p4] == [
        (MOE, "0x313ce567", "0x1"), (WMON, "0x313ce567", "0x1"), (POOL, "0x0dfe1681", "0x1"),
        (POOL, "0xd21220a7", "0x1")]
    p5 = [call["body"]["params"] for call in providers.calls[16:]]
    assert p5[0] == ["finalized", False] and p5[1] == ["latest", False]
    assert [(p[0]["to"], p[1]) for p in p5[2:]] == [(MOE, "0x78"), (WMON, "0x78"), (MOE, "latest"),
                                                    (WMON, "latest")]
    handoff = handoff_of(result)
    assert handoff["accounting"]["admitted"] == {"quicknode": 17, "hypersync": 5}
    assert handoff["accounting"]["unknown_liability"] == 0
    assert oct(attempt.stat().st_mode & 0o777) == "0o700"
    assert {oct(path.stat().st_mode & 0o777) for path in attempt.rglob("*") if path.is_file()} == {"0o600"}


def test_handoff_freezes_literal_first_covering_receipts_counts_and_digests(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path)
    handoff = handoff_of(result)
    assert handoff["evidence_class"] == "SYNTHETIC"
    assert [(b["status"], b["received_at_utc"], b["record_count"], b["payload_sha256"]) for b in handoff["buckets"]] \
        == [("DELIVERED", "2027-01-15T08:05:31Z", 1, ORACLE_ABSENT_SHA),
            ("DELIVERED", "2027-01-15T08:10:31Z", 0, EMPTY_SHA),
            ("DELIVERED", "2027-01-15T08:15:31Z", 0, EMPTY_SHA),
            ("DELIVERED", "2027-01-15T08:20:31Z", 0, EMPTY_SHA)]
    assert handoff["buckets"][0]["received_at_utc_us"] == (T0 + 330) * 1_000_000 + 250_000
    assert handoff["delivery_records"] == {"2027-01-15T08:00:00Z": "2027-01-15T08:05:31Z",
                                           "2027-01-15T08:05:00Z": "2027-01-15T08:10:31Z",
                                           "2027-01-15T08:10:00Z": "2027-01-15T08:15:31Z",
                                           "2027-01-15T08:15:00Z": "2027-01-15T08:20:31Z"}
    assert handoff["boundaries"] == {"B_ANCHOR": 0, "B_PRE": 0, "B_START": 1, "B_END": 120, "B_POST": 121}
    assert handoff["scan"] == {"from_block": 0, "to_block_exclusive": 122}
    assert handoff["scan_log_count"] == 2  # the B_POST boundary log counts in the scan, not in any bucket
    assert "transaction_hash" not in json.dumps(handoff["buckets"])


# Coverage, cursor and second reads


def _lagging_first_reads(providers: SyntheticProviders, clock: FakeClock) -> None:
    providers.lag = 60.0  # at end+30 the head is behind the bucket end; at end+120 it covers


def test_valid_insufficient_first_reads_allow_one_second_read_each_up_to_9_hypersync(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path, configure=_lagging_first_reads)
    hypersync = [call["what"] for call in providers.calls if call["provider"] == "hypersync"]
    assert len(hypersync) == 9
    assert hypersync[1:3] == ["query:0", "query:29"]  # second read starts at the insufficient reply's cursor
    handoff = handoff_of(result)
    assert [b["received_at_utc"] for b in handoff["buckets"]] == [
        "2027-01-15T08:07:01Z", "2027-01-15T08:12:01Z", "2027-01-15T08:17:01Z", "2027-01-15T08:22:01Z"]
    assert handoff["buckets"][0]["record_count"] == 1
    assert handoff["buckets"][0]["payload_sha256"] == ORACLE_ABSENT_SHA


def test_never_covered_bucket_closes_incomplete_and_later_replies_do_not_backfill(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[9] = lambda call: HttpResponse(500, {}, b"{}")  # bucket-0 first read fails
    result, providers, _ = run(tmp_path, configure=configure)
    hypersync = [call["what"] for call in providers.calls if call["provider"] == "hypersync"]
    assert hypersync == ["query:900", "query:0", "query:0", "query:64", "query:94"]  # no second read, no retry
    handoff = handoff_of(result)
    first = handoff["buckets"][0]
    assert (first["status"], first["received_at_utc"], first["payload_sha256"], first["record_count"]) == \
        ("INCOMPLETE", None, None, None)
    assert first["reason"] == "FIRST_READ_FAILED"
    assert handoff["buckets"][1]["status"] == "DELIVERED"
    assert "2027-01-15T08:00:00Z" not in handoff["delivery_records"]


@pytest.mark.parametrize("damage", [
    lambda page: page["data"][0].pop("logs"),
    lambda page: page["data"][0]["blocks"].pop(3),
    lambda page: page.update(next_block=page["data"][0]["blocks"][0]["number"]),
    lambda page: page["data"][0]["blocks"][4].update(hash="0x" + "99" * 32) or page["data"][0]["logs"].append(
        dict(page["data"][0]["logs"][0])),
    lambda page: page["data"][0]["logs"][0].update(block_hash="0x" + "98" * 32),
    lambda page: page["data"][0]["logs"][0].pop("removed"),
    lambda page: page["data"][0]["logs"][0].update(removed=True),
    lambda page: page["data"][0]["logs"][0].update(topic3="0x" + "00" * 32),
    lambda page: page["data"][0]["logs"][0].update(address="0x" + "77" * 20),
    lambda page: page.update(data=page["data"][0]),
    lambda page: page["data"].append("not-an-object"),
    lambda page: page["data"][0].update(logs={}),
    lambda page: page["data"][0].update(blocks={}),
    lambda page: page.update(rollback_guard=[1]),
    lambda page: page["data"][0]["blocks"][5].update(timestamp=T0 + 2000),
], ids=["missing-logs", "missing-header", "empty-range", "duplicate-log", "log-hash-differs", "missing-removed",
        "removed-true", "fourth-topic", "foreign-pool", "object-shape", "batch-not-object", "logs-not-list",
        "blocks-not-list", "guard-not-object", "future-header"])
def test_malformed_first_page_gives_no_delivery_and_no_second_read(tmp_path: Path, damage: Callable) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def damaged(call: dict[str, Any]) -> HttpResponse:
            page = providers._query(call["body"])
            damage(page)
            return HttpResponse(200, {}, json.dumps(page).encode())
        providers.overrides[9] = damaged
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert handoff["buckets"][0]["status"] == "INCOMPLETE"
    assert handoff["buckets"][0]["reason"] == "FIRST_READ_REJECTED"
    assert count(providers, "hypersync") == 5


def test_conflicting_anchor_header_is_a_safety_stop(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def conflicting(call: dict[str, Any]) -> HttpResponse:
            page = providers._query(call["body"])
            page["data"][0]["blocks"][0]["hash"] = "0x" + "97" * 32
            return HttpResponse(200, {}, json.dumps(page).encode())
        providers.overrides[9] = conflicting
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "SAFETY_STOP"
    assert result["stop_reason"] == "CONFLICTING_BLOCK_FACT"
    assert len(providers.calls) == 9


def test_first_read_outstanding_at_the_second_event_expires_without_a_second_read(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def slow(call: dict[str, Any]) -> None:
            assert call["deadline"] - clock.mono == pytest.approx(90 - 0.25)  # first-read cutoff is end+120
            clock.advance(95)
            return None
        providers.overrides[9] = slow
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert handoff["buckets"][0]["reason"] == "FIRST_READ_FAILED"
    assert count(providers, "hypersync") == 5


def test_missed_admission_slot_is_recorded_without_catch_up(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        clock.sleep_hook = lambda target: 1.0 if target == T0 + 630 else 0.0  # wakes at due + 1 second
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert [call["what"] for call in providers.calls if call["provider"] == "hypersync"] == [
        "query:900", "query:0", "query:34", "query:94"]
    assert handoff["buckets"][1]["status"] == "INCOMPLETE"
    assert handoff["buckets"][1]["reason"] == "FIRST_SLOT_MISSED"


def test_admission_at_the_last_instant_of_the_slot_is_allowed(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        clock.sleep_hook = lambda target: 0.999 if target == T0 + 630 else 0.0
    result, providers, _ = run(tmp_path, configure=configure)
    assert count(providers, "hypersync") == 5


def test_clock_reversal_stops_scheduled_sends(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def reverse(call: dict[str, Any]) -> None:
            clock.now -= 30
            return None
        providers.overrides[10] = reverse
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "CLOCK_UNTRUSTED"
    assert len(providers.calls) == 10
    handoff = handoff_of(result)
    assert handoff["clock"]["trusted"] is False
    assert handoff["buckets"][1]["status"] == "INCOMPLETE"


# P2 anchor edges


def test_start_after_the_anchor_window_misses_p2_and_makes_no_p3_reads(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path, start=T0 - 10)
    assert "hypersync:query:0" not in sequence(providers)
    handoff = handoff_of(result)
    assert handoff["phases"]["P2"]["outcome"] == "MISSED"
    assert {b["reason"] for b in handoff["buckets"]} == {"NO_ANCHOR"}
    assert count(providers, "hypersync") == 1


def test_anchor_timestamp_at_or_after_t0_is_a_safety_stop(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.rpc["eth_getBlockByNumber"] = {"number": "0x1", "timestamp": hex(T0), "hash": block_hash(1)}
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["stop_reason"] == "ANCHOR_NOT_BEFORE_T0"
    assert len(providers.calls) == 8


# Failure classes


@pytest.mark.parametrize("status", [401, 402, 403, 429])
@pytest.mark.parametrize("call_number", [2, 9, 14, 18])
def test_auth_payment_and_rate_statuses_stop_every_provider(tmp_path: Path, status: int, call_number: int) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[call_number] = lambda call: HttpResponse(status, {}, b"{}")
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "SAFETY_STOP"
    assert len(providers.calls) == call_number


def test_quota_message_in_a_200_body_is_a_safety_stop(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[17] = lambda call: HttpResponse(200, {}, b'{"error":"monthly quota exceeded"}')
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["stop_reason"] == "QUOTA_OR_PAYMENT_SIGNAL"
    assert len(providers.calls) == 17


def test_failed_p3_and_p4_reads_stay_weak_without_retry_and_p5_still_runs(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def timeout(call: dict[str, Any]) -> None:
            raise SourceTimeout("synthetic timeout")
        providers.overrides[10] = timeout
        providers.overrides[13] = lambda call: HttpResponse(
            200, {}, json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000}}).encode())
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "COMPLETED"
    handoff = handoff_of(result)
    assert handoff["buckets"][1]["reason"] == "FIRST_READ_FAILED"
    assert handoff["facts"]["decimals"]["window_start"]["token1"] == "NOT_READ"
    assert len(providers.calls) == 22
    assert handoff["accounting"]["unknown_liability"] == 1


def test_p4_after_its_cutoff_sends_nothing_and_p5_still_runs(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        clock.sleep_hook = lambda target: 2400.0 if target == T0 + 1321 else 0.0
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "COMPLETED"
    handoff = handoff_of(result)
    assert handoff["facts"]["decimals"]["window_start"] == {"token1": "NOT_READ", "token0": "NOT_READ"}
    assert count(providers, "quicknode") == 6 + 1 + 0 + 6
    assert handoff["accounting"]["unknown_liability"] == 0


@pytest.mark.parametrize("change,where", [
    ({"eth_chainId": "0x279f"}, "chain"),
    ({"eth_getTransactionReceipt": dict(creation_receipt(), status="0x0")}, "receipt-status"),
    ({"eth_getTransactionReceipt": creation_receipt(topics=[CREATION_TOPIC0, "0x" + "01" + _addr_word(WMON)[2:],
                                                            "0x" + _addr_word(MOE)])}, "padding"),
    ({"eth_getTransactionReceipt": creation_receipt(topics=[CREATION_TOPIC0, "0x" + _addr_word(MOE),
                                                            "0x" + _addr_word(WMON)])}, "token-order"),
    ({"eth_getTransactionReceipt": creation_receipt(data="0x" + _addr_word(POOL))}, "word-length"),
    ({"eth_getTransactionReceipt": creation_receipt(topics=[CREATION_TOPIC0, "0x" + _addr_word(WMON),
                                                            "0x" + _addr_word(MOE), ZERO_WORD])}, "topic-count"),
    ({"eth_getTransactionReceipt": dict(creation_receipt(), logs=creation_receipt()["logs"] * 2)}, "ambiguous"),
    ({"eth_getTransactionReceipt": creation_receipt(logIndex="0x7")}, "log-index"),
    ({"eth_call": "0x" + _addr_word("0x" + "56" * 20)}, "factory"),
])
def test_p1_contradictions_stop_all_providers(tmp_path: Path, change: dict[str, Any], where: str) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.rpc.update(change)
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "SAFETY_STOP"
    assert result["stop_reason"].startswith("P1_")
    assert "quicknode:eth_getBlockByNumber" not in sequence(providers)


@pytest.mark.parametrize("log_change", [{"transaction_index": 3}, {"topic2": "0x" + _addr_word(WMON)},
                                        {"data": "0x" + _addr_word(POOL) + _word(1)}, {"topic3": ZERO_WORD},
                                        {"removed": True}])
def test_p1_hypersync_identity_must_equal_the_receipt(tmp_path: Path, log_change: dict[str, Any]) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[3] = lambda call: HttpResponse(200, {}, json.dumps(creation_page(**log_change)).encode())
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["stop_reason"].startswith("P1_")
    assert len(providers.calls) == 3


def test_p1_hypersync_null_topic3_is_accepted(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[3] = lambda call: HttpResponse(200, {}, json.dumps(creation_page(topic3=None)).encode())
    result, _, _ = run(tmp_path, configure=configure)
    assert result["status"] == "COMPLETED"


REAL_REPLY = (Path(__file__).parents[1] / "apps" / "api" / "tests" / "fixtures" / "research_history_native"
              / "real_hypersync_p1_reply_20261021.json")


def test_hypersync_batches_flattens_the_real_reply_data_list() -> None:
    raw = json.loads(REAL_REPLY.read_bytes())
    blocks, logs = hypersync_batches(raw)
    assert [block["number"] for block in blocks] == [107_504_955]
    assert [log["log_index"] for log in logs] == [6]


def test_hypersync_batches_keeps_reply_order_across_batches() -> None:
    raw = json.loads(REAL_REPLY.read_bytes())
    first = raw["data"][0]
    second = {"blocks": [dict(first["blocks"][0], number=107_504_956)], "logs": []}
    raw["data"] = [first, second]
    blocks, logs = hypersync_batches(raw)
    assert [block["number"] for block in blocks] == [107_504_955, 107_504_956]
    assert [log["log_index"] for log in logs] == [6]


def test_hypersync_batches_allows_a_batch_without_blocks_but_refuses_another_shape() -> None:
    raw = json.loads(REAL_REPLY.read_bytes())
    raw["data"] = [{"logs": []}]
    assert hypersync_batches(raw) == ([], [])


@pytest.mark.parametrize("damage", [
    lambda raw: raw.update(data=raw["data"][0]),
    lambda raw: raw.update(data=["not-an-object"]),
    lambda raw: raw["data"][0].pop("logs"),
    lambda raw: raw["data"][0].update(logs={}),
    lambda raw: raw["data"][0].update(blocks={}),
], ids=["data-object", "batch-text", "logs-absent", "logs-not-list", "blocks-not-list"])
def test_hypersync_batches_refuses_every_other_shape(damage: Callable) -> None:
    raw = json.loads(REAL_REPLY.read_bytes())
    damage(raw)
    assert hypersync_batches(raw) is None


def test_bytecode_identity_hashes_decoded_bytes_and_empty_code_has_none(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[7] = lambda call: HttpResponse(200, {}, _rpc("0x"))
    result, _, _ = run(tmp_path, configure=configure)
    code = handoff_of(result)["facts"]["bytecode"]
    assert code["pool"] == {"sha256": hashlib.sha256(bytes.fromhex("6080604052")).hexdigest(), "bytes": 5}
    assert code["token1"] is None


def test_wrong_returned_decimals_is_a_safety_stop(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[13] = lambda call: HttpResponse(200, {}, _rpc("0x" + _word(9)))
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["stop_reason"] == "DECIMALS_DIFFER"
    assert len(providers.calls) == 13


def test_weak_finality_is_recorded_once_without_a_repeat(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.rpc["eth_getBlockByNumber"] = lambda params: (
            {"number": hex(100), "timestamp": hex(block_ts(100)), "hash": block_hash(100)}
            if params[0] == "finalized" else
            {"number": hex(head_at(clock.now, 1.0)), "timestamp": hex(block_ts(head_at(clock.now, 1.0))),
             "hash": block_hash(head_at(clock.now, 1.0))})
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert handoff["facts"]["finality_at_collection"] == "NOT_OBSERVED"
    assert sum(1 for c in providers.calls if (c["body"].get("params") or [None])[0] == "finalized") == 1


def test_missing_b_end_skips_only_dependent_end_reads(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.lag = 10_000.0  # HyperSync never moves past the anchor
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert handoff["boundaries"]["B_END"] is None
    assert handoff["scan"] is None
    assert count(providers, "quicknode") == 6 + 1 + 4 + 4
    assert handoff["facts"]["decimals"]["window_end"] == {"token0": "SKIPPED_NO_B_END", "token1": "SKIPPED_NO_B_END"}


# Preflight, credentials and destinations


@pytest.mark.parametrize("change", [
    {"predecessor_sha256": "00" * 32}, {"t0_utc": "2027-01-15T08:01:00Z"}, {"window_seconds": 1500},
    {"bucket_seconds": 60}, {"chain_id": 10143}, {"swap_topic0": "0x" + "00" * 32},
    {"selectors": {"decimals": "0x313ce568", "token0": "0x0dfe1681", "token1": "0xd21220a7", "factory": "0xc45a0155"}},
    {"pool": "0x" + "22" * 19}, {"attempt_id": "../escape"}, {"unexpected": 1}, {"evidence_class": "MAYBE"},
    {"destinations": {"quicknode_host": QN_HOST, "hypersync_url": "http://hypersync.example.invalid/query"}},
    {"output_dir": "relative/path"},
])
def test_invalid_input_is_refused_before_credentials_or_transport(tmp_path: Path, change: dict[str, Any]) -> None:
    credentials = Credentials()
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    with pytest.raises(RecorderInputError):
        run_attempt(recorder_input(tmp_path, **change), transport=providers, clock=clock, credentials=credentials)
    assert credentials.reads == [] and providers.calls == []


def test_unsupported_creation_layout_is_refused_before_credentials(tmp_path: Path) -> None:
    value = recorder_input(tmp_path)
    value["creation"] = dict(value["creation"], decoder="guessed-fork/1")
    credentials = Credentials()
    with pytest.raises(RecorderInputError):
        run_attempt(value, transport=SyntheticProviders(FakeClock(T0)), clock=FakeClock(T0), credentials=credentials)
    assert credentials.reads == []


@pytest.mark.parametrize("missing", ["D1", "D3", "plans", "p6"])
def test_missing_prerequisite_is_not_ready_with_zero_calls(tmp_path: Path, missing: str) -> None:
    value = recorder_input(tmp_path)
    if missing.startswith("D"):
        value["decisions"] = dict(value["decisions"], **{missing: None})
    elif missing == "plans":
        value["plans"] = dict(value["plans"], hypersync=None)
    else:
        value["p6"] = dict(value["p6"], destination_ref=None)
    credentials = Credentials()
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    result = run_attempt(value, transport=providers, clock=clock, credentials=credentials)
    assert result["status"] == "NOT_READY"
    assert credentials.reads == [] and providers.calls == []


def test_p6_mechanics_stays_external_evidence_required(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path)
    handoff = handoff_of(result)
    assert handoff["facts"]["fee_transfer_semantics"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert not any("source" in call["url"] for call in providers.calls)


def test_destination_mismatch_is_refused_before_any_request(tmp_path: Path) -> None:
    result, providers, attempt = run(tmp_path, credentials=Credentials(f"https://other.invalid/{QN_PATH_SECRET}/"))
    assert result["status"] == "DESTINATION_MISMATCH"
    assert providers.calls == []
    assert QN_PATH_SECRET.encode() not in all_bytes(attempt)


def test_default_cli_prints_a_redacted_plan_and_sends_nothing(tmp_path: Path,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.json"
    path.write_text(json.dumps(recorder_input(tmp_path)))
    assert main(["plan", "--input", str(path)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["calls_max"] == {"quicknode": 17, "hypersync": 9, "total": 26}
    assert plan["p3_admission_slots_utc"][0] == {"bucket": 0, "first": "2027-01-15T08:05:30Z",
                                                 "second": "2027-01-15T08:07:00Z"}
    assert plan["sends"] == 0
    assert list((tmp_path / "attempts").iterdir()) == []


# Bounds and admission ceilings


def _p1_wrapper(tmp_path: Path) -> Any:
    from scripts.forward_history_recorder import AttemptJournal, RecordingTransport
    clock = FakeClock(T0)
    inner = SyntheticProviders(clock)
    attempt = tmp_path / "attempt"
    journal = AttemptJournal.create(attempt)
    wrapper = RecordingTransport(inner, journal, clock, quicknode_url=QN_URL, hypersync_url=HS_URL,
                                 secrets=SECRETS)
    return wrapper, inner, journal, clock


def _send(wrapper: Any, clock: FakeClock, body: bytes, *, phase: str = "P1", provider: str = "quicknode",
          max_response_bytes: int = 2_097_152) -> HttpResponse:
    wrapper.label(phase=phase, slot="test", provider=provider)
    clock.advance(1.0)
    return wrapper.request(method="POST", url=QN_URL if provider == "quicknode" else HS_URL, headers={},
                           body=body, timeout=15.0, deadline=clock.mono + 60, max_response_bytes=max_response_bytes)


RPC_CHAIN = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode()


def test_excess_phase_call_is_refused_before_sending(tmp_path: Path) -> None:
    wrapper, inner, journal, clock = _p1_wrapper(tmp_path)
    for _ in range(6):
        _send(wrapper, clock, RPC_CHAIN)
    with pytest.raises(AdmissionRefused):
        _send(wrapper, clock, RPC_CHAIN)
    assert len(inner.calls) == 6
    assert journal.admitted("quicknode") == 6


def test_request_at_and_over_64_kib(tmp_path: Path) -> None:
    wrapper, inner, _, clock = _p1_wrapper(tmp_path)
    padding = 65_536 - len(RPC_CHAIN)
    exact = RPC_CHAIN[:-1] + b" " * padding + b"}"
    assert len(exact) == 65_536
    _send(wrapper, clock, exact)
    with pytest.raises(AdmissionRefused):
        _send(wrapper, clock, exact + b" ")
    assert len(inner.calls) == 1


def test_injected_reply_over_2_mib_is_refused_and_not_retained(tmp_path: Path) -> None:
    wrapper, inner, journal, clock = _p1_wrapper(tmp_path)
    inner.overrides[1] = lambda call: HttpResponse(200, {}, b"x" * 2_097_152)
    inner.overrides[2] = lambda call: HttpResponse(200, {}, b"y" * 2_097_153)
    _send(wrapper, clock, RPC_CHAIN)
    with pytest.raises(Exception) as caught:
        _send(wrapper, clock, RPC_CHAIN)
    assert getattr(caught.value, "code", None) == "OVERSIZED_RESPONSE"
    assert b"y" * 1000 not in all_bytes(tmp_path / "attempt")
    assert inner.calls[0]["max_response_bytes"] == 2_097_152


def test_aggregate_reply_budget_refuses_admission_that_cannot_fit(tmp_path: Path) -> None:
    wrapper, inner, journal, clock = _p1_wrapper(tmp_path)
    journal.reply_bytes = 67_108_864 - 2_097_151
    with pytest.raises(AdmissionRefused):
        _send(wrapper, clock, RPC_CHAIN)
    assert inner.calls == []


def test_unlisted_destination_is_refused(tmp_path: Path) -> None:
    wrapper, inner, _, clock = _p1_wrapper(tmp_path)
    wrapper.label(phase="P1", slot="x", provider="quicknode")
    with pytest.raises(AdmissionRefused):
        wrapper.request(method="POST", url="https://elsewhere.invalid/", headers={}, body=RPC_CHAIN, timeout=1.0,
                        deadline=clock.mono + 10, max_response_bytes=10)
    assert inner.calls == []


def test_expired_deadline_is_refused_before_admission(tmp_path: Path) -> None:
    wrapper, inner, journal, clock = _p1_wrapper(tmp_path)
    wrapper.label(phase="P1", slot="x", provider="quicknode")
    with pytest.raises(AdmissionRefused):
        wrapper.request(method="POST", url=QN_URL, headers={}, body=RPC_CHAIN, timeout=1.0, deadline=clock.mono,
                        max_response_bytes=10)
    assert inner.calls == [] and journal.admitted("quicknode") == 0


# Durable admission, interruption and files


def test_admission_is_durable_before_the_transport_starts(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.journal_path = tmp_path / "attempts" / "synthetic-attempt-1" / "journal.jsonl"
    _, providers, _ = run(tmp_path, configure=configure)
    assert providers.journal_seen and all(providers.journal_seen)


class Crash(BaseException):
    pass


def test_interrupt_after_send_keeps_unknown_liability_and_refuses_reexecution(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def crash(call: dict[str, Any]) -> None:
            raise Crash()
        providers.overrides[10] = crash
    with pytest.raises(Crash):
        run(tmp_path, configure=configure)
    attempt = tmp_path / "attempts" / "synthetic-attempt-1"
    summary = recover_attempt(attempt)
    assert summary["admitted"] == 10 and summary["resolved"] == 9 and summary["unknown_liability"] == 1
    assert summary["t0_utc"] == "2027-01-15T08:00:00Z"
    assert summary["handoff_present"] is False
    clock = FakeClock(T0 + 700)
    providers = SyntheticProviders(clock)
    credentials = Credentials()
    with pytest.raises(AttemptExists):
        run_attempt(recorder_input(tmp_path), transport=providers, clock=clock, credentials=credentials)
    assert providers.calls == [] and credentials.reads == []
    assert recover_attempt(attempt) == summary


def test_interrupt_before_first_send_leaves_t0_and_zero_liability(tmp_path: Path) -> None:
    class Boom(BaseException):
        pass

    def credentials(slot: str) -> str:
        raise Boom()
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    with pytest.raises(Boom):
        run_attempt(recorder_input(tmp_path), transport=providers, clock=clock, credentials=credentials)
    summary = recover_attempt(tmp_path / "attempts" / "synthetic-attempt-1")
    assert summary["admitted"] == 0 and summary["t0_utc"] == "2027-01-15T08:00:00Z"


def test_body_write_failure_stops_further_sends(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def lock(call: dict[str, Any]) -> None:
            os.chmod(tmp_path / "attempts" / "synthetic-attempt-1" / "bodies", 0o500)
            return None
        providers.overrides[4] = lock
    try:
        result, providers, _ = run(tmp_path, configure=configure)
    finally:
        os.chmod(tmp_path / "attempts" / "synthetic-attempt-1" / "bodies", 0o700)
    assert result["status"] == "EVIDENCE_WRITE_FAILED"
    assert len(providers.calls) == 4
    summary = recover_attempt(tmp_path / "attempts" / "synthetic-attempt-1")
    assert summary["unknown_liability"] == 1


def test_symlinked_output_directory_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real)
    value = recorder_input(tmp_path, output_dir=str(link))
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    with pytest.raises(RecorderInputError):
        run_attempt(value, transport=providers, clock=clock, credentials=Credentials())
    assert list(real.iterdir()) == [] and providers.calls == []


# Credential echo redaction


@pytest.mark.parametrize("where", ["body", "header", "exception", "hs-token-body"])
def test_credential_echo_is_an_incident_that_stops_calls_and_is_never_persisted(
        tmp_path: Path, where: str, capsys: pytest.CaptureFixture[str]) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def echo(call: dict[str, Any]) -> HttpResponse:
            if where == "body":
                return HttpResponse(200, {}, _rpc(f"see {QN_URL}"))
            if where == "header":
                return HttpResponse(200, {"x-debug": f"path /{QN_PATH_SECRET}/"}, _rpc("0x8f"))
            if where == "hs-token-body":
                return HttpResponse(200, {}, json.dumps({"error": f"bad token {HS_TOKEN}"}).encode())
            raise OSError(f"connect failed for {QN_URL}")
        providers.overrides[3 if where == "hs-token-body" else 2] = echo
    result, providers, attempt = run(tmp_path, configure=configure)
    assert result["status"] == "SAFETY_STOP"
    assert result["stop_reason"] == "CREDENTIAL_INCIDENT"
    assert len(providers.calls) == (3 if where == "hs-token-body" else 2)
    stored = all_bytes(attempt)
    printed = capsys.readouterr()
    for secret in SECRETS:
        assert secret.encode() not in stored
        assert secret not in printed.out + printed.err
        assert secret not in json.dumps(result)
    assert b"CREDENTIAL_INCIDENT" in stored


def test_credentials_are_not_read_before_preflight_and_only_once_each(tmp_path: Path) -> None:
    credentials = Credentials()
    run(tmp_path, credentials=credentials)
    assert credentials.reads == ["quicknode_monad_url", "envio_hypersync_bearer"]


def test_hypersync_request_carries_the_literal_forward_query_without_an_end_block(tmp_path: Path) -> None:
    _, providers, _ = run(tmp_path)
    p3 = providers.calls[8]["body"]
    assert p3 == {"from_block": 0, "logs": [{"address": [POOL], "topics": [[SWAP_TOPIC0]]}],
                  "include_all_blocks": True, "max_num_blocks": 10000,
                  "field_selection": {"block": ["number", "timestamp", "hash"],
                                      "log": ["address", "topic0", "topic1", "topic2", "topic3", "data",
                                              "block_number", "block_hash", "transaction_hash",
                                              "transaction_index", "log_index", "removed"]}}
    assert providers.calls[8]["headers"]["authorization"] == f"Bearer {HS_TOKEN}"
    assert providers.calls[2]["body"]["to_block"] == 901
    assert providers.calls[8]["timeout"] <= 15


def test_pacing_keeps_one_second_between_same_provider_admissions(tmp_path: Path) -> None:
    run(tmp_path, latency=0.0)
    admissions = recover_attempt(tmp_path / "attempts" / "synthetic-attempt-1")["admission_monotonic"]
    assert (len(admissions["quicknode"]), len(admissions["hypersync"])) == (17, 5)
    for provider in ("quicknode", "hypersync"):
        series = admissions[provider]
        assert all(later - earlier >= 1.0 for earlier, later in zip(series, series[1:]))


def test_input_validation_accepts_the_complete_synthetic_input(tmp_path: Path) -> None:
    value = validate_input(copy.deepcopy(recorder_input(tmp_path)))
    assert value["t0"] == T0 and value["window_end"] == WE


# SOURCE2 matrix completion


def test_cancellation_stops_every_later_admission(tmp_path: Path) -> None:
    flag = {"cancelled": False}

    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def cancel_during(call: dict[str, Any]) -> None:
            flag["cancelled"] = True
            return None
        providers.overrides[9] = cancel_during
    clock = FakeClock(T0 - 600)
    providers = SyntheticProviders(clock)
    configure(providers, clock)
    result = run_attempt(recorder_input(tmp_path), transport=providers, clock=clock, credentials=Credentials(),
                         cancel=lambda: flag["cancelled"])
    assert result["status"] == "CANCELLED"
    assert len(providers.calls) == 9
    summary = recover_attempt(tmp_path / "attempts" / "synthetic-attempt-1")
    assert summary["admitted"] == 9
    handoff = handoff_of(result)
    assert handoff["buckets"][0]["status"] == "INCOMPLETE"


def _page_override(index: int, damage: Callable[[dict[str, Any]], None]) -> Callable:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def damaged(call: dict[str, Any]) -> HttpResponse:
            page = providers._query(call["body"])
            damage(page)
            return HttpResponse(200, {}, json.dumps(page).encode())
        providers.overrides[index] = damaged
    return configure


def test_rollback_guard_hash_conflict_is_a_safety_stop(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path, configure=_page_override(
        9, lambda page: page.update(rollback_guard={"block_number": 5, "hash": "0x" + "96" * 32})))
    assert (result["status"], result["stop_reason"]) == ("SAFETY_STOP", "CONFLICTING_BLOCK_FACT")
    assert len(providers.calls) == 9


def test_consistent_rollback_guard_is_accepted(tmp_path: Path) -> None:
    # GATE1 correction: a guard names the page-end block (source_transport._frame), not an interior block.
    def guard(page: dict[str, Any]) -> None:
        end = page["data"][0]["blocks"][-1]
        page["rollback_guard"] = {"block_number": end["number"], "timestamp": end["timestamp"], "hash": end["hash"],
                                  "first_block_number": page["data"][0]["blocks"][0]["number"]}
    result, providers, _ = run(tmp_path, configure=_page_override(9, guard))
    assert result["status"] == "COMPLETED"
    assert handoff_of(result)["buckets"][0]["status"] == "DELIVERED"


def test_later_reply_contradicting_an_earlier_reply_header_is_a_safety_stop(tmp_path: Path) -> None:
    def damage(page: dict[str, Any]) -> None:
        page["data"][0]["blocks"].insert(0, {"number": 33, "timestamp": block_ts(33), "hash": "0x" + "95" * 32})
    result, providers, _ = run(tmp_path, configure=_page_override(10, damage))
    assert (result["status"], result["stop_reason"]) == ("SAFETY_STOP", "CONFLICTING_BLOCK_FACT")
    assert len(providers.calls) == 10
    assert handoff_of(result)["buckets"][0]["status"] == "DELIVERED"


def test_later_reply_repeating_an_identical_earlier_header_is_rejected_not_stopped(tmp_path: Path) -> None:
    def damage(page: dict[str, Any]) -> None:
        page["data"][0]["blocks"].insert(0, {"number": 33, "timestamp": block_ts(33), "hash": block_hash(33)})
    result, providers, _ = run(tmp_path, configure=_page_override(10, damage))
    assert result["status"] == "COMPLETED"
    assert handoff_of(result)["buckets"][1]["reason"] == "FIRST_READ_REJECTED"


@pytest.mark.parametrize("extra,flagged", [(59, False), (60, True)])
def test_more_than_61_scan_logs_is_weaker_evidence_and_later_phases_still_run(
        tmp_path: Path, extra: int, flagged: bool) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.swaps = [ORACLE_SWAP, BOUNDARY_SWAP] + [
            dict(ORACLE_SWAP, block_number=2 + index, transaction_hash="0x" + "%064x" % (index + 1))
            for index in range(extra)]
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert handoff["scan_log_count"] == extra + 2
    assert handoff["weaker_evidence"] == (["SCAN_LOG_COUNT_EXCEEDS_61"] if flagged else [])
    assert result["status"] == "COMPLETED"
    assert (count(providers, "quicknode"), count(providers, "hypersync")) == (17, 5)


@pytest.mark.parametrize("call_number,returned", [(15, MOE), (16, WMON)])
def test_wrong_pool_token_order_at_b_start_is_a_safety_stop(tmp_path: Path, call_number: int,
                                                              returned: str) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[call_number] = lambda call: HttpResponse(200, {}, _rpc("0x" + _addr_word(returned)))
    result, providers, _ = run(tmp_path, configure=configure)
    assert (result["status"], result["stop_reason"]) == ("SAFETY_STOP", "TOKEN_ORDER_DIFFERS")
    assert len(providers.calls) == call_number


@pytest.mark.parametrize("reply,outcome", [
    (lambda clock: HttpResponse(500, {}, b"{}"), "FAILED:HTTP_STATUS"),
    (lambda clock: HttpResponse(200, {}, _rpc({"number": "0x0", "timestamp": hex(T0 - 200)})),
     "FAILED:MALFORMED_HEADER"),
    (lambda clock: HttpResponse(200, {}, b"not json"), "FAILED:MALFORMED_PROVIDER_RESPONSE"),
    (lambda clock: clock.advance(120) or HttpResponse(200, {}, _rpc(
        {"number": "0x0", "timestamp": hex(T0 - 200), "hash": block_hash(0)})), "FAILED:SourceTimeout"),
], ids=["status", "missing-hash", "not-json", "after-cutoff"])
def test_failed_or_malformed_anchor_gives_no_p3_scan_and_p5_still_runs(tmp_path: Path, reply: Callable,
                                                                       outcome: str) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[8] = lambda call: reply(clock)
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert result["status"] == "COMPLETED"
    assert handoff["phases"]["P2"]["outcome"] == outcome
    assert count(providers, "hypersync") == 1
    assert {bucket["reason"] for bucket in handoff["buckets"]} == {"NO_ANCHOR"}
    assert handoff["phases"]["P4"]["outcome"] == "SKIPPED_NO_B_START"
    assert count(providers, "quicknode") == 6 + 1 + 0 + 4


@pytest.mark.parametrize("number,final,declarable", [(122, "NOT_OBSERVED", False), (123, "OBSERVED_FINAL", True)])
def test_p5_heads_below_b_post_plus_2_keep_finality_and_archive_height_weak(
        tmp_path: Path, number: int, final: str, declarable: bool) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def header(params: list[Any]) -> dict[str, Any]:
            chosen = number if clock.now > WE else head_at(clock.now, 1.0)
            return {"number": hex(chosen), "timestamp": hex(block_ts(chosen)), "hash": block_hash(chosen)}
        providers.rpc["eth_getBlockByNumber"] = header
    result, providers, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    assert handoff["boundaries"]["B_POST"] == 121
    assert handoff["facts"]["finality_at_collection"] == final
    assert handoff["facts"]["archive_height_declarable"] is declarable
    assert handoff["facts"]["finalized"]["number"] == number and handoff["facts"]["latest"]["number"] == number
    assert count(providers, "quicknode") == 17


def test_recover_cli_reports_a_saved_attempt_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def crash(call: dict[str, Any]) -> None:
            raise Crash()
        providers.overrides[10] = crash
    with pytest.raises(Crash):
        run(tmp_path, configure=configure)
    attempt = tmp_path / "attempts" / "synthetic-attempt-1"
    before = {path: path.read_bytes() for path in attempt.rglob("*") if path.is_file()}
    capsys.readouterr()
    assert main(["recover", "--attempt-dir", str(attempt)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert (printed["admitted"], printed["resolved"], printed["unknown_liability"]) == (10, 9, 1)
    assert printed["handoff_present"] is False and printed["t0_utc"] == "2027-01-15T08:00:00Z"
    assert {path: path.read_bytes() for path in attempt.rglob("*") if path.is_file()} == before
    assert main(["recover", "--attempt-dir", str(tmp_path / "absent")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"


def test_actual_request_through_an_injected_transport_stays_synthetic_with_a_notice(tmp_path: Path) -> None:
    # REPAIR2 correction of the SOURCE2 row-9 test: a caller's ACTUAL string cannot promote an injected transport.
    result, providers, attempt = run(tmp_path, evidence_class="ACTUAL")
    handoff = handoff_of(result)
    assert handoff["evidence_class"] == "SYNTHETIC"
    assert handoff["requested_evidence_class"] == "ACTUAL"
    assert "ACTUAL_NOT_ESTABLISHED" in handoff["evidence_notice"]
    assert "SYNTHETIC" in handoff["claim_limit"]
    assert handoff["release_frozen"] is False
    assert handoff["accounting"]["admitted"] == {"quicknode": 17, "hypersync": 5}
    assert len(list((attempt / "bodies").iterdir())) == 22
    assert {oct(path.stat().st_mode & 0o777) for path in attempt.rglob("*") if path.is_file()} == {"0o600"}
    for secret in SECRETS:
        assert secret.encode() not in all_bytes(attempt)


# REPAIR2: malformed provider values and body hashes


def test_null_creation_transaction_hash_is_a_p1_stop_with_one_handoff(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.rpc["eth_getTransactionReceipt"] = dict(creation_receipt(), transactionHash=None)
    result, providers, attempt = run(tmp_path, configure=configure)
    assert result["status"] == "SAFETY_STOP" and result["stop_reason"].startswith("P1_")
    assert len(providers.calls) == 2
    assert recover_attempt(attempt)["handoff_present"] is True


def test_5000_digit_page_quantity_rejects_the_page_and_later_phases_run(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path, configure=_page_override(9, lambda page: page.update(
        archive_height="9" * 5000)))
    handoff = handoff_of(result)
    assert result["status"] == "COMPLETED"
    assert handoff["buckets"][0]["reason"] == "FIRST_READ_REJECTED"
    assert len(providers.calls) == 22


def test_5000_digit_p2_quantity_is_a_weak_malformed_anchor(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[8] = lambda call: HttpResponse(200, {}, _rpc(
            {"number": "9" * 5000, "timestamp": hex(T0 - 200), "hash": block_hash(0)}))
    result, _, _ = run(tmp_path, configure=configure)
    assert result["status"] == "COMPLETED"
    assert handoff_of(result)["phases"]["P2"]["outcome"] == "FAILED:MALFORMED_HEADER"


def test_handoff_binds_literal_request_and_reply_body_hashes_per_call(tmp_path: Path) -> None:
    result, providers, attempt = run(tmp_path)
    handoff = handoff_of(result)
    first = handoff["calls"][0]
    assert (first["provider"], first["phase"], first["outcome"], first["status"]) == (
        "quicknode", "P1", "REPLY_RECEIVED", 200)
    assert (first["request_bytes"], first["request_sha256"]) == (
        59, "09fabe0af56b7726f1666ddd147482df4d951f86f66124b936716c53ab0e8471")
    assert (first["body_bytes"], first["body_sha256"]) == (
        45, "297e3000506f347fcae580843cdf2272e5f7c69bcbcc0498cda4a774038ec821")
    assert len(handoff["calls"]) == 22
    by_id = {call["call_id"]: call for call in handoff["calls"]}
    for bucket in handoff["buckets"]:
        reply = by_id[bucket["reply_id"]]
        assert bucket["reply_body_sha256"] == reply["body_sha256"]
        stored = (attempt / "bodies" / f"{bucket['reply_id']}.bin").read_bytes()
        assert hashlib.sha256(stored).hexdigest() == reply["body_sha256"]


def test_incident_call_keeps_no_body_hash_in_the_handoff(tmp_path: Path) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[2] = lambda call: HttpResponse(200, {}, _rpc(f"see {QN_URL}"))
    result, _, _ = run(tmp_path, configure=configure)
    handoff = handoff_of(result)
    incident = handoff["calls"][1]
    assert incident["outcome"] == "CREDENTIAL_INCIDENT"
    assert incident["body_sha256"] is None and incident["body_bytes"] is None


# GATE1 repair: G1 admission slot, G3 rollback guard, G4 request limit, G5 torn journal


class SlowReadClock(FakeClock):
    """Each UTC read inside one admission slot costs `step` seconds of elapsed work (authored clock injection)."""

    def __init__(self, utc: float, slot_start: float, step: float) -> None:
        super().__init__(utc)
        self.slot_start, self.step = slot_start, step

    def utc(self) -> float:
        value = self.now
        if self.slot_start <= value < self.slot_start + 1:
            self.advance(self.step)
        return value


def _run_with_clock(tmp_path: Path, clock: FakeClock, lag: float = 1.0) -> tuple[dict, SyntheticProviders]:
    providers = SyntheticProviders(clock, lag=lag)
    result = run_attempt(recorder_input(tmp_path), transport=providers, clock=clock, credentials=Credentials())
    return result, providers


def test_first_slot_admission_after_the_slot_closes_is_missed_with_no_send(tmp_path: Path) -> None:
    result, providers = _run_with_clock(tmp_path, SlowReadClock(T0 - 600, T0 + 330, 0.3))
    handoff = handoff_of(result)
    assert [call["what"] for call in providers.calls if call["provider"] == "hypersync"] == [
        "query:900", "query:0", "query:64", "query:94"]
    assert handoff["buckets"][0]["reason"] == "FIRST_SLOT_MISSED"
    assert handoff["accounting"]["admitted"]["hypersync"] == 4
    assert handoff["accounting"]["unknown_liability"] == 0
    assert result["status"] == "COMPLETED"


def test_second_slot_admission_after_the_slot_closes_is_missed_with_no_send(tmp_path: Path) -> None:
    result, providers = _run_with_clock(tmp_path, SlowReadClock(T0 - 600, T0 + 420, 0.3), lag=60.0)
    handoff = handoff_of(result)
    hypersync = [call["what"] for call in providers.calls if call["provider"] == "hypersync"]
    assert hypersync[:3] == ["query:900", "query:0", "query:29"] and len(hypersync) == 8
    assert handoff["buckets"][0]["reason"] == "SECOND_SLOT_MISSED"
    assert handoff["accounting"]["unknown_liability"] == 0


def test_admission_exactly_at_slot_close_is_refused(tmp_path: Path) -> None:
    result, providers = _run_with_clock(tmp_path, SlowReadClock(T0 - 600, T0 + 330, 0.25))
    assert handoff_of(result)["buckets"][0]["reason"] == "FIRST_SLOT_MISSED"
    assert "hypersync:query:0" in sequence(providers)  # the bucket-1 read still runs from the same cursor


def _guard_page(**changes: Any) -> Callable[[dict[str, Any]], None]:
    def damage(page: dict[str, Any]) -> None:
        end = page["data"][0]["blocks"][-1]
        guard = {"block_number": end["number"], "timestamp": end["timestamp"], "hash": end["hash"],
                 "first_block_number": page["data"][0]["blocks"][0]["number"]}
        guard.update({key: (value(end) if callable(value) else value) for key, value in changes.items()})
        page["rollback_guard"] = guard
    return damage


@pytest.mark.parametrize("changes", [
    {"timestamp": lambda end: end["timestamp"] + 1}, {"block_number": lambda end: end["number"] - 1},
    {"first_block_number": 1}, {"hash": "0x" + "94" * 32},
], ids=["timestamp", "last-block", "first-block", "hash"])
def test_contradictory_rollback_guard_fact_is_a_safety_stop(tmp_path: Path, changes: dict[str, Any]) -> None:
    result, providers, _ = run(tmp_path, configure=_page_override(9, _guard_page(**changes)))
    assert (result["status"], result["stop_reason"]) == ("SAFETY_STOP", "CONFLICTING_BLOCK_FACT")
    assert len(providers.calls) == 9
    assert handoff_of(result)["buckets"][0]["status"] == "INCOMPLETE"


@pytest.mark.parametrize("changes", [{"timestamp": "soon"}, {"block_number": True}, {"hash": "0x12"},
                                     {"first_parent_hash": 7}], ids=["timestamp", "number", "hash", "parent"])
def test_malformed_rollback_guard_fact_rejects_the_page(tmp_path: Path, changes: dict[str, Any]) -> None:
    result, _, _ = run(tmp_path, configure=_page_override(9, _guard_page(**changes)))
    assert result["status"] == "COMPLETED"
    assert handoff_of(result)["buckets"][0]["reason"] == "FIRST_READ_REJECTED"


def test_guard_parent_hash_contradicting_the_previous_page_is_a_safety_stop(tmp_path: Path) -> None:
    result, providers, _ = run(tmp_path, configure=_page_override(10, _guard_page(first_parent_hash="0x" + "93" * 32)))
    assert (result["status"], result["stop_reason"]) == ("SAFETY_STOP", "CONFLICTING_BLOCK_FACT")
    assert len(providers.calls) == 10


REQUEST_LIMIT = json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32005,
                                                                 "message": "request limit exceeded"}}).encode()


@pytest.mark.parametrize("call_number", [2, 9, 13, 17], ids=["P1", "P3", "P4", "P5"])
def test_request_limit_message_at_http_200_stops_every_provider(tmp_path: Path, call_number: int) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[call_number] = lambda call: HttpResponse(200, {}, REQUEST_LIMIT)
    result, providers, _ = run(tmp_path, configure=configure)
    assert (result["status"], result["stop_reason"]) == ("SAFETY_STOP", "QUOTA_OR_PAYMENT_SIGNAL")
    assert len(providers.calls) == call_number


@pytest.mark.parametrize("message", ["execution reverted", "gas limit exceeded"])
def test_unrelated_rpc_error_stays_weak(tmp_path: Path, message: str) -> None:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        providers.overrides[13] = lambda call: HttpResponse(200, {}, json.dumps(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": message}}).encode())
    result, providers, _ = run(tmp_path, configure=configure)
    assert result["status"] == "COMPLETED" and len(providers.calls) == 22


def _crashed_attempt(tmp_path: Path) -> Path:
    def configure(providers: SyntheticProviders, clock: FakeClock) -> None:
        def crash(call: dict[str, Any]) -> None:
            raise Crash()
        providers.overrides[10] = crash
    with pytest.raises(Crash):
        run(tmp_path, configure=configure)
    return tmp_path / "attempts" / "synthetic-attempt-1"


@pytest.mark.parametrize("tail", [b'{"event":"RESOLVED","call_id":"10-P3', b'{"event":"ADMITTED","call_id":"11-P3'],
                         ids=["torn-resolution", "torn-admission"])
def test_torn_final_journal_record_recovers_the_durable_prefix_read_only(
        tmp_path: Path, tail: bytes, capsys: pytest.CaptureFixture[str]) -> None:
    attempt = _crashed_attempt(tmp_path)
    journal = attempt / "journal.jsonl"
    with journal.open("ab") as handle:
        handle.write(tail)
    before = journal.read_bytes()
    summary = recover_attempt(attempt)
    assert (summary["admitted"], summary["resolved"], summary["unknown_liability"]) == (10, 9, 1)
    assert summary["torn_tail"] is True and "TORN_TAIL" in summary["notice"]
    assert journal.read_bytes() == before
    capsys.readouterr()
    assert main(["recover", "--attempt-dir", str(attempt)]) == 0
    assert json.loads(capsys.readouterr().out)["torn_tail"] is True
    clock = FakeClock(T0 + 700)
    providers = SyntheticProviders(clock)
    credentials = Credentials()
    with pytest.raises(AttemptExists):
        run_attempt(recorder_input(tmp_path), transport=providers, clock=clock, credentials=credentials)
    assert providers.calls == [] and credentials.reads == []


def test_clean_journal_reports_no_torn_tail(tmp_path: Path) -> None:
    summary = recover_attempt(_crashed_attempt(tmp_path))
    assert summary["torn_tail"] is False


def test_interior_journal_corruption_is_a_stable_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.history_payload_binding import PayloadError
    attempt = _crashed_attempt(tmp_path)
    journal = attempt / "journal.jsonl"
    lines = journal.read_bytes().split(b"\n")
    lines.insert(3, b"{not json")
    journal.write_bytes(b"\n".join(lines))
    with pytest.raises(PayloadError) as refused:
        recover_attempt(attempt)
    assert refused.value.code == "JOURNAL_CORRUPT"
    capsys.readouterr()
    assert main(["recover", "--attempt-dir", str(attempt)]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "JOURNAL_CORRUPT"}
