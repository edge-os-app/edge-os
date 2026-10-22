"""The one classifier for a Privy signing-error reply.

The Privy sign-only adapter and the live policy proof share `reply_code`. Only
HTTP 400 with the provider code `policy_violation`, and no success-envelope key,
is the definite policy denial. The proof classifies the same status and code as
`POLICY_DENY`. Every other status, code, media type or body is not a denial.
Reply text is never saved, logged or re-raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

POLICY_DENIAL_STATUS = 400
POLICY_DENIAL_CODE = "policy_violation"


def reply_code(body: Any) -> str | None:
    """Return the Privy error code from a flat or nested error body, or None.

    Privy documents ``policy_violation`` but not one body shape. The accepted
    proof reads ``code``, ``error.code`` and the string ``error``; it never keeps
    any other reply text.
    """
    if not isinstance(body, Mapping):
        return None
    code = body.get("code")
    if isinstance(code, str):
        return code
    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, Mapping):
        nested = error.get("code")
        if isinstance(nested, str):
            return nested
    return None


def is_policy_denial(status: Any, body: Any) -> bool:
    """Whether this exact status and body are the Privy policy denial the proof accepts.

    A body that also carries a success envelope key is never a denial: if `data` or
    `method` is present, a signature may exist even when the status is 400.
    """
    if not isinstance(body, Mapping) or "data" in body or "method" in body:
        return False
    return type(status) is int and status == POLICY_DENIAL_STATUS and reply_code(body) == POLICY_DENIAL_CODE
