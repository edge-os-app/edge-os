"""Independent-process driver for the local wallet-setup recovery and concurrency controls.

It drives the real service against the run-labelled database with the authored fake provider. It
performs no network call and no provider action. Crash scenarios stop this process at a named
boundary with `os._exit`, which no `finally` can catch.

Usage: driver.py <db_url> <owner_id> <agent_id> <strategy_id> <revision_id> <scenario> [options]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

from edge_os_api.core.authentication import Principal
from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.wallet_setup import service
from fake_provider import AuthoredFakeWalletProvider, crash_evidence

NETWORK_ID = 10143


def _wait_for(path: str) -> None:
    deadline = time.monotonic() + 30.0
    while not os.path.exists(path):
        if time.monotonic() > deadline:
            sys.exit("start file never appeared")
        time.sleep(0.02)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_url")
    parser.add_argument("owner_id")
    parser.add_argument("agent_id")
    parser.add_argument("strategy_id")
    parser.add_argument("revision_id")
    parser.add_argument("scenario")
    parser.add_argument("--start-file", default=None)
    parser.add_argument("--seed-wallet", action="append", default=[])
    parser.add_argument("--seed-address", default=None)
    args = parser.parse_args()
    if args.start_file:
        _wait_for(args.start_file)

    owner = uuid.UUID(args.owner_id)
    wallets = {wallet_id: crash_evidence(owner, wallet_id, args.seed_address) for wallet_id in args.seed_wallet}
    hooks: dict = {}
    if args.scenario == "crash_at_dispatch":
        hooks["on_create"] = lambda _request: os._exit(7)
    if args.scenario == "crash_at_verify":
        hooks["on_lookup"] = lambda _wallet_id: os._exit(8)
    provider = AuthoredFakeWalletProvider(wallets=wallets, **hooks)

    engine = make_engine(args.db_url)
    session_factory = make_session_factory(engine)
    principal = Principal(user_id=owner, privy_did="did:privy:driver")
    result: dict = {"scenario": args.scenario}
    with session_factory() as session:
        if args.scenario in {"prepare", "prepare_race"}:
            record = service.prepare_setup(session, principal, agent_id=args.agent_id, network_id=NETWORK_ID,
                                           strategy_id=args.strategy_id, strategy_revision_id=args.revision_id,
                                           request_key=f"driver-{args.scenario}")
        elif args.scenario in {"dispatch", "race", "crash_at_dispatch", "crash_at_verify"}:
            record = service.dispatch_setup(session, principal, agent_id=args.agent_id, provider=provider)
        elif args.scenario == "resume":
            record = service.resume_setup(session, principal, agent_id=args.agent_id, provider=provider)
        elif args.scenario == "cancel":
            record = service.cancel_setup(session, principal, agent_id=args.agent_id)
        elif args.scenario == "read":
            record = service.get_setup(session, principal, agent_id=args.agent_id)
        else:
            sys.exit(f"unknown scenario: {args.scenario}")
        result.update({"setup_id": str(record.setup_id), "state": record.state.value, "wallet_id": record.wallet_id,
                       "reason": record.reason})
    result["invoked"] = bool(provider.created)
    result["lookup_count"] = len(provider.lookups)
    engine.dispose()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
