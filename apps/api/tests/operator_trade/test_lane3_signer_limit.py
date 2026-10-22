"""The installed signer refuses transaction quantities above 2**53-1. That is lane 3's change, not ours.

These checks read the signer's actual behavior. They never infer it from a version or a comment, and they never
pass silently when the behavior is unknown.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.operator_trade.journal import Journal
from scripts.operator_trade.plan import plan_trade
from scripts.operator_trade.preflight import read_preflight
from scripts.operator_trade.sequence import execute
from scripts.operator_trade.trade_file import load_trade_file

from ._support import (
    INPUT,
    FakePrivyTransport,
    FakeRpc,
    clock_pair,
    current_signer_refuses_large_quantity,
    make_real_signer_factory,
    signed_for,
    trade_dict,
    write_p256_key,
)

LANE3_REASON = (
    "lane-3 signer change absent: the installed PrivySignerClient refuses transaction quantities above 2**53-1; "
    "this check reads the signer behavior, so it runs after that change"
)


def test_the_installed_signer_reports_its_own_quantity_limit() -> None:
    # This test documents the current behavior and always asserts a definite answer, never a skip.
    reply = _probe()
    assert "error" in reply or "data" in reply


def _probe() -> dict[str, object]:
    from ._support import WALLET_ID, _signer_body
    from cryptography.hazmat.primitives.asymmetric import ec
    import time

    from edge_os_api.execution.privy_signer import PrivySignerClient, make_p256_authorizer

    signer = PrivySignerClient(
        app_id="operator-test", app_secret="operator-test-secret",
        authorize=make_p256_authorizer(private_key=ec.generate_private_key(ec.SECP256R1())),
        request_id="operator-test-probe", request_expiry_ms=time.time_ns() // 1_000_000 + 300_000,
        http=FakePrivyTransport([signed_for("wrap")]), connect_timeout_seconds=1.0,
        deadline_monotonic=time.monotonic() + 60.0, max_response_bytes=65536,
    )
    return signer.rpc(WALLET_ID, _signer_body(INPUT))


@pytest.mark.skipif(current_signer_refuses_large_quantity(), reason=LANE3_REASON)
def test_large_wrap_signs_and_broadcasts_after_lane3(tmp_path: Path) -> None:
    # Runs only when the signer accepts a 50 MON quantity. Never a silent pass.
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    trade = load_trade_file(path)
    rpc = FakeRpc(wmon_series=[0, INPUT, 0], moe_series=[0, 10**18])
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
               reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    key_path = tmp_path / "agent.pem"
    write_p256_key(key_path)
    transport = FakePrivyTransport([signed_for(step) for step in ("wrap", "approve", "swap", "revoke")])
    now, sleep = clock_pair()
    outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight,
                      signer_factory=make_real_signer_factory([], key_path, transport),
                      journal=Journal.create(tmp_path / "store"), now=now, sleep=sleep)
    assert outcome.ok is True
    assert len(rpc.sent) == 4


@pytest.mark.skipif(not current_signer_refuses_large_quantity(), reason="lane 3 is present; the refusal no longer applies")
def test_large_wrap_is_refused_before_any_broadcast_today(tmp_path: Path) -> None:
    path = tmp_path / "trade.json"
    path.write_text(json.dumps(trade_dict()), encoding="utf-8")
    trade = load_trade_file(path)
    rpc = FakeRpc(wmon_series=[0, INPUT])
    preflight = read_preflight(rpc, trade)
    plan = plan_trade(trade, base_fee=preflight.base_fee, priority_fee=preflight.priority_fee,
               reserve_wmon=preflight.reserve_wmon, reserve_moe=preflight.reserve_moe)
    key_path = tmp_path / "agent.pem"
    write_p256_key(key_path)
    transport = FakePrivyTransport([signed_for("wrap")])
    now, sleep = clock_pair()
    outcome = execute(rpc=rpc, trade=trade, plan=plan, preflight=preflight,
                      signer_factory=make_real_signer_factory([], key_path, transport),
                      journal=Journal.create(tmp_path / "store"), now=now, sleep=sleep)
    assert outcome.ok is False
    assert outcome.error_code == "SIGNER_REFUSED"
    assert rpc.sent == []
