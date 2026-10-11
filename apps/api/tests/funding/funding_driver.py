"""Independent-process driver for local funding reconciliation controls.

It drives the real funding service against the run-labelled database with the authored fake observer.
It performs no network call and no provider action. Crash scenarios stop this process at a named
boundary with `os._exit`, which no `finally` can catch.

Usage: funding_driver.py <db_url> <owner_id> <agent_id> <wallet_id> <network_id> <reference> <event_id>
       <raw> <decimals> <asset_id> <scenario>
"""

from __future__ import annotations

import argparse
import json
import os
import uuid

from edge_os_api.core.authentication import Principal
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.funding import service
from edge_os_api.funding.types import ObservationStatus
from fake_observer import AuthoredFakeDepositObserver, observation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_url")
    parser.add_argument("owner_id")
    parser.add_argument("agent_id")
    parser.add_argument("wallet_id")
    parser.add_argument("network_id", type=int)
    parser.add_argument("reference")
    parser.add_argument("event_id")
    parser.add_argument("raw")
    parser.add_argument("decimals", type=int)
    parser.add_argument("asset_id")
    parser.add_argument("scenario")
    args = parser.parse_args()

    hooks: dict = {}
    if args.scenario == "crash_during_observe":
        hooks["on_observe"] = lambda _wallet_id, _network_id: os._exit(9)
    observed = observation(wallet_id=args.wallet_id, network_id=args.network_id, reference=args.reference,
                           status=ObservationStatus.CONFIRMED, asset_id=args.asset_id, raw=args.raw,
                           decimals=args.decimals, event_id=args.event_id)
    observer = AuthoredFakeDepositObserver([observed], **hooks)

    engine = make_engine(args.db_url)
    factory = make_session_factory(engine)
    principal = Principal(user_id=uuid.UUID(args.owner_id), privy_did="did:privy:funding-driver")
    with factory() as session:
        results = service.reconcile_funding(session, principal, agent_id=args.agent_id, observer=observer)
    credits = sum(len(result.credits) for result in results)
    engine.dispose()
    if args.scenario == "crash_after_credit":
        os._exit(10)
    print(json.dumps({"scenario": args.scenario, "credits": credits}))


if __name__ == "__main__":
    main()
