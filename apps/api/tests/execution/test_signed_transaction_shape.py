"""validate_signed refuses incomplete or wrongly typed expected and decoded transactions (#58 Phase B)."""
from __future__ import annotations

import json

import pytest
from eth_account.typed_transactions import TypedTransaction
from hexbytes import HexBytes

import edge_os_api.execution.original_transaction as module
from edge_os_api.execution.original_transaction import validate_signed

from execution.test_original_signed_bytes import (
    ENTRY_NONCE0_HASH, PUBLISHED_SENDER, RECORDINGS, recording)

SIGNED_KEYS = frozenset({"chainId", "nonce", "maxPriorityFeePerGas", "maxFeePerGas", "gas", "to", "value",
                         "data", "accessList", "v", "r", "s", "type"})
SIGNED_NUMERIC = ("chainId", "nonce", "maxPriorityFeePerGas", "maxFeePerGas", "gas", "value", "v", "r", "s", "type")


def _without(unsigned, name):
    value = dict(unsigned)
    del value[name]
    return value


def test_the_real_locked_decoder_accepts_the_frozen_original():
    signed, unsigned = recording()
    assert validate_signed(signed, unsigned, PUBLISHED_SENDER) == (ENTRY_NONCE0_HASH, [])


def test_all_recorded_signatures_decode_to_the_supported_shape():
    data = json.loads(RECORDINGS.read_text())
    seen = set()
    for item in data["signatures"]:
        signed = item["response"]["data"]["signed_transaction"]
        if signed in seen:
            continue
        seen.add(signed)
        fields = TypedTransaction.from_bytes(HexBytes(signed)).as_dict()
        assert set(fields) == SIGNED_KEYS
        assert all(type(fields[name]) is int for name in SIGNED_NUMERIC)
        assert fields["type"] == 2 and fields["v"] in (0, 1)
        assert type(fields["to"]) in (bytes, HexBytes) and len(fields["to"]) == 20
        assert type(fields["data"]) in (bytes, HexBytes)
        assert type(fields["accessList"]) is tuple and fields["accessList"] == ()
    assert len(seen) == 16


@pytest.mark.parametrize("unsigned_factory", [
    lambda u: _without(u, "value"),
    lambda u: {**u, "extra": 1},
    lambda u: {**u, "nonce": False},
    lambda u: {**u, "value": 0.0},
    lambda u: {**u, "chain_id": True},
    lambda u: {**u, "type": 1},
    lambda u: {**u, "type": False},
    lambda u: {**u, "to": "0x1234"},
    lambda u: {**u, "data": "0x123"},
    lambda u: {**u, "gas_limit": -1},
    lambda u: {**u, "max_fee_per_gas": 2 ** 256},
])
def test_incomplete_or_wrongly_typed_expected_transactions_are_refused(unsigned_factory):
    signed, unsigned = recording()
    assert validate_signed(signed, unsigned_factory(unsigned), PUBLISHED_SENDER) == (
        None, ["SIGNED_EXPECTED_MALFORMED"])


class _Decoder:
    def __init__(self, fields, raw):
        self._fields, self._raw = fields, raw

    def as_dict(self):
        return self._fields

    def encode(self):
        return self._raw


def _with_decoder(monkeypatch, mutate):
    signed, unsigned = recording()
    raw = bytes.fromhex(signed[2:])
    fields = TypedTransaction.from_bytes(HexBytes(raw)).as_dict()
    mutate(fields)

    class Stub:
        @staticmethod
        def from_bytes(value):
            return _Decoder(fields, raw)

    monkeypatch.setattr(module, "TypedTransaction", Stub)
    return signed, unsigned


@pytest.mark.parametrize("mutate", [
    lambda f: f.__setitem__("authorizationList", []),
    lambda f: f.pop("accessList"),
    lambda f: f.pop("v"),
    lambda f: f.__setitem__("nonce", False),
    lambda f: f.__setitem__("value", 0.0),
    lambda f: f.__setitem__("accessList", False),
    lambda f: f.__setitem__("accessList", []),
    lambda f: f.__setitem__("data", bytearray(f["data"])),
    lambda f: f.__setitem__("to", "0x" + "11" * 20),
    lambda f: f.__setitem__("type", False),
])
def test_malformed_decoded_shapes_are_refused(monkeypatch, mutate):
    signed, unsigned = _with_decoder(monkeypatch, mutate)
    assert validate_signed(signed, unsigned, PUBLISHED_SENDER) == (None, ["SIGNED_SHAPE_MALFORMED"])
