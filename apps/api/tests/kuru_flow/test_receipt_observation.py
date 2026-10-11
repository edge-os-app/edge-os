from __future__ import annotations

from edge_os_api.admission.types import AssetAmount
from edge_os_api.kuru_flow.receipt_observation import (
    OBS_EFFECTS_UNPROVEN,
    OBS_IDENTITY_MISMATCH,
    OBS_MISSING_RECEIPT,
    OBS_NETWORK_MISMATCH,
    OBS_TX_MISMATCH,
    OBS_WALLET_MISMATCH,
    ObservationInput,
    normalize_observation,
)
from edge_os_api.kuru_flow.types import ObservationState

HASH = "sha256:" + "a" * 64
WALLET = "0x00000000000000000000000000000000000000A1"
TX = "0x" + "b" * 64


def _normalize(observation: ObservationInput, **overrides):
    kwargs = {
        "expected_candidate_hash": HASH,
        "expected_chain_id": 143,
        "expected_wallet": WALLET,
    }
    kwargs.update(overrides)
    return normalize_observation(observation=observation, **kwargs)


def test_success_with_reconciled_deltas_proves_effects():
    observation = ObservationInput(
        status="SUCCESS",
        receipt_present=True,
        tx_hash=TX,
        chain_id=143,
        wallet_id=WALLET,
        candidate_hash=HASH,
        actual_input=AssetAmount(asset_id="monad:143/native", raw="1000000000000000000", decimals=18),
        actual_output=AssetAmount(asset_id="monad:143/usdc", raw="1450000", decimals=6),
        actual_gas=AssetAmount(asset_id="monad:143/native", raw="21000", decimals=18),
    )
    verdict = _normalize(observation)
    assert verdict.state is ObservationState.CONFIRMED
    assert verdict.effects_proven is True
    assert verdict.reasons == []


def test_success_without_deltas_leaves_effects_unproven():
    observation = ObservationInput(status="SUCCESS", receipt_present=True, tx_hash=TX, chain_id=143, wallet_id=WALLET)
    verdict = _normalize(observation)
    assert verdict.state is ObservationState.CONFIRMED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_EFFECTS_UNPROVEN]
    assert verdict.actual_input is None and verdict.actual_output is None


def test_success_with_known_deltas_but_unknown_gas_leaves_effects_unproven():
    observation = ObservationInput(
        status="SUCCESS",
        receipt_present=True,
        actual_input=AssetAmount(asset_id="monad:143/native", raw="1000000000000000000", decimals=18),
        actual_output=AssetAmount(asset_id="monad:143/usdc", raw="1450000", decimals=6),
    )
    verdict = _normalize(observation)
    assert verdict.state is ObservationState.CONFIRMED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_EFFECTS_UNPROVEN]


def test_success_without_receipt_is_rejected():
    observation = ObservationInput(status="SUCCESS", receipt_present=False)
    verdict = _normalize(observation)
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_MISSING_RECEIPT]


def test_reverted_retains_optional_gas():
    observation = ObservationInput(status="REVERTED", receipt_present=True, actual_gas=None)
    verdict = _normalize(observation)
    assert verdict.state is ObservationState.REVERTED
    assert verdict.actual_gas is None


def test_acknowledgement_lost_retains_no_effect():
    verdict = _normalize(ObservationInput(acknowledgement_lost=True))
    assert verdict.state is ObservationState.ACKNOWLEDGEMENT_LOST
    assert verdict.effects_proven is False


def test_timeout_is_not_a_failure_verdict():
    verdict = _normalize(ObservationInput(timeout=True))
    assert verdict.state is ObservationState.TIMEOUT


def test_pending_is_not_confirmation():
    verdict = _normalize(ObservationInput(status="PENDING"))
    assert verdict.state is ObservationState.PENDING


def test_missing_receipt_state_is_submission_unknown():
    verdict = _normalize(ObservationInput())
    assert verdict.state is ObservationState.SUBMISSION_UNKNOWN
    assert verdict.reasons == [OBS_MISSING_RECEIPT]


def test_network_mismatch_rejected():
    verdict = _normalize(ObservationInput(chain_id=10143))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_NETWORK_MISMATCH]


def test_wallet_mismatch_rejected():
    verdict = _normalize(ObservationInput(wallet_id="0x00000000000000000000000000000000000000B2"))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_WALLET_MISMATCH]


def test_candidate_identity_mismatch_rejected():
    verdict = _normalize(ObservationInput(candidate_hash="sha256:" + "c" * 64))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_IDENTITY_MISMATCH]


def test_tx_hash_mismatch_rejected():
    verdict = _normalize(ObservationInput(tx_hash="0x" + "d" * 64), expected_tx_hash=TX)
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_TX_MISMATCH]
