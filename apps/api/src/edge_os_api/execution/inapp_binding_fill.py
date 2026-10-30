"""Assemble the in-app release's binding fill and check the chain reads its proofs cite. Pure; file reads only.

Two parts, both from `docs/qualification/inapp-trade/BINDING_PROOFS.md`:

- `build_reads_artifact` checks the controller's recorded reads at one finalized block (balances, decimals,
  allowance and pool) against the completed release, and returns one canonical, hashed artifact. It fills no proof
  slot: what each proof must contain is still a builder decision (`CLOUD_BINDING_PROOFS_STATUS.md`).
- `assemble_binding_fill` hashes proof artifact files into the step-6 `binding.fill.json` and binds it with
  `bind_release`, so every identity and `market_profile` rule stays the binding's own.

Nothing here reads a network, a key or a database, or adds authority. A value that was not read is refused, never
taken as zero.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from edge_os_api.execution.inapp_trade_release import bind_release, complete_release
from edge_os_api.execution.operating_release import ReleaseRefused, release_sha256
from edge_os_api.execution.original_transaction import BALANCE_OF_SELECTOR, DECIMALS_SELECTOR
from edge_os_api.execution.transaction_rpc_client import json_bytes

RECORDS_SCHEMA = "edge-os.inapp-binding-reads-records/1"
ARTIFACT_SCHEMA = "edge-os.inapp-binding-reads/1"
RECORD_FIELDS = frozenset({"op_id", "method", "expect", "params", "request_sha256", "status", "result", "error", "at"})
STATUSES = frozenset({"RESULT", "RPC_ERROR", "REPLY_LOST", "SKIPPED"})
ALLOWANCE_SELECTOR = "0xdd62ed3e"
TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"
RESERVES_SELECTOR = "0x0902f1ac"
BLOCK_PLACEHOLDER = "<FINALIZED_BLOCK>"
SLOTS = ("position_inventory", "market", "finality", "exit_capacity", "valuation", "cost_model")
REQUIRED_SLOTS = ("position_inventory", "market", "finality")  # `BoundRelease` requires these three
APPROVAL_SLOTS = ("position_inventory", "exit_capacity", "valuation", "cost_model")  # `derive_approval` requires these
SHOWS = (
    "The chain id, and the finalized block number, hash and timestamp, as the observer reported them.",
    "At that block: the wallet's WMON, MOE and native balances, its WMON allowance to the entrypoint, both token "
    "decimals, and the pool's token order and reserves.",
    "The WMON balance covers the release input and the native balance covers the release gas budget at that block.",
)
DOES_NOT_SHOW = (
    "That the block is final on Monad: only that the observer named it finalized.",
    "That the balances belong to any position, or that any position inventory, exit capacity, valuation or cost "
    "model is qualified.",
    "That the state still holds when the release is signed or sent.",
    "Anything about the market source or its delivery profile.",
)

_QUANTITY = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)")
_WORDS = re.compile(r"0x((?:[0-9a-fA-F]{64})+)")
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class BindingFillRefused(Exception):
    """A refusal with one fixed code and no input value in its message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def request_sha256(method: str, params: Any) -> str:
    """The rule of the committed chain store (`scripts/privy_unfunded_proof/chain_proof.request_sha256`)."""
    return hashlib.sha256(json_bytes({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})).hexdigest()


def _word_of(address: str) -> str:
    return "0" * 24 + address[2:].lower()


def _requests(content: Mapping[str, Any], tag: str) -> list[tuple[str, str, list[Any]]]:
    route, quote = content["route"], content["quote"]
    wallet = content["wallet_address"]
    wmon, moe = route["input_asset"]["token_address"].lower(), route["output_asset"]["token_address"].lower()
    pool = quote["pool_address"].lower()

    def call(to: str, data: str) -> list[Any]:
        return [{"to": to, "data": data}, tag]

    return [
        ("binding.chain_id", "eth_chainId", []),
        ("binding.finalized_block", "eth_getBlockByNumber", ["finalized", False]),
        ("binding.wmon_decimals", "eth_call", call(wmon, DECIMALS_SELECTOR)),
        ("binding.moe_decimals", "eth_call", call(moe, DECIMALS_SELECTOR)),
        ("binding.wmon_balance", "eth_call", call(wmon, BALANCE_OF_SELECTOR + _word_of(wallet))),
        ("binding.moe_balance", "eth_call", call(moe, BALANCE_OF_SELECTOR + _word_of(wallet))),
        ("binding.native_balance", "eth_getBalance", [wallet, tag]),
        ("binding.wmon_allowance", "eth_call",
         call(wmon, ALLOWANCE_SELECTOR + _word_of(wallet) + _word_of(route["entrypoint_address"]))),
        ("binding.pool_token0", "eth_call", call(pool, TOKEN0_SELECTOR)),
        ("binding.pool_token1", "eth_call", call(pool, TOKEN1_SELECTOR)),
        ("binding.pool_reserves", "eth_call", call(pool, RESERVES_SELECTOR)),
    ]


def read_plan(authored: Mapping[str, Any], fill: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The exact reads the controller runs, in order. Every block-bound read names the finalized block's number."""
    content = complete_release(authored, fill).content()
    return [{"op_id": op_id, "method": method, "expect": "RESULT", "params": params}
            for op_id, method, params in _requests(content, BLOCK_PLACEHOLDER)]


def _quantity(value: Any) -> int:
    if type(value) is not str or _QUANTITY.fullmatch(value) is None:
        raise BindingFillRefused("READ_MALFORMED")
    return int(value, 16)


def _words(value: Any, count: int) -> list[int]:
    match = _WORDS.fullmatch(value) if type(value) is str else None
    if match is None or len(match.group(1)) != 64 * count:
        raise BindingFillRefused("READ_MALFORMED")
    return [int(match.group(1)[i:i + 64], 16) for i in range(0, 64 * count, 64)]


def _address(value: Any) -> str:
    number = _words(value, 1)[0]
    if number >> 160:
        raise BindingFillRefused("READ_MALFORMED")
    return "0x" + f"{number:040x}"


def _at(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def _records(data: bytes, content: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    def refuse_constant(name: str) -> Any:
        raise ValueError(name)

    try:
        store = json.loads(data.decode("utf-8"), parse_constant=refuse_constant)
    except (UnicodeDecodeError, ValueError):
        raise BindingFillRefused("READS_RECORDS_INVALID") from None
    planned = _requests(content, BLOCK_PLACEHOLDER)
    operations = store.get("operations") if type(store) is dict else None
    if (type(store) is not dict or set(store) != {"schema", "operations"} or store["schema"] != RECORDS_SCHEMA
            or type(operations) is not list or len(operations) != len(planned)):
        raise BindingFillRefused("READS_RECORDS_INVALID")
    for record, (op_id, method, _) in zip(operations, planned):
        if (type(record) is not dict or set(record) != RECORD_FIELDS or record["op_id"] != op_id
                or record["method"] != method or record["expect"] != "RESULT" or record["status"] not in STATUSES
                or type(record["at"]) is not str or _AT.fullmatch(record["at"]) is None):
            raise BindingFillRefused("READS_RECORDS_INVALID")
        try:
            _at(record["at"])
        except ValueError:
            raise BindingFillRefused("READS_RECORDS_INVALID") from None
    # A value that was not read is unavailable. It is never replaced by zero or a default.
    for record in operations:
        if record["status"] != "RESULT" or record["error"] is not None or record["result"] is None:
            raise BindingFillRefused("READ_UNAVAILABLE")
    return {record["op_id"]: record for record in operations}


def _checked_reads(authored: Mapping[str, Any], fill: Mapping[str, Any], data: bytes) -> dict[str, Any]:
    release = complete_release(authored, fill)
    content = release.content()
    route, quote, gas = content["route"], content["quote"], content["gas"]
    by_id = _records(data, content)
    block = by_id["binding.finalized_block"]["result"]
    if type(block) is not dict:
        raise BindingFillRefused("READ_MALFORMED")
    number, stamp = _quantity(block.get("number")), _quantity(block.get("timestamp"))
    if type(block.get("hash")) is not str or _HASH.fullmatch(block["hash"]) is None:
        raise BindingFillRefused("READ_MALFORMED")
    # Every request must be the planned one at that exact block, and its saved hash must be the request's own.
    for op_id, method, params in _requests(content, hex(number)):
        record = by_id[op_id]
        if record["params"] != params or record["request_sha256"] != request_sha256(method, params):
            raise BindingFillRefused("READS_RECORD_MISMATCH")
    chain_id = by_id["binding.chain_id"]["result"]
    if _quantity(chain_id) != content["chain_id"]:
        raise BindingFillRefused("READ_WRONG_CHAIN")
    times = [_at(record["at"]) for record in by_id.values()]
    block_time = dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
    read_at = _at(by_id["binding.finalized_block"]["at"])
    if times != sorted(times) or block_time > read_at:
        raise BindingFillRefused("READ_MALFORMED")
    max_age = route["freshness"]["max_input_age_seconds"]
    if (number < fill["reserves"]["block_number"] or (read_at - block_time).total_seconds() > max_age
            or (times[-1] - times[0]).total_seconds() > max_age):
        raise BindingFillRefused("READ_BLOCK_STALE")
    wmon_decimals = _words(by_id["binding.wmon_decimals"]["result"], 1)[0]
    moe_decimals = _words(by_id["binding.moe_decimals"]["result"], 1)[0]
    if (wmon_decimals, moe_decimals) != (route["input_asset"]["decimals"], route["output_asset"]["decimals"]):
        raise BindingFillRefused("READ_DECIMALS_MISMATCH")
    token0, token1 = _address(by_id["binding.pool_token0"]["result"]), _address(by_id["binding.pool_token1"]["result"])
    reserve0, reserve1, last = _words(by_id["binding.pool_reserves"]["result"], 3)
    if reserve0 <= 0 or reserve1 <= 0:
        raise BindingFillRefused("READ_MALFORMED")
    if (token0, token1) != (quote["token0_address"].lower(), quote["token1_address"].lower()):
        raise BindingFillRefused("READ_POOL_MISMATCH")
    wmon = _words(by_id["binding.wmon_balance"]["result"], 1)[0]
    moe = _words(by_id["binding.moe_balance"]["result"], 1)[0]
    allowance = _words(by_id["binding.wmon_allowance"]["result"], 1)[0]
    native = _quantity(by_id["binding.native_balance"]["result"])
    if wmon < int(route["approved_input_raw"]):
        raise BindingFillRefused("BALANCE_BELOW_INPUT")
    if native < int(gas["budget_raw"]):
        raise BindingFillRefused("NATIVE_BELOW_GAS_BUDGET")
    return {
        "schema": ARTIFACT_SCHEMA, "release_sha256": release_sha256(release),
        "reads_sha256": hashlib.sha256(data).hexdigest(), "chain_id": content["chain_id"],
        "block": {"number": number, "hash": block["hash"], "timestamp": stamp, "read_at": by_id["binding.finalized_block"]["at"]},
        "wallet_address": content["wallet_address"],
        "findings": {
            "wmon": {"token": route["input_asset"]["token_address"], "decimals": wmon_decimals,
                     "balance_raw": str(wmon), "allowance_to_entrypoint_raw": str(allowance)},
            "moe": {"token": route["output_asset"]["token_address"], "decimals": moe_decimals, "balance_raw": str(moe)},
            "native": {"balance_raw": str(native)},
            "pool": {"address": quote["pool_address"], "token0": token0, "token1": token1,
                     "reserve0_raw": str(reserve0), "reserve1_raw": str(reserve1), "block_timestamp_last": last}},
        "checks": {
            "wmon_balance_covers_input": {"required_raw": route["approved_input_raw"], "result": True},
            "native_balance_covers_gas_budget": {"required_raw": gas["budget_raw"], "result": True}},
        "shows": list(SHOWS), "does_not_show": list(DOES_NOT_SHOW), "fills_slot": None,
    }


def build_reads_artifact(authored: Mapping[str, Any], fill: Mapping[str, Any], records: bytes) -> bytes:
    """The canonical artifact bytes for one recorded read pass. Its SHA-256 is the SHA-256 of these bytes."""
    return json_bytes(_checked_reads(authored, fill, records))


def verify_reads_artifact(authored: Mapping[str, Any], fill: Mapping[str, Any], records: bytes,
                          artifact: bytes) -> str:
    """Rebuild the artifact from its records and release; any edited byte refuses."""
    if build_reads_artifact(authored, fill, records) != artifact:
        raise BindingFillRefused("READS_ARTIFACT_MISMATCH")
    return hashlib.sha256(artifact).hexdigest()


def _proof_sha256(slot: str, data: bytes, release_digest: str) -> str:
    """The slot hash is the hash of the exact file. The file must say which slot and release it is for."""
    try:
        value = json.loads(data.decode("utf-8"), parse_constant=lambda name: float("nan"))
        canonical = json_bytes(value) == data
    except (UnicodeDecodeError, ValueError):
        canonical = False
    if not canonical:
        raise BindingFillRefused("PROOF_ARTIFACT_NOT_CANONICAL")
    if (type(value) is not dict or type(value.get("schema")) is not str or value.get("proof") != slot
            or value.get("release_sha256") != release_digest):
        raise BindingFillRefused("PROOF_ARTIFACT_MISMATCH")
    return hashlib.sha256(data).hexdigest()


def assemble_binding_fill(authored: Mapping[str, Any], fill: Mapping[str, Any], identity: Any,
                          proofs: Mapping[str, bytes], market_profile: Any) -> dict[str, Any]:
    """The step-6 binding fill for these proof files, bound with `bind_release`, and what it is ready for."""
    release = complete_release(authored, fill)
    digest = release_sha256(release)
    if not all(slot in SLOTS for slot in proofs):
        raise BindingFillRefused("FRAGMENT_SLOT_INVALID")
    if not all(slot in proofs for slot in REQUIRED_SLOTS):
        raise BindingFillRefused("FRAGMENT_REQUIRED_PROOF_MISSING")
    hashes = {slot: _proof_sha256(slot, proofs[slot], digest) for slot in SLOTS if slot in proofs}
    binding_fill = {"identity": identity, **{f"{slot}_proof_sha256": hashes.get(slot) for slot in SLOTS},
                    "market_profile": market_profile}
    bound = bind_release(release, binding_fill)
    missing = sorted(slot for slot in APPROVAL_SLOTS if slot not in hashes)
    return {"release_sha256": digest, "binding_sha256": bound.sha256, "proof_sha256": hashes,
            "binding_fill": binding_fill, "derive_approval_ready": not missing,
            "missing_for_derive_approval": missing, "market_observation_ready": market_profile is not None}


def _json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_new(path: str, data: bytes) -> None:
    try:
        with open(path, "xb") as handle:
            handle.write(data)
    except FileExistsError:
        raise BindingFillRefused("OUTPUT_EXISTS") from None


def _proof_files(entries: Sequence[str]) -> dict[str, bytes]:
    proofs: dict[str, bytes] = {}
    for entry in entries:
        slot, separator, path = entry.partition("=")
        if not separator or not path or slot in proofs:
            raise BindingFillRefused("FRAGMENT_SLOT_INVALID")
        proofs[slot] = Path(path).read_bytes()
    return proofs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m edge_os_api.execution.inapp_binding_fill")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "reads", "verify-reads", "fragment"):
        command = commands.add_parser(name)
        command.add_argument("--authored", required=True)
        command.add_argument("--fill", required=True)
        if name in ("reads", "verify-reads"):
            command.add_argument("--records", required=True)
        if name == "verify-reads":
            command.add_argument("--artifact", required=True)
        if name == "fragment":
            command.add_argument("--identity", required=True)
            command.add_argument("--proof", action="append", default=[], metavar="SLOT=PATH")
            command.add_argument("--market-profile")
        if name in ("reads", "fragment"):
            command.add_argument("--out", help="a new file; an existing file is never replaced")
    options = parser.parse_args(argv)
    try:
        authored, fill = _json(options.authored), _json(options.fill)
        if options.command == "plan":
            result: dict[str, Any] = {"status": "PLANNED", "reads": read_plan(authored, fill)}
        elif options.command == "reads":
            artifact = build_reads_artifact(authored, fill, Path(options.records).read_bytes())
            if options.out:
                _write_new(options.out, artifact)
            result = {"status": "CHECKED", "reads_artifact_sha256": hashlib.sha256(artifact).hexdigest(),
                      "artifact": json.loads(artifact)}
        elif options.command == "verify-reads":
            result = {"status": "VERIFIED", "reads_artifact_sha256": verify_reads_artifact(
                authored, fill, Path(options.records).read_bytes(), Path(options.artifact).read_bytes())}
        else:
            profile = None if options.market_profile is None else _json(options.market_profile)
            result = {"status": "ASSEMBLED", **assemble_binding_fill(
                authored, fill, _json(options.identity), _proof_files(options.proof), profile)}
            if options.out:
                _write_new(options.out, json_bytes(result["binding_fill"]))
    except (BindingFillRefused, ReleaseRefused) as error:
        code = error.code if isinstance(error, BindingFillRefused) else str(error)
        print(json.dumps({"status": "REFUSED", "code": code}))
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "REFUSED", "code": "INAPP_FILE_UNREADABLE"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
