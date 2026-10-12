"""Bounded agent wallet setup: prepare, dispatch, cancel, resume and read.

The application mounts these authenticated routes over the `wallet_setups` schema from migration
0007. The only concrete provider is an authored local fixture, refused in production; real mode is
the fail-closed unavailable provider. It creates no wallet, signer, funding, mandate activation,
position or trading action. External wallet creation and lookup stay authored fakes, never provider
evidence.
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
