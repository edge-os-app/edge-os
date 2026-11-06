"""The registered Orbio hosted record: what it binds, what it replaces and how production starts with it.

Pure tests (no database, Docker or network). Expected values are literals from the approved release documents, not
values read back from the code under test. The clock is fixed inside the record's window so these tests do not expire.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from edge_os_api import main as main_module
from edge_os_api.core import hosted_deployment
from edge_os_api.core.research.operating_release import APPROVED_RELEASES
from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.research import hermes_relay_composition as composition
from edge_os_api.research.hermes_relay_composition import open_hermes_application
from edge_os_api.research.hermes_transport_mount import MountRefused
from test_hermes_relay_composition import handoff, write_handoff
from test_hosted_deployment import production_env

REPO = Path(__file__).resolve().parents[3]
RECORDS = REPO / "docs/qualification/hosted-gates/records"
RECORD_ID = "edgeos-fun-vps1-orbio"
RECORD_PATH = RECORDS / f"{RECORD_ID}.json"
RECORD_SHA = "75aa306039ce54b8817b4ebb5f17fcd2f81fcb137a2f410a4f967a2a9cc2a201"
ORBIO_ID = "orbio-first-call-1"
ORBIO_SHA = "041f588d3b9564fd605d00d2204083cbfc4e4cd3307906656345a73118ac563f"
OPENROUTER_ID = "hermes-first-call-1"
OPENROUTER_SHA = "3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f"
RESEARCH_ID = "actual-moe-history2h-nansen-20261022/1"
RESEARCH_SHA = "45c8cfbf5d61eb519ee3140e02e50b2b7091669dc28cbef224bdc6a0e77ca877"
OLD_ID = "edgeos-fun-vps1"
OLD_CANONICAL_SHA = "0e56ad4290b522d450142c5baa367b5daacf695dfe563102e85bc43f0bb7b728"
OLD_VALUES_FILE_SHA = "263f9627564b73bf0b58d97d0f1012963754c9f6e92af2c56ba809ce939e3bed"
SNAPSHOT_AUTO_DELETION = datetime(2026, 11, 29, tzinfo=UTC)  # h10_backup_restore.md: the record must end before it
INSIDE_WINDOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


class FixedClock(datetime):
    """`hosted_deployment.datetime` with `now` fixed inside the record's window."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return INSIDE_WINDOW


class EngineReached(Exception):
    """Every admission check passed: the application asked for its database engine."""


@pytest.fixture
def inside_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hosted_deployment, "datetime", FixedClock)


@pytest.fixture
def record() -> dict[str, Any]:
    return json.loads(RECORD_PATH.read_bytes())


def old_record() -> dict[str, Any]:
    return json.loads((RECORDS / f"{OLD_ID}.json").read_bytes())


def hosted_env(deployment_id: str = RECORD_ID, record_path: Path = RECORD_PATH, **changes: str) -> dict[str, str]:
    """The host research worker's production shape: the loopback database route under the record's TLS mode."""
    return production_env(
        EDGE_OS_DATABASE_URL="postgresql+psycopg://app@127.0.0.1:5432/edge_os?sslmode=require",
        EDGE_OS_CORS_ALLOWED_ORIGINS="https://app.edgeos.fun",
        EDGE_OS_HOSTED_DEPLOYMENT_ID=deployment_id,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(record_path),
        **changes)


def release_named(release_id: str) -> Any:
    return next(item for item in composition.RELEASE_DEFINITIONS if json.loads(item.record)["release_id"] == release_id)


def open_selected(settings: Any, root: Path, given: Any) -> Any:
    path, sha = write_handoff(root / "operator", handoff(root, given, channel=given.channel_root))
    return open_hermes_application(settings, handoff_path=path, handoff_sha256=sha, run_id="hosted-orbio-unit")


def test_the_registry_names_only_the_orbio_record(record: dict[str, Any]) -> None:
    assert hashlib.sha256(hosted_deployment.canonical(record)).hexdigest() == RECORD_SHA
    assert dict(hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS) == {RECORD_ID: RECORD_SHA}
    assert record["deployment_id"] == RECORD_ID
    assert RECORD_PATH.read_bytes() == hosted_deployment.canonical(record)


def test_the_record_binds_the_exact_orbio_and_research_releases(record: dict[str, Any]) -> None:
    assert record["hermes_relay"] == {"release_id": ORBIO_ID, "record_sha256": ORBIO_SHA}
    assert record["research_release"] == {"release_id": RESEARCH_ID, "sha256": RESEARCH_SHA}
    assert release_named(ORBIO_ID).record_sha256 == ORBIO_SHA
    assert composition.relay_admission.APPROVED_ACTUAL_RELEASES >= {ORBIO_SHA}
    assert APPROVED_RELEASES[RESEARCH_ID] == RESEARCH_SHA


def test_the_values_file_holds_the_same_fields_as_the_record(record: dict[str, Any]) -> None:
    values = json.loads((RECORDS / f"{RECORD_ID}.values.json").read_bytes())
    assert {**values, "schema_version": hosted_deployment.RECORD_VERSION} == record


def test_only_the_named_fields_differ_from_the_old_record(record: dict[str, Any]) -> None:
    old = old_record()
    assert {name for name in record if record[name] != old[name]} == {
        "deployment_id", "hermes_relay", "host_gates", "valid_from"}
    assert {name for name in record["host_gates"] if record["host_gates"][name] != old["host_gates"][name]} == {
        "h8_provider_spend_cap"}


def test_every_host_gate_reference_matches_its_file_bytes(record: dict[str, Any]) -> None:
    for gate in record["host_gates"].values():
        assert hashlib.sha256((REPO / gate["path"]).read_bytes()).hexdigest() == gate["sha256"], gate["path"]


def test_the_spend_gate_names_the_orbio_account(record: dict[str, Any]) -> None:
    text = (REPO / record["host_gates"]["h8_provider_spend_cap"]["path"]).read_text(encoding="utf-8")
    assert "Orbio" in text


def test_the_window_opens_at_the_replacement_and_ends_before_the_snapshot_is_deleted(record: dict[str, Any]) -> None:
    assert record["valid_from"] == "2026-11-06T00:00:00Z"
    end = datetime.strptime(record["valid_until"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert end < SNAPSHOT_AUTO_DELETION


def test_the_old_record_keeps_its_frozen_bytes() -> None:
    assert hashlib.sha256(hosted_deployment.canonical(old_record())).hexdigest() == OLD_CANONICAL_SHA
    assert (hashlib.sha256((RECORDS / f"{OLD_ID}.values.json").read_bytes()).hexdigest() == OLD_VALUES_FILE_SHA)


@pytest.mark.usefixtures("inside_window")
def test_production_starts_with_the_new_record_and_admits_only_orbio() -> None:
    settings = load_settings(hosted_env())
    deployment = hosted_deployment.check_hosted_deployment(settings)
    assert deployment is not None and deployment.deployment_id == RECORD_ID
    assert deployment.admits_hermes_relay(ORBIO_ID, ORBIO_SHA)
    assert deployment.admits_hermes_release_id(ORBIO_ID)
    assert not deployment.admits_hermes_relay(OPENROUTER_ID, OPENROUTER_SHA)
    assert not deployment.admits_hermes_release_id(OPENROUTER_ID)
    assert deployment.admits_research_release(RESEARCH_ID, RESEARCH_SHA)
    assert deployment.admits_execution_release("anything/1", "0" * 64) is False


@pytest.mark.usefixtures("inside_window")
def test_the_api_starts_in_production_with_the_new_record_and_composes_the_research_release(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "make_engine", lambda *_a, **_k: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(main_module, "require_head", lambda _engine: None)
    monkeypatch.setattr(main_module, "make_session_factory", lambda _engine: (lambda: SimpleNamespace()))
    app = main_module.create_app(load_settings(hosted_env()))
    assert app.state.research_runtime.release.release_id == RESEARCH_ID
    assert app.state.research_runtime.release_sha256 == RESEARCH_SHA


@pytest.mark.usefixtures("inside_window")
def test_production_refuses_the_old_record_after_the_replacement() -> None:
    with pytest.raises(ConfigError, match="hosted_deployment_not_approved"):
        load_settings(hosted_env(OLD_ID, RECORDS / f"{OLD_ID}.json"))


def test_production_refuses_the_new_record_after_its_window(monkeypatch: pytest.MonkeyPatch) -> None:
    class Expired(FixedClock):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 11, 27, tzinfo=UTC)

    monkeypatch.setattr(hosted_deployment, "datetime", Expired)
    with pytest.raises(ConfigError, match="hosted_deployment_outside_window"):
        load_settings(hosted_env())


@pytest.mark.usefixtures("inside_window")
def test_the_relay_application_admits_the_orbio_handoff(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def engine_reached(*_args: Any, **_kwargs: Any) -> None:
        raise EngineReached

    monkeypatch.setattr(composition, "make_engine", engine_reached)
    settings = load_settings(hosted_env(EDGE_OS_INTERPRETER="hermes_local"))
    with pytest.raises(EngineReached):
        open_selected(settings, tmp_path, release_named(ORBIO_ID))


@pytest.mark.usefixtures("inside_window")
def test_the_relay_application_refuses_the_openrouter_handoff(tmp_path: Path) -> None:
    settings = load_settings(hosted_env(EDGE_OS_INTERPRETER="hermes_local"))
    with pytest.raises(MountRefused, match="does not approve"):
        open_selected(settings, tmp_path, release_named(OPENROUTER_ID))
