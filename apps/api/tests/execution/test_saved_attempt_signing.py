"""The production original transport delays signer construction until its durable boundary."""
import dataclasses

import pytest

from edge_os_api.execution.original_transaction import JournalError
from execution.test_privy_signer import original, submit, client, FakeHttp, signed_reply, recorded_signature


def test_signer_is_constructed_for_saved_attempt_after_sign_requested(tmp_path):
    http = FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))
    transport, recordings, stages = original(tmp_path, None)
    built = []

    def signer_for_attempt(prepared):
        assert [stage for stage, _ in stages] == ["PREPARED", "SIGN_REQUESTED"]
        built.append(prepared.attempt_id)
        return client(http, request_id=prepared.attempt_id)

    transport._clients = dataclasses.replace(transport._clients, signer_for_attempt=signer_for_attempt)
    result = submit(transport, stages)
    assert built == ["attempt-0001"]
    assert result.detail == "BROADCAST_RETURNED"
    assert recordings.call_counts()["broadcast.eth_sendRawTransaction"] == 1
    assert http.calls[0]["headers"]["privy-idempotency-key"] == "attempt-0001"


@pytest.mark.parametrize("failure", ["PREPARED", "SIGN_REQUESTED", "stop"])
def test_failed_save_or_stop_never_constructs_signer(tmp_path, failure):
    transport, recordings, _ = original(tmp_path, None)

    def forbidden(prepared):
        raise AssertionError("credentials must not be acquired")

    transport._clients = dataclasses.replace(transport._clients, signer_for_attempt=forbidden)
    if failure == "stop":
        transport._controls = lambda: ["STOPPED_HALT_ALL_SWAPS"]

    def journal(stage, values):
        if stage == failure:
            raise JournalError("test save failed")

    from edge_os_api.execution.transport import PreparedSubmission
    result = transport.submit_original(PreparedSubmission(
        action_id="action-1", owner_id="owner-1", wallet_id=transport._context.wallet_id,
        network_id="monad:143", operation="ENTRY", payload_hash="sha256:payload", attempt_id="saved-attempt"), journal)
    assert result.outcome == "DEFINITELY_UNSENT"
    assert recordings.call_counts().get("broadcast.eth_sendRawTransaction", 0) == 0


def test_approved_raw_minimum_is_preserved_when_estimate_changes(tmp_path):
    from edge_os_api.kuru_flow import ApprovedAdapterConfiguration
    from edge_os_api.execution.original_transaction import OriginalTransactionTransport
    transport, recordings, stages = original(tmp_path, client(FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))))
    c, p = transport._context, recordings.profile
    # The quote is 50 tokens. Its declared 49.5-token guard stays exact even when the application's estimate differs.
    config = ApprovedAdapterConfiguration(network_id="monad:143", entrypoint_address=p.entrypoint,
        method=p.method, selector=p.selector, input_asset={"asset_id": c.sell.asset_id,
        "token_address": c.sell.token, "decimals": 6}, output_asset={"asset_id": c.buy.asset_id,
        "token_address": c.buy.token, "decimals": 18}, recipient=c.wallet_address,
        approved_input_raw="100000000", approved_min_output_raw="49500000000000000000",
        approved_program_hex=p.program_hex, fees={"fee_bps": p.fee_bps, "referrer_fee_bps": p.referrer_fee_bps,
        "fee_collector_address": p.fee_collector, "referrer_address": p.referrer, "is_in_token_fee": p.is_in_token_fee},
        approved_allowance_raw="100000000", freshness={"max_quote_age_seconds": 30, "max_input_age_seconds": 300,
        "intent_expires_at": c.intent_expires_at.isoformat(), "mandate_expires_at": c.mandate_expires_at},
        supported_schema_variants=["TRANSACTION_CALLDATA"])
    context = dataclasses.replace(c, buy=dataclasses.replace(c.buy, raw=100 * 10**18))
    transport = OriginalTransactionTransport(context, transport._clients, p, controls=lambda: [],
                                              clock=transport._clock, approved_route=config)
    result = submit(transport, stages)
    assert result.detail == "BROADCAST_RETURNED"
    assert dict(stages)["PREPARED"]["candidate"]["intent"]["min_amount_user_buys"] == "49500000000000000000"


def test_slow_quote_is_measured_after_network_before_signing(tmp_path):
    import datetime as dt
    transport, recordings, stages = original(tmp_path, client(FakeHttp(None)))
    now = [transport._clock()]
    route = transport._clients.route

    class SlowQuote:
        def quote(self, request):
            response = route.quote(request)
            now[0] += dt.timedelta(minutes=10)
            return response

    transport._clients = dataclasses.replace(transport._clients, route=SlowQuote())
    transport._clock = lambda: now[0]
    result = submit(transport, stages)
    assert result.outcome == "DEFINITELY_UNSENT"
    assert recordings.call_counts().get("broadcast.eth_getTransactionCount", 0) == 0


def bound_original(transport):
    from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
    from execution.test_operating_release import definition
    c, p = transport._context, transport._profile
    source = definition()
    identity = {"owner_id": c.owner_id, "agent_id": c.agent_id, "wallet_id": c.wallet_id,
        "wallet_address": c.wallet_address, "network_id": c.network_id, "strategy_id": "strategy-a",
        "publication_revision_id": "publication-a", "execution_revision_id": "execution-a", "market_binding_id": "market-a",
        "content_sha256": "1" * 64, "manifest_sha256": "2" * 64, "consent_adoption_id": "consent-a",
        "consent_hash": "sha256:" + "3" * 64, "review_hash": "sha256:" + "4" * 64, "terms_hash": "sha256:" + "5" * 64}
    source.update(wallet_id=c.wallet_id, wallet_address=c.wallet_address, valid_until=c.intent_expires_at.isoformat())
    source["transaction"]["request_expires_at"] = c.intent_expires_at.isoformat()
    source["route"].update(network_id=c.network_id, entrypoint_address=p.entrypoint, method=p.method, selector=p.selector,
        input_asset={"asset_id": c.sell.asset_id, "token_address": c.sell.token, "decimals": c.sell.decimals},
        output_asset={"asset_id": c.buy.asset_id, "token_address": c.buy.token, "decimals": c.buy.decimals},
        recipient=c.wallet_address, approved_input_raw=str(c.sell.raw), approved_min_output_raw="49500000000000000000",
        approved_program_hex=p.program_hex, approved_allowance_raw=str(c.allowance_raw),
        fees={"fee_bps": p.fee_bps, "referrer_fee_bps": p.referrer_fee_bps, "fee_collector_address": p.fee_collector,
              "referrer_address": p.referrer, "is_in_token_fee": p.is_in_token_fee},
        freshness={"max_quote_age_seconds": 30, "max_input_age_seconds": 300,
                   "intent_expires_at": c.intent_expires_at.isoformat(), "mandate_expires_at": c.mandate_expires_at})
    source["gas"] = {"gas_limit": p.gas_limit, "max_fee_per_gas": p.max_fee_per_gas,
                     "max_priority_fee_per_gas": p.max_priority_fee_per_gas, "budget_raw": str(c.gas_cap_raw)}
    release = OperatingRelease(source)
    binding = BoundRelease(release, identity, position_inventory_proof_sha256="6" * 64,
                           market_proof_sha256="7" * 64, finality_proof_sha256="8" * 64)
    return binding, {binding.sha256: release_sha256(release)}


def test_transport_refuses_unapproved_binding_before_quote_or_signer(tmp_path):
    from edge_os_api.execution.original_transaction import OriginalTransactionTransport
    transport, recordings, stages = original(tmp_path, client(FakeHttp(None)))
    binding, _ = bound_original(transport)
    context = dataclasses.replace(transport._context, identity=binding.identity())
    transport = OriginalTransactionTransport(context, transport._clients, transport._profile, controls=lambda: [],
        clock=transport._clock, binding=binding, synthetic_bindings={})
    result = submit(transport, stages)
    assert result.outcome == "DEFINITELY_UNSENT"
    assert recordings.call_counts() == {}


def test_transport_records_exact_release_and_binding_without_promoting_fixture_evidence(tmp_path):
    from edge_os_api.execution.original_transaction import OriginalTransactionTransport
    transport, recordings, stages = original(tmp_path, client(FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))))
    binding, approvals = bound_original(transport)
    context = dataclasses.replace(transport._context, identity=binding.identity())
    transport = OriginalTransactionTransport(context, transport._clients, transport._profile, controls=lambda: [],
        clock=transport._clock, binding=binding, synthetic_bindings=approvals)
    assert submit(transport, stages).detail == "BROADCAST_RETURNED"
    saved = dict(stages)["PREPARED"]
    assert saved["binding_sha256"] == binding.sha256
    assert saved["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert saved["release_sha256"] == approvals[binding.sha256]


def test_missing_attempt_id_cannot_construct_signer_or_read_quote(tmp_path):
    from edge_os_api.execution.transport import PreparedSubmission
    transport, recordings, stages = original(tmp_path, None)
    transport._clients = dataclasses.replace(transport._clients, signer_for_attempt=lambda p: pytest.fail("signer acquired"))
    c = transport._context
    result = transport.submit_original(PreparedSubmission(c.action_id, c.owner_id, c.wallet_id, c.network_id,
                                                          c.operation, c.payload_hash),
                                       lambda stage, values: stages.append((stage, values)))
    assert result.detail == "SAVED_ATTEMPT_REQUIRED"
    assert recordings.call_counts() == {}


def test_mandate_expiry_during_quote_preserves_exact_refusal(tmp_path):
    import datetime as dt
    transport, recordings, stages = original(tmp_path, client(FakeHttp(signed_reply(recorded_signature("ENTRY", 0)))))
    start = transport._clock()
    now = [start]
    transport._context = dataclasses.replace(transport._context,
        mandate_expires_at=(start + dt.timedelta(seconds=10)).isoformat())
    route = transport._clients.route

    class ExpiringQuote:
        def quote(self, request):
            reply = route.quote(request)
            now[0] = start + dt.timedelta(seconds=11)
            return reply

    transport._clients = dataclasses.replace(transport._clients, route=ExpiringQuote())
    transport._clock = lambda: now[0]
    result = submit(transport, stages)
    assert result.detail == "MANDATE_EXPIRED"
    assert recordings.call_counts().get("broadcast.eth_getTransactionCount", 0) == 0
    assert recordings.call_counts().get("signer.rpc", 0) == 0
