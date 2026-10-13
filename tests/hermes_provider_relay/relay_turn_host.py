"""A host process that starts one relay-job turn against a hung AUTHORED provider. A test kills it with SIGKILL.

Usage: relay_turn_host.py <image> <run_id> <evidence_dir> <spend.sqlite> <relay_root>
Only test support: synthetic key, AUTHORED provider, no real network.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from edge_os_api.research.hermes_interpreter import SYSTEM_PROMPT, HermesTurn
from relay_admission import RelaySubject
from relay_harness import POLICY, PRICE, RELEASE, ROUTE
from relay_turn_runner import RelayEndpoint, build_relay_job
from spend_ledger import SpendLedger


def main(image: str, run_id: str, evidence: str, spend_path: str, relay_root: str) -> None:
    root = Path(relay_root)
    endpoint = RelayEndpoint(root / "grants", root / "revocations", root / "state", root / "secrets" / "admission-key", "jobs")
    spend = SpendLedger(spend_path, cap_usd=Decimal("0.20"), price=PRICE)
    job = build_relay_job(ROUTE, release=RELEASE, endpoint=endpoint, subject_for=lambda turn: RelaySubject("o", "r"),
                          policy=POLICY, ledger=spend, scope_for=lambda turn: "case-dead", image=image, run_id=run_id,
                          evidence_dir=Path(evidence), script_for=lambda turn: {"kind": "hang"}, timeout_seconds=40)
    job.runner.run_turn(HermesTurn("attempt-dead-1", SYSTEM_PROMPT, "task text", POLICY.model, "local", 4096))


if __name__ == "__main__":
    main(*sys.argv[1:6])
