"""Offline P07 qualification contract for one research pool and its price-volume history.

Standard library only. No network, provider, credential or wallet access.
Amounts stay exact integers. Prices use the accepted decimal-50-half-even context.
"""

from __future__ import annotations

import bisect
import calendar
import hashlib
import re
import runpy
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Context, Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Mapping, Sequence

# The accepted P02 checker owns canonical bytes and the ResearchBinding record. It is reused, not copied.
_P02 = runpy.run_path(str(Path(__file__).resolve().parents[2] / "contracts/p02/check_contract.py"))

_MASK = (1 << 64) - 1
_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROTATIONS = (
    (0, 36, 3, 41, 18), (1, 44, 10, 45, 2), (62, 6, 43, 15, 61), (28, 55, 25, 21, 56), (27, 20, 39, 8, 14),
)


def _rotate_left(value: int, bits: int) -> int:
    bits %= 64
    return ((value << bits) | (value >> (64 - bits))) & _MASK if bits else value


def _permute(lanes: list[int]) -> list[int]:
    for constant in _ROUND_CONSTANTS:
        parity = [lanes[x] ^ lanes[x + 5] ^ lanes[x + 10] ^ lanes[x + 15] ^ lanes[x + 20] for x in range(5)]
        mix = [parity[(x - 1) % 5] ^ _rotate_left(parity[(x + 1) % 5], 1) for x in range(5)]
        lanes = [lanes[i] ^ mix[i % 5] for i in range(25)]
        moved = [0] * 25
        for x in range(5):
            for y in range(5):
                moved[y + 5 * ((2 * x + 3 * y) % 5)] = _rotate_left(lanes[x + 5 * y], _ROTATIONS[x][y])
        lanes = [
            moved[i] ^ ((~moved[(i % 5 + 1) % 5 + 5 * (i // 5)] & _MASK) & moved[(i % 5 + 2) % 5 + 5 * (i // 5)])
            for i in range(25)
        ]
        lanes[0] ^= constant
    return lanes


def keccak256(data: bytes) -> bytes:
    """Ethereum Keccak-256 (not NIST SHA3-256). Used only to check event signature identity."""
    rate = 136
    pad = rate - len(data) % rate
    padded = data + (b"\x81" if pad == 1 else b"\x01" + b"\x00" * (pad - 2) + b"\x80")
    lanes = [0] * 25
    for start in range(0, len(padded), rate):
        block = padded[start:start + rate]
        for i in range(rate // 8):
            lanes[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        lanes = _permute(lanes)
    return b"".join(lane.to_bytes(8, "little") for lane in lanes)[:32]


class Unsupported(ValueError):
    """A record that cannot be used as a qualified trade. It is never guessed or repaired."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Trade:
    block_number: int
    transaction_index: int
    log_index: int
    block_hash: str
    transaction_hash: str
    block_timestamp: int
    pool_side: str
    quote_raw: int
    base_raw: int
    quote_amount: str
    base_amount: str
    price: str
    sender_topic: str
    recipient_topic: str

    @property
    def order_key(self) -> tuple[int, int, int]:
        return (self.block_number, self.transaction_index, self.log_index)


_HEX_WORD = re.compile(r"0x[0-9a-fA-F]{64}\Z")
_PRICE_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)


def parse_uint(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise Unsupported("FIELD_NOT_UINT", f"{field} is a boolean")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str):
        if re.fullmatch(r"0x[0-9a-fA-F]+", value):
            return int(value, 16)
        if re.fullmatch(r"[0-9]+", value):
            return int(value)
    raise Unsupported("FIELD_NOT_UINT", f"{field} must be a non-negative integer, 0x hex or decimal text")


def scale_down(raw: int, decimals: int) -> str:
    """Exact decimal text for a raw integer amount. No rounding."""
    digits = str(raw).rjust(decimals + 1, "0")
    if decimals == 0:
        return digits
    whole, fraction = digits[:-decimals], digits[-decimals:].rstrip("0")
    return f"{whole}.{fraction}" if fraction else whole


def _plain(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _require(log: Mapping[str, Any], names: tuple[str, ...], code: str) -> None:
    missing = [name for name in names if name not in log or log[name] is None]
    if missing:
        raise Unsupported(code, f"missing {', '.join(missing)}")


def decode_swap_log(profile: Mapping[str, Any], log: Mapping[str, Any]) -> Trade:
    """Decode one V2-compatible Swap log into a pool-gross quote/base trade.

    Raises Unsupported with a stable code for every shape the profile does not define.
    """
    removed = log.get("removed", False)
    if not isinstance(removed, bool):
        raise Unsupported("FIELD_NOT_BOOL", "removed must be true or false")
    if removed:
        raise Unsupported("REMOVED_BY_REORG", "node marked this log removed")
    address = log.get("address")
    if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise Unsupported("IDENTITY_FIELD_MISSING", "address is absent or not 40 hex digits")
    if address.lower() != profile["venue"]["pool_address"].lower():
        raise Unsupported("WRONG_POOL", "log address is not the profile pool")
    topics = log.get("topics")
    if not isinstance(topics, list) or not topics or str(topics[0]).lower() != profile["event"]["topic0"].lower():
        raise Unsupported("TOPIC0_MISMATCH", "first topic is not the profile Swap topic")
    if len(topics) != 3:
        raise Unsupported("TOPIC_COUNT", f"expected 3 topics, got {len(topics)}")
    if not all(isinstance(t, str) and _HEX_WORD.fullmatch(t) for t in topics[1:]):
        raise Unsupported("TOPIC_FORMAT", "indexed topics must be 32-byte hex words")
    data = log.get("data")
    if not isinstance(data, str) or not re.fullmatch(r"0x[0-9a-fA-F]{256}", data):
        raise Unsupported("DATA_LENGTH", "data must be exactly four 32-byte words")
    _require(log, ("block_number", "transaction_index", "log_index"), "ORDER_FIELD_MISSING")
    _require(log, ("block_hash", "transaction_hash"), "IDENTITY_FIELD_MISSING")
    _require(log, ("block_timestamp",), "TIME_FIELD_MISSING")
    for name in ("block_hash", "transaction_hash"):
        if not isinstance(log[name], str) or not _HEX_WORD.fullmatch(log[name]):
            raise Unsupported("IDENTITY_FIELD_MISSING", f"{name} is not a 32-byte hex hash")
    block, tx_index, log_index, timestamp = (
        parse_uint(log[name], name) for name in ("block_number", "transaction_index", "log_index", "block_timestamp")
    )
    words = [int(data[2 + 64 * i:66 + 64 * i], 16) for i in range(4)]
    amounts_in, amounts_out = words[0:2], words[2:4]
    inputs = [i for i in (0, 1) if amounts_in[i]]
    outputs = [i for i in (0, 1) if amounts_out[i]]
    if not inputs:
        raise Unsupported("ZERO_INPUT", "no input leg")
    if len(inputs) == 2:
        raise Unsupported("BOTH_INPUTS", "both tokens enter the pool")
    if not outputs:
        raise Unsupported("ZERO_OUTPUT", "no output leg")
    if len(outputs) == 2:
        raise Unsupported("BOTH_OUTPUTS", "both tokens leave the pool")
    if inputs[0] == outputs[0]:
        raise Unsupported("SAME_TOKEN_IN_OUT", "the same token enters and leaves")
    tokens = profile["pool_tokens"]
    quote_index = next(i for i, token in enumerate(tokens) if token["role"] == "QUOTE")
    base_index = 1 - quote_index
    quote_raw = amounts_in[quote_index] + amounts_out[quote_index]
    base_raw = amounts_in[base_index] + amounts_out[base_index]
    quote_decimals, base_decimals = tokens[quote_index]["decimals"], tokens[base_index]["decimals"]
    price = _PRICE_CONTEXT.divide(Decimal(quote_raw * 10**base_decimals), Decimal(base_raw * 10**quote_decimals))
    return Trade(
        block_number=block, transaction_index=tx_index, log_index=log_index,
        block_hash=log["block_hash"].lower(), transaction_hash=log["transaction_hash"].lower(),
        block_timestamp=timestamp,
        pool_side="QUOTE_IN_BASE_OUT" if inputs[0] == quote_index else "BASE_IN_QUOTE_OUT",
        quote_raw=quote_raw, base_raw=base_raw,
        quote_amount=scale_down(quote_raw, quote_decimals), base_amount=scale_down(base_raw, base_decimals),
        price=_plain(price), sender_topic=topics[1].lower(), recipient_topic=topics[2].lower(),
    )


def _try_uint(log: Mapping[str, Any], field_name: str) -> int | None:
    try:
        return parse_uint(log[field_name], field_name)
    except (KeyError, Unsupported):
        return None


def _try_key(log: Mapping[str, Any]) -> tuple[int, int, int] | None:
    keys = [_try_uint(log, f) for f in ("block_number", "transaction_index", "log_index")]
    return None if any(k is None for k in keys) else (keys[0], keys[1], keys[2])  # type: ignore[return-value]


def trade_identity(profile: Mapping[str, Any], trade: Trade) -> str:
    """Canonical raw trade identity: chain, block, transaction index, log index."""
    chain = profile["network"]["chain_id"]
    return f"{'unknown' if chain is None else chain}:{trade.block_number}:{trade.transaction_index}:{trade.log_index}"


@dataclass
class IngestResult:
    """Qualified trades in canonical order plus every record that was held out and why."""

    profile: Mapping[str, Any]
    trades: tuple[Trade, ...]
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    removed: int = 0
    foreign: int = 0

    def identities(self) -> list[str]:
        return [trade_identity(self.profile, trade) for trade in self.trades]

    def summary(self) -> dict[str, Any]:
        return {
            "trades": len(self.trades),
            "duplicate_copies": sum(item["copies"] - 1 for item in self.duplicates),
            "conflicts": len(self.conflicts),
            "rejected": len(self.rejected),
            "rejected_codes": dict(Counter(item["code"] for item in self.rejected)),
            "removed": self.removed,
            "foreign": self.foreign,
            "unlocated_rejections": sum(1 for item in self.rejected if item["block_timestamp"] is None),
            "pool_sides": sorted({trade.pool_side for trade in self.trades}),
        }


def ingest(profile: Mapping[str, Any], logs: Sequence[Mapping[str, Any]]) -> IngestResult:
    """Decode, deduplicate and order logs. Provider row order has no effect.

    A failed record is retained with its code and never stops the batch.
    A conflicting record is held out. No version of a conflict is chosen.
    """
    result = IngestResult(profile=profile, trades=())
    decoded: list[Trade] = []
    for position, log in enumerate(logs):
        if not isinstance(log, Mapping):
            result.rejected.append({"code": "NOT_AN_OBJECT", "detail": "record is not an object", "position": position,
                                    "block_timestamp": None, "block": None, "key": None, "ranges": []})
            continue
        try:
            decoded.append(decode_swap_log(profile, log))
        except Unsupported as error:
            if error.code == "REMOVED_BY_REORG":
                result.removed += 1
            elif error.code == "WRONG_POOL":
                result.foreign += 1
            else:
                result.rejected.append({"code": error.code, "detail": error.detail, "position": position,
                                        "block_timestamp": _try_uint(log, "block_timestamp"),
                                        "block": _try_uint(log, "block_number"),
                                        "key": _try_key(log), "ranges": []})

    def name(trade: Trade) -> str:
        return trade_identity(profile, trade)

    held: list[tuple[str, Sequence[Trade], Sequence[int]]] = []

    def hold_out(kind: str, members: Sequence[Trade], extra_times: Sequence[int] = ()) -> None:
        held.append((kind, list(members), tuple(extra_times)))

    unreadable = {item["key"]: item["block_timestamp"] for item in result.rejected if item["key"] is not None}
    by_position: dict[tuple[int, int, int], list[Trade]] = defaultdict(list)
    for trade in decoded:
        by_position[trade.order_key].append(trade)
    kept: list[Trade] = []
    for key in sorted(by_position):
        versions = by_position[key]
        if len(set(versions)) > 1 or key in unreadable:
            twin = unreadable.get(key)
            hold_out("POSITION_PAYLOAD", versions, () if twin is None else (twin,))
            continue
        if len(versions) > 1:
            result.duplicates.append({"identity": name(versions[0]), "copies": len(versions)})
        kept.append(versions[0])

    def drop_inconsistent(kind: str, trades: list[Trade], group_key: Any, fact: Any) -> list[Trade]:
        groups: dict[Any, list[Trade]] = defaultdict(list)
        for trade in trades:
            groups[group_key(trade)].append(trade)
        bad = {k for k, members in groups.items() if len({fact(t) for t in members}) > 1}
        for k in sorted(bad, key=str):
            hold_out(kind, groups[k])
        return [t for t in trades if group_key(t) not in bad]

    kept = drop_inconsistent("BLOCK_FACTS", kept, lambda t: t.block_number, lambda t: (t.block_hash, t.block_timestamp))
    kept = drop_inconsistent("BLOCK_FACTS", kept, lambda t: t.block_hash, lambda t: t.block_number)
    kept = drop_inconsistent("TX_POSITION", kept, lambda t: t.transaction_hash,
                             lambda t: (t.block_number, t.transaction_index))
    kept = drop_inconsistent("TX_POSITION", kept, lambda t: (t.block_number, t.transaction_index),
                             lambda t: t.transaction_hash)
    kept.sort(key=lambda t: t.order_key)
    # Block times never fall as block numbers rise. Hold out every trade that is part of any inversion.
    flagged: set[int] = set()
    running_max = -1
    for i, trade in enumerate(kept):
        if trade.block_timestamp < running_max:
            flagged.add(i)
        running_max = max(running_max, trade.block_timestamp)
    running_min = None
    for i in range(len(kept) - 1, -1, -1):
        if running_min is not None and kept[i].block_timestamp > running_min:
            flagged.add(i)
        running_min = kept[i].block_timestamp if running_min is None else min(running_min, kept[i].block_timestamp)
    if flagged:
        hold_out("TIMESTAMP_ORDER", [kept[i] for i in sorted(flagged)])
    result.trades = tuple(t for i, t in enumerate(kept) if i not in flagged)
    # A held-out trade has an unreliable time. When the claimed times disagree, its real time can be anywhere
    # between its qualified neighbours, so every bucket in that interval is unreliable too.
    blocks = [t.block_number for t in result.trades]
    times = [t.block_timestamp for t in result.trades]

    def neighbours(block: int) -> tuple[int, int]:
        """Times a record in this block can have. Qualified trades in the same block fix it exactly."""
        i, j = bisect.bisect_left(blocks, block), bisect.bisect_right(blocks, block)
        if i < j:
            return times[i], times[i]
        return (times[i - 1] if i > 0 else 0), (times[j] if j < len(times) else _FAR_FUTURE)

    for kind, members, extra in held:
        claimed = sorted({t.block_timestamp for t in members} | set(extra))
        ranges: list[tuple[int, int]] = []
        for member in members:
            lo, hi = neighbours(member.block_number)
            if kind == "TIMESTAMP_ORDER" or len(claimed) > 1 or not lo <= member.block_timestamp <= hi:
                ranges.append((lo, hi))
        result.conflicts.append({"kind": kind, "identities": sorted({name(t) for t in members}),
                                 "timestamps": claimed, "ranges": sorted(set(ranges))})
    for item in result.rejected:
        item["ranges"] = []
        ts = item["block_timestamp"]
        if ts is None:
            continue
        if item["block"] is None:
            item["ranges"].append((0, _FAR_FUTURE))
            continue
        lo, hi = neighbours(item["block"])
        if not lo <= ts <= hi:
            item["ranges"].append((lo, hi))
    return result


BUCKET_SECONDS = 300
_FAR_FUTURE = 1 << 62


class InvalidInput(ValueError):
    """A caller supplied a value outside the contract. Raised before any work starts."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def epoch(text: str) -> int:
    """Whole-second UTC timestamp. Block timestamps have second precision."""
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-5][0-9]Z", text):
        raise InvalidInput("TIMESTAMP_FORMAT", "expected YYYY-MM-DDTHH:MM:SSZ")
    try:
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError as error:
        raise InvalidInput("TIMESTAMP_FORMAT", str(error)) from error


def iso_utc(seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def _page_claims(page: Mapping[str, Any]) -> list[tuple[int, str, Any]]:
    """What one page says about the blocks at its edges: (block, kind, value)."""
    claims: list[tuple[int, str, Any]] = [
        (page["from_block"], "ts", page["first_block_timestamp"]),
        (page["next_block"] - 1, "ts", page["last_block_timestamp"]),
    ]
    if page.get("last_block_hash"):
        claims.append((page["next_block"] - 1, "hash", str(page["last_block_hash"]).lower()))
    if page.get("first_parent_hash"):
        claims.append((page["from_block"] - 1, "hash", str(page["first_parent_hash"]).lower()))
    return claims


def _untrusted_pages(pages: Sequence[Mapping[str, Any]]) -> dict[int, str]:
    """Indexes of pages that contradict other pages, with the break code for each.

    Every page that speaks about a block with two different hashes or two different times is dropped,
    including pages that repeat one side. Block times must also never fall as block numbers rise.
    A page that chains to a dropped page is dropped. The result does not depend on page ids or page order.
    """
    claims = [(block, kind, value, i) for i, page in enumerate(pages) for block, kind, value in _page_claims(page)]
    dropped: dict[int, str] = {}
    by_block: dict[tuple[int, str], set[Any]] = defaultdict(set)
    for block, kind, value, _ in claims:
        by_block[(block, kind)].add(value)
    for block, kind, _, i in claims:
        if len(by_block[(block, kind)]) > 1:
            dropped.setdefault(i, "REORG_BETWEEN_PAGES" if kind == "hash" else "TIMESTAMP_ORDER")
    times = sorted((block, value, i) for block, kind, value, i in claims if kind == "ts")
    running_max = None
    for _, value, i in times:
        if running_max is not None and value < running_max:
            dropped.setdefault(i, "TIMESTAMP_ORDER")
        running_max = value if running_max is None else max(running_max, value)
    running_min = None
    for _, value, i in reversed(times):
        if running_min is not None and value > running_min:
            dropped.setdefault(i, "TIMESTAMP_ORDER")
        running_min = value if running_min is None else min(running_min, value)
    changed = True
    while changed:
        changed = False
        bad_hashes = {str(pages[i]["last_block_hash"]).lower() for i in dropped if pages[i].get("last_block_hash")}
        for i, page in enumerate(pages):
            parent = str(page.get("first_parent_hash") or "").lower()
            if i not in dropped and parent and parent in bad_hashes:
                dropped[i] = "CHAINED_TO_DROPPED_PAGE"
                changed = True
    return dropped


def assemble_segments(profile: Mapping[str, Any], scan_request: Mapping[str, int],
                      pages: Sequence[Mapping[str, Any]], archive_height: int) -> dict[str, Any]:
    """Turn retained query pages into proven block segments.

    A segment starts at its first scanned block and ends at its last scanned block.
    Block timestamps never decrease with block number. So every block before the segment has a
    timestamp at or below first_ts, and every block after it has one at or above last_ts.
    Pages the node could still reorg, pages that repeat other pages and pages that contradict other pages
    are not used. Page ids only label the output.
    """
    last_final = archive_height - profile["finality"]["depth_blocks"]
    low, high = scan_request["from_block"], scan_request["to_block_exclusive"]
    order = sorted(range(len(pages)), key=lambda i: (pages[i]["from_block"], pages[i]["next_block"], pages[i]["page_id"]))
    dropped = _untrusted_pages(pages)
    segments: list[list[Mapping[str, Any]]] = []
    breaks: list[dict[str, Any]] = []
    for i in order:
        page = pages[i]
        pid = page["page_id"]
        current = segments[-1] if segments else None
        end = current[-1]["next_block"] if current else None
        if i in dropped:
            breaks.append({"code": dropped[i], "page_id": pid})
        elif page["from_block"] < low or page["next_block"] > high or page["next_block"] <= page["from_block"]:
            breaks.append({"code": "OUTSIDE_REQUEST", "page_id": pid})
        elif page["next_block"] - 1 > last_final:
            breaks.append({"code": "NOT_FINAL_AT_COLLECTION", "page_id": pid})
        elif current is not None and page["from_block"] < end:
            breaks.append({"code": "OVERLAP", "page_id": pid})
        elif current is not None and page["from_block"] == end:
            current.append(page)
        else:
            if current is not None:
                breaks.append({"code": "BLOCK_GAP", "page_id": pid})
            segments.append([page])
    return {
        "segments": [
            {"first_block": group[0]["from_block"], "end_block_exclusive": group[-1]["next_block"],
             "first_ts": group[0]["first_block_timestamp"], "last_ts": group[-1]["last_block_timestamp"],
             "page_ids": [p["page_id"] for p in group]}
            for group in segments
        ],
        "breaks": breaks,
    }


def covering_segment(segments: Sequence[Mapping[str, Any]], start: int, end: int) -> int | None:
    """Index of a proven segment that holds every block with a timestamp in [start, end), or None."""
    for index, seg in enumerate(segments):
        if seg["first_ts"] < start and end <= seg["last_ts"]:
            return index
    return None


def window_covered(segments: Sequence[Mapping[str, Any]], start: int, end: int) -> bool:
    return covering_segment(segments, start, end) is not None


def _page_contradictions(result: IngestResult, segments: Sequence[Mapping[str, Any]]) -> tuple[list[tuple[int, str]], set[int]]:
    """Trades that disagree with the page record.

    A trade from a block no segment scanned spoils the bucket of its timestamp.
    A trade inside a segment but outside its first and last block times spoils the whole segment.
    """
    outside: list[tuple[int, str]] = []
    bad_segments: set[int] = set()
    for trade in result.trades:
        for index, seg in enumerate(segments):
            if seg["first_block"] <= trade.block_number < seg["end_block_exclusive"]:
                if not seg["first_ts"] <= trade.block_timestamp <= seg["last_ts"]:
                    bad_segments.add(index)
                break
        else:
            outside.append((trade.block_timestamp, "TRADE_OUTSIDE_SCANNED_BLOCKS"))
    return outside, bad_segments


def _contamination(result: IngestResult) -> tuple[list[tuple[int, str]], list[tuple[int, int, str]], bool]:
    located = [(item["block_timestamp"], f"UNSUPPORTED_EVENT_IN_BUCKET:{item['code']}")
               for item in result.rejected if item["block_timestamp"] is not None]
    located += [(ts, f"CONFLICT_IN_BUCKET:{item['kind']}") for item in result.conflicts for ts in item["timestamps"]]
    ranges = [(lo, hi, f"CONFLICT_IN_BUCKET:{item['kind']}") for item in result.conflicts for lo, hi in item["ranges"]]
    ranges += [(lo, hi, f"UNSUPPORTED_EVENT_IN_BUCKET:{item['code']}") for item in result.rejected
               for lo, hi in item["ranges"]]
    return located, ranges, any(item["block_timestamp"] is None for item in result.rejected)


def _trade_view(profile: Mapping[str, Any], trade: Trade) -> dict[str, Any]:
    return {"identity": trade_identity(profile, trade), "price": trade.price,
            "block_timestamp": trade.block_timestamp, "pool_side": trade.pool_side,
            "quote_amount": trade.quote_amount, "base_amount": trade.base_amount,
            "quote_raw": str(trade.quote_raw), "base_raw": str(trade.base_raw)}


def bucketize(profile: Mapping[str, Any], result: IngestResult, segments: Sequence[Mapping[str, Any]],
              window: Mapping[str, str]) -> list[dict[str, Any]]:
    """Five-minute UTC buckets [start, end). Close is the last trade by chain order. Nothing is filled."""
    start, end = epoch(window["start_utc"]), epoch(window["end_utc"])
    if start >= end or start % BUCKET_SECONDS or end % BUCKET_SECONDS:
        raise InvalidInput("WINDOW_NOT_BUCKET_ALIGNED", "window must hold whole five-minute buckets")
    quote_decimals = next(t["decimals"] for t in profile["pool_tokens"] if t["role"] == "QUOTE")
    located, ranges, unlocated = _contamination(result)
    outside, bad_segments = _page_contradictions(result, segments)
    spoiled: dict[int, set[str]] = defaultdict(set)
    for ts, reason in located:
        spoiled[ts - ts % BUCKET_SECONDS].add(reason)
    for lo, hi, reason in ranges:
        for first in range(max(start, lo - lo % BUCKET_SECONDS), min(end, hi + 1), BUCKET_SECONDS):
            spoiled[first].add(reason)
    page_spoiled: dict[int, set[str]] = defaultdict(set)
    for ts, reason in outside:
        page_spoiled[ts - ts % BUCKET_SECONDS].add(reason)
    trades: dict[int, list[Trade]] = defaultdict(list)
    for trade in result.trades:
        trades[trade.block_timestamp - trade.block_timestamp % BUCKET_SECONDS].append(trade)
    buckets = []
    for first in range(start, end, BUCKET_SECONDS):
        cover = covering_segment(segments, first, first + BUCKET_SECONDS)
        covered = cover is not None
        reasons = ([] if covered else ["COVERAGE_NOT_PROVEN"]) + sorted(spoiled.get(first, ()))
        if covered:
            reasons += sorted(page_spoiled.get(first, ()))
            if cover in bad_segments:
                reasons.append("TRADE_CONTRADICTS_PAGE_TIMES")
        if unlocated:
            reasons.append("UNLOCATED_REJECTED_RECORDS")
        members = trades.get(first, [])
        bucket: dict[str, Any] = {"start": iso_utc(first), "end": iso_utc(first + BUCKET_SECONDS), "reasons": reasons,
                                  "trade_count": None, "quote_volume": None, "quote_volume_raw": None, "close": None}
        if not covered:
            bucket["status"] = "INCOMPLETE"
        elif reasons:
            bucket["status"] = "UNQUALIFIED"
        else:
            raw = sum(t.quote_raw for t in members)
            bucket.update(status="COMPLETE_OCCUPIED" if members else "COMPLETE_EMPTY", trade_count=len(members),
                          quote_volume_raw=str(raw), quote_volume=scale_down(raw, quote_decimals),
                          close=_trade_view(profile, members[-1]) if members else None)
        buckets.append(bucket)
    return buckets


def reference_trade(profile: Mapping[str, Any], result: IngestResult, segments: Sequence[Mapping[str, Any]],
                    window: Mapping[str, str]) -> dict[str, Any]:
    """First qualified trade by chain order in [start, end). A missing reference stays missing."""
    start, end = epoch(window["start_utc"]), epoch(window["end_utc"])
    if start >= end:
        raise InvalidInput("WINDOW_ORDER", "window start must be before its end")
    if not window_covered(segments, start, end):
        return {"status": "MISSING_OUTCOME", "reason": "COVERAGE_NOT_PROVEN"}
    located, ranges, unlocated = _contamination(result)
    outside, bad_segments = _page_contradictions(result, segments)
    if (unlocated or any(start <= ts < end for ts, _ in located + outside)
            or any(lo < end and hi >= start for lo, hi, _ in ranges)
            or covering_segment(segments, start, end) in bad_segments):
        return {"status": "MISSING_OUTCOME", "reason": "UNQUALIFIED_RECORDS"}
    for trade in result.trades:
        if start <= trade.block_timestamp < end:
            return {"status": "FOUND", "trade": _trade_view(profile, trade)}
    return {"status": "MISSING_OUTCOME", "reason": "COMPLETE_EMPTY_WINDOW"}


_AVAILABILITY_MODELS = ("ASSUMED_DELAY", "OBSERVED_DELIVERY", "UNKNOWN")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_availability_model(availability: Mapping[str, Any]) -> None:
    if not isinstance(availability, Mapping):
        raise InvalidInput("AVAILABILITY_MODEL", "availability must be an object")
    model = availability.get("model")
    if model not in _AVAILABILITY_MODELS:
        raise InvalidInput("AVAILABILITY_MODEL", f"model must be one of {', '.join(_AVAILABILITY_MODELS)}")
    if model == "ASSUMED_DELAY" and not (_is_int(availability.get("delay_seconds")) and availability["delay_seconds"] >= 0):
        raise InvalidInput("AVAILABILITY_MODEL", "delay_seconds must be a non-negative integer")
    if model == "OBSERVED_DELIVERY":
        evidence = availability.get("basis_evidence")
        if evidence == "COLLECTION_TIME":
            raise InvalidInput("COLLECTION_TIME_IS_NOT_DELIVERY", "collection time cannot stand in for delivery time")
        if evidence != "SOURCE_DELIVERY_RECORD":
            raise InvalidInput("AVAILABILITY_MODEL", "observed delivery needs basis_evidence SOURCE_DELIVERY_RECORD")


def bucket_available_at(availability: Mapping[str, Any], bucket: Mapping[str, Any],
                        delivered: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Earliest time a bucket close or volume may be used. Unknown stays unknown."""
    check_availability_model(availability)
    if bucket["status"] not in _STATUSES:
        raise InvalidInput("BUCKET_STATUS", f"unknown bucket status {bucket['status']!r}")
    unknown = {"at": None, "basis": "UNKNOWN"}
    if bucket["status"] == "INCOMPLETE":
        return {**unknown, "reason": "BUCKET_INCOMPLETE"}
    if bucket["status"] == "UNQUALIFIED":
        return {**unknown, "reason": "BUCKET_UNQUALIFIED"}
    ends = epoch(bucket["end"])
    model = availability["model"]
    if model == "ASSUMED_DELAY":
        return {"at": iso_utc(ends + availability["delay_seconds"]), "basis": "ASSUMED_DELAY"}
    if model == "OBSERVED_DELIVERY":
        arrived = (delivered or {}).get(bucket["start"])
        if arrived is None:
            return {**unknown, "reason": "DELIVERY_NOT_RECORDED"}
        return {"at": iso_utc(max(ends, epoch(arrived))), "basis": "OBSERVED_DELIVERY"}
    return {**unknown, "reason": "AVAILABILITY_UNKNOWN"}


def opportunity_eligibility(decision_utc: str, requirements: Sequence[tuple[str, str]],
                            buckets: Sequence[Mapping[str, Any]], availability: Mapping[str, Any],
                            delivered: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Check each required series at the declared decision time. The decision time never moves."""
    decision = epoch(decision_utc)
    by_start = {bucket["start"]: bucket for bucket in buckets}
    reasons: list[dict[str, str]] = []
    for series, start in requirements:
        if series not in ("price", "quote_volume"):
            raise InvalidInput("SERIES", f"unsupported series {series}")
        bucket = by_start.get(start)
        code: str | None
        if bucket is not None and bucket["status"] not in _STATUSES:
            raise InvalidInput("BUCKET_STATUS", f"unknown bucket status {bucket['status']!r}")
        if bucket is None:
            code = "BUCKET_NOT_IN_WINDOW"
        elif bucket["status"] == "INCOMPLETE":
            code = "COVERAGE_NOT_PROVEN"
        elif bucket["status"] == "UNQUALIFIED":
            code = "UNQUALIFIED_RECORDS"
        elif series == "price" and bucket["status"] == "COMPLETE_EMPTY":
            code = "EMPTY_BUCKET_NO_CLOSE"
        else:
            when = bucket_available_at(availability, bucket, delivered)
            code = when.get("reason") if when["at"] is None else ("LATE_INPUT" if epoch(when["at"]) > decision else None)
        if code:
            reasons.append({"series": series, "bucket_start": start, "code": code})
    return {"decision": decision_utc, "eligible": not reasons, "reasons": reasons}


def validate_schedule(schedule: Mapping[str, Any]) -> tuple[int, int, int]:
    """Decision clock: anchor, period, and how far before a decision the feature bucket ends."""
    anchor, period, offset = epoch(schedule["anchor_utc"]), schedule["period_seconds"], schedule["feature_end_offset_seconds"]
    if not (_is_int(period) and period > 0 and _is_int(offset) and offset >= 0):
        raise InvalidInput("SCHEDULE_VALUE", "period must be positive and offset non-negative integers")
    if period % BUCKET_SECONDS or (anchor - offset) % BUCKET_SECONDS:
        raise InvalidInput("SCHEDULE_NOT_ALIGNED", "decisions must use feature buckets that end on the bucket grid")
    return anchor, period, offset


def decision_times(schedule: Mapping[str, Any], start_utc: str, end_utc: str) -> list[int]:
    anchor, period, _ = validate_schedule(schedule)
    start, end = epoch(start_utc), epoch(end_utc)
    first = anchor + -(-(start - anchor) // period) * period
    return list(range(first, end, period))


def feasibility(claim: Mapping[str, Any], segments: Sequence[Mapping[str, Any]],
                availability: Mapping[str, Any]) -> dict[str, Any]:
    """Most opportunities each partition can hold, counted before any outcome is read.

    This is an upper bound on opportunities, not on independent observations. It does not look at which
    buckets are unqualified, and overlapping outcome windows are not discounted. The caller declares the
    sample floors. There is no default floor. Observed delivery is treated as ready at bucket end here,
    so only an assumed delay or an unknown model can exclude a slot on availability.
    """
    _, _, offset = validate_schedule(claim["schedule"])
    check_availability_model(availability)
    horizon, window, warmup = claim["horizon_seconds"], claim["reference_window_seconds"], claim["warmup_buckets"]
    if not (_is_int(horizon) and horizon > 0 and _is_int(window) and window > 0 and _is_int(warmup) and warmup >= 0):
        raise InvalidInput("CLAIM_VALUE", "horizon and reference window must be positive, warm-up non-negative integers")
    parts = claim["partitions"]
    declared = [(p.get("required_triggered"), p.get("required_control")) for p in parts]
    if any((a is None) != (b is None) for a, b in declared) or (
            any(a is None for a, _ in declared) and any(a is not None for a, _ in declared)):
        raise InvalidInput("FLOOR_INCOMPLETE", "declare both floors for every partition, or for none")
    if any(a is not None and not (_is_int(a) and a >= 1 and _is_int(b) and b >= 1) for a, b in declared):
        raise InvalidInput("FLOOR_VALUE", "floors must be integers of at least 1")
    spans = sorted((epoch(p["start_utc"]), epoch(p["end_utc"])) for p in parts)
    if any(a >= b for a, b in spans):
        raise InvalidInput("PARTITION_ORDER", "each partition must start before it ends")
    if any(spans[i + 1][0] < spans[i][1] for i in range(len(spans) - 1)):
        raise InvalidInput("PARTITIONS_OVERLAP", "partitions must not overlap")
    if all(a is None for a, _ in declared):
        return {"status": "UNDECLARED", "partitions": []}
    delay = availability.get("delay_seconds", 0) if availability["model"] == "ASSUMED_DELAY" else 0
    report = []
    for partition, (triggered, control) in zip(parts, declared):
        slots = decision_times(claim["schedule"], partition["start_utc"], partition["end_utc"])
        end = epoch(partition["end_utc"])
        counts = {"outcome_window": 0, "outcome_coverage": 0, "availability": 0, "warmup": 0}
        usable = 0
        for d in slots:
            if d + horizon + window > end:
                counts["outcome_window"] += 1
            elif not (window_covered(segments, d, d + window) and window_covered(segments, d + horizon, d + horizon + window)):
                counts["outcome_coverage"] += 1
            elif availability["model"] == "UNKNOWN" or d - offset + delay > d:
                counts["availability"] += 1
            elif not window_covered(segments, d - offset - BUCKET_SECONDS * (warmup + 1), d - offset):
                counts["warmup"] += 1
            else:
                usable += 1
        required = None if triggered is None else triggered + control
        report.append({
            "name": partition["name"], "schedule_slots": len(slots), "usable": usable, "required_total": required,
            "shortfall": None if required is None else max(0, required - usable),
            "excluded_outcome_window": counts["outcome_window"], "excluded_outcome_coverage": counts["outcome_coverage"],
            "excluded_availability": counts["availability"], "excluded_warmup": counts["warmup"],
        })
    short = any(item["shortfall"] for item in report)
    return {"status": "INFEASIBLE" if short else "FEASIBLE", "partitions": report}


# ---- profile contract ------------------------------------------------------------------------------

PROFILE_SCHEMA = "p07.market_dataset_profile/1"
RESULT_SCHEMA = "p07.qualification_result/1"
_ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_V2_SIGNATURE = "Swap(address,uint256,uint256,uint256,uint256,address)"
_EXECUTION_ROUTE = {"adapter": "KURU_FLOW_FIXED_INPUT", "identity_state": "UNKNOWN", "identity": None,
                    "qualification": "UNQUALIFIED"}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_P02["canonical_bytes"](value)).hexdigest()


def profile_sha256(profile: Mapping[str, Any]) -> str:
    return canonical_sha256(profile)


def dataset_revision(pages: Sequence[Mapping[str, Any]]) -> str:
    """Digest of page identities only, in page-id order. Retrieval order and timestamps do not change it."""
    identity = sorted(({key: page[key] for key in ("page_id", "from_block", "next_block", "sha256")} for page in pages),
                      key=lambda item: item["page_id"])
    return canonical_sha256(identity)


def _is_address(value: object) -> bool:
    return isinstance(value, str) and _ADDRESS.fullmatch(value) is not None


def profile_problems(profile: Any) -> list[dict[str, str]]:
    """Every contract violation in one pass. An empty list means the profile is well formed.

    Well formed is not qualified. Qualification needs evidence; see qualify().
    """
    found: dict[tuple[str, str], str] = {}

    def bad(code: str, path: str, detail: str) -> None:
        found.setdefault((code, path), detail)

    def closed(node: Any, allowed: set[str], path: str) -> bool:
        if not isinstance(node, Mapping):
            bad("MALFORMED_SECTION", path, "expected an object")
            return False
        for key in node.keys() - allowed:
            bad("UNKNOWN_KEY", f"{path}/{key}", "key is not part of the contract")
        for key in allowed - node.keys():
            bad("MISSING_KEY", f"{path}/{key}", "required key is absent")
        return not (node.keys() ^ allowed)

    top = {"schema_version", "profile_id", "evidence_class", "network", "venue", "pool_tokens", "orientation", "event",
           "conversion", "resolution", "ordering", "source", "availability", "finality", "execution_route",
           "unmodeled_effects", "dataset"}
    if not closed(profile, top, ""):
        return _problem_list(found)
    if profile["schema_version"] != PROFILE_SCHEMA:
        bad("SCHEMA_VERSION", "/schema_version", f"expected {PROFILE_SCHEMA}")
    if not isinstance(profile["profile_id"], str) or not profile["profile_id"]:
        bad("PROFILE_ID", "/profile_id", "profile_id must be a nonempty string")
    if profile["evidence_class"] not in ("SYNTHETIC_FIXTURE", "RETAINED_REPORT", "REAL_SOURCE"):
        bad("EVIDENCE_CLASS", "/evidence_class", "unknown evidence class")

    net = profile["network"]
    if closed(net, {"network", "chain_id", "chain_id_source"}, "/network"):
        chain = net["chain_id"]
        if net["network"] != "MONAD":
            bad("NETWORK", "/network/network", "only MONAD is defined")
        known = isinstance(chain, int) and not isinstance(chain, bool) and chain >= 1
        if net["chain_id_source"] not in ("PROVIDER_READ", "DOCUMENTATION", "UNKNOWN") or (
                known != (net["chain_id_source"] != "UNKNOWN")) or (chain is not None and not known):
            bad("CHAIN_ID", "/network", "chain_id and chain_id_source must agree")

    venue = profile["venue"]
    pool = venue.get("pool_address") if isinstance(venue, Mapping) else None
    if closed(venue, {"underlying_venue", "pool_family", "pool_address"}, "/venue"):
        if venue["pool_family"] != "UNISWAP_V2_COMPATIBLE":
            bad("POOL_FAMILY", "/venue/pool_family", "only UNISWAP_V2_COMPATIBLE is defined")
        if not _is_address(pool):
            bad("ADDRESS_FORMAT", "/venue/pool_address", "use 0x and 40 lowercase hex digits")
        if not isinstance(venue["underlying_venue"], str) or not venue["underlying_venue"]:
            bad("VENUE", "/venue/underlying_venue", "nonempty string required")

    tokens = profile["pool_tokens"]
    if not isinstance(tokens, list) or len(tokens) != 2:
        bad("TOKEN_COUNT", "/pool_tokens", "exactly two pool tokens in pool order")
    else:
        for i, token in enumerate(tokens):
            where = f"/pool_tokens/{i}"
            if not closed(token, {"address", "symbol_label", "kind", "decimals", "role"}, where):
                continue
            if not _is_address(token["address"]):
                bad("ADDRESS_FORMAT", f"{where}/address", "use 0x and 40 lowercase hex digits")
            if token["kind"] == "NATIVE":
                bad("NATIVE_ASSET_NOT_A_POOL_LEG", f"{where}/kind", "a pool leg is an ERC-20 token. WMON is not native MON")
            elif token["kind"] not in ("ERC20", "WRAPPED_NATIVE_ERC20"):
                bad("TOKEN_KIND", f"{where}/kind", "unknown token kind")
            if not _is_int(token["decimals"]) or not 0 <= token["decimals"] <= 255:
                bad("DECIMALS_RANGE", f"{where}/decimals", "integer from 0 to 255")
        if sorted(str(t.get("role")) for t in tokens if isinstance(t, Mapping)) != ["BASE", "QUOTE"]:
            bad("TOKEN_ROLES", "/pool_tokens", "one BASE and one QUOTE")
        addresses = [t.get("address") for t in tokens if isinstance(t, Mapping) and _is_address(t.get("address"))]
        if len(set(addresses)) != len(addresses):
            bad("TOKEN_ADDRESSES", "/pool_tokens", "token addresses must differ")
        if pool in addresses:
            bad("POOL_IS_TOKEN", "/venue/pool_address", "the pool address is also a token address")
    if profile["orientation"] != "QUOTE_PER_BASE":
        bad("ORIENTATION", "/orientation", "price is quote per base")

    event = profile["event"]
    if closed(event, {"event_schema_version", "signature", "topic0"}, "/event"):
        if event["event_schema_version"] != "uniswap-v2-swap/1":
            bad("EVENT_SCHEMA", "/event/event_schema_version", "only uniswap-v2-swap/1 is defined")
        if event["signature"] != _V2_SIGNATURE:
            bad("EVENT_SIGNATURE", "/event/signature", "only the V2 Swap signature is defined")
        elif event["topic0"] != "0x" + keccak256(_V2_SIGNATURE.encode()).hex():
            bad("TOPIC0_NOT_SIGNATURE_HASH", "/event/topic0", "topic0 must be the Keccak-256 of the signature")
    conversion = profile["conversion"]
    if closed(conversion, {"amount_conversion_version", "numeric", "measurement"}, "/conversion"):
        if conversion["amount_conversion_version"] != "v2-swap-quote-per-base-pool-gross/1":
            bad("CONVERSION_VERSION", "/conversion/amount_conversion_version", "unknown conversion version")
        if conversion["numeric"] != "decimal-50-half-even/1":
            bad("NUMERIC", "/conversion/numeric", "accepted numeric profile is decimal-50-half-even/1")
        if conversion["measurement"] != "POOL_GROSS":
            bad("MEASUREMENT", "/conversion/measurement", "amounts are pool-gross. Trader-net is not defined")
    if profile["resolution"] != {"bucket_seconds": BUCKET_SECONDS, "interval": "[start,end)"}:
        bad("RESOLUTION", "/resolution", "five-minute UTC buckets, start inclusive, end exclusive")
    if profile["ordering"] != {"key": ["block_number", "transaction_index", "log_index"]}:
        bad("ORDERING", "/ordering", "order by block number, transaction index, log index")
    if profile["source"] != {"history_provider": "ENVIO_HYPERSYNC", "corroboration_provider": "QUICKNODE_JSON_RPC",
                             "data_route": "ENVIO_QUICKNODE_CORROBORATED"}:
        bad("SOURCE", "/source", "accepted route is Envio history with QuickNode corroboration")

    availability = profile["availability"]
    if not isinstance(availability, Mapping):
        bad("MALFORMED_SECTION", "/availability", "expected an object")
    else:
        for key in availability.keys() - {"model", "delay_seconds", "basis_evidence"}:
            bad("UNKNOWN_KEY", f"/availability/{key}", "key is not part of the contract")
        try:
            check_availability_model(availability)
        except InvalidInput as error:
            bad(error.code, "/availability", error.args[0])
    finality = profile["finality"]
    if closed(finality, {"depth_blocks", "basis"}, "/finality"):
        if not _is_int(finality["depth_blocks"]) or finality["depth_blocks"] < 1 or finality["basis"] not in (
                "DOCUMENTATION", "MEASURED", "UNKNOWN"):
            bad("FINALITY", "/finality", "depth is a positive integer. basis is DOCUMENTATION, MEASURED or UNKNOWN")
    if profile["execution_route"] != _EXECUTION_ROUTE:
        bad("EXECUTION_ROUTE_MUST_STAY_SEPARATE", "/execution_route",
            "research profile carries only the unqualified route placeholder")
    effects = profile["unmodeled_effects"]
    if not isinstance(effects, list) or not effects or not all(isinstance(e, str) for e in effects):
        bad("UNMODELED_EFFECTS", "/unmodeled_effects", "list the effects this profile leaves out")
    _dataset_problems(profile, pool, bad, closed)
    return _problem_list(found)


def _problem_list(found: Mapping[tuple[str, str], str]) -> list[dict[str, str]]:
    return [{"code": code, "path": path, "detail": detail} for (code, path), detail in sorted(found.items())]


def _dataset_problems(profile: Mapping[str, Any], pool: object, bad: Any, closed: Any) -> None:
    dataset = profile["dataset"]
    if not closed(dataset, {"window", "collection", "query", "pages", "dataset_revision"}, "/dataset"):
        return
    window_end: int | None = None
    window = dataset["window"]
    if closed(window, {"start_utc", "end_utc"}, "/dataset/window"):
        try:
            begin, window_end = epoch(window["start_utc"]), epoch(window["end_utc"])
            if begin >= window_end or begin % BUCKET_SECONDS or window_end % BUCKET_SECONDS:
                bad("WINDOW", "/dataset/window", "whole five-minute buckets, start before end")
        except InvalidInput as error:
            bad("WINDOW", "/dataset/window", error.args[0])
    collection = dataset["collection"]
    if closed(collection, {"collected_at_utc", "collected_on_utc", "archive_height"}, "/dataset/collection"):
        at, day = collection["collected_at_utc"], collection["collected_on_utc"]
        if (at is None) == (day is None) or not (at is None or isinstance(at, str)) or not (
                day is None or isinstance(day, str)):
            bad("COLLECTION", "/dataset/collection", "give collected_at_utc or collected_on_utc, as text")
            at = day = None
        try:
            if at is not None and window_end is not None and epoch(at) < window_end:
                bad("COLLECTED_BEFORE_WINDOW_END", "/dataset/collection", "collection cannot precede the window end")
            if day is not None:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
                    bad("COLLECTION", "/dataset/collection", "collected_on_utc is YYYY-MM-DD")
                elif window_end is not None and day < iso_utc(window_end)[:10]:
                    bad("COLLECTED_BEFORE_WINDOW_END", "/dataset/collection", "collection cannot precede the window end")
        except InvalidInput as error:
            bad("COLLECTION", "/dataset/collection", error.args[0])
        height = collection["archive_height"]
        if height is not None and not (_is_int(height) and height >= 0):
            bad("COLLECTION", "/dataset/collection/archive_height", "non-negative integer or null")
    query = dataset["query"]
    if closed(query, {"identity_sha256", "definition", "from_block", "to_block_exclusive"}, "/dataset/query"):
        definition = query["definition"]
        if definition is None:
            if query["identity_sha256"] is not None:
                bad("QUERY_IDENTITY_MISMATCH", "/dataset/query", "identity without a definition")
        else:
            try:
                if query["identity_sha256"] != canonical_sha256(definition):
                    bad("QUERY_IDENTITY_MISMATCH", "/dataset/query/identity_sha256", "hash of the definition differs")
            except ValueError:
                bad("QUERY_IDENTITY_MISMATCH", "/dataset/query/definition", "definition is not canonical JSON")
            if not (isinstance(definition, Mapping) and definition.get("address") == pool
                    and definition.get("topic0") == _look(profile, "event", "topic0")
                    and definition.get("from_block") == query["from_block"]
                    and definition.get("to_block_exclusive") == query["to_block_exclusive"]):
                bad("QUERY_DEFINITION_MISMATCH", "/dataset/query/definition", "query must target this pool, event and range")
    pages, revision = dataset["pages"], dataset["dataset_revision"]
    if not isinstance(pages, list):
        bad("PAGE_RECORD", "/dataset/pages", "expected a list")
        return
    ids = [pg.get("page_id") for pg in pages if isinstance(pg, Mapping)]
    needed = ("page_id", "from_block", "next_block", "sha256", "first_block_timestamp", "last_block_timestamp")
    numbers = ("from_block", "next_block", "first_block_timestamp", "last_block_timestamp")

    def page_ok(pg: Any) -> bool:
        return (isinstance(pg, Mapping) and all(k in pg for k in needed) and isinstance(pg["page_id"], str)
                and all(_is_int(pg[k]) and pg[k] >= 0 for k in numbers) and pg["next_block"] > pg["from_block"]
                and isinstance(pg["sha256"], str) and _SHA256.fullmatch(pg["sha256"]) is not None
                and all(pg.get(k) is None or (isinstance(pg[k], str) and _HEX_WORD.fullmatch(pg[k]) is not None)
                        for k in ("first_parent_hash", "last_block_hash")))

    if not all(page_ok(pg) for pg in pages) or len(set(ids)) != len(ids):
        bad("PAGE_RECORD", "/dataset/pages", "pages need unique text ids, non-negative integer ranges and times, and hex hashes")
        return
    if pages and _look(dataset, "collection", "archive_height") is None:
        bad("ARCHIVE_HEIGHT_MISSING", "/dataset/collection/archive_height", "finality of the pages needs the archive height")
    if closed(revision, {"basis", "manifest_sha256", "page_count", "row_count"}, "/dataset/dataset_revision"):
        basis, manifest = revision["basis"], revision["manifest_sha256"]
        consistent = {
            "NONE": manifest is None and not pages and revision["page_count"] == 0,
            "PAGE_DIGESTS": bool(pages) and manifest == dataset_revision(pages) and revision["page_count"] == len(pages),
            "PRIVATE_NOT_PORTABLE": not pages and _is_int(revision["page_count"]) and revision["page_count"] >= 0,
        }.get(basis) if isinstance(basis, str) else False
        if not consistent:
            bad("DATASET_REVISION_MISMATCH", "/dataset/dataset_revision", "manifest, basis and pages disagree")
        rows = revision["row_count"]
        if not ((rows is None and basis != "PAGE_DIGESTS") or (_is_int(rows) and rows >= 0)):
            bad("ROW_COUNT", "/dataset/dataset_revision/row_count", "non-negative integer, required for PAGE_DIGESTS")


def research_binding_view(profile: Mapping[str, Any]) -> dict[str, Any]:
    """The accepted P02 ResearchBinding fields, minus evidence_class and qualification.

    P02 token_order is [base, quote]. It is not the pool's token0/token1 order. Pool order stays in the profile.
    """
    base = next(t for t in profile["pool_tokens"] if t["role"] == "BASE")
    quote = next(t for t in profile["pool_tokens"] if t["role"] == "QUOTE")
    return {
        "chain_id": profile["network"]["chain_id"], "underlying_venue": profile["venue"]["underlying_venue"],
        "pool_address": profile["venue"]["pool_address"], "token_order": [base["address"], quote["address"]],
        "base_asset": base["address"], "quote_asset": quote["address"], "orientation": profile["orientation"],
        "base_decimals": base["decimals"], "quote_decimals": quote["decimals"],
        "event_schema_version": profile["event"]["event_schema_version"],
        "amount_conversion_version": profile["conversion"]["amount_conversion_version"],
        "data_route": profile["source"]["data_route"],
    }


_COMPAT_CODES = {
    "chain_id": "CHAIN_MISMATCH", "underlying_venue": "VENUE_MISMATCH", "pool_address": "POOL_MISMATCH",
    "token_order": "TOKEN_ORDER_MISMATCH", "base_asset": "BASE_ASSET_MISMATCH", "quote_asset": "QUOTE_ASSET_MISMATCH",
    "orientation": "ORIENTATION_MISMATCH", "base_decimals": "DECIMALS_MISMATCH", "quote_decimals": "DECIMALS_MISMATCH",
    "event_schema_version": "EVENT_SCHEMA_MISMATCH", "amount_conversion_version": "CONVERSION_VERSION_MISMATCH",
    "data_route": "DATA_ROUTE_MISMATCH",
}


def binding_incompatibilities(profile: Mapping[str, Any], other: Mapping[str, Any]) -> list[str]:
    """Reasons another binding cannot share this profile's qualification. Symbols never count."""
    mine = research_binding_view(profile)
    codes = set()
    for key, code in _COMPAT_CODES.items():
        if key not in other:
            codes.add(f"FIELD_MISSING:{key}")
        elif other[key] != mine[key]:
            codes.add(code)
    if "quote_asset_kind" in other:
        kind = next(t for t in profile["pool_tokens"] if t["role"] == "QUOTE")["kind"]
        if other["quote_asset_kind"] != kind:
            codes.add("NATIVE_VERSUS_WRAPPED" if "NATIVE" in (kind, other["quote_asset_kind"]) else "QUOTE_KIND_MISMATCH")
    return sorted(codes)


class BindingNotEmittable(ValueError):
    """The profile cannot become a P02 ResearchBinding. The code says why."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def to_p02_binding(profile: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Project to the accepted P02 record.

    P02 has no LIMITED state. A limited or unresolved real profile stays a P07 result and is not projected.
    """
    if not isinstance(result, Mapping):
        raise BindingNotEmittable("RESULT_MALFORMED", "result is not an object")
    try:
        digest = profile_sha256(profile)
    except ValueError as error:
        raise BindingNotEmittable("PROFILE_INVALID", str(error)) from error
    if result.get("profile_sha256") != digest:
        raise BindingNotEmittable("RESULT_FOR_OTHER_PROFILE", "qualification result was produced for another profile")
    claims = result.get("claims")
    rank = {"QUALIFIED": 0, "LIMITED": 1, "UNRESOLVED": 2}
    if not (result.get("schema_version") == RESULT_SCHEMA and result.get("scope") == "OFFLINE_CONTRACT_ONLY"
            and isinstance(result.get("observations_sha256"), str) and isinstance(claims, Mapping)
            and set(claims) == set(CLAIMS)
            and all(isinstance(c, Mapping) and isinstance(c.get("verdict"), str) and c["verdict"] in rank
                    for c in claims.values())
            and result.get("overall") == max((c["verdict"] for c in claims.values()), key=rank.__getitem__)):
        raise BindingNotEmittable("RESULT_MALFORMED", "result is not a complete qualification result")
    if profile_problems(profile):
        raise BindingNotEmittable("PROFILE_INVALID", "profile violates the contract")
    if profile["evidence_class"] == "SYNTHETIC_FIXTURE":
        evidence_class, qualification = "SYNTHETIC_FIXTURE", "UNQUALIFIED"
    elif result["overall"] == "QUALIFIED":
        evidence_class, qualification = "QUALIFIED_SOURCE", "QUALIFIED"
    else:
        raise BindingNotEmittable(f"VERDICT_{result['overall']}", "P02 can only carry a fully qualified real binding")
    binding = {**research_binding_view(profile), "evidence_class": evidence_class, "qualification": qualification}
    try:
        _P02["validate_record"]("ResearchBinding", binding)
    except ValueError as error:
        raise BindingNotEmittable("P02_REJECTED", str(error)) from error
    return binding


# ---- per-claim qualification -----------------------------------------------------------------------

CLAIMS = ("BINDING_IDENTITY", "EVENT_AND_AMOUNT_MEANING", "HISTORY_COMPLETENESS_AND_ORDER",
          "POINT_IN_TIME_AVAILABILITY", "SCHEDULE_FEASIBILITY")
NOT_ASSESSED = ("EXECUTION_ATTAINABILITY", "PROFITABILITY_OR_VALIDATION", "TRADER_NET_FILL_OR_PROFIT")
_STATUSES = ("COMPLETE_OCCUPIED", "COMPLETE_EMPTY", "INCOMPLETE", "UNQUALIFIED")
_ORDER_CODES = {"ORDER_FIELD_MISSING", "IDENTITY_FIELD_MISSING", "TIME_FIELD_MISSING"}


def bucket_status_counts(buckets: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(bucket["status"] for bucket in buckets)
    return {status: counts.get(status, 0) for status in _STATUSES}


def history_observations(profile: Mapping[str, Any], logs: Sequence[Mapping[str, Any]],
                         window: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Run the offline pipeline on retained pages and logs. Output feeds qualify()."""
    dataset = profile["dataset"]
    height = dataset["collection"]["archive_height"]
    if dataset["pages"] and height is None:
        raise InvalidInput("ARCHIVE_HEIGHT_MISSING", "finality needs the archive height at collection")
    assembled = assemble_segments(profile, dataset["query"], dataset["pages"], height or 0)
    result = ingest(profile, logs)
    buckets = bucketize(profile, result, assembled["segments"], window or dataset["window"])
    used = window or dataset["window"]
    return {"ingest": result.summary(), "bucket_status_counts": bucket_status_counts(buckets),
            "bucket_window": {"start_utc": used["start_utc"], "end_utc": used["end_utc"]},
            "segment_breaks": [item["code"] for item in assembled["breaks"]]}


def _count(value: object, minimum: int = 0) -> int | None:
    """A count is a real integer at or above its minimum. Booleans and text are not counts."""
    return value if _is_int(value) and value >= minimum else None  # type: ignore[return-value]


def _look(observations: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(observations, Mapping) or key not in observations:
            return None
        observations = observations[key]
    return observations


class _Claim:
    def __init__(self) -> None:
        self.reasons: list[dict[str, str]] = []

    def add(self, kind: str, code: str, detail: str = "") -> None:
        if not any(r["code"] == code and r["kind"] == kind for r in self.reasons):
            self.reasons.append({"code": code, "kind": kind, "detail": detail})

    def verdict(self) -> str:
        kinds = {reason["kind"] for reason in self.reasons}
        if kinds & {"FAILED_CHECK", "MISSING_EVIDENCE"}:
            return "UNRESOLVED"
        return "LIMITED" if kinds & {"ASSUMPTION", "LIMIT"} else "QUALIFIED"

    def view(self) -> dict[str, Any]:
        return {"verdict": self.verdict(), "reasons": self.reasons}


def _check_bucket_counts(claim: "_Claim", profile: Mapping[str, Any], observations: Any, counts: Mapping[str, int],
                         trades: int | None) -> None:
    """Tie the bucket counts to the profile window, the trade count and the retained pages."""
    window = _look(observations, "bucket_window") or _look(profile, "dataset", "window")
    try:
        start, end = epoch(window["start_utc"]), epoch(window["end_utc"])
        if start >= end or start % BUCKET_SECONDS or end % BUCKET_SECONDS:
            raise InvalidInput("WINDOW", "bad window")
        outer = _look(profile, "dataset", "window")
        if start < epoch(outer["start_utc"]) or end > epoch(outer["end_utc"]):
            claim.add("FAILED_CHECK", "BUCKET_WINDOW_OUTSIDE_PROFILE")
            return
        if (start, end) != (epoch(outer["start_utc"]), epoch(outer["end_utc"])):
            claim.add("LIMIT", "SUBWINDOW_ONLY", "only part of the profile window was counted")
    except (InvalidInput, KeyError, TypeError):
        claim.add("MISSING_EVIDENCE", "BUCKET_WINDOW_INVALID")
        return
    complete = counts["COMPLETE_OCCUPIED"] + counts["COMPLETE_EMPTY"]
    if sum(counts[status] for status in _STATUSES) != (end - start) // BUCKET_SECONDS:
        claim.add("FAILED_CHECK", "BUCKET_COUNTS_INCONSISTENT", "counts do not add up to the window")
    if trades is not None and counts["COMPLETE_OCCUPIED"] > trades:
        claim.add("FAILED_CHECK", "BUCKET_COUNTS_INCONSISTENT", "more occupied buckets than trades")
    rows = _look(profile, "dataset", "dataset_revision", "row_count")
    if trades is not None and _look(profile, "dataset", "dataset_revision", "basis") == "PAGE_DIGESTS" and (
            not _is_int(rows) or rows < trades):
        claim.add("FAILED_CHECK", "INGEST_COUNTS_INCONSISTENT", "the retained pages hold fewer rows than trades")
    dataset = _look(profile, "dataset")
    if isinstance(dataset, Mapping) and dataset.get("pages") and not profile_problems(profile):
        try:
            height = dataset["collection"]["archive_height"]
            assembled = assemble_segments(profile, dataset["query"], dataset["pages"], height)
            proven = sum(1 for first in range(start, end, BUCKET_SECONDS)
                         if window_covered(assembled["segments"], first, first + BUCKET_SECONDS))
        except (KeyError, TypeError):
            claim.add("MISSING_EVIDENCE", "PAGES_UNUSABLE")
            return
        if complete > proven:
            claim.add("FAILED_CHECK", "COVERAGE_CLAIM_EXCEEDS_PAGES", f"{complete} claimed, {proven} proven by the pages")


def _history_window(profile: Mapping[str, Any], observations: Any) -> Any:
    window = _look(observations, "bucket_window") or _look(profile, "dataset", "window")
    if isinstance(window, Mapping) and {"start_utc", "end_utc"} <= window.keys():
        return {"start_utc": window["start_utc"], "end_utc": window["end_utc"]}
    return None


def qualify(profile: Mapping[str, Any], observations: Mapping[str, Any]) -> dict[str, Any]:
    """One verdict per claim. Missing or unrecognized evidence is never a pass.

    QUALIFIED needs direct evidence. LIMITED names an assumption or a limit. UNRESOLVED names a failed
    check or missing evidence. Execution, trader-net fills and profit are outside this result.
    """
    if not isinstance(profile, Mapping):
        raise InvalidInput("PROFILE_NOT_OBJECT", "profile must be an object")
    claims = {name: _Claim() for name in CLAIMS}

    binding = claims["BINDING_IDENTITY"]
    try:
        profile_digest: str | None = profile_sha256(profile)
    except ValueError:
        profile_digest = None
        binding.add("FAILED_CHECK", "PROFILE_NOT_CANONICAL", "floats or non-JSON values are not allowed")
    for problem in profile_problems(profile):
        binding.add("FAILED_CHECK", f"PROFILE_INVALID:{problem['code']}", problem["path"])
    chain = _look(profile, "network", "chain_id")
    source = _look(observations, "binding", "chain_id")
    if profile.get("evidence_class") == "RETAINED_REPORT":
        binding.add("LIMIT", "RETAINED_REPORT_NOT_REVERIFIED", "figures come from a report, not a fresh read")
    if source in ("PROVIDER_READ", "DOCUMENTATION") and source != _look(profile, "network", "chain_id_source"):
        binding.add("FAILED_CHECK", "CHAIN_ID_SOURCE_CONTRADICTION", "profile and observation name different sources")
    if chain is None:
        binding.add("MISSING_EVIDENCE", "CHAIN_ID_UNKNOWN")
    elif source == "DOCUMENTATION":
        binding.add("ASSUMPTION", "CHAIN_ID_FROM_DOCUMENTATION_ONLY", "no provider eth_chainId read recorded")
    elif source != "PROVIDER_READ":
        binding.add("MISSING_EVIDENCE", "CHAIN_ID_UNVERIFIED")
    for key, good, weak, label in (("pool_tokens", "CORROBORATED_READ", "SINGLE_READ", "POOL_TOKENS"),
                                   ("pool_venue", "CORROBORATED", "SINGLE_SOURCE", "POOL_VENUE")):
        seen = _look(observations, "binding", key)
        if seen == weak:
            binding.add("LIMIT", f"{label}_{weak}")
        elif seen != good:
            binding.add("MISSING_EVIDENCE", f"{label}_UNVERIFIED")

    event = claims["EVENT_AND_AMOUNT_MEANING"]
    trades = _count(_look(observations, "ingest", "trades"), 1)
    if trades is None:
        event.add("MISSING_EVIDENCE", "NO_EVENT_SAMPLE")
    sides = _look(observations, "ingest", "pool_sides")
    if not isinstance(sides, list) or not sides or not all(isinstance(x, str) for x in sides):
        event.add("MISSING_EVIDENCE", "POOL_SIDES_NOT_REPORTED")
    elif trades is not None and len(set(sides)) > trades:
        event.add("FAILED_CHECK", "POOL_SIDES_EXCEED_TRADES", "one trade has one side")
    elif set(sides) != {"QUOTE_IN_BASE_OUT", "BASE_IN_QUOTE_OUT"}:
        event.add("LIMIT", "ONE_POOL_SIDE_ONLY", ", ".join(sorted(sides)))
    for role in ("base", "quote"):
        reads = _look(observations, "event_meaning", "decimals", role)
        if not isinstance(reads, Mapping):
            event.add("MISSING_EVIDENCE", f"DECIMALS_NOT_READ:{role}")
        elif reads.get("window_start") != "READ":
            if "READ" in (reads.get("window_end"), reads.get("current")):
                event.add("ASSUMPTION", f"DECIMALS_IMMUTABILITY_ASSUMED:{role}", "no read at the window start")
            else:
                event.add("MISSING_EVIDENCE", f"DECIMALS_NOT_READ:{role}")
    if _look(observations, "event_meaning", "fee_transfer_semantics") != "QUALIFIED":
        event.add("LIMIT", "TOKEN_MECHANICS_UNQUALIFIED", "amounts are pool-gross only")

    history = claims["HISTORY_COMPLETENESS_AND_ORDER"]
    if trades is None:
        history.add("MISSING_EVIDENCE", "INGEST_COUNTS_MALFORMED")
    conflicts = _count(_look(observations, "ingest", "conflicts"))
    if conflicts is None:
        history.add("MISSING_EVIDENCE", "CONFLICT_COUNT_NOT_REPORTED")
    elif conflicts:
        history.add("FAILED_CHECK", "CONFLICTING_RECORDS", f"{conflicts} held out")
    codes = _look(observations, "ingest", "rejected_codes")
    if not isinstance(codes, Mapping) or any(_count(n) is None for n in codes.values()):
        history.add("MISSING_EVIDENCE", "UNSUPPORTED_EVENT_COUNT_NOT_REPORTED")
    else:
        if _ORDER_CODES & {code for code, n in codes.items() if n}:
            history.add("FAILED_CHECK", "ORDER_OR_IDENTITY_FIELDS_MISSING")
        if sum(n for code, n in codes.items() if code not in _ORDER_CODES):
            history.add("LIMIT", "UNSUPPORTED_EVENTS_PRESENT")
        total = _count(_look(observations, "ingest", "rejected"))
        if total is None:
            history.add("MISSING_EVIDENCE", "REJECTED_TOTAL_NOT_REPORTED")
        elif total != sum(codes.values()):
            history.add("FAILED_CHECK", "INGEST_COUNTS_INCONSISTENT", "rejected total differs from its codes")
    for field_name, label in (("unlocated_rejections", "UNLOCATED"), ("removed", "REMOVED"), ("foreign", "FOREIGN")):
        seen = _count(_look(observations, "ingest", field_name))
        if seen is None:
            history.add("MISSING_EVIDENCE", f"{label}_COUNT_NOT_REPORTED")
        elif seen and field_name == "unlocated_rejections":
            history.add("FAILED_CHECK", "UNLOCATED_RECORDS", "a rejected record has no timestamp")
        elif seen and field_name == "removed":
            history.add("LIMIT", "REMOVED_LOGS_PRESENT")
        elif seen:
            history.add("LIMIT", "FOREIGN_RECORDS_IN_QUERY_RESULT")
    if profile.get("evidence_class") in ("REAL_SOURCE", "RETAINED_REPORT") and _look(
            profile, "dataset", "dataset_revision", "basis") != "PAGE_DIGESTS":
        history.add("MISSING_EVIDENCE", "COVERAGE_PROOF_NOT_PORTABLE", "pages and their revision must travel with the profile")
    if profile.get("evidence_class") == "RETAINED_REPORT":
        history.add("LIMIT", "RETAINED_REPORT_NOT_REVERIFIED")
    counts = _look(observations, "bucket_status_counts")
    if not isinstance(counts, Mapping) or any(_count(counts.get(status)) is None for status in _STATUSES):
        history.add("MISSING_EVIDENCE", "COVERAGE_PROOF_NOT_PORTABLE")
    else:
        _check_bucket_counts(history, profile, observations, counts, trades)
        if counts["COMPLETE_OCCUPIED"] + counts["COMPLETE_EMPTY"] == 0:
            history.add("MISSING_EVIDENCE", "NO_PROVEN_BUCKET")
        elif counts["INCOMPLETE"] + counts["UNQUALIFIED"]:
            history.add("LIMIT", f"BUCKET_GAPS:{counts['INCOMPLETE'] + counts['UNQUALIFIED']}")
    check = _look(observations, "corroboration")
    kind = _look(check, "class")
    mismatches = _count(_look(check, "mismatches"))
    sample, population = _count(_look(check, "sample_size"), 1), _count(_look(check, "population_size"), 1)
    if kind not in ("COMPLETE", "SAMPLED"):
        history.add("MISSING_EVIDENCE", "NO_CORROBORATION")
    elif _look(check, "provider") != _look(profile, "source", "corroboration_provider"):
        history.add("FAILED_CHECK", "CORROBORATION_PROVIDER_MISMATCH", "the corroborating source must be independent of the history source")
    elif mismatches is None:
        history.add("MISSING_EVIDENCE", "CORROBORATION_RESULT_NOT_REPORTED")
    elif mismatches:
        history.add("FAILED_CHECK", "CORROBORATION_MISMATCH", f"{mismatches} differ")
    elif sample is None or population is None or sample > population or (
            kind == "COMPLETE" and (sample != population or (trades is not None and population < trades))):
        history.add("FAILED_CHECK", "CORROBORATION_CLASS_INCONSISTENT",
                    "complete needs every record compared, and at least as many records as trades")
    elif kind == "SAMPLED":
        history.add("LIMIT", "CORROBORATION_SAMPLED_ONLY", f"{sample} of {population}")

    timing = claims["POINT_IN_TIME_AVAILABILITY"]
    model = None
    try:
        check_availability_model(profile["availability"])
        model = profile["availability"]["model"]
    except (InvalidInput, KeyError, TypeError) as error:
        timing.add("FAILED_CHECK", getattr(error, "code", "AVAILABILITY_MODEL"))
    if model == "UNKNOWN":
        timing.add("MISSING_EVIDENCE", "AVAILABILITY_UNKNOWN")
    elif model == "ASSUMED_DELAY":
        timing.add("ASSUMPTION", "AVAILABILITY_RECONSTRUCTED_NOT_OBSERVED", "original delivery time is not known")
    finality = _look(observations, "finality_at_collection")
    if model and model != "UNKNOWN":
        if finality == "FINALIZED_BY_DEPTH":
            timing.add("ASSUMPTION", "FINALITY_INFERRED_AT_COLLECTION_ONLY", "original finality is not known")
        elif finality != "OBSERVED_FINAL":
            if model == "ASSUMED_DELAY":
                timing.add("ASSUMPTION", "FINALITY_UNKNOWN_CLAIM_RESTRICTED")
            else:
                timing.add("MISSING_EVIDENCE", "FINALITY_UNKNOWN")

    schedule = claims["SCHEDULE_FEASIBILITY"]
    status = _look(observations, "feasibility", "status")
    shown = _look(observations, "feasibility", "partitions")
    if status == "FEASIBLE" and not (isinstance(shown, list) and shown and all(
            isinstance(row, Mapping) and _count(row.get("shortfall")) == 0 for row in shown)):
        status = "UNVERIFIED"
    if status == "INFEASIBLE":
        schedule.add("FAILED_CHECK", "INFEASIBLE_BEFORE_OUTCOMES", "declared sample floors cannot be met")
    elif status != "FEASIBLE":
        schedule.add("MISSING_EVIDENCE", "SCHEDULE_OR_SAMPLE_FLOOR_UNDECLARED" if status in (None, "UNDECLARED")
                     else "FEASIBILITY_UNKNOWN")

    views = {name: claim.view() for name, claim in claims.items()}
    verdicts = {view["verdict"] for view in views.values()}
    overall = "UNRESOLVED" if "UNRESOLVED" in verdicts else "LIMITED" if "LIMITED" in verdicts else "QUALIFIED"
    try:
        evidence_digest = canonical_sha256(observations)
    except ValueError as error:
        raise InvalidInput("OBSERVATIONS_NOT_CANONICAL", str(error)) from error
    return {"schema_version": RESULT_SCHEMA, "profile_id": profile.get("profile_id"),
            "profile_sha256": profile_digest, "observations_sha256": evidence_digest,
            "scope": "OFFLINE_CONTRACT_ONLY", "history_window": _history_window(profile, observations), "claims": views,
            "overall": overall, "not_assessed": sorted(NOT_ASSESSED)}
