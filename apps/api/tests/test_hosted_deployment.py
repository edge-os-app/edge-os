"""The hosted activation record: a code-owned approval that alone admits three production parts.

Pure tests (no database, Docker or network). The registry is empty in this candidate; a test patches it with a
synthetic record to prove that only the named parts are admitted. Every other production refusal and every local
behaviour stays as it was.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import harness
from tokens import TestSigner

from edge_os_api.core import hosted_deployment
from edge_os_api.core.hosted_deployment import HostedDeploymentRefused
from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.main import create_app

RELAY_ID = "hermes-first-call-1"
RELAY_SHA = "3fa94dd73e53a72ca8af6cda9c8633770de89c262fa5303756c1965bb92fed8f"
RESEARCH_ID = "actual-moe-history2h-nansen-20261022/1"
RESEARCH_SHA = "45c8cfbf5d61eb519ee3140e02e50b2b7091669dc28cbef224bdc6a0e77ca877"
IMAGE = "sha256:" + "1" * 64
GATE_SHA = "2" * 64
DEPLOYMENT = "hosted-demo-1"
REGISTERED_ID = "edgeos-fun-vps1"
REGISTERED_SHA = "0e56ad4290b522d450142c5baa367b5daacf695dfe563102e85bc43f0bb7b728"
RECORD_PATH = (Path(__file__).resolve().parents[3]
               / "docs/qualification/hosted-gates/records/edgeos-fun-vps1.json")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def gate_ref(name: str) -> dict[str, str]:
    return {"path": f"docs/qualification/hosted-activation/{name}.md", "sha256": GATE_SHA}


def record(**changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": hosted_deployment.RECORD_VERSION,
        "deployment_id": DEPLOYMENT,
        "public_origins": ["https://app.example.com"],
        "cors_origins": ["https://app.example.com"],
        "database_tls_mode": "verify-full",
        "hermes_relay": {"release_id": RELAY_ID, "record_sha256": RELAY_SHA},
        "research_release": {"release_id": RESEARCH_ID, "sha256": RESEARCH_SHA},
        "host_gates": {
            "h1_egress": gate_ref("H1"),
            "h2_runner_isolation": gate_ref("H2"),
            "h8_provider_spend_cap": gate_ref("H8"),
            "h10_backup_restore": gate_ref("H10"),
        },
        "image_digests": {"api": IMAGE, "worker": IMAGE},
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_until": "2027-01-01T00:00:00Z",
    }
    value.update(changes)
    return value


def write_record(folder: Path, value: dict[str, Any], *, raw: bytes | None = None,
                 name: str = "deployment.json") -> tuple[Path, str]:
    data = canonical(value) if raw is None else raw
    path = folder / name
    path.write_bytes(data)
    return path, hashlib.sha256(canonical(value)).hexdigest()


def running(*, deployment_id: str | None = DEPLOYMENT, record_path: Path | None = None,
            cors: tuple[str, ...] = ("https://app.example.com",),
            sslmode: str = "verify-full") -> SimpleNamespace:
    return SimpleNamespace(
        hosted_deployment_id=deployment_id,
        hosted_deployment_record_path=None if record_path is None else str(record_path),
        cors_origins=list(cors),
        database_url=f"postgresql+psycopg://app@db.internal.example:5432/edge_os?sslmode={sslmode}")


def approve(monkeypatch: pytest.MonkeyPatch, value: dict[str, Any], sha: str) -> None:
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {value["deployment_id"]: sha})


def production_env(**changes: str) -> dict[str, str]:
    env = {
        "EDGE_OS_ENV": "production",
        "EDGE_OS_DATABASE_URL": "postgresql+psycopg://app@db.internal.example:5432/edge_os?sslmode=verify-full",
        "EDGE_OS_PRIVY_APP_ID": "real-app",
        "EDGE_OS_PRIVY_VERIFICATION_KEY": TestSigner().public_pem,
        "EDGE_OS_CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "EDGE_OS_BUILD_SHA": "a" * 40,
    }
    env.update(changes)
    return env


# --- The registry and the record file --------------------------------------------------------------------------------


def test_the_code_owned_registry_pins_the_approved_record() -> None:
    assert dict(hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS) == {REGISTERED_ID: REGISTERED_SHA}


def test_the_committed_record_is_canonical_and_matches_the_pin() -> None:
    raw = RECORD_PATH.read_bytes()
    value = json.loads(raw)
    assert raw == hosted_deployment.canonical(value)
    assert value["deployment_id"] == REGISTERED_ID
    assert hashlib.sha256(hosted_deployment.canonical(value)).hexdigest() == REGISTERED_SHA


def test_the_committed_record_is_admitted_with_the_running_origin_and_tls() -> None:
    value = json.loads(RECORD_PATH.read_bytes())
    digest = hashlib.sha256(hosted_deployment.canonical(value)).hexdigest()
    settings = running(deployment_id=REGISTERED_ID, record_path=RECORD_PATH,
                       cors=("https://app.edgeos.fun",), sslmode="require")
    loaded = hosted_deployment.check_hosted_deployment(
        settings, approvals={REGISTERED_ID: digest}, now=datetime(2026, 10, 30, 12, tzinfo=UTC))
    assert loaded is not None and loaded.record_sha256 == digest
    assert loaded.admits_execution_release("anything/1", "0" * 64) is False


def test_no_named_record_returns_none_and_reads_nothing(tmp_path: Path) -> None:
    assert hosted_deployment.check_hosted_deployment(running(deployment_id=None)) is None
    assert list(tmp_path.iterdir()) == []


def test_an_unregistered_record_is_refused(tmp_path: Path) -> None:
    path, _sha = write_record(tmp_path, record())
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert refused.value.code == "hosted_deployment_not_approved"


def test_a_named_id_without_a_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(deployment_id=DEPLOYMENT))
    assert refused.value.code == "hosted_deployment_incomplete"


def test_a_relative_record_path_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {DEPLOYMENT: GATE_SHA})
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=Path("deployment.json")))
    assert refused.value.code == "hosted_deployment_record_path_invalid"


def test_a_matching_record_is_loaded_with_its_bound_release_identities(tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    loaded = hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert loaded is not None and loaded.record_sha256 == sha
    assert loaded.admits_hermes_relay(RELAY_ID, RELAY_SHA)
    assert not loaded.admits_hermes_relay(RELAY_ID, GATE_SHA)
    assert not loaded.admits_hermes_relay("another-release", RELAY_SHA)
    assert loaded.admits_research_release(RESEARCH_ID, RESEARCH_SHA)
    assert not loaded.admits_research_release(RESEARCH_ID, GATE_SHA)


def test_the_hash_covers_the_canonical_form_not_the_file_layout(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    value = record()
    path, sha = write_record(tmp_path, value, raw=json.dumps(value, indent=2).encode())
    approve(monkeypatch, value, sha)
    assert hosted_deployment.check_hosted_deployment(running(record_path=path)) is not None


def test_a_field_changed_after_the_approval_is_refused(tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    value, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    path = tmp_path / "changed.json"
    path.write_bytes(canonical(record(cors_origins=["https://evil.example.com"],
                                      public_origins=["https://app.example.com"])))
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert refused.value.code == "hosted_deployment_hash_mismatch"


def test_running_origins_must_equal_the_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(
            running(record_path=path, cors=("https://other.example.com",)))
    assert refused.value.code == "hosted_deployment_origin_mismatch"


def test_the_running_tls_mode_must_equal_the_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path, sslmode="require"))
    assert refused.value.code == "hosted_deployment_tls_mismatch"


def test_a_record_outside_its_validity_window_is_refused(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record(valid_until="2026-02-01T00:00:00Z"))
    approve(monkeypatch, record(valid_until="2026-02-01T00:00:00Z"), sha)
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert refused.value.code == "hosted_deployment_outside_window"


@pytest.mark.parametrize("changes,code", [
    ({"schema_version": "another/1"}, "hosted_deployment_invalid"),
    ({"public_origins": ["http://app.example.com"]}, "hosted_deployment_invalid"),
    ({"public_origins": ["https://*.example.com"]}, "hosted_deployment_invalid"),
    ({"cors_origins": ["https://other.example.com"]}, "hosted_deployment_invalid"),
    ({"database_tls_mode": "disable"}, "hosted_deployment_invalid"),
    ({"hermes_relay": {"release_id": RELAY_ID, "record_sha256": "short"}}, "hosted_deployment_invalid"),
    ({"research_release": {"release_id": RESEARCH_ID}}, "hosted_deployment_invalid"),
    ({"host_gates": {}}, "hosted_deployment_invalid"),
    ({"image_digests": {}}, "hosted_deployment_invalid"),
    ({"valid_from": "2026-01-01T00:00:00", "valid_until": "2027-01-01T00:00:00Z"},
     "hosted_deployment_invalid"),
    ({"unknown": "field"}, "hosted_deployment_invalid"),
])
def test_a_malformed_record_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       changes: dict[str, Any], code: str) -> None:
    value = record(**changes)
    path, sha = write_record(tmp_path, value)
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {DEPLOYMENT: sha})
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert refused.value.code == code


def test_a_record_with_repeated_keys_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = canonical(record())
    repeated = raw[:-1] + b',"deployment_id":"other"}'
    path = tmp_path / "repeated.json"
    path.write_bytes(repeated)
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {DEPLOYMENT: hashlib.sha256(raw).hexdigest()})
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert refused.value.code == "hosted_deployment_invalid"


def test_a_symlink_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    link = tmp_path / "link.json"
    os.symlink(path, link)
    approve(monkeypatch, record(), sha)
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=link))
    assert refused.value.code == "hosted_deployment_record_unreadable"


def test_an_oversized_record_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = record()
    raw = canonical(value) + b" " * hosted_deployment.MAX_RECORD_BYTES
    path = tmp_path / "large.json"
    path.write_bytes(raw)
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS",
                        {DEPLOYMENT: hashlib.sha256(canonical(value)).hexdigest()})
    with pytest.raises(HostedDeploymentRefused) as refused:
        hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert refused.value.code == "hosted_deployment_record_too_large"


# --- Settings: only the interpreter admission changes ------------------------------------------------------------------


def test_production_still_refuses_hermes_local_without_a_record() -> None:
    with pytest.raises(ConfigError, match="approved hosted deployment"):
        load_settings(production_env(EDGE_OS_INTERPRETER="hermes_local"))


def test_production_admits_hermes_local_only_with_a_matching_record(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    value = record()
    approve(monkeypatch, value, sha)
    settings = load_settings(production_env(
        EDGE_OS_INTERPRETER="hermes_local",
        EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path)))
    assert settings.interpreter == "hermes_local"


def test_production_hermes_local_needs_the_relay_release_configuration(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    settings = load_settings(production_env(
        EDGE_OS_INTERPRETER="hermes_local",
        EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path)))
    with pytest.raises(ConfigError, match="approved relay release configuration"):
        create_app(settings, hermes_runner=object())  # type: ignore[arg-type]


def test_production_refuses_a_configuration_for_another_relay_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.research.hermes_interpreter import HermesInterpreterConfig, LiveRelease

    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    settings = load_settings(production_env(
        EDGE_OS_INTERPRETER="hermes_local",
        EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path)))
    config = HermesInterpreterConfig(
        model="openai/gpt-6.1-sol", route="openrouter-openai-standard", max_output_tokens=4096,
        runtime_label="LIVE", live_release=LiveRelease(release_id="another-release", provider="openai",
                                                       model="openai/gpt-6.1-sol", budget_usd="2.00",
                                                       recorded_in="docs/approval.md"))
    with pytest.raises(ConfigError, match="naming its relay release"):
        create_app(settings, hermes_runner=object(), hermes_config=config)  # type: ignore[arg-type]


def test_a_matching_record_does_not_admit_wallet_execution_or_authored_modes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    base = production_env(EDGE_OS_INTERPRETER="hermes_local",
                          EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
                          EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path))
    for change, message in (
            ({"EDGE_OS_WALLET_PROVIDER": "fixture"}, "wallet_provider"),
            ({"EDGE_OS_EXECUTION_MODE": "fixture"}, "execution_mode"),
            ({"EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"}, "research_history_mode"),
            ({"EDGE_OS_RESEARCH_SOURCE_CLIENTS": "authored_http"}, "research_source_clients"),
            ({"EDGE_OS_NANSEN_RESEARCH_MODE": "authored_fixture"}, "nansen_research_mode")):
        with pytest.raises(ConfigError, match=message):
            load_settings({**base, **change})


def test_local_hermes_local_needs_no_record() -> None:
    env = harness.api_env(database_url="postgresql+psycopg://app@127.0.0.1:5432/edge_os_test_local",
                          public_pem=TestSigner().public_pem, previous_pem=None, cors=["http://127.0.0.1:3999"])
    settings = load_settings({**env, "EDGE_OS_ENV": "local", "EDGE_OS_INTERPRETER": "hermes_local"})
    assert settings.interpreter == "hermes_local"


# --- The research release is admitted only by its exact record binding -------------------------------------------------


def test_a_matching_record_admits_the_approved_research_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.core.research.released_runtime_bootstrap import server_research_runtime

    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    settings = load_settings(production_env(
        EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path)))
    runtime = server_research_runtime(settings)
    assert runtime is not None
    assert runtime.release.release_id == RESEARCH_ID and runtime.release_sha256 == RESEARCH_SHA


def test_a_record_with_another_research_hash_is_refused_at_composition(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.core.research.operating_release import ReleaseRefused
    from edge_os_api.core.research.released_runtime_bootstrap import server_research_runtime

    value = record(research_release={"release_id": RESEARCH_ID, "sha256": "e" * 64})
    path, sha = write_record(tmp_path, value)
    approve(monkeypatch, value, sha)
    settings = load_settings(production_env(
        EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path)))
    with pytest.raises(ReleaseRefused, match="hosted_deployment_not_matched"):
        server_research_runtime(settings)


# --- A production server with no named record starts with research off -----------------------------------------------


def test_no_record_in_production_composes_nothing_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    from edge_os_api.core.research.released_runtime_bootstrap import server_research_runtime

    settings = running(deployment_id=None)
    settings.env = "production"
    with caplog.at_level(logging.INFO, logger="edge_os"):
        assert server_research_runtime(settings) is None
    assert "research is off: no hosted deployment is named" in caplog.text


def test_create_app_starts_with_research_off_when_no_record_is_named(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from edge_os_api import main as main_module

    monkeypatch.setattr(main_module, "make_engine", lambda *_a, **_k: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(main_module, "require_head", lambda _engine: None)
    monkeypatch.setattr(main_module, "make_session_factory", lambda _engine: (lambda: SimpleNamespace()))
    with caplog.at_level(logging.INFO, logger="edge_os"):
        app = create_app(load_settings(production_env()))
    assert app.state.research_runtime is None
    assert "research is off: no hosted deployment is named" in caplog.text


def test_the_worker_main_starts_without_research_when_no_record_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.core import database, settings as settings_module, worker_loop
    from edge_os_api.research import investigation_jobs

    configured = load_settings(production_env())
    monkeypatch.setattr(settings_module, "load_settings", lambda: configured)
    monkeypatch.setattr(database, "make_engine", lambda *_a, **_k: object())
    monkeypatch.setattr(database, "make_session_factory", lambda _engine: object())
    captured: dict[str, Any] = {}

    class RecordingWorker:
        def __init__(self, _factory: Any, _settings: Any, *, research_runtime: Any = None, **_kwargs: Any) -> None:
            captured["runtime"] = research_runtime

        def run_pending(self, limit: int = 20) -> list[Any]:
            return []

    monkeypatch.setattr(investigation_jobs, "InvestigationWorker", RecordingWorker)
    monkeypatch.setattr(worker_loop, "run", lambda *_a, **_k: 0)
    monkeypatch.setattr(worker_loop, "exit_with", lambda _code: None)
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    investigation_jobs.main()
    assert captured.get("runtime") is None


@pytest.mark.parametrize("case", ["incomplete", "unapproved", "expired"])
def test_a_named_record_that_cannot_be_used_is_still_refused_at_composition(
        case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.core.research.operating_release import ReleaseRefused
    from edge_os_api.core.research.released_runtime_bootstrap import server_research_runtime

    if case == "incomplete":
        settings = running(deployment_id=DEPLOYMENT)
    elif case == "unapproved":
        path, _sha = write_record(tmp_path, record())
        settings = running(record_path=path)
    else:
        value = record(valid_from="2020-01-01T00:00:00Z", valid_until="2020-01-02T00:00:00Z")
        path, sha = write_record(tmp_path, value)
        approve(monkeypatch, value, sha)
        settings = running(record_path=path)
    settings.env = "production"
    with pytest.raises(ReleaseRefused, match="hosted_deployment_refused"):
        server_research_runtime(settings)


def test_create_app_refuses_a_passed_runtime_with_another_research_hash(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from edge_os_api.core.research.released_runtime_bootstrap import server_research_runtime

    local = server_research_runtime(SimpleNamespace(env="local"))
    assert local is not None
    value = record(research_release={"release_id": RESEARCH_ID, "sha256": "e" * 64})
    path, sha = write_record(tmp_path, value)
    approve(monkeypatch, value, sha)
    settings = load_settings(production_env(
        EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
        EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path)))
    with pytest.raises(ConfigError, match="no approved hosted deployment record names"):
        create_app(settings, research_runtime=local)


# --- Record v2: the execution release, and the production gate for controlled execution -----------------------------

EXECUTION_ID = "inapp-wmon-moe-20261023/1"
EXECUTION_SHA = "4" * 64


def record_v2(**changes: Any) -> dict[str, Any]:
    value = record(schema_version=hosted_deployment.RECORD_VERSION_2,
                   execution_release={"release_id": EXECUTION_ID, "sha256": EXECUTION_SHA})
    value.update(changes)
    return value


def approve_actual(monkeypatch: pytest.MonkeyPatch, releases: dict[str, str]) -> None:
    from edge_os_api.execution import operating_release

    monkeypatch.setattr(operating_release, "APPROVED_ACTUAL_RELEASES", releases)


def controlled_env(path: Path, **changes: str) -> dict[str, str]:
    return production_env(EDGE_OS_EXECUTION_MODE="controlled", EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT,
                          EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path), **changes)


def test_a_v2_record_binds_its_exact_execution_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record_v2())
    approve(monkeypatch, record_v2(), sha)
    loaded = hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert loaded is not None
    assert (loaded.execution_release_id, loaded.execution_release_sha256) == (EXECUTION_ID, EXECUTION_SHA)
    assert loaded.admits_execution_release(EXECUTION_ID, EXECUTION_SHA)
    assert not loaded.admits_execution_release(EXECUTION_ID, "5" * 64)
    assert not loaded.admits_execution_release("another-release/1", EXECUTION_SHA)
    assert loaded.admits_research_release(RESEARCH_ID, RESEARCH_SHA)


def test_a_v1_record_still_parses_and_grants_no_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    loaded = hosted_deployment.check_hosted_deployment(running(record_path=path))
    assert loaded is not None
    assert loaded.execution_release_id is None and loaded.execution_release_sha256 is None
    assert not loaded.admits_execution_release(EXECUTION_ID, EXECUTION_SHA)
    assert not loaded.admits_execution_release("", "")


@pytest.mark.parametrize("value", [
    record(execution_release={"release_id": EXECUTION_ID, "sha256": EXECUTION_SHA}),
    {key: item for key, item in record_v2().items() if key != "execution_release"},
    record_v2(execution_release=None),
    record_v2(execution_release={"release_id": EXECUTION_ID}),
    record_v2(execution_release={"release_id": EXECUTION_ID, "sha256": EXECUTION_SHA, "extra": "x"}),
    record_v2(execution_release={"release_id": EXECUTION_ID, "sha256": "A" * 64}),
    record_v2(execution_release={"release_id": "", "sha256": EXECUTION_SHA}),
    record_v2(schema_version="edge-os.hosted-deployment/3"),
])
def test_a_malformed_execution_binding_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                  value: dict[str, Any]) -> None:
    path, sha = write_record(tmp_path, value)
    approve(monkeypatch, value, sha)
    with pytest.raises(HostedDeploymentRefused, match="hosted_deployment_invalid"):
        hosted_deployment.check_hosted_deployment(running(record_path=path))


def test_production_refuses_controlled_execution_without_a_named_record() -> None:
    with pytest.raises(ConfigError, match="execution_mode: controlled execution needs an approved hosted deployment"):
        load_settings(production_env(EDGE_OS_EXECUTION_MODE="controlled"))


def test_production_refuses_controlled_execution_for_an_unregistered_record(tmp_path: Path) -> None:
    path, _ = write_record(tmp_path, record_v2())
    with pytest.raises(ConfigError) as caught:
        load_settings(controlled_env(path))
    assert "hosted_deployment: hosted_deployment_not_approved" in str(caught.value)
    assert "execution_mode: controlled execution needs an approved hosted deployment" in str(caught.value)


def test_production_refuses_controlled_execution_for_a_v1_record(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    approve_actual(monkeypatch, {EXECUTION_ID: EXECUTION_SHA})
    with pytest.raises(ConfigError, match="execution_mode: the hosted deployment record binds no execution release"):
        load_settings(controlled_env(path))


@pytest.mark.parametrize("actual", [{}, {EXECUTION_ID: "5" * 64}, {"another-release/1": EXECUTION_SHA}])
def test_production_refuses_a_bound_release_that_is_not_the_approved_execution_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actual: dict[str, str]) -> None:
    path, sha = write_record(tmp_path, record_v2())
    approve(monkeypatch, record_v2(), sha)
    approve_actual(monkeypatch, actual)
    with pytest.raises(ConfigError, match="execution_mode: the record's execution release is not the approved "
                                          "actual execution release"):
        load_settings(controlled_env(path))


def test_production_admits_controlled_execution_only_for_the_exact_bound_release(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record_v2())
    approve(monkeypatch, record_v2(), sha)
    approve_actual(monkeypatch, {EXECUTION_ID: EXECUTION_SHA})
    settings = load_settings(controlled_env(path))
    assert settings.execution_mode == "controlled"


def test_controlled_execution_never_admits_the_privy_app_secret(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record_v2())
    approve(monkeypatch, record_v2(), sha)
    approve_actual(monkeypatch, {EXECUTION_ID: EXECUTION_SHA})
    with pytest.raises(ConfigError) as caught:
        load_settings({**controlled_env(path), "EDGE_OS_PRIVY_APP_SECRET": "do-not-print"})
    assert "EDGE_OS_PRIVY_APP_SECRET" in str(caught.value)
    assert "do-not-print" not in str(caught.value)


def test_a_v2_record_does_not_admit_fixture_execution_or_other_modes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record_v2())
    approve(monkeypatch, record_v2(), sha)
    approve_actual(monkeypatch, {EXECUTION_ID: EXECUTION_SHA})
    base = controlled_env(path)
    for change, message in (
            ({"EDGE_OS_EXECUTION_MODE": "fixture"}, "execution_mode"),
            ({"EDGE_OS_WALLET_PROVIDER": "fixture"}, "wallet_provider"),
            ({"EDGE_OS_RESEARCH_HISTORY_MODE": "recorded"}, "research_history_mode")):
        with pytest.raises(ConfigError, match=message):
            load_settings({**base, **change})


def test_the_approved_actual_execution_releases_stay_empty() -> None:
    from edge_os_api.execution import operating_release

    assert dict(operating_release.APPROVED_ACTUAL_RELEASES) == {}


# --- Loopback database route for the host research worker (builder decision 2026-10-23, option A) -------------------

LOOPBACK_URL = "postgresql+psycopg://app@127.0.0.1:5432/edge_os?sslmode={mode}"
LOOPBACK_REFUSAL = "database_url: production needs a hosted database, not a loopback host"


def loopback_env(path: Path | None = None, *, mode: str = "verify-full", host: str = "127.0.0.1",
                 **changes: str) -> dict[str, str]:
    env = production_env(EDGE_OS_DATABASE_URL=LOOPBACK_URL.format(mode=mode).replace("127.0.0.1", host), **changes)
    if path is not None:
        env.update(EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT, EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path))
    return env


def test_production_refuses_a_loopback_database_without_a_named_record() -> None:
    with pytest.raises(ConfigError, match=LOOPBACK_REFUSAL):
        load_settings(loopback_env())


def test_production_refuses_a_loopback_database_for_an_unregistered_record(tmp_path: Path) -> None:
    path, _ = write_record(tmp_path, record())
    with pytest.raises(ConfigError) as caught:
        load_settings(loopback_env(path))
    assert "hosted_deployment: hosted_deployment_not_approved" in str(caught.value)
    assert LOOPBACK_REFUSAL in str(caught.value)


def test_production_refuses_a_loopback_database_whose_sslmode_differs_from_the_record(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    with pytest.raises(ConfigError) as caught:
        load_settings(loopback_env(path, mode="require"))
    assert "hosted_deployment: hosted_deployment_tls_mismatch" in str(caught.value)
    assert LOOPBACK_REFUSAL in str(caught.value)


@pytest.mark.parametrize("value", [record(), record_v2()])
def test_production_admits_127_0_0_1_only_for_a_registered_record_with_its_tls_mode(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: dict[str, Any]) -> None:
    path, sha = write_record(tmp_path, value)
    approve(monkeypatch, value, sha)
    settings = load_settings(loopback_env(path))
    assert settings.database_url.startswith("postgresql+psycopg://app@127.0.0.1:5432/")


@pytest.mark.parametrize("host", ["localhost", ""])
def test_production_still_refuses_other_loopback_forms_with_a_registered_record(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    with pytest.raises(ConfigError, match=LOOPBACK_REFUSAL):
        load_settings(loopback_env(path, host=host))


def test_a_v1_record_admits_the_loopback_route_but_still_no_controlled_execution(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    approve_actual(monkeypatch, {EXECUTION_ID: EXECUTION_SHA})
    with pytest.raises(ConfigError) as caught:
        load_settings(loopback_env(path, EDGE_OS_EXECUTION_MODE="controlled"))
    assert "execution_mode: the hosted deployment record binds no execution release" in str(caught.value)
    assert LOOPBACK_REFUSAL not in str(caught.value)


def test_a_non_loopback_production_database_is_unchanged_by_the_loopback_route(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings(production_env()).database_url == production_env()["EDGE_OS_DATABASE_URL"]
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    named = production_env(EDGE_OS_HOSTED_DEPLOYMENT_ID=DEPLOYMENT, EDGE_OS_HOSTED_DEPLOYMENT_RECORD_PATH=str(path))
    assert load_settings(named).database_url == named["EDGE_OS_DATABASE_URL"]


# --- Every loopback, unspecified or multi-host database host is refused in production ------------------------------

OTHER_LOOPBACK_HOSTS = [
    "", "localhost", "LOCALHOST", "LocalHost", "localhost.", "LOCALHOST.", "db.localhost", "DB.LOCALHOST.",
    "127.0.0.1.", "127.0.0.2", "127.1.2.3", "127.255.255.254", "127.1", "2130706433", "0x7f000001", "0177.0.0.1",
    "[::1]", "[0:0:0:0:0:0:0:1]", "[::0001]", "[::1%25lo]", "[::ffff:127.0.0.1]", "[::ffff:7f00:2]",
    "0.0.0.0", "0", "[::]", "[::ffff:0.0.0.0]",
    "127.0.0.1,db.example", "db.example,127.0.0.1", "db.example,db2.example", " 127.0.0.1", "127.0.0.1%09",
]


@pytest.mark.parametrize("host", OTHER_LOOPBACK_HOSTS)
def test_production_refuses_every_other_loopback_unspecified_or_multi_host_form(host: str) -> None:
    with pytest.raises(ConfigError, match=LOOPBACK_REFUSAL):
        load_settings(loopback_env(host=host))


@pytest.mark.parametrize("host", OTHER_LOOPBACK_HOSTS)
def test_a_registered_record_admits_none_of_the_other_loopback_forms(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    path, sha = write_record(tmp_path, record())
    approve(monkeypatch, record(), sha)
    with pytest.raises(ConfigError, match=LOOPBACK_REFUSAL):
        load_settings(loopback_env(path, host=host))


@pytest.mark.parametrize("host", ["edge-os-postgres", "db.example", "localhost.example", "mylocalhost",
                                  "127.example", "10.0.0.5", "128.0.0.1", "1.2.3.4", "[2001:db8::1]",
                                  "[::ffff:10.0.0.5]"])
def test_production_admits_non_loopback_hosts_as_before(host: str) -> None:
    settings = load_settings(loopback_env(host=host))
    assert settings.database_url == LOOPBACK_URL.format(mode="verify-full").replace("127.0.0.1", host)


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "[::1]", "127.0.0.2", "0.0.0.0", "127.0.0.1,db.example"])
def test_local_keeps_accepting_loopback_forms(host: str) -> None:
    url = f"postgresql+psycopg://app@{host}:5432/edge_os"
    settings = load_settings(production_env(EDGE_OS_ENV="local", EDGE_OS_DATABASE_URL=url))
    assert settings.database_url == url
