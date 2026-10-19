"""The bound current-observation collection age holds after an intervening holdings read (#58 Phase B)."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from edge_os_api.core.provider_ports import (
    ControlledRuntime, FixtureMarketObservations, MarketObservationRequest, MarketObservations)
from edge_os_api.execution.operating_release import BoundRelease, release_sha256
from edge_os_api.execution.worker import SLOT, observation_problem
from edge_os_api.research.forward_observation import ForwardObservation

from execution.test_privy_signer import original
from execution.test_saved_attempt_signing import bound_original


def no_io(*args, **kwargs):
    raise AssertionError("no I/O is allowed in this pure check")


def bound_market(transport, max_age):
    prior, _ = bound_original(transport)
    profile = {"source_id": "synthetic-current/1", "delivery_profile_sha256": "9" * 64,
               "finality": "finalized", "warmup_buckets": 2, "max_collection_age_seconds": max_age}
    return BoundRelease(prior.release, prior.identity(), market_profile=profile, **prior.proofs())


def collected_once(transport, binding, now):
    request = MarketObservationRequest("agent-1", "market-a", now, 2, False)
    authored = FixtureMarketObservations().observe(request)
    forward = ForwardObservation(network="monad:143", market_binding_id="market-a",
        base_asset=transport._context.buy.asset_id, quote_asset=transport._context.sell.asset_id,
        units="QUOTE_PER_BASE", event="event-a", collected_at=now.isoformat(), observed_at=now.isoformat(),
        finality="finalized", coverage="COMPLETE", evidence_class="SYNTHETIC_FIXTURE", age_seconds=0,
        availability="AVAILABLE", reason=None)
    provenance = {**authored.provenance, "source": "synthetic-current/1", "evidence_class": "SYNTHETIC_FIXTURE",
        "availability_basis": "FORWARD_OBSERVED", "finality": "finalized", "binding_sha256": binding.sha256,
        "qualification_proof_sha256": binding.proofs()["market_proof_sha256"], "delivery_profile_sha256": "9" * 64,
        "warmup_buckets": 2}
    return MarketObservations(authored.inputs, provenance, forward=forward)


def runtime_for(transport, binding, observed, now):
    source = SimpleNamespace(observe=lambda request: observed)
    return ControlledRuntime(binding=binding, http=no_io, market_source=source, clock=lambda: now,
                             synthetic_bindings={binding.sha256: release_sha256(binding.release)})


def test_the_released_collection_age_still_holds_after_a_holdings_read(tmp_path):
    transport, _, _ = original(tmp_path, None)
    now = transport._clock()
    binding = bound_market(transport, 30)
    observed = collected_once(transport, binding, now)
    runtime = runtime_for(transport, binding, observed, now)
    result = runtime.observe_market(MarketObservationRequest("agent-1", "market-a", now, 2, False))

    # The reading is fresh when the source returns.
    assert observation_problem(result.provenance, now, now, "controlled", runtime=runtime) == (None, now)
    # At the released bound it is still fresh, and one second later it is not.
    at_limit = now + dt.timedelta(seconds=30)
    assert at_limit - now < SLOT
    assert observation_problem(result.provenance, now, at_limit, "controlled", runtime=runtime) == (None, now)
    later = now + dt.timedelta(seconds=31)
    assert observation_problem(result.provenance, now, later, "controlled", runtime=runtime) == (
        "OBSERVATIONS_STALE", now)
