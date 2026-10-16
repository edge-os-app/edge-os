import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.kuru_deployed_source.compare_bytecode import (
    first_difference, inspect_fixture, load_runtime, main, metadata_tail, push_values,
)

FIXTURES = Path(__file__).resolve().parents[2] / "docs/qualification/kuru-deployed-source"
ENTRYPOINT = FIXTURES / "entrypoint-runtime-block-0x6c1db44.hex"
CURRENT_ROUTER = FIXTURES / "current-router-runtime-block-0x6c1db44.hex"
PUBLISHED_ROUTER = FIXTURES / "published-router-runtime-block-0x6c1db44.hex"
SOLC_0_8_28_ONLY = "a164736f6c634300081c"
SOURCE_MIN = "1000276a4"  # 4_295_128_739 + 1 in the public KuruFlow.sol
SOURCE_MAX = "fffd8963efd1fc6a506488495d951d5263988d24"  # ..._970_341 - 1 in the public KuruFlow.sol
OFF_BY_ONE_MAX = "fffd8963efd1fc6a506488495d951d5263988d25"
WMON = "3bd359c1119da7da1d913d1c4d2b7c461115433a"
METADATA = bytes.fromhex("a1") + bytes(2) + (3).to_bytes(2, "big")  # 3-byte stand-in tail plus its length


class FixtureFormatTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".hex", delete=False, encoding="ascii")
        with handle:
            handle.write(text)
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def test_accepts_lowercase_hex_with_one_newline(self):
        self.assertEqual(load_runtime(self._write("0x6001\n")), bytes.fromhex("6001"))

    def test_rejects_malformed_fixtures(self):
        for text in ("6001", "0x600", "0x60 01", "0x6001\n\n", "0X6001", "0x60AB", "0x", "0x60zz"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_runtime(self._write(text))

    def test_rejects_metadata_length_beyond_code(self):
        with self.assertRaises(ValueError):
            metadata_tail(bytes.fromhex("00ff"))


class PushWalkTests(unittest.TestCase):
    def test_skips_push_data_and_counts_values(self):
        # PUSH2 0x6005 hides a PUSH1-looking byte; PUSH1 0x05 is the only real PUSH1.
        code = bytes.fromhex("6160056005") + METADATA
        self.assertEqual(push_values(code), {0x6005: 1, 0x05: 1})

    def test_rejects_truncated_push(self):
        with self.assertRaises(ValueError):
            push_values(bytes.fromhex("6201") + METADATA)


class CompareControlTests(unittest.TestCase):
    def test_known_equal_control(self):
        code = load_runtime(CURRENT_ROUTER)
        self.assertIsNone(first_difference(code, bytes(code)))

    def test_one_byte_different_control(self):
        code = load_runtime(CURRENT_ROUTER)
        changed = bytearray(code)
        changed[4000] ^= 0x01
        self.assertEqual(first_difference(code, bytes(changed)), 4000)

    def test_prefix_reports_shorter_length(self):
        self.assertEqual(first_difference(b"\x01\x02", b"\x01"), 1)

    def test_cli_compare_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["compare", str(CURRENT_ROUTER), str(CURRENT_ROUTER)]), 0)
            self.assertEqual(main(["compare", str(CURRENT_ROUTER), str(PUBLISHED_ROUTER)]), 1)


class DeployedFixtureTests(unittest.TestCase):
    """Pins the facts that SOURCE_IDENTITY.md relies on."""

    def test_entrypoint_identity(self):
        report = inspect_fixture(
            ENTRYPOINT, "da214086b3c9bc283c9fe99966baf01a5b97ad8f6f3a7313d37f89008594e1cf", 3251, []
        )
        self.assertEqual(report["metadata_cbor_hex"], SOLC_0_8_28_ONLY)

    def test_current_router_constants_differ_from_public_source(self):
        report = inspect_fixture(
            CURRENT_ROUTER,
            "9cf6f5c85f5f6a621badb478b91cff95c43542d695ccff90715830fa2bc2c649",
            8783,
            [SOURCE_MIN, SOURCE_MAX, OFF_BY_ONE_MAX, WMON],
        )
        self.assertEqual(report["metadata_cbor_hex"], SOLC_0_8_28_ONLY)
        self.assertEqual(
            report["constant_push_counts"], {SOURCE_MIN: 2, SOURCE_MAX: 0, OFF_BY_ONE_MAX: 2, WMON: 2}
        )

    def test_published_router_control_matches_public_source_constant(self):
        report = inspect_fixture(
            PUBLISHED_ROUTER,
            "de00ae5d02cf8f620781f8b6643b097096d984213adbff898d805ccb61df7282",
            6381,
            [SOURCE_MIN, SOURCE_MAX, OFF_BY_ONE_MAX],
        )
        self.assertEqual(report["constant_push_counts"], {SOURCE_MIN: 1, SOURCE_MAX: 1, OFF_BY_ONE_MAX: 0})

    def test_identity_mismatch_is_an_error(self):
        with self.assertRaises(ValueError):
            inspect_fixture(ENTRYPOINT, "00" * 32, 3251, [])


if __name__ == "__main__":
    unittest.main()
