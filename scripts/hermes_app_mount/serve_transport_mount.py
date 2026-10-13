"""Start the API with the LOCAL Hermes transport mount: the startable composition of `open_transport_mount`.

Run it from `apps/api` with the API's Python, the usual EDGE_OS_* environment and EDGE_OS_INTERPRETER=hermes_local
(refused in production). Each model turn runs ACTUAL pinned Hermes in a no-network container; the AUTHORED transport plays
the next item of `--script-file`, a JSON list of `{"case": name}` items with an optional `"transport_fault"`. Spend goes to
the shared PostgreSQL ledger. Give each API process its own stable `--run-id`; a restart reuses it to recover its dead
turns. `--report-file` receives the startup recovery result. No real provider, key or network. Used by the mapped
verifier's HERMES-MOUNT phase (`scripts/p03/hermes_app_mount_phase.py`) and by `tests/hermes_app_mount`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "hermes_interpretation"))

import uvicorn  # noqa: E402

from authored_cases import load_case, provider_script  # noqa: E402
from edge_os_api.core.settings import load_settings  # noqa: E402
from edge_os_api.main import create_app  # noqa: E402
from edge_os_api.research.hermes_transport_mount import open_transport_mount  # noqa: E402
from edge_os_api.research.provider_spend_ledger import SpendLimits, TokenPrice  # noqa: E402

PRICE = TokenPrice(Decimal("2.00"), Decimal("7.50"))


class FaultQueue:
    """Consumes one script item per turn, so a test controls what each started job's provider does."""

    def __init__(self, path: Path) -> None:
        self.path, self._lock = path, threading.Lock()

    def __call__(self, _turn: object) -> dict[str, Any]:
        with self._lock:
            items = json.loads(self.path.read_text(encoding="utf-8"))
            item = items.pop(0)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(items), encoding="utf-8")
            os.replace(temporary, self.path)
        script = provider_script(load_case(item["case"])["provider"])
        return {**script, "transport_fault": item["transport_fault"]} if "transport_fault" in item else script


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("--image", "--run-id", "--global-cap", "--owner-cap"):
        parser.add_argument(name, required=True)
    for name in ("--evidence-dir", "--script-file", "--credential-file", "--report-file"):
        parser.add_argument(name, type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=90)
    args = parser.parse_args()
    settings = load_settings()
    mount = open_transport_mount(
        settings, limits=SpendLimits(Decimal(args.global_cap), Decimal(args.owner_cap), PRICE), image=args.image,
        run_id=args.run_id, evidence_dir=args.evidence_dir, script_for=FaultQueue(args.script_file),
        credential_file=args.credential_file, timeout_seconds=args.timeout_seconds, recovery_budget_seconds=30.0)
    args.report_file.write_text(json.dumps({"pid": os.getpid(), "startup_recovery": mount.startup_recovery}))
    try:
        uvicorn.run(create_app(settings, hermes_runner=mount.runner), host="127.0.0.1", port=args.port,
                    log_level="warning")
    finally:
        mount.close()


if __name__ == "__main__":
    main()
