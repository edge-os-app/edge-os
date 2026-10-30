"""The Hermes relay application composition: one approved release bound to one price, behind the saved Research path.

Pure tests (no database, Docker or network): empty registries compose nothing and touch nothing; production and another
interpreter are refused; a definition binds only when its record is in the relay's trusted registry and its price
snapshot, schema, image and channel are exactly the record's; the ledger and the relay runner hold the SAME TokenPrice.

Mounted tests (the session's PostgreSQL container): the real composition, `create_app`, the accepted guard and relay
runners and the PostgreSQL ledger. Only the container job and the relay process are replaced by stand-ins that write the
relay's records, so the provider is SYNTHETIC. The record is a synthetic one admitted by patching the registry inside
the test; it is not an approved release and proves no provider, price or deployment.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import harness
from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.main import create_app
from edge_os_api.research import hermes_relay_composition as composition
from edge_os_api.research.hermes_interpreter import HermesTurn, HermesTurnResult
from edge_os_api.research.hermes_relay_composition import (
    RelayApplicationDefinition, bind_release, compose_application, open_hermes_application,
)
from edge_os_api.research.hermes_transport_mount import MountRefused
from edge_os_api.research.provider_spend_ledger import TokenPrice
from hermes_cases import case, turn_result
from test_hermes_research_flow import create, retry, rows
from test_hermes_transport_mount import job_report
from test_provider_spend_ledger import empty_spend_ledger
from tokens import TestSigner

import relay_admission  # noqa: E402 - on the path once the composition module is imported
from relay_turn_runner import RelayEndpoint  # noqa: E402

MODEL = "synthetic-model/1"
SLUG = "synthetic-provider"
SCHEMA = {"type": "json_schema", "json_schema": {"name": "interpretation", "strict": True, "schema": {"type": "object"}}}
ROUTING = {"only": [SLUG], "allow_fallbacks": False, "require_parameters": True, "data_collection": "deny",
           "max_price": {"prompt": 4, "completion": 10}}
IMAGE = "sha256:" + "d" * 64  # the arm64 Docker image id the relay operator launches, not a registry digest reference
AMD64_IMAGE = "sha256:" + "9" * 64  # the amd64 id of the same source; a listed id only for that platform
REFERENCE = "edge-os-p05-hermes:synthetic-local"  # the operator's local tag for that id; it names, never selects
CHANNEL = "app"
# Deliberately not the LOCAL authored 2.00 / 7.50: the ledger must use the snapshot's own rates.
SNAPSHOT = {"model": MODEL, "provider": SLUG, "prompt_usd_per_million": "3.00", "completion_usd_per_million": "9.00"}
RESERVATION = Decimal("0.073056")  # (12,000 + 64) x 3.00 / 1e6 + 4,096 x 9.00 / 1e6
CHARGE = Decimal("0.009768")  # concrete-thesis reports 1,423 prompt and 611 completion tokens: 4,269 + 5,499 nano-USD x 1e3
UNAPPROVED = object()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def record(**changes: Any) -> dict[str, Any]:
    return {"release_id": "rel-app-synthetic-1", "route_id": "route-app-synthetic", "kind": "ACTUAL",
            "approval": {"path": "/synthetic/approval.md", "sha256": "a" * 64},
            "destination": {"host": "openrouter.ai", "port": 443, "path": "/api/v1/chat/completions"},
            "ca_bundle_sha256": "b" * 64, "model": MODEL, "provider": ROUTING, "max_tokens": 4096,
            "reasoning": {"effort": "low"}, "response_format_sha256": hashlib.sha256(canonical(SCHEMA)).hexdigest(),
            "stream": False, "allowed_fields": ["model", "messages", "stream", "response_format", "provider", "reasoning",
                                                "max_tokens", "session_id"],
            "max_request_bytes": 12_000, "max_reply_bytes": 65_536, "timeout_seconds": 90,
            "price_snapshot_sha256": hashlib.sha256(canonical(SNAPSHOT)).hexdigest(), **changes}


def definition(*, record_fields: dict[str, Any] | None = None, snapshot: bytes | None = None,
               **changes: Any) -> RelayApplicationDefinition:
    raw = canonical(record(**(record_fields or {})))
    fields: dict[str, Any] = {"record": raw, "record_sha256": hashlib.sha256(raw).hexdigest(),
                              "price_snapshot": canonical(SNAPSHOT) if snapshot is None else snapshot,
                              "response_format": SCHEMA,
                              "images": (("linux/arm64", IMAGE), ("linux/amd64", AMD64_IMAGE)),
                              "channel_root": CHANNEL, "global_cap_usd": Decimal("0.30"),
                              "owner_cap_usd": Decimal("0.15"), **changes}
    return RelayApplicationDefinition(**fields)


@pytest.fixture
def approve(monkeypatch: pytest.MonkeyPatch):
    """Put definitions in the code-owned map and, unless marked UNAPPROVED, their records in the trusted registry."""
    def put(*items: Any) -> list[RelayApplicationDefinition]:
        definitions = [item for item in items if item is not UNAPPROVED]
        approved = definitions if UNAPPROVED not in items else []
        monkeypatch.setattr(composition, "RELEASE_DEFINITIONS", tuple(definitions))
        monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES",
                            frozenset(item.record_sha256 for item in approved))
        return definitions
    return put


def endpoint(root: Path, channel: str = CHANNEL) -> RelayEndpoint:
    return RelayEndpoint(root / "grants", root / "revocations", root / "state", root / "admission.key", channel)


@pytest.fixture
def unreachable(monkeypatch: pytest.MonkeyPatch):
    """Local Hermes settings over a database nobody serves; opening an engine fails the test."""
    def no_engine(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("an engine was opened before the refusal")

    monkeypatch.setattr(composition, "make_engine", no_engine)
    env = harness.api_env(database_url="postgresql+psycopg://nobody@127.0.0.1:9/edge_os_test_none",
                          public_pem=TestSigner().public_pem, previous_pem=None, cors=["http://127.0.0.1:3999"])
    return load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})


def handoff(root: Path, given: RelayApplicationDefinition, channel: str = CHANNEL, image_id: str | None = None,
            **changes: Any) -> dict[str, Any]:
    """What the lane-1 operator writes once for the relay it started (`edge-os.relay-operator-handoff/1`)."""
    actual = json.loads(given.record)
    relay = root / "relay"
    pinned = image_id or composition.image_for_platform(given, composition._host_platform())
    return {"format": "edge-os.relay-operator-handoff/1", "operation_id": "op-synthetic-1", "config_sha256": "e" * 64,
            "kind": "ACTUAL", "release_record": {"path": "/synthetic/release.json", "sha256": given.record_sha256},
            "release": {"release_id": actual["release_id"], "route_id": actual["route_id"], "kind": "ACTUAL",
                        "model": actual["model"], "max_output_tokens": actual["max_tokens"],
                        "max_request_bytes": actual["max_request_bytes"], "max_reply_bytes": actual["max_reply_bytes"]},
            "ca_bundle_sha256": actual["ca_bundle_sha256"], "image": {"reference": REFERENCE, "id": pinned},
            "endpoint": {"grants": str(relay / "grants"), "revocations": str(relay / "revocations"),
                         "state": str(relay / "state"), "admission_key_file": str(relay / "admission.key"),
                         "channel_root": channel, "heartbeat_max_age_seconds": 2.0},
            "evidence_dir": str(root / "jobs"), "shutdown_owner": "relay_operator", "started_at": 1_760_000_000.0,
            **changes}


def write_handoff(folder: Path, content: dict[str, Any] | bytes) -> tuple[Path, str]:
    raw = content if isinstance(content, bytes) else canonical(content)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "handoff.json"
    path.write_bytes(raw)
    path.chmod(0o444)
    return path, hashlib.sha256(raw).hexdigest()


def open_with(settings: Any, root: Path, located: tuple[Path, str] | None = None, **changes: Any) -> Any:
    path, sha = located or (root / "operator" / "handoff.json", "0" * 64)
    return open_hermes_application(settings, handoff_path=path, handoff_sha256=sha, run_id="rc-unit", **changes)


# --- Pure: refusals before any effect -------------------------------------------------------------------------------


def test_without_an_approved_definition_nothing_is_composed_and_nothing_is_touched(unreachable, approve,
                                                                                   tmp_path: Path) -> None:
    approve()  # explicitly empty registries, whatever the ordinary ones hold
    assert composition.RELEASE_DEFINITIONS == () and relay_admission.APPROVED_ACTUAL_RELEASES == frozenset()
    assert open_with(unreachable, tmp_path) is None  # the named handoff does not exist: it was never opened
    approve(definition(), UNAPPROVED)  # a definition whose record the registry does not list
    assert open_with(unreachable, tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_production_and_another_interpreter_are_refused_before_any_effect(unreachable, approve, tmp_path: Path) -> None:
    approve(definition())
    for settings in (unreachable.model_copy(update={"env": "production"}),
                     unreachable.model_copy(update={"interpreter": "fixture"})):
        with pytest.raises(MountRefused):
            open_with(settings, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_two_approved_definitions_are_refused_before_the_handoff_is_read(unreachable, approve, tmp_path: Path) -> None:
    approve(definition(), definition(record_fields={"release_id": "rel-app-synthetic-2"}))
    with pytest.raises(MountRefused, match="at most one"):
        open_with(unreachable, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_handoff_for_exactly_the_bound_release_gives_its_endpoint_and_evidence_folder(approve, tmp_path: Path) -> None:
    [given] = approve(definition())
    path, sha = write_handoff(tmp_path / "operator", handoff(tmp_path, given))
    found, evidence = composition._handoff(path, sha, bind_release(given))
    assert found == endpoint(tmp_path / "relay") and evidence == tmp_path / "jobs"


@pytest.mark.parametrize("target_platform, expected", [("linux/arm64", IMAGE), ("linux/amd64", AMD64_IMAGE)])
def test_each_admitted_platform_picks_its_own_pinned_id(approve, target_platform: str, expected: str) -> None:
    [given] = approve(definition())
    assert composition.image_for_platform(given, target_platform) == expected


@pytest.mark.parametrize("target_platform", ["linux/riscv64", "linux/arm64/v8", "windows/amd64", "", "LINUX/AMD64"])
def test_a_platform_outside_the_pair_is_refused_and_the_pair_is_named(approve, target_platform: str) -> None:
    [given] = approve(definition())
    with pytest.raises(MountRefused, match="linux/arm64 and linux/amd64"):
        composition.image_for_platform(given, target_platform)


@pytest.mark.parametrize("system, machine, expected", [
    ("Darwin", "arm64", "linux/arm64"), ("Darwin", "x86_64", "linux/amd64"),
    ("Linux", "aarch64", "linux/arm64"), ("Linux", "x86_64", "linux/amd64")])
def test_the_host_platform_is_read_as_a_docker_platform(system: str, machine: str, expected: str) -> None:
    assert composition._docker_platform(system, machine) == expected


@pytest.mark.parametrize("system, machine", [("Windows", "AMD64"), ("Linux", "riscv64"), ("Plan9", "mips")])
def test_a_host_outside_the_pair_is_refused_before_binding(system: str, machine: str) -> None:
    with pytest.raises(MountRefused, match="linux/arm64 and linux/amd64"):
        composition._docker_platform(system, machine)


def test_binding_selects_the_id_for_the_host_platform(approve, monkeypatch: pytest.MonkeyPatch) -> None:
    [given] = approve(definition())
    for target_platform, expected in (("linux/arm64", IMAGE), ("linux/amd64", AMD64_IMAGE)):
        monkeypatch.setattr(composition, "_host_platform", lambda target=target_platform: target)
        assert bind_release(given).image == expected


def test_no_environment_value_supplies_the_image_id(approve, monkeypatch: pytest.MonkeyPatch) -> None:
    [given] = approve(definition())
    monkeypatch.setattr(composition, "_host_platform", lambda: "linux/arm64")
    for name in ("EDGE_OS_HERMES_IMAGE", "EDGE_OS_HERMES_IMAGE_ID", "EDGE_OS_DOCKER_PLATFORM"):
        monkeypatch.setenv(name, AMD64_IMAGE)
    assert bind_release(given).image == IMAGE  # the code-owned pair alone decides


@pytest.mark.parametrize("images", [
    (("linux/arm64", IMAGE),),
    (("linux/arm64", IMAGE), ("linux/amd64", AMD64_IMAGE), ("linux/riscv64", IMAGE)),
    (("linux/arm64", IMAGE), ("windows/amd64", AMD64_IMAGE)),
    (("linux/arm64", IMAGE), ("linux/arm64", AMD64_IMAGE)),
    (("linux/arm64", IMAGE), ("linux/amd64", "edge-os/pinned-hermes:latest")),
    (("linux/arm64", "sha256:" + "D" * 64), ("linux/amd64", AMD64_IMAGE)),
    ("linux/arm64",),
])
def test_a_definition_that_does_not_pin_exactly_the_two_platforms_is_refused(approve, images: Any) -> None:
    [bad] = approve(definition(images=images))
    with pytest.raises(MountRefused, match="job image"):
        bind_release(bad)


def test_a_definition_that_pins_one_id_for_both_platforms_is_refused(approve) -> None:
    [bad] = approve(definition(images=(("linux/arm64", IMAGE), ("linux/amd64", IMAGE))))
    with pytest.raises(MountRefused, match="different Docker image id"):
        composition.image_for_platform(bad, "linux/arm64")


def test_a_listed_id_for_another_platform_is_refused_in_the_handoff(approve, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    [given] = approve(definition())
    monkeypatch.setattr(composition, "_host_platform", lambda: "linux/arm64")
    release = bind_release(given)
    content = handoff(tmp_path, given, image_id=AMD64_IMAGE)  # listed, but pinned for linux/amd64 only
    with pytest.raises(MountRefused, match="platform"):
        composition._handoff(*write_handoff(tmp_path / "operator", content), release)


def test_the_job_runs_the_exact_image_id_the_operator_started_whatever_its_local_tag(approve, tmp_path: Path) -> None:
    [given] = approve(definition())
    release = bind_release(given)
    for reference in (REFERENCE, "edge-os/pinned-hermes@sha256:" + "9" * 64, "x"):  # names only; Docker checked them
        content = handoff(tmp_path, given, image={"reference": reference, "id": release.image})
        composition._handoff(*write_handoff(tmp_path / reference.replace("/", "_"), content), release)
    app = compose_application(release, lazy_engine(), endpoint=endpoint(tmp_path / "relay"), run_id="rc-unit",
                              evidence_dir=tmp_path / "jobs")
    assert app.supervision.image == release.image  # the launch argument is the immutable id itself


def tampered(content: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**content, **changes}


@pytest.mark.parametrize("change", [
    lambda h: tampered(h, format="edge-os.relay-operator-handoff/2"),
    lambda h: tampered(h, extra="field"),
    lambda h: {k: v for k, v in h.items() if k != "started_at"},
    lambda h: tampered(h, kind="AUTHORED"),
    lambda h: tampered(h, release={**h["release"], "max_output_tokens": 2048}),
    lambda h: tampered(h, release_record={"path": "/synthetic/release.json", "sha256": "0" * 64}),
    lambda h: tampered(h, release_record=None),
    lambda h: tampered(h, ca_bundle_sha256="c" * 64),
    lambda h: tampered(h, image={"reference": REFERENCE, "id": "sha256:" + "f" * 64}),  # another image
    lambda h: tampered(h, image={"reference": REFERENCE, "id": "sha256:" + "D" * 64}),
    lambda h: tampered(h, image={"reference": REFERENCE, "id": "edge-os/pinned-hermes@" + IMAGE}),  # a registry digest
    lambda h: tampered(h, image={"reference": REFERENCE, "id": "latest"}),
    lambda h: tampered(h, image={"reference": "", "id": IMAGE}),
    lambda h: tampered(h, image={"reference": "a tag", "id": IMAGE}),
    lambda h: tampered(h, image={"reference": REFERENCE}),
    lambda h: tampered(h, image={"reference": REFERENCE, "id": IMAGE, "digest": IMAGE}),
    lambda h: tampered(h, shutdown_owner="application"),
    lambda h: tampered(h, endpoint={**h["endpoint"], "channel_root": "another-channel"}),
    lambda h: tampered(h, endpoint={**h["endpoint"], "grants": "relay/grants"}),
    lambda h: tampered(h, endpoint={**h["endpoint"], "provider_key_file": "/secret/key"}),
    lambda h: tampered(h, endpoint={**h["endpoint"], "heartbeat_max_age_seconds": 0}),
    lambda h: tampered(h, endpoint={**h["endpoint"], "heartbeat_max_age_seconds": 3600}),
    lambda h: tampered(h, endpoint={**h["endpoint"], "heartbeat_max_age_seconds": True}),
    lambda h: tampered(h, evidence_dir="jobs"),
])
def test_a_handoff_that_differs_from_the_bound_release_is_refused_before_any_engine(
        unreachable, approve, tmp_path: Path, change: Any) -> None:
    [given] = approve(definition())
    located = write_handoff(tmp_path / "operator", change(handoff(tmp_path, given)))
    with pytest.raises(MountRefused):
        open_with(unreachable, tmp_path, located)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["operator"]  # nothing else was created


def test_handoff_bytes_other_than_the_named_hash_a_link_a_folder_or_an_oversized_file_are_refused(
        unreachable, approve, tmp_path: Path) -> None:
    [given] = approve(definition())
    path, sha = write_handoff(tmp_path / "operator", handoff(tmp_path, given))
    link = tmp_path / "operator" / "link.json"
    link.symlink_to(path)
    big, big_sha = write_handoff(tmp_path / "big", canonical(handoff(tmp_path, given, operation_id="x" * 20_000)))
    for located in ((path, "0" * 64), (path, sha.upper()), (link, sha), (tmp_path / "operator", sha), (big, big_sha),
                    (tmp_path / "missing.json", sha)):
        with pytest.raises(MountRefused):
            open_with(unreachable, tmp_path, located)
    with pytest.raises(MountRefused):  # a repeated key: one reader must never see another reader's value
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "dup", canonical(handoff(tmp_path, given))[:-1]
                                                       + b',"kind":"AUTHORED"}'))


def test_the_factory_refuses_a_release_configuration_without_its_runner_local_interpreter_or_outside_production(
        unreachable, approve) -> None:
    approve(definition())
    config = bind_release(definition()).config
    runner = object()
    fixture = unreachable.model_copy(update={"interpreter": "fixture"})
    cases = [(fixture, None), (fixture, runner), (unreachable.model_copy(update={"env": "production"}), runner)]
    for settings, given in cases:
        with pytest.raises(ConfigError, match="release configuration"):  # before any engine: the database is unserved
            create_app(settings, hermes_runner=given, hermes_config=config)  # type: ignore[arg-type]


# --- Pure: one bound release identity ----------------------------------------------------------------------------


def test_an_approved_definition_binds_route_policy_model_schema_and_the_snapshot_price(
        approve, monkeypatch: pytest.MonkeyPatch) -> None:
    [given] = approve(definition())
    monkeypatch.setattr(composition, "_host_platform", lambda: "linux/arm64")
    release = bind_release(given)

    assert release.actual.record_sha256 == given.record_sha256 and release.actual.release.kind == "ACTUAL"
    assert (release.route.kind, release.route.endpoint_url, release.route.route_id) == (
        "ACTUAL", "https://openrouter.ai/api/v1/chat/completions", "route-app-synthetic")
    assert (release.policy.model, release.policy.max_output_tokens, release.policy.max_request_bytes) == (MODEL, 4096, 12_000)
    assert release.policy.required_extra == {"stream": False, "provider": ROUTING, "reasoning": {"effort": "low"},
                                             "response_format": SCHEMA}
    assert release.price == TokenPrice(Decimal("3.00"), Decimal("9.00")) and release.limits.price is release.price
    assert release.price_snapshot_sha256 == hashlib.sha256(given.price_snapshot).hexdigest()
    assert release.approval_sha256 == "a" * 64 and (release.image, release.channel_root) == (IMAGE, CHANNEL)
    config = release.config
    assert (config.model, config.route, config.max_output_tokens, config.runtime_label) == (
        MODEL, "route-app-synthetic", 4096, "LIVE")
    assert config.live_release is not None and (config.live_release.release_id, config.live_release.provider,
                                                config.live_release.budget_usd) == ("rel-app-synthetic-1", SLUG, "0.30")


def test_a_record_outside_the_trusted_registry_is_refused_even_when_well_formed() -> None:
    assert definition().record_sha256 not in relay_admission.APPROVED_ACTUAL_RELEASES  # the ordinary registry
    with pytest.raises(MountRefused, match="ActualReleaseUnapproved"):
        bind_release(definition())


def test_record_bytes_that_do_not_have_the_named_hash_are_refused(approve) -> None:
    [given] = approve(definition())
    with pytest.raises(MountRefused):
        bind_release(definition(record_sha256=given.record_sha256, record_fields={"max_tokens": 2048}))


def snapshot(**changes: Any) -> dict[str, Any]:
    return {key: value for key, value in {**SNAPSHOT, **changes}.items() if value is not None}


@pytest.mark.parametrize("given, why", [
    (canonical(SNAPSHOT) + b" ", "other bytes than the record names"),
    (canonical(snapshot(model="another-model/1")), "another model"),
    (canonical(snapshot(provider="another-provider")), "another provider"),
    (canonical(snapshot(prompt_usd_per_million="4.01")), "a rate above routing max_price"),
    (canonical(snapshot(prompt_usd_per_million="0")), "a zero rate"),
    (canonical(snapshot(prompt_usd_per_million="0.000")), "a zero rate written with decimals"),
    (canonical(snapshot(completion_usd_per_million="-1")), "a negative rate"),
    (canonical(snapshot(completion_usd_per_million=9)), "a JSON number instead of a decimal string"),
    (canonical(snapshot(completion_usd_per_million="9e0")), "an exponent"),
    (canonical(snapshot(completion_usd_per_million="NaN")), "not a number"),
    (canonical(snapshot(completion_usd_per_million=None)), "a missing rate"),
    (canonical(snapshot(cached_usd_per_million="1.00")), "an unknown field"),
    (b'{"model":"synthetic-model/1","model":"x","provider":"synthetic-provider","prompt_usd_per_million":"3.00",'
     b'"completion_usd_per_million":"9.00"}', "a repeated key"),
    (b"[]", "not an object"),
])
def test_a_price_snapshot_that_is_not_exactly_the_records_is_refused(approve, given: bytes, why: str) -> None:
    fields = {"price_snapshot_sha256": hashlib.sha256(given).hexdigest()} if why != "other bytes than the record names" else {}
    [bad] = approve(definition(record_fields=fields, snapshot=given))
    with pytest.raises(MountRefused):
        bind_release(bad)


@pytest.mark.parametrize("max_price", [{"prompt": 4}, {"prompt": True, "completion": 10}, {"prompt": "x", "completion": 10},
                                       {"prompt": float("inf"), "completion": 10}])
def test_a_routing_price_limit_that_cannot_bound_the_snapshot_is_refused(approve, max_price: dict[str, Any]) -> None:
    [bad] = approve(definition(record_fields={"provider": {**ROUTING, "max_price": max_price}}))
    with pytest.raises(MountRefused):
        bind_release(bad)


@pytest.mark.parametrize("changes", [
    {"response_format": None},
    {"response_format": {"type": "json_object"}},
    {"images": (("linux/arm64", "edge-os/pinned-hermes:latest"), ("linux/amd64", AMD64_IMAGE))},
    # a digest reference names an image; it is not the bare id
    {"images": (("linux/arm64", "edge-os/pinned-hermes@" + IMAGE), ("linux/amd64", AMD64_IMAGE))},
    {"images": (("linux/arm64", "sha256:" + "D" * 64), ("linux/amd64", AMD64_IMAGE))},
    {"images": (("linux/arm64", "d" * 64), ("linux/amd64", AMD64_IMAGE))},
    {"channel_root": "../app"},
])
def test_an_output_schema_image_or_channel_that_is_not_bound_is_refused(approve, changes: dict[str, Any]) -> None:
    [bad] = approve(definition(**changes))
    with pytest.raises(MountRefused):
        bind_release(bad)


def test_an_output_schema_is_refused_when_the_record_sends_none_and_omitted_it_binds(approve) -> None:
    fields = ["model", "messages", "stream", "provider", "reasoning", "max_tokens", "session_id"]
    [bad] = approve(definition(record_fields={"allowed_fields": fields}))
    with pytest.raises(MountRefused):
        bind_release(bad)
    [plain] = approve(definition(record_fields={"allowed_fields": fields}, response_format=None))
    assert "response_format" not in bind_release(plain).policy.required_extra


# --- Pure: composition holds one price and builds nothing ----------------------------------------------------------


def lazy_engine() -> Any:
    from sqlalchemy import create_engine
    return create_engine("postgresql+psycopg://nobody@127.0.0.1:9/edge_os_test_none")  # never connects here


def test_the_ledger_and_the_relay_runner_hold_the_same_token_price_object_and_construction_does_no_io(
        approve, tmp_path: Path) -> None:
    [given] = approve(definition())
    release = bind_release(given)
    app = compose_application(release, lazy_engine(), endpoint=endpoint(tmp_path / "relay"), run_id="rc-unit",
                              evidence_dir=tmp_path / "jobs")
    relay_runner = app.runner._delegate  # type: ignore[attr-defined] - accepted GuardedTurnRunner over RelayTurnRunner
    assert app.spend._configured.price is release.price  # what PostgresSpendLedger reserves and settles with
    assert relay_runner._price is release.price and relay_runner._actual is release.actual  # E1-COST1 check
    assert app.runner._policy is release.policy and app.config is release.config  # type: ignore[attr-defined]
    assert list(tmp_path.iterdir()) == []


def test_a_request_shape_changed_after_binding_a_foreign_channel_or_a_bad_run_id_is_refused(approve,
                                                                                           tmp_path: Path) -> None:
    [given] = approve(definition())
    options = {"endpoint": endpoint(tmp_path / "relay"), "run_id": "rc-unit", "evidence_dir": tmp_path / "jobs"}
    changed = bind_release(given)
    changed.policy.required_extra["provider"]["allow_fallbacks"] = True  # type: ignore[index]
    with pytest.raises(MountRefused, match="changed"):
        compose_application(changed, lazy_engine(), **options)
    with pytest.raises(MountRefused):
        compose_application(bind_release(given), lazy_engine(), **{**options, "endpoint": endpoint(tmp_path, "other")})
    with pytest.raises(MountRefused):
        compose_application(bind_release(given), lazy_engine(), **{**options, "run_id": "../run"})
    assert list(tmp_path.iterdir()) == []


def test_changing_the_definitions_routing_after_binding_does_not_reach_the_bound_release(approve) -> None:
    [given] = approve(definition())
    release = bind_release(given)
    release.actual.provider["allow_fallbacks"] = True  # the record's own object, outside the release's copies
    assert release.policy.required_extra["provider"]["allow_fallbacks"] is False
    assert not release.unchanged()  # and composition refuses: the record no longer matches what was bound


# --- Mounted: real PostgreSQL, synthetic provider ------------------------------------------------------------------


def reply_record(cost: float = float(CHARGE), **changes: Any) -> dict[str, Any]:
    return {"outcome": "reply", "status": 200, "cost": cost, "generation_id": "gen-synthetic-1",
            "usage": {"prompt_tokens": 1423, "completion_tokens": 611, "total_tokens": 2034}, **changes}


class StandInRelay:
    """Stands in for the relay process: a fresh heartbeat, the admission key, and the records the job's turn leaves."""

    def __init__(self, root: Path, release: Any) -> None:
        self.root, self.release = root, release
        for folder in ("grants", "revocations", "state"):
            (root / folder).mkdir(parents=True)
        (root / "admission.key").write_bytes(b"k" * 32)
        self._stop = threading.Event()
        self._beat = threading.Thread(target=self._run, daemon=True)
        self._write_beat()
        self._beat.start()

    def _write_beat(self) -> None:
        beat = self.root / "state" / ".heartbeat.tmp"
        beat.write_text(json.dumps({"release": self.release.settings(), "at": time.time(), "started_at": 0}))
        beat.replace(self.root / "state" / "heartbeat.json")

    def _run(self) -> None:
        while not self._stop.wait(0.2):
            self._write_beat()

    def stop(self) -> None:
        self._stop.set()
        self._beat.join(timeout=2)

    def grants(self) -> list[dict[str, Any]]:
        return [json.loads(path.read_text()) for path in sorted((self.root / "grants").glob("*.json"))]


class StandInJob:
    """Stands in for the container job behind the accepted identity checks: each item is (relay records, job report)."""

    def __init__(self, relay: StandInRelay, *script: tuple[dict[str, Any] | None, HermesTurnResult]) -> None:
        self.relay, self.script, self.turns = relay, list(script), []

    def run_turn(self, turn: HermesTurn) -> HermesTurnResult:
        self.turns.append(turn)
        records, result = self.script.pop(0)
        folder = self.relay.root / "state" / turn.attempt_id
        folder.mkdir()
        if records is not None:  # None: the relay left no closed record (killed, or its reply never came)
            (folder / "closed.json").write_text(json.dumps({"started": True}))
            (folder / "finished.json").write_text(json.dumps(records))
        return job_report(result, route="route-app-synthetic")(turn)


RETURNED = turn_result(case("concrete-thesis")["provider"])


@pytest.fixture
def mounted(env, migrated, client, approve, tmp_path: Path) -> Iterator[Any]:
    """`build(name, *script)` opens the composition over the session database and an application over it."""
    [given] = approve(definition())
    release = bind_release(given)
    relay = StandInRelay(tmp_path / "relay", release.actual.release)
    located = write_handoff(tmp_path / "operator", handoff(tmp_path, given))
    empty_spend_ledger(client.app.state.session_factory)
    opened: list[tuple[Any, TestClient]] = []
    settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})

    def build(name: str, job: StandInJob) -> tuple[Any, TestClient]:
        app = open_hermes_application(settings, handoff_path=located[0], handoff_sha256=located[1],
                                      run_id=f"rc-{name}", close_budget_seconds=0.3)
        assert app is not None
        app.supervision.run_turn = job.run_turn  # the job only; guard, relay runner, identity check and ledger stay real
        app_client = TestClient(create_app(settings, hermes_runner=app.runner, hermes_config=app.config))
        app_client.__enter__()
        opened.append((app, app_client))
        return app, app_client

    build.relay = relay  # type: ignore[attr-defined]
    yield build
    for app, app_client in opened:
        app_client.__exit__(None, None, None)
        app.close()
    relay.stop()
    empty_spend_ledger(client.app.state.session_factory)


def saved(app_client: TestClient, attempt_id: str) -> dict[str, Any]:
    [row] = rows(app_client, "SELECT a.owner_id, a.intake_record_id, a.runtime_label, a.config, r.owner_id, "
                             "r.intake_record_id, r.state, r.reserved_nano_usd, r.charged_nano_usd FROM "
                             "interpretation_attempts a JOIN usage_local.provider_spend_reservations r USING (attempt_id) "
                             "WHERE a.attempt_id = :a", a=attempt_id)
    keys = ("owner", "intake", "runtime_label", "config", "reserved_owner", "reserved_intake", "state", "reserved", "charged")
    return dict(zip(keys, row))


def test_a_saved_request_is_sent_once_settled_at_the_snapshot_price_reopened_elsewhere_and_denied_to_another_owner(
        mounted, owner_a, owner_b) -> None:
    job = StandInJob(mounted.relay, (reply_record(), RETURNED))
    app, first = mounted("first", job)

    created = first.post("/v1/research/requests", json=dict(case("concrete-thesis")["intake"]), headers=owner_a)

    assert created.status_code == 201, created.text
    [attempt] = created.json()["attempts"]
    attempt_id = attempt["attempt_id"]
    assert (attempt["status"], attempt["parse_result"], attempt["request_count"]) == ("COMPLETED", "ACCEPTED", 1)
    assert attempt["spend"] == {"state": "SETTLED", "charge_usd": str(CHARGE)}
    row = saved(first, attempt_id)
    assert (row["reserved_owner"], row["reserved_intake"]) == (row["owner"], row["intake"])
    assert (row["state"], row["reserved"], row["charged"]) == ("SETTLED", int(RESERVATION * 10**9), int(CHARGE * 10**9))
    assert row["runtime_label"] == "LIVE" and row["config"]["model"] == MODEL  # the synthetic record's model
    assert row["config"]["live_release_id"] == "rel-app-synthetic-1"
    [grant] = mounted.relay.grants()
    assert (grant["owner_id"], grant["request_id"], grant["scope"], grant["attempt_id"]) == (
        str(row["owner"]), str(row["intake"]), f"intake:{row['intake']}", attempt_id)
    assert [turn.attempt_id for turn in job.turns] == [attempt_id] and app.spend.committed_usd() == CHARGE

    _again, reopened = mounted("reopen", StandInJob(mounted.relay))  # another application instance serves the reopen
    path = f"/v1/research/requests/{created.json()['intake']['record_id']}"
    again = reopened.get(path, headers=owner_a)
    assert again.status_code == 200 and again.json()["attempts"] == created.json()["attempts"]
    assert again.json()["head"] == created.json()["head"]
    assert reopened.get(path, headers=owner_b).status_code == 404
    assert rows(reopened, "SELECT count(*) FROM usage_local.provider_spend_reservations") == [(1,)]
    assert len(job.turns) == 1 and len(mounted.relay.grants()) == 1


@pytest.mark.parametrize("cost", [0.0074285, 0.009767, 0.0097681, 0.05])  # the LOCAL price, one nano-USD either side, above
def test_a_provider_cost_other_than_the_snapshot_price_keeps_the_whole_reservation_and_is_never_resent(
        mounted, owner_a, cost: float) -> None:
    job = StandInJob(mounted.relay, (reply_record(cost=cost), RETURNED))
    app, app_client = mounted("cost", job)

    bundle = create(app_client, owner_a, "concrete-thesis").json()

    [attempt] = bundle["attempts"]
    assert (attempt["status"], attempt["parse_result"], attempt["error_class"]) == (
        "UNKNOWN", "NOT_PARSED", "RelayCostUnverified")
    assert attempt["spend"] == {"state": "UNKNOWN", "charge_usd": str(RESERVATION)}
    assert bundle["head"]["interpretation_revision_id"] is None
    assert retry(app_client, owner_a, bundle, attempt["attempt_id"]).status_code == 409
    assert len(job.turns) == 1 and len(mounted.relay.grants()) == 1 and app.spend.committed_usd() == RESERVATION


@pytest.mark.parametrize("records, result", [
    (reply_record(outcome="lost", status=None), HermesTurnResult("UNKNOWN", None, RETURNED.usage, None, {}, "TransportLost")),
    (None, HermesTurnResult("TIMED_OUT", None, RETURNED.usage.__class__(), None, {}, "TimeoutExpired")),
    (None, RETURNED),  # a reply the job saw, but the relay never recorded its close: a late or cancelled response
])
def test_an_interrupted_attempt_keeps_unknown_liability_across_a_restart_and_is_never_resent(
        mounted, owner_a, records: dict[str, Any] | None, result: HermesTurnResult) -> None:
    job = StandInJob(mounted.relay, (records, result))
    app, app_client = mounted("interrupted", job)

    bundle = create(app_client, owner_a, "concrete-thesis").json()
    [attempt] = bundle["attempts"]
    assert attempt["parse_result"] != "ACCEPTED" and attempt["spend"] == {"state": "UNKNOWN",
                                                                         "charge_usd": str(RESERVATION)}

    restarted, restarted_client = mounted("interrupted", StandInJob(mounted.relay))  # same run id: a restarted process
    path = f"/v1/research/requests/{bundle['intake']['record_id']}"
    assert restarted_client.get(path, headers=owner_a).json()["attempts"][0]["spend"]["state"] == "UNKNOWN"
    assert retry(restarted_client, owner_a, bundle, attempt["attempt_id"]).status_code == 409
    assert restarted.spend.state(attempt["attempt_id"]) == "UNKNOWN" and restarted.spend.committed_usd() == RESERVATION
    assert len(job.turns) == 1 and len(mounted.relay.grants()) == 1


def test_two_instances_share_one_owner_cap_and_a_refused_reservation_never_reaches_the_job(mounted, owner_a,
                                                                                          owner_b) -> None:
    hang = HermesTurnResult("TIMED_OUT", None, RETURNED.usage.__class__(), None, {}, "TimeoutExpired")
    first_job = StandInJob(mounted.relay, (None, hang))
    second_job = StandInJob(mounted.relay, (None, hang), (reply_record(), RETURNED))
    first, first_client = mounted("share-a", first_job)
    _second, second_client = mounted("share-b", second_job)

    # Owner A's two timed-out attempts, one in each instance, hold 0.146112 of the 0.15 owner cap.
    assert create(first_client, owner_a, "concrete-thesis").json()["attempts"][0]["spend"]["state"] == "UNKNOWN"
    assert create(second_client, owner_a, "concrete-thesis").json()["attempts"][0]["spend"]["state"] == "UNKNOWN"
    refused = create(first_client, owner_a, "concrete-thesis").json()["attempts"][0]

    assert (refused["status"], refused["error_class"], refused["request_count"]) == ("PROVIDER_FAILED", "SpendCapReached", 0)
    assert len(first_job.turns) == 1 and len(second_job.turns) == 1 and len(mounted.relay.grants()) == 2
    other_owner = create(second_client, owner_b, "concrete-thesis").json()["attempts"][0]  # 0.219168 of the 0.30 global
    assert other_owner["spend"] == {"state": "SETTLED", "charge_usd": str(CHARGE)}
    assert first.spend.committed_usd() == RESERVATION * 2 + CHARGE
    assert rows(first_client, "SELECT count(*) FROM usage_local.provider_spend_reservations") == [(3,)]


def test_a_reservation_that_no_longer_names_the_saved_owner_gets_no_grant_and_is_released(
        mounted, owner_a, monkeypatch: pytest.MonkeyPatch) -> None:
    job = StandInJob(mounted.relay, (reply_record(), RETURNED))
    app, app_client = mounted("subject", job)
    reserve, moved = app.spend.reserve, []

    def reserve_then_move(attempt_id: str, **kwargs: Any) -> Any:
        made = reserve(attempt_id, **kwargs)
        moved.extend(rows(app_client, "UPDATE usage_local.provider_spend_reservations SET owner_id = gen_random_uuid() "
                                      "WHERE attempt_id = :a RETURNING owner_id", a=attempt_id))
        return made

    monkeypatch.setattr(app.spend, "reserve", reserve_then_move)

    [attempt] = create(app_client, owner_a, "concrete-thesis").json()["attempts"]

    assert (attempt["status"], attempt["request_count"], attempt["error_class"]) == (
        "PROVIDER_FAILED", 0, "RelaySubjectUnavailable")
    assert app.spend.state(attempt["attempt_id"]) == "RELEASED" and job.turns == [] and mounted.relay.grants() == []
    [(new_owner,)] = moved  # exactly one reservation row was moved before the subject check
    row = saved(app_client, attempt["attempt_id"])
    assert row["reserved_owner"] == new_owner != row["owner"]
