"""Authored synthetic fixtures for the local research-history adapter tests.

Everything here is invented and labelled SYNTHETIC_FIXTURE. It is not provider,
chain or market evidence. The recorded responses replay a two-page, two-swap
history. Expected amounts, prices and counts are written by hand from the
decimal-50 half-even rule, not produced by the code under test.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from edge_os_api.research_history.qualification_engine import epoch

POOL = "0x" + "aa" * 20
QUOTE = "0x" + "bb" * 20
BASE = "0x" + "cc" * 20
TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
SENDER = "0x" + "11" * 32
RECIPIENT = "0x" + "22" * 32
HASH_103 = "0x" + "11" * 32
HASH_110 = "0x" + "33" * 32

WINDOW_START = "2026-09-25T10:00:00Z"
WINDOW_END = "2026-09-25T10:20:00Z"
COLLECTED_AT = "2026-09-25T10:30:00Z"
ARCHIVE_HEIGHT = 1_000_000

_T0 = epoch(WINDOW_START)
T0 = _T0
E1_TS = _T0 + 30
E2_TS = _T0 + 330
P1_FIRST_TS = _T0 - 360
P1_LAST_TS = _T0 + 60
P2_FIRST_TS = _T0 + 60
P2_LAST_TS = _T0 + 1200

SCAN = {"from_block": 100, "to_block_exclusive": 111}


def _hex32(seed: str) -> str:
    return "0x" + hashlib.sha256(seed.encode()).hexdigest()


def _word(value: int) -> str:
    return f"{value:064x}"


def _data(*words: int) -> str:
    return "0x" + "".join(_word(word) for word in words)


QUOTE_IN = 2_000_000
BASE_LEG = 10 ** 18
QUOTE_OUT = 3_000_000

# e1: quote enters, base leaves -> QUOTE_IN_BASE_OUT, price 2, quote amount 2.
EVENT_QUOTE_IN = {
    "address": POOL, "topic0": TOPIC0, "topic1": SENDER, "topic2": RECIPIENT,
    "data": _data(QUOTE_IN, 0, 0, BASE_LEG),
    "block_number": 101, "block_hash": _hex32("block-101"), "block_timestamp": str(E1_TS),
    "transaction_hash": _hex32("tx-101"), "transaction_index": 0, "log_index": 0, "removed": False,
}
# e2: base enters, quote leaves -> BASE_IN_QUOTE_OUT, price 3, quote amount 3.
EVENT_BASE_IN = {
    "address": POOL, "topic0": TOPIC0, "topic1": SENDER, "topic2": RECIPIENT,
    "data": _data(0, BASE_LEG, QUOTE_OUT, 0),
    "block_number": 106, "block_hash": _hex32("block-106"), "block_timestamp": str(E2_TS),
    "transaction_hash": _hex32("tx-106"), "transaction_index": 0, "log_index": 1, "removed": False,
}


def profile(availability: dict[str, Any] | None = None,
            evidence_class: str = "SYNTHETIC_FIXTURE",
            decimals: tuple[int, int] = (6, 18)) -> dict[str, Any]:
    """A valid P07 profile template with an empty dataset. Quote decimals then base decimals."""
    quote_decimals, base_decimals = decimals
    return {
        "schema_version": "p07.market_dataset_profile/1",
        "profile_id": "rh-syn/1",
        "evidence_class": evidence_class,
        "network": {"network": "MONAD", "chain_id": 999001, "chain_id_source": "PROVIDER_READ"},
        "venue": {"underlying_venue": "synthetic-v2-venue-rh/1", "pool_family": "UNISWAP_V2_COMPATIBLE",
                  "pool_address": POOL},
        "pool_tokens": [
            {"address": QUOTE, "symbol_label": "SYNQ", "kind": "ERC20", "decimals": quote_decimals,
             "role": "QUOTE"},
            {"address": BASE, "symbol_label": "SYNB", "kind": "ERC20", "decimals": base_decimals,
             "role": "BASE"},
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
        "availability": availability or {"model": "OBSERVED_DELIVERY", "basis_evidence": "SOURCE_DELIVERY_RECORD"},
        "finality": {"depth_blocks": 2, "basis": "DOCUMENTATION"},
        "execution_route": {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None,
                            "qualification": "UNQUALIFIED"},
        "unmodeled_effects": ["TRANSFER_OR_REFLECTION", "WRAPPING", "ROUTING", "GAS", "PRICE_IMPACT",
                              "CAPACITY"],
        "dataset": {
            "window": {"start_utc": WINDOW_START, "end_utc": WINDOW_END},
            "collection": {"collected_at_utc": COLLECTED_AT, "collected_on_utc": None,
                           "archive_height": ARCHIVE_HEIGHT},
            "query": {"identity_sha256": None, "definition": None, "from_block": None,
                      "to_block_exclusive": None},
            "pages": [],
            "dataset_revision": {"basis": "NONE", "manifest_sha256": None, "page_count": 0,
                                 "row_count": None},
        },
    }


def _page(page_id: str, from_block: int, next_block: int, first_ts: int, last_ts: int,
          first_parent_hash: str | None = None, last_block_hash: str | None = None) -> dict[str, Any]:
    page = {"page_id": page_id, "from_block": from_block, "next_block": next_block,
            "sha256": hashlib.sha256(page_id.encode()).hexdigest(),
            "first_block_timestamp": first_ts, "last_block_timestamp": last_ts}
    if first_parent_hash is not None:
        page["first_parent_hash"] = first_parent_hash
    if last_block_hash is not None:
        page["last_block_hash"] = last_block_hash
    return page


def _response(page: dict[str, Any], events: list[Any], before: int | None, after: int | None,
              complete: bool, served_utc: str = COLLECTED_AT,
              provider: str = "ENVIO_HYPERSYNC",
              provider_version: str = "envio-hypersync/1") -> dict[str, Any]:
    return {
        "provider": provider, "provider_version": provider_version, "served_utc": served_utc,
        "query": {"address": POOL, "topic0": TOPIC0, "from_block": SCAN["from_block"],
                  "to_block_exclusive": SCAN["to_block_exclusive"]},
        "page": page, "cursor": {"before": before, "after": after}, "complete": complete,
        "events": events,
    }


def standard_responses() -> list[dict[str, Any]]:
    """Two recorded pages that tile blocks 100-110 and carry the two swaps."""
    return responses_with([copy.deepcopy(EVENT_QUOTE_IN)], [copy.deepcopy(EVENT_BASE_IN)])


def responses_with(events_page1: list[Any], events_page2: list[Any],
                   page1: dict[str, Any] | None = None,
                   page2: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Two recorded pages with caller-chosen events. Pages default to the standard tiling."""
    first = page1 or _page("rh-p1", 100, 104, P1_FIRST_TS, P1_LAST_TS, last_block_hash=HASH_103)
    second = page2 or _page("rh-p2", 104, 111, P2_FIRST_TS, P2_LAST_TS, first_parent_hash=HASH_103,
                            last_block_hash=HASH_110)
    return [
        _response(first, list(events_page1), None, 104, complete=False),
        _response(second, list(events_page2), 104, None, complete=True),
    ]


def single_page(events: list[Any], page: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One complete recorded page carrying the caller's events."""
    chosen = page or _page("rh-solo", 100, 111, P1_FIRST_TS, P2_LAST_TS, last_block_hash=HASH_110)
    return [_response(chosen, list(events), None, None, complete=True)]


def evidence_facts(**overrides: Any) -> dict[str, Any]:
    """Facts only a provider read gives. Complete and observed unless overridden."""
    facts: dict[str, Any] = {
        "collected_at_utc": COLLECTED_AT,
        "archive_height": ARCHIVE_HEIGHT,
        "chain_id_source": "PROVIDER_READ",
        "pool_tokens": "CORROBORATED_READ",
        "pool_venue": "CORROBORATED",
        "decimals": {
            "base": {"window_start": "READ", "window_end": "READ", "current": "READ"},
            "quote": {"window_start": "READ", "window_end": "READ", "current": "READ"},
        },
        "fee_transfer_semantics": "QUALIFIED",
        "corroboration": {"class": "COMPLETE", "provider": "QUICKNODE_JSON_RPC", "sample_size": 2,
                          "population_size": 2, "mismatches": 0},
        "finality_at_collection": "OBSERVED_FINAL",
        "feasibility_claim": {
            "schedule": {"anchor_utc": WINDOW_START, "period_seconds": 300,
                         "feature_end_offset_seconds": 0},
            "horizon_seconds": 300, "reference_window_seconds": 300, "warmup_buckets": 0,
            "partitions": [{"name": "rh-window", "start_utc": WINDOW_START,
                            "end_utc": "2026-09-25T10:15:00Z", "required_triggered": 1,
                            "required_control": 1}],
        },
    }
    facts.update(overrides)
    return facts


def limits(**overrides: Any) -> dict[str, Any]:
    values = {"max_pages": 8, "max_rows": 64, "max_bytes": 131072, "deadline_utc": None}
    values.update(overrides)
    return values


# Public builder aliases so tests do not reach into private names.
build_page = _page
build_response = _response
