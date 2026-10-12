"""A host process that starts one transport-job turn against a hung authored provider. A test kills it with SIGKILL.

Usage: hung_turn_host.py <image> <run_id> <evidence_dir> <spend.sqlite> <credential>
Only test support: no real provider, network or key.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from authored_cases import load_case, provider_script
from edge_os_api.research.hermes_interpreter import SYSTEM_PROMPT, HermesTurn
from provider_guard import GuardPolicy
from provider_transport import TransportRoute
from spend_ledger import SpendLedger, TokenPrice
from transport_turn_runner import build_transport_job

POLICY = GuardPolicy(model="fixture-model/1", max_output_tokens=4096, max_request_bytes=12_000, max_envelope_chars=2_500)
ROUTE = TransportRoute("authored-local-1", "AUTHORED", "https://authored-transport.invalid/v1/chat/completions", 65_536)


def main(image: str, run_id: str, evidence: str, spend_path: str, credential: str) -> None:
    spend = SpendLedger(spend_path, cap_usd=Decimal("0.20"), price=TokenPrice(Decimal("2.00"), Decimal("7.50")))
    job = build_transport_job(ROUTE, policy=POLICY, ledger=spend, scope_for=lambda turn: "case-a", image=image,
                              run_id=run_id, evidence_dir=Path(evidence), credential_file=Path(credential),
                              script_for=lambda turn: provider_script(load_case("provider-hang")["provider"]),
                              timeout_seconds=300)
    job.runner.run_turn(HermesTurn("attempt-dead-1", SYSTEM_PROMPT, "task text", "fixture-model/1", "local", 4096))


if __name__ == "__main__":
    main(*sys.argv[1:6])
