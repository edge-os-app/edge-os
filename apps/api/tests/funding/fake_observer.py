"""AUTHORED FAKE deposit observer. Its results are not provider, chain or financial evidence.

It exists only to exercise the local funding service and its reconciliation controls. It returns
authored observations for one exact wallet and network, so a fresh process holds no observations it
did not receive.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable

from edge_os_api.funding.observation import DepositObservation, ObservationUnavailable
from edge_os_api.funding.types import ObservationStatus


def observation(*, wallet_id: str, network_id: int, reference: str, status: ObservationStatus, asset_id: str,
                raw: str | None = None, decimals: int | None = None, event_id: str | None = None,
                sender: str | None = None, recipient: str | None = None, fee_asset_id: str | None = None,
                fee_raw: str | None = None, fee_decimals: int | None = None,
                observed_at: dt.datetime | None = None) -> DepositObservation:
    """Build one authored observation with explicit fields. Unknown fields stay `None`."""
    return DepositObservation(wallet_id=wallet_id, network_id=network_id, reference=reference, status=status,
                              asset_id=asset_id, raw=raw, decimals=decimals, event_id=event_id, sender=sender,
                              recipient=recipient, fee_asset_id=fee_asset_id, fee_raw=fee_raw,
                              fee_decimals=fee_decimals,
                              observed_at=observed_at or dt.datetime(2026, 10, 11, 12, 0, tzinfo=dt.timezone.utc))


class AuthoredFakeDepositObserver:
    """An authored fake. Never treat a result here as provider, chain or financial evidence."""

    def __init__(self, observations: list[DepositObservation] | None = None, *, unavailable: bool = False,
                 on_observe: Callable[[str, int], None] | None = None) -> None:
        self.observations = list(observations or [])
        self.unavailable = unavailable
        self.calls: list[tuple[str, int]] = []
        self.on_observe = on_observe

    def observe(self, wallet_id: str, network_id: int) -> list[DepositObservation]:
        if self.on_observe is not None:
            self.on_observe(wallet_id, network_id)
        self.calls.append((wallet_id, network_id))
        if self.unavailable:
            raise ObservationUnavailable()
        return [item for item in self.observations
                if item.wallet_id == wallet_id and item.network_id == network_id]
