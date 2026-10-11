"""The controlled deposit-observation boundary.

The selected funding transport is unqualified, so this module defines the port only. Every concrete
implementation used in this local task is an authored fake (see `tests/funding/fake_observer.py`).
An authored observation is never provider, chain or financial evidence. A real provider observation
is not replaceable by arbitrary incoming JSON: the caller supplies the port, not a raw observation
body.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from edge_os_api.funding.types import ObservationStatus


@dataclass(frozen=True)
class DepositObservation:
    """One observation of a deposit for one exact wallet and network.

    `reference` is the reviewed flow reference the observation answers. `event_id` is the unique
    transaction-event identity used for once-only credit. `raw`, `decimals`, `fee_raw` and
    `fee_decimals` stay `None` when unknown; they never become `0`.
    """

    wallet_id: str
    network_id: int
    reference: str
    status: ObservationStatus
    asset_id: str
    raw: str | None
    decimals: int | None
    event_id: str | None
    sender: str | None
    recipient: str | None
    fee_raw: str | None
    fee_decimals: int | None
    observed_at: dt.datetime


class ObservationUnavailable(RuntimeError):
    """The observation source cannot answer. The caller must leave the flow `UNKNOWN`."""


@runtime_checkable
class DepositObservationPort(Protocol):
    def observe(self, wallet_id: str, network_id: int) -> list[DepositObservation]:
        """Return the current observations for one exact wallet and network.

        An unavailable source raises `ObservationUnavailable`. The service never treats an
        unavailable source as a confirmed zero deposit.
        """
