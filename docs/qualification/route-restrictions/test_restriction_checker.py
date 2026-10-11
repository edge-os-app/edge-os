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
    "fee_collector_address": "",
    "referrer_address": "",
    "is_in_token_fee": None,
    "program_hex": "0xdeadbeef",
    "allowance_raw": "1000000000000000000",
    "gas_capacity_raw": "50000000000000000",
    "gas_used_raw": "21000000000000000",
    "action_capacity": 1,
    "actions_used": 0,
    "quote_age_seconds": 5,
    "max_quote_age_seconds": 30,
    "input_age_seconds": 4,
    "max_input_age_seconds": 30,
    "intent_expires_at_seconds": 2000000000,
    "mandate_expires_at_seconds": 2000000000,
    "now_seconds": 1791668000,
    "approved_networks": ["143"],
    "approved_entrypoints": ["0xb3e6778480b2E488385E8205eA05E20060B813cb"],
    "approved_signers": ["signer-A"],
    "approved_assets": {"MON-native-143": 18, "USDC-143": 6},
    "approved_methods": ["executeSwap"],
    "approved_recipients": ["wallet-A"],
    "approved_input_raw": "1000000000000000000",
    "approved_program_hex": ["0xdeadbeef"],
    "approved_fee_bps": 0,
    "approved_referrer_fee_bps": 0,
    "approved_fee_collectors": [],
    "approved_referrers": [],
    "approved_is_in_token_fee": None,
    "approved_allowance_raw": "1000000000000000000",
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

    def test_enforced_with_not_run_evidence_is_reported(self) -> None:
        declarations = {c: dict(_READY_CONTROL) for c in checker.MANDATORY_CONTROLS}
        declarations["fees"] = {"state": "ENFORCED", "layer": "CONTRACT", "evidence": "NOT_RUN"}
        profile = checker.load_profile({"version": "t", "declarations": declarations})
        reasons = checker.profile_readiness_reasons(profile)
        self.assertIn(f"{checker.R_EVIDENCE_MISSING}:fees", reasons)


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

    def test_wallet_whitespace(self) -> None:
        _expect_blocked(
            self,
            self._blocked(wallet_id=" ", policy_binding_wallet_id=" "),
            checker.R_WALLET_BINDING_MISSING,
        )

    def test_wallet_tabs_newline(self) -> None:
        _expect_blocked(
            self,
            self._blocked(wallet_id="\t\n", policy_binding_wallet_id="\t\n"),
            checker.R_WALLET_BINDING_MISSING,
        )

    def test_signer_whitespace(self) -> None:
        _expect_blocked(self, self._blocked(signer_id=" "), checker.R_WALLET_BINDING_MISSING)

    def test_policy_whitespace(self) -> None:
        _expect_blocked(self, self._blocked(policy_binding_wallet_id=" "), checker.R_WALLET_BINDING_MISSING)

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

    def test_entrypoint_not_allowed(self) -> None:
        _expect_blocked(
            self,
            self._blocked(entrypoint_address="0x000000000000000000000000000000000000dEaD"),
            checker.R_ENTRYPOINT_NOT_ALLOWED,
        )

    def test_entrypoint_empty(self) -> None:
        _expect_blocked(self, self._blocked(entrypoint_address=""), checker.R_ENTRYPOINT_NOT_ALLOWED)

    def test_output_asset_not_allowed(self) -> None:
        _expect_blocked(self, self._blocked(output_asset_id="DAI-143"), checker.R_ASSET_NOT_ALLOWED)

    def test_quote_unknown(self) -> None:
        _expect_blocked(self, self._blocked(quote_output_raw=None), checker.R_QUOTE_UNKNOWN)

    def test_quote_malformed(self) -> None:
        _expect_blocked(self, self._blocked(quote_output_raw="1e3"), checker.R_RAW_AMOUNT_INVALID)

    def test_freshness_unknown(self) -> None:
        _expect_blocked(self, self._blocked(quote_age_seconds=None), checker.R_FRESHNESS_UNKNOWN)

    def test_max_freshness_unknown(self) -> None:
        _expect_blocked(self, self._blocked(max_quote_age_seconds=None), checker.R_FRESHNESS_UNKNOWN)

    def test_action_capacity_unknown(self) -> None:
        _expect_blocked(self, self._blocked(action_capacity=None), checker.R_CAPACITY_UNKNOWN)

    def test_actions_used_unknown(self) -> None:
        _expect_blocked(self, self._blocked(actions_used=None), checker.R_CAPACITY_UNKNOWN)

    def test_signer_not_allowed(self) -> None:
        _expect_blocked(self, self._blocked(signer_id="signer-B"), checker.R_SIGNER_NOT_ALLOWED)

    def test_input_not_approved(self) -> None:
        _expect_blocked(self, self._blocked(input_raw="3000000000000000000"), checker.R_INPUT_NOT_APPROVED)

    def test_raw_trailing_newline(self) -> None:
        _expect_blocked(self, self._blocked(input_raw="1000000000000000000\n"), checker.R_RAW_AMOUNT_INVALID)

    def test_program_empty_bytes(self) -> None:
        _expect_blocked(self, self._blocked(program_hex="0x"), checker.R_PROGRAM_MISSING)

    def test_program_trailing_newline(self) -> None:
        _expect_blocked(self, self._blocked(program_hex="0xdeadbeef\n"), checker.R_PROGRAM_MISSING)

    def test_program_not_approved(self) -> None:
        _expect_blocked(self, self._blocked(program_hex="0xccdd"), checker.R_PROGRAM_NOT_APPROVED)

    def test_fee_not_approved(self) -> None:
        _expect_blocked(self, self._blocked(fee_bps=1), checker.R_FEE_NOT_APPROVED)

    def test_fee_unknown(self) -> None:
        _expect_blocked(self, self._blocked(fee_bps=None), checker.R_FEE_UNKNOWN)

    def test_referrer_fee_unknown(self) -> None:
        _expect_blocked(self, self._blocked(referrer_fee_bps=None), checker.R_FEE_UNKNOWN)

    def test_fee_collector_not_allowed(self) -> None:
        _expect_blocked(
            self,
            self._blocked(fee_bps=5, approved_fee_bps=5, fee_collector_address="wallet-B"),
            checker.R_FEE_COLLECTOR_NOT_ALLOWED,
        )

    def test_fee_collector_missing(self) -> None:
        _expect_blocked(self, self._blocked(fee_bps=5, approved_fee_bps=5), checker.R_FEE_COLLECTOR_NOT_ALLOWED)

    def test_referrer_not_allowed(self) -> None:
        _expect_blocked(
            self,
            self._blocked(referrer_fee_bps=5, approved_referrer_fee_bps=5, referrer_address="wallet-B"),
            checker.R_REFERRER_NOT_ALLOWED,
        )

    def test_fee_mode_unknown(self) -> None:
        _expect_blocked(
            self,
            self._blocked(
                fee_bps=5,
                approved_fee_bps=5,
                fee_collector_address="wallet-FC",
                approved_fee_collectors=["wallet-FC"],
            ),
            checker.R_FEE_MODE_UNKNOWN,
        )

    def test_fee_mode_not_approved(self) -> None:
        _expect_blocked(
            self,
            self._blocked(
                fee_bps=5,
                approved_fee_bps=5,
                fee_collector_address="wallet-FC",
                approved_fee_collectors=["wallet-FC"],
                is_in_token_fee=True,
                approved_is_in_token_fee=False,
            ),
            checker.R_FEE_MODE_NOT_APPROVED,
        )

    def test_allowance_unknown(self) -> None:
        _expect_blocked(self, self._blocked(allowance_raw=None), checker.R_ALLOWANCE_UNKNOWN)

    def test_allowance_not_approved(self) -> None:
        _expect_blocked(self, self._blocked(allowance_raw="999"), checker.R_ALLOWANCE_NOT_APPROVED)

    def test_input_freshness_unknown(self) -> None:
        _expect_blocked(self, self._blocked(input_age_seconds=None), checker.R_INPUT_FRESHNESS_UNKNOWN)

    def test_stale_input_age(self) -> None:
        _expect_blocked(self, self._blocked(input_age_seconds=31), checker.R_STALE_INPUT_AGE)

    def test_expiry_unknown(self) -> None:
        _expect_blocked(self, self._blocked(now_seconds=None), checker.R_EXPIRY_UNKNOWN)

    def test_intent_expired(self) -> None:
        _expect_blocked(self, self._blocked(now_seconds=2000000000), checker.R_INTENT_EXPIRED)

    def test_mandate_expired(self) -> None:
        _expect_blocked(
            self,
            self._blocked(mandate_expires_at_seconds=1791668000, now_seconds=1791668001),
            checker.R_MANDATE_EXPIRED,
        )

    def test_recipient_empty_binding(self) -> None:
        _expect_blocked(self, self._blocked(recipient="", approved_recipients=[""]), checker.R_RECIPIENT_NOT_ALLOWED)

    def test_recipient_whitespace(self) -> None:
        _expect_blocked(self, self._blocked(recipient="   "), checker.R_RECIPIENT_NOT_ALLOWED)

    def test_entrypoint_empty_binding(self) -> None:
        _expect_blocked(
            self,
            self._blocked(entrypoint_address="", approved_entrypoints=[""]),
            checker.R_ENTRYPOINT_NOT_ALLOWED,
        )

    def test_method_empty_binding(self) -> None:
        _expect_blocked(self, self._blocked(method="", approved_methods=[""]), checker.R_METHOD_NOT_ALLOWED)

    def test_signer_empty_adopted(self) -> None:
        _expect_blocked(self, self._blocked(approved_signers=[""]), checker.R_ADOPTED_IDENTITY_INVALID)

    def test_asset_empty_adopted(self) -> None:
        _expect_blocked(
            self,
            self._blocked(approved_assets={"": 18, "MON-native-143": 18, "USDC-143": 6}),
            checker.R_ADOPTED_IDENTITY_INVALID,
        )

    def test_network_empty_adopted(self) -> None:
        _expect_blocked(self, self._blocked(approved_networks=[""]), checker.R_ADOPTED_IDENTITY_INVALID)

    def test_program_empty_adopted(self) -> None:
        _expect_blocked(self, self._blocked(approved_program_hex=[""]), checker.R_ADOPTED_IDENTITY_INVALID)

    def test_fee_collector_empty_binding(self) -> None:
        _expect_blocked(
            self,
            self._blocked(
                fee_bps=5,
                approved_fee_bps=5,
                fee_collector_address="",
                approved_fee_collectors=[""],
                is_in_token_fee=True,
                approved_is_in_token_fee=True,
            ),
            checker.R_FEE_COLLECTOR_NOT_ALLOWED,
        )

    def test_referrer_empty_binding(self) -> None:
        _expect_blocked(
            self,
            self._blocked(
                referrer_fee_bps=5,
                approved_referrer_fee_bps=5,
                referrer_address="",
                approved_referrers=[""],
                is_in_token_fee=True,
                approved_is_in_token_fee=True,
            ),
            checker.R_REFERRER_NOT_ALLOWED,
        )

    def test_missing_key_placeholder_still_blocks(self) -> None:
        # The gate reproduction: an absent address with an adopted [""] placeholder.
        data = dict(_VALID_ACTION)
        data.pop("fee_collector_address", None)
        data.update(
            {
                "fee_bps": 5,
                "approved_fee_bps": 5,
                "approved_fee_collectors": [""],
                "is_in_token_fee": True,
                "approved_is_in_token_fee": True,
            }
        )
        verdict = checker.evaluate_declared_case(_ready_profile(), checker.load_action(data))
        self.assertFalse(verdict.accepted)
        self.assertIn(checker.R_FEE_COLLECTOR_NOT_ALLOWED, verdict.reasons)


class MalformedDeclarationTest(unittest.TestCase):
    """A malformed declaration raises a field-specific ValueError. No coercion."""

    def _load(self, **overrides: object) -> None:
        checker.load_action(_action(**overrides))

    def test_fee_float_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(fee_bps=12.5)

    def test_fee_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(fee_bps=-100)

    def test_fee_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(fee_bps="30")

    def test_fee_boolean_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(fee_bps=True)

    def test_capacity_float_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(action_capacity=0.5)

    def test_actions_used_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(actions_used=-5)

    def test_decimals_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(input_decimals="18")

    def test_decimals_none_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(input_decimals=None)

    def test_network_non_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            checker.load_action({**_VALID_ACTION, "network": ["143"]})

    def test_identifier_boolean_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(method=True)

    def test_approved_item_non_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(approved_methods=[True])

    def test_approved_asset_decimal_float_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._load(approved_assets={"MON-native-143": 18, "USDC-143": 6.5})

    def test_profile_version_missing_rejected(self) -> None:
        with self.assertRaises(ValueError):
            checker.load_profile({"declarations": {}})

    def test_profile_version_non_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            checker.load_profile({"version": True, "declarations": {}})

    def test_action_id_missing_rejected(self) -> None:
        with self.assertRaises(ValueError):
            checker.load_action({**_VALID_ACTION, "action_id": ""})


class FixtureExpectationTest(unittest.TestCase):
    """The real command rejects a non-boolean fixture expectation."""

    def test_non_boolean_expectation_runs_clean_error(self) -> None:
        import json
        import tempfile

        fixtures = {
            "schema": "p21-route-restrictions/1",
            "scenarios": [
                {
                    "name": "tampered",
                    "profile": {"version": "v", "declarations": {c: dict(_READY_CONTROL) for c in checker.MANDATORY_CONTROLS}},
                    "base_action": dict(_VALID_ACTION),
                    "cases": [{"name": "boom", "override": {}, "expect": {"accepted": "false"}}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tampered.json"
            path.write_text(json.dumps(fixtures), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(_CHECKER_PATH), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PASS", result.stdout)
        self.assertIn("error:", result.stdout)


class OfflinePropertyTest(unittest.TestCase):
    _ALLOWED_IMPORTS = {"__future__", "json", "re", "sys", "dataclasses", "enum", "pathlib", "typing", "fractions"}
    _FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
    _MODULE_PATHS = (_CHECKER_PATH, _HERE / "capacity_examples.py")

    def _imports(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        return imported

    def test_checker_imports_are_offline_only(self) -> None:
        for path in self._MODULE_PATHS:
            unexpected = self._imports(path) - self._ALLOWED_IMPORTS
            self.assertEqual(unexpected, set(), f"{path.name} imports non-offline modules: {unexpected}")

    def test_checker_has_no_dynamic_execution(self) -> None:
        for path in self._MODULE_PATHS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            called = {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            self.assertEqual(called & self._FORBIDDEN_CALLS, set(), f"{path.name} has dynamic execution")

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
