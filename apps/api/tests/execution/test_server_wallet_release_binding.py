"""The A2 authored release binds the server wallet used by the local wallet-binding path.

Pure file read and hash only. This test proves the wallet, signer and policy identity that the lookup
process requires, and the exact canonical hash that WALLET_BOUND evidence carries.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts" / "privy_wallet_lookup"))
import lookup_server  # noqa: E402

AUTHORED = REPO / "docs" / "qualification" / "inapp-trade" / "release.authored.json"


def test_a2_authored_release_binds_the_server_wallet():
    release = lookup_server.load_server_wallet_release(json.loads(AUTHORED.read_text(encoding="utf-8")))
    assert (release.wallet_id, release.address, release.signer_id, release.policy_id, release.policy_owner_id) == (
        "bsb2feecuxl81dl5jz4u9xxo", "0x91BB52A63c91986813288965e4681FF111De1b63",
        "zu1qjdfqlbcq1ct7sdxendgg", "c30racyru6duaipj815cvjce", "a5gwmgrsn6903ac09lphyv9a")
    canonical = json.dumps({"release_id": release.release_id, "chain_id": release.chain_id,
                            "wallet_id": release.wallet_id, "wallet_address": release.address.lower(),
                            "chain_type": "ethereum", "signer_id": release.signer_id,
                            "policy_id": release.policy_id, "policy_owner_id": release.policy_owner_id},
                           sort_keys=True, separators=(",", ":")).encode("ascii")
    assert release.binding_sha256 == hashlib.sha256(canonical).hexdigest()
