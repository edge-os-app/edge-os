"""Authored sanitized fixtures for the Nansen research tests.

Every token, address and number here is synthetic. No provider response, account
identifier or credential is included. The helpers build the same JSON shapes the
pinned OpenAPI schema describes so the tests exercise the real seams offline.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping, Sequence

from edge_os_api.nansen_research import (
    NansenLimits,
    NansenRequest,
    NansenResponse,
    ObservationWindow,
)

WINDOW_START = "2026-10-06T09:44:14Z"
WINDOW_END = "2026-10-07T09:44:14Z"
TOKEN = "0xd8e004acba279417c04c0633cb5a21ceca207777"
SYMBOL = "MOE"
COLLECTED_AT = "2026-10-07T09:50:00Z"
QUESTION = "How concentrated are MOE current holdings, and what do qualified basic flow records show?"


def limits(**overrides: Any) -> NansenLimits:
    base: dict[str, Any] = {
        "max_requests": 6,
        "max_pages": 4,
        "max_bytes": 200_000,
        "max_credits": Decimal("25"),
        "per_page": 100,
    }
    base.update(overrides)
    return NansenLimits(**base)


def window(start: str = WINDOW_START, end: str = WINDOW_END) -> ObservationWindow:
    return ObservationWindow(start_utc=start, end_utc=end)


def request(**overrides: Any) -> NansenRequest:
    base: dict[str, Any] = {
        "question": QUESTION,
        "token_address": TOKEN,
        "token_symbol": SYMBOL,
        "window": window(),
        "operations": ("holders", "flows"),
        "limits": limits(),
    }
    base.update(overrides)
    return NansenRequest(**base)


def response(status: int = 200, payload: Any = None, headers: Mapping[str, str] | None = None) -> NansenResponse:
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return NansenResponse(status=status, headers=dict(headers or {}), body=body)


def raw_response(status: int = 200, body: bytes = b"", headers: Mapping[str, str] | None = None) -> NansenResponse:
    return NansenResponse(status=status, headers=dict(headers or {}), body=body)


def holder_row(address: str, *, token_amount: Any = 1000, ownership_percentage: Any = 0.5,
               value_usd: Any = None, address_label: Any = None) -> dict[str, Any]:
    return {
        "address": address,
        "token_amount": token_amount,
        "ownership_percentage": ownership_percentage,
        "value_usd": value_usd,
        "address_label": address_label,
    }


def holder_payload(rows: Sequence[Mapping[str, Any]], *, is_last_page: bool = True,
                   warnings: Sequence[str] | None = None, page: int = 1) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "data": list(rows),
        "pagination": {"page": page, "per_page": 100, "is_last_page": is_last_page},
    }
    if warnings is not None:
        payload["warnings"] = list(warnings)
    return payload


def flow_bucket(date: str, *, bucket_end: str | None = None, is_complete: bool | None = True,
                price_usd: Any = 0.01, token_amount: Any = 5.0, value_usd: Any = 0.05,
                holders_count: Any = 100, total_inflows_count: Any = 1.5,
                total_outflows_count: Any = -2, total_inflows_dex: Any = None,
                total_outflows_dex: Any = None, total_inflows_cex: Any = None,
                total_outflows_cex: Any = None) -> dict[str, Any]:
    return {
        "date": date,
        "bucket_end": bucket_end,
        "is_complete": is_complete,
        "price_usd": price_usd,
        "token_amount": token_amount,
        "value_usd": value_usd,
        "holders_count": holders_count,
        "total_inflows_count": total_inflows_count,
        "total_outflows_count": total_outflows_count,
        "total_inflows_dex": total_inflows_dex,
        "total_outflows_dex": total_outflows_dex,
        "total_inflows_cex": total_inflows_cex,
        "total_outflows_cex": total_outflows_cex,
    }


def flow_payload(buckets: Sequence[Mapping[str, Any]], *, is_last_page: bool = True,
                 warnings: Sequence[str] | None = None, page: int = 1) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "data": list(buckets),
        "pagination": {"page": page, "per_page": 100, "is_last_page": is_last_page},
    }
    if warnings is not None:
        payload["warnings"] = list(warnings)
    return payload


def hourly_starts(count: int, start_hour: int = 9, start_day: int = 6) -> list[str]:
    from datetime import datetime, timedelta, timezone

    moment = datetime(2026, 10, start_day, start_hour, tzinfo=timezone.utc)
    return [(moment + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M:%SZ") for index in range(count)]


def holder_body(*, page: int = 1, per_page: int = 100, value_usd_min: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "chain": "monad",
        "token_address": TOKEN,
        "aggregate_by_entity": False,
        "label_type": "all_holders",
        "pagination": {"page": page, "per_page": per_page},
        "order_by": [{"field": "token_amount", "direction": "DESC"}],
    }
    if value_usd_min is not None:
        body["filters"] = {"value_usd": {"min": value_usd_min}}
    return body


def flow_body(*, page: int = 1, per_page: int = 100) -> dict[str, Any]:
    return {
        "chain": "monad",
        "token_address": TOKEN,
        "date": {"from": WINDOW_START, "to": WINDOW_END},
        "label": "top_100_holders",
        "pagination": {"page": page, "per_page": per_page},
        "order_by": [{"field": "date", "direction": "ASC"}],
    }


class RecordingTransport:
    """An authored transport. It records calls, serves scripted items and never retries."""

    def __init__(self, script: Sequence[NansenResponse | BaseException]) -> None:
        self._script = list(script)
        self.calls: list[tuple[str, str, Mapping[str, Any]]] = []

    def request(self, operation: str, path: str, body: Mapping[str, Any]) -> NansenResponse:
        self.calls.append((operation, path, dict(body)))
        item = self._script.pop(0) if self._script else NansenResponse(
            status=200, headers={}, body=b'{"data": [], "pagination": {"is_last_page": true}}')
        if isinstance(item, BaseException):
            raise item
        return item


def run(req: NansenRequest, script: Sequence[NansenResponse | BaseException],
        *, clock=lambda: COLLECTED_AT):
    """Run a request against a recorded transport with a fixed clock."""
    from edge_os_api.nansen_research import RecordedNansenTransport, run_research

    return run_research(req, RecordedNansenTransport(script), clock=clock)
