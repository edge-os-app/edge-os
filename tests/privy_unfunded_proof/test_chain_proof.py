"""Read-only chain operations for the in-app trade control proofs. Recorded fakes only; no network."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from edge_os_api.execution.direct_route_quote_client import DirectRoutePins, build_calldata_hex
from scripts.privy_unfunded_proof import chain_proof
from scripts.privy_unfunded_proof.chain_proof import ChainRefused, ReadOnlyChainClient

from tests.privy_unfunded_proof._control_support import (
    AUTHORED_PATH,
    FakeChain,
    chain_client,
    pool_output,
    recorded_chain,
)

CLOCK = "2026-10-24T00:00:00Z"
MODULE = Path(chain_proof.__file__)


def _authored() -> dict:
    return json.loads(AUTHORED_PATH.read_text(encoding="utf-8"))


def _by_id(records: list[dict]) -> dict[str, dict]:
    return {record["op_id"]: record for record in records}


# ---------------------------------------------------------------- frozen inputs equal the authored release


def test_frozen_chain_inputs_equal_the_authored_release() -> None:
    release = _authored()["release"]
    route, quote, gas = release["route"], release["quote"], release["gas"]
    assert chain_proof.WALLET == release["wallet_address"] == route["recipient"]
    assert chain_proof.ENTRYPOINT == route["entrypoint_address"]
    assert chain_proof.ROUTER == release["deployment"]["router_address"]
    assert chain_proof.WMON == route["input_asset"]["token_address"] == quote["token0_address"]
    assert chain_proof.MOE == route["output_asset"]["token_address"] == quote["token1_address"]
    assert chain_proof.POOL == quote["pool_address"]
    assert chain_proof.PROGRAM_HEX == route["approved_program_hex"]
    assert chain_proof.PROGRAM_FEE_PPM == quote["program_fee_ppm"]
    assert str(chain_proof.INPUT_RAW) == route["approved_input_raw"] == route["approved_allowance_raw"]
    assert chain_proof.SWAP_GAS_LIMIT == gas["gas_limit"]
    assert chain_proof.EXECUTE_SWAP_SELECTOR == route["selector"]
    assert chain_proof.release_inputs_match(_authored()) is True


def test_release_inputs_mismatch_is_detected() -> None:
    changed = _authored()
    changed["release"]["route"]["approved_input_raw"] = "9000000000000000000"
    assert chain_proof.release_inputs_match(changed) is False


def test_baseline_swap_calldata_is_the_app_built_calldata() -> None:
    release = _authored()["release"]
    route, quote = release["route"], release["quote"]
    pins = DirectRoutePins(endpoint="https://relay.example.test/rpc", pool_address=quote["pool_address"],
                           token0_address=quote["token0_address"], token1_address=quote["token1_address"],
                           direction=quote["direction"], program_fee_ppm=quote["program_fee_ppm"],
                           approved_program_hex=route["approved_program_hex"],
                           approved_input_raw=route["approved_input_raw"], approved_min_output_raw="123456789",
                           entrypoint_address=route["entrypoint_address"],
                           input_token=route["input_asset"]["token_address"],
                           output_token=route["output_asset"]["token_address"])
    assert chain_proof.swap_calldata(min_output_raw=123456789) == build_calldata_hex(pins)


def test_mutated_swap_calldata_changes_only_the_named_word() -> None:
    base = chain_proof.swap_calldata(min_output_raw=7)
    words = lambda data: [data[10 + 64 * i: 10 + 64 * (i + 1)] for i in range((len(data) - 10) // 64)]  # noqa: E731
    cases = {
        0: chain_proof.swap_calldata(min_output_raw=7, buy=chain_proof.WMON),
        1: chain_proof.swap_calldata(min_output_raw=8),
        2: chain_proof.swap_calldata(min_output_raw=7, sell=chain_proof.MOE),
        3: chain_proof.swap_calldata(min_output_raw=7, amount=chain_proof.INPUT_RAW + 1),
    }
    for index, data in cases.items():
        changed = [i for i, (a, b) in enumerate(zip(words(base), words(data))) if a != b]
        assert changed == [index]
    fee = chain_proof.swap_calldata(min_output_raw=7, fee_bps=10001, fee_collector=chain_proof.SINK)
    assert [i for i, (a, b) in enumerate(zip(words(base), words(fee))) if a != b] == [4, 5]


# ---------------------------------------------------------------- no operation can move funds


def test_every_operation_is_a_read_only_method() -> None:
    assert set(chain_proof.READ_ONLY_METHODS) == {
        "eth_chainId", "eth_getBlockByNumber", "eth_getCode", "eth_call", "eth_estimateGas", "debug_traceCall"}
    for op_id in chain_proof.OPERATION_ORDER:
        assert chain_proof.OPERATIONS[op_id].method in chain_proof.READ_ONLY_METHODS


@pytest.mark.parametrize("method", ["eth_sendRawTransaction", "eth_sendTransaction", "eth_sign",
                                    "eth_signTransaction", "personal_sign", "eth_accounts",
                                    "debug_traceTransaction", "anvil_setBalance", "hardhat_impersonateAccount"])
def test_client_refuses_every_other_method_before_any_io(method: str) -> None:
    fake = FakeChain()
    with pytest.raises(ChainRefused) as caught:
        chain_client(fake).call(method, [])
    assert caught.value.code == "CHAIN_METHOD_NOT_ALLOWED"
    assert fake.requests == []


def test_client_has_no_send_path() -> None:
    assert not any(name.startswith("send") for name in dir(ReadOnlyChainClient))
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "eth_sendRawTransaction" not in strings
    assert "eth_sendTransaction" not in strings


@pytest.mark.parametrize("params", [
    [{"from": chain_proof.WALLET, "to": chain_proof.ENTRYPOINT, "value": "0x1", "data": "0x"}, "latest"],
    [{"to": chain_proof.ENTRYPOINT, "data": "0x", "nonce": "0x0"}, "latest"],
    [{"to": chain_proof.ENTRYPOINT, "data": "0x"}, "latest", {chain_proof.WMON: {"balance": "0x1"}}],
    [{"to": chain_proof.ENTRYPOINT, "data": "0x"}, "latest", {chain_proof.WMON: {"code": "0x00"}}],
    [{"to": chain_proof.ENTRYPOINT, "data": "0x"}, "pending"],
    [{"from": "0x" + "11" * 20, "to": chain_proof.ENTRYPOINT, "data": "0x"}, "latest"],
])
def test_client_refuses_value_unknown_fields_other_overrides_and_other_senders(params: list) -> None:
    fake = FakeChain()
    with pytest.raises(ChainRefused) as caught:
        chain_client(fake).call("eth_call", params)
    assert caught.value.code == "CHAIN_CALL_INVALID"
    assert fake.requests == []


def test_every_planned_request_uses_only_the_wallet_as_sender_and_zero_value() -> None:
    fake = FakeChain()
    chain_proof.run_chain_operations(chain_client(fake), clock=lambda: CLOCK)
    assert len(fake.requests) == len(chain_proof.OPERATION_ORDER)
    for wire in fake.requests:
        assert wire["method"] in chain_proof.READ_ONLY_METHODS
        params = wire["params"]
        if wire["method"] in ("eth_call", "eth_estimateGas", "debug_traceCall"):
            call = params[0]
            assert call.get("from", chain_proof.WALLET) == chain_proof.WALLET
            assert call.get("value", "0x0") == "0x0"
            assert call["to"].lower() in {chain_proof.ENTRYPOINT.lower(), chain_proof.WMON.lower(),
                                          chain_proof.POOL.lower()}
            if len(params) == 3:
                overrides = params[2]["stateOverrides"] if wire["method"] == "debug_traceCall" else params[2]
                assert overrides == chain_proof.STATE_OVERRIDES
                assert set(overrides) == {chain_proof.WMON}


def test_state_overrides_touch_only_the_wallet_wmon_balance_and_entrypoint_allowance() -> None:
    diff = chain_proof.STATE_OVERRIDES[chain_proof.WMON]["stateDiff"]
    assert set(diff) == {chain_proof.balance_slot(chain_proof.WALLET),
                         chain_proof.allowance_slot(chain_proof.WALLET, chain_proof.ENTRYPOINT)}
    assert int(diff[chain_proof.balance_slot(chain_proof.WALLET)], 16) == 2 * chain_proof.INPUT_RAW
    assert int(diff[chain_proof.allowance_slot(chain_proof.WALLET, chain_proof.ENTRYPOINT)], 16) == chain_proof.INPUT_RAW


# ---------------------------------------------------------------- recorded run


def test_recorded_run_follows_the_frozen_order_at_one_pinned_block() -> None:
    records = recorded_chain()
    assert [record["op_id"] for record in records] == list(chain_proof.OPERATION_ORDER)
    block_tags = {json.dumps(record["params"][1]) for record in records
                  if record["method"] in ("eth_getCode", "eth_call", "eth_estimateGas", "debug_traceCall")}
    assert block_tags == {json.dumps(hex(0x6D00000))}
    for record in records:
        assert record["request_sha256"] == chain_proof.request_sha256(record["method"], record["params"])
        assert record["at"] == CLOCK


def test_recorded_run_records_success_reverts_and_outputs() -> None:
    records = _by_id(recorded_chain())
    output = pool_output(chain_proof.INPUT_RAW)
    assert records["chain.swap_probe"]["status"] == "RESULT"
    assert int(records["chain.swap_probe"]["result"], 16) == output
    assert records["chain.swap_min_equal"]["params"][0]["data"] == chain_proof.swap_calldata(min_output_raw=output)
    assert records["chain.swap_min_above"]["params"][0]["data"] == chain_proof.swap_calldata(min_output_raw=output + 1)
    for op_id in ("chain.swap_min_above", "chain.swap_input_above_allowance", "chain.swap_wrong_output",
                  "chain.swap_wrong_input", "chain.swap_fee_over_bound"):
        assert records[op_id]["status"] == "RPC_ERROR"
        assert records[op_id]["error"]["reverted"] is True
        assert records[op_id]["result"] is None
    assert int(records["chain.swap_fee_charged"]["result"], 16) < output
    assert int(records["chain.estimate_swap"]["result"], 16) == 544_967
    assert records["chain.swap_at_release_gas"]["params"][0]["gas"] == hex(chain_proof.SWAP_GAS_LIMIT)
    assert records["chain.swap_trace"]["status"] == "RESULT"


def test_dependent_operations_are_skipped_without_a_baseline_output() -> None:
    fake = FakeChain(state_overrides_honoured=False)
    records = _by_id(chain_proof.run_chain_operations(chain_client(fake), clock=lambda: CLOCK))
    assert records["chain.swap_probe"]["status"] == "RPC_ERROR"
    for op_id in chain_proof.DEPENDS_ON_BASELINE:
        assert records[op_id]["status"] == "SKIPPED"
        assert records[op_id]["params"] is None
    assert len(fake.requests) == len(chain_proof.OPERATION_ORDER) - len(chain_proof.DEPENDS_ON_BASELINE)


def test_an_unsupported_trace_is_recorded_not_raised() -> None:
    records = _by_id(recorded_chain(debug_supported=False))
    assert records["chain.swap_trace"]["status"] == "RPC_ERROR"
    assert records["chain.swap_trace"]["error"]["reverted"] is False
    assert records["chain.swap_trace"]["error"]["code"] == -32601


def test_provider_error_text_and_the_endpoint_are_never_saved() -> None:
    fake = FakeChain(debug_supported=False)
    records = chain_proof.run_chain_operations(
        ReadOnlyChainClient(transport=fake, endpoint="https://rpc.example.test/secret-key-abc/rpc"),
        clock=lambda: CLOCK)
    text = json.dumps(records)
    assert "secret-key-abc" not in text
    assert "the method does not exist" not in text
    assert "execution reverted" not in text


# ---------------------------------------------------------------- operator command


def test_dry_run_lists_every_operation_without_reading_the_environment(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(chain_proof.RPC_URL_ENV, raising=False)
    assert chain_proof.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    for op_id in chain_proof.OPERATION_ORDER:
        assert op_id in out


def test_live_command_needs_a_new_store_and_the_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(chain_proof.RPC_URL_ENV, raising=False)
    assert chain_proof.main([]) == 2
    assert "STORE_REQUIRED" in capsys.readouterr().out
    existing = tmp_path / "exists"
    existing.mkdir()
    assert chain_proof.main(["--store", str(existing)]) == 2
    assert "STORE_ALREADY_EXISTS" in capsys.readouterr().out
    assert chain_proof.main(["--store", str(tmp_path / "new")]) == 2
    assert "RPC_URL_MISSING" in capsys.readouterr().out
    assert not (tmp_path / "new").exists()


def test_live_command_writes_one_results_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeChain()
    monkeypatch.setenv(chain_proof.RPC_URL_ENV, "https://rpc.example.test/rpc")
    monkeypatch.setattr(chain_proof, "_transport", lambda: fake)
    store = tmp_path / "chain-store"
    assert chain_proof.main(["--store", str(store)]) == 0
    saved = json.loads((store / chain_proof.RESULTS_FILE).read_text(encoding="utf-8"))
    assert saved["schema"] == chain_proof.RESULTS_SCHEMA
    assert [record["op_id"] for record in saved["operations"]] == list(chain_proof.OPERATION_ORDER)
    assert "rpc.example.test" not in (store / chain_proof.RESULTS_FILE).read_text(encoding="utf-8")
    assert chain_proof.main(["--store", str(store)]) == 2
