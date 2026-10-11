"""Local inactive controlled-qualification consent domain (P26 inactive preparation).

Owned application package. It groups one exact-revision/wallet/limits review and
persists an owner's explicit adoption as a clearly INACTIVE consent. It provides
no API/UI wiring, no shared migration, no activation, no signing, no admission,
no scheduler and no provider-policy operation, and it mints no active authority
snapshot. Live execution and full P26 activation remain closed.
"""

from edge_os_api.consent.adoption import acquire_review_lock, consent_hash, find_adoption, save_adoption, to_consent_view
from edge_os_api.consent.grouped_review import (assets_outside_network, build_review_content, content_hash,
                                                network_name, parse_saved_strategy, review_meaning, strategy_block,
                                                strategy_identity)
from edge_os_api.consent.records import (CONSENT_SCHEMA, ConsentAdoptionRow, ConsentBase, ConsentDenialRow,
                                         ConsentReviewRow)
from edge_os_api.consent.service import ConsentConflict, ConsentDenied, ConsentError, ConsentNotFound, ConsentService
from edge_os_api.consent.types import (AdoptionRequest, AssetAmount, AllowanceTerm, ConsentView, GroupedReviewView,
                                       ReviewedEvidence, ReviewedPolicy, ReviewedRoute, ReviewedTerms, ReviewRequest,
                                       CONSENT_STATUS, NETWORKS, OPERATIONS)

__all__ = [
    "CONSENT_SCHEMA",
    "CONSENT_STATUS",
    "NETWORKS",
    "OPERATIONS",
    "AdoptionRequest",
    "AllowanceTerm",
    "AssetAmount",
    "ConsentAdoptionRow",
    "ConsentBase",
    "ConsentConflict",
    "ConsentDenied",
    "ConsentDenialRow",
    "ConsentError",
    "ConsentNotFound",
    "ConsentReviewRow",
    "ConsentService",
    "ConsentView",
    "GroupedReviewView",
    "ReviewedEvidence",
    "ReviewedPolicy",
    "ReviewedRoute",
    "ReviewedTerms",
    "ReviewRequest",
    "acquire_review_lock",
    "assets_outside_network",
    "build_review_content",
    "consent_hash",
    "content_hash",
    "find_adoption",
    "network_name",
    "parse_saved_strategy",
    "review_meaning",
    "save_adoption",
    "strategy_block",
    "strategy_identity",
    "to_consent_view",
]
