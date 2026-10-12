"""Authored recorded-response bundle for the local #58 research journey.

Every response here is invented and labelled SYNTHETIC_FIXTURE. It is not provider, chain or market evidence. The
bundle replays a two-hour, one-swap-per-bucket history in the P07 recorded-response shape so the application can
collect, qualify, compare and replay without a network, a provider or a credential. Prices are authored by hand.

`build_bundle()` is the only writer. `test_real_research_journey.py` checks that the saved JSON equals it.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from edge_os_api.research_history.qualification_engine import epoch, iso_utc

BUNDLE_PATH = Path(__file__).resolve().parent / "fixtures" / "research_history_recorded" / "recorded_history_v1.json"
BUNDLE_VERSION = "edge-os.recorded-history-bundle/1"

POOL = "0x" + "aa" * 20
QUOTE = "0x" + "bb" * 20
BASE = "0x" + "cc" * 20
TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
WINDOW_START = "2026-09-25T10:00:00Z"
WINDOW_END = "2026-09-25T12:00:00Z"
COLLECTED_AT = "2026-09-25T12:30:00Z"
ARCHIVE_HEIGHT = 1_000_000
FIRST_BLOCK = 100
# Each swap lands 30 seconds into its bucket, so a decision at a bucket end finds its reference trade in the next
# minute. The standard recording delivers each bucket at its end; the late-delivery recording delivers it 30 seconds
# later, which a decision at the bucket end must not read.
SWAP_OFFSET = 30
# Close price per five-minute bucket, quote per base, at most six decimals (the quote token's decimals).
CLOSES = ("100", "100.5", "101", "102.5", "102", "101", "100", "99", "99.5", "101", "102.5", "104",
          "103", "102", "101.5", "101", "102", "103.5", "105", "104", "103", "102.5", "102", "101")


def _hex32(seed: str) -> str:
    return "0x" + hashlib.sha256(seed.encode()).hexdigest()


def _data(*words: int) -> str:
    return "0x" + "".join(f"{word:064x}" for word in words)


def _swap(index: int, close: str) -> dict[str, Any]:
    """One swap 30 seconds into bucket `index`. Even buckets buy base with quote; odd buckets sell base."""
    quote_raw = int(round(float(close) * 1_000_000))
    base_raw = 10 ** 18
    data = _data(quote_raw, 0, 0, base_raw) if index % 2 == 0 else _data(0, base_raw, quote_raw, 0)
    block = FIRST_BLOCK + 1 + index
    return {"address": POOL, "topic0": TOPIC0, "topic1": "0x" + "11" * 32, "topic2": "0x" + "22" * 32,
            "data": data, "block_number": block, "block_hash": _hex32(f"block-{block}"),
            "block_timestamp": str(epoch(WINDOW_START) + 300 * index + SWAP_OFFSET),
            "transaction_hash": _hex32(f"tx-{block}"), "transaction_index": 0, "log_index": index % 3,
            "removed": False}


def _profile(source_id: str) -> dict[str, Any]:
    return {
        "schema_version": "p07.market_dataset_profile/1",
        "profile_id": source_id,
        "evidence_class": "SYNTHETIC_FIXTURE",
        "network": {"network": "MONAD", "chain_id": 999001, "chain_id_source": "PROVIDER_READ"},
        "venue": {"underlying_venue": "synthetic-v2-venue-rh/1", "pool_family": "UNISWAP_V2_COMPATIBLE",
                  "pool_address": POOL},
        "pool_tokens": [
            {"address": QUOTE, "symbol_label": "SYNQ", "kind": "ERC20", "decimals": 6, "role": "QUOTE"},
            {"address": BASE, "symbol_label": "SYNB", "kind": "ERC20", "decimals": 18, "role": "BASE"},
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
    # Block 100 precedes the first swap; the final block, with no swap, closes the window at its end time.
    return {"from_block": FIRST_BLOCK, "to_block_exclusive": FIRST_BLOCK + 2 + len(CLOSES)}


def _responses() -> list[dict[str, Any]]:
    """Two recorded pages that tile the scan. The page boundary sits after the twelfth swap."""
    events = [_swap(index, close) for index, close in enumerate(CLOSES)]
    scan = _scan()
    split = FIRST_BLOCK + 13
    last_first_page = _hex32(f"block-{split - 1}")
    last_block = _hex32(f"block-{scan['to_block_exclusive'] - 1}")
    start = epoch(WINDOW_START)
    pages = [
        {"page_id": "rec-p1", "from_block": FIRST_BLOCK, "next_block": split,
         "sha256": hashlib.sha256(b"rec-p1").hexdigest(), "first_block_timestamp": start - 360,
         "last_block_timestamp": start + 300 * 11 + SWAP_OFFSET, "last_block_hash": last_first_page},
        {"page_id": "rec-p2", "from_block": split, "next_block": scan["to_block_exclusive"],
         "sha256": hashlib.sha256(b"rec-p2").hexdigest(), "first_block_timestamp": start + 300 * 12 + SWAP_OFFSET,
         "last_block_timestamp": epoch(WINDOW_END), "first_parent_hash": last_first_page,
         "last_block_hash": last_block},
    ]
    query = {"address": POOL, "topic0": TOPIC0, **scan}
    return [
        {"provider": "ENVIO_HYPERSYNC", "provider_version": "envio-hypersync/1", "served_utc": COLLECTED_AT,
         "query": query, "page": pages[0], "cursor": {"before": None, "after": split}, "complete": False,
         "events": events[:12]},
        {"provider": "ENVIO_HYPERSYNC", "provider_version": "envio-hypersync/1", "served_utc": COLLECTED_AT,
         "query": query, "page": pages[1], "cursor": {"before": split, "after": None}, "complete": True,
         "events": events[12:]},
    ]


def _evidence(corroboration_class: str = "COMPLETE", delivery_delay: int = 0) -> dict[str, Any]:
    start = epoch(WINDOW_START)
    return {
        "collected_at_utc": COLLECTED_AT,
        "archive_height": ARCHIVE_HEIGHT,
        "chain_id_source": "PROVIDER_READ",
        "pool_tokens": "CORROBORATED_READ",
        "pool_venue": "CORROBORATED",
        "decimals": {"base": {"window_start": "READ", "window_end": "READ", "current": "READ"},
                     "quote": {"window_start": "READ", "window_end": "READ", "current": "READ"}},
        "fee_transfer_semantics": "QUALIFIED",
        "corroboration": {"class": corroboration_class, "provider": "QUICKNODE_JSON_RPC",
                          "sample_size": len(CLOSES), "population_size": len(CLOSES), "mismatches": 0},
        "finality_at_collection": "OBSERVED_FINAL",
        "delivery_records": {iso_utc(start + 300 * step): iso_utc(start + 300 * step + 300 + delivery_delay)
                             for step in range(len(CLOSES))},
        "feasibility_claim": {
            "schedule": {"anchor_utc": WINDOW_START, "period_seconds": 300, "feature_end_offset_seconds": 0},
            "horizon_seconds": 300, "reference_window_seconds": 300, "warmup_buckets": 0,
            "partitions": [{"name": "rec-window", "start_utc": WINDOW_START, "end_utc": "2026-09-25T11:55:00Z",
                            "required_triggered": 1, "required_control": 1}],
        },
    }


def _source(source_id: str, title: str, *, responses: list[dict[str, Any]] | None = None,
            evidence: dict[str, Any] | None = None, provider_requests: Any = "MATCH_PAGES") -> dict[str, Any]:
    chosen = _responses() if responses is None else responses
    if provider_requests == "MATCH_PAGES":
        provider_requests = {"ENVIO_HYPERSYNC": sum(1 for item in chosen if "fault" not in item)}
    return {"source_id": source_id, "title": title, "evidence_class": "RECORDED_RESPONSE",
            "content_label": "SYNTHETIC_FIXTURE", "profile": _profile(source_id), "scan": _scan(),
            "responses": chosen, "evidence": evidence or _evidence(),
            "provider_requests": provider_requests}


def build_bundle() -> dict[str, Any]:
    """Every supported recorded source. Each id names its scenario; none is observed market history."""
    responses = _responses()
    return {
        "schema_version": BUNDLE_VERSION,
        "label": "SYNTHETIC recorded responses for local tests only; not provider, chain or market evidence.",
        "sources": [
            _source("recorded-syn-qualified/1", "Synthetic recorded history (qualifies)"),
            _source("recorded-syn-provider-failure/1", "Synthetic recorded history (provider fails on page 2)",
                    responses=[copy.deepcopy(responses[0]), {"fault": "SOURCE_FAILURE"}]),
            _source("recorded-syn-uncorroborated/1", "Synthetic recorded history (corroboration incomplete)",
                    evidence=_evidence("PARTIAL")),
            _source("recorded-syn-late-delivery/1", "Synthetic recorded history (each bucket delivered 30 s late)",
                    evidence=_evidence(delivery_delay=30)),
            _source("recorded-syn-usage-unknown/1", "Synthetic recorded history (provider usage not reported)",
                    provider_requests=None),
            _source("recorded-syn-usage-invalid/1", "Synthetic recorded history (provider usage malformed)",
                    provider_requests={"ENVIO_HYPERSYNC": -1}),
        ],
    }


def write_bundle() -> None:
    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE_PATH.write_text(json.dumps(build_bundle(), indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_bundle()
