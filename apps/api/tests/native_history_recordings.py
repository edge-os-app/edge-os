"""Authored native-shaped recordings for the #58 SOURCE-LOCAL journey (`edge-os.recorded-native-bundle/1`).

Every value here is invented and labelled SYNTHETIC_FIXTURE. It is not provider, chain or market evidence. Each source
holds native Envio HyperSync `QueryResponse` pages and QuickNode JSON-RPC results that the application replays through
the accepted P07 transport (`EnvioHypersyncSource`) and corroboration (`read_chain_id`, `corroborate_records`) with
offline recorded clients. The pool and assets differ from the RECORDED_RESPONSE sample bundle, so a declaration on this
market cannot reuse the sample's tested market. Prices are authored by hand.

`build_bundle()` is the only writer. `test_native_source_journey.py` checks that the saved JSON equals it.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from edge_os_api.research_history.qualification_engine import epoch, iso_utc

BUNDLE_PATH = Path(__file__).resolve().parent / "fixtures" / "research_history_native" / "native_history_v1.json"
BUNDLE_VERSION = "edge-os.recorded-native-bundle/1"

POOL = "0x" + "d1" * 20
QUOTE = "0x" + "d2" * 20
BASE = "0x" + "d3" * 20
TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
WINDOW_START = "2026-09-25T10:00:00Z"
WINDOW_END = "2026-09-25T12:00:00Z"
COLLECTED_AT = "2026-09-25T12:30:00Z"
ARCHIVE_HEIGHT = 2_000_000
FIRST_BLOCK = 500
SWAP_OFFSET = 30
MONAD_CHAIN_HEX = "0x8f"  # 143, the only chain the accepted P07 corroboration verifies
CLOSES = ("50", "50.25", "50.5", "51", "50.75", "50.5", "50", "49.5", "49.75", "50.5", "51.25", "52",
          "51.5", "51", "50.75", "50.5", "51", "51.75", "52.5", "52", "51.5", "51.25", "51", "50.5")


def _hex32(seed: str) -> str:
    return "0x" + hashlib.sha256(seed.encode()).hexdigest()


def _data(*words: int) -> str:
    return "0x" + "".join(f"{word:064x}" for word in words)


def _swap(index: int, close: str) -> dict[str, Any]:
    """One native log 30 seconds into bucket `index`. Even buckets buy base with quote; odd buckets sell base."""
    quote_raw = int(round(float(close) * 1_000_000))
    base_raw = 10 ** 18
    data = _data(quote_raw, 0, 0, base_raw) if index % 2 == 0 else _data(0, base_raw, quote_raw, 0)
    block = FIRST_BLOCK + 1 + index
    return {"address": POOL, "topic0": TOPIC0, "topic1": "0x" + "41" * 32, "topic2": "0x" + "42" * 32,
            "data": data, "block_number": block, "block_hash": _hex32(f"native-block-{block}"),
            "transaction_hash": _hex32(f"native-tx-{block}"), "transaction_index": 0, "log_index": index % 3,
            "removed": False}


def _swap_time(index: int) -> int:
    return epoch(WINDOW_START) + 300 * index + SWAP_OFFSET


def _profile(source_id: str) -> dict[str, Any]:
    return {
        "schema_version": "p07.market_dataset_profile/1",
        "profile_id": source_id,
        "evidence_class": "SYNTHETIC_FIXTURE",
        "network": {"network": "MONAD", "chain_id": 143, "chain_id_source": "PROVIDER_READ"},
        "venue": {"underlying_venue": "synthetic-v2-venue-native/1", "pool_family": "UNISWAP_V2_COMPATIBLE",
                  "pool_address": POOL},
        "pool_tokens": [
            {"address": QUOTE, "symbol_label": "NATQ", "kind": "ERC20", "decimals": 6, "role": "QUOTE"},
            {"address": BASE, "symbol_label": "NATB", "kind": "ERC20", "decimals": 18, "role": "BASE"},
        ],
        "orientation": "QUOTE_PER_BASE",
        "event": {"event_schema_version": "uniswap-v2-swap/1",
                  "signature": "Swap(address,uint256,uint256,uint256,uint256,address)", "topic0": TOPIC0},
        "conversion": {"amount_conversion_version": "v2-swap-quote-per-base-pool-gross/1",
                       "numeric": "decimal-50-half-even/1", "measurement": "POOL_GROSS"},
        "resolution": {"bucket_seconds": 300, "interval": "[start,end)"},
        "ordering": {"key": ["block_number", "transaction_index", "log_index"]},
        "source": {"history_provider": "ENVIO_HYPERSYNC", "corroboration_provider": "QUICKNODE_JSON_RPC",
                   "data_route": "ENVIO_QUICKNODE_CORROBORATED"},
        "availability": {"model": "OBSERVED_DELIVERY", "basis_evidence": "SOURCE_DELIVERY_RECORD"},
        "finality": {"depth_blocks": 2, "basis": "DOCUMENTATION"},
        "execution_route": {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None,
                            "qualification": "UNQUALIFIED"},
        "unmodeled_effects": ["TRANSFER_OR_REFLECTION", "WRAPPING", "ROUTING", "GAS", "PRICE_IMPACT", "CAPACITY"],
        "dataset": {
            "window": {"start_utc": WINDOW_START, "end_utc": WINDOW_END},
            "collection": {"collected_at_utc": COLLECTED_AT, "collected_on_utc": None,
                           "archive_height": ARCHIVE_HEIGHT},
            "query": {"identity_sha256": None, "definition": None, "from_block": None, "to_block_exclusive": None},
            "pages": [],
            "dataset_revision": {"basis": "NONE", "manifest_sha256": None, "page_count": 0, "row_count": None},
        },
    }


def _scan() -> dict[str, int]:
    return {"from_block": FIRST_BLOCK, "to_block_exclusive": FIRST_BLOCK + 2 + len(CLOSES)}


def _native_log(event: dict[str, Any]) -> dict[str, Any]:
    return dict(event)


def _native_page(from_block: int, next_block: int, indices: range, first_ts: int, last_ts: int) -> dict[str, Any]:
    """One native `QueryResponse`: logs, the block facts that time them, and the page-edge block facts."""
    events = [_swap(index, CLOSES[index]) for index in indices]
    blocks = {from_block: {"number": hex(from_block), "timestamp": hex(first_ts)}}
    for index, event in zip(indices, events):
        blocks[event["block_number"]] = {"number": event["block_number"], "timestamp": _swap_time(index),
                                         "hash": event["block_hash"]}
    last_hash = _hex32(f"native-block-{next_block - 1}")
    blocks[next_block - 1] = {"number": next_block - 1, "timestamp": last_ts, "hash": last_hash}
    return {"archive_height": ARCHIVE_HEIGHT, "next_block": hex(next_block), "total_execution_time": 4,
            "data": [{"blocks": [blocks[key] for key in sorted(blocks)], "logs": [_native_log(e) for e in events]}],
            "rollback_guard": {"block_number": next_block - 1, "timestamp": last_ts, "hash": last_hash,
                               "first_block_number": from_block}}


def _pages() -> list[dict[str, Any]]:
    """Two native pages that tile the scan; the boundary sits after the twelfth swap."""
    scan = _scan()
    split = FIRST_BLOCK + 13
    start = epoch(WINDOW_START)
    return [_native_page(FIRST_BLOCK, split, range(0, 12), start - 360, _swap_time(11)),
            _native_page(split, scan["to_block_exclusive"], range(12, len(CLOSES)), _swap_time(12),
                         epoch(WINDOW_END))]


def _receipt(event: dict[str, Any]) -> dict[str, Any]:
    log = {"address": event["address"], "topics": [event["topic0"], event["topic1"], event["topic2"]],
           "data": event["data"], "logIndex": hex(event["log_index"]), "transactionHash": event["transaction_hash"],
           "transactionIndex": hex(event["transaction_index"]), "blockNumber": hex(event["block_number"]),
           "blockHash": event["block_hash"], "removed": False}
    return {"transactionHash": event["transaction_hash"], "transactionIndex": hex(event["transaction_index"]),
            "blockNumber": hex(event["block_number"]), "blockHash": event["block_hash"], "status": "0x1",
            "logs": [log]}


def _quicknode(chain: str = MONAD_CHAIN_HEX) -> dict[str, Any]:
    receipts = {}
    for index, close in enumerate(CLOSES):
        event = _swap(index, close)
        receipts[event["transaction_hash"]] = _receipt(event)
    return {"eth_chainId": chain, "receipts": receipts, "rpc_faults": {}}


def _provider_facts(delivery_delay: int = 0) -> dict[str, Any]:
    """P07 evidence the P07 library does not read itself. Recorded declarations, not application reads."""
    start = epoch(WINDOW_START)
    return {
        "collected_at_utc": COLLECTED_AT,
        "archive_height": ARCHIVE_HEIGHT,
        "pool_tokens": "CORROBORATED_READ",
        "pool_venue": "CORROBORATED",
        "decimals": {"base": {"window_start": "READ", "window_end": "READ", "current": "READ"},
                     "quote": {"window_start": "READ", "window_end": "READ", "current": "READ"}},
        "fee_transfer_semantics": "QUALIFIED",
        "finality_at_collection": "OBSERVED_FINAL",
        "delivery_records": {iso_utc(start + 300 * step): iso_utc(start + 300 * step + 300 + delivery_delay)
                             for step in range(len(CLOSES))},
        "feasibility_claim": {
            "schedule": {"anchor_utc": WINDOW_START, "period_seconds": 300, "feature_end_offset_seconds": 0},
            "horizon_seconds": 300, "reference_window_seconds": 300, "warmup_buckets": 0,
            "partitions": [{"name": "native-window", "start_utc": WINDOW_START, "end_utc": "2026-09-25T11:55:00Z",
                            "required_triggered": 1, "required_control": 1}],
        },
    }


def _source(source_id: str, title: str, *, pages: list[Any] | None = None, quicknode: dict[str, Any] | None = None,
            sample: int = len(CLOSES), delivery_delay: int = 0) -> dict[str, Any]:
    return {"source_id": source_id, "title": title, "evidence_class": "RECORDED_NATIVE_RESPONSE",
            "content_label": "SYNTHETIC_FIXTURE", "profile": _profile(source_id), "scan": _scan(),
            "envio_pages": _pages() if pages is None else pages,
            "quicknode": _quicknode() if quicknode is None else quicknode,
            "corroboration_sample_size": sample, "provider_facts": _provider_facts(delivery_delay)}


def build_bundle() -> dict[str, Any]:
    """Every supported native recording. Each id names its scenario; none is observed market history."""
    pages = _pages()
    no_end_fact = copy.deepcopy(pages)
    no_end_fact[1]["data"][0]["blocks"] = no_end_fact[1]["data"][0]["blocks"][:-1]
    no_end_fact[1].pop("rollback_guard")
    wrong_network = copy.deepcopy(pages)
    wrong_network[0]["chain_id"] = "0x1"
    mismatched = _quicknode()
    first = _swap(3, CLOSES[3])["transaction_hash"]
    mismatched["receipts"][first]["blockHash"] = _hex32("a-different-block")
    rpc_failure = _quicknode()
    rpc_failure["rpc_faults"] = {_swap(5, CLOSES[5])["transaction_hash"]: "RPC_FAILED"}
    return {
        "schema_version": BUNDLE_VERSION,
        "label": ("SYNTHETIC native-shaped Envio and QuickNode recordings for local tests only; "
                  "not provider, chain or market evidence."),
        "sources": [
            _source("native-syn-qualified/1", "Native recording, full corroboration (qualifies)"),
            _source("native-syn-sampled/1", "Native recording, sampled corroboration (limited)", sample=8),
            _source("native-syn-page-facts-missing/1", "Native recording, page 2 omits its end block fact",
                    pages=no_end_fact),
            _source("native-syn-wrong-network/1", "Native recording, page 1 echoes another chain",
                    pages=wrong_network),
            _source("native-syn-provider-failure/1", "Native recording, provider fails on page 2",
                    pages=[copy.deepcopy(pages[0]), {"fault": "SOURCE_FAILURE"}]),
            _source("native-syn-receipt-mismatch/1", "Native recording, one receipt names another block",
                    quicknode=mismatched),
            _source("native-syn-rpc-failure/1", "Native recording, one receipt call fails", quicknode=rpc_failure),
            _source("native-syn-wrong-chain/1", "Native recording, the RPC reports another chain",
                    quicknode=_quicknode("0x1")),
            _source("native-syn-late-delivery/1", "Native recording, each bucket delivered 30 s late",
                    delivery_delay=30),
        ],
    }


def write_bundle() -> None:
    """One compact source per line keeps the file small and each scenario's diff on its own line."""
    bundle = build_bundle()
    lines = [json.dumps(source, sort_keys=True, separators=(",", ":")) for source in bundle["sources"]]
    head = {key: bundle[key] for key in ("label", "schema_version")}
    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE_PATH.write_text(json.dumps(head, sort_keys=True)[:-1] + ', "sources": [\n' + ",\n".join(lines) + "\n]}\n",
                           encoding="utf-8")


if __name__ == "__main__":
    write_bundle()
