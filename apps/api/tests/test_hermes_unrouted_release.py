"""A release that names no routing binds, and a routed release keeps every routing rule (draft section 7 step 3).

Synthetic definitions only: no file, socket, key or provider. `bind_release` is pure.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from test_hermes_relay_composition import (  # noqa: F401 - fixtures
    MODEL, ROUTING, SLUG, SNAPSHOT, approve, canonical, definition,
)

from edge_os_api.research.hermes_relay_composition import bind_release
from edge_os_api.research.hermes_transport_mount import MountRefused
from edge_os_api.research.provider_spend_ledger import TokenPrice

SELLER = "synthetic-seller"
UNROUTED_FIELDS = ["model", "messages", "stream", "response_format", "reasoning", "max_tokens", "session_id"]
# Above the routed fixture's max_price (4 / 10): no routing means no routing ceiling to compare with.
UNROUTED_SNAPSHOT = {"model": MODEL, "provider": SELLER, "prompt_usd_per_million": "4.20",
                     "completion_usd_per_million": "10.50"}


def unrouted(*, seller: str | None = SELLER, snapshot: dict[str, Any] | None = None) -> Any:
    prices = canonical(UNROUTED_SNAPSHOT if snapshot is None else snapshot)
    return definition(record_fields={"provider": None, "allowed_fields": UNROUTED_FIELDS,
                                     "price_snapshot_sha256": hashlib.sha256(prices).hexdigest()},
                      snapshot=prices, seller=seller)


def test_a_release_naming_no_routing_binds_with_no_routing_field_in_the_request(approve) -> None:  # noqa: F811
    [given] = approve(unrouted())
    bound = bind_release(given)
    assert bound.actual.provider is None
    assert "provider" not in bound.policy.required_extra
    assert bound.price == TokenPrice(Decimal("4.20"), Decimal("10.50"))
    assert bound.config.live_release.provider == SELLER
    assert bound.unchanged()


def test_a_release_naming_no_routing_needs_a_named_seller(approve) -> None:  # noqa: F811
    [given] = approve(unrouted(seller=None))
    with pytest.raises(MountRefused, match="seller"):
        bind_release(given)


def test_the_snapshot_of_a_release_naming_no_routing_must_name_its_seller(approve) -> None:  # noqa: F811
    [given] = approve(unrouted(snapshot={**UNROUTED_SNAPSHOT, "provider": "someone-else"}))
    with pytest.raises(MountRefused, match="seller"):
        bind_release(given)


@pytest.mark.parametrize("rate", ["0", "0.000", "1e3", "-1", ""])
def test_a_release_naming_no_routing_still_needs_positive_plain_rates(approve, rate: str) -> None:  # noqa: F811
    [given] = approve(unrouted(snapshot={**UNROUTED_SNAPSHOT, "prompt_usd_per_million": rate}))
    with pytest.raises(MountRefused, match="positive plain decimal"):
        bind_release(given)


def test_a_routing_field_added_to_a_bound_unrouted_request_is_seen(approve) -> None:  # noqa: F811
    [given] = approve(unrouted())
    bound = bind_release(given)
    for added in (None, {}, ROUTING):
        changed = replace(bound.policy, required_extra={**bound.policy.required_extra, "provider": added})
        assert not replace(bound, policy=changed).unchanged()


def test_a_routed_release_may_not_name_a_seller(approve) -> None:  # noqa: F811
    [given] = approve(definition(seller=SLUG))
    with pytest.raises(MountRefused, match="seller"):
        bind_release(given)


def test_a_routed_release_keeps_its_routed_provider_rule(approve) -> None:  # noqa: F811
    prices = canonical({**SNAPSHOT, "provider": SELLER})
    [given] = approve(definition(record_fields={"price_snapshot_sha256": hashlib.sha256(prices).hexdigest()},
                                 snapshot=prices))
    with pytest.raises(MountRefused, match="routed provider"):
        bind_release(given)


@pytest.mark.parametrize("limit", [{"completion": 10}, {"prompt": 4}, {}, {"prompt": None, "completion": 10},
                                   {"prompt": 2.99, "completion": 10}])
def test_a_routed_release_keeps_its_price_ceiling(approve, limit: dict[str, Any]) -> None:  # noqa: F811
    [given] = approve(definition(record_fields={"provider": {**ROUTING, "max_price": limit}}))
    with pytest.raises(MountRefused, match="max_price"):
        bind_release(given)


def test_the_relay_runner_accepts_exactly_the_unrouted_request_shape(approve) -> None:  # noqa: F811
    from relay_turn_runner import _check_actual  # noqa: PLC0415 - on the path once the composition module is imported
    [given] = approve(unrouted())
    bound = bind_release(given)
    _check_actual(bound.route, bound.actual, bound.policy)
    changed = replace(bound.policy, required_extra={**bound.policy.required_extra, "provider": None})
    with pytest.raises(ValueError, match="request shape"):
        _check_actual(bound.route, bound.actual, changed)
