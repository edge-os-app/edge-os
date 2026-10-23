"""The worker builds its one controlled runtime from worker-only settings and an approved release.

Every approval here is authored for the test (`SYNTHETIC_FIXTURE`). No real key, wallet, release or provider is
used, and no socket is opened. The API role must never receive a signer.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import edge_os_api.core.provider_ports as provider_ports
from edge_os_api.core import hosted_deployment
from edge_os_api.core.provider_ports import build_provider_ports
import edge_os_api.execution.released_execution_bootstrap as bootstrap
from edge_os_api.execution.direct_route_quote_client import build_program_hex
from edge_os_api.execution.operating_release import BoundRelease, OperatingRelease, release_sha256
from edge_os_api.execution.released_execution_bootstrap import (
    ExecutionBootstrapRefused,
    ReleaseCandidate,
    build_worker_execution_runtime,
    load_authorization_key,
    read_worker_execution_settings,
)
from edge_os_api.execution.worker import build_worker_ports
from execution.test_operating_release import definition

NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
APP_ID = "cltestappid0000000000000000"
APP_SECRET = "test-app-secret-0000000000000000"
WALLET_ID = "synthetic-wallet-a"
RPC_URL = "https://rpc.invalid/rpc"
POOL = "0x" + "4" * 40


def app_settings(env: str = "local", mode: str = "controlled") -> SimpleNamespace:
    return SimpleNamespace(env=env, execution_mode=mode)


def key_material():
    return ec.generate_private_key(ec.SECP256R1())


def write_key(path: Path, key=None, mode: int = 0o600) -> tuple[Path, object]:
    key = key_material() if key is None else key
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(mode)
    return path, key


def environment(key_path: Path) -> dict[str, str]:
    return {
        "EDGE_OS_EXECUTION_PRIVY_APP_ID": APP_ID,
        "EDGE_OS_EXECUTION_PRIVY_APP_SECRET": APP_SECRET,
        "EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH": str(key_path),
        "EDGE_OS_EXECUTION_SERVER_WALLET_ID": WALLET_ID,
        "EDGE_OS_EXECUTION_MONAD_RPC_URL": RPC_URL,
    }


def direct_definition(*, wallet_id: str = WALLET_ID, wallet_address: str = "0x" + "1" * 40,
                      release_id: str = "synthetic-exec-bootstrap-a") -> dict:
    source = definition()
    input_token = source["route"]["input_asset"]["token_address"]
    source.update(release_id=release_id, wallet_id=wallet_id, wallet_address=wallet_address)
    source["route"].update(method="EXECUTE_SWAP", selector="0xce1e7030", recipient=wallet_address,
                           approved_program_hex=build_program_hex(input_token=input_token, pool_address=POOL,
                                                                  direction=0, fee_ppm=16000))
    source["quote"] = {"source": "DIRECT_V2_PROGRAM", "endpoint": "https://quote.invalid/rpc", "slippage_bps": 50,
                       "pool_address": POOL, "token0_address": input_token,
                       "token1_address": source["route"]["output_asset"]["token_address"],
                       "direction": 0, "program_fee_ppm": 16000}
    return source


def identity(*, wallet_id: str = WALLET_ID, wallet_address: str = "0x" + "1" * 40,
             owner_id: str = "owner-a", agent_id: str = "agent-a",
             consent_adoption_id: str = "consent-a") -> dict[str, str]:
    return {"owner_id": owner_id, "agent_id": agent_id, "wallet_id": wallet_id,
            "wallet_address": wallet_address, "network_id": "monad:143", "strategy_id": "strategy-a",
            "publication_revision_id": "publication-a", "execution_revision_id": "execution-a",
            "market_binding_id": "market-a", "content_sha256": "1" * 64, "manifest_sha256": "2" * 64,
            "consent_adoption_id": consent_adoption_id, "consent_hash": "sha256:" + "3" * 64,
            "review_hash": "sha256:" + "4" * 64, "terms_hash": "sha256:" + "5" * 64}


def synthetic_candidate(**release_overrides) -> tuple[ReleaseCandidate, dict[str, str], dict[str, str]]:
    release = OperatingRelease(direct_definition(**release_overrides))
    bound = BoundRelease(release, identity(wallet_id=release.content()["wallet_id"],
                                           wallet_address=release.content()["wallet_address"]),
                        position_inventory_proof_sha256="6" * 64, market_proof_sha256="7" * 64,
                        finality_proof_sha256="8" * 64)
    digest = release_sha256(release)
    return ReleaseCandidate(release=release, binding=bound), {release.content()["release_id"]: digest}, {
        bound.sha256: digest}


def build(tmp_path, *, candidates=None, settings=None, env=None, approvals=None, bindings=None,
          expected_identity=None):
    default_candidate, default_approvals, default_bindings = synthetic_candidate()
    write_key(tmp_path / "key.pem")
    return build_worker_execution_runtime(
        role="worker", settings=app_settings() if settings is None else settings,
        candidates=(default_candidate,) if candidates is None else candidates,
        environ=environment(tmp_path / "key.pem") if env is None else env,
        approvals=default_approvals if approvals is None else approvals,
        bindings=default_bindings if bindings is None else bindings,
        expected_identity=expected_identity, clock=lambda: NOW, http=object())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


# ------------------------------------------------------------------------------------- the worker-only settings

@pytest.mark.parametrize("name, code", [
    ("EDGE_OS_EXECUTION_PRIVY_APP_ID", "EXECUTION_BOOTSTRAP_APP_ID_MISSING"),
    ("EDGE_OS_EXECUTION_PRIVY_APP_SECRET", "EXECUTION_BOOTSTRAP_APP_SECRET_MISSING"),
    ("EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH", "EXECUTION_BOOTSTRAP_KEY_PATH_MISSING"),
    ("EDGE_OS_EXECUTION_SERVER_WALLET_ID", "EXECUTION_BOOTSTRAP_WALLET_ID_MISSING"),
    ("EDGE_OS_EXECUTION_MONAD_RPC_URL", "EXECUTION_BOOTSTRAP_RPC_URL_MISSING"),
])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_every_missing_or_blank_worker_setting_refuses_with_its_own_reason(tmp_path, name, code, value):
    env = environment(tmp_path / "key.pem")
    if value is None:
        env.pop(name)
    else:
        env[name] = value
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        read_worker_execution_settings(env)
    assert refused.value.code == code


@pytest.mark.parametrize("name, value, code", [
    ("EDGE_OS_EXECUTION_PRIVY_APP_ID", "bad app id", "EXECUTION_BOOTSTRAP_APP_ID_INVALID"),
    ("EDGE_OS_EXECUTION_PRIVY_APP_SECRET", "with space", "EXECUTION_BOOTSTRAP_APP_SECRET_INVALID"),
    ("EDGE_OS_EXECUTION_AUTHORIZATION_KEY_PATH", "relative/key.pem", "EXECUTION_BOOTSTRAP_KEY_PATH_INVALID"),
    ("EDGE_OS_EXECUTION_SERVER_WALLET_ID", "bad wallet id", "EXECUTION_BOOTSTRAP_WALLET_ID_INVALID"),
    ("EDGE_OS_EXECUTION_MONAD_RPC_URL", "http://rpc.invalid", "EXECUTION_BOOTSTRAP_RPC_URL_INVALID"),
])
def test_a_malformed_worker_setting_refuses_with_a_named_reason(tmp_path, name, value, code):
    env = environment(tmp_path / "key.pem")
    env[name] = value
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        read_worker_execution_settings(env)
    assert refused.value.code == code


def test_settings_never_echo_a_secret_or_a_path(tmp_path):
    env = environment(tmp_path / "key.pem")
    env["EDGE_OS_EXECUTION_PRIVY_APP_SECRET"] = "secret with space"
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        read_worker_execution_settings(env)
    assert "secret with space" not in str(refused.value)
    assert str(refused.value) == "EXECUTION_BOOTSTRAP_APP_SECRET_INVALID"


# ------------------------------------------------------------------------------------------------ key custody

def test_key_file_must_be_owner_only_and_a_p256_private_key(tmp_path, monkeypatch):
    path, key = write_key(tmp_path / "key.pem")
    assert isinstance(load_authorization_key(path), ec.EllipticCurvePrivateKey)

    unreadable = tmp_path / "missing.pem"
    with pytest.raises(ExecutionBootstrapRefused, match="KEY_FILE_UNREADABLE"):
        load_authorization_key(unreadable)

    other_owned, _ = write_key(tmp_path / "other.pem")
    current_uid = os.geteuid()
    with monkeypatch.context() as patch:
        patch.setattr(bootstrap.os, "geteuid", lambda: current_uid + 1)
        with pytest.raises(ExecutionBootstrapRefused, match="KEY_FILE_NOT_OWNED"):
            load_authorization_key(other_owned)

    loose, _ = write_key(tmp_path / "loose.pem", mode=0o644)
    with pytest.raises(ExecutionBootstrapRefused, match="KEY_FILE_NOT_OWNER_ONLY"):
        load_authorization_key(loose)

    invalid = tmp_path / "invalid.pem"
    invalid.write_text("not a key", encoding="utf-8")
    invalid.chmod(0o600)
    with pytest.raises(ExecutionBootstrapRefused, match="KEY_INVALID"):
        load_authorization_key(invalid)

    wrong_curve, _ = write_key(tmp_path / "wrong.pem", key=ec.generate_private_key(ec.SECP384R1()))
    with pytest.raises(ExecutionBootstrapRefused, match="KEY_INVALID"):
        load_authorization_key(wrong_curve)


# ---------------------------------------------------------------------------------- the role and environment gate

def test_the_api_role_is_refused_before_any_setting_or_key_read():
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build_worker_execution_runtime(role="api", settings=app_settings(), candidates=(),
                                       environ={}, clock=lambda: NOW)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_ROLE_NOT_WORKER"


@pytest.mark.parametrize("env", ["test"])
def test_a_non_local_non_production_environment_is_refused_before_the_key_file(tmp_path, env):
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build_worker_execution_runtime(role="worker", settings=app_settings(env=env), candidates=(),
                                       environ=environment(tmp_path / "absent.pem"), clock=lambda: NOW)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_ENV_NOT_ADMITTED"


# ----------------------------------------------------------------------------------------- release and binding

def test_empty_approved_registries_refuse_before_reading_the_key(tmp_path):
    candidate, _, _ = synthetic_candidate()
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build_worker_execution_runtime(role="worker", settings=app_settings(), candidates=(candidate,),
                                       environ=environment(tmp_path / "absent.pem"), clock=lambda: NOW)
    assert refused.value.code == "EXECUTION_RELEASE_NOT_APPROVED"


def test_an_unapproved_binding_refuses(tmp_path):
    candidate, approvals, _ = synthetic_candidate()
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build(tmp_path, candidates=(candidate,), approvals=approvals, bindings={})
    assert refused.value.code == "EXECUTION_BINDING_NOT_APPROVED"


def test_an_unapproved_synthetic_release_refuses(tmp_path):
    candidate, _, bindings = synthetic_candidate()
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build(tmp_path, candidates=(candidate,), approvals={}, bindings=bindings)
    assert refused.value.code == "EXECUTION_RELEASE_NOT_APPROVED"


def test_two_admitted_releases_refuse(tmp_path):
    first, approvals, bindings = synthetic_candidate()
    second, second_approvals, second_bindings = synthetic_candidate(release_id="synthetic-exec-bootstrap-b")
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build(tmp_path, candidates=(first, second), approvals={**approvals, **second_approvals},
              bindings={**bindings, **second_bindings})
    assert refused.value.code == "EXECUTION_BOOTSTRAP_MULTIPLE_RELEASES"


def test_the_binding_wallet_must_equal_the_worker_wallet_setting(tmp_path):
    candidate, *_ = synthetic_candidate()
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build(tmp_path, candidates=(candidate,), expected_identity=None,
              env={**environment(tmp_path / "key.pem"), "EDGE_OS_EXECUTION_SERVER_WALLET_ID": "another-wallet"})
    assert refused.value.code == "EXECUTION_BOOTSTRAP_WALLET_MISMATCH"


def test_a_mismatched_saved_owner_agent_or_consent_refuses(tmp_path):
    candidate, *_ = synthetic_candidate()
    write_key(tmp_path / "key.pem")
    for changed in ({"owner_id": "foreign-owner"}, {"agent_id": "foreign-agent"},
                    {"consent_adoption_id": "foreign-consent"}):
        with pytest.raises(ExecutionBootstrapRefused) as refused:
            build(tmp_path, candidates=(candidate,), expected_identity={**identity(), **changed})
        assert refused.value.code == "EXECUTION_BOOTSTRAP_IDENTITY_MISMATCH"


def test_a_matching_saved_identity_is_accepted(tmp_path):
    candidate, *_ = synthetic_candidate()
    built = build(tmp_path, candidates=(candidate,), expected_identity=identity())
    assert built.agent_id == "agent-a"


# ------------------------------------------------------------------------------------------ one worker runtime

def test_the_worker_builds_one_runtime_and_leaves_the_module_registry_empty(tmp_path):
    candidate, *_ = synthetic_candidate()
    built = build(tmp_path, candidates=(candidate,))
    assert built.agent_id == "agent-a"
    runtime = built.runtime
    assert runtime.binding is candidate.binding
    assert runtime.quote_token is None
    access = runtime.signer_access()
    assert access["app_id"] == APP_ID and access["app_secret"] == APP_SECRET
    assert callable(access["authorize"])
    with pytest.raises(ValueError):
        access["authorize"]({})
    assert provider_ports.CONTROLLED_RUNTIMES == {}


def test_a_kuru_quote_release_refuses_because_no_quote_token_setting_exists(tmp_path):
    source = definition()
    source["wallet_id"] = WALLET_ID
    release = OperatingRelease(source)
    bound = BoundRelease(release, identity(wallet_address=source["wallet_address"]),
                         position_inventory_proof_sha256="6" * 64, market_proof_sha256="7" * 64,
                         finality_proof_sha256="8" * 64)
    digest = release_sha256(release)
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        build(tmp_path, candidates=(ReleaseCandidate(release=release, binding=bound),),
              approvals={source["release_id"]: digest}, bindings={bound.sha256: digest})
    assert refused.value.code == "EXECUTION_BOOTSTRAP_QUOTE_TOKEN_UNAVAILABLE"


def test_the_worker_ports_get_the_signer_and_the_api_copy_does_not(tmp_path):
    candidate, *_ = synthetic_candidate()
    built = build(tmp_path, candidates=(candidate,))
    worker = build_provider_ports("controlled", None, role="worker", controlled=built.ports)
    assert worker.controlled["agent-a"].signer_access is not None
    api = worker.for_role("api")
    assert api.role == "api"
    assert api.controlled["agent-a"].signer_access is None
    assert api.controlled["agent-a"].quote_token is None
    assert api.original_clients("agent-a") is None
    assert worker.for_role("recurring").controlled["agent-a"].signer_access is None


def test_the_api_role_never_builds_a_runtime_even_with_a_full_synthetic_candidate(tmp_path):
    candidate, approvals, bindings = synthetic_candidate()
    write_key(tmp_path / "key.pem")
    with pytest.raises(ExecutionBootstrapRefused, match="ROLE_NOT_WORKER"):
        build_worker_execution_runtime(role="api", settings=app_settings(), candidates=(candidate,),
                                       environ=environment(tmp_path / "key.pem"), approvals=approvals,
                                       bindings=bindings, clock=lambda: NOW)


def test_worker_ports_are_built_only_in_controlled_mode_and_fail_closed(tmp_path):
    assert build_worker_ports(app_settings(mode="fixture"), None, candidates=()) is None
    assert build_worker_ports(app_settings(mode="unavailable"), None, candidates=()) is None
    with pytest.raises(ExecutionBootstrapRefused, match="EXECUTION_RELEASE_NOT_APPROVED"):
        build_worker_ports(app_settings(mode="controlled"), None, candidates=(),
                           environ=environment(tmp_path / "absent.pem"))


def test_the_module_has_no_environment_loaded_registry():
    assert provider_ports.CONTROLLED_RUNTIMES == {}
    assert not hasattr(provider_ports, "register")


# ------------------------------------------------ production admission: a hosted record v2 that binds this release

RECORD_DEPLOYMENT = "hosted-exec-1"
RECORD_ORIGIN = "https://app.example.com"
RECORD_DATABASE_URL = "postgresql+psycopg://app@db.internal.example:5432/edge_os?sslmode=verify-full"


def record_v2(*, execution_id: str, execution_sha: str) -> dict:
    """One synthetic v2 record. Only its execution binding changes between cases."""
    return {
        "schema_version": hosted_deployment.RECORD_VERSION_2,
        "deployment_id": RECORD_DEPLOYMENT,
        "public_origins": [RECORD_ORIGIN],
        "cors_origins": [RECORD_ORIGIN],
        "database_tls_mode": "verify-full",
        "hermes_relay": {"release_id": "synthetic-relay/1", "record_sha256": "9" * 64},
        "research_release": {"release_id": "synthetic-research/1", "sha256": "a" * 64},
        "host_gates": {
            "h1_egress": {"path": "docs/qualification/hosted-gates/H1.md", "sha256": "b" * 64},
            "h2_runner_isolation": {"path": "docs/qualification/hosted-gates/H2.md", "sha256": "c" * 64},
            "h8_provider_spend_cap": {"path": "docs/qualification/hosted-gates/H8.md", "sha256": "d" * 64},
            "h10_backup_restore": {"path": "docs/qualification/hosted-gates/H10.md", "sha256": "e" * 64},
        },
        "image_digests": {"api": "sha256:" + "f" * 64},
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_until": "2027-01-01T00:00:00Z",
        "execution_release": {"release_id": execution_id, "sha256": execution_sha},
    }


def write_record(folder: Path, value: dict) -> tuple[Path, str]:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path = folder / "deployment.json"
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def production_settings(record_path: Path | None, *, deployment_id: str | None = RECORD_DEPLOYMENT):
    return SimpleNamespace(
        env="production", execution_mode="controlled", hosted_deployment_id=deployment_id,
        hosted_deployment_record_path=None if record_path is None else str(record_path),
        cors_origins=[RECORD_ORIGIN], database_url=RECORD_DATABASE_URL)


def production_refused(tmp_path, path, *, candidates, approvals, bindings, deployment_id=RECORD_DEPLOYMENT):
    """Build in production with an absent key file: admission must refuse before any key read."""
    return build_worker_execution_runtime(
        role="worker", settings=production_settings(path, deployment_id=deployment_id), candidates=candidates,
        environ=environment(tmp_path / "absent.pem"), approvals=approvals, bindings=bindings, clock=lambda: NOW)


def test_production_admits_a_v2_record_that_binds_the_admitted_release(tmp_path, monkeypatch):
    candidate, approvals, bindings = synthetic_candidate()
    digest = release_sha256(candidate.release)
    path, sha = write_record(tmp_path, record_v2(execution_id=candidate.release.content()["release_id"],
                                                 execution_sha=digest))
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {RECORD_DEPLOYMENT: sha})
    write_key(tmp_path / "key.pem")
    built = build_worker_execution_runtime(
        role="worker", settings=production_settings(path), candidates=(candidate,),
        environ=environment(tmp_path / "key.pem"), approvals=approvals, bindings=bindings, clock=lambda: NOW,
        http=object())
    assert built.agent_id == "agent-a"


def test_production_refuses_without_a_named_record_before_the_key_file(tmp_path):
    candidate, approvals, bindings = synthetic_candidate()
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        production_refused(tmp_path, None, deployment_id=None, candidates=(candidate,),
                           approvals=approvals, bindings=bindings)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_HOSTED_RECORD_REFUSED"


def test_production_refuses_an_unregistered_record_before_the_key_file(tmp_path):
    candidate, approvals, bindings = synthetic_candidate()
    path, _ = write_record(tmp_path, record_v2(execution_id=candidate.release.content()["release_id"],
                                               execution_sha=release_sha256(candidate.release)))
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        production_refused(tmp_path, path, candidates=(candidate,), approvals=approvals, bindings=bindings)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_HOSTED_RECORD_REFUSED"


def test_production_refuses_a_v1_record_before_the_key_file(tmp_path, monkeypatch):
    candidate, approvals, bindings = synthetic_candidate()
    value = record_v2(execution_id=candidate.release.content()["release_id"],
                      execution_sha=release_sha256(candidate.release))
    value = {key: item for key, item in value.items() if key != "execution_release"}
    value["schema_version"] = hosted_deployment.RECORD_VERSION
    path, sha = write_record(tmp_path, value)
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {RECORD_DEPLOYMENT: sha})
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        production_refused(tmp_path, path, candidates=(candidate,), approvals=approvals, bindings=bindings)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_HOSTED_RELEASE_MISMATCH"


@pytest.mark.parametrize("execution_id, execution_sha", [
    ("another-release/1", None),
    (None, "0" * 64),
])
def test_production_refuses_a_record_that_binds_another_release_before_the_key_file(
        tmp_path, monkeypatch, execution_id, execution_sha):
    candidate, approvals, bindings = synthetic_candidate()
    digest = release_sha256(candidate.release)
    path, sha = write_record(tmp_path, record_v2(
        execution_id=candidate.release.content()["release_id"] if execution_id is None else execution_id,
        execution_sha=digest if execution_sha is None else execution_sha))
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {RECORD_DEPLOYMENT: sha})
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        production_refused(tmp_path, path, candidates=(candidate,), approvals=approvals, bindings=bindings)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_HOSTED_RELEASE_MISMATCH"


def test_the_production_record_check_uses_the_existing_settings_check_not_a_new_parse(tmp_path, monkeypatch):
    candidate, approvals, bindings = synthetic_candidate()
    path, sha = write_record(tmp_path, record_v2(execution_id=candidate.release.content()["release_id"],
                                                 execution_sha=release_sha256(candidate.release)))
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {RECORD_DEPLOYMENT: sha})
    calls = []
    original = hosted_deployment.check_hosted_deployment

    def recording(settings, **kwargs):
        calls.append(settings)
        return original(settings, **kwargs)

    monkeypatch.setattr(hosted_deployment, "check_hosted_deployment", recording)
    with pytest.raises(ExecutionBootstrapRefused, match="KEY_FILE_UNREADABLE"):
        production_refused(tmp_path, path, candidates=(candidate,), approvals=approvals, bindings=bindings)
    assert len(calls) == 1
    assert calls[0].env == "production"


def test_production_refuses_a_record_outside_its_validity_window_before_the_key_file(tmp_path, monkeypatch):
    candidate, approvals, bindings = synthetic_candidate()
    value = record_v2(execution_id=candidate.release.content()["release_id"],
                      execution_sha=release_sha256(candidate.release))
    value["valid_until"] = "2026-02-01T00:00:00Z"
    path, sha = write_record(tmp_path, value)
    monkeypatch.setattr(hosted_deployment, "APPROVED_HOSTED_DEPLOYMENTS", {RECORD_DEPLOYMENT: sha})
    with pytest.raises(ExecutionBootstrapRefused) as refused:
        production_refused(tmp_path, path, candidates=(candidate,), approvals=approvals, bindings=bindings)
    assert refused.value.code == "EXECUTION_BOOTSTRAP_HOSTED_RECORD_REFUSED"
