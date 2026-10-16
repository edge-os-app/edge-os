"""Literal tests for the local synthetic Privy policy-proof driver.

Every expected value below is written by hand from CONTRACT.md. Nothing here
contacts a provider or chain. Send, clock and signed-transaction decoding are
local doubles, and every result is SYNTHETIC_FIXTURE.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from edge_os_api.kuru_flow.flow_calldata import CalldataDecodeError, decode_flow_call
from edge_os_api.kuru_flow.policy_binding.policy_request import _flow_abi
from scripts.privy_unfunded_proof import evidence, specimens
from scripts.privy_unfunded_proof.evidence import Outcome, Reply, run_specimen
from scripts.privy_unfunded_proof.specimens import (
    AttemptState,
    AttemptStore,
    SpecimenRefused,
    SpecimenTableError,
)

CHECKOUT_ROOT = Path(__file__).resolve().parents[2]
TEMP_PREFIX = "p21-driver-test-"

ENTRYPOINT = "0xb3e6778480b2E488385E8205eA05E20060B813cb"
WALLET_A = "0x00000000000000000000000000000000000000a1"
WALLET_B = "0x00000000000000000000000000000000000000a2"
URL_A = "https://api.privy.io/v1/wallets/synthetic-probe-wallet-a/rpc"
URL_B = "https://api.privy.io/v1/wallets/synthetic-probe-wallet-b/rpc"

BASELINE_DATA = (
    "0x12345678"
    "00000000000000000000000000000000000000000000000000000000000000b1"
    "00000000000000000000000000000000000000000000000000000000000f4240"
    "00000000000000000000000000000000000000000000000000000000000000c1"
    "00000000000000000000000000000000000000000000000000000000001e8480"
    "00000000000000000000000000000000000000000000000000000000000000d1"
    "000000000000000000000000000000000000000000000000000000000000000a"
    "00000000000000000000000000000000000000000000000000000000000000e1"
    "0000000000000000000000000000000000000000000000000000000000000005"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000140"
    "0000000000000000000000000000000000000000000000000000000000000008"
    "a1b2c3d4e5f60718000000000000000000000000000000000000000000000000"
)

BASELINE_TX = {
    "type": 2,
    "chain_id": 143,
    "to": ENTRYPOINT,
    "value": 0,
    "nonce": 0,
    "gas_limit": 300000,
    "max_fee_per_gas": 100000000000,
    "max_priority_fee_per_gas": 2000000000,
    "data": BASELINE_DATA,
}

BASELINE_DECODED = {
    "selector": "0x12345678",
    "method": "EXECUTE_SWAP",
    "token_user_buys": "0x00000000000000000000000000000000000000b1",
    "min_amount_user_buys": "1000000",
    "token_user_sells": "0x00000000000000000000000000000000000000c1",
    "amount_user_sells": "2000000",
    "fee_collector_address": "0x00000000000000000000000000000000000000d1",
    "fee_bps": 10,
    "referrer_address": "0x00000000000000000000000000000000000000e1",
    "referrer_fee_bps": 5,
    "is_in_token_fee": False,
    "program_hex": "0xa1b2c3d4e5f60718",
    "receiver": None,
}

# specimen suffix -> (changed decoded field, literal new value, changed calldata byte indexes)
CALLDATA_MUTATIONS = {
    "token_user_buys": ("token_user_buys", "0x00000000000000000000000000000000000000b2", {35}),
    "min_amount_user_buys": ("min_amount_user_buys", "999999", {67}),
    "token_user_sells": ("token_user_sells", "0x00000000000000000000000000000000000000c2", {99}),
    "amount_user_sells": ("amount_user_sells", "2000001", {131}),
    "fee_collector_address": ("fee_collector_address", "0x00000000000000000000000000000000000000d2", {163}),
    "fee_bps": ("fee_bps", 11, {195}),
    "referrer_address": ("referrer_address", "0x00000000000000000000000000000000000000e2", {227}),
    "referrer_fee_bps": ("referrer_fee_bps", 6, {259}),
    "is_in_token_fee": ("is_in_token_fee", True, {291}),
    "program_byte_flip": ("program_hex", "0xa1b2c32be5f60718", {359}),
}

TRANSACTION_MUTATIONS = {
    "wrong_chain": ("chain_id", 10143),
    "wrong_to": ("to", "0x00000000000000000000000000000000000000f1"),
    "native_value": ("value", 1),
    "gas_limit": ("gas_limit", 300001),
    "max_fee_per_gas": ("max_fee_per_gas", 100000000001),
    "max_priority_fee_per_gas": ("max_priority_fee_per_gas", 2000000001),
}

RAW_IDS = [
    "raw.baseline", "raw.wrong_chain", "raw.foreign_wallet", "raw.wrong_to",
    "raw.receiver_selector", "raw.program_byte_flip", "raw.trailing_word", "raw.data_hex_case",
    "raw.token_user_sells", "raw.token_user_buys", "raw.amount_user_sells",
    "raw.min_amount_user_buys", "raw.fee_collector_address", "raw.fee_bps",
    "raw.referrer_address", "raw.referrer_fee_bps", "raw.is_in_token_fee", "raw.native_value",
    "raw.type1_envelope", "raw.type0_envelope", "raw.type4_envelope", "raw.gas_limit",
    "raw.max_fee_per_gas", "raw.max_priority_fee_per_gas", "raw.window_at_t",
    "raw.window_after_t", "raw.request_expiry", "raw.allowance_approve", "raw.personal_sign",
    "raw.post_removal",
]
DECODED_IDS = [
    "decoded.baseline", "decoded.program_byte_flip", "decoded.program_hex_case",
    "decoded.trailing_word", "decoded.token_user_sells", "decoded.token_user_buys",
    "decoded.amount_user_sells", "decoded.min_amount_user_buys",
    "decoded.fee_collector_address", "decoded.fee_bps", "decoded.referrer_address",
    "decoded.referrer_fee_bps", "decoded.is_in_token_fee", "decoded.receiver_selector",
]

SECRET_CANARY = "CANARY-SECRET-7f3e"
SIGNATURE_CANARY = "CANARY-AUTHSIG-91ab"
SIGNED_CANARY = "CANARY-SIGNED-c0de"
CANARIES = (SECRET_CANARY, SIGNATURE_CANARY, SIGNED_CANARY)


# ---------------------------------------------------------------- doubles


@pytest.fixture
def store_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as name:
        yield Path(name)


def clock() -> str:
    return "2026-10-16T00:00:00Z"


def decode_signed(raw: bytes) -> dict:
    """Synthetic decoder: the fake signed bytes are JSON public fields."""
    return json.loads(raw.decode("utf-8"))


def signed_fields(**overrides: object) -> dict:
    fields: dict[str, object] = {
        "wallet": WALLET_A,
        **{key: value for key, value in BASELINE_TX.items()},
    }
    fields.update(overrides)
    return fields


def success_reply(fields: dict, *, extra: dict | None = None) -> Reply:
    signed_hex = "0x" + json.dumps(fields).encode("utf-8").hex()
    body = {"method": "eth_signTransaction", "data": {"signed_transaction": signed_hex, "encoding": "rlp"}}
    if extra:
        body["data"].update(extra)
    return Reply(status=200, content_type="application/json", body=json.dumps(body).encode("utf-8"))


def code_reply(status: int, code: str) -> Reply:
    return Reply(status=status, content_type="application/json", body=json.dumps({"code": code}).encode("utf-8"))


class RecordingSend:
    def __init__(self, reply: Reply | None = None, error: BaseException | None = None) -> None:
        self.reply = reply
        self.error = error
        self.requests: list = []

    def __call__(self, request):  # noqa: ANN001
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.reply


def run(specimen_id: str, store_dir: Path, send, **kwargs):  # noqa: ANN001
    return run_specimen(
        specimen_id,
        store=AttemptStore(store_dir),
        send=send,
        decode_signed=kwargs.pop("decoder", decode_signed),
        clock=clock,
        **kwargs,
    )


def allow_baseline(store_dir: Path, profile: str = "raw") -> None:
    result = run(f"{profile}.baseline", store_dir, RecordingSend(success_reply(signed_fields())))
    assert result.outcome is Outcome.ALLOW


def body_of(specimen_id: str) -> dict:
    request = specimens.FROZEN_TABLE.get(specimen_id).request
    return json.loads(request.body.decode("utf-8"))


def calldata_of(specimen_id: str) -> str:
    return body_of(specimen_id)["params"]["transaction"]["data"]


def decoded_dict(data_hex: str, method: str = "EXECUTE_SWAP") -> dict:
    call = decode_flow_call(data_hex=data_hex, method=method)
    return {
        "selector": call.selector,
        "method": call.method,
        "token_user_buys": call.intent.token_user_buys,
        "min_amount_user_buys": call.intent.min_amount_user_buys,
        "token_user_sells": call.intent.token_user_sells,
        "amount_user_sells": call.intent.amount_user_sells,
        "fee_collector_address": call.fees.fee_collector_address,
        "fee_bps": call.fees.fee_bps,
        "referrer_address": call.fees.referrer_address,
        "referrer_fee_bps": call.fees.referrer_fee_bps,
        "is_in_token_fee": call.fees.is_in_token_fee,
        "program_hex": call.program_hex,
        "receiver": call.receiver,
    }


def changed_byte_indexes(left: str, right: str) -> set[int]:
    a, b = bytes.fromhex(left[2:]), bytes.fromhex(right[2:])
    assert len(a) == len(b)
    return {index for index in range(len(a)) if a[index] != b[index]}


def all_saved_text(root: Path) -> str:
    return "".join(path.read_text(encoding="utf-8", errors="replace") for path in sorted(root.iterdir()))


def run_child(code: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-s", "-c", code],
        cwd=CHECKOUT_ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=timeout, check=False,
    )


CHILD_PRELUDE = """
import json, os, sys
from pathlib import Path
from scripts.privy_unfunded_proof.evidence import Reply, run_specimen
from scripts.privy_unfunded_proof.specimens import AttemptStore, SpecimenRefused
root = Path(sys.argv[1])
"""


# ---------------------------------------------------------------- 3 matrix


def test_matrix_ids_and_counts() -> None:
    table = specimens.FROZEN_TABLE
    assert [s.specimen_id for s in table.profile("raw")] == RAW_IDS
    assert [s.specimen_id for s in table.profile("decoded")] == DECODED_IDS
    assert len(RAW_IDS) == 30 and len(DECODED_IDS) == 14
    assert table.manifest_sha256 == specimens.MANIFEST_SHA256
    assert table.get("raw.baseline").expected == "ALLOW"
    assert table.get("raw.foreign_wallet").expected == "AUTHORIZATION_DENY"
    assert table.get("raw.post_removal").expected == "AUTHORIZATION_DENY"
    assert table.get("raw.request_expiry").expected == "EXPIRY_REFUSAL"
    assert table.get("raw.data_hex_case").expected == "DIAGNOSTIC"
    assert table.get("decoded.program_hex_case").expected == "DIAGNOSTIC"
    assert table.get("raw.type4_envelope").expected == "NOT_RUN"
    assert table.get("raw.wrong_chain").expected == "POLICY_DENY"


def test_baseline_request_is_literal() -> None:
    request = specimens.FROZEN_TABLE.get("raw.baseline").request
    assert request.url == URL_A
    assert request.http_method == "POST"
    assert request.headers == ()
    assert body_of("raw.baseline") == {"method": "eth_signTransaction", "params": {"transaction": BASELINE_TX}}
    assert request.body == json.dumps(
        {"method": "eth_signTransaction", "params": {"transaction": BASELINE_TX}}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert decoded_dict(calldata_of("raw.baseline")) == BASELINE_DECODED


@pytest.mark.parametrize("profile", ["raw", "decoded"])
@pytest.mark.parametrize("suffix", sorted(CALLDATA_MUTATIONS))
def test_calldata_mutations_change_only_named_field(profile: str, suffix: str) -> None:
    field, value, indexes = CALLDATA_MUTATIONS[suffix]
    data = calldata_of(f"{profile}.{suffix}")
    assert changed_byte_indexes(BASELINE_DATA, data) == indexes
    want = dict(BASELINE_DECODED)
    want[field] = value
    assert decoded_dict(data) == want
    transaction = body_of(f"{profile}.{suffix}")["params"]["transaction"]
    assert {k: v for k, v in transaction.items() if k != "data"} == {k: v for k, v in BASELINE_TX.items() if k != "data"}
    assert specimens.FROZEN_TABLE.get(f"{profile}.{suffix}").expected == "POLICY_DENY"


@pytest.mark.parametrize("suffix", sorted(TRANSACTION_MUTATIONS))
def test_transaction_mutations_change_only_named_field(suffix: str) -> None:
    field, value = TRANSACTION_MUTATIONS[suffix]
    want = dict(BASELINE_TX)
    want[field] = value
    assert body_of(f"raw.{suffix}") == {"method": "eth_signTransaction", "params": {"transaction": want}}


def test_receiver_selector_variant() -> None:
    for profile in ("raw", "decoded"):
        decoded = decoded_dict(calldata_of(f"{profile}.receiver_selector"), method="EXECUTE_SWAP_WITH_RECEIVER")
        want = dict(BASELINE_DECODED)
        want.update(selector="0x87654321", method="EXECUTE_SWAP_WITH_RECEIVER", receiver=WALLET_B)
        assert decoded == want


def test_envelope_variants_declared_separately() -> None:
    table = specimens.FROZEN_TABLE
    base = {k: v for k, v in BASELINE_TX.items() if k not in ("type", "max_fee_per_gas", "max_priority_fee_per_gas")}
    assert body_of("raw.type1_envelope")["params"]["transaction"] == {**base, "type": 1, "gas_price": 100000000000}
    assert body_of("raw.type0_envelope")["params"]["transaction"] == {**base, "type": 0, "gas_price": 100000000000}
    for sid in ("raw.type1_envelope", "raw.type0_envelope", "raw.type4_envelope"):
        assert table.get(sid).category == "ENVELOPE_VARIANT"
    for sid in ("raw.wrong_chain", "raw.gas_limit", "raw.fee_bps"):
        assert table.get(sid).category == "FIELD_MUTATION"


def test_operation_and_timing_specimens_are_literal() -> None:
    approve = body_of("raw.allowance_approve")["params"]["transaction"]
    assert approve == {
        **BASELINE_TX,
        "to": "0x00000000000000000000000000000000000000c1",
        "data": "0x095ea7b3"
        "000000000000000000000000b3e6778480b2e488385e8205ea05e20060b813cb"
        "00000000000000000000000000000000000000000000000000000000001e8480",
    }
    assert body_of("raw.personal_sign") == {
        "method": "personal_sign",
        "params": {"message": "edge-os synthetic inert probe text", "encoding": "utf-8"},
    }
    expiry = specimens.FROZEN_TABLE.get("raw.request_expiry").request
    assert expiry.headers == (("privy-request-expiry", "1792000000000"),)
    assert body_of("raw.request_expiry") == body_of("raw.baseline")
    for sid in ("raw.window_at_t", "raw.window_after_t", "raw.post_removal"):
        assert body_of(sid) == body_of("raw.baseline")
    assert specimens.FROZEN_TABLE.get("raw.foreign_wallet").request.url == URL_B
    assert body_of("raw.foreign_wallet") == body_of("raw.baseline")


def test_case_diagnostics_keep_the_same_bytes() -> None:
    upper = calldata_of("raw.data_hex_case")
    assert upper == "0x" + BASELINE_DATA[2:].upper()
    program_case = calldata_of("decoded.program_hex_case")
    assert program_case == BASELINE_DATA.replace("a1b2c3d4e5f60718", "A1B2C3D4E5F60718")
    assert bytes.fromhex(upper[2:]) == bytes.fromhex(BASELINE_DATA[2:])
    assert bytes.fromhex(program_case[2:]) == bytes.fromhex(BASELINE_DATA[2:])


def test_trailing_word_stays_raw_challenge() -> None:
    for profile in ("raw", "decoded"):
        data = calldata_of(f"{profile}.trailing_word")
        assert data == BASELINE_DATA + "00" * 31 + "01"
        with pytest.raises(CalldataDecodeError) as caught:
            decode_flow_call(data_hex=data, method="EXECUTE_SWAP")
        assert caught.value.reason == "INCONSISTENT_ABI"
        assert specimens.FROZEN_TABLE.get(f"{profile}.trailing_word").expected == "POLICY_DENY"


def test_decoded_profile_uses_alias_paths() -> None:
    assert specimens.DECODED_POLICY_FIELD_PATHS == (
        "executeSwap.intent.tokenUserBuys",
        "executeSwap.intent.minAmountUserBuys",
        "executeSwap.intent.tokenUserSells",
        "executeSwap.intent.amountUserSells",
        "executeSwap.fees.feeCollectorAddress",
        "executeSwap.fees.feeBps",
        "executeSwap.fees.referrerAddress",
        "executeSwap.fees.referrerFeeBps",
        "executeSwap.fees.isInTokenFee",
        "executeSwap.program",
    )
    accepted = _flow_abi("executeSwap", "EXECUTE_SWAP")[0]["inputs"]
    accepted_paths = [
        f"executeSwap.{arg['name']}.{part['name']}" for arg in accepted if arg["type"] == "tuple" for part in arg["components"]
    ] + [f"executeSwap.{arg['name']}" for arg in accepted if arg["type"] == "bytes"]
    assert list(specimens.DECODED_POLICY_FIELD_PATHS) == accepted_paths
    assert not any("swapIntent" in p or "feeCollection" in p for p in specimens.DECODED_POLICY_FIELD_PATHS)


# ---------------------------------------------------------------- 2 admission and bounds


def test_table_admission_rejects_bad_tables() -> None:
    baseline = specimens.FROZEN_TABLE.get("raw.baseline")
    cases = {
        "DUPLICATE_ID": [baseline, baseline],
        "MALFORMED_ID": [specimens.replace_specimen(baseline, specimen_id="raw/Bad")],
        "OVER_CAP": [specimens.replace_specimen(baseline, specimen_id=f"raw.s{i}") for i in range(33)],
    }
    for code, rows in cases.items():
        with pytest.raises(SpecimenTableError) as caught:
            specimens.build_table(rows)
        assert caught.value.code == code
    assert len(specimens.build_table(
        [specimens.replace_specimen(baseline, specimen_id=f"raw.s{i}") for i in range(32)]
    ).profile("raw")) == 32
    with pytest.raises(SpecimenTableError) as caught:
        specimens.freeze_request("synthetic-probe-wallet-a", {"method": "eth_sendTransaction", "params": {}})
    assert caught.value.code == "UNSUPPORTED_OPERATION"
    with pytest.raises(SpecimenTableError) as caught:
        specimens.freeze_request("other-wallet", {"method": "personal_sign", "params": {}})
    assert caught.value.code == "UNSUPPORTED_DESTINATION"
    with pytest.raises(SpecimenTableError) as caught:
        specimens.freeze_request(
            "synthetic-probe-wallet-a", {"method": "personal_sign", "params": {}}, headers={"authorization": "x"}
        )
    assert caught.value.code == "UNSUPPORTED_HEADER"


def test_request_bound_exact_and_overflow() -> None:
    skeleton = {"method": "personal_sign", "params": {"message": "", "encoding": "utf-8"}}
    empty_size = len(json.dumps(skeleton, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    pad = 4096 - empty_size
    exact = specimens.freeze_request(
        "synthetic-probe-wallet-a", {"method": "personal_sign", "params": {"message": "x" * pad, "encoding": "utf-8"}}
    )
    assert len(exact.body) == 4096
    with pytest.raises(SpecimenTableError) as caught:
        specimens.freeze_request(
            "synthetic-probe-wallet-a",
            {"method": "personal_sign", "params": {"message": "x" * (pad + 1), "encoding": "utf-8"}},
        )
    assert caught.value.code == "REQUEST_OVER_BOUND"


def test_record_bound_exact_and_overflow() -> None:
    empty = len(specimens.encode_bounded_record({"k": ""}))
    exact = specimens.encode_bounded_record({"k": "y" * (4096 - empty)})
    assert len(exact) == 4096
    with pytest.raises(specimens.EvidenceOverBound):
        specimens.encode_bounded_record({"k": "y" * (4097 - empty)})


def test_changed_request_bytes_refused(store_dir: Path) -> None:
    allow_baseline(store_dir)
    table = specimens.FROZEN_TABLE
    tampered = specimens.replace_specimen(
        table.get("raw.wrong_chain"),
        request=specimens.replace_request(table.get("raw.wrong_chain").request, body=table.get("raw.baseline").request.body),
    )
    rows = [tampered if s.specimen_id == "raw.wrong_chain" else s for s in table.all()]
    send = RecordingSend(code_reply(400, "synthetic_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.wrong_chain", store_dir, send, table=specimens.build_table(rows, check_frozen=False))
    assert caught.value.code in {"REQUEST_BYTES_CHANGED", "MANIFEST_MISMATCH"}
    assert send.requests == []
    assert AttemptStore(store_dir).state("raw.wrong_chain") is AttemptState.NOT_SENT


def test_manifest_mismatch_refused(store_dir: Path) -> None:
    table = specimens.FROZEN_TABLE
    rows = [s for s in table.all() if s.specimen_id != "raw.post_removal"]
    send = RecordingSend(success_reply(signed_fields()))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, send, table=specimens.build_table(rows, check_frozen=False))
    assert caught.value.code == "MANIFEST_MISMATCH"
    assert send.requests == []
    assert list(store_dir.iterdir()) == []


def test_unknown_specimen_refused(store_dir: Path) -> None:
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.not_listed", store_dir, RecordingSend(success_reply(signed_fields())))
    assert caught.value.code == "UNKNOWN_SPECIMEN"


def test_reply_bound_exact_and_overflow(store_dir: Path) -> None:
    def padded(size: int) -> Reply:
        reply = success_reply(signed_fields())
        body = reply.body + b" " * (size - len(reply.body))
        return Reply(status=200, content_type="application/json", body=body)

    exact = run("raw.baseline", store_dir, RecordingSend(padded(16384)))
    assert exact.outcome is Outcome.ALLOW
    other = store_dir / "second"
    other.mkdir()
    over = run("raw.baseline", other, RecordingSend(padded(16385)))
    assert over.outcome is Outcome.UNKNOWN
    assert over.reason == "RESPONSE_OVER_BOUND"
    capture = json.loads((other / "raw.baseline.capture.json").read_text())
    assert capture["byte_count"] == 16385
    assert capture["metadata_valid"] is True


@pytest.mark.parametrize(
    "status,content_type",
    [("200", "application/json"), (200, None), (99, "application/json"), (600, "application/json"),
     (200, "a" * 129), (200, "application/jsoné"), (True, "application/json")],
)
def test_malformed_metadata_is_unknown(store_dir: Path, status: object, content_type: object) -> None:
    reply = success_reply(signed_fields())
    result = run("raw.baseline", store_dir, RecordingSend(Reply(status=status, content_type=content_type, body=reply.body)))
    assert result.outcome is Outcome.UNKNOWN
    assert result.reason == "MALFORMED_METADATA"
    assert json.loads((store_dir / "raw.baseline.capture.json").read_text())["metadata_valid"] is False


def test_content_type_exact_bound_is_accepted(store_dir: Path) -> None:
    reply = success_reply(signed_fields())
    content_type = "application/json;x=" + "a" * (128 - len("application/json;x="))
    assert len(content_type) == 128
    result = run("raw.baseline", store_dir, RecordingSend(Reply(status=200, content_type=content_type, body=reply.body)))
    assert result.outcome is Outcome.ALLOW


# ---------------------------------------------------------------- 1 lifecycle


def test_intent_is_saved_before_send_and_request_is_frozen(store_dir: Path) -> None:
    seen: dict = {}

    def send(request):  # noqa: ANN001
        seen["state"] = AttemptStore(store_dir).state("raw.baseline")
        seen["intent"] = json.loads((store_dir / "raw.baseline.intent.json").read_text())
        seen["request"] = request
        return success_reply(signed_fields())

    result = run("raw.baseline", store_dir, send)
    assert result.outcome is Outcome.ALLOW
    assert result.evidence_class == "SYNTHETIC_FIXTURE"
    assert seen["state"] is AttemptState.INTENT_SAVED
    frozen = specimens.FROZEN_TABLE.get("raw.baseline").request
    assert seen["request"] is frozen
    assert seen["intent"]["request_sha256"] == frozen.request_sha256
    assert seen["intent"]["state"] == "INTENT_SAVED"
    assert seen["intent"]["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert AttemptStore(store_dir).state("raw.baseline") is AttemptState.TERMINAL


def test_terminal_specimen_refused(store_dir: Path) -> None:
    allow_baseline(store_dir)
    send = RecordingSend(success_reply(signed_fields()))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, send)
    assert caught.value.code == "ALREADY_CLAIMED"
    assert send.requests == []


def test_send_failure_is_unknown_and_consumed(store_dir: Path) -> None:
    result = run("raw.baseline", store_dir, RecordingSend(error=TimeoutError("timed out")))
    assert result.outcome is Outcome.UNKNOWN
    assert result.reason == "SEND_FAILED"
    second = RecordingSend(success_reply(signed_fields()))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, second)
    assert caught.value.code == "ALREADY_CLAIMED"
    assert second.requests == []


def test_uncertain_specimen_refused_after_new_store_and_transport(store_dir: Path) -> None:
    store = AttemptStore(store_dir)
    store.claim(specimens.FROZEN_TABLE.get("raw.baseline"), at=clock())
    assert AttemptStore(store_dir).state("raw.baseline") is AttemptState.INTENT_SAVED
    for reply in (success_reply(signed_fields()), code_reply(400, "synthetic_policy_violation")):
        send = RecordingSend(reply)
        with pytest.raises(SpecimenRefused) as caught:
            run("raw.baseline", store_dir, send)
        assert caught.value.code == "ATTEMPT_UNCERTAIN"
        assert send.requests == []


def test_corrupt_intent_is_uncertain(store_dir: Path) -> None:
    (store_dir / "raw.baseline.intent.json").write_text('{"specimen_id": "raw.base')
    assert AttemptStore(store_dir).state("raw.baseline") is AttemptState.UNCERTAIN
    send = RecordingSend(success_reply(signed_fields()))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, send)
    assert caught.value.code == "ATTEMPT_UNCERTAIN"
    assert send.requests == []
    (store_dir / "raw.baseline.outcome.json").write_text("not json")
    assert AttemptStore(store_dir).state("raw.baseline") is AttemptState.UNCERTAIN


def test_intent_persist_failure_makes_no_send(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_fsync(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(specimens.os, "fsync", failing_fsync)
    send = RecordingSend(success_reply(signed_fields()))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, send)
    assert caught.value.code == "INTENT_NOT_PERSISTED"
    assert send.requests == []
    monkeypatch.undo()
    assert AttemptStore(store_dir).state("raw.baseline") in {AttemptState.INTENT_SAVED, AttemptState.UNCERTAIN}
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, send)
    assert caught.value.code == "ATTEMPT_UNCERTAIN"
    assert send.requests == []


def test_second_claim_loses(store_dir: Path) -> None:
    specimen = specimens.FROZEN_TABLE.get("raw.baseline")
    AttemptStore(store_dir).claim(specimen, at=clock())
    with pytest.raises(SpecimenRefused) as caught:
        AttemptStore(store_dir).claim(specimen, at=clock())
    assert caught.value.code == "ALREADY_CLAIMED"
    assert json.loads((store_dir / "raw.baseline.intent.json").read_text())["intent_at"] == clock()


def test_concurrent_threads_send_once(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Every thread passes the state check, so only the exclusive create decides the claim.
    monkeypatch.setattr(AttemptStore, "state", lambda self, specimen_id: AttemptState.NOT_SENT)
    barrier = threading.Barrier(8)
    sends: list = []
    refusals: list[str] = []
    lock = threading.Lock()

    def send(request):  # noqa: ANN001
        with lock:
            sends.append(request)
        return success_reply(signed_fields())

    def worker() -> None:
        barrier.wait()
        try:
            run("raw.baseline", store_dir, send)
        except SpecimenRefused as error:
            with lock:
                refusals.append(error.code)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(sends) == 1
    assert refusals == ["ALREADY_CLAIMED"] * 7


CHILD_SEND = CHILD_PRELUDE + """
marker_dir = Path(sys.argv[2])
def send(request):
    (marker_dir / f"sent-{os.getpid()}").write_text("x")
    if sys.argv[3] == "die":
        os._exit(17)
    body = json.dumps({"code": "synthetic_wallet_not_authorized"}).encode()
    return Reply(status=403, content_type="application/json", body=body)
try:
    result = run_specimen("raw.baseline", store=AttemptStore(root), send=send,
                          decode_signed=lambda raw: {}, clock=lambda: "2026-10-16T00:00:00Z")
    print("RESULT", result.outcome)
except SpecimenRefused as error:
    print("REFUSED", error.code)
"""


def test_fresh_process_refuses_specimen_lost_after_intent(store_dir: Path) -> None:
    markers = store_dir / "markers"
    markers.mkdir()
    attempts = store_dir / "attempts"
    attempts.mkdir()
    first = run_child(CHILD_SEND.replace("sys.argv[1]", repr(str(attempts))).replace(
        "sys.argv[2]", repr(str(markers))).replace("sys.argv[3]", repr("die")))
    assert first.returncode == 17, first.stderr
    assert len(list(markers.iterdir())) == 1
    assert AttemptStore(attempts).state("raw.baseline") is AttemptState.INTENT_SAVED
    second = run_child(CHILD_SEND.replace("sys.argv[1]", repr(str(attempts))).replace(
        "sys.argv[2]", repr(str(markers))).replace("sys.argv[3]", repr("live")))
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "REFUSED ATTEMPT_UNCERTAIN"
    assert len(list(markers.iterdir())) == 1


def test_concurrent_processes_send_once(store_dir: Path) -> None:
    markers = store_dir / "markers"
    markers.mkdir()
    attempts = store_dir / "attempts"
    attempts.mkdir()
    code = CHILD_SEND.replace("sys.argv[1]", repr(str(attempts))).replace(
        "sys.argv[2]", repr(str(markers))).replace("sys.argv[3]", repr("live"))
    children = [
        subprocess.Popen([sys.executable, "-B", "-s", "-c", code], cwd=CHECKOUT_ROOT, env=dict(os.environ),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(4)
    ]
    outputs = [child.communicate(timeout=60) for child in children]
    assert all(child.returncode == 0 for child in children), outputs
    lines = sorted(out.strip() for out, _ in outputs)
    assert len(list(markers.iterdir())) == 1
    assert sum(line.startswith("RESULT") for line in lines) == 1
    assert sum(line.startswith("REFUSED") for line in lines) == 3


# ---------------------------------------------------------------- 4 type 4


def test_type4_is_not_run_without_owner_authority(store_dir: Path) -> None:
    allow_baseline(store_dir)
    specimen = specimens.FROZEN_TABLE.get("raw.type4_envelope")
    assert specimen.request is None
    assert specimen.not_run_reason == "OWNER_AUTHORITY_ABSENT"
    send = RecordingSend(success_reply(signed_fields(type=4)))
    for authority, reason in ((None, "OWNER_AUTHORITY_ABSENT"), (object(), "SYNTHETIC_AUTHORITY_NOT_PROOF")):
        with pytest.raises(SpecimenRefused) as caught:
            run("raw.type4_envelope", store_dir, send, owner_authority=authority)
        assert caught.value.code == "NOT_RUN"
        assert caught.value.detail == reason
    assert send.requests == []
    assert AttemptStore(store_dir).state("raw.type4_envelope") is AttemptState.NOT_SENT


# ---------------------------------------------------------------- 5 capture and redaction


def test_capture_saved_before_parse(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}
    real_loads = evidence.json.loads

    def watching_loads(text, *args, **kwargs):  # noqa: ANN001
        seen.setdefault("capture_exists_at_parse", (store_dir / "raw.baseline.capture.json").exists())
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(evidence.json, "loads", watching_loads)
    reply = success_reply(signed_fields())
    result = run("raw.baseline", store_dir, RecordingSend(reply))
    assert result.outcome is Outcome.ALLOW
    assert seen["capture_exists_at_parse"] is True
    capture = json.loads((store_dir / "raw.baseline.capture.json").read_text())
    assert capture == {
        "specimen_id": "raw.baseline",
        "profile": "raw",
        "request_sha256": specimens.FROZEN_TABLE.get("raw.baseline").request.request_sha256,
        "status": 200,
        "content_type": "application/json",
        "byte_count": len(reply.body),
        "raw_body_sha256": __import__("hashlib").sha256(reply.body).hexdigest(),
        "metadata_valid": True,
        "captured_at": "2026-10-16T00:00:00Z",
        "evidence_class": "SYNTHETIC_FIXTURE",
    }
    outcome = json.loads((store_dir / "raw.baseline.outcome.json").read_text())
    assert outcome["outcome"] == "ALLOW"
    assert outcome["provider_proof"] == "UNQUALIFIED"
    assert outcome["capture_record_sha256"] == __import__("hashlib").sha256(
        (store_dir / "raw.baseline.capture.json").read_bytes()).hexdigest()
    signed_hex = json.loads(reply.body)["data"]["signed_transaction"]
    assert outcome["signed_bytes_sha256"] == __import__("hashlib").sha256(bytes.fromhex(signed_hex[2:])).hexdigest()
    assert outcome["decoded_public_fields"]["chain_id"] == 143
    assert signed_hex[2:] not in all_saved_text(store_dir)


def test_canaries_absent_everywhere(
    store_dir: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    leaky = success_reply(
        signed_fields(canary=SIGNED_CANARY),
        extra={"authorization_signature": SIGNATURE_CANARY, "nested": {"deep": [{"secret": SECRET_CANARY}]}},
    )
    results = [run("raw.baseline", store_dir, RecordingSend(leaky))]
    error = RuntimeError(f"transport failed token={SECRET_CANARY} sig={SIGNATURE_CANARY}")
    results.append(run("raw.wrong_chain", store_dir, RecordingSend(error=error)))
    body = json.dumps({"code": f"unknown {SECRET_CANARY}", "message": SIGNATURE_CANARY}).encode()
    results.append(run("raw.wrong_to", store_dir, RecordingSend(Reply(400, "application/json", body))))

    def leaking_decoder(raw: bytes) -> dict:
        raise ValueError(f"cannot decode {SIGNED_CANARY}")

    results.append(run("raw.post_removal", store_dir, RecordingSend(leaky), decoder=leaking_decoder))
    printed = capsys.readouterr()
    surfaces = [all_saved_text(store_dir), printed.out, printed.err, caplog.text]
    surfaces += [repr(r) for r in results] + [str(r) for r in results]
    for canary in CANARIES:
        assert all(canary not in surface for surface in surfaces), canary
    assert results[1].reason == "SEND_FAILED"
    assert results[2].outcome is Outcome.UNKNOWN
    assert results[3].outcome is Outcome.BREACH


def test_capture_failure_is_unknown_and_stops(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allow_baseline(store_dir)
    real_write = AttemptStore.write_capture

    def failing_write(self, specimen_id, record):  # noqa: ANN001
        raise OSError("capture disk failure")

    monkeypatch.setattr(AttemptStore, "write_capture", failing_write)
    result = run("raw.wrong_chain", store_dir, RecordingSend(code_reply(400, "synthetic_policy_violation")))
    assert result.outcome is Outcome.UNKNOWN
    assert result.reason == "CAPTURE_FAILED"
    monkeypatch.setattr(AttemptStore, "write_capture", real_write)
    assert AttemptStore(store_dir).state("raw.wrong_chain") is AttemptState.INTENT_SAVED
    send = RecordingSend(code_reply(400, "synthetic_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.wrong_to", store_dir, send)
    assert caught.value.code == "STOPPED_AFTER_BREACH"
    assert send.requests == []


# ---------------------------------------------------------------- 6 classification


@pytest.mark.parametrize(
    "reply,reason",
    [
        (Reply(403, "text/html", b"<html>Cloudflare 1010</html>"), "NON_JSON"),
        (Reply(403, "application/json", b'{"error":"forbidden"}'), "UNRECOGNIZED_REPLY"),
        (Reply(400, "application/json", b"{not json"), "MALFORMED_JSON"),
        (Reply(400, "application/json", b'["synthetic_policy_violation"]'), "UNRECOGNIZED_REPLY"),
        (Reply(400, "application/json", b'{"code":"policy_violation"}'), "UNRECOGNIZED_REPLY"),
        (Reply(400, "application/json", b'{"code":"simulation_failed"}'), "UNRECOGNIZED_REPLY"),
        (Reply(200, "application/json", b'{"data":{}}'), "MALFORMED_SUCCESS"),
    ],
)
def test_generic_and_malformed_replies_are_unknown(store_dir: Path, reply: Reply, reason: str) -> None:
    allow_baseline(store_dir)
    result = run("raw.wrong_chain", store_dir, RecordingSend(reply))
    assert result.outcome is Outcome.UNKNOWN
    assert result.reason == reason
    assert result.matches_expectation is False


def test_synthetic_codes_classify(store_dir: Path) -> None:
    allow_baseline(store_dir)
    policy = run("raw.wrong_chain", store_dir, RecordingSend(code_reply(400, "synthetic_policy_violation")))
    assert (policy.outcome, policy.matches_expectation) == (Outcome.POLICY_DENY, True)
    authz = run("raw.foreign_wallet", store_dir, RecordingSend(code_reply(403, "synthetic_wallet_not_authorized")))
    assert (authz.outcome, authz.matches_expectation) == (Outcome.AUTHORIZATION_DENY, True)
    schema = run("raw.gas_limit", store_dir, RecordingSend(code_reply(400, "synthetic_invalid_field")))
    assert (schema.outcome, schema.matches_expectation) == (Outcome.SCHEMA_REJECTED, False)
    expiry = run("raw.request_expiry", store_dir, RecordingSend(code_reply(400, "synthetic_request_expired")))
    assert (expiry.outcome, expiry.reason, expiry.matches_expectation) == (Outcome.UNKNOWN, "EXPIRY_REFUSAL", True)
    diagnostic = run("raw.data_hex_case", store_dir, RecordingSend(success_reply(signed_fields())))
    assert (diagnostic.outcome, diagnostic.matches_expectation) == (Outcome.ALLOW, True)
    misplaced = run("raw.wrong_to", store_dir, RecordingSend(code_reply(403, "synthetic_wallet_not_authorized")))
    assert (misplaced.outcome, misplaced.matches_expectation) == (Outcome.AUTHORIZATION_DENY, False)


def test_negative_refused_before_positive_control(store_dir: Path) -> None:
    send = RecordingSend(code_reply(400, "synthetic_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.wrong_chain", store_dir, send)
    assert caught.value.code == "POSITIVE_CONTROL_NOT_QUALIFIED"
    assert send.requests == []
    unknown = run("raw.baseline", store_dir, RecordingSend(Reply(403, "text/html", b"blocked")))
    assert unknown.outcome is Outcome.UNKNOWN
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.wrong_chain", store_dir, send)
    assert caught.value.code == "POSITIVE_CONTROL_NOT_QUALIFIED"
    assert send.requests == []


def test_profiles_do_not_gate_each_other(store_dir: Path) -> None:
    allow_baseline(store_dir, "raw")
    send = RecordingSend(code_reply(400, "synthetic_policy_violation"))
    with pytest.raises(SpecimenRefused) as caught:
        run("decoded.fee_bps", store_dir, send)
    assert caught.value.code == "POSITIVE_CONTROL_NOT_QUALIFIED"
    allow_baseline(store_dir, "decoded")
    assert run("decoded.fee_bps", store_dir, send).outcome is Outcome.POLICY_DENY
    assert AttemptStore(store_dir).state("raw.fee_bps") is AttemptState.NOT_SENT


@pytest.mark.parametrize(
    "field,value",
    [("wallet", WALLET_B), ("chain_id", 10143), ("type", 4), ("data", BASELINE_DATA[:-2] + "19"),
     ("nonce", 1), ("gas_limit", 300001), ("max_fee_per_gas", 1), ("max_priority_fee_per_gas", 1), ("value", 1)],
)
def test_decoded_mismatch_is_breach(store_dir: Path, field: str, value: object) -> None:
    result = run("raw.baseline", store_dir, RecordingSend(success_reply(signed_fields(**{field: value}))))
    assert result.outcome is Outcome.BREACH
    assert result.reason == "SIGNED_FIELDS_MISMATCH"
    assert (store_dir / "STOP.json").exists()


def test_case_only_hex_difference_is_not_mismatch(store_dir: Path) -> None:
    result = run("raw.baseline", store_dir, RecordingSend(success_reply(signed_fields(
        to=ENTRYPOINT.lower(), data="0x" + BASELINE_DATA[2:].upper()))))
    assert result.outcome is Outcome.ALLOW


def test_decode_failure_on_expected_allow_is_unknown(store_dir: Path) -> None:
    def broken(raw: bytes) -> dict:
        raise ValueError("bad rlp")

    result = run("raw.baseline", store_dir, RecordingSend(success_reply(signed_fields())), decoder=broken)
    assert (result.outcome, result.reason) == (Outcome.UNKNOWN, "DECODE_FAILED")


def test_stop_after_breach(store_dir: Path) -> None:
    allow_baseline(store_dir)
    allow_baseline(store_dir, "decoded")
    breach = run("raw.wrong_chain", store_dir, RecordingSend(success_reply(signed_fields(chain_id=10143))))
    assert (breach.outcome, breach.reason) == (Outcome.BREACH, "ALLOWED_WHERE_DENIAL_REQUIRED")
    stop = json.loads((store_dir / "STOP.json").read_text())
    assert stop["specimen_id"] == "raw.wrong_chain"
    for sid in ("raw.wrong_to", "decoded.fee_bps"):
        send = RecordingSend(code_reply(400, "synthetic_policy_violation"))
        with pytest.raises(SpecimenRefused) as caught:
            run(sid, store_dir, send)
        assert caught.value.code == "STOPPED_AFTER_BREACH"
        assert send.requests == []


def test_personal_sign_success_is_breach(store_dir: Path) -> None:
    allow_baseline(store_dir)
    body = json.dumps({"method": "personal_sign", "data": {"signature": "0x" + "ab" * 65, "encoding": "hex"}}).encode()
    result = run("raw.personal_sign", store_dir, RecordingSend(Reply(200, "application/json", body)))
    assert result.outcome is Outcome.BREACH
    assert ("ab" * 65) not in all_saved_text(store_dir)


def test_actual_profile_refused() -> None:
    with pytest.raises(evidence.ProfileUnqualified):
        evidence.ReplyProfile(qualification="QUALIFIED")
    assert evidence.SYNTHETIC_PROFILE.qualification == "SYNTHETIC"


# ---------------------------------------------------------------- actual-run refusal and import safety


def test_actual_mode_refused(store_dir: Path) -> None:
    send = RecordingSend(success_reply(signed_fields()))
    with pytest.raises(SpecimenRefused) as caught:
        run("raw.baseline", store_dir, send, run_mode="ACTUAL")
    assert caught.value.code == "ACTUAL_RUN_REFUSED"
    assert send.requests == []
    assert list(store_dir.iterdir()) == []


@pytest.mark.parametrize("module", ["specimens", "evidence"])
def test_module_run_refused(module: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "-s", "-m", f"scripts.privy_unfunded_proof.{module}"],
        cwd=CHECKOUT_ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 2
    assert completed.stderr.strip() == "refused: local synthetic driver has no actual runner"


def test_import_makes_no_network_or_process_call() -> None:
    code = """
import sys
events = []
def hook(event, args):
    if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn")):
        events.append(event)
sys.addaudithook(hook)
import scripts.privy_unfunded_proof.specimens
import scripts.privy_unfunded_proof.evidence
print(sorted(set(events)))
"""
    completed = run_child(code)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"
