"""Pure grouped-review composition for the inactive consent stage.

No database access. The review groups one exact saved revision with its rules and
evidence status, the resolved wallet/network, the reviewed terms (allocation,
per-asset cumulative allowances, attempts, gas, expiry and stop effects), the
read-only facts from the accepted modules, and the material limitations. The
meaning and its hash bind the adopted identities only, so a later read of the
same records cannot drift the reviewed meaning. Every review is INACTIVE.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from edge_os_api.consent.types import CONSENT_STATUS, ReviewedTerms
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.strategies import compiler
from edge_os_api.wallet_setup.types import NetworkId

# The accepted binding network ids mapped to their accepted contract names.
BINDING_NETWORK_NAMES = {
    NetworkId.MONAD_MAINNET: "monad:143",
    NetworkId.MONAD_TESTNET: "monad-testnet:10143",
}

INACTIVE_NOTES = (
    "allocation_is_not_wallet_balance",
    "historical_success_is_not_required",
    "route_and_policy_evidence_may_be_unqualified",
    "no_live_operational_gate_is_claimed",
)


def network_name(network_id: int) -> str | None:
    """Map an accepted binding network id to its contract name. An unknown id returns `None`."""
    try:
        return BINDING_NETWORK_NAMES.get(NetworkId(network_id))
    except ValueError:
        return None


def assets_outside_network(network_id: str, asset_ids: list[str]) -> list[str]:
    """Asset ids that do not carry the wallet's own network prefix. Different networks never mix."""
    prefix = network_id + "/"
    return [asset_id for asset_id in asset_ids if not asset_id.startswith(prefix)]


def parse_saved_strategy(strategy_canonical: str) -> dict[str, Any]:
    """Parse and re-validate the exact saved revision bytes through the accepted compiler."""
    strategy = record_contract.strict_loads(strategy_canonical)
    compiler.validate_strategy(strategy)
    return strategy


def strategy_block(strategy: dict[str, Any]) -> dict[str, Any]:
    """The rules the owner reviews, taken verbatim from the exact saved revision."""
    return {
        "strategy_id": strategy["strategy_id"],
        "schema_version": strategy["schema_version"],
        "domain": strategy["domain"],
        "data_inputs": strategy["data_inputs"],
        "market": strategy["market"],
        "entry": strategy["entry"],
        "exit": strategy["exit"],
        "invalidation": strategy["invalidation"],
        "sizing": strategy["sizing"],
        "action_scope": strategy["action_scope"],
        "additions": strategy["additions"],
        "partial_exits": strategy["partial_exits"],
        "risk_limits": strategy["risk_limits"],
        "cost_assumptions": strategy["cost_assumptions"],
        "warmup_buckets": strategy["warmup_buckets"],
        "execution_permission": strategy["execution_permission"],
    }


def review_meaning(
    *,
    strategy_identity: dict[str, Any],
    terms: ReviewedTerms,
    agent_id: str,
    wallet_id: str,
    network_id: str,
) -> dict[str, Any]:
    """The stable adopted meaning. Volatile read-only facts are deliberately excluded."""
    return {
        "agent_id": agent_id,
        "wallet_id": wallet_id,
        "network_id": network_id,
        "strategy": strategy_identity,
        "terms_hash": terms.content_hash(),
        "status": CONSENT_STATUS,
    }


def content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def strategy_identity(*, strategy_id: str, revision_id: str, content_sha256: str,
                      manifest_sha256: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "revision_id": revision_id,
        "content_sha256": content_sha256,
        "manifest_sha256": manifest_sha256,
    }


def build_review_content(
    *,
    meaning: dict[str, Any],
    terms: ReviewedTerms,
    strategy: dict[str, Any],
    funding: list[dict[str, Any]],
    existing_allowances: list[dict[str, Any]],
    existing_decisions: list[dict[str, Any]],
    stops: list[dict[str, Any]],
    unknowns: list[str],
) -> dict[str, Any]:
    """Compose the stored review content: the meaning, the exact terms and the display facts."""
    review = {
        "status": CONSENT_STATUS,
        "authority": "INACTIVE",
        "inactive": True,
        "strategy": strategy,
        "operating_purpose": terms.operating_purpose,
        "terms_version": terms.terms_version,
        "terms_hash": terms.content_hash(),
        "allocation": [amount.model_dump(mode="json") for amount in terms.allocation],
        "allowances": [term.model_dump(mode="json") for term in terms.allowances],
        "attempt_budget": terms.attempt_budget,
        "gas_budget": terms.gas_budget.model_dump(mode="json") if terms.gas_budget is not None else None,
        "expiry": terms.expiry,
        "stop_effects": list(terms.stop_effects),
        "route": terms.route.model_dump(mode="json"),
        "policy": terms.policy.model_dump(mode="json") if terms.policy is not None else None,
        "evidence": terms.evidence.model_dump(mode="json"),
        "funding": funding,
        "existing_allowances": existing_allowances,
        "existing_decisions": existing_decisions,
        "stops": stops,
        "unknowns": unknowns,
        "notes": list(INACTIVE_NOTES),
    }
    return {"meaning": meaning, "terms": terms.model_dump(mode="json"), "review": review}
