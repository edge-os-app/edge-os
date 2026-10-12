"""Red/green slice: durable, idempotent, fail-closed INACTIVE adoption.

Adoption binds the exact reviewed meaning and content identities, is idempotent on
an identical repeat, conflicts on a changed reuse, denies a stale or drifted
review, and is durable across a genuinely new process.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

import harness
from consent import _support as support

from edge_os_api.consent.records import ConsentAdoptionRow, ConsentDenialRow
from edge_os_api.consent.service import ConsentDenied, ConsentNotFound
from edge_os_api.consent.types import AdoptionRequest

HERE = Path(__file__).resolve().parent


def _review(consent_engine, consent_service, **terms_kwargs) -> object:
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)
    return consent_service.review(support.OWNER_A, support.review_request(revision, reviewed_terms=support.terms(**terms_kwargs)))


def test_adopt_returns_clearly_inactive_consent_with_exact_identities(consent_engine, consent_service) -> None:
    view = _review(consent_engine, consent_service)
    consent = consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                                    expected_review_hash=view.review_hash))

    assert consent.status == "INACTIVE"
    assert str(consent.review_id) == str(view.review_id)
    assert consent.review_hash == view.review_hash
    content = consent.content
    assert content["status"] == "INACTIVE"
    assert content["authority"] == "INACTIVE"
    assert content["inactive"] is True
    assert content["strategy"]["revision_id"] == str(view.strategy_revision_id)
    assert content["strategy"]["content_sha256"] == view.content_sha256
    assert content["wallet_id"] == support.WALLET_A
    assert content["network_id"] == support.NETWORK
    assert content["terms_version"] == view.terms_version
    assert content["terms_hash"] == view.terms_hash
    assert content["route"]["qualification"] == "UNQUALIFIED"
    assert content["evidence_status"] == "UNRESOLVED"
    assert content["status"] == "INACTIVE"


def test_repeated_adoption_is_idempotent(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)
    request = AdoptionRequest(review_id=str(view.review_id), expected_review_hash=view.review_hash)

    first = consent_service.adopt(support.OWNER_A, request)
    second = consent_service.adopt(support.OWNER_A, request)

    assert first.adoption_id == second.adoption_id
    assert first.consent_hash == second.consent_hash
    rows = session.execute(select(ConsentAdoptionRow)).scalars().all()
    assert len(rows) == 1


def test_stale_review_hash_is_denied_and_saves_no_consent(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)

    with pytest.raises(ConsentDenied) as error:
        consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash="sha256:" + "0" * 64))
    assert error.value.code == "stale_review"
    assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []
    assert "STALE_REVIEW" in set(session.execute(select(ConsentDenialRow.code)).scalars())


def test_expired_terms_are_denied(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service, expiry="2020-01-01T00:00:00Z")

    with pytest.raises(ConsentDenied) as error:
        consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash=view.review_hash))
    assert error.value.code == "expired_terms"
    assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []


def test_wallet_drift_after_review_denies_adoption(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)
    with consent_engine.begin() as connection:
        connection.execute(text("UPDATE public.wallet_setups SET state = 'UNKNOWN', wallet_id = NULL"))

    with pytest.raises(ConsentDenied) as error:
        consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash=view.review_hash))
    assert error.value.code == "wallet_drifted"
    assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []


def test_revision_drift_after_review_denies_adoption(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)
    # The saved review no longer matches the current revision identity it was built from.
    with consent_engine.begin() as connection:
        connection.execute(text("UPDATE consent_local.consent_reviews SET content_sha256 = :hash"),
                           {"hash": "f" * 64})

    with pytest.raises(ConsentDenied) as error:
        consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash=view.review_hash))
    assert error.value.code == "revision_drifted"
    assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []


def test_drifted_stored_terms_are_denied(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)
    # The stored reviewed terms change without changing the recorded terms_hash.
    with consent_engine.begin() as connection:
        connection.execute(text(
            "UPDATE consent_local.consent_reviews "
            "SET content = jsonb_set(content, '{terms,evidence,status}', '\"SUPPORTED\"')"))

    with pytest.raises(ConsentDenied) as error:
        consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash=view.review_hash))
    assert error.value.code == "corrupt_review"
    assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []
    assert "CORRUPT_REVIEW" in set(session.execute(select(ConsentDenialRow.code)).scalars())


def test_a_review_missing_its_meaning_is_denied_not_crashed(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)
    with consent_engine.begin() as connection:
        connection.execute(text("UPDATE consent_local.consent_reviews SET content = content - 'meaning'"))

    with pytest.raises(ConsentDenied) as error:
        consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash=view.review_hash))
    assert error.value.code == "corrupt_review"
    assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []


def test_another_owner_cannot_adopt_or_read_the_consent(consent_engine, consent_service) -> None:
    view = _review(consent_engine, consent_service)
    with pytest.raises(ConsentNotFound):
        consent_service.adopt(support.OWNER_B, AdoptionRequest(review_id=str(view.review_id),
                                                               expected_review_hash=view.review_hash))
    consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                           expected_review_hash=view.review_hash))
    with pytest.raises(ConsentNotFound):
        consent_service.read_consent(support.OWNER_B, str(view.review_id))


def test_concurrent_adoption_yields_one_consent(consent_engine, consent_service, session) -> None:
    view = _review(consent_engine, consent_service)
    request = AdoptionRequest(review_id=str(view.review_id), expected_review_hash=view.review_hash)
    barrier, results = threading.Barrier(2), [None, None]

    def adopt(index: int) -> None:
        barrier.wait()
        results[index] = consent_service.adopt(support.OWNER_A, request)

    threads = [threading.Thread(target=adopt, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results[0].consent_hash == results[1].consent_hash
    rows = session.execute(select(ConsentAdoptionRow)).scalars().all()
    assert len(rows) == 1
    assert rows[0].consent_hash == results[0].consent_hash


def test_wallet_becoming_unknown_before_the_adoption_lock_denies(consent_engine, consent_service) -> None:
    """Deterministic regression: the wallet is changed after the first read, before the save."""
    revision = support.seed_revision(consent_engine, support.OWNER_A)
    support.seed_wallet_setup(consent_engine, support.OWNER_A, revision)
    view = consent_service.review(support.OWNER_A, support.review_request(revision))
    request = AdoptionRequest(review_id=str(view.review_id), expected_review_hash=view.review_hash)

    at_lock, release = threading.Event(), threading.Event()
    result: dict = {}

    def pause_at_lock(connection, cursor, statement, parameters, context, executemany):
        if "pg_advisory_xact_lock" in statement and threading.current_thread().name == "race-adopter":
            at_lock.set()
            if not release.wait(15):
                raise RuntimeError("lock pause timed out")

    def adopter() -> None:
        try:
            result["view"] = consent_service.adopt(support.OWNER_A, request)
        except Exception as error:  # noqa: BLE001 - the denial is the expected outcome
            result["error"] = error

    event.listen(consent_engine, "before_cursor_execute", pause_at_lock)
    try:
        thread = threading.Thread(target=adopter, name="race-adopter")
        thread.start()
        assert at_lock.wait(15), "adoption never reached its advisory lock"
        with consent_engine.begin() as connection:
            connection.execute(text(
                "UPDATE public.wallet_setups SET state = 'UNKNOWN', wallet_id = NULL WHERE owner_id = CAST(:owner AS uuid)"),
                {"owner": support.OWNER_A})
        release.set()
        thread.join(15)
        assert not thread.is_alive(), "adopter did not finish"
    finally:
        release.set()
        event.remove(consent_engine, "before_cursor_execute", pause_at_lock)

    assert isinstance(result.get("error"), ConsentDenied)
    assert result["error"].code == "wallet_drifted"
    with Session(consent_engine) as session:
        assert session.execute(select(ConsentAdoptionRow)).scalars().all() == []
        assert "WALLET_DRIFTED" in set(session.execute(select(ConsentDenialRow.code)).scalars())


def test_second_process_adoption_is_idempotent(consent_engine, consent_service, pg) -> None:
    view = _review(consent_engine, consent_service)
    first = consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                                   expected_review_hash=view.review_hash))

    result = subprocess.run(
        [harness.api_python(), str(HERE / "adopt_driver.py"), pg.url, str(support.OWNER_A), str(view.review_id),
         view.review_hash],
        capture_output=True, text=True, timeout=60, check=True)
    second = json.loads(result.stdout)

    assert second["consent_hash"] == first.consent_hash
    assert second["status"] == "INACTIVE"
    assert second["adoption_id"] == str(first.adoption_id)
    with Session(consent_engine) as session:
        assert len(session.execute(select(ConsentAdoptionRow)).scalars().all()) == 1


def test_true_process_reopen_reads_the_durable_consent(consent_engine, consent_service, pg) -> None:
    view = _review(consent_engine, consent_service)
    consent = consent_service.adopt(support.OWNER_A, AdoptionRequest(review_id=str(view.review_id),
                                                                    expected_review_hash=view.review_hash))

    result = subprocess.run(
        [harness.api_python(), str(HERE / "reopen_driver.py"), pg.url, str(support.OWNER_A), str(view.review_id)],
        capture_output=True, text=True, timeout=60, check=True)
    reopened = json.loads(result.stdout)

    assert reopened["consent_hash"] == consent.consent_hash
    assert reopened["review_hash"] == view.review_hash
    assert reopened["status"] == "INACTIVE"
