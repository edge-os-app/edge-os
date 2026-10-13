"""The trusted forward-observation contract a later P27 scheduler consumes (#58 RESEARCH-PORTS-LOCAL, types only).

A forward observation is one fresh, identity-bound market reading for an adopted strategy: network, market binding,
assets and units, the observed event, when it was collected and observed, its finality, coverage, evidence class,
age and availability. Nothing in this milestone produces one. Historical datasets, recorded or authored responses,
Nansen holder/flow context and quotes describe the past or another question, so `forward_observation_from` returns
UNAVAILABLE with the reason for each of them. No polling, scheduler or recurring engine exists here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

Availability = Literal["AVAILABLE", "UNAVAILABLE"]


@dataclass(frozen=True)
class ForwardObservation:
    network: str | None
    market_binding_id: str | None
    base_asset: str | None
    quote_asset: str | None
    units: str | None
    event: str | None
    collected_at: str | None
    observed_at: str | None
    finality: str | None
    coverage: str | None
    evidence_class: str | None
    age_seconds: int | None
    availability: Availability
    reason: str | None


# Why each current source cannot be a forward observation.
_UNAVAILABLE_REASONS = {
    "RECORDED_RESPONSE": "HISTORICAL_RECORDING",
    "RECORDED_NATIVE_RESPONSE": "HISTORICAL_RECORDING",
    "AUTHORED_HTTP_RESPONSE": "HISTORICAL_RECORDING",
    "AUTHORED_FIXTURE": "NANSEN_CONTEXT_NOT_MARKET_OBSERVATION",
    "SYNTHETIC_FIXTURE": "SYNTHETIC_FIXTURE",
}


def forward_observation_from(source: Mapping[str, Any]) -> ForwardObservation:
    """Project any current research source onto the forward contract. Every one is UNAVAILABLE, with its reason."""
    evidence_class = source.get("evidence_class")
    reason = _UNAVAILABLE_REASONS.get(str(evidence_class), "NO_TRUSTED_FORWARD_SOURCE")
    return ForwardObservation(network=None, market_binding_id=None, base_asset=None, quote_asset=None, units=None,
                              event=None, collected_at=None, observed_at=None, finality=None, coverage=None,
                              evidence_class=None if evidence_class is None else str(evidence_class),
                              age_seconds=None, availability="UNAVAILABLE", reason=reason)
