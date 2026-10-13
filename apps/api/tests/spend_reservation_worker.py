"""One independent OS process that reserves provider spend through `PostgresSpendLedger`. Test support only.

Usage: spend_reservation_worker.py <database_url> <global_cap_usd> <owner_cap_usd> <start_at_epoch> <attempt_id:scope>...
Every attempt is reserved from its own thread once the shared start time arrives. Prints one JSON object per attempt.
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
    results: list[dict[str, str]] = []
    lock = threading.Lock()

    def reserve(pair: str) -> None:
        attempt, scope = pair.split(":", 1)
        time.sleep(max(0.0, float(start_at) - time.time()))
        try:
            spend.reserve(attempt, scope=scope, max_input_tokens=12_064, max_output_tokens=4_096)
            outcome = "RESERVED"
        except Exception as error:  # noqa: BLE001 - the class name is the result being tested
            outcome = type(error).__name__
        with lock:
            results.append({"attempt_id": attempt, "outcome": outcome})

    threads = [threading.Thread(target=reserve, args=(pair,)) for pair in pairs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    engine.dispose()
    print(json.dumps(results))


if __name__ == "__main__":
    main(*sys.argv[1:])
