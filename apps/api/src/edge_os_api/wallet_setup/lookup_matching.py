"""Match one browser wallet claim against the verified owner's own Privy user record.

Pure functions only: no I/O, no credential. The trusted lookup process and the tests share them. A
wallet's `owner_id` is a key quorum, not the user DID, and `entity` is attribution, not ownership, so
neither is read. The match uses only the user record fetched for the verified DID. Missing, null,
duplicate or inconsistent identity returns `None`, which callers keep as `UNKNOWN`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
WALLET_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
DID = re.compile(r"did:privy:[A-Za-z0-9_-]{1,128}\Z")


@dataclass(frozen=True)
class MatchedWallet:
    wallet_id: str
    address: str
    chain_type: str


def valid_did(value: object) -> bool:
    return isinstance(value, str) and DID.fullmatch(value) is not None


def valid_address(value: object) -> bool:
    return isinstance(value, str) and ADDRESS.fullmatch(value) is not None


def valid_wallet_id(value: object) -> bool:
    return isinstance(value, str) and WALLET_ID.fullmatch(value) is not None


def _embedded_ethereum(account: object) -> bool:
    return (isinstance(account, dict) and account.get("type") == "wallet"
            and account.get("wallet_client_type") == "privy" and account.get("chain_type") == "ethereum")


def match_claim(user: object, did: str, address: str, wallet_id: str | None) -> MatchedWallet | None:
    """Return the one embedded Ethereum wallet of this exact user with this exact address, or `None`.

    A claimed wallet ID must equal the linked account's own ID. With no claimed ID, the linked account must
    carry its own ID; this function never guesses one.
    """
    if not (isinstance(user, dict) and valid_did(did) and user.get("id") == did and valid_address(address)):
        return None
    if wallet_id is not None and not valid_wallet_id(wallet_id):
        return None
    accounts = user.get("linked_accounts")
    if not isinstance(accounts, list):
        return None
    same = [a for a in accounts if _embedded_ethereum(a) and isinstance(a.get("address"), str)
            and a["address"].lower() == address.lower()]
    if len(same) != 1:
        return None
    found: dict[str, Any] = same[0]
    found_id = found.get("id")
    if not valid_wallet_id(found_id) or not valid_address(found["address"]):
        return None
    if wallet_id is not None and found_id != wallet_id:
        return None
    return MatchedWallet(wallet_id=found_id, address=found["address"], chain_type="ethereum")
