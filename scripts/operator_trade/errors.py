"""Stable, sanitized operator errors.

The script handles real funds. Every refusal has a stable code so an operator and a test can tell
two different failures apart. Details carry only local field names or public chain data; never an
RPC URL, a credential, a key path or provider text.
"""

from __future__ import annotations


class OperatorError(Exception):
    """One stopped operator step. ``code`` is the stable reason; ``detail`` is safe local context."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
