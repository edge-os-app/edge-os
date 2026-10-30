"""The binding-fill assembler and the checked binding reads for the in-app WMON -> MOE release.

Pure: no database, socket, provider, signer or credential. Every chain record below is a test fake, built here by
hand from the release facts, so the expected requests do not come from the module under test. The real records
come from the controller's later read pass (see `docs/qualification/inapp-trade/BINDING_PROOFS.md`).
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import socket
from pathlib import Path

import pytest

from edge_os_api.execution import inapp_binding_fill as bf
from edge_os_api.execution import inapp_trade_release as inapp
from edge_os_api.execution.operating_release import ReleaseRefused, release_sha256

from execution.test_inapp_trade_release import AUTHORED_PATH, ENTRYPOINT, MOE, POOL, WALLET, WMON, authored, fill, identity

INPUT_RAW = 10 * 10**18
BUDGET_RAW = 169680000000000000
BLOCK = 0x6E7E3BD
BLOCK_TIME = 1_780_000_000
READ_AT = "2026-05-28T20:26:50Z"  # BLOCK_TIME + 10 s
WALLET_WORD = "0" * 24 + WALLET[2:].lower()
ENTRY_WORD = "0" * 24 + ENTRYPOINT[2:].lower()


def word(value: int) -> str:
    return "0x" + f"{value:064x}"


def address_word(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def request_hash(method: str, params) -> str:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def expected_requests(tag: str) -> list[tuple[str, str, list]]:
    """The eleven reads, written out from the release facts."""
    call = lambda to, data: [{"to": to, "data": data}, tag]  # noqa: E731
    return [
        ("binding.chain_id", "eth_chainId", []),
        ("binding.finalized_block", "eth_getBlockByNumber", ["finalized", False]),
        ("binding.wmon_decimals", "eth_call", call(WMON, "0x313ce567")),
        ("binding.moe_decimals", "eth_call", call(MOE, "0x313ce567")),
        ("binding.wmon_balance", "eth_call", call(WMON, "0x70a08231" + WALLET_WORD)),
        ("binding.moe_balance", "eth_call", call(MOE, "0x70a08231" + WALLET_WORD)),
        ("binding.native_balance", "eth_getBalance", [WALLET, tag]),
        ("binding.wmon_allowance", "eth_call", call(WMON, "0xdd62ed3e" + WALLET_WORD + ENTRY_WORD)),
        ("binding.pool_token0", "eth_call", call(POOL, "0x0dfe1681")),
        ("binding.pool_token1", "eth_call", call(POOL, "0xd21220a7")),
        ("binding.pool_reserves", "eth_call", call(POOL, "0x0902f1ac")),
    ]


def results(**changes):
    value = {
        "binding.chain_id": "0x8f",
        "binding.finalized_block": {"number": hex(BLOCK), "hash": "0x" + "ab" * 32, "timestamp": hex(BLOCK_TIME)},
        "binding.wmon_decimals": word(18), "binding.moe_decimals": word(18),
        "binding.wmon_balance": word(12 * 10**18), "binding.moe_balance": word(7),
        "binding.native_balance": hex(5 * 10**17), "binding.wmon_allowance": word(0),
        "binding.pool_token0": address_word(WMON), "binding.pool_token1": address_word(MOE),
        "binding.pool_reserves": "0x" + f"{4000 * 10**18:064x}" + f"{9_000_000 * 10**18:064x}" + f"{BLOCK_TIME - 5:064x}",
    }
    value.update(changes)
    return value


def records(values=None, tag: str = hex(BLOCK)) -> dict:
    values = results() if values is None else values
    ops = []
    for op_id, method, params in expected_requests(tag):
        ops.append({"op_id": op_id, "method": method, "expect": "RESULT", "params": params,
                    "request_sha256": request_hash(method, params), "status": "RESULT",
                    "result": values[op_id], "error": None, "at": READ_AT})
    return {"schema": "edge-os.inapp-binding-reads-records/1", "operations": ops}


def raw(value) -> bytes:
    return json.dumps(value, indent=1).encode("utf-8")


def build(store=None, release_fill=None) -> bytes:
    return bf.build_reads_artifact(authored(), fill() if release_fill is None else release_fill,
                                   raw(records() if store is None else store))


def refused(code: str, store=None, release_fill=None) -> None:
    with pytest.raises(bf.BindingFillRefused) as error:
        build(store, release_fill)
    assert error.value.code == code


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


# ---------------------------------------------------------------- the read plan

def test_plan_names_the_exact_eleven_reads_at_one_placeholder_block():
    plan = bf.read_plan(authored(), fill())
    assert [(r["op_id"], r["method"], r["params"]) for r in plan] == [
        (op, method, params) for op, method, params in expected_requests("<FINALIZED_BLOCK>")]
    assert all(r["expect"] == "RESULT" for r in plan)


# ---------------------------------------------------------------- binding reads: pass

def test_checked_reads_produce_a_canonical_artifact_bound_to_the_records_and_release():
    store_bytes = raw(records())
    artifact_bytes = bf.build_reads_artifact(authored(), fill(), store_bytes)
    artifact = json.loads(artifact_bytes)
    assert artifact_bytes == json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    release = inapp.complete_release(authored(), fill())
    assert artifact["schema"] == "edge-os.inapp-binding-reads/1"
    assert artifact["release_sha256"] == release_sha256(release)
    assert artifact["reads_sha256"] == hashlib.sha256(store_bytes).hexdigest()
    assert artifact["chain_id"] == 143 and artifact["fills_slot"] is None
    assert artifact["block"] == {"number": BLOCK, "hash": "0x" + "ab" * 32, "timestamp": BLOCK_TIME, "read_at": READ_AT}
    assert artifact["wallet_address"] == WALLET
    assert artifact["findings"] == {
        "wmon": {"token": WMON, "decimals": 18, "balance_raw": str(12 * 10**18), "allowance_to_entrypoint_raw": "0"},
        "moe": {"token": MOE, "decimals": 18, "balance_raw": "7"},
        "native": {"balance_raw": str(5 * 10**17)},
        "pool": {"address": POOL, "token0": WMON, "token1": MOE, "reserve0_raw": str(4000 * 10**18),
                 "reserve1_raw": str(9_000_000 * 10**18), "block_timestamp_last": BLOCK_TIME - 5}}
    assert artifact["checks"] == {
        "wmon_balance_covers_input": {"required_raw": str(INPUT_RAW), "result": True},
        "native_balance_covers_gas_budget": {"required_raw": str(BUDGET_RAW), "result": True}}
    assert artifact["shows"] and artifact["does_not_show"]
    digest = bf.verify_reads_artifact(authored(), fill(), store_bytes, artifact_bytes)
    assert digest == hashlib.sha256(artifact_bytes).hexdigest()


def test_balances_exactly_at_the_input_and_the_gas_budget_pass():
    build(records(results(**{"binding.wmon_balance": word(INPUT_RAW), "binding.native_balance": hex(BUDGET_RAW)})))


def test_a_reads_block_equal_to_the_release_reserves_block_passes():
    build(release_fill=fill(reserves={**fill()["reserves"], "block_number": BLOCK}))


# ---------------------------------------------------------------- binding reads: refusals

def test_a_block_below_the_release_reserves_read_is_stale():
    refused("READ_BLOCK_STALE", release_fill=fill(reserves={**fill()["reserves"], "block_number": BLOCK + 1}))


def test_a_finalized_block_older_than_the_input_age_at_its_read_is_stale():
    block = {"number": hex(BLOCK), "hash": "0x" + "ab" * 32, "timestamp": hex(BLOCK_TIME - 51)}  # 61 s before
    refused("READ_BLOCK_STALE", records(results(**{"binding.finalized_block": block})))
    block["timestamp"] = hex(BLOCK_TIME - 50)  # exactly 60 s
    build(records(results(**{"binding.finalized_block": block})))


def test_a_pass_longer_than_the_input_age_is_stale():
    store = records()
    store["operations"][-1]["at"] = "2026-05-28T20:27:51Z"  # 61 s after the first read
    refused("READ_BLOCK_STALE", store)


def test_a_block_after_its_own_read_time_or_reads_out_of_time_order_refuse():
    block = {"number": hex(BLOCK), "hash": "0x" + "ab" * 32, "timestamp": hex(BLOCK_TIME + 11)}
    refused("READ_MALFORMED", records(results(**{"binding.finalized_block": block})))
    store = records()
    store["operations"][5]["at"] = "2026-05-28T20:26:49Z"
    refused("READ_MALFORMED", store)


def test_a_wmon_balance_below_the_input_refuses():
    refused("BALANCE_BELOW_INPUT", records(results(**{"binding.wmon_balance": word(INPUT_RAW - 1)})))


def test_a_native_balance_below_the_gas_budget_refuses():
    refused("NATIVE_BELOW_GAS_BUDGET", records(results(**{"binding.native_balance": hex(BUDGET_RAW - 1)})))


@pytest.mark.parametrize("op_id", ["binding.wmon_decimals", "binding.moe_decimals"])
@pytest.mark.parametrize("decimals", [0, 6, 17, 19])
def test_wrong_token_decimals_refuse(op_id, decimals):
    refused("READ_DECIMALS_MISMATCH", records(results(**{op_id: word(decimals)})))


def test_wrong_chain_refuses():
    refused("READ_WRONG_CHAIN", records(results(**{"binding.chain_id": "0x279f"})))


@pytest.mark.parametrize("change", [{"binding.pool_token0": address_word(MOE)},
                                    {"binding.pool_token1": address_word(WMON)},
                                    {"binding.pool_token0": address_word("0x" + "1" * 40)}])
def test_a_pool_other_than_the_release_pool_order_refuses(change):
    refused("READ_POOL_MISMATCH", records(results(**change)))


@pytest.mark.parametrize("status", ["RPC_ERROR", "REPLY_LOST", "SKIPPED"])
@pytest.mark.parametrize("op_id", ["binding.wmon_balance", "binding.native_balance", "binding.wmon_allowance",
                                   "binding.finalized_block", "binding.pool_reserves"])
def test_an_unread_value_is_unavailable_never_zero(op_id, status):
    store = records()
    record = next(r for r in store["operations"] if r["op_id"] == op_id)
    record.update(status=status, result=None, error={"code": -32000} if status == "RPC_ERROR" else None)
    refused("READ_UNAVAILABLE", store)


def test_a_result_with_an_error_or_a_null_result_is_unavailable():
    store = records()
    store["operations"][4]["error"] = {"code": -32000}
    refused("READ_UNAVAILABLE", store)
    store = records()
    store["operations"][4]["result"] = None
    refused("READ_UNAVAILABLE", store)


@pytest.mark.parametrize("op_id,value", [
    ("binding.wmon_balance", "0x"), ("binding.wmon_balance", "0x" + "0" * 63),
    ("binding.wmon_balance", 12), ("binding.native_balance", "0x01"), ("binding.native_balance", "12"),
    ("binding.moe_balance", word(1) + "00"), ("binding.wmon_allowance", "0xZZ" + "0" * 62),
    ("binding.pool_reserves", word(1) + word(1)), ("binding.pool_reserves", "0x" + "0" * 64 + f"{1:064x}" + "0" * 64),
    ("binding.chain_id", 143), ("binding.finalized_block", {"number": hex(BLOCK), "hash": "0x12"}),
    ("binding.finalized_block", {"number": hex(BLOCK), "hash": "0x" + "ab" * 32, "timestamp": "0x"}),
    ("binding.finalized_block", "0x1")])
def test_a_malformed_value_refuses(op_id, value):
    refused("READ_MALFORMED", records(results(**{op_id: value})))


def test_a_read_at_another_block_or_with_edited_params_refuses():
    store = records()
    store["operations"][4]["params"][1] = hex(BLOCK - 1)
    store["operations"][4]["request_sha256"] = request_hash("eth_call", store["operations"][4]["params"])
    refused("READS_RECORD_MISMATCH", store)
    store = records()
    store["operations"][6]["params"][0] = "0x" + "9" * 40
    store["operations"][6]["request_sha256"] = request_hash("eth_getBalance", store["operations"][6]["params"])
    refused("READS_RECORD_MISMATCH", store)
    store = records(tag="latest")
    refused("READS_RECORD_MISMATCH", store)


def test_an_edited_request_hash_refuses():
    store = records()
    store["operations"][4]["request_sha256"] = "0" * 64
    refused("READS_RECORD_MISMATCH", store)


@pytest.mark.parametrize("change", [
    lambda s: s.update(extra=1),
    lambda s: s.update(schema="edge-os.inapp-control-proof-chain-results/1"),
    lambda s: s["operations"][3].update(note="x"),
    lambda s: s["operations"][3].pop("at"),
    lambda s: s["operations"].pop(),
    lambda s: s["operations"].append(copy.deepcopy(s["operations"][0])),
    lambda s: s["operations"].reverse(),
    lambda s: s["operations"][2].update(method="eth_getStorageAt"),
    lambda s: s["operations"][2].update(expect="RPC_ERROR"),
    lambda s: s["operations"][2].update(at="2026-05-28 20:26:50"),
    lambda s: s.update(operations={}),
])
def test_an_unknown_missing_or_reordered_field_refuses(change):
    store = records()
    change(store)
    with pytest.raises(bf.BindingFillRefused) as error:
        build(store)
    assert error.value.code in ("READS_RECORDS_INVALID",)


def test_records_that_are_not_json_refuse():
    with pytest.raises(bf.BindingFillRefused, match="READS_RECORDS_INVALID"):
        bf.build_reads_artifact(authored(), fill(), b"not json")
    with pytest.raises(bf.BindingFillRefused, match="READS_RECORDS_INVALID"):
        bf.build_reads_artifact(authored(), fill(), b'{"schema": NaN}')


def test_an_invalid_release_fill_refuses_with_the_release_code():
    with pytest.raises(ReleaseRefused, match="INAPP_FILL_INVALID"):
        build(release_fill={})


def test_an_edited_record_or_artifact_after_the_build_refuses():
    store_bytes = raw(records())
    artifact_bytes = bf.build_reads_artifact(authored(), fill(), store_bytes)
    edited = records(results(**{"binding.moe_balance": word(8)}))
    with pytest.raises(bf.BindingFillRefused, match="READS_ARTIFACT_MISMATCH"):
        bf.verify_reads_artifact(authored(), fill(), raw(edited), artifact_bytes)
    artifact = json.loads(artifact_bytes)
    artifact["findings"]["wmon"]["balance_raw"] = str(100 * 10**18)
    tampered = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(bf.BindingFillRefused, match="READS_ARTIFACT_MISMATCH"):
        bf.verify_reads_artifact(authored(), fill(), store_bytes, tampered)
    with pytest.raises(bf.BindingFillRefused, match="READS_ARTIFACT_MISMATCH"):
        bf.verify_reads_artifact(authored(), fill(), store_bytes, artifact_bytes + b"\n")
    other_fill = fill(valid_until="2026-10-24T00:00:01Z")
    with pytest.raises(bf.BindingFillRefused, match="READS_ARTIFACT_MISMATCH"):
        bf.verify_reads_artifact(authored(), other_fill, store_bytes, artifact_bytes)


# ---------------------------------------------------------------- binding fill assembler

def proof(slot: str, release_digest: str | None = None, **extra) -> bytes:
    digest = release_digest or release_sha256(inapp.complete_release(authored(), fill()))
    value = {"schema": "edge-os.test-binding-proof/1", "proof": slot, "release_sha256": digest, **extra}
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


REQUIRED = {slot: proof(slot) for slot in ("position_inventory", "market", "finality")}
PROFILE = {"source_id": "test-source", "delivery_profile_sha256": "c" * 64, "finality": "finalized",
           "warmup_buckets": 3, "max_collection_age_seconds": 60}


def assemble(proofs=None, profile=None, ident=None):
    return bf.assemble_binding_fill(authored(), fill(), identity() if ident is None else ident,
                                    REQUIRED if proofs is None else proofs, profile)


def test_the_fragment_carries_the_file_hashes_and_binds_like_bind_release():
    result = assemble(profile=PROFILE)
    hashes = {slot: hashlib.sha256(data).hexdigest() for slot, data in REQUIRED.items()}
    assert result["proof_sha256"] == hashes
    assert result["binding_fill"] == {
        "identity": identity(), "position_inventory_proof_sha256": hashes["position_inventory"],
        "market_proof_sha256": hashes["market"], "finality_proof_sha256": hashes["finality"],
        "exit_capacity_proof_sha256": None, "valuation_proof_sha256": None, "cost_model_proof_sha256": None,
        "market_profile": PROFILE}
    release = inapp.complete_release(authored(), fill())
    assert result["binding_sha256"] == inapp.bind_release(release, result["binding_fill"]).sha256
    assert result["release_sha256"] == release_sha256(release)
    assert result["derive_approval_ready"] is False
    assert result["missing_for_derive_approval"] == ["cost_model", "exit_capacity", "valuation"]
    assert result["market_observation_ready"] is True


def test_all_six_proofs_make_the_fragment_ready_for_derive_approval():
    proofs = {**REQUIRED, **{slot: proof(slot) for slot in ("exit_capacity", "valuation", "cost_model")}}
    result = assemble(proofs)
    assert result["derive_approval_ready"] is True and result["missing_for_derive_approval"] == []
    assert result["market_observation_ready"] is False and result["binding_fill"]["market_profile"] is None


@pytest.mark.parametrize("slot", ["position_inventory", "market", "finality"])
def test_a_missing_required_proof_refuses(slot):
    proofs = dict(REQUIRED)
    proofs.pop(slot)
    with pytest.raises(bf.BindingFillRefused, match="FRAGMENT_REQUIRED_PROOF_MISSING"):
        assemble(proofs)


def test_an_unknown_slot_refuses():
    with pytest.raises(bf.BindingFillRefused, match="FRAGMENT_SLOT_INVALID"):
        assemble({**REQUIRED, "identity": proof("identity")})


@pytest.mark.parametrize("data", [
    proof("finality"),  # placed in the market slot below
    proof("market", release_digest="0" * 64),
    json.dumps({"proof": "market", "release_sha256": "0" * 64}, sort_keys=True, separators=(",", ":")).encode(),
    json.dumps({"schema": 1, "proof": "market"}, sort_keys=True, separators=(",", ":")).encode(),
    json.dumps(["market"]).encode(),
])
def test_an_artifact_for_another_slot_or_release_refuses(data):
    with pytest.raises(bf.BindingFillRefused, match="PROOF_ARTIFACT_MISMATCH"):
        assemble({**REQUIRED, "market": data})


def test_the_reads_artifact_fills_no_slot():
    reads = build()
    with pytest.raises(bf.BindingFillRefused, match="PROOF_ARTIFACT_MISMATCH"):
        assemble({**REQUIRED, "position_inventory": reads})


@pytest.mark.parametrize("data", [proof("market") + b"\n", b'{"proof": "market"}', b"not json", b"\xff"])
def test_a_non_canonical_artifact_refuses(data):
    with pytest.raises(bf.BindingFillRefused, match="PROOF_ARTIFACT_NOT_CANONICAL"):
        assemble({**REQUIRED, "market": data})


@pytest.mark.parametrize("profile", [
    {**PROFILE, "finality": "latest"}, {**PROFILE, "max_collection_age_seconds": 61},
    {**PROFILE, "extra": 1}, {k: v for k, v in PROFILE.items() if k != "source_id"},
    {**PROFILE, "warmup_buckets": True}, {**PROFILE, "delivery_profile_sha256": "C" * 64}])
def test_a_market_profile_outside_the_binding_rules_refuses(profile):
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        assemble(profile=profile)


@pytest.mark.parametrize("ident", [
    {**identity(), "extra": "x"}, {**identity(), "wallet_address": WALLET.lower()},
    {k: v for k, v in identity().items() if k != "terms_hash"}])
def test_an_identity_outside_the_binding_rules_refuses(ident):
    with pytest.raises(ReleaseRefused, match="EXECUTION_RELEASE_INVALID"):
        assemble(ident=ident)


def test_a_non_object_identity_refuses():
    with pytest.raises(ReleaseRefused, match="INAPP_BINDING_FILL_INVALID"):
        assemble(ident=[])


# ---------------------------------------------------------------- command

def write(path: Path, data) -> str:
    path.write_bytes(data if type(data) is bytes else json.dumps(data).encode())
    return str(path)


def test_command_plan_reads_and_verify(tmp_path, capsys):
    fill_path = write(tmp_path / "fill.json", fill())
    base = ["--authored", str(AUTHORED_PATH), "--fill", fill_path]
    assert bf.main(["plan", *base]) == 0
    assert json.loads(capsys.readouterr().out)["reads"] == bf.read_plan(authored(), fill())
    store_path = write(tmp_path / "binding_reads.json", raw(records()))
    out = tmp_path / "binding_reads.proof.json"
    assert bf.main(["reads", *base, "--records", store_path, "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "CHECKED"
    assert printed["reads_artifact_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert out.read_bytes() == bf.build_reads_artifact(authored(), fill(), raw(records()))
    assert bf.main(["reads", *base, "--records", store_path, "--out", str(out)]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "OUTPUT_EXISTS"}
    assert bf.main(["verify-reads", *base, "--records", store_path, "--artifact", str(out)]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "VERIFIED",
                                                   "reads_artifact_sha256": printed["reads_artifact_sha256"]}
    low = write(tmp_path / "low.json", raw(records(results(**{"binding.wmon_balance": word(1)}))))
    assert bf.main(["reads", *base, "--records", low]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "BALANCE_BELOW_INPUT"}
    assert bf.main(["reads", *base, "--records", str(tmp_path / "absent.json")]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "INAPP_FILE_UNREADABLE"}


def test_command_fragment_prints_hashes_and_the_binding_fill(tmp_path, capsys):
    base = ["--authored", str(AUTHORED_PATH), "--fill", write(tmp_path / "fill.json", fill())]
    args = ["fragment", *base, "--identity", write(tmp_path / "identity.json", identity()),
            "--market-profile", write(tmp_path / "profile.json", PROFILE)]
    for slot, data in REQUIRED.items():
        args += ["--proof", f"{slot}={write(tmp_path / (slot + '.json'), data)}"]
    out = tmp_path / "binding.fill.json"
    assert bf.main([*args, "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    expected = assemble(profile=PROFILE)
    assert printed == {"status": "ASSEMBLED", **expected}
    assert json.loads(out.read_bytes()) == expected["binding_fill"]
    release = inapp.complete_release(authored(), fill())
    assert inapp.bind_release(release, json.loads(out.read_bytes())).sha256 == printed["binding_sha256"]
    assert bf.main([*args, "--proof", f"market={tmp_path / 'market.json'}"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "FRAGMENT_SLOT_INVALID"}
    assert bf.main([*args, "--proof", "nonsense"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "REFUSED", "code": "FRAGMENT_SLOT_INVALID"}


def test_the_module_imports_no_network_signing_or_provider_code():
    tree = ast.parse(Path(bf.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {f"{node.module}.{alias.name}" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                 for alias in node.names}
    assert imported == {
        "__future__.annotations", "argparse", "datetime", "hashlib", "json", "re", "sys",
        "collections.abc.Mapping", "collections.abc.Sequence", "pathlib.Path", "typing.Any",
        "edge_os_api.execution.inapp_trade_release.bind_release",
        "edge_os_api.execution.inapp_trade_release.complete_release",
        "edge_os_api.execution.operating_release.ReleaseRefused",
        "edge_os_api.execution.operating_release.release_sha256",
        "edge_os_api.execution.original_transaction.BALANCE_OF_SELECTOR",
        "edge_os_api.execution.original_transaction.DECIMALS_SELECTOR",
        "edge_os_api.execution.transaction_rpc_client.json_bytes"}
