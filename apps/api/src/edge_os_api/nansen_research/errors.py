"""Errors for the local Nansen research package.

Every error carries a stable ``code`` so a caller or test can branch without
reading message text. ``NansenInputError`` marks a caller problem that must be
fixed. ``NansenTransportError`` marks an expected provider or transport failure
whose partial result the collector records without a retry.
"""

from __future__ import annotations


class NansenError(Exception):
    """Base error with a stable code and a short detail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class NansenInputError(NansenError):
    """A caller supplied a value the package cannot turn into valid evidence."""


class NansenLimitError(NansenInputError):
    """A finite limit is missing, negative or not an integer."""


class NansenRequestError(NansenInputError):
    """A local rule refuses a request before dispatch.

    Used for a non-allowlisted operation or an unexpected body field. The caller
    must fix the request. It propagates and never becomes partial evidence.
    """


class NansenProtocolError(NansenInputError):
    """An injected transport returned a value outside the package protocol."""


class NansenBudgetExhausted(NansenLimitError):
    """A caller-configured request or credit cap stops further dispatch."""


class NansenTransportError(NansenError):
    """An expected provider or transport failure.

    The collector records the attempted call and a partial result. A programmer
    defect must raise a different error type so it is not mistaken for a provider
    failure.
    """


class NansenContractError(NansenTransportError):
    """A provider response violates the pinned local contract.

    Used for an oversized or malformed response, or a response that contradicts
    the request. The collector records a partial result rather than crashing the
    run. No row of a refused response is retained.
    """


class NansenAuthError(NansenTransportError):
    """The provider refused the request as unauthenticated or forbidden."""


class NansenRateLimited(NansenTransportError):
    """The provider rate limit rejected the request."""


class NansenPaymentRequired(NansenTransportError):
    """The provider asked for payment. No payment path is taken."""


class NansenProviderError(NansenTransportError):
    """Any other provider error, carrying only the stable provider code."""


class NansenTimeout(NansenTransportError):
    """A local deadline or an injected timeout stopped the call."""


class NansenCancelled(NansenTransportError):
    """The caller cancelled the collection. The partial result is retained."""
