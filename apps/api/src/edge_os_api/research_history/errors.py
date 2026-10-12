"""Errors for the local research-history adapter.

They subclass the reused P07 ``InvalidInput`` so a consumer that catches the
accepted error type also catches a malformed caller profile, limit, evidence or
manifest. Each error carries a stable code so a caller can branch without
reading message text.
"""

from __future__ import annotations

from edge_os_api.research_history.qualification_engine import InvalidInput


class AdapterInputError(InvalidInput):
    """A caller supplied a value the adapter cannot turn into valid P07 evidence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.detail = detail


class InvalidLimits(AdapterInputError):
    """A finite collection limit is missing, negative or not an integer."""

    def __init__(self, detail: str) -> None:
        super().__init__("INVALID_LIMIT", detail)


class ManifestTampered(AdapterInputError):
    """A manifest does not match its own content hash or its declared page facts."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
