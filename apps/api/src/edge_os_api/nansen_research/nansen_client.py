"""Read-only Nansen Token God Mode client over an injected transport.

The client frames one bounded provider call at a time. It enforces the operation
allowlist, finite request/byte/credit/deadline limits, and error sanitization. It
counts an attempted request before the transport call, so a call that raises still
counts. It never retries, never upgrades and never sends a payment header. It does
not read or set a credential; the injected transport owns any credential.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from edge_os_api.nansen_research.errors import (
    NansenAuthError,
    NansenBudgetExhausted,
    NansenContractError,
    NansenPaymentRequired,
    NansenProtocolError,
    NansenProviderError,
    NansenRateLimited,
    NansenRequestError,
    NansenTimeout,
)
from edge_os_api.nansen_research.models import NansenContext, NansenLimits
from edge_os_api.nansen_research.serialization import (
    canonical_sha256,
    load_provider_json,
    parse_instant,
    utc_now,
)
from edge_os_api.nansen_research.transport import NansenResponse, NansenTransport

OPERATIONS: dict[str, tuple[str, str, Decimal]] = {
    "holders": ("POST", "/api/v1/tgm/holders", Decimal("5")),
    "flows": ("POST", "/api/v1/tgm/flows", Decimal("1")),
}

ALLOWED_BODY_FIELDS: dict[str, frozenset[str]] = {
    "holders": frozenset({"chain", "token_address", "aggregate_by_entity", "label_type",
                          "pagination", "filters", "premium_labels", "order_by"}),
    "flows": frozenset({"chain", "token_address", "date", "label", "pagination", "filters", "order_by"}),
}

RETAINED_HEADERS = ("x-request-id", "x-nansen-credits-cost", "x-nansen-credits-used",
                    "x-nansen-credits-remaining", "retry-after")

# The pinned provider error envelope codes. A body code outside this set is not a
# trusted provider code and never reaches an error, a source record or a report.
PROVIDER_ERROR_CODES = frozenset({
    "missing_field", "unknown_field", "invalid_field_value", "invalid_address_format",
    "invalid_date_format", "invalid_date_range", "mutually_exclusive_fields", "value_out_of_range",
    "too_many_items", "unauthenticated", "forbidden", "insufficient_scope", "geo_blocked",
    "plan_upgrade_required", "insufficient_credits", "rate_limit_exceeded", "not_found",
    "method_not_allowed", "conflict", "payload_too_large", "query_timeout", "query_too_large",
    "upstream_unavailable", "internal_error",
})


def _effective_charge(reservation: Decimal, quoted: str | None, deducted: str | None) -> Decimal:
    """The settled credits for one call: the charged amount when known, else the reservation.

    A known deduction or quote replaces the conservative reservation. An unknown
    settlement keeps the reservation, so the cap stays conservative.
    """
    for value in (deducted, quoted):
        if value is None:
            continue
        try:
            amount = Decimal(value)
        except InvalidOperation:
            continue
        if amount.is_finite() and amount >= 0:
            return amount
    return reservation


@dataclass(frozen=True)
class NansenFetch:
    """The framed facts of one successful provider call."""

    operation: str
    method: str
    path: str
    request_body: dict
    request_sha256: str
    status: int
    request_id: str | None
    quoted_credits: str | None
    deducted_credits: str | None
    remaining_credits: str | None
    retry_after: str | None
    response_sha256: str
    collected_at: str
    payload: dict


def _safe_credit(text: str | None) -> str | None:
    """A received credit amount as its exact text, or ``None``.

    Only a finite, nonnegative decimal is a credit amount. ``NaN``, a signaling
    NaN, a positive or negative infinity, a negative finite value or malformed
    text returns ``None`` so the invalid text is never exposed as a charge.
    """
    if text is None:
        return None
    try:
        amount = Decimal(text.strip())
    except (InvalidOperation, AttributeError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return text


def _provider_code(body: bytes) -> str | None:
    """A bounded, documented provider error code only.

    Any message, detail or instruction-like string is refused, so provider text
    never reaches an error, a source record or a report control field.
    """
    try:
        payload = load_provider_json(body)
    except (UnicodeDecodeError, ValueError):
        return None
    if isinstance(payload, Mapping) and isinstance(payload.get("code"), str):
        code = payload["code"]
        if code in PROVIDER_ERROR_CODES:
            return code
    return None


class NansenClient:
    """A bounded read-only client. One transport call per ``call``, no retry."""

    def __init__(self, transport: NansenTransport, limits: NansenLimits, *,
                 context: NansenContext | None = None, clock: Callable[[], str] = utc_now) -> None:
        limits.validate()
        self._context = context or NansenContext()
        self._context.validate()
        self._transport = transport
        self._limits = limits
        self._clock = clock
        self._deadline = parse_instant(limits.deadline_utc) if limits.deadline_utc is not None else None
        self._attempts = 0
        self._pages = 0
        self._bytes = 0
        self._reservations: list[Decimal] = []
        self._fetches: list[NansenFetch] = []

    @property
    def context(self) -> NansenContext:
        return self._context

    @property
    def limits(self) -> NansenLimits:
        return self._limits

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def pages(self) -> int:
        return self._pages

    @property
    def bytes_read(self) -> int:
        return self._bytes

    @property
    def fetches(self) -> tuple[NansenFetch, ...]:
        return tuple(self._fetches)

    @property
    def reserved_credits(self) -> Decimal:
        return sum(self._reservations, Decimal("0"))

    def now(self) -> str:
        """The injected clock instant, so a failure record matches the run clock."""
        return self._clock()

    def _pin_body(self, operation: str, body: Mapping[str, Any]) -> dict:
        if not isinstance(body, Mapping):
            raise NansenRequestError("BODY_INVALID", "the request body must be a mapping")
        extra = set(body) - ALLOWED_BODY_FIELDS[operation]
        if extra:
            raise NansenRequestError("BODY_NOT_ALLOWED", f"unexpected body fields: {sorted(extra)}")
        pinned = dict(body)
        if pinned.get("chain") != self._context.network:
            raise NansenRequestError("WRONG_NETWORK", f"body chain must be {self._context.network}")
        if operation == "holders":
            if pinned.get("premium_labels", False) is not False:
                raise NansenRequestError("PREMIUM_NOT_ALLOWED", "premium labels are not allowed")
            pinned["premium_labels"] = False
        return pinned

    def _enforce_budget(self, reservation: Decimal) -> None:
        if self._deadline is not None and parse_instant(self._clock()) > self._deadline:
            raise NansenTimeout("DEADLINE", "the local deadline passed before dispatch")
        if self._attempts >= self._limits.max_requests:
            raise NansenBudgetExhausted("REQUEST_LIMIT", "the request cap is reached")
        if self.reserved_credits + reservation > self._limits.max_credits:
            raise NansenBudgetExhausted("CREDIT_LIMIT", "the credit cap is reached")

    def _received(self, error, status, retained, response_sha256, retry_after=None):
        """Attach the sanitized allowlisted facts of a received response to an error."""
        error.status = status
        error.request_id = retained.get("x-request-id")
        error.quoted_credits = _safe_credit(retained.get("x-nansen-credits-cost"))
        error.deducted_credits = _safe_credit(retained.get("x-nansen-credits-used"))
        error.remaining_credits = _safe_credit(retained.get("x-nansen-credits-remaining"))
        error.response_sha256 = response_sha256
        error.retry_after = retry_after
        return error

    def _raise_for_status(self, status: int, body: bytes, retained: Mapping[str, str],
                          response_sha256: str) -> None:
        if 200 <= status < 300:
            return
        if status == 401:
            raise self._received(
                NansenAuthError("UNAUTHENTICATED", "the provider refused the request as unauthenticated"),
                status, retained, response_sha256)
        if status == 402:
            raise self._received(
                NansenPaymentRequired("PAYMENT_REQUIRED", "the provider requires payment; no payment path is taken"),
                status, retained, response_sha256)
        if status == 429:
            retry_after = retained.get("retry-after")
            if retry_after is not None:
                try:
                    int(retry_after.strip())
                except ValueError:
                    retry_after = None
            raise self._received(
                NansenRateLimited("the provider rate limit rejected the request", retry_after),
                status, retained, response_sha256, retry_after)
        code = _provider_code(body)
        raise self._received(
            NansenProviderError(code or f"HTTP_{status}", f"the provider returned status {status}"),
            status, retained, response_sha256)

    def _decode(self, body: bytes) -> dict:
        try:
            payload = load_provider_json(body)
        except (UnicodeDecodeError, ValueError) as error:
            raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "the response is not JSON") from error
        if not isinstance(payload, dict):
            raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "the response is not a JSON object")
        return payload

    def call(self, operation: str, body: Mapping[str, Any]) -> NansenFetch:
        """Make one bounded provider call and frame its success facts."""
        if operation not in OPERATIONS:
            raise NansenRequestError("OPERATION_NOT_ALLOWED", f"operation {operation!r} is not allowed")
        method, path, reservation = OPERATIONS[operation]
        pinned = self._pin_body(operation, body)
        self._enforce_budget(reservation)
        request_sha = canonical_sha256(pinned)
        self._attempts += 1
        self._reservations.append(reservation)

        response = self._transport.request(operation, path, pinned)
        if not isinstance(response, NansenResponse):
            raise NansenProtocolError("TRANSPORT_NOT_A_RESPONSE", "the transport returned a non-response value")
        self._bytes += len(response.body)
        headers = {str(name).lower(): str(value) for name, value in response.headers.items()}
        retained = {name: headers[name] for name in RETAINED_HEADERS if name in headers}
        response_hash = hashlib.sha256(response.body).hexdigest()
        if self._bytes > self._limits.max_bytes:
            raise self._received(
                NansenContractError("OVERSIZED_RESPONSE", "the response body passes the byte cap"),
                response.status, retained, response_hash)
        self._raise_for_status(response.status, response.body, retained, response_hash)
        try:
            payload = self._decode(response.body)
        except NansenContractError as error:
            raise self._received(error, response.status, retained, response_hash)
        self._pages += 1
        fetch = NansenFetch(
            operation=operation,
            method=method,
            path=path,
            request_body=pinned,
            request_sha256=request_sha,
            status=response.status,
            request_id=retained.get("x-request-id"),
            quoted_credits=_safe_credit(retained.get("x-nansen-credits-cost")),
            deducted_credits=_safe_credit(retained.get("x-nansen-credits-used")),
            remaining_credits=_safe_credit(retained.get("x-nansen-credits-remaining")),
            retry_after=retained.get("retry-after"),
            response_sha256=response_hash,
            collected_at=self._clock(),
            payload=payload,
        )
        self._reservations[-1] = _effective_charge(reservation, fetch.quoted_credits, fetch.deducted_credits)
        self._fetches.append(fetch)
        return fetch
