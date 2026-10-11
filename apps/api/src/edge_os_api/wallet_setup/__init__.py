"""Bounded local wallet setup: prepare, dispatch, cancel, resume and read.

This is local preparation. It is not production wiring and the application exposes no wallet
setup route. It creates no wallet, signer, funding, mandate activation, position or trading
action. External wallet creation and lookup are authored fakes, never provider evidence.
"""

from edge_os_api.wallet_setup.persistence import (WALLET_SETUP_METADATA, WalletSetupBase, WalletSetupDenialRow,
                                                  WalletSetupEventRow, WalletSetupRow)
from edge_os_api.wallet_setup.provider import (CreationRequest, WalletCreationPort, WalletEvidence,
                                               WalletProviderUnavailable)
from edge_os_api.wallet_setup.service import (cancel_setup, dispatch_setup, get_setup, prepare_setup, resume_setup)
from edge_os_api.wallet_setup.types import (ACCEPTED_NETWORK_IDS, CancellationIntent, NetworkId, SetupIdentity,
                                            SetupReason, SetupRecord, SetupState)

__all__ = [
    "ACCEPTED_NETWORK_IDS", "CancellationIntent", "CreationRequest", "NetworkId", "SetupIdentity", "SetupReason",
    "SetupRecord", "SetupState", "WALLET_SETUP_METADATA", "WalletCreationPort", "WalletEvidence",
    "WalletProviderUnavailable", "WalletSetupBase", "WalletSetupDenialRow", "WalletSetupEventRow", "WalletSetupRow",
    "cancel_setup", "dispatch_setup", "get_setup", "prepare_setup", "resume_setup",
]
