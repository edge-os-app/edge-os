from __future__ import annotations

import ast
from pathlib import Path

import edge_os_api.kuru_flow.policy_binding as policy_binding

PACKAGE_DIR = Path(policy_binding.__file__).parent
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
    "os",
}
SECRET_TOKENS = ("PRIVY_APP_SECRET", "PRIVATE_KEY", "getenv", "environ")


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


def test_package_reads_no_credentials_or_environment():
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in SECRET_TOKENS:
            if token in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def test_package_declares_the_provider_as_not_run():
    assert policy_binding.PROVIDER_EXECUTED == "NOT_RUN"


NO_RETRY_OR_LOG_TOKENS = ("retry", "timeout", "sleep", "logging", "logger", "print(")


def test_package_has_no_retry_timeout_or_logging_constructs():
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in NO_RETRY_OR_LOG_TOKENS:
            if token in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def test_package_defines_no_signing_or_broadcast_function():
    forbidden = ("sign", "broadcast", "send", "transfer", "approve")
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered = node.name.lower()
                if any(token in lowered for token in forbidden):
                    offenders.append(f"{path.name}:{node.name}")
    assert offenders == []
