"""Separate-process quota driver for the shared-quota tests. One process per call; prints one JSON line.

Usage: python usage_driver.py <mode> <db_url> <owner> <global_key> <subject> <provider> <compute> <owner_cap> <global_cap>
Modes: reserve (reserve and commit), reserve-die (reserve, then end the process before commit).
"""

from __future__ import annotations

import json
import os
import sys
import uuid

from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.usage import quota


def main() -> None:
    mode, url, owner, global_key, subject, provider, compute, owner_cap, global_cap = sys.argv[1:10]
    caps = quota.Caps(owner={"provider_requests": int(owner_cap), "compute_seconds": 1000},
                      global_={"provider_requests": int(global_cap), "compute_seconds": 100000},
                      global_key=uuid.UUID(global_key))
    engine = make_engine(url, 30_000)
    with make_session_factory(engine)() as session:
        outcome = quota.reserve(session, uuid.UUID(owner), "test_subject", subject,
                                {"provider_requests": int(provider), "compute_seconds": int(compute)}, caps)
        if mode == "reserve-die":
            os._exit(9)  # killed while holding the locks and before the commit
        session.commit()
    if isinstance(outcome, quota.Grant):
        print(json.dumps({"granted": True, "replayed": outcome.replayed}))
    else:
        print(json.dumps({"granted": False, "scope": outcome.scope, "resource": outcome.resource}))


if __name__ == "__main__":
    main()
