"""Authority in the connected journey: stops, removal, expiry, stale quotes, unavailable inputs, contention.

Every denial is checked against the independent fixture effect record: a denied action reaches no provider.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

import pytest

import financial_flows as ff
from edge_os_api.core.provider_ports import ProviderUnavailable, QuoteResult


@pytest.fixture
def journey(settings, tmp_path):
    with ff.fixture_client(settings, tmp_path / "effects.jsonl") as client:
        yield client


def hold_before_submission(client):
    """Run the job to ENQUEUED and stop there, so a control can land between admission and submission."""
    connected = client.app.state.financial.connected
    original = connected._submit
    connected._submit = lambda *args, **kwargs: None
    return lambda: setattr(connected, "_submit", original)


def removal(client, headers, agent):
    response = client.post(f"/v1/agents/{agent}/removal", headers=headers,
                           json={"request_key": f"remove-{agent}", "reason": "owner removes the agent"})
    assert response.status_code == 200, response.text
    return response.json()


def test_stop_before_admission_denies_without_reservation_or_effect(journey, owner_a):
    agent = "auth-stop-first"
    ff.ready_for_action(journey, owner_a, agent)
    stop = journey.post(f"/v1/agents/{agent}/stops", headers=owner_a,
                        json={"mode": "STOP_NEW_ENTRIES", "scope": "AGENT_WALLET_NETWORK"})
    assert stop.status_code == 200, stop.text
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert (job["outcome"], job["reason"]) == ("ADMISSION_DENIED", "STOPPED_NEW_ENTRIES")
    action = journey.get(f"/v1/actions/{job['action_id']}", headers=owner_a).json()
    assert action["reservations"] == []
    assert ff.effects(journey) == []


@pytest.mark.parametrize("control", ["stop", "removal"])
def test_control_recorded_after_admission_denies_at_submission(journey, owner_a, control):
    agent = f"auth-late-{control}"
    ff.ready_for_action(journey, owner_a, agent)
    release = hold_before_submission(journey)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert job["state"] == "ENQUEUED"
    release()
    if control == "stop":
        journey.post(f"/v1/agents/{agent}/stops", headers=owner_a,
                     json={"mode": "HALT_ALL_SWAPS", "scope": "AGENT_WALLET_NETWORK"})
        expected = "STOPPED_HALT_ALL_SWAPS"
    else:
        assert removal(journey, owner_a, agent)["state"] == "REQUESTED"
        expected = "REMOVAL_REQUESTED"
    done = ff.run_job(journey, job)
    assert (done["outcome"], done["reason"]) == ("REVALIDATION_DENIED", expected)
    assert ff.effects(journey) == []
    action = journey.get(f"/v1/actions/{done['action_id']}", headers=owner_a).json()
    assert action["admission"][0]["status"] == "ADMITTED"  # reservations stay until explicitly released
    assert all(attempt["state"] != "IN_FLIGHT" for attempt in action["attempts"])


def test_requested_removal_denies_new_admission(journey, owner_a):
    agent = "auth-removal-first"
    ff.ready_for_action(journey, owner_a, agent)
    removal(journey, owner_a, agent)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert (job["outcome"], job["reason"]) == ("ADMISSION_DENIED", "REMOVAL_REQUESTED")
    assert ff.effects(journey) == []


def test_removal_after_submission_ownership_never_undoes_the_original_action(journey, owner_a):
    agent = "auth-removal-inflight"
    ff.ready_for_action(journey, owner_a, agent)
    ports = journey.app.state.financial.ports
    real_transport = ports.transport

    def transport_requesting_removal(**kwargs):
        transport = real_transport(**kwargs)
        real_submit = transport.submit

        def submit(prepared):
            removal(journey, owner_a, agent)  # commits after ownership, while the effect may be in flight
            return real_submit(prepared)
        transport.submit = submit
        return transport

    ports.transport = transport_requesting_removal
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert job["outcome"] == "SUBMITTED_CONFIRMED"
    assert len(ff.effects(journey)) == 1
    states = journey.get(f"/v1/agents/{agent}/removal", headers=owner_a).json()["removals"]
    assert [item["state"] for item in states] == ["REQUESTED"]
    confirmed = journey.post(f"/v1/agents/{agent}/removal/reconcile", headers=owner_a)
    assert confirmed.json()["state"] == "CONFIRMED"
    # Owner access and the residual position stay visible after confirmed removal.
    overview = journey.get(f"/v1/agents/{agent}/actions", headers=owner_a).json()
    assert overview["positions"][0]["inventory_raw"] == ff.ENTRY_BASE_OUTPUT


def test_expired_consent_leaves_the_action_unavailable(journey, owner_a):
    agent = "auth-expired"
    ff.confirmed_agent(journey, owner_a, agent)
    declaration = ff.funded(journey, owner_a, agent)
    expiry = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ff.adopted(journey, owner_a, agent, declaration, expiry=expiry)
    job = ff.schedule(journey, owner_a, agent).json()
    connected = journey.app.state.financial.connected
    original = connected._clock
    connected._clock = lambda: original() + dt.timedelta(hours=1)
    try:
        done = ff.run_job(journey, job)
    finally:
        connected._clock = original
    # The decision is saved first; authority is checked before any intent exists.
    assert (done["state"], done["reason"]) == ("UNAVAILABLE", "CONSENT_EXPIRED")
    assert ff.effects(journey) == []


def test_changed_quote_before_submission_denies_without_repricing(journey, owner_a):
    agent = "auth-quote"
    ff.ready_for_action(journey, owner_a, agent)
    release = hold_before_submission(journey)
    job = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    release()
    quotes = journey.app.state.financial.ports.quotes
    real_quote = quotes.quote

    def moved(request):
        result = real_quote(request)
        output = result.output.model_copy(update={"raw": str(int(result.output.raw) // 2)})
        return QuoteResult(output=output, observed_at=result.observed_at, expires_at=result.expires_at,
                           source_ref=result.source_ref)
    quotes.quote = moved
    done = ff.run_job(journey, job)
    assert (done["outcome"], done["reason"]) == ("REVALIDATION_DENIED", "QUOTE_CHANGED")
    action = journey.get(f"/v1/actions/{done['action_id']}", headers=owner_a).json()
    assert action["payload"]["quantity"]["raw"] == ff.ENTRY_BASE_OUTPUT  # the saved payload is never repriced
    assert ff.effects(journey) == []


def test_unavailable_holdings_keep_the_action_unavailable(journey, owner_a):
    agent = "auth-holdings"
    ff.ready_for_action(journey, owner_a, agent)

    def unavailable(**_):
        raise ProviderUnavailable("holdings")
    journey.app.state.financial.ports.holdings.observe = unavailable
    done = ff.run_job(journey, ff.schedule(journey, owner_a, agent).json())
    assert (done["state"], done["reason"]) == ("UNAVAILABLE", "HOLDINGS_UNAVAILABLE")
    assert ff.effects(journey) == []


def test_concurrent_runs_and_schedules_create_one_job_and_one_effect(journey, owner_a):
    agent = "auth-concurrent"
    ff.ready_for_action(journey, owner_a, agent)
    barrier = threading.Barrier(4)
    scheduled: list = [None] * 4

    def schedule(index):
        barrier.wait()
        scheduled[index] = ff.schedule(journey, owner_a, agent, f"key-{index}").json()["job_id"]
    threads = [threading.Thread(target=schedule, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(scheduled)) == 1
    job_id = uuid.UUID(scheduled[0])
    connected = journey.app.state.financial.connected
    results: list = [None] * 4
    barrier = threading.Barrier(4)

    def run(index):
        barrier.wait()
        results[index] = connected.run_job(job_id)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert any(result is not None for result in results)
    assert len(ff.effects(journey)) == 1
    final = connected.run_job(job_id)
    assert final["outcome"] == "SUBMITTED_CONFIRMED"


def test_unavailable_execution_mode_runs_nothing(settings, owner_a):
    unavailable = settings.model_copy(update={"wallet_provider": "fixture", "execution_mode": "unavailable"})
    from fastapi.testclient import TestClient
    from edge_os_api.main import create_app
    with TestClient(create_app(unavailable)) as client:
        agent = "auth-unavailable"
        ff.confirmed_agent(client, owner_a, agent)
        declaration = ff.funded(client, owner_a, agent)
        funding = client.get(f"/v1/agents/{agent}/funding", headers=owner_a).json()
        assert funding["current_holdings"]["state"] == "UNAVAILABLE"
        assert all(flow["state"] == "PENDING" for flow in funding["flows"])  # nothing credited without a port
        adopt = ff.adopted(client, owner_a, agent, declaration)
        assert adopt["status"] == "INACTIVE"
        assert adopt["activation"] == {"state": "UNAVAILABLE", "reason": "ACTIVATION_UNAVAILABLE",
                                       "evidence_class": None}
        job = ff.run_job(client, ff.schedule(client, owner_a, agent).json())
        assert (job["state"], job["reason"]) == ("UNAVAILABLE", "OBSERVATIONS_UNAVAILABLE")
        assert client.get("/v1/financial/provider", headers=owner_a).json()["mode"] == "unavailable"
