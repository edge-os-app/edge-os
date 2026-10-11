"""The request guard and the spend ledger around ACTUAL pinned Hermes (commit 54bc5e5) in a no-egress container.

The provider is a local controlled fake behind the guard. No real provider, key or network is used. The credential is
a dummy sentinel. Each test runs a real Hermes process, so each takes several seconds and needs Docker.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from authored_cases import load_case, provider_script
from edge_os_api.research.hermes_interpreter import HermesInterpreter, HermesInterpreterConfig, Interpreted, OutputRejected, Unavailable
from edge_os_api.research.interpretation_attempts import AttemptLedger
from guarded_docker_runner import GuardedDockerTurnRunner
from guarded_turn_runner import GuardedTurnRunner
from leak_scan import find_leaks
from provider_guard import GuardPolicy
from spend_ledger import SpendLedger, TokenPrice

SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"
PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))
CONFIG = HermesInterpreterConfig(model="fixture-model/1", route="local-fake-provider", max_output_tokens=4096)
POLICY = GuardPolicy(model="fixture-model/1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
OWNER, INTAKE = "owner-a-7f3c", "intake-5e21"


class Rig:
    """One interpreter over the guarded runner, a durable spend ledger and a private credential file."""

    def __init__(self, image: str, run_id: str, root: Path, name: str, script: dict[str, Any], policy: GuardPolicy = POLICY,
                 cap: Decimal = Decimal("0.20"), timeout_seconds: int = 90) -> None:
        import itertools
        import datetime as dt
        from test_interpretation_attempts import MemoryAttemptStore
        self.root = root / name
        self.root.mkdir(parents=True)
        self.credential = self.root / "private-credential"
        self.credential.write_text(SENTINEL, encoding="utf-8")
        self.credential.chmod(0o400)
        self.evidence = self.root / "evidence"
        self.spend = SpendLedger(self.root / "spend.sqlite", cap_usd=cap, price=PRICE)
        self.docker = GuardedDockerTurnRunner(
            image=image, run_id=run_id, evidence_dir=self.evidence, script_for=lambda turn: script, policy=policy,
            credential_file=self.credential, forbidden=[OWNER, INTAKE], timeout_seconds=timeout_seconds)
        self.runner = GuardedTurnRunner(self.docker, self.spend, policy, scope_for=lambda turn: "case-a")
        self.store = MemoryAttemptStore()
        ids, ticks = itertools.count(1), itertools.count(0)
        self.ledger = AttemptLedger(self.store, new_id=lambda: f"attempt-{next(ids)}", now=lambda: dt.datetime(
            2026, 10, 11, 12, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=next(ticks)))
        self.interpreter = HermesInterpreter(CONFIG, self.runner, self.ledger, monotonic=time.monotonic)

    def run_case(self, name: str):
        return self.interpreter.interpret(OWNER, INTAKE, load_case(name)["intake"])

    def container_result(self, turn: int = 1) -> dict[str, Any]:
        [path] = sorted(self.evidence.glob(f"turn-{turn:02d}-*/output/container-result.json"))
        return json.loads(path.read_text())

    def refusals(self, turn: int = 1) -> list[dict[str, Any]]:
        return [r for r in self.container_result(turn)["guard"]["evidence"] if not r["admitted"]]


def rig(image: str, run_id: str, evidence_root: Path, name: str, case: str, **kwargs) -> Rig:
    return Rig(image, run_id, evidence_root, name, provider_script(load_case(case)["provider"]), **kwargs)


def test_a_valid_turn_is_admitted_once_charged_exactly_and_leaks_nothing(pinned_hermes_image, run_id, evidence_root) -> None:
    session = rig(pinned_hermes_image, run_id, evidence_root, "valid", "concrete-thesis")

    result = session.run_case("concrete-thesis")

    assert isinstance(result, Interpreted)
    guard = session.container_result()["guard"]
    assert (guard["admitted_count"], guard["seen_count"], guard["credential_injected"]) == (1, 1, True)
    [attempt] = session.ledger.history(OWNER, INTAKE)
    assert attempt.settlement.request_count == 1
    assert attempt.settlement.runtime_observed["spend_state"] == "SETTLED"
    assert session.spend.committed_usd() == Decimal("0.0074285")  # 1,423 x 2.00 / 1e6 + 611 x 7.50 / 1e6
    assert find_leaks(session.root, SENTINEL, exclude=[session.credential]) == []


def test_a_cut_off_answer_gets_no_larger_continuation_and_is_charged_once(pinned_hermes_image, run_id, evidence_root) -> None:
    session = rig(pinned_hermes_image, run_id, evidence_root, "truncated", "truncated-cut-off")

    result = session.run_case("truncated-cut-off")

    assert isinstance(result, OutputRejected) and result.rejection.reason_code == "truncated"
    result_file = session.container_result()
    assert result_file["guard"]["admitted_count"] == 1
    assert result_file["hermes"]["request_count"] == 1  # the controlled provider did work for ONE request only
    # actual Hermes asks for a continuation after a cut-off answer; the guard refuses it before the provider sees it
    assert [(r["reason"], r["phase"]) for r in session.refusals()] == [
        ("physical_request_count_exceeded", "truncation_continuation")]
    assert session.spend.committed_usd() == Decimal("0.0074285")
    assert find_leaks(session.root, SENTINEL, exclude=[session.credential]) == []


def test_a_provider_error_is_not_retried_and_keeps_liability_with_the_credential_hidden(pinned_hermes_image, run_id, evidence_root) -> None:
    session = rig(pinned_hermes_image, run_id, evidence_root, "http503", "provider-503")

    result = session.run_case("provider-503")

    assert isinstance(result, Unavailable) and result.reason_code == "provider_failed"
    assert session.container_result()["hermes"]["request_count"] == 1
    assert (session.spend.state("attempt-1"), session.spend.committed_usd()) == ("UNKNOWN", Decimal("0.054848"))
    assert find_leaks(session.root, SENTINEL, exclude=[session.credential]) == []
    assert session.container_result()["guard"]["seen_count"] == 1  # this Hermes build sent no second request


def test_missing_usage_keeps_the_full_reservation(pinned_hermes_image, run_id, evidence_root) -> None:
    session = rig(pinned_hermes_image, run_id, evidence_root, "nousage", "usage-not-reported")

    session.run_case("usage-not-reported")

    assert (session.spend.state("attempt-1"), session.spend.committed_usd()) == ("UNKNOWN", Decimal("0.054848"))


def test_a_hung_provider_is_killed_at_the_deadline_and_stays_liable(pinned_hermes_image, run_id, evidence_root) -> None:
    session = rig(pinned_hermes_image, run_id, evidence_root, "hang", "provider-hang", timeout_seconds=12)

    result = session.run_case("provider-hang")

    assert isinstance(result, Unavailable) and result.reason_code == "timed_out"
    assert (session.spend.state("attempt-1"), session.spend.committed_usd()) == ("UNKNOWN", Decimal("0.054848"))
    [lifecycle] = session.evidence.glob("turn-01-*/container-lifecycle.json")
    assert json.loads(lifecycle.read_text())["container_absent"] is True


def test_the_guard_in_the_container_refuses_a_request_that_differs_from_the_policy(pinned_hermes_image, run_id, evidence_root) -> None:
    policy = GuardPolicy(model="fixture-model/1", max_output_tokens=2048, max_request_bytes=12_000, max_envelope_chars=2_500)
    session = rig(pinned_hermes_image, run_id, evidence_root, "mismatch", "concrete-thesis")
    session.docker.policy = policy  # the container is told a different output limit than the turn carries

    session.run_case("concrete-thesis")

    result_file = session.container_result()
    assert result_file["hermes"]["request_count"] == 0  # the controlled provider did no work
    assert [r["reason"] for r in session.refusals()] == ["output_limit_not_as_configured"]
    assert session.spend.state("attempt-1") == "RELEASED" and session.spend.committed_usd() == 0


def test_a_provider_that_echoes_the_credential_is_withheld_and_never_saved(pinned_hermes_image, run_id, evidence_root) -> None:
    script = {"kind": "content", "content": f"here is the key {SENTINEL}", "finish_reason": "stop",
              "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
    session = Rig(pinned_hermes_image, run_id, evidence_root, "echo", script)

    result = session.run_case("concrete-thesis")

    assert not isinstance(result, Interpreted)
    assert (session.spend.state("attempt-1"), session.spend.committed_usd()) == ("UNKNOWN", Decimal("0.054848"))
    scripts = list(session.evidence.glob("turn-*/input.json"))  # the authored provider script holds the echo by design
    assert find_leaks(session.root, SENTINEL, exclude=[session.credential, *scripts]) == []
    saved = json.dumps([vars(h.settlement) if h.settlement else None for h in session.ledger.history(OWNER, INTAKE)], default=str)
    assert SENTINEL not in saved
