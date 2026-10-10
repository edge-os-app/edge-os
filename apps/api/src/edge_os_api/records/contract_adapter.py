"""Small adapter over the frozen P02 contract checker (`docs/contracts/p02/check_contract.py`).

The checker module is loaded unchanged from the repository. `FROZEN_SHA256` pins the reviewed bytes so a
changed contract fails loudly instead of silently altering API behaviour.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
CONTRACT_DIR = REPO_ROOT / "docs" / "contracts" / "p02"
CHECKER_PATH = CONTRACT_DIR / "check_contract.py"
FROZEN_SHA256 = {
    "check_contract.py": "06f3820a2ccfcf1445aef8240e5808977f8adc708ab32aecfedf28ef323d8f79",
    "contract.json": "1ce8a41cc6d6a097f73cf1fbd24cd8fc4d99c685c52ebf25437427a1a7948768",
    "fixtures/complete-strategy.json": "9ff3ab72c10616aacd37d2381a9a10500789fdbe671f2adb8314ed6a54479771",
}


class ContractChanged(RuntimeError):
    pass


def verify_frozen_files() -> None:
    for name, expected in FROZEN_SHA256.items():
        actual = hashlib.sha256((CONTRACT_DIR / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ContractChanged(f"frozen P02 file changed: {name}")


def _load() -> Any:
    verify_frozen_files()
    spec = importlib.util.spec_from_file_location("edge_os_p02_checker", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the P02 contract checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_checker = _load()
Invalid = _checker.Invalid
CONTRACT: dict[str, Any] = _checker.CONTRACT
FIXTURE_STRATEGY: dict[str, Any] = _checker.STRATEGY
canonical_bytes = _checker.canonical_bytes
sha256_hex = _checker.sha256
strict_loads = _checker.strict_loads
validate_record = _checker.validate_record
validate_strategy = _checker.validate_strategy
validate_envelope = _checker.validate_envelope
validate_record_bundle = _checker.validate_record_bundle
validate_http_error = _checker.validate_http_error
validate_compile_fields = _checker._validate_compile_fields  # no public equivalent; same checks as StrategySpec
required_history = _checker.required_history
parse_utc_timestamp = _checker.parse_utc_timestamp

CREATE_STRATEGY_FIELDS: list[str] = CONTRACT["required_strategy_fields"]["CREATE_STRATEGY"]
SUPPORTED_RESTRICTIONS: dict[str, dict[str, Any]] = CONTRACT["supported_restrictions"]
MANIFEST: dict[str, str] = CONTRACT["identity"]["manifest_components"]


def utc_string(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc)


def manifest_sha256() -> str:
    return sha256_hex(MANIFEST)
