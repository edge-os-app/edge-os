"""Offline restriction checker for the selected Kuru Flow route.

Standard library only. This module evaluates AUTHORED declarations of a
controlled action and the readiness of a restriction profile. It has no
network, signing, wallet, provider or broadcast code path. A local success is
always ``AUTHORED_FAKE_ONLY``; it is never a live or provider approval.

Every mandatory control has an adopted-value comparison. Missing or unknown
required values block the action. The loader raises ``ValueError`` for a
malformed declaration and never coerces a non-string identifier, a non-integer
quantity or a non-boolean expectation.

Public interface:
    evaluate_declared_case(profile, action) -> CaseVerdict
    profile_readiness_reasons(profile) -> tuple[str, ...]
    load_profile(mapping) -> RestrictionProfile
    load_action(mapping) -> ControlledAction

See README.md for the meaning and the evidence classes.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Tuple

NETWORK_MAINNET = "143"
NETWORK_TESTNET = "10143"
SUPPORTED_NETWORKS = frozenset({NETWORK_MAINNET, NETWORK_TESTNET})

RESULT_BLOCKED = "BLOCKED"
RESULT_AUTHORED_FAKE_ONLY = "AUTHORED_FAKE_ONLY"
PROVIDER_EXECUTED = "NOT_RUN"
FIXTURES_SCHEMA = "p21-route-restrictions/1"

MANDATORY_CONTROLS: Tuple[str, ...] = (
    "chain",
    "wallet_signer_binding",
    "entrypoint_method",
    "input_output_assets",
    "raw_input",
    "recipient",
    "minimum_output",
    "fees",
    "approvals",
    "gas_action_capacity",
    "expiry_freshness",
    "opaque_program",
)

R_MISSING_CONTROL = "MISSING_MANDATORY_CONTROL"
R_UNSUPPORTED_CONTROL = "UNSUPPORTED_CONTROL"
R_EVIDENCE_MISSING = "EVIDENCE_MISSING"
R_NETWORK_NOT_ALLOWED = "NETWORK_NOT_ALLOWED"
R_WALLET_BINDING_MISSING = "WALLET_BINDING_MISSING"
R_WALLET_BINDING_MISMATCH = "WALLET_BINDING_MISMATCH"
R_ADOPTED_IDENTITY_INVALID = "ADOPTED_IDENTITY_INVALID"
R_SIGNER_NOT_ALLOWED = "SIGNER_NOT_ALLOWED"
R_ENTRYPOINT_NOT_ALLOWED = "ENTRYPOINT_NOT_ALLOWED"
R_METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
R_ASSET_NOT_ALLOWED = "ASSET_NOT_ALLOWED"
R_RECIPIENT_NOT_ALLOWED = "RECIPIENT_NOT_ALLOWED"
R_RAW_AMOUNT_INVALID = "RAW_AMOUNT_INVALID"
R_BOOLEAN_NOT_INTEGER = "BOOLEAN_NOT_INTEGER"
R_INPUT_NOT_APPROVED = "INPUT_NOT_APPROVED"
R_DECIMALS_MISMATCH = "DECIMALS_MISMATCH"
R_MIN_OUTPUT_MISSING = "MIN_OUTPUT_MISSING"
R_MIN_OUTPUT_INVALID = "MIN_OUTPUT_INVALID"
R_QUOTE_UNKNOWN = "QUOTE_UNKNOWN"
R_FEE_UNKNOWN = "FEE_UNKNOWN"
R_FEE_NOT_APPROVED = "FEE_NOT_APPROVED"
R_FEE_COLLECTOR_NOT_ALLOWED = "FEE_COLLECTOR_NOT_ALLOWED"
R_REFERRER_NOT_ALLOWED = "REFERRER_NOT_ALLOWED"
R_FEE_MODE_UNKNOWN = "FEE_MODE_UNKNOWN"
R_FEE_MODE_NOT_APPROVED = "FEE_MODE_NOT_APPROVED"
R_FEE_BOUND_EXCEEDED = "FEE_BOUND_EXCEEDED"
R_PROGRAM_MISSING = "PROGRAM_MISSING"
R_PROGRAM_NOT_APPROVED = "PROGRAM_NOT_APPROVED"
R_ALLOWANCE_UNKNOWN = "ALLOWANCE_UNKNOWN"
R_ALLOWANCE_NOT_APPROVED = "ALLOWANCE_NOT_APPROVED"
R_CAPACITY_UNKNOWN = "CAPACITY_UNKNOWN"
R_CAPACITY_EXHAUSTED = "CAPACITY_EXHAUSTED"
R_FRESHNESS_UNKNOWN = "FRESHNESS_UNKNOWN"
R_STALE_INPUT = "STALE_INPUT"
R_INPUT_FRESHNESS_UNKNOWN = "INPUT_FRESHNESS_UNKNOWN"
R_STALE_INPUT_AGE = "STALE_INPUT_AGE"
R_EXPIRY_UNKNOWN = "EXPIRY_UNKNOWN"
R_INTENT_EXPIRED = "INTENT_EXPIRED"
R_MANDATE_EXPIRED = "MANDATE_EXPIRED"
R_EVIDENCE_UNMATCHED = "EVIDENCE_UNMATCHED"

_CANONICAL_RAW = re.compile(r"(?:0|[1-9][0-9]*)")
_HEX_BYTES = re.compile(r"(?:0x)?(?:[0-9a-fA-F]{2})+")


class EvidenceClass(str, Enum):
    """Provenance of one enforcement claim. Distinct classes are preserved."""

    DOCUMENTED = "DOCUMENTED"
    SOURCE_INSPECTED = "SOURCE_INSPECTED"
    LOCAL_TESTED = "LOCAL_TESTED"
    PROVIDER_ACTUAL = "PROVIDER_ACTUAL"
    NOT_RUN = "NOT_RUN"


class EnforcementLayer(str, Enum):
    """The layer that would enforce a mandatory control."""

    HOST = "HOST"
    CONTRACT = "CONTRACT"
    INDEPENDENT_POLICY = "INDEPENDENT_POLICY"


class SupportState(str, Enum):
    """Whether the declared enforcement exists for the selected route."""

    ENFORCED = "ENFORCED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    UNSET = "UNSET"


@dataclass(frozen=True)
class ControlDeclaration:
    """One mandatory control's declared enforcement."""

    state: SupportState
    layer: EnforcementLayer
    evidence: EvidenceClass
    note: str = ""


@dataclass(frozen=True)
class RestrictionProfile:
    """A declared restriction profile for the selected route."""

    version: str
    declarations: Mapping[str, ControlDeclaration]


@dataclass(frozen=True)
class ControlledAction:
    """One declared controlled action plus its authored approval bounds.

    Any field left as ``None`` is UNKNOWN. An unknown required value is never
    treated as zero or as an approved value.
    """

    action_id: str
    network: str
    entrypoint_address: str
    method: str
    wallet_id: str
    signer_id: str
    policy_binding_wallet_id: str
    input_asset_id: str
    input_raw: Optional[str]
    input_decimals: int
    output_asset_id: str
    output_decimals: int
    recipient: str
    min_output_raw: Optional[str]
    quote_output_raw: Optional[str]
    fee_bps: Optional[int]
    referrer_fee_bps: Optional[int]
    fee_collector_address: str
    referrer_address: str
    is_in_token_fee: Optional[bool]
    program_hex: Optional[str]
    allowance_raw: Optional[str]
    gas_capacity_raw: Optional[str]
    gas_used_raw: Optional[str]
    action_capacity: Optional[int]
    actions_used: Optional[int]
    quote_age_seconds: Optional[int]
    max_quote_age_seconds: Optional[int]
    input_age_seconds: Optional[int]
    max_input_age_seconds: Optional[int]
    intent_expires_at_seconds: Optional[int]
    mandate_expires_at_seconds: Optional[int]
    now_seconds: Optional[int]
    approved_networks: frozenset[str]
    approved_entrypoints: frozenset[str]
    approved_signers: frozenset[str]
    approved_assets: Mapping[str, int]
    approved_methods: frozenset[str]
    approved_recipients: frozenset[str]
    approved_input_raw: Optional[str]
    approved_program_hex: frozenset[str]
    approved_fee_bps: Optional[int]
    approved_referrer_fee_bps: Optional[int]
    approved_fee_collectors: frozenset[str]
    approved_referrers: frozenset[str]
    approved_is_in_token_fee: Optional[bool]
    approved_allowance_raw: Optional[str]
    claimed_result_class: str


@dataclass(frozen=True)
class CaseVerdict:
    """The result of evaluating one declared action offline."""

    action_id: str
    accepted: bool
    result_class: str
    reasons: Tuple[str, ...]


def _reject_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _validate_raw(raw: Any) -> Optional[str]:
    """Return a rejection code when raw is not a complete canonical amount."""
    if _reject_bool(raw):
        return R_BOOLEAN_NOT_INTEGER
    if not isinstance(raw, str):
        return R_RAW_AMOUNT_INVALID
    if _CANONICAL_RAW.fullmatch(raw) is None:
        return R_RAW_AMOUNT_INVALID
    return None


def _is_hex_program(value: Any) -> bool:
    return isinstance(value, str) and _HEX_BYTES.fullmatch(value) is not None


def _has_empty_entry(approved: frozenset[str]) -> bool:
    """True when an adopted identity set contains an empty or whitespace entry."""
    return any(not entry.strip() for entry in approved)


def _identity_reasons(
    actual: str, approved: frozenset[str], not_allowed: str, applicable: bool = True
) -> list[str]:
    """Block an absent/empty actual identity, an invalid adopted entry, or a mismatch.

    The check is independent of membership: an empty actual value blocks even
    when the adopted set also contains an empty placeholder.
    """
    if not applicable:
        return []
    reasons: list[str] = []
    if not actual.strip():
        reasons.append(not_allowed)
    if _has_empty_entry(approved):
        reasons.append(R_ADOPTED_IDENTITY_INVALID)
    elif actual not in approved:
        reasons.append(not_allowed)
    return reasons


def _asset_reasons(actual: str, decimals: int, approved: Mapping[str, int]) -> list[str]:
    """Block an absent/empty asset, an invalid adopted asset key, or a mismatch."""
    reasons: list[str] = []
    if not actual.strip():
        reasons.append(R_ASSET_NOT_ALLOWED)
    if any(not key.strip() for key in approved):
        reasons.append(R_ADOPTED_IDENTITY_INVALID)
    elif actual not in approved:
        reasons.append(R_ASSET_NOT_ALLOWED)
    elif approved[actual] != decimals:
        reasons.append(R_DECIMALS_MISMATCH)
    return reasons


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _require_nonempty_str(value: Any, field: str) -> str:
    text = _require_str(value, field)
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


def _strict_nonneg_int(value: Any, field: str) -> int:
    if _reject_bool(value) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must not be negative")
    return value


def _strict_optional_nonneg_int(value: Any, field: str) -> Optional[int]:
    if value is None:
        return None
    return _strict_nonneg_int(value, field)


def _strict_optional_bool(value: Any, field: str) -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def profile_readiness_reasons(profile: RestrictionProfile) -> Tuple[str, ...]:
    """Return reasons the declared profile cannot back a real action.

    Empty tuple means every mandatory control is declared ENFORCED with a
    concrete enforcement layer and some evidence above ``NOT_RUN``. It does not
    mean the action is safe.
    """
    reasons: list[str] = []
    for control in MANDATORY_CONTROLS:
        declaration = profile.declarations.get(control)
        if declaration is None:
            reasons.append(f"{R_MISSING_CONTROL}:{control}")
            continue
        if declaration.state is not SupportState.ENFORCED:
            reasons.append(f"{R_UNSUPPORTED_CONTROL}:{control}")
            continue
        if declaration.evidence is EvidenceClass.NOT_RUN:
            reasons.append(f"{R_EVIDENCE_MISSING}:{control}")
    return tuple(reasons)


def _approved_raw_reasons(actual: Optional[str], approved: Optional[str]) -> list[str]:
    if approved is None:
        return [R_INPUT_NOT_APPROVED]
    approved_reason = _validate_raw(approved)
    if approved_reason is not None:
        return [approved_reason]
    if actual is None:
        return [R_INPUT_NOT_APPROVED]
    if actual != approved:
        return [R_INPUT_NOT_APPROVED]
    return []


def _fee_reasons(action: ControlledAction) -> list[str]:
    if (
        action.fee_bps is None
        or action.referrer_fee_bps is None
        or action.approved_fee_bps is None
        or action.approved_referrer_fee_bps is None
    ):
        return [R_FEE_UNKNOWN]

    reasons: list[str] = []
    total = action.fee_bps + action.referrer_fee_bps
    if total > 10000:
        reasons.append(R_FEE_BOUND_EXCEEDED)
    if action.fee_bps != action.approved_fee_bps or action.referrer_fee_bps != action.approved_referrer_fee_bps:
        reasons.append(R_FEE_NOT_APPROVED)

    if action.fee_bps > 0:
        reasons.extend(
            _identity_reasons(action.fee_collector_address, action.approved_fee_collectors, R_FEE_COLLECTOR_NOT_ALLOWED)
        )
    if action.referrer_fee_bps > 0:
        reasons.extend(
            _identity_reasons(action.referrer_address, action.approved_referrers, R_REFERRER_NOT_ALLOWED)
        )

    if total > 0:
        if action.is_in_token_fee is None or action.approved_is_in_token_fee is None:
            reasons.append(R_FEE_MODE_UNKNOWN)
        elif action.is_in_token_fee != action.approved_is_in_token_fee:
            reasons.append(R_FEE_MODE_NOT_APPROVED)
    return reasons


def _allowance_reasons(action: ControlledAction) -> list[str]:
    if action.allowance_raw is None or action.approved_allowance_raw is None:
        return [R_ALLOWANCE_UNKNOWN]
    actual_reason = _validate_raw(action.allowance_raw)
    if actual_reason is not None:
        return [actual_reason]
    approved_reason = _validate_raw(action.approved_allowance_raw)
    if approved_reason is not None:
        return [approved_reason]
    if action.allowance_raw != action.approved_allowance_raw:
        return [R_ALLOWANCE_NOT_APPROVED]
    return []


def _capacity_reasons(action: ControlledAction) -> list[str]:
    reasons: list[str] = []
    if action.gas_capacity_raw is None or action.gas_used_raw is None:
        reasons.append(R_CAPACITY_UNKNOWN)
    else:
        gas_cap_reason = _validate_raw(action.gas_capacity_raw)
        gas_used_reason = _validate_raw(action.gas_used_raw)
        if gas_cap_reason is not None:
            reasons.append(gas_cap_reason)
        elif gas_used_reason is not None:
            reasons.append(gas_used_reason)
        elif int(action.gas_used_raw) > int(action.gas_capacity_raw):
            reasons.append(R_CAPACITY_EXHAUSTED)

    if action.action_capacity is None or action.actions_used is None:
        reasons.append(R_CAPACITY_UNKNOWN)
    elif action.actions_used >= action.action_capacity:
        reasons.append(R_CAPACITY_EXHAUSTED)
    return reasons


def _freshness_reasons(action: ControlledAction) -> list[str]:
    reasons: list[str] = []
    if action.quote_age_seconds is None or action.max_quote_age_seconds is None:
        reasons.append(R_FRESHNESS_UNKNOWN)
    elif action.quote_age_seconds > action.max_quote_age_seconds:
        reasons.append(R_STALE_INPUT)
    if action.input_age_seconds is None or action.max_input_age_seconds is None:
        reasons.append(R_INPUT_FRESHNESS_UNKNOWN)
    elif action.input_age_seconds > action.max_input_age_seconds:
        reasons.append(R_STALE_INPUT_AGE)
    return reasons


def _expiry_reasons(action: ControlledAction) -> list[str]:
    if (
        action.now_seconds is None
        or action.intent_expires_at_seconds is None
        or action.mandate_expires_at_seconds is None
    ):
        return [R_EXPIRY_UNKNOWN]
    reasons: list[str] = []
    if action.now_seconds >= action.intent_expires_at_seconds:
        reasons.append(R_INTENT_EXPIRED)
    if action.now_seconds >= action.mandate_expires_at_seconds:
        reasons.append(R_MANDATE_EXPIRED)
    return reasons


def _evaluate_action(action: ControlledAction) -> list[str]:
    reasons: list[str] = []

    if action.network not in SUPPORTED_NETWORKS:
        reasons.append(R_NETWORK_NOT_ALLOWED)
    reasons.extend(_identity_reasons(action.network, action.approved_networks, R_NETWORK_NOT_ALLOWED))

    if not action.wallet_id or not action.signer_id or not action.policy_binding_wallet_id:
        reasons.append(R_WALLET_BINDING_MISSING)
    elif action.policy_binding_wallet_id != action.wallet_id:
        reasons.append(R_WALLET_BINDING_MISMATCH)
    reasons.extend(_identity_reasons(action.signer_id, action.approved_signers, R_SIGNER_NOT_ALLOWED))

    reasons.extend(
        _identity_reasons(action.entrypoint_address, action.approved_entrypoints, R_ENTRYPOINT_NOT_ALLOWED)
    )
    reasons.extend(_identity_reasons(action.method, action.approved_methods, R_METHOD_NOT_ALLOWED))

    reasons.extend(_asset_reasons(action.input_asset_id, action.input_decimals, action.approved_assets))
    reasons.extend(_asset_reasons(action.output_asset_id, action.output_decimals, action.approved_assets))

    raw_reason = _validate_raw(action.input_raw)
    if raw_reason is not None:
        reasons.append(raw_reason)
    reasons.extend(_approved_raw_reasons(action.input_raw, action.approved_input_raw))

    reasons.extend(_identity_reasons(action.recipient, action.approved_recipients, R_RECIPIENT_NOT_ALLOWED))

    reasons.extend(_min_output_reasons(action))
    reasons.extend(_fee_reasons(action))

    if not _is_hex_program(action.program_hex):
        reasons.append(R_PROGRAM_MISSING)
    elif _has_empty_entry(action.approved_program_hex):
        reasons.append(R_ADOPTED_IDENTITY_INVALID)
    elif action.program_hex not in action.approved_program_hex:
        reasons.append(R_PROGRAM_NOT_APPROVED)

    reasons.extend(_allowance_reasons(action))
    reasons.extend(_capacity_reasons(action))
    reasons.extend(_freshness_reasons(action))
    reasons.extend(_expiry_reasons(action))

    if action.claimed_result_class != RESULT_AUTHORED_FAKE_ONLY:
        reasons.append(R_EVIDENCE_UNMATCHED)

    return reasons


def _min_output_reasons(action: ControlledAction) -> list[str]:
    if action.min_output_raw is None:
        return [R_MIN_OUTPUT_MISSING]
    min_reason = _validate_raw(action.min_output_raw)
    if min_reason is not None:
        return [min_reason]
    if action.quote_output_raw is None:
        return [R_QUOTE_UNKNOWN]
    quote_reason = _validate_raw(action.quote_output_raw)
    if quote_reason is not None:
        return [quote_reason]
    if int(action.min_output_raw) > int(action.quote_output_raw):
        return [R_MIN_OUTPUT_INVALID]
    return []


def evaluate_declared_case(profile: RestrictionProfile, action: ControlledAction) -> CaseVerdict:
    """Evaluate one declared action offline against a declared profile.

    Returns an accepted ``AUTHORED_FAKE_ONLY`` verdict only when the profile is
    ready and every declared action check passes. Any missing, unknown or
    unsupported mandatory control blocks the action. Local success is never a
    provider or live approval.
    """
    reasons = list(profile_readiness_reasons(profile))
    reasons.extend(_evaluate_action(action))
    seen: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.append(reason)
    accepted = not seen
    result_class = RESULT_AUTHORED_FAKE_ONLY if accepted else RESULT_BLOCKED
    return CaseVerdict(action.action_id, accepted, result_class, tuple(seen))


def _enum(enum_type: type[Enum], value: Any) -> Any:
    if _reject_bool(value) or not isinstance(value, str):
        raise ValueError(f"invalid enum value for {enum_type.__name__}: {value!r}")
    return enum_type(value)


def load_profile(mapping: Mapping[str, Any]) -> RestrictionProfile:
    """Build a RestrictionProfile from a JSON-like mapping."""
    declarations: dict[str, ControlDeclaration] = {}
    raw_declarations = mapping.get("declarations", {})
    if not isinstance(raw_declarations, Mapping):
        raise ValueError("profile.declarations must be an object")
    for control, raw in raw_declarations.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"declaration for {control!r} must be an object")
        declarations[str(control)] = ControlDeclaration(
            state=_enum(SupportState, raw.get("state")),
            layer=_enum(EnforcementLayer, raw.get("layer")),
            evidence=_enum(EvidenceClass, raw.get("evidence")),
            note=str(raw.get("note", "")),
        )
    return RestrictionProfile(
        version=_require_nonempty_str(mapping.get("version"), "version"),
        declarations=declarations,
    )


def _string_set(value: Any, field: str) -> frozenset[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list")
    return frozenset(_require_str(item, f"{field}[]") for item in value)


def _asset_decimals(value: Any, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return {_require_str(k, f"{field}.key"): _strict_nonneg_int(v, f"{field}.{k}") for k, v in value.items()}


def load_action(mapping: Mapping[str, Any]) -> ControlledAction:
    """Build a ControlledAction from a JSON-like mapping.

    Raises ``ValueError`` for a malformed declaration. It never coerces a
    non-string identifier, a non-integer quantity or a non-boolean value.
    """
    return ControlledAction(
        action_id=_require_nonempty_str(mapping.get("action_id"), "action_id"),
        network=_require_str(mapping.get("network"), "network"),
        entrypoint_address=_require_str(mapping.get("entrypoint_address", ""), "entrypoint_address"),
        method=_require_str(mapping.get("method", ""), "method"),
        wallet_id=_require_str(mapping.get("wallet_id", ""), "wallet_id"),
        signer_id=_require_str(mapping.get("signer_id", ""), "signer_id"),
        policy_binding_wallet_id=_require_str(
            mapping.get("policy_binding_wallet_id", ""), "policy_binding_wallet_id"
        ),
        input_asset_id=_require_str(mapping.get("input_asset_id", ""), "input_asset_id"),
        input_raw=mapping.get("input_raw"),
        input_decimals=_strict_nonneg_int(mapping.get("input_decimals", 0), "input_decimals"),
        output_asset_id=_require_str(mapping.get("output_asset_id", ""), "output_asset_id"),
        output_decimals=_strict_nonneg_int(mapping.get("output_decimals", 0), "output_decimals"),
        recipient=_require_str(mapping.get("recipient", ""), "recipient"),
        min_output_raw=mapping.get("min_output_raw"),
        quote_output_raw=mapping.get("quote_output_raw"),
        fee_bps=_strict_optional_nonneg_int(mapping.get("fee_bps"), "fee_bps"),
        referrer_fee_bps=_strict_optional_nonneg_int(mapping.get("referrer_fee_bps"), "referrer_fee_bps"),
        fee_collector_address=_require_str(mapping.get("fee_collector_address", ""), "fee_collector_address"),
        referrer_address=_require_str(mapping.get("referrer_address", ""), "referrer_address"),
        is_in_token_fee=_strict_optional_bool(mapping.get("is_in_token_fee"), "is_in_token_fee"),
        program_hex=mapping.get("program_hex"),
        allowance_raw=mapping.get("allowance_raw"),
        gas_capacity_raw=mapping.get("gas_capacity_raw"),
        gas_used_raw=mapping.get("gas_used_raw"),
        action_capacity=_strict_optional_nonneg_int(mapping.get("action_capacity"), "action_capacity"),
        actions_used=_strict_optional_nonneg_int(mapping.get("actions_used"), "actions_used"),
        quote_age_seconds=_strict_optional_nonneg_int(mapping.get("quote_age_seconds"), "quote_age_seconds"),
        max_quote_age_seconds=_strict_optional_nonneg_int(
            mapping.get("max_quote_age_seconds"), "max_quote_age_seconds"
        ),
        input_age_seconds=_strict_optional_nonneg_int(mapping.get("input_age_seconds"), "input_age_seconds"),
        max_input_age_seconds=_strict_optional_nonneg_int(
            mapping.get("max_input_age_seconds"), "max_input_age_seconds"
        ),
        intent_expires_at_seconds=_strict_optional_nonneg_int(
            mapping.get("intent_expires_at_seconds"), "intent_expires_at_seconds"
        ),
        mandate_expires_at_seconds=_strict_optional_nonneg_int(
            mapping.get("mandate_expires_at_seconds"), "mandate_expires_at_seconds"
        ),
        now_seconds=_strict_optional_nonneg_int(mapping.get("now_seconds"), "now_seconds"),
        approved_networks=_string_set(mapping.get("approved_networks", []), "approved_networks"),
        approved_entrypoints=_string_set(mapping.get("approved_entrypoints", []), "approved_entrypoints"),
        approved_signers=_string_set(mapping.get("approved_signers", []), "approved_signers"),
        approved_assets=_asset_decimals(mapping.get("approved_assets", {}), "approved_assets"),
        approved_methods=_string_set(mapping.get("approved_methods", []), "approved_methods"),
        approved_recipients=_string_set(mapping.get("approved_recipients", []), "approved_recipients"),
        approved_input_raw=mapping.get("approved_input_raw"),
        approved_program_hex=_string_set(mapping.get("approved_program_hex", []), "approved_program_hex"),
        approved_fee_bps=_strict_optional_nonneg_int(mapping.get("approved_fee_bps"), "approved_fee_bps"),
        approved_referrer_fee_bps=_strict_optional_nonneg_int(
            mapping.get("approved_referrer_fee_bps"), "approved_referrer_fee_bps"
        ),
        approved_fee_collectors=_string_set(
            mapping.get("approved_fee_collectors", []), "approved_fee_collectors"
        ),
        approved_referrers=_string_set(mapping.get("approved_referrers", []), "approved_referrers"),
        approved_is_in_token_fee=_strict_optional_bool(
            mapping.get("approved_is_in_token_fee"), "approved_is_in_token_fee"
        ),
        approved_allowance_raw=mapping.get("approved_allowance_raw"),
        claimed_result_class=_require_str(mapping.get("claimed_result_class", RESULT_BLOCKED), "claimed_result_class"),
    )


def _load_fixtures(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _expected_accepted(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("fixture expect.accepted must be a boolean")
    return value


def _run_fixtures(path: Path) -> int:
    data = _load_fixtures(path)
    if data.get("schema") != FIXTURES_SCHEMA:
        raise ValueError(f"unsupported fixtures schema: {data.get('schema')!r}")
    failures = 0
    total = 0
    for scenario in data["scenarios"]:
        profile = load_profile(scenario["profile"])
        base = scenario.get("base_action", {})
        for case in scenario["cases"]:
            merged = dict(base)
            merged.update(case.get("override", {}))
            merged["action_id"] = case["name"]
            verdict = evaluate_declared_case(profile, load_action(merged))
            expect = case["expect"]
            expected_accepted = _expected_accepted(expect["accepted"])
            ok = verdict.accepted == expected_accepted
            if ok and not expected_accepted:
                wanted = expect.get("reason")
                ok = wanted is None or any(r.startswith(wanted) for r in verdict.reasons)
            status = "PASS" if ok else "FAIL"
            total += 1
            if not ok:
                failures += 1
            print(f"{status} {verdict.action_id} {verdict.result_class} {list(verdict.reasons)}")
    print(f"provider_executed: {PROVIDER_EXECUTED}")
    print(f"cases: {total} failures: {failures}")
    return 1 if failures else 0


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    path = Path(args[1]) if len(args) > 1 else Path(__file__).with_name("fixtures.json")
    try:
        return _run_fixtures(path)
    except ValueError as error:
        print(f"error: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
