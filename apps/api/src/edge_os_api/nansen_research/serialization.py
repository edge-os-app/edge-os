"""Deterministic serialization and raw provider-value handling.

The package keeps provider numbers as their exact decimal text. Canonical bytes
are UTF-8 JSON with sorted keys and no ASCII escaping, so the same value always
hashes the same. A JSON float is refused; the accepted P02 rule allows canonical
decimal strings, not floats.

This module also holds a small typed (de)serializer for the frozen dataclasses so
every request, evidence package and report can round-trip through JSON.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints


def _check_canonical(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("a JSON float is not canonical; use a decimal string")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be text")
            _check_canonical(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _check_canonical(item)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"value is not canonical JSON data: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    _check_canonical(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=_json_default).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_provider_json(body: bytes) -> Any:
    """Parse provider JSON and keep every number's exact literal text.

    ``parse_float=str`` keeps the decimal text. Integer literals stay ``int``
    because they are exact. The caller must refuse a non-object result.
    """
    return json.loads(body.decode("utf-8"), parse_float=str)


def raw_decimal(value: Any) -> str | None:
    """The provider's exact decimal text, or ``None`` when the value is null.

    A JSON null stays ``None``. An integer becomes its decimal text. A kept float
    literal is validated but stored unchanged. A nonfinite value (``NaN``, a
    signaling NaN, a positive or negative infinity, or their quoted form) is
    refused so it never becomes a false finite amount. Any other type is refused
    so the caller can branch instead of coercing.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("a boolean is not a decimal value")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("an empty string is not a decimal value")
        try:
            parsed = Decimal(text)
        except InvalidOperation as error:
            raise ValueError(f"not a decimal value: {text!r}") from error
        if not parsed.is_finite():
            raise ValueError(f"not a finite decimal value: {text!r}")
        return text
    raise ValueError(f"a {type(value).__name__} is not a decimal value")


def parse_instant(text: str) -> datetime:
    """Parse an aware ISO-8601 instant. A missing offset is refused."""
    if not isinstance(text, str) or not text:
        raise ValueError("an instant must be non-empty text")
    parsed = datetime.fromisoformat(text)
    if parsed.utcoffset() is None:
        raise ValueError("an instant requires an offset")
    return parsed


def format_instant(moment: datetime) -> str:
    """Format an aware instant as UTC ``YYYY-MM-DDTHH:MM:SSZ``."""
    if moment.utcoffset() is None:
        raise ValueError("an instant requires an offset")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    """The current UTC instant in the pinned text format."""
    return format_instant(datetime.now(timezone.utc))


# --- typed (de)serialization for the frozen dataclasses -----------------------

def to_plain(value: Any) -> Any:
    """A JSON-ready view of a frozen dataclass tree. Decimal becomes text."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [to_plain(item) for item in value]
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain(item) for key, item in value.items()}
    return value


def _coerce(declared: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(declared)
    if origin is Union or origin is UnionType:
        inner = [arg for arg in get_args(declared) if arg is not type(None)]
        if len(inner) != 1:
            raise TypeError(f"unsupported union: {declared!r}")
        return _coerce(inner[0], value)
    if origin is tuple:
        (item_type, _ellipsis) = get_args(declared)
        return tuple(_coerce(item_type, item) for item in value)
    if origin is dict:
        (_key_type, item_type) = get_args(declared)
        return {key: _coerce(item_type, item) for key, item in value.items()}
    if is_dataclass(declared):
        return from_plain(declared, value)
    if declared is Decimal:
        return Decimal(value)
    return value


def from_plain(declared: Any, value: Any) -> Any:
    """Rebuild a frozen dataclass tree from a plain JSON object."""
    if not is_dataclass(declared):
        raise TypeError(f"not a dataclass: {declared!r}")
    names = {field.name for field in fields(declared)}
    extra = set(value) - names
    if extra:
        raise ValueError(f"unexpected fields for {declared.__name__}: {sorted(extra)}")
    hints = get_type_hints(declared)
    kwargs: dict[str, Any] = {}
    for field in fields(declared):
        if field.name not in value:
            raise ValueError(f"missing field {field.name!r} for {declared.__name__}")
        kwargs[field.name] = _coerce(hints[field.name], value[field.name])
    return declared(**kwargs)
