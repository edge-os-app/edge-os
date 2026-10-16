"""`open_relay_mount` refuses production, another interpreter, an ACTUAL route and a mismatched policy before it opens a
database engine, reads a key or starts anything. No Docker, no database: the engine factory must never be called.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import harness
import relay_application_mount
from edge_os_api.core.settings import load_settings
from edge_os_api.research.hermes_transport_mount import AUTHORED_ROUTE, DEFAULT_POLICY, MountRefused
from provider_transport import ActualProviderUnavailable, TransportRoute
from relay_admission import RelayRelease
from relay_turn_runner import RelayEndpoint
from tokens import TestSigner

RELEASE = RelayRelease("local-relay-app-1", AUTHORED_ROUTE.route_id, "AUTHORED", DEFAULT_POLICY.model,
                       DEFAULT_POLICY.max_output_tokens, DEFAULT_POLICY.max_request_bytes, AUTHORED_ROUTE.max_reply_bytes)


@pytest.fixture
def settings(monkeypatch):
    def no_engine(*_args, **_kwargs):
        raise AssertionError("an engine was opened before the refusal")

    monkeypatch.setattr(relay_application_mount, "make_engine", no_engine)
    env = harness.api_env(database_url="postgresql+psycopg://nobody@127.0.0.1:9/edge_os_test_none", public_pem=TestSigner().public_pem,
                          previous_pem=None, cors=["http://127.0.0.1:3999"])
    return load_settings({**env, "EDGE_OS_INTERPRETER": "hermes_local"})


def open_with(settings, tmp_path: Path, **changes):
    endpoint = RelayEndpoint(*(tmp_path / name for name in ("g", "r", "s", "k")), "app")
    arguments = dict(limits=None, release=RELEASE, endpoint=endpoint, image="unused", run_id="r",
                     evidence_dir=tmp_path / "e", script_for=lambda turn: {})
    return relay_application_mount.open_relay_mount(settings, **{**arguments, **changes})


def test_production_another_interpreter_actual_and_a_mismatched_policy_are_refused_before_any_effect(settings, tmp_path):
    with pytest.raises(MountRefused):
        open_with(settings.model_copy(update={"env": "production"}), tmp_path)
    with pytest.raises(MountRefused):
        open_with(settings.model_copy(update={"interpreter": "fixture"}), tmp_path)
    actual = TransportRoute(AUTHORED_ROUTE.route_id, "ACTUAL", AUTHORED_ROUTE.endpoint_url, AUTHORED_ROUTE.max_reply_bytes)
    with pytest.raises(ActualProviderUnavailable):
        open_with(settings, tmp_path, route=actual)
    with pytest.raises(MountRefused):
        open_with(settings, tmp_path, policy=replace(DEFAULT_POLICY, model="other-model"))
    assert list(tmp_path.iterdir()) == []  # no folder, key or file was touched
