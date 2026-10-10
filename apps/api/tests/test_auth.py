"""P01 failure matrix rows A1-A13, A20, A24-A29 through the real verifier and a real database."""

from __future__ import annotations

import logging
import time

import jwt
import pytest

from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.core.authentication import Verifier
from tokens import DROP, OWNER_A, TestSigner

URL = "/v1/me"


def get(client, token: str | None = None, header: str | None = None):
    headers = {}
    if header is not None:
        headers["Authorization"] = header
    elif token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.get(URL, headers=headers)


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == code
    record_contract.validate_http_error(body)  # envelope shape from the frozen contract


def test_a1_missing_header(client):
    response = get(client)
    assert_error(response, 401, "auth_required")
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Basic abc", "Bearer ", "Bearer", "Bearer a b"])
def test_a2_wrong_scheme_or_empty(client, header):
    assert_error(get(client, header=header), 401, "auth_invalid")


@pytest.mark.parametrize("token", ["notatoken", "a.b", "a.b.c", "....", "%%%.%%%.%%%"])
def test_a3_malformed(client, token):
    assert_error(get(client, token), 401, "auth_invalid")


def test_a4_oversized(client, signer):
    assert_error(get(client, signer.token(sid="x" * 5000)), 401, "auth_invalid")


def test_a5_other_key(client):
    assert_error(get(client, TestSigner().token(OWNER_A)), 401, "auth_invalid")


@pytest.mark.parametrize("alg", ["HS256", "none"])
def test_a6_disallowed_alg(client, signer, alg):
    claims = signer.claims()
    token = jwt.encode(claims, "secret" if alg == "HS256" else None, algorithm=alg)
    assert_error(get(client, token), 401, "auth_invalid")


def test_a6_rs256(client, signer):
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(65537, 2048)
    assert_error(get(client, jwt.encode(signer.claims(), key, algorithm="RS256")), 401, "auth_invalid")


def test_a7_expired(client, signer):
    assert_error(get(client, signer.token(exp=int(time.time()) - 60, iat=int(time.time()) - 3700)), 401, "auth_expired")


def test_a7_within_leeway_accepted(client, signer):
    assert get(client, signer.token(exp=int(time.time()) - 5)).status_code == 200


def test_a8_wrong_audience(client, signer):
    assert_error(get(client, signer.token(aud="another-app")), 401, "auth_invalid")


def test_a9_wrong_issuer(client, signer):
    assert_error(get(client, signer.token(iss="evil.example")), 401, "auth_invalid")


@pytest.mark.parametrize("claim", ["sub", "exp", "iat", "iss", "aud", "sid"])
def test_a10_missing_required_claim(client, signer, claim):
    assert_error(get(client, signer.token(**{claim: DROP})), 401, "auth_invalid")


@pytest.mark.parametrize("overrides", [{"exp": None}, {"exp": [1]}, {"iat": None}, {"iat": [1]}, {"iat": True},
                                       {"iat": str(int(time.time()))}, {"exp": {"a": 1}}])
def test_a10_wrong_types(client, signer, overrides):
    response = get(client, signer.token(**overrides))
    assert response.status_code == 401
    assert response.json()["code"] in {"auth_invalid", "auth_expired"}


@pytest.mark.parametrize("sub", ["", 5, None, "did:other:x", "x" * 300, "did:privy:" + "y" * 300])
def test_a11_bad_subject(client, signer, sub):
    token = jwt.encode({**signer.claims(), "sub": sub}, signer.private_key, algorithm="ES256")
    assert_error(get(client, token), 401, "auth_invalid")


def test_a12_expired_with_bad_signature(client):
    token = TestSigner().token(exp=int(time.time()) - 600)
    assert_error(get(client, token), 401, "auth_invalid")


def test_a13_verifier_missing(settings):
    from fastapi.testclient import TestClient
    from edge_os_api.main import create_app
    with TestClient(create_app(settings)) as isolated:
        isolated.app.state.verifier = None
        assert_error(isolated.get(URL, headers={"Authorization": "Bearer x.y.z"}), 503, "auth_unavailable")


def test_a13_invalid_key_error(signer, monkeypatch):
    verifier = Verifier("edge-os-test-app", [signer.private_key.public_key()])

    def explode(*_a, **_k):
        raise jwt.InvalidKeyError("bad")
    monkeypatch.setattr(jwt, "decode", explode)
    with pytest.raises(Exception) as caught:
        verifier.verify("a.b.c")
    assert caught.value.code == "auth_unavailable"


def test_a24_future_iat(client, signer):
    assert_error(get(client, signer.token(iat=int(time.time()) + 600)), 401, "auth_invalid")


def test_a25_audience_list(client, signer):
    assert_error(get(client, signer.token(aud=["edge-os-test-app"])), 401, "auth_invalid")


@pytest.mark.parametrize("value", ["data", "", [], {}, None])
@pytest.mark.parametrize("claim", ["linked_accounts", "custom_metadata"])
def test_a26_a28_identity_claims_rejected_by_presence(client, signer, claim, value):
    assert_error(get(client, signer.token(**{claim: value})), 401, "auth_invalid")


def test_a28_both_claims(client, signer):
    assert_error(get(client, signer.token(linked_accounts=[], custom_metadata={})), 401, "auth_invalid")


@pytest.mark.parametrize("sid", ["", "s" * 256, 12, None])
def test_a27_bad_sid(client, signer, sid):
    assert_error(get(client, signer.token(sid=sid)), 401, "auth_invalid")


def test_a27_missing_sid_is_a10(client, signer):
    assert_error(get(client, signer.token(sid=DROP)), 401, "auth_invalid")


def test_a29_valid_access_shaped_control_creates_one_user(client, signer, pg):
    sub = "did:privy:control-" + str(time.time_ns())
    first = get(client, signer.token(sub))
    second = get(client, signer.token(sub))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert pg.psql(f"select count(*) from users where privy_did = '{sub}'") == "1"


def test_a21_login_adds_only_a_user_row(client, signer, pg):
    tables = {"records": 0, "strategy_revisions": 0, "idempotency_records": 0}
    before = {t: pg.psql(f"select count(*) from {t}") for t in tables}
    assert get(client, signer.token("did:privy:onlyuser-" + str(time.time_ns()))).status_code == 200
    assert {t: pg.psql(f"select count(*) from {t}") for t in tables} == before


def test_a20_previous_key_rotation(signer, settings, pg, env):
    import harness
    from fastapi.testclient import TestClient
    from edge_os_api.main import create_app
    from edge_os_api.core.settings import load_settings
    old = TestSigner()
    rotated_env = harness.api_env(database_url=pg.url, public_pem=signer.public_pem, previous_pem=old.public_pem,
                                  cors=["http://127.0.0.1:3999"])
    with TestClient(create_app(load_settings(rotated_env))) as rotated:
        assert get(rotated, old.token("did:privy:rot-" + str(time.time_ns()))).status_code == 200
        assert get(rotated, signer.token("did:privy:rot2-" + str(time.time_ns()))).status_code == 200
    with TestClient(create_app(settings)) as current:  # previous key removed
        assert_error(get(current, old.token()), 401, "auth_invalid")


def test_ec_key_type_enforced(signer, env):
    from edge_os_api.core.settings import ConfigError, load_settings
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, ec as ec_
    ed = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    p384 = ec_.generate_private_key(ec_.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    for pem in (ed, p384, "not a key"):
        with pytest.raises(ConfigError) as caught:
            load_settings({**env, "EDGE_OS_PRIVY_VERIFICATION_KEY": pem.replace("\n", "\\n")})
        assert "privy_verification_key" in str(caught.value)
        assert "BEGIN" not in str(caught.value)


def test_logs_never_contain_token(client, signer, caplog):
    caplog.set_level(logging.DEBUG)
    secrets = [signer.token(exp=int(time.time()) - 600), TestSigner().token(), signer.token(linked_accounts=[])]
    for token in secrets:
        get(client, token)
    joined = "\n".join(record.getMessage() for record in caplog.records)
    for token in secrets:
        assert token not in joined and token.split(".")[1] not in joined


def test_fuzz_never_5xx(client, signer):
    import base64, json, random
    random.seed(7)
    good = signer.token().split(".")
    attempts = ["", ".", "..", "a." * 50, good[0], ".".join(good[:2]), ".".join(good[:2]) + ".",
                good[0] + "." + good[1] + ".AAAA", "\x00\x01", "é.é.é"]
    for _ in range(40):
        mutated = list(".".join(good))
        mutated[random.randrange(len(mutated))] = random.choice("AZaz09-_.=")
        attempts.append("".join(mutated))
    for header in [base64.urlsafe_b64encode(json.dumps({"alg": a, "typ": t}).encode()).decode()
                   for a in ("ES256", "ES512", ["ES256"], None) for t in ("JWT", "x", None)]:
        attempts.append(f"{header}.{good[1]}.{good[2]}")
    for token in attempts:
        try:
            response = client.get(URL, headers={"Authorization": "Bearer " + token})
        except UnicodeEncodeError:
            continue
        assert response.status_code < 500, token


def test_no_auth_disabling_setting(env):
    from edge_os_api.core.settings import ConfigError, Settings, load_settings
    assert not any("secret" in f or "bypass" in f or "disable" in f for f in Settings.model_fields)
    for name in ("EDGE_OS_PRIVY_APP_SECRET", "EDGE_OS_AUTH_DISABLED", "EDGE_OS_DEV_AUTH_BYPASS"):
        with pytest.raises(ConfigError):
            load_settings({**env, name: "1"})


def test_rotation_counters_are_logged_for_operators(signer, pg, migrated, caplog):
    """P01: `auth.signature_failure` shows a spike, `auth.previous_key_accepted` shows when the old key is safe to remove."""
    import harness
    from fastapi.testclient import TestClient
    from edge_os_api.core import authentication as auth_module
    from edge_os_api.main import create_app
    from edge_os_api.core.settings import load_settings
    old = TestSigner()
    env = harness.api_env(database_url=pg.url, public_pem=signer.public_pem, previous_pem=old.public_pem,
                          cors=["http://127.0.0.1:3999"])
    auth_module._last_logged.clear()
    caplog.set_level(logging.INFO, logger="edge_os.auth")
    with TestClient(create_app(load_settings(env))) as rotated:
        assert get(rotated, old.token("did:privy:rotlog-" + str(time.time_ns()))).status_code == 200
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "auth.previous_key_accepted" in text and "auth.signature_failure" in text  # the current key failed first
        caplog.clear()
        before = auth_module.counters["auth.signature_failure"]
        assert get(rotated, TestSigner().token()).status_code == 401  # a key we never trusted
        assert auth_module.counters["auth.signature_failure"] > before
        assert "auth.signature_failure" not in "\n".join(r.getMessage() for r in caplog.records)  # rate limited: once a minute
        auth_module._last_logged.clear()
        assert get(rotated, TestSigner().token()).status_code == 401
        assert "auth.signature_failure" in "\n".join(r.getMessage() for r in caplog.records)
    token_text = old.token()
    assert token_text not in "\n".join(r.getMessage() for r in caplog.records)


def test_a_signed_subject_with_a_nul_character_is_a_401_not_a_503(client, signer):
    token = jwt.encode({**signer.claims(), "sub": "did:privy:\x00x"}, signer.private_key, algorithm="ES256")
    assert_error(get(client, token), 401, "auth_invalid")
