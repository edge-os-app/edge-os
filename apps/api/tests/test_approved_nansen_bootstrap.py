"""The server default registers and composes exactly one approved MOE history plus Nansen release (#58 NANSEN-RUNTIME-RELEASE-L4).

Runs with `--noconftest`: no database, socket or provider. A recording stand-in for `os.environ` holding only literal
fake sentinels is installed before any project import, so the real environment is never consulted and every looked-up
slot is counted. Unlike `test_environment_runtime_bootstrap.py`, this file does not replace the code-owned registries:
it pins the exact production default, its literal release SHA-256 and its literal report request. See
`docs/qualification/research-provider-composition/NANSEN_ACTUAL_RELEASE.md`.
"""

from __future__ import annotations

import dataclasses
import importlib
import logging
import os
import socket
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

RELEASE_ID = "actual-moe-history-nansen-20261022/1"
RELEASE_SHA256 = "2d359daca6f9ca131ee6f90ca1efb97a6f12af4aa285104ebd062366648564c5"
# The one report request the release permits, pinned independently of the definition it must match.
EXPECTED_REQUEST: dict[str, Any] = {
    "token_address": "0xd8e004acba279417c04c0633cb5a21ceca207777",
    "token_symbol": "MOE",
    "window": {"start_utc": "2026-10-21T07:55:00Z", "end_utc": "2026-10-22T07:55:00Z"},
    "operations": ["holders", "flows"],
    "holder_query": {"label_type": "all_holders", "aggregate_by_entity": False, "order_field": "token_amount",
                     "value_usd_min": None},
    "flow_query": {"label": "top_100_holders"},
    "limits": {"max_requests": 2, "max_pages": 1, "max_bytes": 2000000, "max_credits": "6", "per_page": 100},
    "deadline_seconds": 300,
    "compute_seconds": 300,
}


class RecordingEnviron(dict[str, str]):
    """A stand-in for `os.environ` that records every key looked up, in order."""

    def __init__(self, values: dict[str, str]) -> None:
        super().__init__(values)
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        return super().__getitem__(key)

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        self.lookups.append(key)
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        self.lookups.append(str(key))
        return super().__contains__(key)

    def __iter__(self) -> Iterator[str]:
        self.lookups.append("<iterated>")
        return super().__iter__()

    def copy(self) -> dict[str, str]:
        self.lookups.append("<copied>")
        return dict(self)


def _fake_environ(*, with_nansen: bool = True) -> RecordingEnviron:
    values = {"HYPERSYNC_API_KEY": "fake-hypersync-SENTINEL-b7c8d9",
              "QUICKNODE_API_URL": "https://quicknode.bootstrap-test.example/fake-quicknode-SENTINEL-e1f2a3/"}
    if with_nansen:
        values["NANSEN_API_KEY"] = "fake-nansen-SENTINEL-4b5c6d"
    return RecordingEnviron(values)


# The fake is in place before the first project import, so an import-time environment read would be recorded here.
IMPORT_ENVIRON = _fake_environ()
_real_environ, os.environ = os.environ, IMPORT_ENVIRON  # type: ignore[assignment]
try:
    from edge_os_api.core.research import operating_release, released_runtime_bootstrap
    from edge_os_api.core.research.operating_release import ReleaseRefused, release_sha256
    from edge_os_api.core.research.released_source_runtime import NansenHttpFactory, nansen_request, prepare_nansen
finally:
    os.environ = _real_environ

SETTINGS = SimpleNamespace(env="local")


@pytest.fixture
def environ(monkeypatch: pytest.MonkeyPatch) -> RecordingEnviron:
    recording = _fake_environ()
    monkeypatch.setattr(os, "environ", recording)
    return recording


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> None:
        opened.append(args)
        raise AssertionError("a socket was opened")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return opened


def _definition() -> Any:
    return released_runtime_bootstrap.RELEASE_DEFINITIONS[RELEASE_ID]


def test_importing_the_default_reads_no_credential_and_never_the_whole_environment() -> None:
    # Third-party imports look up their own configuration names; no credential name or bulk read may appear.
    assert not set(IMPORT_ENVIRON.lookups) & {*_fake_environ(), "<iterated>", "<copied>"}


def test_the_registries_carry_exactly_the_one_accepted_nansen_only_release() -> None:
    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == {RELEASE_ID}
    assert operating_release.APPROVED_RELEASES == {RELEASE_ID: RELEASE_SHA256}
    definition = _definition()
    assert definition.kind == "ACTUAL" and definition.history is not None and definition.nansen is not None
    assert definition.nansen.endpoint == "https://api.nansen.ai"
    assert definition.nansen.credential_slot == "NANSEN_API_KEY"
    assert release_sha256(definition) == RELEASE_SHA256


def test_the_registered_definition_agrees_with_the_literal_pinned_request() -> None:
    assert nansen_request(_definition().nansen) == EXPECTED_REQUEST


def test_the_default_composes_the_api_and_worker_runtime_without_reading_or_socketing(
        environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    api = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    worker = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert api is not None and worker is not None
    assert api.release_sha256 == worker.release_sha256 == RELEASE_SHA256
    assert api.release.history is not None and worker.release.history is not None
    assert (api.evidence_class, api.transport_kind, api.nansen_transport_kind) == (
        "PROVIDER_ACTUAL", "PROVIDER_HTTP", "PROVIDER_HTTP")
    assert api.network_transport is True and api.nansen_network is True
    assert isinstance(api.nansen_transport, NansenHttpFactory) and api.nansen_transport.network
    assert nansen_request(api.release.nansen) == EXPECTED_REQUEST
    with pytest.raises(dataclasses.FrozenInstanceError):
        api.release_sha256 = "0" * 64  # type: ignore[misc]
    assert environ.lookups == [] and no_sockets == []


def test_the_default_is_registered_in_code_not_gated_by_settings_or_environment(
        monkeypatch: pytest.MonkeyPatch, no_sockets: list[Any], caplog: pytest.LogCaptureFixture) -> None:
    # Registration is code-owned: a hostile environment changes nothing and local/test composition stays available.
    # Production names no hosted deployment record here, so research stays off and the server still starts.
    monkeypatch.setenv("EDGE_OS_NANSEN_RELEASE", "actual-attacker/1")
    monkeypatch.setenv("NANSEN_API_KEY", "fake-nansen-SENTINEL-4b5c6d")
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert runtime is not None and runtime.release_sha256 == RELEASE_SHA256
    with caplog.at_level(logging.INFO, logger="edge_os"):
        assert released_runtime_bootstrap.server_research_runtime(SimpleNamespace(env="production")) is None
    assert "no hosted deployment is named" in caplog.text
    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == {RELEASE_ID}
    assert operating_release.APPROVED_RELEASES == {RELEASE_ID: RELEASE_SHA256}
    assert nansen_request(runtime.release.nansen) == EXPECTED_REQUEST
    assert no_sockets == []


def test_a_reload_keeps_the_same_approved_default_and_reads_nothing(
        environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    saved = dict(vars(released_runtime_bootstrap))
    try:
        importlib.reload(released_runtime_bootstrap)
        reloaded = released_runtime_bootstrap.RELEASE_DEFINITIONS
        assert set(reloaded) == {RELEASE_ID} and release_sha256(reloaded[RELEASE_ID]) == RELEASE_SHA256
        assert released_runtime_bootstrap.server_research_runtime(SETTINGS).release_sha256 == RELEASE_SHA256
    finally:  # restore the original globals, so other tests keep one class identity
        vars(released_runtime_bootstrap).clear()
        vars(released_runtime_bootstrap).update(saved)
    assert environ.lookups == [] and no_sockets == []


def test_a_changed_hash_for_the_registered_release_composes_nothing_and_reads_nothing(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES", {RELEASE_ID: "0" * 64})
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is None
    assert environ.lookups == [] and no_sockets == []


def test_an_explicitly_emptied_registry_composes_nothing_and_reads_nothing(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is None
    assert environ.lookups == [] and no_sockets == []


def test_a_missing_selected_slot_refuses_at_preparation_before_any_network_and_touches_no_other_slot(
        monkeypatch: pytest.MonkeyPatch, no_sockets: list[Any]) -> None:
    recording = _fake_environ(with_nansen=False)
    monkeypatch.setattr(os, "environ", recording)
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert runtime is not None and recording.lookups == []
    with pytest.raises(ReleaseRefused) as refused:
        prepare_nansen(runtime)
    assert refused.value.code == "operating_release_credential_unavailable"
    assert recording.lookups == ["NANSEN_API_KEY"] and no_sockets == []


def test_the_legacy_fixture_caller_supplies_no_release_and_restores_the_registered_default(
        environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    """The authored-fixture caller chain must run without the registered release; the scoped fixture override supplies
    no release for that legacy scenario only and restores on exit. The registries are never changed."""
    import harness  # scripts/p03, on the test path. Its factory helper composes no release.

    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == {RELEASE_ID}
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is not None  # ordinary default unchanged
    with harness.no_registered_release():
        assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is None  # fixture supplies no release
        assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == {RELEASE_ID}  # registries untouched
        assert operating_release.APPROVED_RELEASES == {RELEASE_ID: RELEASE_SHA256}
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is not None  # restored on exit
    assert environ.lookups == [] and no_sockets == []


def test_the_default_refuses_but_the_fixture_helper_passes_the_authored_mode_check(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    from edge_os_api import main
    from edge_os_api.core.settings import ConfigError

    import harness

    settings = SimpleNamespace(env="local", interpreter="fixture", nansen_research_mode="authored_fixture",
                               database_url="postgresql+psycopg://postgres:fake@127.0.0.1:1/edge_os_test_fixture",
                               database_statement_timeout_ms=1000)
    with pytest.raises(ConfigError, match="research_runtime"):
        main.create_app(settings)  # the default composes the registered release and the mode refuses it

    class _EngineReached(BaseException):
        pass

    real = released_runtime_bootstrap.server_research_runtime

    def sentinel(*args: Any, **kwargs: Any) -> None:
        raise _EngineReached()

    monkeypatch.setattr(main, "make_engine", sentinel)
    with pytest.raises(_EngineReached):
        harness.create_app_fixture(settings)  # passes the mode check and reaches the engine sentinel
    assert released_runtime_bootstrap.server_research_runtime is real  # restored after the exception
    assert not set(environ.lookups) & {"HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"}
    assert no_sockets == []


def test_the_fixture_helper_forwards_settings_and_runner_and_restores_on_exception(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    from edge_os_api import main

    import harness

    settings = SimpleNamespace(env="local", interpreter="hermes_local", nansen_research_mode="unavailable")
    runner = object()
    recorded: dict[str, Any] = {}
    real = released_runtime_bootstrap.server_research_runtime

    class _EngineReached(BaseException):
        pass

    def recording(settings_arg: Any, **kwargs: Any) -> None:
        recorded.update({"settings": settings_arg,
                         "override_active": released_runtime_bootstrap.server_research_runtime is not real, **kwargs})
        raise _EngineReached()

    monkeypatch.setattr(main, "create_app", recording)
    with pytest.raises(_EngineReached):
        harness.create_app_fixture(settings, hermes_runner=runner)
    assert recorded["settings"] is settings and recorded["hermes_runner"] is runner
    assert recorded["override_active"] is True
    assert released_runtime_bootstrap.server_research_runtime is real
    assert not set(environ.lookups) & {"HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"}
    assert no_sockets == []


def test_every_inherited_authored_launcher_selects_the_fixture_composition() -> None:
    import harness

    root = harness.REPO
    for relative in ("scripts/p03/runtime_phase.py", "scripts/p03/p05_phase.py",
                     "scripts/p03/hermes_app_mount_phase.py"):
        text = (root / relative).read_text(encoding="utf-8")
        assert 'factory="harness:create_app_fixture"' in text, relative
        assert "app_dir=harness.P03_DIR" in text, relative
    for relative in ("scripts/hermes_interpretation/serve_local.py",
                     "scripts/hermes_app_mount/serve_transport_mount.py"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "harness.create_app_fixture(" in text, relative
