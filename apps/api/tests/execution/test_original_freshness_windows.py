"""The frozen quote and input ages are rechecked before each original effect (#58 Phase B)."""
from __future__ import annotations

import dataclasses
import datetime as dt

from edge_os_api.execution.original_transaction import OriginalTransactionTransport
from edge_os_api.execution.transport import PreparedSubmission

from execution.test_privy_signer import NOW, FakeHttp, client, original, recorded_signature, signed_reply


def _prepared(transport):
    c = transport._context
    return PreparedSubmission(action_id=c.action_id, owner_id=c.owner_id, wallet_id=c.wallet_id,
                              network_id=c.network_id, operation=c.operation, payload_hash=c.payload_hash,
                              attempt_id="attempt-0001")


def _transport(tmp_path, changes, clock):
    http = FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))
    transport, recordings, stages = original(tmp_path, client(http))
    profile = dataclasses.replace(recordings.profile, **changes)
    transport = OriginalTransactionTransport(transport._context, transport._clients, profile,
                                             controls=lambda: [], clock=clock)
    return transport, recordings, stages, http


class _SlowBroadcast:
    def __init__(self, inner, advance):
        self._inner, self._advance = inner, advance

    def call(self, method, params):
        result = self._inner.call(method, params)
        if method == "eth_getTransactionCount":
            self._advance()
        return result


class _SlowSigner:
    def __init__(self, inner, advance):
        self._inner, self._advance = inner, advance

    def rpc(self, wallet_id, body):
        reply = self._inner.rpc(wallet_id, body)
        self._advance()
        return reply


def _submit(transport, stages, journal_hook=None):
    def journal(stage, values):
        stages.append((stage, values))
        if journal_hook is not None:
            journal_hook(stage)
    return transport.submit_original(_prepared(transport), journal)


def test_a_slow_pre_sign_save_refuses_before_signing(tmp_path):
    now = [NOW]
    transport, recordings, stages, http = _transport(tmp_path, {"max_quote_age_seconds": 30}, lambda: now[0])

    def slow_save(stage):
        if stage == "SIGN_REQUESTED":
            now[0] += dt.timedelta(seconds=31)

    result = _submit(transport, stages, slow_save)
    assert (result.outcome, result.detail) == ("DEFINITELY_UNSENT", "STALE_QUOTE")
    assert http.calls == []
    assert recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0) == 0


def test_a_slow_nonce_read_refuses_before_signing(tmp_path):
    now = [NOW]
    transport, recordings, stages, http = _transport(tmp_path, {"max_quote_age_seconds": 30}, lambda: now[0])

    def advance():
        now[0] += dt.timedelta(seconds=31)

    transport._clients = dataclasses.replace(
        transport._clients, broadcast=_SlowBroadcast(transport._clients.broadcast, advance))
    result = _submit(transport, stages)
    assert (result.outcome, result.detail) == ("DEFINITELY_UNSENT", "STALE_QUOTE")
    assert http.calls == []
    assert recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0) == 0


def test_a_stale_input_refuses_before_signing(tmp_path):
    now = [NOW]
    transport, recordings, stages, http = _transport(
        tmp_path, {"max_quote_age_seconds": 1000, "max_input_age_seconds": 300}, lambda: now[0])

    def slow_save(stage):
        if stage == "SIGN_REQUESTED":
            now[0] += dt.timedelta(seconds=241)

    result = _submit(transport, stages, slow_save)
    assert (result.outcome, result.detail) == ("DEFINITELY_UNSENT", "STALE_INPUT")
    assert http.calls == []
    assert recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0) == 0


def test_a_slow_signature_refuses_before_broadcast_with_the_liability_kept(tmp_path):
    now = [NOW]
    transport, recordings, stages, http = _transport(tmp_path, {"max_quote_age_seconds": 30}, lambda: now[0])

    def advance():
        now[0] += dt.timedelta(seconds=31)

    transport._clients = dataclasses.replace(
        transport._clients, signer=_SlowSigner(transport._clients.signer, advance))
    result = _submit(transport, stages)
    assert (result.outcome, result.detail) == ("SUBMISSION_POSSIBLE", "STOPPED_AFTER_SIGNING:STALE_QUOTE")
    assert recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0) == 0


def test_fresh_quote_and_input_still_reach_one_broadcast(tmp_path):
    now = [NOW]
    transport, recordings, stages, http = _transport(tmp_path, {"max_quote_age_seconds": 30}, lambda: now[0])
    result = _submit(transport, stages)
    assert (result.outcome, result.detail) == ("SUBMISSION_POSSIBLE", "BROADCAST_RETURNED")
    assert len(http.calls) == 1
    assert recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0) == 1
