"""With several approved releases, the operator's handoff selects one, and it can select nothing else.

Seam: `open_hermes_application`. The handoff is hash-checked first. It can name only a code-owned record whose hash is in
both registries, and without a handoff nothing starts: no default exists.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_hermes_relay_composition import (  # noqa: F401 - fixtures
    approve, definition, handoff, open_with, unreachable, write_handoff,
)
from test_hosted_relay_admission import hosted_settings, no_engine

from edge_os_api.core.settings import load_settings
from edge_os_api.research import hermes_relay_composition as composition
from edge_os_api.research.hermes_relay_composition import open_hermes_application
from edge_os_api.research.hermes_transport_mount import MountRefused

import relay_admission  # noqa: E402 - on the path once the composition module is imported


def two() -> tuple[Any, Any]:
    return definition(), definition(record_fields={"release_id": "rel-app-synthetic-2", "route_id": "route-app-second"})


@pytest.fixture
def opened(env, migrated, approve, tmp_path: Path) -> Iterator[Any]:  # noqa: F811
    """`select(given)` opens the application over the session database through a handoff that names `given`."""
    apps: list[Any] = []
    settings = load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})

    def select(given: Any) -> Any:
        located = write_handoff(tmp_path / given.record_sha256[:8], handoff(tmp_path, given))
        app = open_hermes_application(settings, handoff_path=located[0], handoff_sha256=located[1], run_id="rc-select")
        apps.append(app)
        return app

    yield select
    for app in apps:
        app.close()


@pytest.mark.parametrize("chosen", [0, 1])
def test_the_handoff_selects_exactly_the_release_it_names(approve, opened, chosen: int) -> None:  # noqa: F811
    releases = approve(*two())
    app = opened(releases[chosen])
    assert app.release.actual.record_sha256 == releases[chosen].record_sha256
    assert app.config.route == app.release.actual.release.route_id == (
        ("route-app-synthetic", "route-app-second")[chosen])
    assert app.spend._route_id == app.config.route  # the ledger serves the selected route


def test_with_several_approved_releases_no_handoff_starts_nothing(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    approve(*two())
    with pytest.raises(MountRefused, match="handoff cannot be opened"):
        open_with(unreachable, tmp_path)


def test_with_one_approved_release_no_handoff_still_starts_nothing(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    approve(definition())
    with pytest.raises(MountRefused, match="handoff cannot be opened"):
        open_with(unreachable, tmp_path)


def test_a_handoff_whose_bytes_are_not_the_named_hash_is_refused(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    first, _second = approve(*two())
    path, _sha = write_handoff(tmp_path / "operator", handoff(tmp_path, first))
    with pytest.raises(MountRefused, match="named hash"):
        open_with(unreachable, tmp_path, (path, "0" * 64))


def test_a_handoff_naming_an_unknown_record_is_refused(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    first, _second = approve(*two())
    named = handoff(tmp_path, first, release_record={"path": "/synthetic/release.json", "sha256": "f" * 64})
    with pytest.raises(MountRefused, match="no approved release"):
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "operator", named))


def test_a_handoff_naming_a_definition_that_is_not_approved_is_refused(  # the definition registry only
        unreachable, approve, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    first, second = approve(*two())
    monkeypatch.setattr(relay_admission, "APPROVED_ACTUAL_RELEASES", frozenset({first.record_sha256}))
    with pytest.raises(MountRefused, match="no approved release"):
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "operator", handoff(tmp_path, second)))


def test_a_handoff_naming_an_approved_hash_with_no_definition_is_refused(  # the approved registry only
        unreachable, approve, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    first, second = approve(*two())
    monkeypatch.setattr(composition, "RELEASE_DEFINITIONS", (first,))
    with pytest.raises(MountRefused, match="no approved release"):
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "operator", handoff(tmp_path, second)))


@pytest.mark.parametrize("record", [None, [], "x", {}, {"path": "/x"}, {"sha256": 7}])
def test_a_handoff_with_no_readable_record_hash_is_refused(unreachable, approve, tmp_path: Path, record: Any) -> None:  # noqa: F811
    first, _second = approve(*two())
    with pytest.raises(MountRefused):
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "operator", handoff(tmp_path, first, release_record=record)))


def test_a_handoff_may_not_pair_one_record_with_another_releases_settings(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    first, second = approve(*two())
    mixed = {**handoff(tmp_path, first), "release_record": handoff(tmp_path, second)["release_record"]}
    with pytest.raises(MountRefused, match="not for this release"):
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "operator", mixed))


def test_two_definitions_of_one_record_select_nothing(unreachable, approve, tmp_path: Path) -> None:  # noqa: F811
    given = definition()
    approve(given, given)
    with pytest.raises(MountRefused, match="no approved release"):
        open_with(unreachable, tmp_path, write_handoff(tmp_path / "operator", handoff(tmp_path, given)))


def test_production_refuses_a_selected_release_its_deployment_does_not_name(  # noqa: F811
        approve, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = approve(*two())
    monkeypatch.setattr(composition, "make_engine", no_engine)
    settings = hosted_settings(tmp_path, monkeypatch, relay_id="rel-app-synthetic-1", relay_sha=first.record_sha256)
    with pytest.raises(MountRefused, match="does not approve"):
        open_with(settings, tmp_path, write_handoff(tmp_path / "operator", handoff(tmp_path, second)))


def test_the_real_registries_agree_and_each_approved_record_has_one_definition() -> None:
    hashes = [item.record_sha256 for item in composition.RELEASE_DEFINITIONS]
    assert sorted(hashes) == sorted(relay_admission.APPROVED_ACTUAL_RELEASES)
    assert all(hashlib.sha256(item.record).hexdigest() == item.record_sha256 for item in composition.RELEASE_DEFINITIONS)
