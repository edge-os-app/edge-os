"""Capability boundaries use production composition without a DB or network."""
from types import SimpleNamespace

import pytest

from edge_os_api.core.financial_services import build_financial_services
from edge_os_api.core.provider_ports import ProviderPorts
from edge_os_api.execution.recurring_producer import build_producer
from edge_os_api.execution.worker import ConnectedExecution


def no_io(*args, **kwargs):
    raise AssertionError("unexpected database or execution capability construction")


@pytest.mark.parametrize("role", ["api", "recurring"])
def test_read_only_roles_cannot_construct_original_execution_clients(role):
    ports = ProviderPorts("fixture", None, None, None, None, None, None,
                          original=SimpleNamespace(clients=no_io))
    settings = SimpleNamespace(execution_mode="fixture", fixture_effects_path=None, original_recordings_dir=None)
    services = build_financial_services(no_io, settings, ports, role=role)
    assert services.ports.original_clients("agent-fx-original") is None


def test_recurring_builder_does_not_inherit_worker_capabilities(monkeypatch):
    from edge_os_api.core import financial_services

    real_builder = financial_services.build_financial_services
    observed = []

    def builder(factory, settings, **kwargs):
        observed.append(kwargs.get("role"))
        return real_builder(factory, settings, **kwargs)

    monkeypatch.setattr(financial_services, "build_financial_services", builder)
    settings = SimpleNamespace(execution_mode="unavailable", fixture_effects_path=None, original_recordings_dir=None)
    build_producer(no_io, settings, no_io)
    assert observed == ["recurring"]


@pytest.mark.parametrize("envelope, expected", [
    ({"stage": "REFUSED_UNSENT"}, "ORIGINAL_REFUSED_UNSENT"),
    ({"in_flight": True}, "ORIGINAL_IN_FLIGHT"),
    ({"stage": "SIGNING_UNKNOWN"}, "original:no-transaction-hash"),
])
def test_recovery_without_hash_never_acquires_any_original_client(envelope, expected):
    ports = SimpleNamespace(original_clients=no_io, original_observer=no_io)
    recovery = SimpleNamespace(status=lambda *args: SimpleNamespace(state="UNKNOWN", decision_status="SUBMISSION_UNKNOWN"))
    connected = ConnectedExecution(no_io, SimpleNamespace(recovery=recovery), ports, qualification="unavailable")
    # This intent has the exact recovery binding shape; no persistence is needed to exercise the reader boundary.
    intent = SimpleNamespace(action_id="action", agent_id="agent", operation="ENTRY", revision_id="revision",
                             policy_binding="policy", payload_hash="sha256:" + "a" * 64,
                             payload={"binding": {"agent_id": "agent", "wallet_id": "wallet",
                                 "network_id": "monad:143", "strategy_revision": "revision", "mandate_id": "mandate"}})
    connected._apply = lambda owner, action, evidence, outcome: evidence
    result = connected._reconcile_original("owner", intent, envelope)
    assert result.detail == expected


def test_composition_keeps_recorded_holdings_on_the_same_injected_clock(tmp_path):
    import datetime as dt
    import shutil
    from pathlib import Path
    recording = Path(__file__).parents[1] / "fixtures/original_transaction/original_transaction_v1.json"
    shutil.copy(recording, tmp_path / recording.name)
    settings = SimpleNamespace(execution_mode="fixture", fixture_effects_path=None, original_recordings_dir=str(tmp_path))
    services = build_financial_services(no_io, settings, role="api")
    moment = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
    services.ports.clock = lambda: moment
    assert services.ports.holdings._clock() == moment


def test_controlled_runtime_denies_unapproved_release_before_loading_any_credential(tmp_path):
    from edge_os_api.core.provider_ports import ControlledRuntime, ProviderUnavailable
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    binding, _ = bound_original(transport)
    runtime = ControlledRuntime(binding=binding, http=no_io, quote_token=no_io, signer_access=no_io,
                                clock=transport._clock, synthetic_bindings={})
    with pytest.raises(ProviderUnavailable):
        runtime.clients(no_io, transport._context, no_io, role="worker")


@pytest.mark.parametrize("role", ["api", "recurring"])
def test_controlled_runtime_cannot_supply_signing_or_broadcast_to_read_only_roles(tmp_path, role):
    from edge_os_api.core.provider_ports import ControlledRuntime, ProviderUnavailable
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    binding, approvals = bound_original(transport)
    runtime = ControlledRuntime(binding=binding, http=no_io, quote_token=no_io, signer_access=no_io,
                                clock=transport._clock, synthetic_bindings=approvals)
    with pytest.raises(ProviderUnavailable):
        runtime.clients(no_io, transport._context, no_io, role=role)


@pytest.mark.parametrize("prior_attempt", [False, True])
def test_runtime_mounts_accepted_clients_with_same_saved_attempt_and_original_bytes(tmp_path, prior_attempt):
    import dataclasses
    import json
    import uuid
    from edge_os_api.core.provider_ports import ControlledRuntime
    from edge_os_api.execution.original_transaction import OriginalTransactionTransport
    from edge_os_api.execution.transport import PreparedSubmission
    from edge_os_api.research_history.http_clients.http_transport import HttpResponse
    from execution.test_privy_signer import original, recorded_signature, ENTRY_NONCE0_HASH
    from execution.test_saved_attempt_signing import bound_original
    transport, recordings, _ = original(tmp_path, None)
    transport._context = dataclasses.replace(transport._context, owner_id=str(uuid.uuid4()))
    binding, approvals = bound_original(transport)
    context = dataclasses.replace(transport._context, identity=binding.identity())
    attempt_id, queue_id = uuid.uuid4(), uuid.uuid4()
    row = SimpleNamespace(attempt_id=attempt_id, owner_id=uuid.UUID(context.owner_id), action_id=context.action_id,
        agent_id=context.agent_id, wallet_id=context.wallet_id, network_id=context.network_id,
        payload_hash=context.payload_hash, transport_id="original-transaction/1", state="IN_FLIGHT", queue_id=queue_id,
        content={"original_transaction": {}})
    claim = SimpleNamespace(state="ACTIVE", queue_id=queue_id, action_id=context.action_id)
    admission = SimpleNamespace(status="SUBMISSION_UNKNOWN")

    class SavedSession:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement):
            if statement.column_descriptions[0]["name"] == "attempt_id":
                return SimpleNamespace(scalar_one_or_none=lambda: uuid.uuid4() if prior_attempt else None)
            entity = statement.column_descriptions[0]["entity"].__name__
            value = {"SubmissionAttemptRow": row, "ClaimRow": claim, "DecisionRow": admission}[entity]
            return SimpleNamespace(scalar_one_or_none=lambda: value)

    class Http:
        def __init__(self): self.calls = []
        def request(self, **request):
            body = json.loads(request["body"])
            self.calls.append((request["url"], body, request["headers"]))
            if request["url"].endswith("/api/quote"):
                reply = dict(recordings.data["routes"][0]["response"])
                reply["transaction"] = {**reply["transaction"], "value":"0"}
                reply.update(type="quote", status="success", gasPrices={key:"2000000000" for key in ("slow","standard","fast","rapid","extreme")})
            elif request["url"].startswith("https://api.privy.io/"):
                reply = {"method":"eth_signTransaction", "data":{"signed_transaction":recorded_signature("ENTRY",0), "encoding":"rlp"}}
            else:
                result = "0x0" if body["method"] == "eth_getTransactionCount" else ENTRY_NONCE0_HASH
                if body["method"] == "eth_sendRawTransaction":
                    assert row.content["original_transaction"]["stage"] == "BROADCAST_REQUESTED"
                    assert body["params"] == [row.content["original_transaction"]["signed_bytes"]]
                reply = {"jsonrpc":"2.0", "id":body["id"], "result":result}
            return HttpResponse(200, {}, json.dumps(reply).encode())

    acquired = []
    def credentials():
        assert row.content["original_transaction"]["stage"] == "SIGN_REQUESTED"
        acquired.append(str(attempt_id))
        return {"app_id":"fake_app", "app_secret":"fake_worker_secret", "authorize":lambda p:"ZmFrZQ=="}

    http = Http()
    runtime = ControlledRuntime(binding=binding, http=http, quote_token=lambda:"fake_quote_token", signer_access=credentials,
        clock=transport._clock, synthetic_bindings=approvals)
    clients = runtime.clients(SavedSession, context, lambda: [], role="worker")
    assert acquired == [] and http.calls == []
    mounted = OriginalTransactionTransport(context, clients, transport._profile, controls=lambda: [],
        clock=transport._clock, binding=binding, synthetic_bindings=approvals)
    def journal(stage, values):
        row.content["original_transaction"].update(values, stage=stage)
    result = mounted.submit_original(PreparedSubmission(context.action_id, context.owner_id, context.wallet_id,
        context.network_id, context.operation, context.payload_hash, str(attempt_id)), journal)
    if prior_attempt:
        assert result.outcome == "DEFINITELY_UNSENT"
        assert acquired == [] and http.calls == []
        return
    assert result.detail == "BROADCAST_RETURNED", (result, [(url, body.get("method", "quote")) for url,body,_ in http.calls])
    assert acquired == [str(attempt_id)]
    assert [body.get("method", "quote") for _,body,_ in http.calls] == ["quote", "eth_getTransactionCount", "eth_signTransaction", "eth_sendRawTransaction"]
    assert http.calls[2][2]["privy-idempotency-key"] == str(attempt_id)


def test_controlled_observer_has_no_sign_or_broadcast_capability(tmp_path):
    from edge_os_api.core.provider_ports import ControlledRuntime
    from edge_os_api.execution.original_transaction import RpcError
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    binding, approvals = bound_original(transport)
    runtime = ControlledRuntime(binding=binding, http=no_io, quote_token=no_io, signer_access=no_io,
                                clock=transport._clock, synthetic_bindings=approvals)
    observer = runtime.observer()
    with pytest.raises(RpcError):
        observer.call("eth_sendRawTransaction", ["0x02"])
    with pytest.raises(RpcError):
        observer.call("eth_signTransaction", [{}])


def test_api_composition_removes_worker_credential_loaders_from_registered_runtime(tmp_path):
    from edge_os_api.core.provider_ports import ControlledRuntime, build_provider_ports, ProviderUnavailable
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    binding, approvals = bound_original(transport)
    runtime = ControlledRuntime(binding=binding, http=no_io, quote_token=no_io, signer_access=no_io,
                                clock=transport._clock, synthetic_bindings=approvals)
    ports = build_provider_ports("controlled", no_io, role="worker", controlled={"agent-1":runtime})
    settings = SimpleNamespace(execution_mode="controlled", fixture_effects_path=None, original_recordings_dir=None)
    api = build_financial_services(no_io, settings, ports, role="api")
    exposed = api.ports.controlled["agent-1"]
    assert exposed.signer_access is None and exposed.quote_token is None
    with pytest.raises(ProviderUnavailable):
        exposed.clients(no_io, transport._context, no_io, role="worker")
    assert runtime.signer_access is no_io  # composing the API did not mutate the worker's object


def test_missing_current_feed_qualification_does_not_call_a_source(tmp_path):
    from edge_os_api.core.provider_ports import ControlledRuntime, MarketObservationRequest, ProviderUnavailable
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    binding, approvals = bound_original(transport)
    runtime = ControlledRuntime(binding=binding, http=no_io, market_source=SimpleNamespace(observe=no_io),
                                clock=transport._clock, synthetic_bindings=approvals)
    request = MarketObservationRequest("agent-1", "market-a", transport._clock(), 2, False)
    with pytest.raises(ProviderUnavailable):
        runtime.observe_market(request)


def test_only_release_bound_current_observations_reach_the_evaluator(tmp_path):
    from edge_os_api.core.provider_ports import ControlledRuntime, MarketObservationRequest, FixtureMarketObservations, MarketObservations, ProviderUnavailable
    from edge_os_api.execution.operating_release import BoundRelease, release_sha256
    from edge_os_api.research.forward_observation import ForwardObservation
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    prior, _ = bound_original(transport)
    profile = {"source_id":"synthetic-current/1", "delivery_profile_sha256":"9" * 64,
               "finality":"finalized", "warmup_buckets":2, "max_collection_age_seconds":30}
    binding = BoundRelease(prior.release, prior.identity(), market_profile=profile, **prior.proofs())
    now = transport._clock()
    request = MarketObservationRequest("agent-1", "market-a", now, 2, False)
    authored = FixtureMarketObservations().observe(request)
    forward = ForwardObservation(network="monad:143", market_binding_id="market-a",
        base_asset=transport._context.buy.asset_id, quote_asset=transport._context.sell.asset_id,
        units="QUOTE_PER_BASE", event="event-a", collected_at=now.isoformat(), observed_at=now.isoformat(),
        finality="finalized", coverage="COMPLETE", evidence_class="SYNTHETIC_FIXTURE", age_seconds=0,
        availability="AVAILABLE", reason=None)
    provenance = {**authored.provenance, "source":"synthetic-current/1", "evidence_class":"SYNTHETIC_FIXTURE",
        "availability_basis":"FORWARD_OBSERVED", "finality":"finalized", "binding_sha256":binding.sha256,
        "qualification_proof_sha256":binding.proofs()["market_proof_sha256"], "delivery_profile_sha256":"9" * 64,
        "warmup_buckets":2}
    observed = MarketObservations(authored.inputs, provenance, forward=forward)
    source = SimpleNamespace(observe=lambda req: observed)
    runtime = ControlledRuntime(binding=binding, http=no_io, market_source=source, clock=lambda: now,
        synthetic_bindings={binding.sha256:release_sha256(binding.release)})
    result = runtime.observe_market(request)
    assert result.inputs == authored.inputs
    from edge_os_api.execution.worker import observation_problem
    assert observation_problem(result.provenance, now, now, "controlled", runtime=runtime) == (None, now)
    assert result.provenance["forward_observation"]["event"] == "event-a"
    provenance["evidence_class"] = "RECORDED_RESPONSE"
    with pytest.raises(ProviderUnavailable):
        runtime.observe_market(request)


def test_controlled_quote_is_an_approved_minimum_and_cannot_change_raw_input(tmp_path):
    from edge_os_api.core.provider_ports import ControlledRuntime, build_provider_ports, QuoteRequest, ProviderUnavailable
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    binding, approvals = bound_original(transport)
    runtime = ControlledRuntime(binding=binding, http=no_io, clock=transport._clock, synthetic_bindings=approvals)
    ports = build_provider_ports("controlled", no_io, role="worker", controlled={"agent-1":runtime})
    c = transport._context
    identity = binding.identity()
    request = QuoteRequest("ENTRY", c.sell.asset_id, 6, c.buy.asset_id, 18, "100000000", None, transport._clock(),
                           owner_id=identity["owner_id"], agent_id=identity["agent_id"],
                           consent_adoption_id=identity["consent_adoption_id"])
    result = ports.quotes.quote(request)
    assert result.output.raw == "49500000000000000000"
    assert result.basis == "APPROVED_MINIMUM"
    import dataclasses
    with pytest.raises(ProviderUnavailable):
        ports.quotes.quote(dataclasses.replace(request, quote_input_raw="100000001"))


def test_controlled_holdings_refuses_foreign_owner_before_observer(tmp_path, monkeypatch):
    from edge_os_api.core.provider_ports import ControlledRuntime, build_provider_ports, ProviderUnavailable
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    from execution.test_provider_observations import Rpc
    transport, _, _ = original(tmp_path, None)
    binding, approvals = bound_original(transport)
    rpc = Rpc(timestamp=int(transport._clock().timestamp()))
    monkeypatch.setattr(ControlledRuntime, "observer", lambda self: rpc)
    runtime = ControlledRuntime(binding=binding, http=no_io, clock=transport._clock, synthetic_bindings=approvals)
    ports = build_provider_ports("controlled", no_io, role="api", controlled={"agent-1":runtime})
    c = transport._context
    result = ports.holdings.observe(owner_id=c.owner_id, agent_id=c.agent_id, wallet_id=c.wallet_id,
        network_id=c.network_id, assets=[(c.sell.asset_id, 6)])
    assert result.assets[c.sell.asset_id].raw == "123"
    before = len(rpc.calls)
    with pytest.raises(ProviderUnavailable):
        ports.holdings.observe(owner_id="foreign", agent_id=c.agent_id, wallet_id=c.wallet_id,
            network_id=c.network_id, assets=[(c.sell.asset_id, 6)])
    assert len(rpc.calls) == before


def test_controlled_worker_without_registered_release_refuses_before_database_or_credentials():
    settings = SimpleNamespace(execution_mode="controlled", fixture_effects_path=None, original_recordings_dir=None)
    services = build_financial_services(no_io, settings, role="worker")
    assert services.connected.approval(SimpleNamespace(agent_id="missing"), no_io) == (None, "ACTIVATION_UNAVAILABLE")


def test_api_and_worker_recorded_holdings_keep_their_own_clocks(tmp_path):
    import datetime as dt
    import shutil
    from pathlib import Path
    recording = Path(__file__).parents[1] / "fixtures/original_transaction/original_transaction_v1.json"
    shutil.copy(recording, tmp_path / recording.name)
    settings = SimpleNamespace(execution_mode="fixture", fixture_effects_path=None, original_recordings_dir=str(tmp_path))
    api = build_financial_services(no_io, settings, role="api")
    worker = build_financial_services(no_io, settings, api.ports, role="worker")
    first, second = dt.datetime(2026,10,18,tzinfo=dt.timezone.utc), dt.datetime(2026,10,19,tzinfo=dt.timezone.utc)
    api.ports.clock, worker.ports.clock = lambda:first, lambda:second
    assert api.ports.holdings._clock() == first
    assert worker.ports.holdings._clock() == second


def owner_runtimes(tmp_path, clock=None, **inputs):
    """Two owners' synthetic runtimes on one route. `inputs` gives an owner a different approved input amount."""
    from edge_os_api.core.provider_ports import ControlledRuntime
    from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
    from execution.test_privy_signer import original
    from execution.test_saved_attempt_signing import bound_original
    transport, _, _ = original(tmp_path, None)
    prior, _ = bound_original(transport)
    runtimes = {}
    for owner in ("a", "b"):
        release = prior.release
        if owner in inputs:
            content = prior.release.content()
            content.pop("schema")
            content["route"].update(approved_input_raw=inputs[owner], approved_allowance_raw=inputs[owner])
            release = OperatingRelease(content)
        identity = {**prior.identity(), "owner_id": f"owner-{owner}", "agent_id": f"agent-{owner}",
                    "consent_adoption_id": f"consent-{owner}"}
        binding = BoundRelease(release, identity, **prior.proofs())
        runtimes[f"agent-{owner}"] = ControlledRuntime(binding=binding, http=no_io, quote_token=lambda: "token",
            signer_access=lambda: {}, clock=clock or transport._clock,
            synthetic_bindings={binding.sha256: release_sha256(release)})
    return transport, runtimes


def quote_for(transport, owner, raw="100000000", **identity):
    from edge_os_api.core.provider_ports import QuoteRequest
    c = transport._context
    values = {"owner_id": f"owner-{owner}", "agent_id": f"agent-{owner}", "consent_adoption_id": f"consent-{owner}",
              **identity}
    return QuoteRequest("ENTRY", c.sell.asset_id, 6, c.buy.asset_id, 18, raw, None, transport._clock(), **values)


def test_controlled_quote_selects_only_the_requesting_owners_runtime_on_a_shared_route(tmp_path):
    from edge_os_api.core.provider_ports import build_provider_ports, ProviderUnavailable
    transport, runtimes = owner_runtimes(tmp_path)
    ports = build_provider_ports("controlled", no_io, role="worker", controlled=runtimes)
    for owner in ("a", "b"):
        result = ports.quotes.quote(quote_for(transport, owner))
        assert result.source_ref == "approved-minimum:" + runtimes[f"agent-{owner}"].binding.sha256
        assert result.basis == "APPROVED_MINIMUM"
    refused = [quote_for(transport, "c"),  # an owner with no runtime
               quote_for(transport, "a", agent_id="agent-b"),  # another owner's agent
               quote_for(transport, "a", owner_id="owner-b"),
               quote_for(transport, "a", consent_adoption_id="consent-b"),
               quote_for(transport, "a", owner_id=None, agent_id=None, consent_adoption_id=None)]
    for request in refused:
        with pytest.raises(ProviderUnavailable, match="approved_minimum"):
            ports.quotes.quote(request)


def test_controlled_quote_with_another_owners_amount_never_reads_that_owners_binding(tmp_path):
    from edge_os_api.core.provider_ports import build_provider_ports, ProviderUnavailable
    transport, runtimes = owner_runtimes(tmp_path, clock=no_io, b="200000000")
    ports = build_provider_ports("controlled", no_io, role="worker", controlled=runtimes)
    # Owner a asks for owner b's approved amount: refused before any runtime is admitted or its clock is read.
    with pytest.raises(ProviderUnavailable, match="approved_minimum"):
        ports.quotes.quote(quote_for(transport, "a", raw="200000000"))
    with pytest.raises(ProviderUnavailable, match="approved_minimum"):
        ports.quotes.quote(quote_for(transport, "b", raw="100000000"))


@pytest.mark.parametrize("first", ["api", "recurring", "worker"])
def test_worker_ports_always_build_from_the_full_controlled_set(tmp_path, first):
    from edge_os_api.core.provider_ports import build_provider_ports
    _, runtimes = owner_runtimes(tmp_path)
    reduced = build_provider_ports("controlled", no_io, role=first, controlled=runtimes)
    worker = reduced.for_role("worker")
    assert worker.role == "worker"
    assert {key: (runtime.quote_token, runtime.signer_access) for key, runtime in worker.controlled.items()} == {
        key: (runtime.quote_token, runtime.signer_access) for key, runtime in runtimes.items()}
    for role in ("api", "recurring"):
        assert all(runtime.signer_access is None and runtime.quote_token is None
                   for runtime in worker.for_role(role).controlled.values())
    settings = SimpleNamespace(execution_mode="controlled", fixture_effects_path=None, original_recordings_dir=None)
    services = build_financial_services(no_io, settings, reduced, role="worker")
    assert all(runtime.signer_access is not None for runtime in services.ports.controlled.values())
