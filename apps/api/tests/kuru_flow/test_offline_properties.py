from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

import edge_os_api.kuru_flow as kuru_flow

from edge_os_api.kuru_flow.transaction_preparation import prepare_unsigned_transaction
from edge_os_api.kuru_flow.types import ResponseProvenance

from kuru_flow._support import base_config, encode_execute_swap, load_fixtures, transaction_response

PACKAGE_DIR = Path(kuru_flow.__file__).parent
FORBIDDEN_ROOTS = {
    "socket",
    "ssl",
    "http",
    "httpx",
    "requests",
    "urllib",
    "aiohttp",
    "websockets",
    "web3",
    "eth_account",
    "eth_utils",
    "eth_abi",
    "subprocess",
}


def _source_files() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def test_package_imports_no_network_or_provider_module():
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in FORBIDDEN_ROOTS:
                    offenders.append(f"{path.name}:{name}")
    assert offenders == []


def test_no_sha3_substitution_for_ethereum_keccak():
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        assert "sha3_" not in text, f"{path.name} references a SHA-3 call"
        assert "keccak_256" not in text and "keccak256" not in text, f"{path.name} references keccak"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _source_files())
    assert "Keccak" in combined


def test_application_composition_does_not_reference_the_package():
    import edge_os_api

    app_root = Path(edge_os_api.__file__).parent
    offenders = [
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if path.parent != PACKAGE_DIR and "kuru_flow" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_candidate_is_frozen_and_immutable():
    result = prepare_unsigned_transaction(
        quote_response=transaction_response(encode_execute_swap()),
        provenance=ResponseProvenance.AUTHORED,
        config=base_config(),
        now="2026-10-10T00:00:00Z",
        quote_age_seconds=1,
        input_age_seconds=1,
    )
    candidate = result.candidate
    assert candidate is not None
    with pytest.raises(Exception):
        candidate.value_raw = "0"
    with pytest.raises(Exception):
        candidate.intent.amount_user_sells = "0"


def _canonical_sha(response: dict) -> str:
    payload = json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_fixture_manifest_is_intact():
    document = load_fixtures()
    assert document["schema"] == "p20-kuru-flow-adapter/1"
    labels = {fixture["label"] for fixture in document["fixtures"]}
    assert labels == {"AUTHORED"}
    assert "RECORDED" not in labels
    for fixture in document["fixtures"]:
        assert _canonical_sha(fixture["response"]) == fixture["sha256"], fixture["name"]
