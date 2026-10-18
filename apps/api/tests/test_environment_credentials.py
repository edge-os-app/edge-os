"""The process-environment credential source for the three accepted research slots (#58 L4).

Runs with `--noconftest`: no database, socket or provider. Every value is a literal fake sentinel, set only through
`monkeypatch` on a recording copy of the environment, so a test can count every slot the source looked up.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

import operating_release_stand_in as stand_in
from edge_os_api.core.research import environment_credentials, operating_release, released_runtime_bootstrap
from edge_os_api.core.research.environment_credentials import EnvironmentCredentialSource
from edge_os_api.core.research.operating_release import ReleaseRefused
from edge_os_api.core.research.released_source_runtime import (
    CredentialUnavailable,
    prepare_history,
    prepare_nansen,
)

FAKE_HYPERSYNC = "fake-hypersync-SENTINEL-a1b2c3"
FAKE_QUICKNODE = "https://quicknode.stand-in.invalid/fake-quicknode-SENTINEL-d4e5f6/"
FAKE_NANSEN = "fake-nansen-SENTINEL-0718af"
SENTINELS = ("SENTINEL-a1b2c3", "SENTINEL-d4e5f6", "SENTINEL-0718af")
SETTINGS = SimpleNamespace(env="local")


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


@pytest.fixture
def environ(monkeypatch: pytest.MonkeyPatch) -> RecordingEnviron:
    recording = RecordingEnviron({"HYPERSYNC_API_KEY": FAKE_HYPERSYNC, "QUICKNODE_API_URL": FAKE_QUICKNODE,
                                  "NANSEN_API_KEY": FAKE_NANSEN, "OPENROUTER_API_KEY": "fake-openrouter-SENTINEL-0",
                                  "PRIVY_APP_SECRET": "fake-privy-SENTINEL-0",
                                  "EDGE_OS_DATABASE_URL": "postgresql://fake-db-SENTINEL-0"})
    monkeypatch.setattr(os, "environ", recording)
    return recording


def _no_sentinel(text: str) -> None:
    for sentinel in (*SENTINELS, "SENTINEL-0"):
        assert sentinel not in text


# ------------------------------------------------------------------------------------------- read(slot)

@pytest.mark.parametrize(("slot", "want"), [("HYPERSYNC_API_KEY", FAKE_HYPERSYNC),
                                             ("QUICKNODE_API_URL", FAKE_QUICKNODE),
                                             ("NANSEN_API_KEY", FAKE_NANSEN)])
def test_each_allowed_slot_reads_only_its_own_environment_value(environ: RecordingEnviron, slot: str,
                                                                want: str) -> None:
    assert EnvironmentCredentialSource().read(slot) == want
    assert environ.lookups == [slot]


def test_a_nonblank_value_is_returned_unchanged(environ: RecordingEnviron) -> None:
    environ["NANSEN_API_KEY"] = "  padded fake-nansen-SENTINEL-0718af\t"
    assert EnvironmentCredentialSource().read("NANSEN_API_KEY") == "  padded fake-nansen-SENTINEL-0718af\t"


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_a_missing_empty_or_blank_value_is_unavailable(environ: RecordingEnviron, value: str | None) -> None:
    if value is None:
        del environ["HYPERSYNC_API_KEY"]
    else:
        environ["HYPERSYNC_API_KEY"] = value
    with pytest.raises(CredentialUnavailable) as raised:
        EnvironmentCredentialSource().read("HYPERSYNC_API_KEY")
    assert environ.lookups == ["HYPERSYNC_API_KEY"]
    assert str(raised.value) == "the credential slot has no value"


@pytest.mark.parametrize("slot", ["OPENROUTER_API_KEY", "PRIVY_APP_SECRET", "EDGE_OS_DATABASE_URL", "PATH",
                                  "hypersync_api_key", " NANSEN_API_KEY", "STAND_IN_NANSEN_KEY",
                                  "fake-unknown-SENTINEL-0", ""])
def test_an_unknown_slot_is_refused_before_any_environment_lookup(environ: RecordingEnviron, slot: str) -> None:
    with pytest.raises(CredentialUnavailable) as raised:
        EnvironmentCredentialSource().read(slot)
    assert environ.lookups == []
    assert str(raised.value) == "the credential slot is not allowed"
    _no_sentinel(repr(raised.value))


def test_import_and_construction_read_no_environment_value(environ: RecordingEnviron) -> None:
    import importlib

    importlib.reload(environment_credentials)
    source = environment_credentials.EnvironmentCredentialSource()
    assert environ.lookups == []
    assert vars(source) == {}


def test_each_read_sees_the_current_environment(environ: RecordingEnviron) -> None:
    source = EnvironmentCredentialSource()
    assert source.read("NANSEN_API_KEY") == FAKE_NANSEN
    environ["NANSEN_API_KEY"] = "fake-nansen-changed-SENTINEL-0"
    assert source.read("NANSEN_API_KEY") == "fake-nansen-changed-SENTINEL-0"
    del environ["NANSEN_API_KEY"]
    with pytest.raises(CredentialUnavailable):
        source.read("NANSEN_API_KEY")


def test_repr_errors_and_logs_hold_no_value(environ: RecordingEnviron, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    source = EnvironmentCredentialSource()
    for slot in ("HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"):
        source.read(slot)
    environ["HYPERSYNC_API_KEY"] = "   "
    with pytest.raises(CredentialUnavailable) as blank:
        source.read("HYPERSYNC_API_KEY")
    with pytest.raises(CredentialUnavailable) as unknown:
        source.read("OPENROUTER_API_KEY")
    for error in (blank.value, unknown.value):
        assert error.__cause__ is None and error.__context__ is None
        _no_sentinel(repr(error) + str(error.args))
    _no_sentinel(repr(source) + str(vars(source)))
    assert caplog.records == []


# --------------------------------------------------------------------------- the existing preparation seam

def _env_slot_release(*, quicknode_host: str = stand_in.INVALID_QUICKNODE_HOST) -> object:
    release = stand_in.stand_in_release(quicknode_host=quicknode_host)
    history = dataclasses.replace(release.history, envio_credential_slot="HYPERSYNC_API_KEY",
                                  quicknode_credential_slot="QUICKNODE_API_URL")
    nansen = dataclasses.replace(release.nansen, credential_slot="NANSEN_API_KEY")
    return dataclasses.replace(release, history=history, nansen=nansen)


def _runtime(release: object) -> tuple[object, stand_in.RecordingStandIn, stand_in.StandInNansen]:
    runtime, provider, nansen, _ = stand_in.recording_runtime(SETTINGS, release=release,
                                                              creds=EnvironmentCredentialSource())
    return runtime, provider, nansen


def test_composing_the_release_reads_no_environment_value(environ: RecordingEnviron) -> None:
    _runtime(_env_slot_release())
    assert environ.lookups == []


def test_preparation_reads_the_three_slots_and_sends_nothing(environ: RecordingEnviron) -> None:
    runtime, provider, nansen = _runtime(_env_slot_release())
    history = prepare_history(runtime)
    report = prepare_nansen(runtime)
    assert environ.lookups == ["HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"]
    assert (history._bearer, history._quicknode_url, report._key) == (FAKE_HYPERSYNC, FAKE_QUICKNODE, FAKE_NANSEN)
    assert provider.requests == [] and nansen.requests == []
    _no_sentinel(repr(history) + repr(report) + repr(runtime))


@pytest.mark.parametrize(("slot", "prepare"), [("HYPERSYNC_API_KEY", prepare_history),
                                               ("QUICKNODE_API_URL", prepare_history),
                                               ("NANSEN_API_KEY", prepare_nansen)])
def test_a_missing_slot_refuses_preparation_and_sends_nothing(environ: RecordingEnviron, slot: str,
                                                              prepare: object) -> None:
    environ[slot] = " "
    runtime, provider, nansen = _runtime(_env_slot_release())
    with pytest.raises(ReleaseRefused) as raised:
        prepare(runtime)  # type: ignore[operator]
    assert raised.value.code == "operating_release_credential_unavailable"
    assert provider.requests == [] and nansen.requests == []
    _no_sentinel(str(raised.value))


def test_a_quicknode_url_on_another_host_keeps_the_endpoint_mismatch(environ: RecordingEnviron) -> None:
    environ["QUICKNODE_API_URL"] = "https://other.stand-in.invalid/fake-quicknode-SENTINEL-d4e5f6/"
    runtime, provider, nansen = _runtime(_env_slot_release())
    with pytest.raises(ReleaseRefused) as raised:
        prepare_history(runtime)
    assert raised.value.code == "operating_release_endpoint_mismatch"
    assert provider.requests == [] and nansen.requests == []
    _no_sentinel(str(raised.value))


def test_the_default_bootstrap_composes_the_one_approved_release_and_reads_nothing(
        environ: RecordingEnviron) -> None:
    # The code-owned default now carries exactly the one accepted Nansen-only ACTUAL release and its approved SHA-256.
    assert set(released_runtime_bootstrap.RELEASE_DEFINITIONS) == set(operating_release.APPROVED_RELEASES)
    runtime = released_runtime_bootstrap.server_research_runtime(SETTINGS,
                                                                 credentials=EnvironmentCredentialSource())
    assert runtime is not None
    assert runtime.release_sha256 == operating_release.APPROVED_RELEASES[runtime.release.release_id]
    assert environ.lookups == []


def test_an_explicitly_emptied_registry_composes_nothing_and_reads_nothing(
        monkeypatch: pytest.MonkeyPatch, environ: RecordingEnviron) -> None:
    monkeypatch.setattr(released_runtime_bootstrap, "RELEASE_DEFINITIONS", {})
    assert released_runtime_bootstrap.server_research_runtime(SETTINGS,
                                                              credentials=EnvironmentCredentialSource()) is None
    assert environ.lookups == []
