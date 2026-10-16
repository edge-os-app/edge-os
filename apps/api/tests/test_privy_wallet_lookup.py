"""Pure controls for the owner-bound Privy wallet lookup: no database, socket, network or credential.

The lookup executable and the API share `lookup_matching`; these controls prove an exact DID-scoped embedded
Ethereum match, refusal of `owner_id`/`entity` attribution, bounded frames, the single fixed operation,
secret isolation, settings selection and the once-only browser creation permission.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from edge_os_api.core.authentication import Principal
from edge_os_api.core.settings import ConfigError, load_settings
from edge_os_api.wallet_setup import browser_intent
from edge_os_api.wallet_setup.lookup_client import OwnerBoundLookupProvider
from edge_os_api.wallet_setup.lookup_framing import MAX_FRAME, FrameError, decode_body, encode_frame
from edge_os_api.wallet_setup.lookup_matching import match_claim
from edge_os_api.wallet_setup.provider import WalletProviderUnavailable
from edge_os_api.wallet_setup.types import CancellationIntent, SetupEventType, SetupState

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "privy_wallet_lookup"))
import lookup_server  # noqa: E402

DID = "did:privy:owner-a"
ADDR = "0x" + "ab" * 20
WID = "wallet-id-1"


def _wallet(**overrides: object) -> dict[str, object]:
    account = {"type": "wallet", "wallet_client_type": "privy", "chain_type": "ethereum", "address": ADDR,
               "id": WID, "wallet_index": 1}
    account.update(overrides)
    return account


def _user(*accounts: dict[str, object], did: str = DID) -> dict[str, object]:
    return {"id": did, "linked_accounts": list(accounts)}


# Matching -------------------------------------------------------------------------------------------------------


def test_exact_embedded_ethereum_wallet_matches():
    matched = match_claim(_user(_wallet()), DID, ADDR, WID)
    assert matched is not None and (matched.wallet_id, matched.address) == (WID, ADDR)


@pytest.mark.parametrize("user,did,address,wallet_id", [
    (_user(_wallet(), did="did:privy:other"), DID, ADDR, WID),            # DID mismatch
    (_user(_wallet()), DID, "0x" + "cd" * 20, WID),                        # address mismatch
    (_user(_wallet()), DID, ADDR, "other-wallet"),                         # ID mismatch
    (_user(_wallet(chain_type="solana")), DID, ADDR, WID),                # chain mismatch
    (_user(_wallet(wallet_client_type="metamask")), DID, ADDR, WID),       # external wallet, not embedded
    (_user(_wallet(id=None)), DID, ADDR, None),                            # null ID stays UNKNOWN
    (_user(_wallet(id=None)), DID, ADDR, WID),
    (_user(_wallet(), _wallet(id="dup")), DID, ADDR, None),                # ambiguous duplicate address
    (_user(), DID, ADDR, WID),                                             # no linked wallet
    ({"id": DID, "linked_accounts": None}, DID, ADDR, WID),
    (None, DID, ADDR, WID),
])
def test_mismatch_or_ambiguity_never_matches(user, did, address, wallet_id):
    assert match_claim(user, did, address, wallet_id) is None


def test_owner_id_and_entity_attribution_are_not_trusted():
    """A wallet record naming this DID as `owner_id` or `entity` but absent from the user's links is no match."""
    stray = {"id": WID, "address": ADDR, "chain_type": "ethereum", "owner_id": DID, "entity": DID}
    assert match_claim({"id": DID, "linked_accounts": [], "wallets": [stray]}, DID, ADDR, WID) is None
    assert match_claim(_user(_wallet(owner_id="did:privy:other", entity="x")), DID, ADDR, WID) is not None


# Frames ---------------------------------------------------------------------------------------------------------


def test_frames_are_bounded_objects():
    assert decode_body(encode_frame({"a": 1})[4:]) == {"a": 1}
    with pytest.raises(FrameError):
        encode_frame({"a": "x" * (MAX_FRAME + 1)})
    for body in (b"[1]", b"\xff\xfe", b"secret-marker-7f3a"):
        with pytest.raises(FrameError) as error:
            decode_body(body)
        assert "secret-marker" not in str(error.value)  # errors never repeat received bytes


# Lookup executable: one fixed operation ------------------------------------------------------------------------


def test_only_the_fixed_operation_is_answered():
    calls: list[str] = []

    def fetch(did: str) -> object:
        calls.append(did)
        return _user(_wallet())

    ok = lookup_server.answer({"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": WID}, fetch)
    assert ok == {"status": "matched", "wallet_id": WID, "address": ADDR, "chain_type": "ethereum"}
    refused = [
        {"op": "create_wallet", "did": DID, "address": ADDR, "wallet_id": WID},
        {"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": WID, "url": "https://x"},
        {"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": WID, "method": "POST"},
        {"op": "lookup_embedded_wallet", "did": "../v1/wallets", "address": ADDR, "wallet_id": WID},
        {"op": "lookup_embedded_wallet", "did": DID, "address": "0x12", "wallet_id": WID},
    ]
    for message in refused:
        assert lookup_server.answer(message, fetch)["status"] == "unknown"
    assert calls == [DID]


def test_unavailable_provider_record_is_unknown():
    reply = lookup_server.answer({"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": WID},
                                 lambda did: None)
    assert reply == {"status": "unknown", "reason": "LOOKUP_UNAVAILABLE"}


def test_credential_reader_hides_secret_and_refuses_redirects():
    reader = lookup_server.PrivyUserReader("app-id-fake", "fake-secret-value")
    assert "fake-secret-value" not in repr(reader) and "fake-secret-value" not in str(vars(reader).keys())
    assert lookup_server.API_BASE == "https://api.privy.io/v1/users/"
    assert lookup_server._NoRedirect().redirect_request() is None
    with pytest.raises(SystemExit):
        lookup_server.PrivyUserReader("app-id-fake", "")


def test_socket_path_must_be_absolute_and_private(tmp_path):
    with pytest.raises(SystemExit):
        lookup_server.prepare_socket_path("relative.sock")
    with pytest.raises(SystemExit):
        lookup_server.prepare_socket_path(str(tmp_path / ".." / "x.sock"))
    open_dir = tmp_path / "open"
    open_dir.mkdir(mode=0o755)
    open_dir.chmod(0o755)
    with pytest.raises(SystemExit):
        lookup_server.prepare_socket_path(str(open_dir / "x.sock"))
    private = tmp_path / "p"
    private.mkdir()
    private.chmod(0o700)
    (private / "x.sock").write_text("not a socket")
    with pytest.raises(SystemExit):
        lookup_server.prepare_socket_path(str(private / "x.sock"))


def test_api_package_never_reads_the_app_secret():
    src = REPO / "apps" / "api" / "src" / "edge_os_api"
    offenders = [p for p in src.rglob("*.py") if "PRIVY_APP_SECRET" in p.read_text() and p.name != "settings.py"]
    assert offenders == []
    settings_text = (src / "core" / "settings.py").read_text()
    assert "EDGE_OS_PRIVY_APP_SECRET" in settings_text  # only as a forbidden name


# API client --------------------------------------------------------------------------------------------------------


def _provider(reply: dict[str, object] | Exception, address: str | None = ADDR) -> OwnerBoundLookupProvider:
    provider = OwnerBoundLookupProvider("/tmp/unused.sock", uuid.uuid4(), DID).with_claim(address)

    def ask(request: dict[str, object]) -> dict[str, object]:
        assert set(request) == {"op", "did", "address", "wallet_id"} and request["did"] == DID
        if isinstance(reply, Exception):
            raise reply
        return reply

    provider._ask = ask  # type: ignore[method-assign]
    return provider


def test_client_binds_only_an_exact_matched_reply():
    good = {"status": "matched", "wallet_id": WID, "address": ADDR, "chain_type": "ethereum"}
    evidence = _provider(good).lookup_wallet(WID)
    assert evidence is not None and evidence.address == ADDR and evidence.chain_type == "ethereum"
    for reply in ({**good, "wallet_id": "other"}, {**good, "address": "0x" + "cd" * 20},
                  {**good, "chain_type": "solana"}, {"status": "unknown", "reason": "NO_EXACT_MATCH"}, {}):
        assert _provider(reply).lookup_wallet(WID) is None
    assert _provider(good, address=None).lookup_wallet(WID) is None  # no retained claim, no lookup


def test_client_failure_and_create_are_unavailable():
    """Socket-level failure mapping (absent, timeout, malformed reply) is in the separate guarded IPC slot."""
    with pytest.raises(WalletProviderUnavailable):
        _provider(WalletProviderUnavailable()).lookup_wallet(WID)
    real = OwnerBoundLookupProvider("/tmp/unused.sock", uuid.uuid4(), DID).with_claim(ADDR)
    with pytest.raises(WalletProviderUnavailable):
        real.create_wallet(None)  # type: ignore[arg-type]
    assert "fake" not in repr(real) and ADDR not in repr(real)


# Settings -------------------------------------------------------------------------------------------------------


def _env(**extra: str) -> dict[str, str]:
    pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return {"EDGE_OS_ENV": "local", "EDGE_OS_DATABASE_URL": "postgresql+psycopg://u@127.0.0.1/edge_os_test_x",
            "EDGE_OS_PRIVY_APP_ID": "fake-app", "EDGE_OS_PRIVY_VERIFICATION_KEY": pem,
            "EDGE_OS_CORS_ALLOWED_ORIGINS": "http://localhost:3000", **extra}


def test_lookup_socket_setting_is_validated():
    assert load_settings(_env()).wallet_lookup_socket is None
    assert load_settings(_env(EDGE_OS_WALLET_LOOKUP_SOCKET="/tmp/edge/l.sock")).wallet_lookup_socket == "/tmp/edge/l.sock"
    for bad in ("relative.sock", "/tmp/../l.sock"):
        with pytest.raises(ConfigError) as error:
            load_settings(_env(EDGE_OS_WALLET_LOOKUP_SOCKET=bad))
        assert bad not in str(error.value)
    with pytest.raises(ConfigError):
        load_settings(_env(EDGE_OS_WALLET_LOOKUP_SOCKET="/tmp/l.sock", EDGE_OS_WALLET_PROVIDER="fixture"))


def test_route_dependency_selects_owner_bound_lookup():
    from edge_os_api.wallet_setup.router import get_provider

    principal = Principal(user_id=uuid.uuid4(), privy_did=DID)
    fixture = object()
    configured = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(wallet_lookup_socket="/tmp/l.sock"), wallet_provider=fixture)))
    selected = get_provider(configured, principal)
    assert isinstance(selected, OwnerBoundLookupProvider)
    assert (selected.owner_id, selected.privy_did) == (principal.user_id, DID)
    default = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(wallet_lookup_socket=None), wallet_provider=fixture)))
    assert get_provider(default, principal) is fixture


# Once-only browser creation permission ---------------------------------------------------------------------------


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, item: object) -> None:
        self.added.append(item)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _row(**overrides: object) -> SimpleNamespace:
    now = dt.datetime.now(dt.timezone.utc)
    values = dict(setup_id=uuid.uuid4(), owner_id=uuid.uuid4(), agent_id="agent-1", network_id=10143,
                  strategy_id="s", strategy_revision_id=uuid.uuid4(), content_sha256="c", manifest_sha256="m",
                  state=SetupState.REQUESTED.value, cancellation_intent=CancellationIntent.NONE.value,
                  creation_dispatched=False, request_key="k", wallet_id=None, reason=None, created_at=now,
                  updated_at=now)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_first_begin_commits_intent_before_permission_and_later_begins_are_denied(monkeypatch):
    row = _row()
    monkeypatch.setattr(browser_intent, "load_setup", lambda *a, **k: row)
    session = _Session()
    principal = Principal(user_id=row.owner_id, privy_did=DID)
    first = browser_intent.begin_browser_creation(session, principal, agent_id="agent-1")
    assert first.create_permitted and session.commits == 1
    assert row.creation_dispatched and row.state == SetupState.PENDING.value
    assert [e.event_type for e in session.added] == [SetupEventType.DISPATCH_INTENT.value]
    for _ in range(3):  # duplicate begin, second tab, retry after a lost permission reply
        again = browser_intent.begin_browser_creation(session, principal, agent_id="agent-1")
        assert not again.create_permitted
    assert session.commits == 1 and len(session.added) == 1


@pytest.mark.parametrize("overrides", [
    {"cancellation_intent": CancellationIntent.REQUESTED_BEFORE_DISPATCH.value, "state": SetupState.FAILED.value},
    {"state": SetupState.CONFIRMED.value, "creation_dispatched": True, "wallet_id": WID},
    {"state": SetupState.UNKNOWN.value, "creation_dispatched": True},
])
def test_cancelled_confirmed_or_uncertain_setups_get_no_permission(monkeypatch, overrides):
    row = _row(**overrides)
    monkeypatch.setattr(browser_intent, "load_setup", lambda *a, **k: row)
    session = _Session()
    begun = browser_intent.begin_browser_creation(session, Principal(row.owner_id, DID), agent_id="agent-1")
    assert not begun.create_permitted and session.commits == 0 and session.added == []


def test_provider_info_reports_lookup_mode_without_fixture_counters():
    from edge_os_api.wallet_setup.adapter import provider_info

    info = provider_info(OwnerBoundLookupProvider("/tmp/l.sock", uuid.uuid4(), DID))
    assert info == {"provider": "privy_lookup", "create_calls": None, "lookup_calls": None}
