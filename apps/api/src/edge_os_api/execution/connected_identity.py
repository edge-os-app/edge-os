"""Server-side identity and authority resolution for the connected financial journey.

IC01: one owner-scoped resolver binds the saved publication revision UUID, its canonical bytes and
content/manifest digests to the hash-derived execution revision identity. Every later step uses the
returned `ConnectedAgent`, so consent, decision, intent and receipt carry one consistent identity, and a
forged, stale or mismatched identity resolves to nothing.

IC05: activation authority comes only from saved server state: the exact adopted consent for this agent,
wallet, network and revision, plus the server-owned qualification profile. The consent row itself stays
INACTIVE. In fixture mode the server derives a SYNTHETIC approval snapshot from the adopted terms; in
production no qualification exists yet, so no approval exists and every action is unavailable. No request
field can mark anything qualified, active or approved.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.admission.types import AllowanceCap, ApprovalSnapshot, IdentityBinding
from edge_os_api.consent.records import ConsentAdoptionRow, ConsentReviewRow
from edge_os_api.consent.types import ReviewedTerms, parse_utc
from edge_os_api.execution.types import FrozenRevision, freeze_revision
from edge_os_api.records import contract_adapter as record_contract
from edge_os_api.records.models import StrategyRevision
from edge_os_api.strategies.compiler import CompilerError
from edge_os_api.wallet_setup.persistence import load_setup
from edge_os_api.wallet_setup.types import SetupState

NETWORK_NAMES = {143: "monad:143", 10143: "monad-testnet:10143"}
NATIVE_GAS_DECIMALS = 18
CONNECTED_TERMS_VERSION = "connected-spot/1"
# The allowance names the connected terms version requires. Each maps to one approval cap.
ALLOWANCE_NAMES = ("quote_input", "base_inventory", "per_action_gas", "per_exit_gas")
FIXTURE_QUALIFICATION_LABEL = "SYNTHETIC_FIXTURE_QUALIFICATION"


@dataclass(frozen=True)
class AssetIdentity:
    asset_id: str
    decimals: int


@dataclass(frozen=True)
class ConnectedAgent:
    """The verified owner's agent with its confirmed wallet and exact publication/execution revision."""

    owner_id: uuid.UUID
    agent_id: str
    wallet_id: str
    network_number: int
    network_id: str
    strategy_id: str
    publication_revision_id: uuid.UUID
    content_sha256: str
    manifest_sha256: str
    revision: FrozenRevision
    quote: AssetIdentity
    base: AssetIdentity
    gas: AssetIdentity

    @property
    def strategy(self) -> dict[str, Any]:
        return self.revision.strategy

    def identity(self) -> dict[str, Any]:
        return {"agent_id": self.agent_id, "wallet_id": self.wallet_id, "network_id": self.network_id,
                "strategy_id": self.strategy_id, "publication_revision_id": str(self.publication_revision_id),
                "content_sha256": self.content_sha256, "manifest_sha256": self.manifest_sha256,
                "execution_revision_id": self.revision.revision_id,
                "market_binding_id": self.revision.market_binding_id}


@dataclass(frozen=True)
class AdoptedConsent:
    adoption_id: uuid.UUID
    review_id: uuid.UUID
    consent_hash: str
    review_hash: str
    terms: ReviewedTerms
    adopted_at: dt.datetime


class IdentityError(Exception):
    """The saved identities disagree. The caller denies without any provider effect."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def asset_ids_for(network_number: int, market: dict[str, Any]) -> tuple[AssetIdentity, AssetIdentity, AssetIdentity]:
    """The funding/admission asset ids for the revision's market on the bound network."""
    prefix = NETWORK_NAMES[network_number]
    binding = market["research_binding"]
    quote = AssetIdentity(f"{prefix}/{binding['quote_asset'].lower()}", int(binding["quote_decimals"]))
    base = AssetIdentity(f"{prefix}/{binding['base_asset'].lower()}", int(binding["base_decimals"]))
    gas = AssetIdentity(f"{prefix}/native", NATIVE_GAS_DECIMALS)
    return quote, base, gas


def resolve_agent(session: Session, owner_id: uuid.UUID, agent_id: str) -> ConnectedAgent | None:
    """Resolve the confirmed agent wallet and its exact saved revision. Anything missing or drifted is None.

    The publication UUID, the saved canonical bytes and both digests must agree with the setup binding, and
    the frozen execution identity must hash to the saved content digest.
    """
    setup = load_setup(session, owner_id, agent_id, lock=False)
    if setup is None or setup.state != SetupState.CONFIRMED.value or not setup.wallet_id:
        return None
    row = session.execute(select(StrategyRevision).where(
        StrategyRevision.owner_id == owner_id, StrategyRevision.strategy_id == setup.strategy_id,
        StrategyRevision.revision_id == setup.strategy_revision_id)).scalar_one_or_none()
    if row is None or row.content_sha256 != setup.content_sha256 or row.manifest_sha256 != setup.manifest_sha256:
        return None
    try:
        strategy = record_contract.strict_loads(row.strategy_canonical)
        revision = freeze_revision(strategy)
    except (CompilerError, record_contract.Invalid, ValueError, KeyError, TypeError):
        return None
    if revision.content_hash != "sha256:" + row.content_sha256:
        return None
    if setup.network_id not in NETWORK_NAMES:
        return None
    quote, base, gas = asset_ids_for(setup.network_id, revision.strategy["market"])
    return ConnectedAgent(owner_id=owner_id, agent_id=agent_id, wallet_id=setup.wallet_id,
                          network_number=setup.network_id, network_id=NETWORK_NAMES[setup.network_id],
                          strategy_id=row.strategy_id, publication_revision_id=row.revision_id,
                          content_sha256=row.content_sha256, manifest_sha256=row.manifest_sha256,
                          revision=revision, quote=quote, base=base, gas=gas)


def adopted_consent(session: Session, agent: ConnectedAgent) -> AdoptedConsent | None:
    """The latest adopted consent whose review binds exactly this agent, wallet, network and revision."""
    rows = session.execute(select(ConsentAdoptionRow, ConsentReviewRow).join(
        ConsentReviewRow, (ConsentReviewRow.review_id == ConsentAdoptionRow.review_id)
        & (ConsentReviewRow.owner_id == ConsentAdoptionRow.owner_id)).where(
        ConsentAdoptionRow.owner_id == agent.owner_id, ConsentReviewRow.agent_id == agent.agent_id,
        ConsentReviewRow.wallet_id == agent.wallet_id, ConsentReviewRow.network_id == agent.network_id,
        ConsentReviewRow.strategy_revision_id == agent.publication_revision_id,
        ConsentReviewRow.content_sha256 == agent.content_sha256,
        ConsentReviewRow.manifest_sha256 == agent.manifest_sha256,
    ).order_by(ConsentAdoptionRow.created_at.desc(), ConsentAdoptionRow.adoption_id.desc())).all()
    for adoption, review in rows:
        if adoption.review_hash != review.review_hash:
            continue
        try:
            terms = ReviewedTerms.model_validate(review.content["terms"])
        except Exception:  # noqa: BLE001 - a stored term set that no longer validates is not usable authority
            continue
        if terms.content_hash() != review.terms_hash:
            continue
        return AdoptedConsent(adoption_id=adoption.adoption_id, review_id=review.review_id,
                              consent_hash=adoption.consent_hash, review_hash=review.review_hash, terms=terms,
                              adopted_at=adoption.created_at)
    return None


def _cap(amount: Any) -> AllowanceCap:
    return AllowanceCap(asset_id=amount.asset_id, decimals=amount.decimals, approved_raw=amount.raw)


def derive_approval(agent: ConnectedAgent, consent: AdoptedConsent, *, qualification: str,
                    now: dt.datetime) -> tuple[ApprovalSnapshot | None, str | None]:
    """The approval snapshot the server may use for this agent now, or the reason none exists.

    Only the fixture qualification profile produces a snapshot, labelled SYNTHETIC. Expired terms, a
    different terms version, an asset outside the revision's market or a missing required limit deny.
    """
    if qualification != "fixture":
        return None, "ACTIVATION_UNAVAILABLE"
    terms = consent.terms
    if terms.terms_version != CONNECTED_TERMS_VERSION:
        return None, "TERMS_VERSION_UNSUPPORTED"
    if parse_utc(terms.expiry) <= now:
        return None, "CONSENT_EXPIRED"
    allowances = {term.name: term.amount for term in terms.allowances}
    if set(allowances) != set(ALLOWANCE_NAMES) or terms.gas_budget is None or len(terms.allocation) != 1:
        return None, "TERMS_INCOMPLETE"
    expected = {"quote_input": agent.quote, "base_inventory": agent.base, "per_action_gas": agent.gas,
                "per_exit_gas": agent.gas}
    for name, identity in expected.items():
        amount = allowances[name]
        if (amount.asset_id, amount.decimals) != (identity.asset_id, identity.decimals):
            return None, "TERMS_ASSET_MISMATCH"
    allocation = terms.allocation[0]
    if (allocation.asset_id, allocation.decimals) != (agent.quote.asset_id, agent.quote.decimals) or \
            (terms.gas_budget.asset_id, terms.gas_budget.decimals) != (agent.gas.asset_id, agent.gas.decimals):
        return None, "TERMS_ASSET_MISMATCH"
    actions = [action for action in terms.supported_actions if action in ("ENTRY", "EXIT")]
    if not actions:
        return None, "TERMS_INCOMPLETE"
    mandate = str(consent.adoption_id)
    approval = ApprovalSnapshot(
        approval_id=mandate,
        binding=IdentityBinding(agent_id=agent.agent_id, wallet_id=agent.wallet_id, network_id=agent.network_id,
                                strategy_revision=agent.revision.revision_id, mandate_id=mandate),
        state="ACTIVE", policy_binding=consent.consent_hash, expires_at=terms.expiry, actions=actions,
        allocation_quote=_cap(allocation), quote_allowance=_cap(allowances["quote_input"]),
        base_allowance=_cap(allowances["base_inventory"]), gas=_cap(terms.gas_budget),
        per_action_gas=_cap(allowances["per_action_gas"]), per_exit_gas=_cap(allowances["per_exit_gas"]),
        attempt_budget=terms.attempt_budget, stops=[], exit_capacity_qualified=True, valuation_qualified=True,
        cost_model_qualified=True, fixture_label=FIXTURE_QUALIFICATION_LABEL)
    return approval, None
