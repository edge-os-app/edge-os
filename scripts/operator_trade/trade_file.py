"""Frozen operator trade file: strict fields, frozen pins and the operator's own limits.

This file is an authority input, not a live configuration. ``--live`` requires its SHA256 on the
command line. It holds no credential: the Privy app id, app secret and agent key file come only
from named environment variables at run time.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from edge_os_api.kuru_flow.types import canonical_raw, is_address

from scripts.operator_trade.errors import OperatorError

FIELDS = frozenset({
    "version", "chain_id", "wallet_address", "wallet_id", "wmon", "moe", "pool", "entrypoint",
    "token0", "token1", "direction", "program_fee_ppm", "input_raw", "slippage_bps", "usd_ceiling",
    "mon_usd_price", "gas_limits", "code_sha256", "receipt_timeout_seconds", "receipt_poll_seconds",
})
GAS_FIELDS = frozenset({"wrap", "approve", "swap", "revoke"})
CODE_ROLES = frozenset({"entrypoint", "wmon", "pool"})
MAX_RAW_DIGITS = 78
POLICY_MAX_INPUT = 70 * 10**18
ABSOLUTE_USD_CEILING = Decimal("2.00")
MAX_GAS_LIMIT = 30_000_000
MAX_RECEIPT_SECONDS = 600.0
POLICY_WALLET_ADDRESS = "0x91BB52A63c91986813288965e4681FF111De1b63"
POLICY_WALLET_ID = "bsb2feecuxl81dl5jz4u9xxo"
PINNED_ADDRESSES = {
    "wmon": "0x3bd359c1119da7da1d913d1c4d2b7c461115433a",
    "moe": "0xd8e004acba279417c04c0633cb5a21ceca207777",
    "pool": "0x97199b34564911936bc850ac45ede785892b5aad",
    "entrypoint": "0xb3e6778480b2E488385E8205eA05E20060B813cb",
}
PINNED_PROGRAM_FEE_PPM = 16000
PINNED_DIRECTION = 0
_HEX64 = re.compile(r"[0-9a-f]{64}")
_WALLET_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_ZERO_ADDRESS = "0x" + "0" * 40


@dataclass(frozen=True)
class GasLimits:
    wrap: int
    approve: int
    swap: int
    revoke: int

    def total(self) -> int:
        return self.wrap + self.approve + self.swap + self.revoke


@dataclass(frozen=True)
class OperatorTrade:
    chain_id: int
    wallet_address: str
    wallet_id: str
    wmon: str
    moe: str
    pool: str
    entrypoint: str
    token0: str
    token1: str
    direction: int
    program_fee_ppm: int
    input_raw: int
    slippage_bps: int
    usd_ceiling: Decimal
    mon_usd_price: Decimal
    gas_limits: GasLimits
    code_sha256: dict[str, str]
    receipt_timeout_seconds: float
    receipt_poll_seconds: float
    file_sha256: str

    @property
    def usd_ceiling_text(self) -> str:
        return format(self.usd_ceiling, "f")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise OperatorError("TRADE_FILE_INVALID", "duplicate key")
    return dict(pairs)


def _int(value: Any) -> bool:
    return type(value) is int


def _raw(value: Any) -> bool:
    return (type(value) is str and len(value) <= MAX_RAW_DIGITS and canonical_raw(value)
            and 0 < int(value) < 2**256)


def _decimal(value: Any) -> Decimal | None:
    if type(value) is not str or not value or len(value) > 32:
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _gas_limits(value: Any) -> GasLimits:
    if type(value) is not dict or set(value) != GAS_FIELDS:
        raise OperatorError("TRADE_FILE_INVALID", "gas_limits")
    if not all(_int(value[name]) and 1 <= value[name] <= MAX_GAS_LIMIT for name in GAS_FIELDS):
        raise OperatorError("TRADE_FILE_INVALID", "gas_limits value")
    return GasLimits(wrap=value["wrap"], approve=value["approve"], swap=value["swap"], revoke=value["revoke"])


def _code_hashes(value: Any) -> dict[str, str]:
    if type(value) is not dict or set(value) != CODE_ROLES:
        raise OperatorError("TRADE_FILE_INVALID", "code_sha256")
    if not all(type(item) is str and _HEX64.fullmatch(item) for item in value.values()):
        raise OperatorError("TRADE_FILE_INVALID", "code_sha256 value")
    return {role: value[role] for role in CODE_ROLES}


def load_trade_file(path: Path) -> OperatorTrade:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise OperatorError("TRADE_FILE_UNREADABLE", Path(path).name) from error
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except OperatorError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise OperatorError("TRADE_FILE_INVALID", "not JSON") from error
    return parse_trade(value, hashlib.sha256(raw).hexdigest())


def parse_trade(value: Any, file_sha256: str) -> OperatorTrade:
    if type(value) is not dict or set(value) != FIELDS:
        raise OperatorError("TRADE_FILE_INVALID", "fields")
    addresses = ("wallet_address", "wmon", "moe", "pool", "entrypoint", "token0", "token1")
    if not all(type(value[name]) is str and is_address(value[name]) for name in addresses):
        raise OperatorError("TRADE_FILE_INVALID", "address")
    if any(value[name].lower() == _ZERO_ADDRESS for name in addresses):
        raise OperatorError("TRADE_FILE_INVALID", "zero address")
    if type(value["wallet_id"]) is not str or not _WALLET_ID.fullmatch(value["wallet_id"]):
        raise OperatorError("TRADE_FILE_INVALID", "wallet_id")
    if not _int(value["chain_id"]) or value["chain_id"] != 143:
        raise OperatorError("TRADE_FILE_INVALID", "chain_id")
    if not _int(value["version"]) or value["version"] != 1:
        raise OperatorError("TRADE_FILE_INVALID", "version")
    if not _int(value["direction"]) or value["direction"] != PINNED_DIRECTION:
        raise OperatorError("TRADE_FILE_INVALID", "direction")
    if not _int(value["program_fee_ppm"]) or value["program_fee_ppm"] != PINNED_PROGRAM_FEE_PPM:
        raise OperatorError("TRADE_FILE_INVALID", "program_fee_ppm")
    if value["wallet_address"].lower() != POLICY_WALLET_ADDRESS.lower() or value["wallet_id"] != POLICY_WALLET_ID:
        raise OperatorError("TRADE_FILE_INVALID", "wallet pins")
    if any(value[name].lower() != pinned.lower() for name, pinned in PINNED_ADDRESSES.items()):
        raise OperatorError("TRADE_FILE_INVALID", "address pins")
    if value["token0"].lower() != value["wmon"].lower() or value["token1"].lower() != value["moe"].lower():
        raise OperatorError("TRADE_FILE_INVALID", "token pins")
    if not _raw(value["input_raw"]):
        raise OperatorError("TRADE_FILE_INVALID", "input_raw")
    if int(value["input_raw"]) > POLICY_MAX_INPUT:
        raise OperatorError("TRADE_FILE_INVALID", "input_raw above the Privy policy limit")
    if not _int(value["slippage_bps"]) or not 1 <= value["slippage_bps"] <= 10000:
        raise OperatorError("TRADE_FILE_INVALID", "slippage_bps")
    ceiling = _decimal(value["usd_ceiling"])
    if ceiling is None or ceiling <= 0 or ceiling > ABSOLUTE_USD_CEILING:
        raise OperatorError("TRADE_FILE_INVALID", "usd_ceiling")
    price = _decimal(value["mon_usd_price"])
    if price is None or price <= 0:
        raise OperatorError("TRADE_FILE_INVALID", "mon_usd_price")
    timeout = value["receipt_timeout_seconds"]
    poll = value["receipt_poll_seconds"]
    if (type(timeout) not in (int, float) or isinstance(timeout, bool) or not 0 < timeout <= MAX_RECEIPT_SECONDS):
        raise OperatorError("TRADE_FILE_INVALID", "receipt_timeout_seconds")
    if type(poll) not in (int, float) or isinstance(poll, bool) or not 0 < poll <= timeout:
        raise OperatorError("TRADE_FILE_INVALID", "receipt_poll_seconds")
    return OperatorTrade(
        chain_id=value["chain_id"],
        wallet_address=value["wallet_address"],
        wallet_id=value["wallet_id"],
        wmon=value["wmon"],
        moe=value["moe"],
        pool=value["pool"],
        entrypoint=value["entrypoint"],
        token0=value["token0"],
        token1=value["token1"],
        direction=value["direction"],
        program_fee_ppm=value["program_fee_ppm"],
        input_raw=int(value["input_raw"]),
        slippage_bps=value["slippage_bps"],
        usd_ceiling=ceiling,
        mon_usd_price=price,
        gas_limits=_gas_limits(value["gas_limits"]),
        code_sha256=_code_hashes(value["code_sha256"]),
        receipt_timeout_seconds=float(timeout),
        receipt_poll_seconds=float(poll),
        file_sha256=file_sha256,
    )
