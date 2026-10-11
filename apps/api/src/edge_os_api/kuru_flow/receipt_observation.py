"""Normalize supplied receipt and observation fixtures.

This binds one supplied observation to the original expected action identity and
preserves missing receipts, lost acknowledgements, timeouts, pending or reverted
results, identity mismatches and unknown actual deltas. The bytes/action binding
is required: an observation that omits the candidate identity, or the transaction
identity when one is expected, is rejected with ``OBS_BINDING_MISSING`` and never
proves effects. A success status alone is not proof of all asset effects: without
reconciled input, output and gas the effects stay unproven. The normalizer never
retries, replaces a route, produces a second action or builds a durable queue.
"""

from __future__ import annotations

from typing import Literal

from edge_os_api.admission.types import AssetAmount
from edge_os_api.kuru_flow.types import ObservationState, StrictModel

OBS_NETWORK_MISMATCH = "OBS_NETWORK_MISMATCH"
OBS_WALLET_MISMATCH = "OBS_WALLET_MISMATCH"
OBS_TX_MISMATCH = "OBS_TX_MISMATCH"
OBS_IDENTITY_MISMATCH = "OBS_IDENTITY_MISMATCH"
OBS_BINDING_MISSING = "OBS_BINDING_MISSING"
OBS_MISSING_RECEIPT = "OBS_MISSING_RECEIPT"
OBS_EFFECTS_UNPROVEN = "OBS_EFFECTS_UNPROVEN"


class ObservationInput(StrictModel):
    """One supplied observation fixture. Absent fields are unknown, never zero."""

    status: Literal["SUCCESS", "REVERTED", "PENDING"] | None = None
    tx_hash: str | None = None
    chain_id: int | None = None
    wallet_id: str | None = None
    candidate_hash: str | None = None
    receipt_present: bool = False
    acknowledgement_lost: bool = False
    timeout: bool = False
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None


class ObservationVerdict(StrictModel):
    """The normalized observation bound to the original expected action identity."""

    state: ObservationState
    expected_candidate_hash: str
    receipt_present: bool
    effects_proven: bool
    tx_hash: str | None = None
    chain_id: int | None = None
    wallet_id: str | None = None
    actual_input: AssetAmount | None = None
    actual_output: AssetAmount | None = None
    actual_gas: AssetAmount | None = None
    reasons: list[str] = []


def normalize_observation(
    *,
    observation: ObservationInput,
    expected_candidate_hash: str,
    expected_chain_id: int,
    expected_wallet: str,
    expected_tx_hash: str | None = None,
) -> ObservationVerdict:
    """Normalize one observation without inventing any economic effect."""

    def verdict(
        state: ObservationState,
        *,
        effects_proven: bool = False,
        reasons: list[str] | None = None,
    ) -> ObservationVerdict:
        return ObservationVerdict(
            state=state,
            expected_candidate_hash=expected_candidate_hash,
            receipt_present=observation.receipt_present,
            effects_proven=effects_proven,
            tx_hash=observation.tx_hash,
            chain_id=observation.chain_id,
            wallet_id=observation.wallet_id,
            actual_input=observation.actual_input,
            actual_output=observation.actual_output,
            actual_gas=observation.actual_gas,
            reasons=reasons or [],
        )

    if observation.acknowledgement_lost:
        return verdict(ObservationState.ACKNOWLEDGEMENT_LOST)
    if observation.timeout:
        return verdict(ObservationState.TIMEOUT)
    if observation.status == "PENDING":
        return verdict(ObservationState.PENDING)

    if observation.chain_id is not None and observation.chain_id != expected_chain_id:
        return verdict(ObservationState.REJECTED, reasons=[OBS_NETWORK_MISMATCH])
    if observation.wallet_id is not None and observation.wallet_id != expected_wallet:
        return verdict(ObservationState.REJECTED, reasons=[OBS_WALLET_MISMATCH])
    if observation.candidate_hash is None:
        return verdict(ObservationState.REJECTED, reasons=[OBS_BINDING_MISSING])
    if observation.candidate_hash != expected_candidate_hash:
        return verdict(ObservationState.REJECTED, reasons=[OBS_IDENTITY_MISMATCH])
    if expected_tx_hash is not None:
        if observation.tx_hash is None:
            return verdict(ObservationState.REJECTED, reasons=[OBS_BINDING_MISSING])
        if observation.tx_hash != expected_tx_hash:
            return verdict(ObservationState.REJECTED, reasons=[OBS_TX_MISMATCH])

    if observation.status == "REVERTED":
        return verdict(ObservationState.REVERTED)

    if observation.status == "SUCCESS":
        if not observation.receipt_present:
            return verdict(ObservationState.REJECTED, reasons=[OBS_MISSING_RECEIPT])
        if (
            observation.actual_input is None
            or observation.actual_output is None
            or observation.actual_gas is None
        ):
            return verdict(ObservationState.CONFIRMED, effects_proven=False, reasons=[OBS_EFFECTS_UNPROVEN])
        return verdict(ObservationState.CONFIRMED, effects_proven=True)

    return verdict(ObservationState.SUBMISSION_UNKNOWN, reasons=[OBS_MISSING_RECEIPT])
