"""Operator entry point for the frozen unfunded packets: the v3 policy packet and the control-proof packet.

This command never reads ``.env``. It reads exactly three environment values
(``PRIVY_APP_ID``, ``PRIVY_APP_SECRET``, ``PRIVY_AGENT_KEY_FILE``) and one P-256
PEM file, and only for a live run. ``--dry-run`` reads nothing and sends nothing.

The live path runs the packet's specimens one at a time in the frozen order. It
stops on the first ``BREACH``, ``UNKNOWN`` or unexpected outcome and never
retries. The runner has no broadcast path; the wallet must be unfunded, and the
operator must pass ``--confirm-unfunded`` after an independent balance read.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from edge_os_api.execution.privy_signer import make_p256_authorizer
from edge_os_api.research_history.http_clients.http_transport import StdlibHttpTransport

from scripts.privy_unfunded_proof.actual_packet import (
    CONTROL_PROOF_ORDER,
    CONTROL_PROOF_PACKET,
    CONTROL_PROOF_TABLE,
    UNFUNDED_POLICY_ORDER,
    UNFUNDED_POLICY_PACKET,
    UNFUNDED_POLICY_PROFILE_ID,
    UNFUNDED_POLICY_TABLE,
    resolve_approved_packet,
)
from scripts.privy_unfunded_proof.actual_profile import resolve_qualified_profile
from scripts.privy_unfunded_proof.actual_runner import run_actual_specimen
from scripts.privy_unfunded_proof.actual_transport import ActualSignOnlyTransport, deadline_bounded_connect
from scripts.privy_unfunded_proof.evidence import Outcome, RunResult
from scripts.privy_unfunded_proof.specimens import AttemptStore, SpecimenRefused

MAX_RESPONSE_BYTES = 16384
CONNECT_TIMEOUT_SECONDS = 15.0
PER_REQUEST_DEADLINE_SECONDS = 60.0
# The registered packets this command runs: the v3 policy packet (default) and the control-proof packet.
PACKETS = {
    "policy-v3": (UNFUNDED_POLICY_PACKET, UNFUNDED_POLICY_TABLE, UNFUNDED_POLICY_ORDER),
    "control-proofs": (CONTROL_PROOF_PACKET, CONTROL_PROOF_TABLE, CONTROL_PROOF_ORDER),
}


def _clock() -> str:
    return datetime.now(timezone.utc).isoformat()


def should_stop(result: RunResult) -> bool:
    """Stop on a breach, a mismatch or an unknown reply; an expected expiry refusal is a matched result."""
    if result.outcome is Outcome.BREACH or not result.matches_expectation:
        return True
    return result.outcome is Outcome.UNKNOWN and result.reason != "EXPIRY_REFUSAL"


def _dry_run(name: str) -> int:
    frozen, table, order = PACKETS[name]
    try:
        packet = resolve_approved_packet(frozen.packet_id, now_epoch=int(time.time()), table=table)
        profile = resolve_qualified_profile(UNFUNDED_POLICY_PROFILE_ID)
    except SpecimenRefused as refused:
        print(f"REFUSED {refused.code}")
        return 2
    print(f"packet={packet.packet_id}")
    print(f"profile_id={UNFUNDED_POLICY_PROFILE_ID} profile={profile.profile}")
    print(f"expires_at_epoch={packet.expires_at_epoch} auth_header_expiry={packet.auth_header_expiry}")
    for specimen_id in order:
        request = packet.requests[specimen_id]
        print(f"{specimen_id} expected={packet.specimen_expected[specimen_id]} "
              f"request_sha256={request.request_sha256}")
    return 0


def _credentials() -> tuple[str, str, Path] | None:
    app_id = os.environ.get("PRIVY_APP_ID", "")
    app_secret = os.environ.get("PRIVY_APP_SECRET", "")
    key_file = os.environ.get("PRIVY_AGENT_KEY_FILE", "")
    if not app_id or not app_secret or not key_file:
        print("CREDENTIAL_ENV_MISSING: set PRIVY_APP_ID, PRIVY_APP_SECRET and PRIVY_AGENT_KEY_FILE")
        return None
    return app_id, app_secret, Path(key_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen unfunded policy-layer packet once.")
    parser.add_argument("--dry-run", action="store_true", help="validate and list the packet; read no credential")
    parser.add_argument("--packet", choices=sorted(PACKETS), default="policy-v3",
                        help="the registered packet to run (default: the v3 policy packet)")
    parser.add_argument("--store", type=Path, help="a new empty directory for the one-use attempt store")
    parser.add_argument("--confirm-unfunded", action="store_true",
                        help="the operator confirmed an independent zero-balance read of the agent wallet")
    args = parser.parse_args(argv)

    if args.dry_run:
        return _dry_run(args.packet)
    frozen, table, order = PACKETS[args.packet]

    if not args.confirm_unfunded:
        print("UNFUNDED_CONFIRMATION_REQUIRED: read the wallet balance first, then pass --confirm-unfunded")
        return 2
    if args.store is None:
        print("STORE_REQUIRED: pass a new --store directory")
        return 2
    if args.store.exists():
        print("STORE_ALREADY_EXISTS: one packet uses one new store")
        return 2

    now_epoch = int(time.time())
    try:
        packet = resolve_approved_packet(frozen.packet_id, now_epoch=now_epoch, table=table)
        resolve_qualified_profile(UNFUNDED_POLICY_PROFILE_ID)
    except SpecimenRefused as refused:
        print(f"REFUSED {refused.code}")
        return 2
    if now_epoch * 1000 >= int(packet.auth_header_expiry):
        print("PACKET_WINDOW_CLOSED: the frozen auth-header expiry is past")
        return 2

    credentials = _credentials()
    if credentials is None:
        return 2
    app_id, app_secret, key_file = credentials
    try:
        private_key = load_pem_private_key(key_file.read_bytes(), password=None)
    except (OSError, ValueError, TypeError):
        print("AGENT_KEY_UNREADABLE")
        return 2
    try:
        authorize = make_p256_authorizer(private_key=private_key)
    except TypeError:
        print("AGENT_KEY_NOT_P256")
        return 2

    args.store.mkdir(parents=True, exist_ok=False)
    store = AttemptStore(args.store)
    started_at_epoch = now_epoch
    for specimen_id in order:
        deadline = time.monotonic() + PER_REQUEST_DEADLINE_SECONDS
        http = StdlibHttpTransport(connect=deadline_bounded_connect(deadline_monotonic=deadline))
        transport = ActualSignOnlyTransport(
            http=http,
            destination=packet.signing_url,
            wallet_id=packet.wallet_id,
            app_id=app_id,
            app_secret=app_secret,
            authorize=authorize,
            request_id=packet.attempt_identity_for(specimen_id),
            request_expiry_ms=int(packet.auth_header_expiry),
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            deadline_monotonic=deadline,
            max_response_bytes=MAX_RESPONSE_BYTES,
        )
        try:
            result = run_actual_specimen(
                specimen_id,
                store=store,
                transport=transport,
                packet_id=packet.packet_id,
                profile_id=UNFUNDED_POLICY_PROFILE_ID,
                clock=_clock,
                now_epoch=int(time.time()),
                started_at_epoch=started_at_epoch,
                table=table,
            )
        except SpecimenRefused as refused:
            print(f"REFUSED {specimen_id} {refused.code}")
            return 2
        print(f"{specimen_id} expected={result.expected} outcome={result.outcome.value} "
              f"reason={result.reason} matches={str(result.matches_expectation).lower()}")
        if should_stop(result):
            print("STOP: review the saved capture and outcome; do not run the next specimen")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
