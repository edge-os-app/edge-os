"""The hosted activation record: a code-owned approval that alone admits three production parts.

Pure tests (no database, Docker or network). The registry is empty in this candidate; a test patches it with a
synthetic record to prove that only the named parts are admitted. Every other production refusal and every local
behaviour stays as it was.
"""

from __future__ import annotations

import hashlib
import json
import os
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
RESEARCH_ID = "actual-moe-nansen-demo-20261018/1"
RESEARCH_SHA = "dce1e05ffdecf72eedaf340e55fad0e2a4271c1ea7860d15aed17fd2c1b1d743"
IMAGE = "sha256:" + "1" * 64
GATE_SHA = "2" * 64
DEPLOYMENT = "hosted-demo-1"


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


def test_the_code_owned_registry_is_empty_in_this_candidate() -> None:
    assert hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS == {}


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


# --- Both research entry points refuse without a matching record -------------------------------------------------------


def test_create_app_refuses_the_approved_research_release_without_a_record() -> None:
    with pytest.raises(ConfigError, match="research_runtime: hosted_deployment"):
        create_app(load_settings(production_env()))


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


def test_the_worker_main_refuses_before_it_runs_without_a_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from edge_os_api.core import database, settings as settings_module
    from edge_os_api.core.research.operating_release import ReleaseRefused
    from edge_os_api.research import investigation_jobs

    configured = load_settings(production_env())
    monkeypatch.setattr(settings_module, "load_settings", lambda: configured)
    monkeypatch.setattr(database, "make_engine", lambda *_a, **_k: object())
    monkeypatch.setattr(database, "make_session_factory", lambda _engine: object())
    monkeypatch.setattr("sys.argv", ["worker", "--once"])
    with pytest.raises(ReleaseRefused, match="hosted_deployment"):
        investigation_jobs.main()
