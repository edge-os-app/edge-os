"""The server bootstrap composes the accepted environment credential source by default (#58 L4 credential delivery).

Runs with `--noconftest`: no database, socket or provider. A recording stand-in for `os.environ` holding only literal
fake sentinels is installed before any project import and for every test, so the real environment is never consulted
and every looked-up slot is counted. The synthetic `.example` ACTUAL releases in this file are approved only by
`monkeypatch`; the code-owned default registry is left intact and is covered by `test_approved_nansen_bootstrap.py`.
See `docs/qualification/research-provider-composition/CREDENTIAL_DELIVERY.md`.
"""

from __future__ import annotations

import dataclasses
import os
import socket
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest


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


FAKE_HYPERSYNC = "fake-hypersync-SENTINEL-b7c8d9"
FAKE_QUICKNODE = "https://quicknode.bootstrap-test.example/fake-quicknode-SENTINEL-e1f2a3/"
FAKE_NANSEN = "fake-nansen-SENTINEL-4b5c6d"
SENTINELS = ("SENTINEL-b7c8d9", "SENTINEL-e1f2a3", "SENTINEL-4b5c6d", "SENTINEL-0")


def _fake_environ() -> RecordingEnviron:
    return RecordingEnviron({"HYPERSYNC_API_KEY": FAKE_HYPERSYNC, "QUICKNODE_API_URL": FAKE_QUICKNODE,
                             "NANSEN_API_KEY": FAKE_NANSEN, "OPENROUTER_API_KEY": "fake-openrouter-SENTINEL-0",
                             "STAND_IN_NANSEN_KEY": "fake-stand-in-SENTINEL-0"})


# The fake is in place before the first project import, so an import-time environment read would be recorded here.
IMPORT_ENVIRON = _fake_environ()
_real_environ, os.environ = os.environ, IMPORT_ENVIRON  # type: ignore[assignment]
try:
    import operating_release_stand_in as stand_in
    from edge_os_api.core.research import environment_credentials, operating_release, released_runtime_bootstrap
    from edge_os_api.core.research.environment_credentials import EnvironmentCredentialSource
    from edge_os_api.core.research.operating_release import OperatingRelease, ReleaseRefused, release_sha256
    from edge_os_api.core.research.released_source_runtime import NansenHttpFactory, prepare_history, prepare_nansen
    from edge_os_api.nansen_research.http_transport import NANSEN_ORIGIN
    from edge_os_api.research_history.http_clients import StdlibHttpTransport
finally:
    os.environ = _real_environ

SETTINGS = SimpleNamespace(env="local")
QUICKNODE_HOST = "quicknode.bootstrap-test.example"


def synthetic_release(*, release_id: str = "synthetic-bootstrap/1",
                      slots: tuple[str, str, str] = ("HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"),
                      ) -> OperatingRelease:
    """A synthetic ACTUAL definition over `.example` hosts with the given credential slots. No job runs over it."""
    base = stand_in.stand_in_release(envio_endpoint="https://hypersync.bootstrap-test.example",
                                     quicknode_host=QUICKNODE_HOST, nansen_endpoint=NANSEN_ORIGIN)
    history = dataclasses.replace(base.history, envio_credential_slot=slots[0], quicknode_credential_slot=slots[1])
    nansen = dataclasses.replace(base.nansen, credential_slot=slots[2])
    return OperatingRelease(release_id, "ACTUAL", history=history, nansen=nansen)


def install(monkeypatch: pytest.MonkeyPatch, *releases: OperatingRelease, approved: bool = True,
            filed_as: str | None = None) -> None:
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS",
                        {filed_as or release.release_id: release for release in releases})
    monkeypatch.setattr(operating_release, "APPROVED_RELEASES",
                        {release.release_id: release_sha256(release) for release in releases} if approved else {})


@pytest.fixture
def environ(monkeypatch: pytest.MonkeyPatch) -> RecordingEnviron:
    recording = _fake_environ()
    monkeypatch.setattr(os, "environ", recording)
    return recording


@pytest.fixture
def constructed(monkeypatch: pytest.MonkeyPatch) -> list[EnvironmentCredentialSource]:
    """Every environment source the bootstrap constructs, in order."""
    built: list[EnvironmentCredentialSource] = []

    class Counted(EnvironmentCredentialSource):
        def __init__(self) -> None:
            built.append(self)

    monkeypatch.setattr(released_runtime_bootstrap, "EnvironmentCredentialSource", Counted)
    return built


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> None:
        opened.append(args)
        raise AssertionError("a socket was opened")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return opened


def _no_sentinel(text: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text


# ------------------------------------------------------------------------------- refusals before any source

def test_importing_the_bootstrap_reads_no_credential_and_never_the_whole_environment() -> None:
    # Third-party imports look up their own configuration names; no credential name or bulk read may appear.
    assert not set(IMPORT_ENVIRON.lookups) & {*_fake_environ(), "<iterated>", "<copied>"}


def test_a_reload_reads_nothing_and_an_emptied_registry_composes_nothing(
        environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    import importlib

    saved = {module: dict(vars(module)) for module in (environment_credentials, released_runtime_bootstrap)}
    try:
        importlib.reload(environment_credentials)
        importlib.reload(released_runtime_bootstrap)
        # The code-owned default now registers exactly one approved ACTUAL release (the empty-by-default assumption is
        # superseded); importing or reloading it still reads no credential and opens no socket.
        assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == set(operating_release.APPROVED_RELEASES)
        assert released_runtime_bootstrap.RELEASE_DEFINITIONS != {} and operating_release.APPROVED_RELEASES != {}
        assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is not None
        # An explicitly emptied registry still composes nothing and has no effect at all.
        released_runtime_bootstrap.RELEASE_DEFINITIONS = {}
        assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is None
    finally:  # restore the original globals, so other tests keep one class identity
        for module, namespace in saved.items():
            vars(module).clear()
            vars(module).update(namespace)
    assert environ.lookups == [] and no_sockets == []


@pytest.mark.parametrize("case", ["two_approved", "misfiled"])
def test_an_invalid_registry_refuses_before_constructing_or_reading_a_source(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, constructed: list[Any], case: str) -> None:
    if case == "two_approved":
        install(monkeypatch, synthetic_release(), synthetic_release(release_id="synthetic-bootstrap/2"))
    else:
        install(monkeypatch, synthetic_release(), filed_as="another-id/1")
    with pytest.raises(ReleaseRefused) as refused:
        released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert refused.value.code == "operating_release_invalid"
    assert constructed == [] and environ.lookups == []


def test_an_unapproved_or_changed_definition_composes_nothing_and_reads_nothing(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, constructed: list[Any]) -> None:
    install(monkeypatch, synthetic_release(), approved=False)
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is None
    release = synthetic_release()
    install(monkeypatch, release)
    changed = dataclasses.replace(release, nansen=dataclasses.replace(release.nansen, deadline_seconds=601))
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {release.release_id: changed})
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS) is None
    assert constructed == [] and environ.lookups == []


# ------------------------------------------------------------------------------- the composed default

def test_one_approved_definition_composes_the_environment_source_for_api_and_worker_without_reading(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, constructed: list[Any],
        no_sockets: list[Any]) -> None:
    release = synthetic_release()
    install(monkeypatch, release)
    api = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    worker = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert api is not None and worker is not None
    assert len(constructed) == 2 and api.credentials is constructed[0] and worker.credentials is constructed[1]
    assert api.release_sha256 == worker.release_sha256 == release_sha256(release)
    assert (api.evidence_class, api.transport_kind, api.nansen_transport_kind) == (
        "PROVIDER_ACTUAL", "PROVIDER_HTTP", "PROVIDER_HTTP")
    assert api.http_transport is StdlibHttpTransport and isinstance(api.nansen_transport, NansenHttpFactory)
    with pytest.raises(dataclasses.FrozenInstanceError):
        api.release_sha256 = "0" * 64  # type: ignore[misc]
    assert environ.lookups == [] and no_sockets == []
    _no_sentinel(repr(api) + repr(worker))


def test_the_default_source_reads_the_three_allowed_slots_only_at_preparation(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    install(monkeypatch, synthetic_release())
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert runtime is not None and environ.lookups == []
    history = prepare_history(runtime)
    report = prepare_nansen(runtime)
    assert environ.lookups == ["HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"]
    assert (history._bearer, history._quicknode_url, report._key) == (FAKE_HYPERSYNC, FAKE_QUICKNODE, FAKE_NANSEN)
    assert no_sockets == []


@pytest.mark.parametrize(("slot", "value"), [("HYPERSYNC_API_KEY", None), ("QUICKNODE_API_URL", "   "),
                                             ("NANSEN_API_KEY", ""), ("NANSEN_API_KEY", None)])
def test_a_missing_or_blank_slot_refuses_at_preparation_and_reaches_no_provider(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any], slot: str,
        value: str | None) -> None:
    if value is None:
        del environ[slot]
    else:
        environ[slot] = value
    install(monkeypatch, synthetic_release())
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert runtime is not None
    prepare = prepare_nansen if slot == "NANSEN_API_KEY" else prepare_history
    built: list[Any] = []
    monkeypatch.setattr(NansenHttpFactory, "__call__", lambda *args, **kwargs: built.append(args))
    with pytest.raises(ReleaseRefused) as refused:
        prepare(runtime)
    assert refused.value.code == "operating_release_credential_unavailable"
    assert environ.lookups[-1] == slot and built == [] and no_sockets == []
    _no_sentinel(str(refused.value) + repr(refused.value.args))


def test_an_unknown_slot_refuses_at_preparation_without_any_environment_lookup(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, no_sockets: list[Any]) -> None:
    install(monkeypatch, synthetic_release(slots=("OPENROUTER_API_KEY", "QUICKNODE_API_URL", "STAND_IN_NANSEN_KEY")))
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS)
    assert runtime is not None
    for prepare in (prepare_history, prepare_nansen):
        with pytest.raises(ReleaseRefused) as refused:
            prepare(runtime)
        assert refused.value.code == "operating_release_credential_unavailable"
    assert environ.lookups == [] and no_sockets == []


# ------------------------------------------------------------------------------- explicit injection

def test_an_explicit_source_is_used_unchanged_and_the_environment_is_never_consulted(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, constructed: list[Any]) -> None:
    install(monkeypatch, synthetic_release())
    creds = stand_in.credentials()
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS, credentials=creds)
    assert runtime is not None and runtime.credentials is creds
    assert constructed == [] and creds.reads == [] and environ.lookups == []


def test_a_broken_explicit_source_refuses_without_falling_back_to_the_environment(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron, constructed: list[Any],
        no_sockets: list[Any]) -> None:
    class Broken:
        def read(self, slot: str) -> str:
            raise RuntimeError("fake-broken-SENTINEL-0")

    install(monkeypatch, synthetic_release())
    broken = Broken()
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS, credentials=broken)
    assert runtime is not None and runtime.credentials is broken
    for prepare in (prepare_history, prepare_nansen):
        with pytest.raises(ReleaseRefused) as refused:
            prepare(runtime)
        assert refused.value.code == "operating_release_credential_unavailable"
        _no_sentinel(str(refused.value))
    assert constructed == [] and environ.lookups == [] and no_sockets == []

