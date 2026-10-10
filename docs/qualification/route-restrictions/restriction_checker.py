"""Offline restriction checker for the selected Kuru Flow route.

Standard library only. This module evaluates AUTHORED declarations of a
controlled action and the readiness of a restriction profile. It has no
network, signing, wallet, provider or broadcast code path. A local success is
always ``AUTHORED_FAKE_ONLY``; it is never a live or provider approval.

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
R_NETWORK_NOT_ALLOWED = "NETWORK_NOT_ALLOWED"
R_WALLET_BINDING_MISSING = "WALLET_BINDING_MISSING"
R_WALLET_BINDING_MISMATCH = "WALLET_BINDING_MISMATCH"
R_METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
R_ASSET_NOT_ALLOWED = "ASSET_NOT_ALLOWED"
R_RECIPIENT_NOT_ALLOWED = "RECIPIENT_NOT_ALLOWED"
R_RAW_AMOUNT_INVALID = "RAW_AMOUNT_INVALID"
R_BOOLEAN_NOT_INTEGER = "BOOLEAN_NOT_INTEGER"
R_DECIMALS_MISMATCH = "DECIMALS_MISMATCH"
R_MIN_OUTPUT_MISSING = "MIN_OUTPUT_MISSING"
R_MIN_OUTPUT_INVALID = "MIN_OUTPUT_INVALID"
R_FEE_BOUND_EXCEEDED = "FEE_BOUND_EXCEEDED"
R_PROGRAM_MISSING = "PROGRAM_MISSING"
R_CAPACITY_UNKNOWN = "CAPACITY_UNKNOWN"
R_CAPACITY_EXHAUSTED = "CAPACITY_EXHAUSTED"
R_STALE_INPUT = "STALE_INPUT"
R_EVIDENCE_UNMATCHED = "EVIDENCE_UNMATCHED"

_CANONICAL_RAW = re.compile(r"^(0|[1-9][0-9]*)$")
_HEX_BYTES = re.compile(r"^(0x)?([0-9a-fA-F]{2})*$")


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

    Any field left as ``None`` is UNKNOWN. An unknown required quantity is
    never treated as zero.
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
    fee_bps: int
    referrer_fee_bps: int
    program_hex: Optional[str]
    gas_capacity_raw: Optional[str]
    gas_used_raw: Optional[str]
    action_capacity: int
    actions_used: int
    quote_age_seconds: int
    max_quote_age_seconds: int
    approved_networks: frozenset[str]
    approved_assets: Mapping[str, int]
    approved_methods: frozenset[str]
    approved_recipients: frozenset[str]
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
    """Return a rejection code when raw is not a canonical amount, else None."""
    if _reject_bool(raw):
        return R_BOOLEAN_NOT_INTEGER
    if not isinstance(raw, str):
        return R_RAW_AMOUNT_INVALID
    if not _CANONICAL_RAW.match(raw):
        return R_RAW_AMOUNT_INVALID
    return None


def profile_readiness_reasons(profile: RestrictionProfile) -> Tuple[str, ...]:
    """Return reasons the declared profile cannot back a real action.

    Empty tuple means every mandatory control is declared with ENFORCED state
    and a concrete enforcement layer. It does not mean the action is safe.
    """
    reasons: list[str] = []
    if not profile.version:
        reasons.append(f"{R_MISSING_CONTROL}:version")
    for control in MANDATORY_CONTROLS:
        declaration = profile.declarations.get(control)
        if declaration is None:
            reasons.append(f"{R_MISSING_CONTROL}:{control}")
            continue
        if declaration.state is not SupportState.ENFORCED:
            reasons.append(f"{R_UNSUPPORTED_CONTROL}:{control}")
    return tuple(reasons)


def _evaluate_action(action: ControlledAction) -> list[str]:
    reasons: list[str] = []

    if _reject_bool(action.network) or action.network not in SUPPORTED_NETWORKS:
        reasons.append(R_NETWORK_NOT_ALLOWED)
    if action.network not in action.approved_networks:
        reasons.append(R_NETWORK_NOT_ALLOWED)

    if not action.wallet_id or not action.signer_id:
        reasons.append(R_WALLET_BINDING_MISSING)
    elif action.policy_binding_wallet_id != action.wallet_id:
        reasons.append(R_WALLET_BINDING_MISMATCH)

    if action.method not in action.approved_methods:
        reasons.append(R_METHOD_NOT_ALLOWED)

    if action.input_asset_id not in action.approved_assets:
        reasons.append(R_ASSET_NOT_ALLOWED)
    elif action.approved_assets[action.input_asset_id] != action.input_decimals:
        reasons.append(R_DECIMALS_MISMATCH)
    if action.output_decimals != action.approved_assets.get(action.output_asset_id):
        reasons.append(R_DECIMALS_MISMATCH)

    raw_reason = _validate_raw(action.input_raw)
    if raw_reason is not None:
        reasons.append(raw_reason)
    if action.input_decimals < 0:
        reasons.append(R_DECIMALS_MISMATCH)

    if action.recipient not in action.approved_recipients:
        reasons.append(R_RECIPIENT_NOT_ALLOWED)

    if action.min_output_raw is None:
        reasons.append(R_MIN_OUTPUT_MISSING)
    else:
        min_reason = _validate_raw(action.min_output_raw)
        if min_reason is not None:
            reasons.append(min_reason)
        elif action.quote_output_raw is not None:
            if int(action.min_output_raw) > int(action.quote_output_raw):
                reasons.append(R_MIN_OUTPUT_INVALID)

    if _reject_bool(action.fee_bps) or _reject_bool(action.referrer_fee_bps):
        reasons.append(R_BOOLEAN_NOT_INTEGER)
    elif action.fee_bps + action.referrer_fee_bps > 10000:
        reasons.append(R_FEE_BOUND_EXCEEDED)

    if not action.program_hex or not _HEX_BYTES.match(action.program_hex):
        reasons.append(R_PROGRAM_MISSING)

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

    if _reject_bool(action.action_capacity) or _reject_bool(action.actions_used):
        reasons.append(R_BOOLEAN_NOT_INTEGER)
    elif action.actions_used >= action.action_capacity:
        reasons.append(R_CAPACITY_EXHAUSTED)

    if _reject_bool(action.quote_age_seconds):
        reasons.append(R_BOOLEAN_NOT_INTEGER)
    elif action.quote_age_seconds > action.max_quote_age_seconds:
        reasons.append(R_STALE_INPUT)

    if action.claimed_result_class != RESULT_AUTHORED_FAKE_ONLY:
        reasons.append(R_EVIDENCE_UNMATCHED)

    return reasons


def evaluate_declared_case(
    profile: RestrictionProfile, action: ControlledAction
) -> CaseVerdict:
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
    return RestrictionProfile(version=str(mapping.get("version", "")), declarations=declarations)


def _frozenset_of_strings(value: Any, field: str) -> frozenset[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list")
    return frozenset(str(item) for item in value)


def load_action(mapping: Mapping[str, Any]) -> ControlledAction:
    """Build a ControlledAction from a JSON-like mapping."""
    approved_assets_raw = mapping.get("approved_assets", {})
    if not isinstance(approved_assets_raw, Mapping):
        raise ValueError("approved_assets must be an object")
    approved_assets = {str(k): int(v) for k, v in approved_assets_raw.items()}
    return ControlledAction(
        action_id=str(mapping.get("action_id", "")),
        network=mapping.get("network"),
        entrypoint_address=str(mapping.get("entrypoint_address", "")),
        method=str(mapping.get("method", "")),
        wallet_id=str(mapping.get("wallet_id", "")),
        signer_id=str(mapping.get("signer_id", "")),
        policy_binding_wallet_id=str(mapping.get("policy_binding_wallet_id", "")),
        input_asset_id=str(mapping.get("input_asset_id", "")),
        input_raw=mapping.get("input_raw"),
        input_decimals=int(mapping.get("input_decimals", 0)),
        output_asset_id=str(mapping.get("output_asset_id", "")),
        output_decimals=int(mapping.get("output_decimals", 0)),
        recipient=str(mapping.get("recipient", "")),
        min_output_raw=mapping.get("min_output_raw"),
        quote_output_raw=mapping.get("quote_output_raw"),
        fee_bps=mapping.get("fee_bps", 0),
        referrer_fee_bps=mapping.get("referrer_fee_bps", 0),
        program_hex=mapping.get("program_hex"),
        gas_capacity_raw=mapping.get("gas_capacity_raw"),
        gas_used_raw=mapping.get("gas_used_raw"),
        action_capacity=mapping.get("action_capacity", 0),
        actions_used=mapping.get("actions_used", 0),
        quote_age_seconds=mapping.get("quote_age_seconds", 0),
        max_quote_age_seconds=mapping.get("max_quote_age_seconds", 0),
        approved_networks=_frozenset_of_strings(mapping.get("approved_networks", []), "approved_networks"),
        approved_assets=approved_assets,
        approved_methods=_frozenset_of_strings(mapping.get("approved_methods", []), "approved_methods"),
        approved_recipients=_frozenset_of_strings(mapping.get("approved_recipients", []), "approved_recipients"),
        claimed_result_class=str(mapping.get("claimed_result_class", RESULT_BLOCKED)),
    )


def _load_fixtures(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _run_fixtures(path: Path) -> int:
    data = _load_fixtures(path)
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
            expected_accepted = bool(expect["accepted"])
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
    return _run_fixtures(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
