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


# Source2: by-address fallback, address-only claims, retained-claim resume, socket target -----------------------

RECORD = {"id": "resolved-wallet", "address": ADDR, "chain_type": "ethereum", "owner_id": "quorum-x", "policy_ids": []}


def test_null_linked_id_resolves_only_through_exact_address_record():
    user = _user(_wallet(id=None))
    matched = match_claim(user, DID, ADDR, None, wallet_record=RECORD)
    assert matched is not None and matched.wallet_id == "resolved-wallet"


@pytest.mark.parametrize("record,claimed", [
    ({**RECORD, "address": "0x" + "cd" * 20}, None),       # response address differs
    ({**RECORD, "chain_type": "solana"}, None),             # wrong chain
    ({**RECORD, "id": None}, None),                         # no valid ID
    ({**RECORD, "id": "../x"}, None),
    (RECORD, "browser-said-other"),                         # claimed ID inconsistent with resolved ID
    (None, None),                                           # lookup unavailable
    ([RECORD], None),                                       # malformed shape
])
def test_by_address_record_mismatch_stays_unknown(record, claimed):
    assert match_claim(_user(_wallet(id=None)), DID, ADDR, claimed, wallet_record=record) is None


def test_by_address_record_never_proves_a_wallet_absent_from_the_user():
    """The address record may name the DID as owner/entity; without the user's own linked wallet it is no match."""
    assert match_claim(_user(), DID, ADDR, None, wallet_record={**RECORD, "owner_id": DID, "entity": DID}) is None


def test_linked_id_must_agree_with_any_address_record():
    assert match_claim(_user(_wallet()), DID, ADDR, None, wallet_record={**RECORD, "id": "other"}) is None
    assert match_claim(_user(_wallet()), DID, ADDR, None) is not None  # ID from the user's own link


def test_answer_uses_address_lookup_only_after_the_user_link_matches():
    calls: list[tuple[str, str]] = []

    def fetch_user(did: str) -> object:
        calls.append(("user", did))
        return _user(_wallet(id=None))

    def fetch_wallet(address: str) -> object:
        calls.append(("wallet", address))
        return RECORD

    msg = {"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": None}
    reply = lookup_server.answer(msg, fetch_user, fetch_wallet)
    assert reply == {"status": "matched", "wallet_id": "resolved-wallet", "address": ADDR, "chain_type": "ethereum"}
    assert calls == [("user", DID), ("wallet", ADDR)]
    calls.clear()
    stranger = lookup_server.answer(msg, lambda did: _user(), fetch_wallet)
    assert stranger["status"] == "unknown" and calls == []  # no address lookup for a wallet the user does not link


class _FakeResponse:
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, size: int) -> bytes:
        return self._body[:size]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_reader_address_lookup_is_one_fixed_post():
    import json as _json

    reader = lookup_server.PrivyUserReader("app-id-fake", "fake-secret-value")
    sent: list[object] = []

    def opener(request: object, timeout: float) -> _FakeResponse:
        sent.append((request, timeout))
        return _FakeResponse(_json.dumps(RECORD).encode())

    reader._opener = SimpleNamespace(open=opener)
    assert reader.wallet_by_address(ADDR) == RECORD
    (request, timeout), = sent
    assert (request.full_url, request.get_method()) == ("https://api.privy.io/v1/wallets/address", "POST")
    assert _json.loads(request.data) == {"address": ADDR} and timeout == lookup_server.DEADLINE_SECONDS
    assert reader.wallet_by_address("0x12") is None and len(sent) == 1


def test_existing_socket_target_is_refused_not_unlinked(short_private_dir):
    target = short_private_dir / "x.sock"
    target.symlink_to(short_private_dir / "elsewhere")
    with pytest.raises(SystemExit):
        lookup_server.prepare_socket_path(str(target))
    assert target.is_symlink()


def test_client_sends_address_only_claim_and_takes_the_resolved_id():
    provider = OwnerBoundLookupProvider("/tmp/unused.sock", uuid.uuid4(), DID)
    seen: list[dict[str, object]] = []

    def ask(request: dict[str, object]) -> dict[str, object]:
        seen.append(request)
        return {"status": "matched", "wallet_id": "resolved-wallet", "address": ADDR, "chain_type": "ethereum"}

    provider._ask = ask  # type: ignore[method-assign]
    evidence = provider.lookup_claim(ADDR, None)
    assert evidence is not None and evidence.wallet_id == "resolved-wallet"
    assert seen == [{"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": None}]
    assert provider.lookup_claim(ADDR, "wallet-x") is None  # a claimed ID the lookup did not confirm


@pytest.fixture
def short_private_dir():
    """Socket paths are limited to 100 characters, so the pytest base path is too long for this control."""
    import shutil
    import tempfile

    path = Path(tempfile.mkdtemp(prefix="l3w"))
    path.chmod(0o700)
    if len(str(path)) > 80:
        pytest.fail("no short private temp directory available")
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_existing_socket_like_target_is_not_unlinked(short_private_dir, monkeypatch):
    """Without a proved own claim a live or stale socket target stays; startup refuses instead."""
    target = short_private_dir / "x.sock"
    target.write_text("stand-in for a live socket")
    monkeypatch.setattr(lookup_server.stat, "S_ISSOCK", lambda mode: True)
    with pytest.raises(SystemExit):
        lookup_server.prepare_socket_path(str(target))
    assert target.exists()


# Source2: address-only completion and server-retained claim resume ----------------------------------------------

from edge_os_api.wallet_setup import service  # noqa: E402


class _ClaimLookup:
    """Owner-bound lookup double: answers only the exact address, recording each question."""

    def __init__(self, resolved_id: str | None) -> None:
        self.resolved_id = resolved_id
        self.calls: list[tuple[str | None, str | None]] = []

    def create_wallet(self, request: object) -> None:
        raise AssertionError("completion must never create")

    def lookup_wallet(self, wallet_id: str) -> None:
        raise AssertionError("an address claim uses lookup_claim")

    def lookup_claim(self, address: str | None, wallet_id: str | None):
        from edge_os_api.wallet_setup.provider import WalletEvidence

        self.calls.append((address, wallet_id))
        if self.resolved_id is None or address != ADDR or wallet_id not in (None, self.resolved_id):
            return None
        return WalletEvidence(wallet_id=self.resolved_id, owner_id=self.owner_id, chain_type="ethereum", address=ADDR)


def _service_row(monkeypatch, **overrides: object) -> tuple[SimpleNamespace, _Session]:
    row = _row(state=SetupState.PENDING.value, creation_dispatched=True, **overrides)
    session = _Session()
    monkeypatch.setattr(service, "load_setup", lambda *a, **k: row)
    monkeypatch.setattr(service, "conflicting_binding", lambda *a, **k: None)
    return row, session


def test_address_only_claim_binds_the_independently_resolved_id(monkeypatch):
    row, session = _service_row(monkeypatch)
    lookup = _ClaimLookup("resolved-wallet")
    lookup.owner_id = row.owner_id
    record = service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                           provider=lookup, address=ADDR)
    assert record.state == SetupState.CONFIRMED and record.wallet_id == "resolved-wallet"
    assert lookup.calls == [(ADDR, None)]
    retained = [e.content for e in session.added if e.event_type == SetupEventType.RESULT_RETURNED.value]
    assert retained == [{"wallet_id": None, "owner_id": str(row.owner_id), "chain_type": "ethereum", "address": None,
                         "claimed_address": ADDR, "claimed_wallet_index": None, "claimed_chain_type": None,
                         "source": "BROWSER_COMPLETION", "trusted": False}]


def test_address_only_claim_without_match_stays_unknown(monkeypatch):
    row, session = _service_row(monkeypatch)
    lookup = _ClaimLookup(None)
    lookup.owner_id = row.owner_id
    record = service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                           provider=lookup, address=ADDR)
    assert record.state == SetupState.UNKNOWN and record.wallet_id is None


def test_resume_after_restart_uses_the_server_retained_claim(monkeypatch):
    row, session = _service_row(monkeypatch)
    retained = {"wallet_id": None, "owner_id": str(row.owner_id), "chain_type": "ethereum", "address": None,
                "claimed_address": ADDR, "source": "BROWSER_COMPLETION", "trusted": False}
    monkeypatch.setattr(browser_intent, "load_setup", lambda *a, **k: row)
    monkeypatch.setattr(browser_intent, "latest_event", lambda *a, **k: retained)
    lookup = _ClaimLookup("resolved-wallet")
    lookup.owner_id = row.owner_id
    record = browser_intent.resume_retained_claim(session, Principal(row.owner_id, DID), agent_id="agent-1",
                                                  provider=lookup)
    assert record.state == SetupState.CONFIRMED and lookup.calls == [(ADDR, None)]


def test_resume_without_a_retained_claim_never_creates(monkeypatch):
    row, session = _service_row(monkeypatch)
    monkeypatch.setattr(browser_intent, "load_setup", lambda *a, **k: row)
    monkeypatch.setattr(browser_intent, "latest_event", lambda *a, **k: None)
    from edge_os_api.wallet_setup import recovery

    monkeypatch.setattr(recovery, "latest_event", lambda *a, **k: None)  # existing reconcile path, no retained ID
    lookup = _ClaimLookup("resolved-wallet")
    lookup.owner_id = row.owner_id
    record = browser_intent.resume_retained_claim(session, Principal(row.owner_id, DID), agent_id="agent-1",
                                                  provider=lookup)
    assert record.state == SetupState.UNKNOWN and record.reason == "RECONCILE_NO_EXACT_ID" and lookup.calls == []


def test_retained_claim_keeps_the_returned_wallet_index(monkeypatch):
    row, session = _service_row(monkeypatch)
    lookup = _ClaimLookup(None)
    lookup.owner_id = row.owner_id
    service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                  provider=lookup, address=ADDR, wallet_index=2)
    retained = [e.content for e in session.added if e.event_type == SetupEventType.RESULT_RETURNED.value]
    assert retained[0]["claimed_wallet_index"] == 2


# Live private-socket controls (heavy IPC slot only; never in the pure node list) ---------------------------------


@pytest.fixture
def served_socket(short_private_dir):
    """The real `serve` loop in a thread with authored records; no credential, no network."""
    import threading

    path = short_private_dir / "lookup.sock"
    users = {DID: _user(_wallet())}
    thread = threading.Thread(target=lookup_server.serve, args=(str(path), users.get, lambda a: None), daemon=True)
    thread.start()
    for _ in range(100):
        if path.exists():
            break
        threading.Event().wait(0.02)
    assert path.exists(), "lookup socket did not start"
    yield path


def _raw_exchange(path, payload: bytes, *, timeout: float = 2.0) -> bytes:
    import socket as _socket

    with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(path))
        sock.sendall(payload)
        chunks = []
        while True:
            try:
                chunk = sock.recv(4096)
            except TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def test_ipc_socket_is_private_and_answers_the_owner_bound_client(served_socket):
    import os
    import stat as _stat

    assert _stat.S_IMODE(os.stat(served_socket).st_mode) == 0o600  # same-user peer accepted (LOCAL_PEERCRED/SO_PEERCRED)
    provider = OwnerBoundLookupProvider(str(served_socket), uuid.uuid4(), DID, timeout=2.0).with_claim(ADDR)
    evidence = provider.lookup_wallet(WID)
    assert evidence is not None and (evidence.wallet_id, evidence.address) == (WID, ADDR)


@pytest.mark.parametrize("payload", [
    b"\x00\x00\x00\x05[1,2]",                      # not an object
    b"\x00\x00\x10\x01" + b"x" * 16,               # declared size above 4096
    b"\x00\x00\x00\x00",                           # empty frame
    b"\x00\x00\x00\x08not-json",                   # not JSON
])
def test_ipc_malformed_or_oversized_frames_get_a_code_only(served_socket, payload):
    reply = decode_body(_raw_exchange(served_socket, payload)[4:])
    assert reply == {"status": "unknown", "reason": "MALFORMED_FRAME"}


def test_ipc_unsupported_operation_is_refused(served_socket):
    frame = encode_frame({"op": "create_wallet", "did": DID, "address": ADDR, "wallet_id": WID})
    assert decode_body(_raw_exchange(served_socket, frame)[4:])["reason"] == "UNSUPPORTED_REQUEST"


def test_ipc_silent_peer_is_dropped_and_the_server_keeps_serving(served_socket, monkeypatch):
    monkeypatch.setattr(lookup_server, "CONNECTION_TIMEOUT", 0.5)
    _raw_exchange(served_socket, b"\x00\x00", timeout=3.0)  # half a header, then silence until the server drops it
    provider = OwnerBoundLookupProvider(str(served_socket), uuid.uuid4(), DID, timeout=2.0).with_claim(ADDR)
    assert provider.lookup_wallet(WID) is not None


def test_ipc_absent_socket_or_timeout_is_unavailable(short_private_dir):
    absent = OwnerBoundLookupProvider(str(short_private_dir / "absent.sock"), uuid.uuid4(), DID, timeout=0.5)
    with pytest.raises(WalletProviderUnavailable):
        absent.with_claim(ADDR).lookup_wallet(WID)


# Repair 1 regressions (RED first) ---------------------------------------------------------------------------------

def _confirmed_row(monkeypatch, bound_address: str = ADDR):
    row = _row(state=SetupState.CONFIRMED.value, creation_dispatched=True, wallet_id="resolved-wallet-1")
    session = _Session()
    monkeypatch.setattr(service, "load_setup", lambda *a, **k: row)
    bound = {"wallet_id": "resolved-wallet-1", "evidence": {"owner_id": str(row.owner_id), "chain_type": "ethereum",
                                                            "address": bound_address}}
    monkeypatch.setattr(service, "latest_event",
                        lambda s, r, kind: bound if kind == SetupEventType.WALLET_BOUND else None)
    return row, session


def test_address_only_retry_on_the_bound_address_records_no_conflict(monkeypatch):
    """A F1 / B MINOR-1: the lost-completion retry of the same address-only claim is idempotent."""
    row, session = _confirmed_row(monkeypatch)
    same_address_other_case = "0x" + ADDR[2:].upper()
    record = service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                           provider=_ClaimLookup("resolved-wallet-1"), address=same_address_other_case)
    assert record.wallet_id == "resolved-wallet-1"
    assert [type(a).__name__ for a in session.added] == []  # no denial row, no event


def test_address_only_claim_for_another_address_on_a_bound_setup_records_a_conflict(monkeypatch):
    row, session = _confirmed_row(monkeypatch)
    service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                  provider=_ClaimLookup(None), address="0x" + "cd" * 20)
    assert [d.code for d in session.added] == ["CONFLICTING_RESULT"]


def test_retained_claim_keeps_the_browser_chain_type(monkeypatch):
    """A F2: the server keeps the chain type the browser reported instead of writing a fixed value."""
    row, session = _service_row(monkeypatch)
    lookup = _ClaimLookup(None)
    lookup.owner_id = row.owner_id
    service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                  provider=lookup, address=ADDR, chain_type="ethereum")
    retained = [e.content for e in session.added if e.event_type == SetupEventType.RESULT_RETURNED.value]
    assert retained[0]["claimed_chain_type"] == "ethereum"


def test_non_ethereum_browser_claim_is_refused_before_retention(monkeypatch):
    row, session = _service_row(monkeypatch)
    with pytest.raises(Exception) as error:
        service.complete_from_browser(session, Principal(row.owner_id, DID), agent_id="agent-1", wallet_id=None,
                                      provider=_ClaimLookup(None), address=ADDR, chain_type="solana")
    assert getattr(error.value, "status", None) == 422 or "422" in repr(error.value)
    assert session.added == []


def test_resume_keeps_the_retained_wallet_index_and_chain(monkeypatch):
    """B MINOR-3: resume re-sends the retained index and chain, so the newest retained claim does not lose them."""
    row, session = _service_row(monkeypatch)
    retained = {"wallet_id": None, "owner_id": str(row.owner_id), "chain_type": "ethereum", "address": None,
                "claimed_address": ADDR, "claimed_wallet_index": 2, "claimed_chain_type": "ethereum",
                "source": "BROWSER_COMPLETION", "trusted": False}
    monkeypatch.setattr(browser_intent, "load_setup", lambda *a, **k: row)
    monkeypatch.setattr(browser_intent, "latest_event", lambda *a, **k: retained)
    lookup = _ClaimLookup(None)
    lookup.owner_id = row.owner_id
    browser_intent.resume_retained_claim(session, Principal(row.owner_id, DID), agent_id="agent-1", provider=lookup)
    new = [e.content for e in session.added if e.event_type == SetupEventType.RESULT_RETURNED.value]
    assert (new[0]["claimed_wallet_index"], new[0]["claimed_chain_type"]) == (2, "ethereum")


def test_reader_maps_a_malformed_http_response_to_none():
    """B MAJOR-2: http.client.HTTPException is not OSError or URLError; it must not escape the reader."""
    import http.client

    reader = lookup_server.PrivyUserReader("app-id-fake", "fake-secret-value")

    def opener(request: object, timeout: float) -> object:
        raise http.client.BadStatusLine("garbage")

    reader._opener = SimpleNamespace(open=opener)
    assert reader.wallet_by_address(ADDR) is None
    assert reader(DID) is None


class _FakeConn:
    """Minimal stand-in for an accepted socket: records what the server sends."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def settimeout(self, value: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)


def test_handle_answers_a_code_when_a_lookup_raises(monkeypatch):
    """B MAJOR-2: one failing lookup answers UNKNOWN and returns, so the serve loop keeps running."""
    monkeypatch.setattr(lookup_server, "same_user_peer", lambda conn: True)
    message = {"op": "lookup_embedded_wallet", "did": DID, "address": ADDR, "wallet_id": None}
    monkeypatch.setattr(lookup_server, "read_frame", lambda conn: message)

    def broken(did: str) -> object:
        raise RuntimeError("provider exploded with secret-marker-9b")

    conn = _FakeConn()
    lookup_server.handle(conn, broken)
    assert [decode_body(frame[4:]) for frame in conn.sent] == [{"status": "unknown", "reason": "LOOKUP_FAILED"}]


def test_handle_sends_nothing_to_a_foreign_peer(monkeypatch):
    """A F6 / B MINOR-6: a peer that is not this user gets no answer and no lookup."""
    monkeypatch.setattr(lookup_server, "same_user_peer", lambda conn: False)
    calls: list[str] = []
    conn = _FakeConn()
    lookup_server.handle(conn, lambda did: calls.append(did))
    assert conn.sent == [] and calls == []


def test_same_user_peer_refuses_a_foreign_uid_or_unreadable_credentials():
    import os
    import struct

    class Peer:
        def __init__(self, raw: bytes | None) -> None:
            self.raw = raw

        def getsockopt(self, *args: object) -> bytes:
            if self.raw is None:
                raise OSError("no credentials")
            return self.raw

    foreign = os.getuid() + 1
    if hasattr(lookup_server.socket, "SO_PEERCRED"):
        raw = struct.pack("3i", 1, foreign, 0)
    else:
        raw = struct.pack("Ii", 0, foreign) + b"\0" * 68
    assert lookup_server.same_user_peer(Peer(raw)) is False
    assert lookup_server.same_user_peer(Peer(None)) is False


def test_client_timeout_budget_covers_both_fixed_server_reads():
    """B MINOR-5: the client waits longer than the server's two bounded provider reads."""
    from edge_os_api.wallet_setup import lookup_client

    assert lookup_client.DEADLINE_SECONDS > 2 * lookup_server.DEADLINE_SECONDS


def test_ipc_client_times_out_on_a_silent_server(short_private_dir):
    """A F6 / B MINOR-6: a server that accepts but never answers ends as unavailable within the client timeout."""
    import socket as _socket
    import time

    path = short_private_dir / "silent.sock"
    server = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    try:
        server.bind(str(path))
        server.listen(1)
        provider = OwnerBoundLookupProvider(str(path), uuid.uuid4(), DID, timeout=0.5).with_claim(ADDR)
        started = time.monotonic()
        with pytest.raises(WalletProviderUnavailable):
            provider.lookup_wallet(WID)
        assert time.monotonic() - started < 5
    finally:
        server.close()
