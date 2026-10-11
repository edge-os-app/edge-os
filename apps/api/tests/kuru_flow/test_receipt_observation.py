from __future__ import annotations

from edge_os_api.admission.types import AssetAmount
from edge_os_api.kuru_flow.receipt_observation import (
    OBS_BINDING_MISSING,
    OBS_CHAIN_MISSING,
    OBS_EFFECTS_UNPROVEN,
    OBS_IDENTITY_MISMATCH,
    OBS_MISSING_RECEIPT,
    OBS_NETWORK_MISMATCH,
    OBS_TX_MISMATCH,
    OBS_TX_MISSING,
    OBS_WALLET_MISMATCH,
    OBS_WALLET_MISSING,
    ObservationInput,
    normalize_observation,
)
from edge_os_api.kuru_flow.types import ObservationState

HASH = "sha256:" + "a" * 64
WALLET = "0x00000000000000000000000000000000000000A1"
OTHER_WALLET = "0x00000000000000000000000000000000000000B2"
TX = "0x" + "b" * 64
INPUT = AssetAmount(asset_id="monad:143/native", raw="1000000000000000000", decimals=18)
OUTPUT = AssetAmount(asset_id="monad:143/usdc", raw="1450000", decimals=6)
GAS = AssetAmount(asset_id="monad:143/native", raw="21000", decimals=18)


def _normalize(observation: ObservationInput, **overrides):
    kwargs = {"expected_candidate_hash": HASH, "expected_chain_id": 143, "expected_wallet": WALLET}
    kwargs.update(overrides)
    return normalize_observation(observation=observation, **kwargs)


def _bound(**overrides) -> ObservationInput:
    fields = {
        "status": "SUCCESS",
        "receipt_present": True,
        "tx_hash": TX,
        "chain_id": 143,
        "wallet_id": WALLET,
        "candidate_hash": HASH,
        "actual_input": INPUT,
        "actual_output": OUTPUT,
        "actual_gas": GAS,
    }
    fields.update(overrides)
    return ObservationInput(**fields)


def test_fully_bound_success_proves_effects():
    verdict = _normalize(_bound())
    assert verdict.state is ObservationState.CONFIRMED
    assert verdict.effects_proven is True
    assert verdict.reasons == []


def test_missing_chain_binding_rejected():
    verdict = _normalize(_bound(chain_id=None))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_CHAIN_MISSING]


def test_missing_wallet_binding_rejected():
    verdict = _normalize(_bound(wallet_id=None))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_WALLET_MISSING]


def test_missing_candidate_binding_rejected():
    verdict = _normalize(_bound(candidate_hash=None), expected_tx_hash=TX)
    assert verdict.state is ObservationState.REJECTED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_BINDING_MISSING]


def test_missing_transaction_binding_rejected():
    verdict = _normalize(_bound(tx_hash=None), expected_tx_hash=TX)
    assert verdict.state is ObservationState.REJECTED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_TX_MISSING]


def test_network_mismatch_rejected():
    verdict = _normalize(_bound(chain_id=10143))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_NETWORK_MISMATCH]


def test_wallet_mismatch_rejected():
    verdict = _normalize(_bound(wallet_id=OTHER_WALLET))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_WALLET_MISMATCH]


def test_candidate_identity_mismatch_rejected():
    verdict = _normalize(_bound(candidate_hash="sha256:" + "c" * 64))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_IDENTITY_MISMATCH]


def test_tx_hash_mismatch_rejected():
    verdict = _normalize(_bound(tx_hash="0x" + "d" * 64), expected_tx_hash=TX)
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_TX_MISMATCH]


def test_success_without_deltas_leaves_effects_unproven():
    verdict = _normalize(_bound(actual_input=None, actual_output=None, actual_gas=None))
    assert verdict.state is ObservationState.CONFIRMED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_EFFECTS_UNPROVEN]


def test_success_with_known_deltas_but_unknown_gas_leaves_effects_unproven():
    verdict = _normalize(_bound(actual_gas=None))
    assert verdict.state is ObservationState.CONFIRMED
    assert verdict.effects_proven is False
    assert verdict.reasons == [OBS_EFFECTS_UNPROVEN]


def test_success_without_receipt_is_rejected():
    verdict = _normalize(_bound(receipt_present=False))
    assert verdict.state is ObservationState.REJECTED
    assert verdict.reasons == [OBS_MISSING_RECEIPT]


def test_reverted_retains_optional_gas():
    verdict = _normalize(_bound(status="REVERTED", actual_gas=None))
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
    verdict = _normalize(_bound(status=None))
    assert verdict.state is ObservationState.SUBMISSION_UNKNOWN
    assert verdict.reasons == [OBS_MISSING_RECEIPT]
