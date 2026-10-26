"""The ACTUAL request shape from the saved application to the provider send: every bound field, exactly, on the wire.

Pure tests (no Docker, database or network): the job maps the guard policy's required fields onto pinned Hermes' own
request options and adds nothing for an AUTHORED policy; the optional record field `prompt_cache_options` is exactly
`{"mode": "explicit"}` across record admission, body refusal, the runner's policy check and the application binding,
and a record without it keeps the earlier shape.

Docker tests (one pinned Hermes image built from this candidate, the API session's PostgreSQL container): the real
`open_hermes_application` composition, `create_app`, the accepted guard and relay runners, the PostgreSQL ledger, the
genuine relay job in a no-network container and the file channel. The relay code runs in this process so that only its
provider send is replaced by a counted SYNTHETIC reply; the synthetic record and definition are approved only inside
the test. Everything here is SYNTHETIC: no provider, key, price or release is proved, whatever the record's ACTUAL kind
or the configuration's LIVE label says.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import hermes_turn_job
import relay_admission
from provider_guard import GuardPolicy
from relay_admission import ActualReleaseUnapproved, load_actual_release
from relay_turn_runner import RelayEndpoint, build_relay_job
from spend_ledger import TokenPrice
from test_hermes_relay_composition import (  # noqa: F401 - `approve` is used as a fixture
    CHARGE, MODEL, RESERVATION, ROUTING, SCHEMA, SNAPSHOT, approve, canonical, definition, handoff, record,
    write_handoff,
)

CACHE = {"mode": "explicit"}
CACHED_FIELDS = ["model", "messages", "stream", "response_format", "provider", "reasoning", "max_tokens", "session_id",
                 "prompt_cache_options"]
EXTRA = {"stream": False, "provider": ROUTING, "reasoning": {"effort": "low"}, "response_format": SCHEMA}


def cached_record(**changes: Any) -> dict[str, Any]:
    return record(**{"prompt_cache_options": dict(CACHE), "allowed_fields": list(CACHED_FIELDS), **changes})


def loaded(value: dict[str, Any]) -> Any:
    raw = canonical(value)
    sha = hashlib.sha256(raw).hexdigest()
    return load_actual_release(raw, sha, approved=frozenset({sha}))


def wire(attempt: str = "att-1", **changes: Any) -> bytes:
    value = {"model": MODEL, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
             "max_tokens": 4096, "session_id": f"p05-{attempt}", **EXTRA, "prompt_cache_options": dict(CACHE),
             **changes}
    return json.dumps({k: v for k, v in value.items() if v is not None}).encode()


# --- Pure: the job's request options ------------------------------------------------------------------------------


def test_an_authored_policy_or_a_job_with_no_guard_adds_no_hermes_option() -> None:
    assert hermes_turn_job.request_options({}) == {}
    assert hermes_turn_job.request_options({"guard": {"policy": {"required_extra": {}}}}) == {}


def test_every_bound_field_goes_to_the_hermes_option_that_puts_it_on_the_wire() -> None:
    required = {**EXTRA, "prompt_cache_options": dict(CACHE)}
    options = hermes_turn_job.request_options({"guard": {"policy": {"required_extra": required}}})
    assert options == {"reasoning_config": {"effort": "low"}, "request_overrides": {
        "stream": False, "response_format": SCHEMA,
        "extra_body": {"provider": ROUTING, "reasoning": {"effort": "low"}, "prompt_cache_options": CACHE}}}


def test_without_reasoning_no_reasoning_setting_is_given_and_an_unknown_field_is_left_to_the_guard() -> None:
    options = hermes_turn_job.request_options({"guard": {"policy": {"required_extra": {
        "stream": False, "provider": ROUTING, "temperature": 0}}}})
    assert options == {"request_overrides": {"stream": False, "extra_body": {"provider": ROUTING}}}


# --- Pure: the optional cache field in the record and the body ----------------------------------------------------


def test_a_record_without_the_cache_field_keeps_its_shape_and_refuses_the_field_in_a_body() -> None:
    actual = loaded(record())
    assert actual.prompt_cache_options is None and "prompt_cache_options" not in actual.allowed_fields
    assert actual.body_refusal(wire(prompt_cache_options=None), "att-1") is None
    assert actual.body_refusal(wire(), "att-1") == "body_field_not_permitted"


def test_a_record_with_exactly_explicit_mode_requires_exactly_that_value_in_the_body() -> None:
    actual = loaded(cached_record())
    assert actual.prompt_cache_options == CACHE and actual.body_refusal(wire(), "att-1") is None
    assert actual.body_refusal(wire(prompt_cache_options=None), "att-1") == "body_field_missing"
    for changed in ({"mode": "auto"}, {"mode": "explicit", "breakpoint": 1}, {"mode": "explicit", "ttl": "5m"}, {},
                    "explicit"):
        assert actual.body_refusal(wire(prompt_cache_options=changed), "att-1") == "body_cache_options_mismatch"
    assert actual.body_refusal(wire(prompt_cache_breakpoint=1), "att-1") == "body_field_not_permitted"


@pytest.mark.parametrize("changes", [
    {"prompt_cache_options": {"mode": "auto"}},
    {"prompt_cache_options": {"mode": "explicit", "breakpoint": {"index": 0}}},
    {"prompt_cache_options": {"mode": "explicit", "ttl": "5m"}},
    {"prompt_cache_options": {"mode": "EXPLICIT"}},
    {"prompt_cache_options": {}},
    {"prompt_cache_options": None},
    {"prompt_cache_options": "explicit"},
    {"allowed_fields": [name for name in CACHED_FIELDS if name != "prompt_cache_options"]},  # set, but not allowed
    {"allowed_fields": CACHED_FIELDS + ["prompt_cache_breakpoint"]},
])
def test_any_other_cache_value_or_a_field_list_that_disagrees_with_it_is_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        loaded(cached_record(**changes))


def test_a_field_list_naming_the_cache_field_without_the_value_is_refused() -> None:
    with pytest.raises(ValueError):
        loaded(record(allowed_fields=list(CACHED_FIELDS)))
    with pytest.raises(ValueError):
        loaded(record(prompt_cache_breakpoint={"index": 0}))


def test_an_unapproved_cached_record_is_still_refused() -> None:
    raw = canonical(cached_record())
    with pytest.raises(ActualReleaseUnapproved):
        load_actual_release(raw, hashlib.sha256(raw).hexdigest())


def runner_with(tmp_path: Path, actual: Any, extra: dict[str, Any]) -> Any:
    policy = GuardPolicy(model=MODEL, max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500,
                         required_extra=extra)
    from provider_transport import TransportRoute

    route = TransportRoute(actual.release.route_id, "ACTUAL", actual.endpoint_url, actual.release.max_reply_bytes)
    return build_relay_job(route, release=actual.release, actual=actual, price=TokenPrice(Decimal("3"), Decimal("9")),
                           endpoint=RelayEndpoint(*(tmp_path / n for n in ("g", "r", "s", "k")), "app"),
                           subject_for=lambda turn: None, policy=policy, ledger=None, scope_for=lambda turn: "s",
                           image="unused", run_id="run-1", evidence_dir=tmp_path / "jobs", script_for=lambda turn: {},
                           timeout_seconds=actual.timeout_seconds)


def test_the_runner_needs_the_policy_to_require_exactly_the_records_cache_value(tmp_path: Path) -> None:
    cached, plain = loaded(cached_record()), loaded(record())
    runner_with(tmp_path, cached, {**EXTRA, "prompt_cache_options": dict(CACHE)})
    runner_with(tmp_path, plain, dict(EXTRA))
    for actual, extra in ((cached, dict(EXTRA)), (cached, {**EXTRA, "prompt_cache_options": {"mode": "auto"}}),
                          (plain, {**EXTRA, "prompt_cache_options": dict(CACHE)})):
        with pytest.raises(ValueError, match="request shape"):
            runner_with(tmp_path, actual, extra)


def test_the_application_binds_the_cache_value_and_refuses_it_changed_after_binding(approve, tmp_path: Path) -> None:
    from edge_os_api.research.hermes_relay_composition import bind_release, compose_application
    from edge_os_api.research.hermes_transport_mount import MountRefused
    from test_hermes_relay_composition import endpoint, lazy_engine

    [cached, plain] = approve(definition(record_fields={"prompt_cache_options": dict(CACHE),
                                                        "allowed_fields": list(CACHED_FIELDS)}),
                              definition(record_fields={"release_id": "rel-app-plain-1"}))
    release = bind_release(cached)
    assert release.policy.required_extra == {**EXTRA, "prompt_cache_options": CACHE} and release.unchanged()
    assert "prompt_cache_options" not in bind_release(plain).policy.required_extra
    release.policy.required_extra["prompt_cache_options"]["mode"] = "auto"  # type: ignore[index]
    assert not release.unchanged()
    with pytest.raises(MountRefused, match="changed"):
        compose_application(release, lazy_engine(), endpoint=endpoint(tmp_path / "relay"), run_id="rc-unit",
                            evidence_dir=tmp_path / "jobs")
    again = bind_release(cached)
    again.actual.prompt_cache_options["mode"] = "auto"  # type: ignore[index] - the record's object, not the bound copy
    assert again.policy.required_extra["prompt_cache_options"] == CACHE and not again.unchanged()


# --- Docker: the saved application through the genuine job and channel, one counted SYNTHETIC send ----------------


RELEASE_ID = "SYNTHETIC-hermes-app-1"
OTHER_PLATFORM_IMAGE = "sha256:" + "0" * 64
IMAGE_RECEIPT = "HERMES_APP_IMAGE_RECEIPT"  # a kept `source_identity.json` of this candidate's pinned Hermes image
SPEND_TABLES = ("usage_local.provider_spend_events, usage_local.provider_spend_reservations, "
                "usage_local.provider_spend_settings")


def docker_names(*args: str) -> list[str]:
    from relay_supervisor import docker

    return docker(*args, check=False).stdout.split()


class InProcessRelay:
    """The accepted relay code with its own records and the file channel, run here so only `send_once` is replaced."""

    def __init__(self, root: Path, record_raw: bytes, record_sha: str, ca: bytes, channel: Path, key: str,
                 monkeypatch: pytest.MonkeyPatch) -> None:
        import relay_service
        from relay_transport import SentReply

        self.root, self.sends, self.answers = root, [], []
        for folder in ("grants", "revocations", "state"):
            (root / folder).mkdir(parents=True)
        (root / "admission.key").write_bytes(secrets.token_bytes(32))
        (root / "provider-key").write_text(key)
        (root / "ca.pem").write_bytes(ca)
        (root / "release.json").write_bytes(record_raw)
        self.reply = SentReply

        def counted_send(destination: Any, **kwargs: Any) -> Any:
            self.sends.append({"destination": destination, **kwargs})
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(relay_service, "send_once", counted_send)
        self.relay = relay_service.Relay({
            "release_record": {"path": str(root / "release.json"), "sha256": record_sha},
            "channel_roots": {"app": str(channel)}, "gateway_socket": "/relay/egress/gateway.sock",
            "paths": {"provider_key": str(root / "provider-key"), "admission_key": str(root / "admission.key"),
                      "provider_ca": str(root / "ca.pem"), "grants": str(root / "grants"),
                      "revocations": str(root / "revocations"), "state": str(root / "state")}})
        self.relay.recover()
        self.relay.heartbeat()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.wait(0.02):
            self.relay.heartbeat()
            self.relay.serve_once()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def record_of(self, attempt: str, name: str) -> dict[str, Any] | None:
        path = self.root / "state" / attempt / f"{name}.json"
        return json.loads(path.read_text()) if path.exists() else None


def provider_reply(cost: float, model: str = MODEL) -> bytes:
    from authored_cases import load_case, provider_script

    script = provider_script(load_case("concrete-thesis")["provider"])
    return json.dumps({"id": "gen-SYNTHETIC-1", "object": "chat.completion", "created": 0, "model": model,
                       "choices": [{"index": 0, "message": {"role": "assistant", "content": script["content"]},
                                    "finish_reason": "stop"}],
                       "usage": {**script["usage"], "cost": cost}}).encode()


@pytest.fixture(scope="module")
def pinned_hermes_image() -> str:
    """Overrides the session builder for this module: reuse the candidate's kept image by its immutable id, named by
    its build receipt. Nothing is built, pulled or removed here; the image stays its builder's."""
    from docker_turn_runner import PINNED_HERMES, PYTHON_IMAGE
    from relay_supervisor import docker

    receipt = os.environ.get(IMAGE_RECEIPT)
    if not receipt:
        pytest.fail(f"{IMAGE_RECEIPT} must name the source_identity.json of the candidate's pinned image; this test "
                    "builds no image")
    value = json.loads(Path(receipt).read_text())
    assert (value["commit"], value["python_image"]) == (PINNED_HERMES, PYTHON_IMAGE), value
    seen = docker("image", "inspect", value["image_id"], "--format", "{{.Id}}", check=False)
    assert seen.returncode == 0 and seen.stdout.strip() == value["image_id"], "the receipted image is not present"
    return value["image_id"]


@pytest.fixture(scope="module")
def image_id(pinned_hermes_image: str, evidence_root: Path) -> str:
    """The receipted image id, and proof that the image carries this candidate's job source byte for byte."""
    from docker_turn_runner import HERE, LABEL
    from relay_supervisor import docker

    found = pinned_hermes_image
    inside = docker("run", "--rm", "--network", "none", "--label", f"{LABEL}=shape-image-check", "--entrypoint",
                    "sha256sum", found, "/opt/p05/hermes_turn_job.py").stdout.split()[0]
    identity = {"image_tag": pinned_hermes_image, "image_id": found, "job_source_sha256_in_image": inside,
                "job_source_sha256_candidate": hashlib.sha256((HERE / "hermes_turn_job.py").read_bytes()).hexdigest(),
                "label": "SYNTHETIC"}
    (evidence_root / "shape-image-identity.json").write_text(json.dumps(identity, indent=1) + "\n")
    assert inside == identity["job_source_sha256_candidate"]
    return found


@pytest.fixture
def shaped(image_id: str, env, migrated, pg, run_id: str, evidence_root: Path, request,
           monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """One application over the composition with a test-approved SYNTHETIC record that asks for no prompt caching.

    An indirect parameter gives `definition` keyword changes, merged over these (its `record_fields` likewise)."""
    from edge_os_api.core.settings import load_settings
    from edge_os_api.main import create_app
    from edge_os_api.research import hermes_relay_composition as composition
    from edge_os_api.research.hermes_relay_composition import open_hermes_application
    from fastapi.testclient import TestClient

    from conftest import SENTINEL

    root = evidence_root / f"shape-{request.node.name}"  # the full name: parametrized cases differ only at the end
    channel = root / "jobs"
    channel.mkdir(parents=True)
    ca = b"SYNTHETIC CA bundle"
    changes = dict(getattr(request, "param", {}))
    record_changes = changes.pop("record_fields", {})
    given = definition(images=(("linux/arm64", image_id), ("linux/amd64", OTHER_PLATFORM_IMAGE)), **changes,
                       record_fields={
        "release_id": RELEASE_ID, "ca_bundle_sha256": hashlib.sha256(ca).hexdigest(),
        "prompt_cache_options": dict(CACHE), "allowed_fields": list(CACHED_FIELDS), **record_changes})
    monkeypatch.setattr(composition, "RELEASE_DEFINITIONS", (given,))
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({given.record_sha256}))
    pg.psql(f"truncate {SPEND_TABLES}")
    before = {"containers": docker_names("ps", "-aq"), "networks": docker_names("network", "ls", "-q"),
              "volumes": docker_names("volume", "ls", "-q"), "bridge": docker_names("network", "inspect", "bridge",
                                                                                   "--format", "{{.Id}}")}
    relay = InProcessRelay(root / "relay", given.record, given.record_sha256, ca, channel, SENTINEL, monkeypatch)
    content = handoff(root, given, image={"reference": image_id[:19], "id": image_id})
    content["evidence_dir"] = str(channel)
    located = write_handoff(root / "operator", content)
    settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})
    opened: list[tuple[Any, Any]] = []
    job_run = f"{run_id}-sh{secrets.token_hex(3)}"  # 1-64 letters, digits or ._:- (relay identifiers)

    def build(name: str) -> Any:
        app = open_hermes_application(settings, handoff_path=located[0], handoff_sha256=located[1],
                                      run_id=f"{job_run}-{name}", close_budget_seconds=5.0)
        assert app is not None and app.release.image == image_id
        client = TestClient(create_app(settings, hermes_runner=app.runner, hermes_config=app.config))
        client.__enter__()
        opened.append((app, client))
        return client

    build.relay, build.root, build.channel, build.given = relay, root, channel, given  # type: ignore[attr-defined]
    try:
        yield build
    finally:
        for app, client in opened:
            client.__exit__(None, None, None)
            app.close()
        relay.stop()
        pg.psql(f"truncate {SPEND_TABLES}")
        from docker_turn_runner import LABEL

        owned = docker_names("ps", "-a", "--filter", f"name=^p05-{job_run}-", "--format", "{{.Names}}")
        after = {"containers": docker_names("ps", "-aq"), "networks": docker_names("network", "ls", "-q"),
                 "volumes": docker_names("volume", "ls", "-q"), "bridge": docker_names("network", "inspect", "bridge",
                                                                                      "--format", "{{.Id}}")}
        cleanup = {"owned_containers_left": owned, "foreign_containers_gone": sorted(set(before["containers"])
                                                                                      - set(after["containers"])),
                   "foreign_networks_gone": sorted(set(before["networks"]) - set(after["networks"])),
                   "foreign_volumes_gone": sorted(set(before["volumes"]) - set(after["volumes"])),
                   "bridge_unchanged": before["bridge"] == after["bridge"], "label": LABEL}
        (root / "cleanup.json").write_text(json.dumps(cleanup, indent=1) + "\n")
        assert cleanup == {"owned_containers_left": [], "foreign_containers_gone": [], "foreign_networks_gone": [],
                           "foreign_volumes_gone": [], "bridge_unchanged": True, "label": LABEL}, cleanup


def intake() -> dict[str, Any]:
    from authored_cases import load_case

    return dict(load_case("concrete-thesis")["intake"])


def container_result(channel: Path, attempt: str) -> dict[str, Any]:
    [output] = list(channel.glob(f"turn-*-{attempt}/output"))
    return json.loads((output / "container-result.json").read_text())


def test_docker_the_saved_request_leaves_the_job_with_every_bound_field_is_sent_once_settled_and_reopened(
        shaped, owner_a, owner_b, pg, evidence_root: Path) -> None:
    from leak_scan import find_leaks

    from conftest import SENTINEL

    relay = shaped.relay
    relay.answers.append(relay.reply(200, "application/json", provider_reply(float(CHARGE))))
    first = shaped("first")
    assert first.get("/v1/interpreter", headers=owner_a).json()["interpreter"]["id"] == RELEASE_ID  # visibly SYNTHETIC

    created = first.post("/v1/research/requests", json=intake(), headers=owner_a)

    assert created.status_code == 201, created.text
    assert created.json()["interpreter"]["kind"] == "HERMES_LIVE_RELEASE"
    assert RELEASE_ID in created.json()["interpreter"]["notice"]
    [attempt] = created.json()["attempts"]
    attempt_id = attempt["attempt_id"]
    assert (attempt["status"], attempt["parse_result"], attempt["request_count"]) == ("COMPLETED", "ACCEPTED", 1)
    assert attempt["spend"] == {"state": "SETTLED", "charge_usd": str(CHARGE)}

    [send] = relay.sends  # the one counted provider send, with the exact bytes the relay would send
    body = json.loads(send["body"])
    expected = {**EXTRA, "prompt_cache_options": CACHE, "model": MODEL, "max_tokens": 4096,
                "session_id": f"p05-{attempt_id}"}
    assert {name: body[name] for name in expected} == expected and set(body) == set(expected) | {"messages"}
    assert (send["destination"].host, send["destination"].path, send["key"]) == (
        "openrouter.ai", "/api/v1/chat/completions", SENTINEL)
    wire_sha = hashlib.sha256(send["body"]).hexdigest()
    [admitted] = [e for e in container_result(shaped.channel, attempt_id)["guard"]["evidence"] if e["admitted"]]
    assert admitted["request_sha256"] == wire_sha  # the job's guard admitted these same bytes
    (shaped.root / "wire.json").write_text(json.dumps({
        "label": "SYNTHETIC", "attempt_id": attempt_id, "body_sha256": wire_sha, "body_bytes": len(send["body"]),
        "bound_fields": {name: body[name] for name in expected}}, indent=1, sort_keys=True) + "\n")

    started, finished = relay.record_of(attempt_id, "started"), relay.record_of(attempt_id, "finished")
    assert started is not None and finished["outcome"] == "reply" and finished["cost"] == float(CHARGE)
    owner, intake_id = pg.psql(f"select owner_id || '|' || intake_record_id from interpretation_attempts "
                               f"where attempt_id = '{attempt_id}'").split("|")
    grant = json.loads((relay.root / "grants" / f"{attempt_id}.json").read_text())
    assert (grant["owner_id"], grant["request_id"], grant["scope"]) == (owner, intake_id, f"intake:{intake_id}")
    assert pg.psql(f"select state || '|' || owner_id || '|' || intake_record_id || '|' || charged_nano_usd from "
                   f"usage_local.provider_spend_reservations where attempt_id = '{attempt_id}'") == (
        f"SETTLED|{owner}|{intake_id}|{int(CHARGE * 10**9)}")
    sandbox = container_result(shaped.channel, attempt_id)["sandbox"]
    assert sandbox["network"]["blocked"] is True and sandbox["credential_mounted"] is False

    reopened = shaped("reopen")  # another application instance serves the reopen
    path = f"/v1/research/requests/{created.json()['intake']['record_id']}"
    again = reopened.get(path, headers=owner_a).json()
    assert again["attempts"] == created.json()["attempts"] and again["head"] == created.json()["head"]
    assert reopened.get(path, headers=owner_b).status_code == 404
    assert pg.psql("select count(*) from interpretation_attempts") == "1"
    assert pg.psql("select count(*) from usage_local.provider_spend_reservations") == "1"
    assert len(relay.sends) == 1
    assert find_leaks(shaped.channel, SENTINEL) == [] and find_leaks(shaped.root / "operator", SENTINEL) == []


PREFERRED_MODEL = "openai/gpt-6.1-sol"  # the builder's preferred model: a SYNTHETIC record value here, not proof of it


def application_schema_release() -> dict[str, Any]:
    """`shaped` changes for the application's own strict response format, the preferred model and a body limit that
    holds the real prompt, task and schema (about 14 KB). The rates stay SNAPSHOT's, so the reservation is
    (24,000 + 64) x 3.00 / 1e6 + 4,096 x 9.00 / 1e6 = USD 0.109056, under the owner cap."""
    from edge_os_api.research.interpreter_output_schema import interpretation_response_format

    response_format = interpretation_response_format()
    snapshot = canonical({**SNAPSHOT, "model": PREFERRED_MODEL})
    return {"response_format": response_format, "snapshot": snapshot, "record_fields": {
        "model": PREFERRED_MODEL, "max_request_bytes": 24_000,
        "response_format_sha256": hashlib.sha256(canonical(response_format)).hexdigest(),
        "price_snapshot_sha256": hashlib.sha256(snapshot).hexdigest()}}


def cache_markers(value: Any, path: str = "") -> list[str]:
    """Every key in the body that names a cache breakpoint or cache control, at any depth."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if "cache" in key and path + key != "prompt_cache_options":
                found.append(path + key)
            found.extend(cache_markers(child, f"{path}{key}/"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(cache_markers(child, f"{path}{index}/"))
    return found


@pytest.mark.parametrize("shaped", [application_schema_release()], indirect=True, ids=["application-schema"])
def test_docker_the_application_schema_and_preferred_model_go_on_the_wire_with_no_cache_marker(
        shaped, owner_a, pg) -> None:
    from edge_os_api.records import contract_adapter as record_contract
    from edge_os_api.research.hermes_interpreter import SYSTEM_PROMPT
    from edge_os_api.research.interpreter_output_schema import interpretation_response_format

    relay = shaped.relay
    relay.answers.append(relay.reply(200, "application/json", provider_reply(float(CHARGE), PREFERRED_MODEL)))
    client = shaped("schema")

    created = client.post("/v1/research/requests", json=intake(), headers=owner_a)

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    attempt_id = attempt["attempt_id"]
    assert (attempt["status"], attempt["parse_result"], attempt["request_count"]) == ("COMPLETED", "ACCEPTED", 1)
    assert attempt["spend"] == {"state": "SETTLED", "charge_usd": str(CHARGE)}
    [send] = relay.sends
    body = json.loads(send["body"])
    expected = {**EXTRA, "response_format": interpretation_response_format(), "prompt_cache_options": CACHE,
                "model": PREFERRED_MODEL, "max_tokens": 4096, "session_id": f"p05-{attempt_id}"}
    assert {name: body[name] for name in expected} == expected and set(body) == set(expected) | {"messages"}
    assert [set(message) for message in body["messages"]] == [{"role", "content"}] * 2
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    system, user = (message["content"] for message in body["messages"])
    assert isinstance(system, str) and SYSTEM_PROMPT in system  # Hermes wraps the prompt in its own text
    assert isinstance(user, str) and record_contract.canonical_bytes(json.loads(user)).decode() == user
    task = json.loads(user)
    assert (task["task"], task["original_request"]) == ("interpret", intake()["original_request"])
    assert cache_markers(body) == []
    wire_sha = hashlib.sha256(send["body"]).hexdigest()
    [admitted] = [e for e in container_result(shaped.channel, attempt_id)["guard"]["evidence"] if e["admitted"]]
    assert admitted["request_sha256"] == wire_sha
    (shaped.root / "wire.json").write_text(json.dumps({
        "label": "SYNTHETIC", "attempt_id": attempt_id, "body_sha256": wire_sha, "body_bytes": len(send["body"]),
        "response_format_sha256": hashlib.sha256(canonical(expected["response_format"])).hexdigest(),
        "message_roles": ["system", "user"], "cache_markers": []}, indent=1, sort_keys=True) + "\n")
    assert len(relay.sends) == 1 and pg.psql("select count(*) from usage_local.provider_spend_reservations") == "1"


@pytest.mark.parametrize("answer", ["cost_mismatch", "lost_reply"])
def test_docker_a_cost_mismatch_or_a_lost_reply_is_never_accepted_keeps_the_full_reservation_and_is_never_resent(
        shaped, owner_a, pg, answer: str) -> None:
    from relay_transport import ReplyLost

    relay = shaped.relay
    relay.answers.append(relay.reply(200, "application/json", provider_reply(0.05)) if answer == "cost_mismatch"
                         else ReplyLost("SYNTHETIC lost reply"))
    first = shaped("unknown")

    created = first.post("/v1/research/requests", json=intake(), headers=owner_a)

    [attempt] = created.json()["attempts"]
    assert attempt["parse_result"] != "ACCEPTED" and created.json()["head"]["interpretation_revision_id"] is None
    assert attempt["spend"] == {"state": "UNKNOWN", "charge_usd": str(RESERVATION)}
    assert len(relay.sends) == 1 and relay.record_of(attempt["attempt_id"], "started") is not None
    path = f"/v1/research/requests/{created.json()['intake']['record_id']}"
    retried = first.post(f"{path}/interpretation-retries", headers=owner_a, json={"retry_of": attempt["attempt_id"]})
    assert retried.status_code == 409
    reopened = shaped("unknown-reopen")
    assert reopened.get(path, headers=owner_a).json()["attempts"][0]["spend"]["state"] == "UNKNOWN"
    assert len(relay.sends) == 1 and pg.psql("select count(*) from usage_local.provider_spend_reservations") == "1"
