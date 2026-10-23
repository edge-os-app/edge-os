"""The worker passes the bound approve -> swap -> revoke plan into its clients and transport.

The clients and HTTP boundaries here are local doubles. The plan comes from one synthetic release binding.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import uuid
from types import SimpleNamespace

import pytest
from eth_utils import keccak

from edge_os_api.core.provider_ports import ControlledRuntime
from edge_os_api.execution.original_transaction import OriginalContext, TradeSteps
from edge_os_api.execution.privy_signer import PrivySignerClient
from edge_os_api.execution.transport import PreparedSubmission
from edge_os_api.execution.worker import ConnectedExecution
from edge_os_api.research_history.http_clients.http_transport import HttpResponse
import edge_os_api.execution.worker as worker_module

from execution.test_approve_swap_revoke import Chain, Signer, bound_steps, envelope, multi, run, steps
from execution.test_privy_signer import BUY_TOKEN, NOW, PUBLISHED_WALLET, SELL_TOKEN, WALLET_ID

PACKET_AGENT = "agent-1"
PACKET_OWNER = "owner-1"


class FakeAmount:
    def __init__(self, raw: str, asset_id: str = "monad:143/native", decimals: int = 18) -> None:
        self.raw, self.asset_id, self.decimals = raw, asset_id, decimals

    def as_int(self) -> int:
        return int(self.raw)


class FakeControls:
    def denial_reasons(self, *_args, **_kwargs) -> list[str]:
        return []


def agent(quote_decimals: int) -> SimpleNamespace:
    return SimpleNamespace(
        owner_id=PACKET_OWNER, agent_id=PACKET_AGENT, wallet_id=WALLET_ID, network_id="monad:143",
        network_number=143,
        quote=SimpleNamespace(asset_id=f"monad:143/{SELL_TOKEN}", decimals=quote_decimals),
        base=SimpleNamespace(asset_id=f"monad:143/{BUY_TOKEN}", decimals=18),
        gas=SimpleNamespace(asset_id="monad:143/native", decimals=18))


def job() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1", owner_id=PACKET_OWNER, agent_id=PACKET_AGENT, wallet_id=WALLET_ID,
        network_id="monad:143", strategy_id="strategy-a", publication_revision_id="publication-a",
        execution_revision_id="execution-a", content_hash="sha256:" + "a" * 64,
        consent_adoption_id="consent-a", consent_hash="sha256:" + "b" * 64,
        decision_slot=NOW.replace(minute=15), action_id="action-1")


def intent() -> SimpleNamespace:
    return SimpleNamespace(
        action_id="action-1", operation="ENTRY", payload_hash="sha256:payload", policy_binding="policy-a",
        position_id="position-1", agent_id=PACKET_AGENT,
        payload={"input": {"quote_input": {"asset_id": f"monad:143/{SELL_TOKEN}", "raw": "100000000",
                                           "decimals": 18}},
                 "quantity": {"asset_id": f"monad:143/{BUY_TOKEN}", "raw": str(50 * 10**18),
                              "decimals": 18}})


def approval() -> SimpleNamespace:
    return SimpleNamespace(
        per_action_gas=FakeAmount(str(10**18)), quote_allowance=FakeAmount("100000000"),
        per_exit_gas=FakeAmount(str(10**18)), base_allowance=FakeAmount(str(50 * 10**18)),
        expires_at="2026-01-01T01:00:00+00:00")


@contextlib.contextmanager
def no_session():
    yield None


def prepare_worker(monkeypatch, runtime: ControlledRuntime, clients):
    """A worker whose identity reads are authored; its one controlled runtime supplies the binding."""
    monkeypatch.setattr(worker_module, "wallet_address", lambda *_args, **_kwargs: PUBLISHED_WALLET)
    monkeypatch.setattr(worker_module, "resolve_agent", lambda *_args, **_kwargs: agent(18))
    monkeypatch.setattr(worker_module, "adopted_consent", lambda *_args, **_kwargs: SimpleNamespace(
        adoption_id="consent-a", consent_hash="sha256:" + "b" * 64))
    monkeypatch.setattr(worker_module, "saved_release_identity",
                        lambda *_args, **_kwargs: runtime.binding.identity())
    monkeypatch.setattr(worker_module, "SubmissionControls", lambda *_args: FakeControls())
    captured: dict = {}

    def mounted(factory, context, controls, *, role, steps=None):
        captured.update(steps=steps, role=role)
        return clients

    object.__setattr__(runtime, "clients", mounted)
    ports = SimpleNamespace(controlled={PACKET_AGENT: runtime}, role="worker")
    services = SimpleNamespace(stops=object(), removals=object())
    connected = ConnectedExecution(no_session, services, ports, qualification="controlled",
                                   clock=lambda: NOW)
    transport = connected._original_transport(job(), agent(18), approval(), intent(), None,
                                              runtime.profile(), runtime=runtime)
    return transport, captured


def runtime_for(binding, approvals, plan: TradeSteps | None) -> ControlledRuntime:
    return ControlledRuntime(binding=binding, http=object(), clock=lambda: NOW,
                             synthetic_bindings=approvals, steps=plan)


def submitted(stages: list) -> PreparedSubmission:
    return PreparedSubmission(action_id="action-1", owner_id=PACKET_OWNER, wallet_id=WALLET_ID,
                              network_id="monad:143", operation="ENTRY", payload_hash="sha256:payload",
                              attempt_id="attempt-0001")


def test_the_worker_passes_the_bound_plan_into_the_clients_and_runs_each_step_once(tmp_path, monkeypatch):
    signer, chain = Signer(), Chain()
    base, _, _ = multi(tmp_path, signer=signer, chain=chain)
    binding, approvals = bound_steps(base)
    plan = steps()
    transport, captured = prepare_worker(monkeypatch, runtime_for(binding, approvals, plan),
                                         dataclasses.replace(base._clients, signer=signer, broadcast=chain))
    stages: list = []
    outcome = transport.submit_original(submitted(stages), lambda stage, values: stages.append((stage, values)))

    assert captured["steps"] is plan
    assert outcome.detail == "BROADCAST_RETURNED;REVOKE:BROADCAST_RETURNED"
    assert signer.calls == [("approve", 5), ("swap", 6), ("revoke", 7)]
    assert chain.sent == [("approve", 5), ("swap", 6), ("revoke", 7)]
    assert envelope(stages)["steps"] == ["approve", "swap", "revoke"]


def test_a_single_action_release_keeps_the_single_swap_path(tmp_path, monkeypatch):
    signer, chain = Signer(), Chain()
    base, _, _ = multi(tmp_path, signer=signer, chain=chain)
    from execution.test_saved_attempt_signing import bound_original

    binding, approvals = bound_original(base)
    plan = None
    transport, captured = prepare_worker(monkeypatch, runtime_for(binding, approvals, plan),
                                         dataclasses.replace(base._clients, signer=signer, broadcast=chain))
    stages: list = []
    outcome = transport.submit_original(submitted(stages), lambda stage, values: stages.append((stage, values)))

    assert captured["steps"] is None
    assert outcome.detail == "BROADCAST_RETURNED"
    assert signer.calls == [("swap", 5)]
    assert chain.sent == [("swap", 5)]
    assert "steps" not in envelope(stages)


def test_a_plan_that_does_not_match_the_bound_release_sends_nothing(tmp_path, monkeypatch):
    signer, chain = Signer(), Chain()
    base, _, _ = multi(tmp_path, signer=signer, chain=chain)
    binding, approvals = bound_steps(base)
    plan = steps()
    object.__setattr__(plan, "order", ("approve", "revoke", "swap"))
    transport, captured = prepare_worker(monkeypatch, runtime_for(binding, approvals, plan),
                                         dataclasses.replace(base._clients, signer=signer, broadcast=chain))
    stages: list = []
    outcome = transport.submit_original(submitted(stages), lambda stage, values: stages.append((stage, values)))

    assert captured["steps"] is plan
    assert (outcome.outcome, outcome.detail) == ("DEFINITELY_UNSENT", "RELEASE_STEPS_MISMATCH")
    assert signer.calls == [] and chain.sent == []
    assert [stage for stage, _ in stages] == ["REFUSED_UNSENT"]


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    """The three reads of `saved` and the one prior-attempt read of `begin_attempt`, in order."""

    def __init__(self, attempt):
        self.attempt, self.claim = attempt, SimpleNamespace(state="ACTIVE", released_at=None)
        self.admission = SimpleNamespace(status="SUBMISSION_UNKNOWN")
        self.results = [attempt, self.claim, self.admission, None]

    def execute(self, _statement):
        return FakeResult(self.results.pop(0))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class BroadcastHttp:
    def __init__(self):
        self.calls = []

    def request(self, **request):
        body = json.loads(request["body"])
        self.calls.append((request["url"], body["method"]))
        if body["method"] == "eth_getTransactionCount":
            result = "0x5"
        else:
            result = "0x" + keccak(bytes.fromhex(body["params"][0][2:])).hex()
        return HttpResponse(200, {}, json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode())


def test_the_real_clients_read_the_step_record_being_signed_and_broadcast(tmp_path):
    owner = str(uuid.uuid4())
    base, recordings, _ = multi(tmp_path, owner_id=owner)
    binding, approvals = bound_steps(base)
    plan = steps()
    from execution.test_approve_swap_revoke import bound_transport
    transport = bound_transport(base, binding, approvals, plan=plan)
    stages: list = []
    outcome = transport.submit_original(
        PreparedSubmission(action_id="action-1", owner_id=owner, wallet_id=WALLET_ID, network_id="monad:143",
                           operation="ENTRY", payload_hash="sha256:payload", attempt_id="attempt-0001"),
        lambda stage, values: stages.append((stage, values)))
    assert outcome.detail == "BROADCAST_RETURNED;REVOKE:BROADCAST_RETURNED", outcome.detail
    saved = envelope(stages)
    attempt_id = uuid.uuid4()
    saved["attempt_id"] = str(attempt_id)
    saved["approve"]["signing_request"]["request_id"] = f"{attempt_id}:approve"
    saved["approve"]["stage"] = "SIGN_REQUESTED"
    saved["stage"] = "APPROVE_SIGN_REQUESTED"

    queue_id = uuid.uuid4()
    attempt = SimpleNamespace(
        state="IN_FLIGHT", transport_id="original-transaction/1", owner_id=owner, queue_id=queue_id,
        attempt_id=attempt_id, agent_id=PACKET_AGENT, action_id="action-1", wallet_id=WALLET_ID,
        network_id="monad:143", payload_hash="sha256:payload", content={"original_transaction": {}})
    session = FakeSession(attempt)
    session.claim.queue_id = queue_id
    runtime = ControlledRuntime(binding=binding, http=BroadcastHttp(), clock=lambda: NOW,
                                quote_token=lambda: "fake_token",
                                signer_access=lambda: {"app_id": "fake_app", "app_secret": "fake_secret",
                                                      "authorize": lambda _payload: "ZmFrZQ=="},
                                synthetic_bindings=approvals, steps=plan)

    def prepared(step_id: str) -> PreparedSubmission:
        return PreparedSubmission(action_id="action-1", owner_id=owner, wallet_id=WALLET_ID,
                                  network_id="monad:143", operation="ENTRY", payload_hash="sha256:payload",
                                  attempt_id=step_id)

    import datetime as dt

    context = OriginalContext(
        owner_id=owner, agent_id=PACKET_AGENT, wallet_id=WALLET_ID, wallet_address=PUBLISHED_WALLET,
        network_id="monad:143", chain_id=143, identity=binding.identity(), action_id="action-1",
        payload_hash="sha256:payload", operation="ENTRY", sell=base._context.sell, buy=base._context.buy,
        gas_asset_id="monad:143/native", gas_cap_raw=10**18, allowance_raw=100000000,
        decision_slot=NOW - dt.timedelta(minutes=1), intent_expires_at=NOW + dt.timedelta(minutes=5),
        mandate_expires_at="2026-01-01T01:00:00+00:00")
    clients = runtime.clients(lambda: session, context, lambda: [], role="worker", steps=plan)

    clients.begin_attempt(prepared(str(attempt_id)))
    attempt.content = {"original_transaction": saved}
    session.results.extend([attempt, session.claim, session.admission])
    signer = clients.signer_for_attempt(prepared(f"{attempt_id}:approve"))
    assert isinstance(signer, PrivySignerClient)

    saved["approve"]["stage"] = "BROADCAST_REQUESTED"
    saved["stage"] = "APPROVE_BROADCAST_REQUESTED"
    session.results.extend([attempt, session.claim, session.admission])
    assert clients.broadcast.call("eth_getTransactionCount", [PUBLISHED_WALLET, "pending"]) == "0x5"
    returned = clients.broadcast.call("eth_sendRawTransaction", [saved["approve"]["signed_bytes"]])
    assert returned == saved["approve"]["transaction_hash"]
