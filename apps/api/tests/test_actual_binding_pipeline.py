"""Synthetic /2 producer -> admission -> PostgreSQL -> saved consumer and fresh-session rerun.

Requires a separately granted DB boundary. The actual producer uses an in-memory HTTPS peer, never a provider.
The existing stand-in journey suite separately covers HTTP adoption/replay and API/worker restart.
"""
from __future__ import annotations

import copy
import datetime as dt
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from edge_os_api.core.authentication import Principal
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.core.errors import AppError
from edge_os_api.core.research.operating_release import _check_history
from edge_os_api.records.contract_adapter import sha256_hex
from edge_os_api.research import history_dataset, history_payload_binding as binding
from edge_os_api.research.investigation_jobs import InvestigationEventRow
from edge_os_api.research_history.qualification_engine import raw_sha256
from test_actual_binding_admission import history_for
from test_saved_history_payload_binding import env, settings  # existing isolated DB/migration fixtures
from tests.test_history_payload_binding_v2 import graph


@pytest.fixture
def persisted_actual(settings, tmp_path, monkeypatch):
    anchor, export, _ = graph(tmp_path, monkeypatch)
    _check_history("ACTUAL", history_for(anchor))
    # Each case has independent application identities in the same module-owned database.
    content = copy.deepcopy(export["content"])
    for name in ("dataset_id", "owner_id", "job_id", "attempt_id", "declaration_id"):
        content[name] = str(uuid.uuid4())
    owner, dataset, job, attempt = (uuid.UUID(content[key]) for key in ("owner_id", "dataset_id", "job_id", "attempt_id"))
    content[binding.REQUIREMENT_KEY] = binding.requirement(anchor)
    started = {"operating_release": content["operating_release"], "input": {"source_id": content["source_id"]},
               binding.REQUIREMENT_KEY: content[binding.REQUIREMENT_KEY]}
    engine = make_engine(settings.database_url, statement_timeout_ms=10000)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            session.add(InvestigationEventRow(event_id=uuid.uuid4(), owner_id=owner, job_id=job, attempt_id=attempt,
                        kind="ATTEMPT_STARTED", content=started, created_at=dt.datetime.now(dt.timezone.utc)))
            history_dataset.save_dataset(session, content, export["raw_records"])
            event = binding.record_binding(session, owner_id=owner, job_id=job, attempt_id=attempt,
                                            dataset_id=dataset, definition=anchor)
            assert event["result"] == "PASS"
            session.commit()
        yield engine, factory, owner, dataset, job, attempt, event
    finally:
        engine.dispose()


def consumer(factory, owner, dataset):
    with factory() as session:
        row = binding._stored_row(session, owner, dataset)
        return binding.require_bound(session, Principal(owner, "synthetic-owner"), row,
                                     stage="TEST_ACTUAL_SAVED_CONSUMER", path="history_dataset")


def test_actual_bound_dataset_reopens_with_exact_graph_after_connections_restart(persisted_actual):
    engine, factory, owner, dataset, job, attempt, event = persisted_actual
    before = consumer(factory, owner, dataset)
    assert before["status"] == "PASS"
    engine.dispose()  # discard connections and identity maps; load persisted rows through a fresh session
    after = consumer(factory, owner, dataset)
    assert before == after and after["report_sha256"] == event["report_sha256"]
    with factory() as session:
        saved = session.execute(select(InvestigationEventRow).where(InvestigationEventRow.job_id == job,
                                InvestigationEventRow.kind == binding.EVENT_KIND)).scalar_one()
        assert saved.content["provenance_json"] == event["provenance_json"]
        assert binding._stored_row(session, uuid.uuid4(), dataset) is None
        shown = binding.public_event(binding.EVENT_KIND, saved.content)
        assert "handoff_json" not in shown and "provenance_json" not in shown
        saved.content = {**saved.content, "result": "MISMATCH"}
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_actual_consumer_rereads_saved_rows_and_rejects_rehashed_mutation(persisted_actual):
    _, factory, owner, dataset, *_ = persisted_actual
    with factory() as session:
        row = binding._stored_row(session, owner, dataset)
        raw, content = copy.deepcopy(row.raw_records), copy.deepcopy(row.content)
        raw[0]["data"] = "0x" + "00" * 128
        content["raw_evidence"]["sha256"] = raw_sha256(raw)
        # Model corrupt storage in this module-owned test DB; restore its trigger in the same transaction.
        session.execute(text("ALTER TABLE research_local.history_datasets DISABLE TRIGGER history_datasets_immutable"))
        try:
            row.raw_records, row.content, row.content_sha256 = raw, content, sha256_hex(content)
            session.flush()
        finally:
            session.execute(text("ALTER TABLE research_local.history_datasets ENABLE TRIGGER history_datasets_immutable"))
        session.commit()
    with pytest.raises(AppError) as caught:
        consumer(factory, owner, dataset)
    assert caught.value.code == "payload_binding_mismatch"


@pytest.mark.parametrize("mutation,reason", [
    ("missing-anchor", "forward_history_binding_not_admitted"),
    ("changed-checker", "forward_history_checker_unavailable"),
    ("replacement-graph", "operating_release_changed"),
])
def test_actual_job_boundary_refuses_before_reservation_and_worker_effects(settings, owner_a, monkeypatch,
                                                                          mutation, reason):
    # AUTHORED TEST graph: this case proves effect ordering, not provider provenance or payload collection.
    import json
    from dataclasses import replace
    from fastapi.testclient import TestClient
    import forward_history_stand_in as bound
    from edge_os_api.core.research import operating_release
    from edge_os_api.core.research.operating_release import BINDING_FACT
    from edge_os_api.core.research.released_source_runtime import open_released_runtime
    from edge_os_api.main import create_app
    from edge_os_api.research_history.http_clients import StdlibHttpTransport
    from test_actual_binding_admission import authored_actual_history
    from test_saved_history_payload_binding import counts, job_view, rows, started, worker
    from tests.test_history_payload_binding_v2 import reanchor

    class NoEffects:
        def __init__(self):
            self.reads, self.requests = [], []

        def read(self, slot):
            self.reads.append(slot)
            raise AssertionError("refused ACTUAL job must not read credentials")

        def request(self, *args, **kwargs):
            self.requests.append((args, kwargs))
            raise AssertionError("refused ACTUAL job must not send")

    effects = NoEffects()
    history = replace(bound.bound_release(nansen=False).history, envio_endpoint="https://hypersync.example.com",
                      quicknode_host="quicknode.example.com")
    release = operating_release.OperatingRelease("authored-boundary-actual/2", "ACTUAL",
                                                history=authored_actual_history(history))
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {
        release.release_id: operating_release.release_sha256(release)})
    runtime = open_released_runtime(settings, release, credentials=effects, http_transport=StdlibHttpTransport)
    monkeypatch.setattr(StdlibHttpTransport, "request", effects.request)
    with TestClient(create_app(settings, research_runtime=runtime)) as client:
        intake, declaration, _ = bound.declare(client, owner_a, runtime.release.history.limits)
        queued = started(client, owner_a, runtime)
        before_budget = client.get("/v1/research/budget", headers=owner_a).json()
        before_counts = counts(client)
        reservations = rows(client, "select count(*) n from usage_local.usage_reservations")[0]["n"]
        if mutation == "missing-anchor":
            monkeypatch.delitem(runtime.release.history.provider_facts, BINDING_FACT)
        elif mutation == "changed-checker":
            monkeypatch.setattr(binding, "CHECKER_SHA256_V2", "b" * 64)
        else:
            anchor = runtime.release.history.provider_facts[BINDING_FACT]
            h = json.loads(anchor["handoff_json"])
            h["evidence_notice"] = "Different internally valid AUTHORED TEST graph"
            replacement, _ = reanchor(anchor, {}, handoff=h)
            monkeypatch.setitem(runtime.release.history.provider_facts, BINDING_FACT, replacement)
            _check_history("ACTUAL", runtime.release.history)
        from research_flows import jobs_path
        refused = client.post(jobs_path(intake, declaration), headers=owner_a,
                              json={"operation_id": str(uuid.uuid4()), "request_key": f"invalid-{uuid.uuid4()}"})
        assert (refused.status_code, refused.json()["code"]) == (409, reason)
        assert counts(client) == before_counts
        assert rows(client, "select count(*) n from usage_local.usage_reservations")[0]["n"] == reservations
        assert client.get("/v1/research/budget", headers=owner_a).json() == before_budget
        worker(client, runtime).run_job(uuid.UUID(queued))
        saved = job_view(client, owner_a, queued)
        assert (saved["state"], saved["terminal_reason"]) == ("UNAVAILABLE", reason)
        assert saved["budget"]["released"]["provider_requests"] == runtime.release.history.limits["provider_requests"]
        assert saved["budget"]["unknown_liability"] == {"provider_requests": 0, "compute_seconds": 0}
        assert "ATTEMPT_STARTED" not in [event["kind"] for event in saved["events"]]
    assert effects.reads == effects.requests == []


def test_authored_actual_journey_fixture_qualifies_and_binds_without_runtime_effects(monkeypatch):
    """Pure: native recorded clients only; no runtime, credentials, API, DB or socket."""
    import json
    from edge_os_api.research import native_history_collection
    from edge_os_api.research_history.qualification_engine import epoch

    history, source = authored_journey_history()
    _check_history("ACTUAL", history)
    from types import SimpleNamespace
    from edge_os_api.core.research import operating_release
    from edge_os_api.core.research.released_source_runtime import history_source, open_released_runtime
    from edge_os_api.research_history.http_clients import StdlibHttpTransport
    release_definition = operating_release.OperatingRelease("authored-journey-actual/2", "ACTUAL", history=history)
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {
        release_definition.release_id: operating_release.release_sha256(release_definition)})

    class NoCredentials:
        def read(self, slot):
            raise AssertionError("pure recorded-client qualification must not read credentials")

    runtime = open_released_runtime(SimpleNamespace(env="test"), release_definition,
        credentials=NoCredentials(), http_transport=StdlibHttpTransport)
    source.update(history_source(runtime))
    assert source["profile"]["evidence_class"] == "REAL_SOURCE"
    collection, normalized, transport = native_history_collection.collect_native(
        source, history.limits, None, lambda: False, lambda: source["profile"]["dataset"]["collection"]["collected_at_utc"])
    assert collection["status"] == "COMPLETE" and normalized["qualification"]["overall"] == "QUALIFIED"
    assert normalized["bound_profile"]["dataset"]["dataset_revision"]["basis"] == "PAGE_DIGESTS"
    from edge_os_api.research_history.qualification_engine import BindingNotEmittable, qualify
    from edge_os_api.research_history.history_normalizer import project_binding
    for basis in ("NONE", "PRIVATE_NOT_PORTABLE"):
        nonportable = copy.deepcopy(normalized["bound_profile"])
        nonportable["dataset"]["pages"] = []
        nonportable["dataset"]["dataset_revision"] = {"basis": basis, "manifest_sha256": None,
                                                     "page_count": 0, "row_count": None}
        refusal = qualify(nonportable, normalized["observations"])
        assert refusal["overall"] in {"LIMITED", "UNRESOLVED"}
        assert "COVERAGE_PROOF_NOT_PORTABLE" in json.dumps(refusal)
        with pytest.raises(BindingNotEmittable):
            project_binding(nonportable, refusal)
    owner, dataset, job, attempt, declaration = [uuid.UUID(int=n) for n in range(1, 6)]
    content = history_dataset.dataset_content(dataset_id=dataset, owner_id=owner, declaration_id=declaration,
        job_id=job, attempt_id=attempt, source=source, collection=collection, normalized=normalized, transport=transport)
    release = {"release_id": "authored-journey-actual/2", "sha256": "a" * 64, "kind": "ACTUAL"}
    content.update(operating_release=release, evidence_class="PROVIDER_ACTUAL")
    anchor = history.provider_facts["forward_history_binding"]
    expected = {"owner_id": str(owner), "dataset_id": str(dataset), "source_id": history.source_id,
                "release": release, "job_id": str(job), "attempt_id": str(attempt), **binding.requirement(anchor)}
    from types import SimpleNamespace
    row = SimpleNamespace(owner_id=owner, dataset_id=dataset, content=content,
                          content_sha256=sha256_hex(content), raw_records=normalized["raw_records"])
    report, result, reason = binding.run_checker(anchor["handoff_json"], row, expected,
                                                provenance_text=anchor["provenance_json"])
    assert (result, reason) == ("PASS", None), json.dumps(report, sort_keys=True)
    bucket = content["buckets"][2]
    assert epoch(bucket["available_at"]) == epoch(bucket["bucket_end"]) + 301
    assert content["binding_view"]["quote_asset"] == next(token["address"] for token in history.profile["pool_tokens"]
                                                         if token["role"] == "QUOTE")
    assert bucket["status"] == "COMPLETE_OCCUPIED" and bucket["close"] is not None
    # Check the exact existing replay engine's timing rule in memory; this is not API/DB evidence.
    from edge_os_api.records import contract_adapter
    from edge_os_api.replay import delayed_history_profile, history_inputs, simulator
    from edge_os_api.strategies import compiler
    from research_flows import OWN_EXIT, rising, volume_above
    values = {name: copy.deepcopy(contract_adapter.FIXTURE_STRATEGY[name])
              for name in contract_adapter.CREATE_STRATEGY_FIELDS if name != "restrictions"}
    values["market"] = content["strategy_market"]
    values["entry"] = {"op": "and", "args": [rising(1), volume_above("101", values["market"]["quote_unit"])]}
    values["exit"] = copy.deepcopy(OWN_EXIT)
    values["invalidation"] = {"state": "NOT_REQUESTED", "source_ref": "authored-actual-journey-test"}
    values["data_inputs"] = ["price", "quote_volume"]
    values["sizing"]["unit"] = values["market"]["quote_unit"]
    strategy = compiler.build_strategy("authored-actual-journey-test", values)
    end = dt.datetime(2026, 9, 25, 10, 25, tzinfo=dt.timezone.utc)
    dataset = history_inputs.replay_dataset(row, end)
    essential = {"schema_version": simulator.ESSENTIAL_VERSION, "strategy_revision": "authored-revision",
                 "run_configuration_id": "authored-config", "dataset_revision": str(dataset.revision_id),
                 "market_binding_id": dataset.market_binding_id, "fields": {
                     "entry": {"state": "BOUND", "essential_dependencies": [
                         {"series": "price", "offset_buckets": 0}, {"series": "price", "offset_buckets": -1},
                         {"series": "quote_volume", "offset_buckets": 0}]},
                     "exit": {"state": "BOUND", "essential_dependencies": [
                         {"series": "price", "offset_buckets": 0}, {"series": "price", "offset_buckets": -2}]}}}
    replay_input = simulator.ReplayInput(strategy_revision_id="authored-revision", run_configuration_id="authored-config",
        dataset=dataset, essential_evidence=essential, window_start=end-dt.timedelta(seconds=300), window_end=end,
        initial_cash_quote="1000", initial_base_amount="0", initial_basis_quote="0")
    replay = simulator.run_spot_replay(strategy, replay_input, timing_profile=delayed_history_profile.PROFILE_VERSION)
    decisions = [item for item in replay.events if item["kind"] == "DECISION"]
    assert len(decisions) == 1
    assert {"LATE_INPUT", "FUTURE_INFORMATION:2"} <= set(decisions[0]["entry"]["eligibility_reasons"])
    assert not decisions[0]["entry"]["eligible"] and not replay.trades
    assert not any(item.get("status") in {"BUY_FILLED", "SELL_FILLED"} for item in replay.events)


def authored_journey_history():
    """Complete AUTHORED TEST /2 graph over the existing native recording; never recorder/provider proof."""
    import json
    from dataclasses import replace
    import forward_history_stand_in as bound
    from edge_os_api.core.research.operating_release import BINDING_FACT
    from edge_os_api.research_history.qualification_engine import epoch, iso_utc
    from test_actual_binding_admission import authored_actual_history
    from tests.test_history_payload_binding_v2 import reanchor

    source = bound.recording()
    history = authored_actual_history(replace(bound.bound_release(nansen=False).history,
        envio_endpoint="https://hypersync.example.com", quicknode_host="quicknode.example.com"))
    anchor = history.provider_facts[BINDING_FACT]
    h = json.loads(anchor["handoff_json"])
    projection = binding.checker()  # reuse the accepted canonicalization; do not relabel a legacy handoff
    page = source["envio_pages"][0]
    h["headers"] = [{"number": projection.quantity(block["number"], "number"),
                     "timestamp": projection.quantity(block["timestamp"], "timestamp"), "hash": block["hash"]}
                    for block in page["data"]["blocks"] if block.get("hash")]
    timestamps = {header["number"]: header["timestamp"] for header in h["headers"]}
    projected = [projection.project_log(log, block_timestamp=timestamps[log["block_number"]])
                 for log in page["data"]["logs"]]
    h["scan_log_count"] = len(projected)
    p = json.loads(anchor["provenance_json"])
    r = json.loads(p["receipts_json"])
    for bucket in h["buckets"]:
        members = projection.bucket_members(projected, epoch(bucket["start_utc"]), epoch(bucket["end_utc"]))
        bucket.update(record_count=len(members), payload_sha256=projection.payload_sha256(members))
    # One second beyond the fixed300s decision delay: a reproducible no-fill timing reason.
    late = h["buckets"][2]
    received = epoch(late["end_utc"]) + 301
    late.update(received_at_utc=iso_utc(received), received_at_utc_us=received * 1000000)
    next(reply for reply in h["p3_replies"] if reply["call_id"] == late["reply_id"])["received_utc_us"] = received * 1000000
    next(receipt for receipt in r["receipts"] if receipt["call_id"] == late["reply_id"])["received_at_utc_us"] = received * 1000000
    for reply in h["p3_replies"]:
        reply["log_count"] = sum(reply["from_block"] <= log["block_number"] < reply["next_block"] for log in projected)
    h["delivery_records"] = {bucket["start_utc"]: bucket["received_at_utc"] for bucket in h["buckets"]}
    anchor, _ = reanchor(anchor, {}, handoff=h, receipts=r)
    history = replace(history, provider_facts={**history.provider_facts, BINDING_FACT: anchor,
                                              "delivery_records": h["delivery_records"]})
    source.update(source_id=history.source_id, profile=history.profile, provider_facts=history.provider_facts)
    return history, source


def test_authored_actual_api_worker_adoption_delayed_replay_reopen_and_tamper(settings, owner_a, owner_b,
                                                                            monkeypatch):
    """DB boundary only. AUTHORED TEST provider replies exercise ACTUAL code; they prove no real provenance."""
    import http.client
    import json
    from fastapi.testclient import TestClient
    import forward_history_stand_in as bound
    import operating_release_stand_in as stand_in
    from edge_os_api.core.research import operating_release
    from edge_os_api.core.research.released_source_runtime import open_released_runtime
    from edge_os_api.main import create_app
    from edge_os_api.replay import delayed_history_profile
    from edge_os_api.research_history.http_clients import StdlibHttpTransport
    from edge_os_api.research_history.qualification_engine import epoch
    from flows import publish
    from test_saved_history_payload_binding import (
        adopted_revision, adopted_revision_foreign, bound_events, collected, counts, job_view, replay_body, rows, worker,
    )
    from tests.test_forward_history_transport_receipts import FixtureConnection

    history, source = authored_journey_history()
    release = operating_release.OperatingRelease("authored-journey-actual/2", "ACTUAL", history=history)
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {
        release.release_id: operating_release.release_sha256(release)})  # test-owned exact approval only
    creds = stand_in.credentials(quicknode=stand_in.quicknode_url(history.quicknode_host, "https"))
    peer = bound.BoundRecordingStandIn()
    peer.replies = stand_in.StandInReplies(source)
    peer.envio_url = history.envio_endpoint + "/query"
    peer.quicknode_url = stand_in.quicknode_url(history.quicknode_host, "https")
    # The existing in-memory connection preserves the real stdlib/HTTP-client path without opening a socket.
    monkeypatch.setattr(http.client, "HTTPSConnection", lambda host, port, timeout:
                        FixtureConnection(peer.transport(), "https", host, port))
    runtime = open_released_runtime(settings, release, credentials=creds, http_transport=StdlibHttpTransport)
    anchor = history.provider_facts["forward_history_binding"]
    assert creds.reads == peer.requests == []
    with TestClient(create_app(settings, research_runtime=runtime)) as client:
        job_id, job = collected(client, owner_a, runtime)
        dataset_id = job["dataset"]["dataset_id"]
        events = bound_events(client, job_id)
        assert len(events) == 1
        event = events[0]["content"]
        assert (event["result"], event["reason"], event["checker"]) == ("PASS", None, binding.checker_identity(2))
        assert event["handoff_json"] == anchor["handoff_json"]
        assert event["provenance_json"] == anchor["provenance_json"]
        single = client.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()
        content = single["content"]
        assert (content["verdict"]["overall"], content["binding_state"], content["operating_release"]["kind"]) == (
            "QUALIFIED", "QUALIFIED_BINDING", "ACTUAL")
        assert content["evidence_class"] == "PROVIDER_ACTUAL"
        assert content["profile_evidence_class"] == "REAL_SOURCE"
        assert single["payload_binding"]["status"] == "PASS"
        assert content["payload_binding_requirement"] == binding.requirement(anchor)
        assert content["binding_view"]["quote_asset"] == next(token["address"] for token in history.profile["pool_tokens"]
                                                             if token["role"] == "QUOTE")
        late = content["buckets"][2]
        assert epoch(late["available_at"]) == epoch(late["bucket_end"]) + 301
        saved_before = (rows(client, "select owner_id, content, content_sha256, raw_records from "
                             "research_local.history_datasets where dataset_id=:id", id=dataset_id), events)
        (bundle, parent), adopted = adopted_revision(client, owner_a, dataset_id)
        assert adopted.status_code == 201, adopted.text
        lineage = binding.lineage(single["payload_binding"])
        assert adopted.json()["adoption"]["payload_binding"] == lineage
        published, _ = publish(client, owner_a, adopted.json()["bundle"], parent=parent)
        assert published.status_code == 201, published.text
        request = replay_body(bundle, published.json()["revision_id"], dataset_id)
        request.update(window_start="2026-09-25T10:20:00Z", window_end="2026-09-25T10:25:00Z",
                       timing_profile=delayed_history_profile.PROFILE_VERSION)
        response = client.post("/v1/spot-replays", headers=owner_a, json=request)
        assert response.status_code == 201, response.text
        replay = response.json()
        inputs, result = replay["content"]["inputs"], replay["content"]["result"]
        assert inputs["history_input"]["payload_binding"] == lineage
        assert inputs["history_input"]["source_evidence_class"] == "PROVIDER_ACTUAL"
        assert inputs["history_input"]["profile_evidence_class"] == "REAL_SOURCE"
        assert result["evidence_class"] == "PROVIDER_ACTUAL"
        assert inputs["timing_policy"] == dict(delayed_history_profile.POLICY)
        assert inputs["timing_policy"]["decision_delay_seconds"] == 300
        assert result["status"] == "COMPLETE", result
        decisions = [item for item in result["events"] if item["kind"] == "DECISION"]
        assert len(decisions) == 1
        assert dt.datetime.fromisoformat(decisions[0]["at"].replace("Z", "+00:00")) == (
            dt.datetime(2026, 9, 25, 10, 20, tzinfo=dt.timezone.utc))
        assert dt.datetime.fromisoformat(decisions[0]["source_bucket_end"].replace("Z", "+00:00")) == (
            dt.datetime.fromisoformat(late["bucket_end"].replace("Z", "+00:00")))
        assert decisions[0]["entry"]["eligible"] is False
        assert {"LATE_INPUT", "FUTURE_INFORMATION:2"} <= set(decisions[0]["entry"]["eligibility_reasons"])
        assert result["trades"] == []
        assert not any(item.get("status") in {"BUY_FILLED", "SELL_FILLED"} for item in result["events"])
        assert "Hypothetical" in replay["content"]["notice"]
        assert not any(secret in json.dumps(job) + json.dumps(single) + json.dumps(replay) for secret in stand_in.SENTINELS)
        assert rows(client, "select owner_id, content, content_sha256, raw_records from "
                    "research_local.history_datasets where dataset_id=:id", id=dataset_id) == saved_before[0]
        assert bound_events(client, job_id) == saved_before[1]
        assert len(peer.requests) == bound.provider_requests(source) == 7
        assert creds.reads == [stand_in.ENVIO_SLOT, stand_in.QUICKNODE_SLOT]
        # Event immutability is checked through the application's actual persisted row.
        with client.app.state.session_factory() as session:
            immutable = session.execute(select(InvestigationEventRow).where(
                InvestigationEventRow.job_id == uuid.UUID(job_id),
                InvestigationEventRow.kind == binding.EVENT_KIND)).scalar_one()
            immutable.content = {**immutable.content, "result": "MISMATCH"}
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        with client.app.state.session_factory() as session:
            immutable_dataset = binding._stored_row(session, uuid.UUID(content["owner_id"]), uuid.UUID(dataset_id))
            immutable_dataset.content = {**immutable_dataset.content, "status": "PARTIAL"}
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        original_engine = client.app.state.engine
        reads, requests = list(creds.reads), list(peer.requests)

    # New app/engine/session factory and worker object, no live release registry needed for saved consumers.
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {})
    with TestClient(create_app(settings)) as reopened:
        assert reopened.app.state.engine is not original_engine
        assert reopened.get(f"/v1/spot-replays/{replay['replay_id']}", headers=owner_a).json() == replay
        reopened_dataset = reopened.get(f"/v1/research/history-datasets/{dataset_id}", headers=owner_a).json()
        assert reopened_dataset == single
        assert job_view(reopened, owner_a, job_id) == job
        worker(reopened, None).run_job(uuid.UUID(job_id))  # terminal job must not recollect after application reopen
        assert job_view(reopened, owner_a, job_id) == job
        assert bound_events(reopened, job_id) == saved_before[1]
        assert counts(reopened)["spot_replay_runs"] >= 1
        for route in (f"/v1/research/history-datasets/{dataset_id}",
                      f"/v1/research/investigation-jobs/{job_id}", f"/v1/spot-replays/{replay['replay_id']}"):
            assert reopened.get(route, headers=owner_b).status_code == 404
        (foreign_bundle, foreign_parent), foreign_adoption = adopted_revision_foreign(reopened, owner_b, dataset_id)
        assert foreign_adoption.status_code == 404
        foreign_request = replay_body(foreign_bundle, foreign_parent, dataset_id)
        foreign_request.update(window_start=request["window_start"], window_end=request["window_end"],
                               timing_profile=request["timing_profile"])
        assert reopened.post("/v1/spot-replays", headers=owner_b, json=foreign_request).status_code == 404
        # A new replay/adoption rechecks saved raw rows rather than accepting the old PASS or fresh outer hashes.
        with reopened.app.state.session_factory() as session:
            row = binding._stored_row(session, uuid.UUID(content["owner_id"]), uuid.UUID(dataset_id))
            raw, changed = copy.deepcopy(row.raw_records), copy.deepcopy(row.content)
            raw[0]["data"] = "0x" + "00" * 128
            changed["raw_evidence"]["sha256"] = raw_sha256(raw)
            session.execute(text("ALTER TABLE research_local.history_datasets DISABLE TRIGGER history_datasets_immutable"))
            try:
                row.raw_records, row.content, row.content_sha256 = raw, changed, sha256_hex(changed)
                session.flush()
            finally:
                session.execute(text("ALTER TABLE research_local.history_datasets ENABLE TRIGGER history_datasets_immutable"))
            session.commit()
        before = counts(reopened)
        (_, _), refused_adoption = adopted_revision(reopened, owner_a, dataset_id)
        assert (refused_adoption.status_code, refused_adoption.json()["code"]) == (409, "payload_binding_mismatch")
        changed_request = {**request, "idempotency_key": f"tampered-{uuid.uuid4()}",
                           "run_configuration_id": f"tampered-{uuid.uuid4()}"}
        refused_replay = reopened.post("/v1/spot-replays", headers=owner_a, json=changed_request)
        assert (refused_replay.status_code, refused_replay.json()["code"]) == (409, "payload_binding_mismatch")
        assert counts(reopened)["spot_replay_runs"] == before["spot_replay_runs"]
        assert counts(reopened)["spot_replay_configurations"] == before["spot_replay_configurations"]
        assert bound_events(reopened, job_id) == saved_before[1]
        assert reopened.get(f"/v1/spot-replays/{replay['replay_id']}", headers=owner_a).json() == replay
    assert creds.reads == reads and peer.requests == requests


@pytest.mark.parametrize("profile", ["REAL_SOURCE", "PROVIDER_ACTUAL"])
@pytest.mark.parametrize("release,outer", [(None, "PROVIDER_ACTUAL"), ({"kind": "STAND_IN"}, "PROVIDER_ACTUAL"),
                                           ({"kind": "ACTUAL"}, "RELEASE_STAND_IN_RESPONSE")])
def test_actual_replay_profile_requires_consistent_saved_source_and_release(profile, release, outer):
    from types import SimpleNamespace
    from edge_os_api.replay.history_inputs import replay_dataset
    content = {"profile_evidence_class": profile, "evidence_class": outer, "operating_release": release,
               "market_binding_id": "authored-market", "buckets": [], "verdict": {"overall": "QUALIFIED"},
               "status": "COMPLETE", "coverage": {"covers_requested_scan": True}}
    with pytest.raises(AppError) as caught:
        replay_dataset(SimpleNamespace(content=content, dataset_id=uuid.UUID(int=1)), dt.datetime.now(dt.timezone.utc))
    assert caught.value.code == "evidence_class_inconsistent"


@pytest.mark.parametrize("profile,outer,kind,expected", [
    ("REAL_SOURCE", "PROVIDER_ACTUAL", "ACTUAL", "PROVIDER_ACTUAL"),
    ("PROVIDER_ACTUAL", "PROVIDER_ACTUAL", "ACTUAL", "PROVIDER_ACTUAL"),
    ("SYNTHETIC_FIXTURE", "RELEASE_STAND_IN_RESPONSE", "STAND_IN", "SYNTHETIC_FIXTURE"),
])
def test_replay_profile_mapping_keeps_saved_classes_and_fixture_behavior(profile, outer, kind, expected):
    from types import SimpleNamespace
    from edge_os_api.replay.history_inputs import replay_dataset
    content = {"profile_evidence_class": profile, "evidence_class": outer, "operating_release": {"kind": kind},
               "market_binding_id": "authored-market", "buckets": [], "verdict": {"overall": "QUALIFIED"},
               "status": "COMPLETE", "coverage": {"covers_requested_scan": True}}
    before = copy.deepcopy(content)
    result = replay_dataset(SimpleNamespace(content=content, dataset_id=uuid.UUID(int=1)), dt.datetime.now(dt.timezone.utc))
    assert result.evidence_class == expected
    assert content == before
