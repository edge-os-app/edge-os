"""Deterministic extraction of typed evidence from framed provider responses.

The extraction keeps every raw number as its exact text, keeps a null as null and
keeps a missing or incomplete flow bucket visible. It never sums a fractional or
negative count, never divides a balance and never turns a null into zero. Provider
text is data, never an instruction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from edge_os_api.nansen_research.errors import NansenContractError
from edge_os_api.nansen_research.models import (
    FlowBucket,
    FlowEvidence,
    HolderEvidence,
    HolderRow,
    NansenContext,
    NansenEvidence,
    NansenRequest,
    ObservationWindow,
    SourceRecord,
)
from edge_os_api.nansen_research.nansen_client import NansenFetch
from edge_os_api.nansen_research.serialization import parse_instant, raw_decimal

_HOLDER_FIELDS = ("token_amount", "ownership_percentage", "value_usd")
_FLOW_NUMBER_FIELDS = ("price_usd", "token_amount", "value_usd", "holders_count",
                       "total_inflows_count", "total_outflows_count",
                       "total_inflows_dex", "total_outflows_dex",
                       "total_inflows_cex", "total_outflows_cex")
_HOURLY_LIMIT_DAYS = 7


def _raw(container: Mapping, key: str) -> str | None:
    try:
        return raw_decimal(container.get(key))
    except ValueError as error:
        raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", f"{key} is not a decimal value") from error


def _text(container: Mapping, key: str) -> str | None:
    value = container.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", f"{key} is not text")
    return value


def _bool(container: Mapping, key: str) -> bool | None:
    value = container.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", f"{key} is not a boolean")
    return value


def _rows(fetch: NansenFetch) -> list:
    data = fetch.payload.get("data")
    if not isinstance(data, list):
        raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "response data is not a list")
    for item in data:
        if not isinstance(item, Mapping):
            raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "a response row is not an object")
    return data


def _warnings(fetch: NansenFetch) -> list[str]:
    warnings = fetch.payload.get("warnings")
    if warnings is None:
        return []
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "warnings is not a list of text")
    return list(warnings)


def _is_last_page(fetch: NansenFetch) -> bool | None:
    pagination = fetch.payload.get("pagination")
    if pagination is None:
        return None
    if not isinstance(pagination, Mapping):
        raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "pagination is not an object")
    return _bool(pagination, "is_last_page")


def extract_holder_evidence(fetches: Sequence[NansenFetch]) -> HolderEvidence:
    """Turn holder pages into typed rows, keeping duplicates, nulls and pagination."""
    rows: list[HolderRow] = []
    warnings: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    last_page: bool | None = None
    for fetch in fetches:
        if fetch.operation != "holders":
            raise NansenContractError("WRONG_OPERATION", "a holder page came from another operation")
        for item in _rows(fetch):
            address = _text(item, "address")
            if address is not None:
                if address in seen:
                    duplicates.append(address)
                seen.add(address)
            rows.append(HolderRow(
                address=address,
                token_amount=_raw(item, "token_amount"),
                ownership_percentage=_raw(item, "ownership_percentage"),
                value_usd=_raw(item, "value_usd"),
                address_label=_text(item, "address_label"),
            ))
        warnings.extend(_warnings(fetch))
        page_flag = _is_last_page(fetch)
        if page_flag is not None:
            last_page = page_flag
    return HolderEvidence(
        rows=tuple(rows),
        pagination_is_last_page=last_page,
        pages=len(fetches),
        duplicate_addresses=tuple(sorted(set(duplicates))),
        warnings=tuple(warnings),
    )


def expected_bucket_starts(window: ObservationWindow) -> tuple[str, ...]:
    """The expected bucket starts. Hourly for a span of seven days or less, else daily."""
    start = parse_instant(window.start_utc)
    end = parse_instant(window.end_utc)
    step = timedelta(hours=1) if (end - start) <= timedelta(days=_HOURLY_LIMIT_DAYS) else timedelta(days=1)
    start_aligned = start.replace(minute=0, second=0, microsecond=0)
    if step == timedelta(days=1):
        start_aligned = start_aligned.replace(hour=0)
    end_floor = end.replace(minute=0, second=0, microsecond=0)
    if step == timedelta(days=1):
        end_floor = end_floor.replace(hour=0)
    starts: list[str] = []
    moment = start_aligned
    while moment <= end_floor:
        starts.append(moment.strftime("%Y-%m-%dT%H:%M:%SZ"))
        moment += step
    return tuple(starts)


def extract_flow_evidence(fetches: Sequence[NansenFetch], window: ObservationWindow) -> FlowEvidence:
    """Turn flow pages into typed buckets with explicit coverage and completeness."""
    buckets: list[FlowBucket] = []
    warnings: list[str] = []
    counts: dict[datetime, int] = {}
    for fetch in fetches:
        if fetch.operation != "flows":
            raise NansenContractError("WRONG_OPERATION", "a flow page came from another operation")
        for item in _rows(fetch):
            raw_date = _text(item, "date")
            if raw_date is None:
                raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "a flow bucket has no date")
            try:
                moment = parse_instant(raw_date)
            except ValueError as error:
                raise NansenContractError("MALFORMED_PROVIDER_RESPONSE", "a bucket date is not an instant") from error
            counts[moment] = counts.get(moment, 0) + 1
            buckets.append(FlowBucket(
                date=raw_date,
                bucket_end=_text(item, "bucket_end"),
                is_complete=_bool(item, "is_complete"),
                **{field: _raw(item, field) for field in _FLOW_NUMBER_FIELDS},
            ))
        warnings.extend(_warnings(fetch))

    expected = expected_bucket_starts(window)
    returned = {parse_instant(bucket.date) for bucket in buckets}
    expected_set = {parse_instant(item) for item in expected}
    window_end = parse_instant(window.end_utc)
    missing = [item for item in expected if parse_instant(item) not in returned]

    incomplete: list[str] = []
    intervals: dict[datetime, tuple[datetime, datetime]] = {}
    conflict = False
    for bucket in buckets:
        if bucket.is_complete is False:
            incomplete.append(bucket.date)
            continue
        if bucket.is_complete is None:
            warnings.append("a bucket has unknown completeness; it is not counted as complete")
            continue
        if bucket.bucket_end is None:
            warnings.append("a complete bucket has no bucket_end; its seconds are not counted")
            continue
        try:
            start = parse_instant(bucket.date)
            end = parse_instant(bucket.bucket_end)
        except ValueError as error:
            raise NansenContractError("MALFORMED_PROVIDER_RESPONSE",
                                      "a bucket_end is not an instant") from error
        if start not in expected_set:
            warnings.append("a complete bucket start is outside the expected window; it is not counted")
            continue
        if end > window_end:
            warnings.append("a complete bucket end passes the window; it is not counted")
            continue
        if end <= start:
            conflict = True
            continue
        if start in intervals:
            warnings.append("a duplicate complete start is not counted twice")
            continue
        intervals[start] = (start, end)

    ordered = sorted(intervals.values())
    if any(prev_end > nxt_start for (_, prev_end), (nxt_start, _) in zip(ordered, ordered[1:])):
        conflict = True
    complete_seconds = None if conflict else int(sum((end - start).total_seconds() for start, end in ordered))

    duplicate_starts = [item for item in expected if counts.get(parse_instant(item), 0) > 1]
    extra_duplicates = sorted(
        moment.strftime("%Y-%m-%dT%H:%M:%SZ") for moment, count in counts.items()
        if count > 1 and moment not in expected_set
    )
    return FlowEvidence(
        buckets=tuple(buckets),
        expected_starts=expected,
        missing_starts=tuple(missing),
        duplicate_starts=tuple(duplicate_starts + extra_duplicates),
        incomplete_starts=tuple(incomplete),
        complete_seconds=complete_seconds,
        warnings=tuple(warnings),
    )


def classify_availability(available_at: str | None, checked_at: str, max_age: int) -> str:
    """The D01 availability rule, including the corrected future-time case.

    Returns ``unknown``, ``not_yet_available``, ``within_declared_age`` or ``stale``.
    Both timestamps need an offset. The age limit is a nonnegative integer second.
    """
    if type(max_age) is not int or max_age < 0:
        raise ValueError("the age limit must be a nonnegative integer second count")
    checked = parse_instant(checked_at)
    if available_at is None:
        return "unknown"
    available = parse_instant(available_at)
    age = (checked - available).total_seconds()
    if age < 0:
        return "not_yet_available"
    return "stale" if age > max_age else "within_declared_age"


def _unknowns(request: NansenRequest, holder: HolderEvidence | None,
              flows: FlowEvidence | None) -> tuple[str, ...]:
    """The field meanings this local run cannot qualify, by operation."""
    unknowns = ["total_supply", "balance_scaling"]
    if "holders" in request.operations:
        unknowns += ["ownership_percentage_denominator", "token_amount_units"]
    if "flows" in request.operations:
        unknowns += ["flow_count_meaning", "hourly_price"]
    return tuple(unknowns)


def build_evidence(request: NansenRequest, context: NansenContext, *, sources: Sequence[SourceRecord],
                   attempts: int, pages: int, reserved_credits: Decimal, holder: HolderEvidence | None,
                   flows: FlowEvidence | None, stop_reason: str | None) -> NansenEvidence:
    """Assemble the immutable evidence package from the collected sources."""
    warnings: list[str] = []
    if holder is not None:
        warnings.extend(holder.warnings)
    if flows is not None:
        warnings.extend(flows.warnings)
    if stop_reason is not None:
        warnings.append(f"collection stopped: {stop_reason}")
    return NansenEvidence(
        question=request.question,
        token_address=request.token_address,
        token_symbol=request.token_symbol,
        network=request.network,
        chain_id=request.chain_id,
        window=request.window,
        provider=context.provider,
        provider_version=context.provider_version,
        endpoint=context.endpoint,
        api_schema_version=context.api_schema_version,
        profile_version=request.profile_version,
        conventions_version=request.conventions_version,
        sources=tuple(sources),
        attempts=attempts,
        pages=pages,
        reserved_credits=format(reserved_credits, "f"),
        holder=holder,
        flows=flows,
        stop_reason=stop_reason,
        unknowns=_unknowns(request, holder, flows),
        warnings=tuple(warnings),
    )


def refuse_foreign_echo(request: NansenRequest, payload: Mapping) -> str | None:
    """Refuse a response whose token or network echo contradicts the request.

    The pinned TGM responses carry no such echo today, so this is a defensive
    check. When an echo is present and wrong, the caller records a contract
    failure and keeps no row. Returns a stable code, or ``None`` when the echo is
    absent or matches.
    """
    chain = payload.get("chain")
    if chain is None:
        chain = payload.get("network")
    if isinstance(chain, str) and chain.strip() and chain.strip().lower() != request.network.lower():
        return "WRONG_NETWORK"
    token = payload.get("token_address")
    if token is None:
        token = payload.get("token")
    if isinstance(token, str) and token.strip() and token.strip().lower() != request.token_address.lower():
        return "WRONG_TOKEN"
    return None
