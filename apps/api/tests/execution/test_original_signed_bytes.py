"""Signed-byte identity and validation against independent anchors (#58 ORIGINAL-LOCAL).

Anchors that do not come from the code under test:
- Keccak-256 of the empty input (the standard known answer);
- the eth-account documentation's published legacy transaction: its raw bytes recover the published sender, and
  Keccak of the full bytes equals the published transaction hash;
- the frozen AUTHORED recording: expected fields are written here as literals from the writer's constants.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eth_account.typed_transactions import TypedTransaction
from eth_utils import keccak
from hexbytes import HexBytes

from edge_os_api.execution.original_transaction import validate_signed

RECORDINGS = Path(__file__).parent.parent / "fixtures" / "original_transaction" / "original_transaction_v1.json"
PUBLISHED_SENDER = "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23"
PUBLISHED_LEGACY_RAW = (
    "0xf86a8086d55698372431831e848094f0109fc8df283027b6285cc889f5aa624eac1f55843b9aca008025a009ebb6ca057a0535d618"
    "6462bc0b465b561c94a295bdb0621fc19208ab149a9ca0440ffd775ce91a833ab410777204d5341a6f9fa91216a6f3ee2c051fea6a0428")
PUBLISHED_LEGACY_HASH = "0xd8f64a42b57be0d565f385378db2f6bf324ce14a594afc05de90436e9ce01f60"
ENTRY_NONCE0_HASH = "0x7067b4c886f172b32b1c2839bcd70a45186817e3ade5648bb34fc0d6ea7aa28d"


def recording():
    data = json.loads(RECORDINGS.read_text())
    signed = next(item["response"]["data"]["signed_transaction"] for item in data["signatures"]
                  if item["operation"] == "ENTRY" and item["nonce"] == 0)
    calldata = "0x" + next(route["response"]["transaction"]["calldata"] for route in data["routes"]
                           if route["request"]["amount"] == "100000000")
    unsigned = {"type": 2, "chain_id": 143, "nonce": 0, "to": "0x00000000000000000000000000000000000f1007",
                "value": 0, "data": calldata, "gas_limit": 300000, "max_fee_per_gas": 3000000000,
                "max_priority_fee_per_gas": 1000000000}
    return signed, unsigned


def test_keccak_matches_the_standard_empty_input_answer():
    assert keccak(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"


def test_the_published_legacy_vector_hashes_its_full_bytes_and_is_refused_as_unsupported():
    assert "0x" + keccak(bytes.fromhex(PUBLISHED_LEGACY_RAW[2:])).hex() == PUBLISHED_LEGACY_HASH
    _, unsigned = recording()
    assert validate_signed(PUBLISHED_LEGACY_RAW, unsigned, PUBLISHED_SENDER) == (None, [
        "TRANSACTION_TYPE_UNSUPPORTED"])


def test_the_authored_eip1559_bytes_validate_to_the_full_signed_hash_not_the_signing_preimage():
    signed, unsigned = recording()
    assert validate_signed(signed, unsigned, PUBLISHED_SENDER) == (ENTRY_NONCE0_HASH, [])
    preimage = "0x" + TypedTransaction.from_bytes(HexBytes(signed)).hash().hex()
    assert preimage != ENTRY_NONCE0_HASH


@pytest.mark.parametrize("field,value,reason", [
    ("chain_id", 10143, "SIGNED_CHAINID_MISMATCH"), ("nonce", 1, "SIGNED_NONCE_MISMATCH"),
    ("to", "0x00000000000000000000000000000000000f1008", "SIGNED_TO_MISMATCH"),
    ("value", 1, "SIGNED_VALUE_MISMATCH"), ("data", "0x12345678", "SIGNED_DATA_MISMATCH"),
    ("gas_limit", 300001, "SIGNED_GAS_MISMATCH"), ("max_fee_per_gas", 3000000001, "SIGNED_MAXFEEPERGAS_MISMATCH"),
    ("max_priority_fee_per_gas", 1, "SIGNED_MAXPRIORITYFEEPERGAS_MISMATCH")])
def test_each_field_that_differs_from_the_frozen_original_is_refused(field, value, reason):
    signed, unsigned = recording()
    assert validate_signed(signed, {**unsigned, field: value}, PUBLISHED_SENDER) == (None, [reason])


def test_bytes_from_another_signer_are_refused():
    signed, unsigned = recording()
    assert validate_signed(signed, unsigned, "0x" + "11" * 20) == (None, ["SIGNED_SENDER_MISMATCH"])


def test_a_tampered_byte_never_validates():
    signed, unsigned = recording()
    tampered = signed[:-6] + ("00" if signed[-6:-4] != "00" else "01") + signed[-4:]
    transaction_hash, reasons = validate_signed(tampered, unsigned, PUBLISHED_SENDER)
    assert transaction_hash is None and reasons
