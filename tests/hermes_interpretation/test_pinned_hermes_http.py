"""The saved Research path over authenticated HTTP, with ACTUAL pinned Hermes in a no-network container.

What this proves: routes, authentication, owner scoping, PostgreSQL storage, the attempt history and the strict parser
work around the real Hermes runtime. What it does not prove: how any real model reads a request. The provider is a
LOCAL FAKE that returns authored text from `apps/api/tests/fixtures/hermes_interpretation`. No real provider, key or
account is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from authored_cases import load_case, load_follow_up, provider_script
from docker_turn_runner import DockerHermesTurnRunner
from edge_os_api.core.settings import load_settings
from edge_os_api.main import create_app

THESIS_ENTRY = load_case("concrete-thesis")["expect"]["entry_value"]
TWO_PERCENT = load_follow_up("hunch-reply-fills-both-rules")["expect"]["entry_value"]


class PinnedApp:
    """An application whose interpreter is actual pinned Hermes, with a list of authored provider scripts to consume."""

    def __init__(self, image: str, run_id: str, evidence_root: Path, name: str, env: dict[str, str],
                 forbidden: list[str], run_budget_seconds: int = 60, timeout_seconds: int = 90) -> None:
        self.queue: list[dict[str, Any]] = []
        self.runner = DockerHermesTurnRunner(
            image=image, run_id=run_id, evidence_dir=evidence_root / name, script_for=lambda turn: self.queue.pop(0),
            forbidden=forbidden, run_budget_seconds=run_budget_seconds, timeout_seconds=timeout_seconds)
        settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
        self.client = TestClient(create_app(settings, hermes_runner=self.runner))
        self.client.__enter__()

    def script(self, *items: dict[str, Any]) -> None:
        self.queue.extend(items)

    def close(self) -> None:
        self.client.__exit__(None, None, None)


@pytest.fixture
def pinned_app(pinned_hermes_image, run_id, evidence_root, env, migrated, request):
    apps: list[PinnedApp] = []

    def build(forbidden: list[str] | None = None, **limits: int) -> PinnedApp:
        app = PinnedApp(pinned_hermes_image, run_id, evidence_root, f"http-{request.node.name[:40]}-{len(apps)}", env,
                        forbidden or [], **limits)
        apps.append(app)
        return app

    yield build
    for app in apps:
        app.close()


def case_script(name: str) -> dict[str, Any]:
    return provider_script(load_case(name)["provider"])


def follow_up_script(name: str) -> dict[str, Any]:
    return provider_script(load_follow_up(name)["provider"])


def create(app: PinnedApp, headers: dict[str, str], name: str) -> dict[str, Any]:
    response = app.client.post("/v1/research/requests", json=load_case(name)["intake"], headers=headers)
    assert response.status_code == 201, response.text
    bundle = response.json()
    app.runner.forbidden.append(bundle["intake"]["record_id"])
    return bundle


def answer(app: PinnedApp, headers: dict[str, str], bundle: dict[str, Any], question_id: str, **body: str):
    return app.client.post(f"/v1/research/requests/{bundle['intake']['record_id']}/clarifications", headers=headers, json={
        "previous_revision_id": bundle["head"]["interpretation_revision_id"], "question_id": question_id, **body})


def evidence(bundle: dict[str, Any], name: str, index: int = -1) -> dict[str, Any]:
    return next(i for i in bundle["interpretations"][index]["content"]["field_evidence"] if i["field_name"] == name)


def sql(app: PinnedApp, statement: str, **params: Any) -> list[Any]:
    with app.client.app.state.engine.begin() as connection:
        return list(connection.execute(text(statement), params))


def test_a_concrete_thesis_goes_through_actual_hermes_and_compiles_only_after_adoption(pinned_app, owner_a) -> None:
    app = pinned_app()
    app.script(case_script("concrete-thesis"))

    bundle = create(app, owner_a, "concrete-thesis")

    assert bundle["head"]["outcome"] == "NEEDS_CLARIFICATION"
    assert evidence(bundle, "entry")["value"] == THESIS_ENTRY and evidence(bundle, "entry")["origin"] == "USER_STATED"
    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["completion"], attempt["request_count"]) == ("COMPLETED", "COMPLETE", 1)
    assert attempt["usage"]["source"] == "PROVIDER_REPORTED" and attempt["usage"]["input_tokens"] == 1423
    assert attempt["latency_ms"] > 0 and attempt["identity"]["hermes_commit"] == "54bc5e509c985f37265c3d416bd2c64b10fc77ba"
    assert attempt["identity"]["runtime_label"] == "LOCAL_FAKE_PROVIDER"
    [stored] = sql(app, "select runtime_observed from interpretation_settlements where attempt_id = :a",
                   a=attempt["attempt_id"])
    observed = stored[0]
    assert observed["tools_effective"] == [] and observed["fallback_count"] == 0 and observed["network_blocked"] is True
    assert observed["wire_system_contains_prompt"] is True and observed["wire_user_message_verbatim"] is True

    adopted = answer(app, owner_a, bundle, "adopt-suggested-settings", choice_id="adopt")
    assert adopted.status_code == 201 and adopted.json()["head"]["outcome"] == "COMPILED"
    assert app.runner.turn_count == 1


def test_a_free_text_reply_fills_both_rules_with_quotes_from_the_reply(pinned_app, owner_a) -> None:
    follow_up = load_follow_up("hunch-reply-fills-both-rules")
    app = pinned_app()
    app.script(case_script("rough-hunch"), follow_up_script("hunch-reply-fills-both-rules"))
    bundle = create(app, owner_a, "rough-hunch")

    response = answer(app, owner_a, bundle, follow_up["answers_question"], answer_text=follow_up["reply"])

    assert response.status_code == 201, response.text
    after = response.json()
    assert (evidence(after, "entry")["origin"], evidence(after, "entry")["value"]) == ("USER_STATED", TWO_PERCENT)
    assert evidence(after, "exit")["origin"] == "USER_STATED"
    assert [a["purpose"] for a in after["attempts"]] == ["INTERPRET", "FOLLOW_UP"]
    assert all(a["status"] == "COMPLETED" and a["request_count"] == 1 for a in after["attempts"])
    adopted = answer(app, owner_a, after, "adopt-suggested-settings", choice_id="adopt").json()
    assert adopted["head"]["outcome"] == "COMPILED"


def test_a_reply_with_two_values_is_a_conflict_and_a_reply_that_changes_chosen_meaning_is_rejected(
        pinned_app, owner_a, owner_b) -> None:
    two = load_follow_up("hunch-reply-states-two-values")
    overwrite = load_follow_up("reply-overwrites-chosen-entry")
    app = pinned_app()
    app.script(case_script("rough-hunch"), follow_up_script("hunch-reply-states-two-values"),
               case_script("rough-hunch"), follow_up_script("reply-overwrites-chosen-entry"))

    first = create(app, owner_a, "rough-hunch")
    conflict = answer(app, owner_a, first, two["answers_question"], answer_text=two["reply"]).json()
    assert evidence(conflict, "entry")["state"] == "CONFLICTING"
    assert [a["value"] for a in evidence(conflict, "entry")["conflicts"]] == two["expect"]["conflict_values"]

    second = create(app, owner_b, "rough-hunch")
    chosen = answer(app, owner_b, second, *overwrite["after_choice"][:1], choice_id=overwrite["after_choice"][1]).json()
    rejected = answer(app, owner_b, chosen, overwrite["answers_question"], answer_text=overwrite["reply"])
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["head"]["reply"]["reason_code"] == "silent_overwrite"
    assert len(body["interpretations"]) == len(chosen["interpretations"])
    assert body["attempts"][-1]["parse_result"] == "REJECTED:silent_overwrite"


def test_a_provider_failure_and_a_cut_off_answer_are_kept_apart_and_a_retry_is_a_separate_attempt(
        pinned_app, owner_a) -> None:
    app = pinned_app()
    app.script(case_script("provider-503"), case_script("truncated-cut-off"), case_script("concrete-thesis"))
    failed = create(app, owner_a, "concrete-thesis")
    assert failed["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "interpreter_unavailable"
    assert failed["attempts"][0]["usage"]["source"] == "UNKNOWN" and failed["attempts"][0]["completion"] == "NONE"
    assert "sk-LEAK" not in json.dumps(failed)

    retried = app.client.post(f"/v1/research/requests/{failed['intake']['record_id']}/interpretation-retries",
                              json={"retry_of": failed["attempts"][0]["attempt_id"]}, headers=owner_a).json()
    cut = retried["attempts"][1]
    assert (cut["status"], cut["completion"], cut["parse_result"]) == ("TRUNCATED", "TRUNCATED", "REJECTED:truncated")
    assert cut["usage"] == {"source": "PROVIDER_REPORTED", "input_tokens": 1423, "output_tokens": 611, "total_tokens": 2034}
    assert retried["outcomes"][-1]["record"]["content"]["findings"][0]["code"] == "malformed_model_output"

    final = app.client.post(f"/v1/research/requests/{failed['intake']['record_id']}/interpretation-retries",
                            json={"retry_of": cut["attempt_id"]}, headers=owner_a).json()
    assert [(a["sequence"], a["status"], a["retry_of"]) for a in final["attempts"]] == [
        (1, "PROVIDER_FAILED", None), (2, "TRUNCATED", failed["attempts"][0]["attempt_id"]),
        (3, "COMPLETED", cut["attempt_id"])]
    assert final["attempts"][:2] == retried["attempts"][:2]
    assert app.runner.turn_count == 3


def test_a_provider_that_never_answers_leaves_an_unknown_attempt_that_is_not_retried(pinned_app, owner_a) -> None:
    app = pinned_app(run_budget_seconds=6, timeout_seconds=40)
    app.script(case_script("provider-hang"), case_script("concrete-thesis"))

    hung = create(app, owner_a, "concrete-thesis")

    [attempt] = hung["attempts"]
    assert attempt["status"] in {"TIMED_OUT", "UNKNOWN"} and attempt["completion"] == "UNKNOWN"
    assert attempt["usage"]["source"] == "UNKNOWN"
    refused = app.client.post(f"/v1/research/requests/{hung['intake']['record_id']}/interpretation-retries",
                              json={"retry_of": attempt["attempt_id"]}, headers=owner_a)
    assert refused.status_code == 409 and app.runner.turn_count == 1


def test_a_second_application_over_the_same_database_shows_the_same_saved_state(pinned_app, owner_a, owner_b) -> None:
    app = pinned_app()
    app.script(case_script("rough-hunch"))
    bundle = create(app, owner_a, "rough-hunch")
    chosen = answer(app, owner_a, bundle, "choose-entry", choice_id="g3-2pct").json()

    reopened = pinned_app()
    again = reopened.client.get(f"/v1/research/requests/{chosen['intake']['record_id']}", headers=owner_a)

    assert again.json() == chosen and reopened.runner.turn_count == 0
    assert reopened.client.get(f"/v1/research/requests/{chosen['intake']['record_id']}", headers=owner_b).status_code == 404
