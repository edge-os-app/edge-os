"""The process-environment credential source for the accepted research slots (#58 RESEARCH-ENVIRONMENT-CREDENTIALS).

`EnvironmentCredentialSource` is the `CredentialSource` the API and the worker pass as `credentials=`. It reads one
environment variable only when `read(slot)` is called, and only for a slot in `ALLOWED_SLOTS`; any other slot is refused
before the environment is consulted. Nothing is captured at import or construction, and a refusal message never holds a
slot value or the requested name. The QuickNode URL host is checked by `prepare_history`, not here. See
`docs/implementation/RESEARCH_ENVIRONMENT_CREDENTIALS.md`.
"""

from __future__ import annotations

import os

from edge_os_api.core.research.released_source_runtime import CredentialUnavailable

ALLOWED_SLOTS = frozenset({"HYPERSYNC_API_KEY", "QUICKNODE_API_URL", "NANSEN_API_KEY"})


class EnvironmentCredentialSource:
    """Reads an allowed slot from `os.environ` at call time. Holds no state."""

    def read(self, slot: str) -> str:
        if slot not in ALLOWED_SLOTS:
            raise CredentialUnavailable("the credential slot is not allowed")
        value = os.environ.get(slot, "")
        if not value.strip():
            raise CredentialUnavailable("the credential slot has no value")
        return value
