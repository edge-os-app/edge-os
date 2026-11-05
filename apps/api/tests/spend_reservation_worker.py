"""One independent OS process that reserves provider spend through `PostgresSpendLedger`. Test support only.

Usage: spend_reservation_worker.py <database_url> <global_cap_usd> <owner_cap_usd> <start_at_epoch> [min=<tokens>]
       <attempt_id:scope>...
Every attempt is reserved from its own thread once the shared start time arrives. Prints one JSON object per attempt.
With `min=<tokens>`, each reservation passes that `min_output_tokens` and may get a lowered output limit.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from decimal import Decimal

from edge_os_api.core.database import make_engine, make_session_factory
from edge_os_api.research.provider_spend_ledger import PostgresSpendLedger, SpendLimits, TokenPrice


def main(url: str, global_cap: str, owner_cap: str, start_at: str, *pairs: str) -> None:
    engine = make_engine(url)
    spend = PostgresSpendLedger(make_session_factory(engine), SpendLimits(
        Decimal(global_cap), Decimal(owner_cap), TokenPrice(Decimal("2.00"), Decimal("7.50"))))
    smallest = int(pairs[0].removeprefix("min=")) if pairs and pairs[0].startswith("min=") else None
    pairs = pairs[1:] if smallest is not None else pairs
    results: list[dict[str, object]] = []
    lock = threading.Lock()

    def reserve(pair: str) -> None:
        attempt, scope = pair.split(":", 1)
        time.sleep(max(0.0, float(start_at) - time.time()))
        limit = None
        try:
            if smallest is None:
                limit = spend.reserve(attempt, scope=scope, max_input_tokens=12_064, max_output_tokens=4_096).max_output_tokens
            else:
                limit = spend.reserve(attempt, scope=scope, max_input_tokens=12_064, max_output_tokens=4_096,
                                      min_output_tokens=smallest).max_output_tokens
            outcome = "RESERVED"
        except Exception as error:  # noqa: BLE001 - the class name is the result being tested
            outcome = type(error).__name__
        with lock:
            results.append({"attempt_id": attempt, "outcome": outcome, "max_output_tokens": limit})

    threads = [threading.Thread(target=reserve, args=(pair,)) for pair in pairs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    engine.dispose()
    print(json.dumps(results))


if __name__ == "__main__":
    main(*sys.argv[1:])
