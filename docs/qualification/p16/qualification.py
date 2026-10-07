"""Offline P16 wallet-qualification model. This module never calls a provider."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


NETWORK_ID = 10143
_SETUP_ID = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")


@dataclass(frozen=True)
class Binding:
    owner_id: str
    agent_id: str
    wallet_id: str
    network_id: int
    position_id: str

    def matches(self, other: Binding) -> bool:
        return self == other

    def with_value(self, field: str, value: Any) -> Binding:
        if field not in self.__dataclass_fields__:
            raise ValueError(f"unknown binding field: {field}")
        return replace(self, **{field: value})


@dataclass(frozen=True)
class Position:
    binding: Binding
    asset_id: str
    inventory_raw: str


class SetupLedger:
    """Temporary local state for the authored offline recovery check."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: dict[str, dict[str, Any]] = {}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("setup ledger must contain a JSON object")
            self.records = loaded

    def get(self, setup_id: str) -> dict[str, Any]:
        return dict(self.records[setup_id])

    def put(self, setup_id: str, record: dict[str, Any]) -> None:
        self.records[setup_id] = dict(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.records, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.path)


class SetupManager:
    """Model stable local setup identity with an explicitly authored fake."""

    def __init__(self, ledger: SetupLedger, provider: FakePrivy) -> None:
        self.ledger = ledger
        self.provider = provider

    def create(
        self,
        setup_id: str,
        owner_id: str,
        agent_id: str,
        *,
        lose_response: bool = False,
    ) -> str:
        record = self.prepare(setup_id, owner_id, agent_id)
        if record["owner_id"] != owner_id or record["agent_id"] != agent_id:
            raise ValueError("setup identity is already bound to another owner or agent")
        if record["state"] != "REQUESTED":
            return self.resume(setup_id)
        return self._attempt(record, lose_response=lose_response)

    def prepare(self, setup_id: str, owner_id: str, agent_id: str) -> dict[str, Any]:
        if not _SETUP_ID.fullmatch(setup_id):
            raise ValueError("setup_id must use 1-48 URL-safe characters")
        if not owner_id or not agent_id:
            raise ValueError("owner_id and agent_id are required")
        if setup_id in self.ledger.records:
            return self.ledger.get(setup_id)
        record = {
            "state": "REQUESTED",
            "setup_id": setup_id,
            "owner_id": owner_id,
            "agent_id": agent_id,
            "network_id": NETWORK_ID,
            "external_id": f"edgeos_{setup_id}",
            "idempotency_key": str(uuid4()),
            "wallet_id": None,
        }
        self.ledger.put(setup_id, record)
        return record

    def resume(self, setup_id: str) -> str:
        record = self.ledger.get(setup_id)
        if record["state"] == "CANCELLED":
            return "CANCELLED"
        if record["state"] == "CONFIRMED":
            return "CONFIRMED"
        if record["state"] not in {"REQUESTED", "UNKNOWN"}:
            raise ValueError("saved setup state is invalid")
        return self._attempt(record)

    def cancel(self, setup_id: str) -> str:
        record = self.ledger.get(setup_id)
        if record["state"] == "REQUESTED":
            record["state"] = "CANCELLED"
        elif record["state"] not in {"UNKNOWN", "CONFIRMED", "CANCELLED"}:
            raise ValueError("setup has an unsupported state")
        self.ledger.put(setup_id, record)
        return record["state"]

    def _attempt(self, record: dict[str, Any], *, lose_response: bool = False) -> str:
        try:
            response = self.provider.create_wallet(
                idempotency_key=record["idempotency_key"],
                request={
                    "owner_id": record["owner_id"],
                    "agent_id": record["agent_id"],
                    "network_id": record["network_id"],
                    "external_id": record["external_id"],
                },
                lose_response=lose_response,
            )
        except Exception:
            record["state"] = "UNKNOWN"
            self.ledger.put(record["setup_id"], record)
            raise
        if response is None:
            record["state"] = "UNKNOWN"
        else:
            record["state"] = "CONFIRMED"
            record["wallet_id"] = response["wallet_id"]
        self.ledger.put(record["setup_id"], record)
        return record["state"]


class FakePrivy:
    """An authored fake. Its results are not Privy provider evidence."""

    def __init__(self) -> None:
        self.wallets: dict[str, dict[str, Any]] = {}
        self.idempotency: dict[str, tuple[str, str]] = {}
        self.create_count = 0
        self.sign_attempts: list[dict[str, str]] = []

    def create_wallet(
        self,
        *,
        idempotency_key: str,
        request: dict[str, Any],
        lose_response: bool = False,
    ) -> dict[str, str] | None:
        fingerprint = json.dumps(request, sort_keys=True, separators=(",", ":"))
        cached = self.idempotency.get(idempotency_key)
        if cached is not None:
            if cached[0] != fingerprint:
                raise ValueError("an idempotency key cannot identify changed setup data")
            wallet_id = cached[1]
        else:
            self.create_count += 1
            wallet_id = f"wallet-{self.create_count}"
            self.wallets[wallet_id] = {
                **request,
                "address": f"address-{wallet_id}",
                "signers": set(),
                "pending_records": [],
            }
            self.idempotency[idempotency_key] = (fingerprint, wallet_id)
        if lose_response:
            return None
        return {"wallet_id": wallet_id}

    def add_signer(self, wallet_id: str, signer_id: str) -> None:
        self.wallets[wallet_id]["signers"].add(signer_id)

    def remove_signer(self, wallet_id: str, signer_id: str) -> None:
        self.wallets[wallet_id]["signers"].discard(signer_id)

    def add_pending_record(self, wallet_id: str, record_id: str) -> None:
        self.wallets[wallet_id]["pending_records"].append(record_id)

    def pending_records(self, wallet_id: str) -> list[str]:
        return list(self.wallets[wallet_id]["pending_records"])

    def safe_test_payload(self, wallet_id: str) -> dict[str, Any]:
        wallet = self.wallets[wallet_id]
        return {
            "method": "eth_signTransaction",
            "type": 2,
            "chain_id": NETWORK_ID,
            "to": wallet["address"],
            "value": "0x0",
            "data": "0x",
            "gas_limit": 21000,
            "nonce": 0,
            "max_fee_per_gas": "1",
            "max_priority_fee_per_gas": "1",
        }

    def sign(self, wallet_id: str, signer_id: str, payload: dict[str, Any]) -> str:
        self.sign_attempts.append({"wallet_id": wallet_id, "signer_id": signer_id})
        wallet = self.wallets[wallet_id]
        if signer_id not in wallet["signers"]:
            return "DENY_SIGNER_NOT_ATTACHED"
        safe = self.safe_test_payload(wallet_id)
        if payload != safe:
            return "DENY_FAKE_POLICY"
        return "ALLOW_FAKE_ONLY"

    def owner_access(self, wallet_id: str, owner_id: str) -> bool:
        return self.wallets[wallet_id]["owner_id"] == owner_id


def local_binding_allows(expected: Binding, request: Binding) -> bool:
    return expected.matches(request)


def demo() -> dict[str, str]:
    """Run a deterministic fake-only example and label its evidence limits."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="edge-os-p16-") as directory:
        provider = FakePrivy()
        manager = SetupManager(SetupLedger(Path(directory) / "setup.json"), provider)
        state = manager.create("agent-a", "owner-a", "agent-a", lose_response=True)
        state = manager.resume("agent-a")
        record = manager.ledger.get("agent-a")
        return {
            "setup_recovery": state,
            "wallet_creations": str(provider.create_count),
            "evidence_class": "AUTHORED_FAKE_ONLY",
            "provider_executed": "NOT_RUN",
            "owner_observed": "NOT_RUN",
            "wallet_id": str(record["wallet_id"]),
        }


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, sort_keys=True))
