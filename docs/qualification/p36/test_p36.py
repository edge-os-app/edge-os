import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class P36QualificationCheckTests(unittest.TestCase):
    def test_public_check_reports_unresolved_and_independent_fixture_values(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "check_p36.py")],
            cwd=ROOT.parents[2],
            check=True,
            capture_output=True,
            text=True,
        )

        report = json.loads(result.stdout)
        self.assertEqual(report["assessment"], "UNRESOLVED")
        self.assertEqual(report["fixture_status"], "ILLUSTRATIVE_UNADOPTED")
        self.assertEqual(report["reference_case"]["lp_inventory_value"], "400")
        self.assertEqual(report["reference_case"]["holding_comparator_value"], "500")
        self.assertEqual(report["reference_case"]["gross_fees"], "5")
        self.assertEqual(report["reference_case"]["impermanent_loss"], "-100")
        self.assertEqual(report["reference_case"]["net_benefit"], "-98")


if __name__ == "__main__":
    unittest.main()
