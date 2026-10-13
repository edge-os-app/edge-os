"""Current wallet holdings as one identity-bound observation (`edge-os.current-holdings/1`).

A holdings port returns a `HoldingsObservation`: per requested asset the exact raw amount and decimals, plus the
observed wallet, chain, block, observation time, finality, source and the assets it could not read. It is kept
apart from deposit history, attributed positions and reservations. `checked_at` for admission is the observation
time, never the current clock, so a stale reading is refused by the existing freshness checks.

`read_rpc_holdings` reads one finalized block and the balances at that block through an injected JSON-RPC client.
Native MON is the gas asset only.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from edge_os_api.admission.types import AssetAmount
from edge_os_api.execution.original_transaction import (
    BALANCE_OF_SELECTOR,
    DECIMALS_SELECTOR,
    ReplyLost,
    RpcClient,
    RpcError,
    abi_word,
    hex_quantity,
    token_of,
)

SCHEMA = "edge-os.current-holdings/1"
FRESHNESS = dt.timedelta(minutes=5)


@dataclass(frozen=True)
class HoldingsObservation:
    assets: dict[str, AssetAmount]
    observed_at: dt.datetime | None  # None: an authored account computed at the caller's own read, no supplied time
    source: str
    evidence_class: str
    finality: str
    wallet_address: str | None = None
    chain_id: int | None = None
    block_number: int | None = None
    missing: list[str] = field(default_factory=list)

    def refusal(self, *, wallet_address: str | None, chain_id: int | None, now: dt.datetime) -> str | None:
        """Why this observation cannot support an admission now, or None."""
        if self.wallet_address is not None and (wallet_address or "").lower() != self.wallet_address.lower():
            return "HOLDINGS_WRONG_WALLET"
        if self.chain_id is not None and chain_id != self.chain_id:
            return "HOLDINGS_WRONG_CHAIN"
        if self.missing:
            return "HOLDINGS_INCOMPLETE"
        if self.observed_at is not None and self.observed_at > now:
            return "HOLDINGS_TIME_INVALID"
        if self.observed_at is not None and now - self.observed_at > FRESHNESS:
            return "HOLDINGS_STALE"
        return None

    def view(self, refusal: str | None = None) -> dict[str, Any]:
        return {"schema": SCHEMA, "state": "UNAVAILABLE" if refusal else "OBSERVED", "reason": refusal,
                "source": self.source, "evidence_class": self.evidence_class, "finality": self.finality,
                "observed_at": None if self.observed_at is None else self.observed_at.astimezone(dt.timezone.utc).isoformat(),
                "wallet_address": self.wallet_address, "chain_id": self.chain_id, "block_number": self.block_number,
                "missing": list(self.missing),
                "assets": [amount.model_dump(mode="json") for amount in self.assets.values()]}


def read_rpc_holdings(client: RpcClient, *, wallet_address: str, assets: list[tuple[str, int]], source: str,
                      evidence_class: str) -> HoldingsObservation:
    """Read the finalized block, then each asset's balance and token decimals at that block.

    An unreadable value, or token decimals other than the expected ones, leaves the asset missing; nothing is
    filled with zero or a default.
    """
    try:
        chain_id = hex_quantity(client.call("eth_chainId", []))
        block = client.call("eth_getBlockByNumber", ["finalized", False])
    except (ReplyLost, TimeoutError, OSError, RpcError):
        raise HoldingsUnavailable("HOLDINGS_UNAVAILABLE") from None
    number = hex_quantity(block.get("number")) if isinstance(block, dict) else None
    stamp = hex_quantity(block.get("timestamp")) if isinstance(block, dict) else None
    if chain_id is None or number is None or stamp is None:  # an observation that cannot name its chain is refused
        raise HoldingsUnavailable("HOLDINGS_UNAVAILABLE")
    tag = hex(number)
    observed: dict[str, AssetAmount] = {}
    missing: list[str] = []
    for asset_id, decimals in assets:
        token = token_of(asset_id)
        try:
            if token is None:
                raw = hex_quantity(client.call("eth_getBalance", [wallet_address, tag]))
                token_decimals: int | None = 18
            else:
                token_decimals = abi_word(client.call("eth_call", [{"to": token, "data": DECIMALS_SELECTOR}, tag]))
                raw = abi_word(client.call("eth_call", [
                    {"to": token, "data": BALANCE_OF_SELECTOR + "0" * 24 + wallet_address[2:].lower()}, tag]))
        except (ReplyLost, TimeoutError, OSError, RpcError):
            raw, token_decimals = None, None
        if raw is None or token_decimals != decimals:
            missing.append(asset_id)
            continue
        observed[asset_id] = AssetAmount(asset_id=asset_id, raw=str(raw), decimals=decimals)
    return HoldingsObservation(
        assets=observed, observed_at=dt.datetime.fromtimestamp(stamp, dt.timezone.utc), source=source,
        evidence_class=evidence_class, finality="FINALIZED", wallet_address=wallet_address, chain_id=chain_id,
        block_number=number, missing=missing)


class HoldingsUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
