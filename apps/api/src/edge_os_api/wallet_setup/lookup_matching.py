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


def match_claim(user: object, did: str, address: str, wallet_id: str | None,
                wallet_record: object = None) -> MatchedWallet | None:
    """Return the one embedded Ethereum wallet of this exact user with this exact address, or `None`.

    The verified DID's own linked wallet must match first. Its ID comes from that link; when the link has no ID,
    only `wallet_record` (the fixed by-address lookup answer) may supply it, with the same exact address, chain
    `ethereum` and a valid ID. Any ID present in the link, the record or the browser claim must agree. A record's
    `owner_id` (key quorum) or `entity` (attribution) is never read.
    """
    found = linked_wallet(user, did, address)
    if found is None or (wallet_id is not None and not valid_wallet_id(wallet_id)):
        return None
    ids = set()
    if found.get("id") is not None:
        if not valid_wallet_id(found.get("id")):
            return None
        ids.add(found["id"])
    if wallet_record is not None:
        if not (isinstance(wallet_record, dict) and valid_wallet_id(wallet_record.get("id"))
                and isinstance(wallet_record.get("address"), str)
                and wallet_record["address"].lower() == address.lower()
                and wallet_record.get("chain_type") == "ethereum"):
            return None
        ids.add(wallet_record["id"])
    if wallet_id is not None:
        ids.add(wallet_id)
    if len(ids) != 1 or (found.get("id") is None and wallet_record is None):
        return None
    return MatchedWallet(wallet_id=ids.pop(), address=found["address"], chain_type="ethereum")


def linked_wallet(user: object, did: str, address: str) -> dict[str, Any] | None:
    """The single embedded Ethereum account with this exact address in the verified DID's own user record."""
    if not (isinstance(user, dict) and valid_did(did) and user.get("id") == did and valid_address(address)):
        return None
    accounts = user.get("linked_accounts")
    if not isinstance(accounts, list):
        return None
    same = [a for a in accounts if _embedded_ethereum(a) and isinstance(a.get("address"), str)
            and a["address"].lower() == address.lower()]
    if len(same) != 1 or not valid_address(same[0]["address"]):
        return None
    return same[0]
