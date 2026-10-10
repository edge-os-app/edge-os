"""Offline unit tests for the route-restrictions checker.

These tests exercise the public offline interface only. They prove the
restriction logic and that the default command has no network or signing code
path. A local success is always AUTHORED_FAKE_ONLY.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

import restriction_checker as checker

_HERE = Path(__file__).resolve().parent
_CHECKER_PATH = _HERE / "restriction_checker.py"

_READY_CONTROL = {
    "state": "ENFORCED",
    "layer": "CONTRACT",
    "evidence": "LOCAL_TESTED",
}

_VALID_ACTION = {
    "action_id": "test",
    "network": "143",
    "entrypoint_address": "0xb3e6778480b2E488385E8205eA05E20060B813cb",
    "method": "executeSwap",
    "wallet_id": "wallet-A",
    "signer_id": "signer-A",
    "policy_binding_wallet_id": "wallet-A",
    "input_asset_id": "MON-native-143",
    "input_raw": "1000000000000000000",
    "input_decimals": 18,
    "output_asset_id": "USDC-143",
    "output_decimals": 6,
    "recipient": "wallet-A",
    "min_output_raw": "950000",
    "quote_output_raw": "1000000",
    "fee_bps": 0,
    "referrer_fee_bps": 0,
    "program_hex": "0xdeadbeef",
    "gas_capacity_raw": "50000000000000000",
    "gas_used_raw": "21000000000000000",
    "action_capacity": 1,
    "actions_used": 0,
    "quote_age_seconds": 5,
    "max_quote_age_seconds": 30,
    "approved_networks": ["143"],
    "approved_assets": {"MON-native-143": 18, "USDC-143": 6},
    "approved_methods": ["executeSwap"],
    "approved_recipients": ["wallet-A"],
    "claimed_result_class": "AUTHORED_FAKE_ONLY",
}


def _ready_profile() -> checker.RestrictionProfile:
    return checker.load_profile(
        {
            "version": "test-ready",
            "declarations": {c: dict(_READY_CONTROL) for c in checker.MANDATORY_CONTROLS},
        }
    )


def _action(**overrides: object) -> checker.ControlledAction:
    data = dict(_VALID_ACTION)
    data.update(overrides)
    return checker.load_action(data)


def _expect_blocked(test: unittest.TestCase, verdict: checker.CaseVerdict, reason: str) -> None:
    test.assertFalse(verdict.accepted)
    test.assertEqual(verdict.result_class, checker.RESULT_BLOCKED)
    test.assertTrue(
        any(r.startswith(reason) for r in verdict.reasons),
        f"expected reason {reason}, got {verdict.reasons}",
    )


class PositiveControlTest(unittest.TestCase):
    def test_valid_action_is_authored_fake_only(self) -> None:
        verdict = checker.evaluate_declared_case(_ready_profile(), _action())
        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.result_class, checker.RESULT_AUTHORED_FAKE_ONLY)
        self.assertEqual(verdict.reasons, ())


class ProfileReadinessTest(unittest.TestCase):
    def test_ready_profile_has_no_reasons(self) -> None:
        self.assertEqual(checker.profile_readiness_reasons(_ready_profile()), ())

    def test_missing_control_is_reported(self) -> None:
        declarations = {c: dict(_READY_CONTROL) for c in checker.MANDATORY_CONTROLS}
        declarations.pop("opaque_program")
        profile = checker.load_profile({"version": "t", "declarations": declarations})
        reasons = checker.profile_readiness_reasons(profile)
        self.assertIn(f"{checker.R_MISSING_CONTROL}:opaque_program", reasons)

    def test_unsupported_control_is_reported(self) -> None:
        declarations = {c: dict(_READY_CONTROL) for c in checker.MANDATORY_CONTROLS}
        declarations["opaque_program"] = {"state": "UNKNOWN", "layer": "INDEPENDENT_POLICY", "evidence": "NOT_RUN"}
        profile = checker.load_profile({"version": "t", "declarations": declarations})
        reasons = checker.profile_readiness_reasons(profile)
        self.assertIn(f"{checker.R_UNSUPPORTED_CONTROL}:opaque_program", reasons)


class OneFieldAdversarialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _ready_profile()

    def _blocked(self, **overrides: object) -> checker.CaseVerdict:
        verdict = checker.evaluate_declared_case(self.profile, _action(**overrides))
        self.assertFalse(verdict.accepted)
        return verdict

    def test_wrong_network(self) -> None:
        _expect_blocked(self, self._blocked(network="10143"), checker.R_NETWORK_NOT_ALLOWED)

    def test_wallet_policy_mismatch(self) -> None:
        _expect_blocked(self, self._blocked(policy_binding_wallet_id="wallet-B"), checker.R_WALLET_BINDING_MISMATCH)

    def test_missing_signer(self) -> None:
        _expect_blocked(self, self._blocked(signer_id=""), checker.R_WALLET_BINDING_MISSING)

    def test_method_not_allowed(self) -> None:
        _expect_blocked(self, self._blocked(method="executeSwapWithReceiver"), checker.R_METHOD_NOT_ALLOWED)

    def test_asset_not_allowed(self) -> None:
        _expect_blocked(self, self._blocked(input_asset_id="DAI-143"), checker.R_ASSET_NOT_ALLOWED)

    def test_input_decimals_mismatch(self) -> None:
        _expect_blocked(self, self._blocked(input_decimals=6), checker.R_DECIMALS_MISMATCH)

    def test_raw_negative(self) -> None:
        _expect_blocked(self, self._blocked(input_raw="-1"), checker.R_RAW_AMOUNT_INVALID)

    def test_raw_leading_zero(self) -> None:
        _expect_blocked(self, self._blocked(input_raw="0100"), checker.R_RAW_AMOUNT_INVALID)

    def test_raw_boolean(self) -> None:
        _expect_blocked(self, self._blocked(input_raw=True), checker.R_BOOLEAN_NOT_INTEGER)

    def test_raw_missing_is_not_zero(self) -> None:
        _expect_blocked(self, self._blocked(input_raw=None), checker.R_RAW_AMOUNT_INVALID)

    def test_recipient_not_allowed(self) -> None:
        _expect_blocked(self, self._blocked(recipient="wallet-B"), checker.R_RECIPIENT_NOT_ALLOWED)

    def test_min_output_missing(self) -> None:
        _expect_blocked(self, self._blocked(min_output_raw=None), checker.R_MIN_OUTPUT_MISSING)

    def test_min_output_above_quote(self) -> None:
        _expect_blocked(self, self._blocked(min_output_raw="1000001"), checker.R_MIN_OUTPUT_INVALID)

    def test_fee_bound_exceeded(self) -> None:
        _expect_blocked(self, self._blocked(fee_bps=6000, referrer_fee_bps=5000), checker.R_FEE_BOUND_EXCEEDED)

    def test_fee_boolean(self) -> None:
        _expect_blocked(self, self._blocked(fee_bps=True), checker.R_BOOLEAN_NOT_INTEGER)

    def test_program_missing(self) -> None:
        _expect_blocked(self, self._blocked(program_hex=None), checker.R_PROGRAM_MISSING)

    def test_program_not_hex(self) -> None:
        _expect_blocked(self, self._blocked(program_hex="zzzz"), checker.R_PROGRAM_MISSING)

    def test_gas_capacity_unknown(self) -> None:
        _expect_blocked(self, self._blocked(gas_capacity_raw=None), checker.R_CAPACITY_UNKNOWN)

    def test_gas_exhausted(self) -> None:
        _expect_blocked(self, self._blocked(gas_used_raw="50000000000000001"), checker.R_CAPACITY_EXHAUSTED)

    def test_action_capacity_exhausted(self) -> None:
        _expect_blocked(self, self._blocked(actions_used=1), checker.R_CAPACITY_EXHAUSTED)

    def test_stale_input(self) -> None:
        _expect_blocked(self, self._blocked(quote_age_seconds=31), checker.R_STALE_INPUT)

    def test_evidence_unmatched(self) -> None:
        _expect_blocked(self, self._blocked(claimed_result_class="REAL_READY"), checker.R_EVIDENCE_UNMATCHED)


class OfflinePropertyTest(unittest.TestCase):
    _ALLOWED_IMPORTS = {"__future__", "json", "re", "sys", "dataclasses", "enum", "pathlib", "typing"}
    _FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}

    def test_checker_imports_are_offline_only(self) -> None:
        tree = ast.parse(_CHECKER_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        unexpected = imported - self._ALLOWED_IMPORTS
        self.assertEqual(unexpected, set(), f"checker imports non-offline modules: {unexpected}")

    def test_checker_has_no_dynamic_execution(self) -> None:
        tree = ast.parse(_CHECKER_PATH.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(called & self._FORBIDDEN_CALLS, set())

    def test_default_command_runs_offline_and_reports_not_run(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(_CHECKER_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provider_executed: NOT_RUN", result.stdout)
        self.assertIn("failures: 0", result.stdout)
        self.assertIn("AUTHORED_FAKE_ONLY", result.stdout)


if __name__ == "__main__":
    unittest.main()
