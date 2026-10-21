"""Production admission of the Hermes relay application through one approved hosted deployment record.

Pure tests (no database, Docker or network). The synthetic relay definition is admitted by patching the relay's trusted
registry inside the test; it is not an approved release. A test patches the hosted-deployment registry with a synthetic
record. Only the record's exact relay release id and record SHA-256 pass the hosted gate; everything else is refused
before the handoff, an engine or Docker is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from edge_os_api.core import hosted_deployment
from edge_os_api.core.settings import load_settings
from edge_os_api.research import hermes_relay_composition as composition
from edge_os_api.research.hermes_relay_composition import open_hermes_application
from edge_os_api.research.hermes_transport_mount import MountRefused
from test_hermes_relay_composition import approve, definition, unreachable  # noqa: F401 - fixtures by name
from test_hosted_deployment import (  # noqa: F401 - shared record helpers
    DEPLOYMENT, approve as approve_deployment, production_env, record as deployment_record,
    write_record as write_deployment,
)

OTHER_ID = "rel-app-synthetic-2"


def hosted_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *,
                    relay_id: str = "rel-app-synthetic-1", relay_sha: str = "0" * 64,
                    interpreter: str = "hermes_local", with_record: bool = True) -> Any:
    value = deployment_record(hermes_relay={"release_id": relay_id, "record_sha256": relay_sha})
    path, sha = write_deployment(tmp_path, value)
    approve_deployment(monkeypatch, value, sha)
    changes = {"EDGE_OS_INTERPRETER": interpreter}
    if with_record:
        changes.update({"EDGE_OS_HOSTED_DEPLOYMENT_ID": DEPLOYMENT,
                        "EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH": str(path)})
    return load_settings(production_env(**changes))


def open_with(settings: Any, root: Path) -> Any:
    return open_hermes_application(settings, handoff_path=root / "operator" / "handoff.json",
                                   handoff_sha256="0" * 64, run_id="hosted-unit")


def no_engine(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("an engine was opened before the refusal")


def test_production_without_a_record_keeps_the_existing_refusal(unreachable, tmp_path: Path) -> None:
    settings = load_settings(production_env())
    with pytest.raises(MountRefused, match="deployment is qualified"):
        open_with(settings, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_production_refuses_the_relay_with_the_fixture_interpreter(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = hosted_settings(tmp_path, monkeypatch, interpreter="fixture")
    with pytest.raises(MountRefused, match="EDGE_OS_INTERPRETER"):
        open_with(settings, tmp_path)


def test_production_admits_the_bound_relay_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    given = definition()
    monkeypatch.setattr(composition, "RELEASE_DEFINITIONS", (given,))
    monkeypatch.setattr(composition.relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({given.record_sha256}))
    monkeypatch.setattr(composition, "make_engine", no_engine)
    settings = hosted_settings(tmp_path, monkeypatch, relay_id="rel-app-synthetic-1",
                              relay_sha=given.record_sha256)
    # The gate and the release binding pass; the missing handoff is the next refusal, before any engine.
    with pytest.raises(MountRefused, match="handoff cannot be opened"):
        open_with(settings, tmp_path)


def test_production_refuses_a_record_naming_another_relay_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    given = definition()
    monkeypatch.setattr(composition, "RELEASE_DEFINITIONS", (given,))
    monkeypatch.setattr(composition.relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({given.record_sha256}))
    settings = hosted_settings(tmp_path, monkeypatch, relay_id=OTHER_ID, relay_sha=given.record_sha256)
    with pytest.raises(MountRefused, match="does not approve"):
        open_with(settings, tmp_path)


def test_production_refuses_a_record_with_another_relay_record_hash(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    given = definition()
    monkeypatch.setattr(composition, "RELEASE_DEFINITIONS", (given,))
    monkeypatch.setattr(composition.relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({given.record_sha256}))
    settings = hosted_settings(tmp_path, monkeypatch, relay_id="rel-app-synthetic-1", relay_sha="f" * 64)
    with pytest.raises(MountRefused, match="does not approve"):
        open_with(settings, tmp_path)


def test_local_admission_is_unchanged(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    approve()  # explicitly empty relay registries, whatever the ordinary ones hold
    assert hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS == {}
    assert open_with(unreachable, tmp_path) is None
    assert list(tmp_path.iterdir()) == []
