"""The hosted record build tool: builds, verifies and hashes one version 1 record, offline and read-only.

Pure tests: temporary files only. No database, Docker, network, provider or host access.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from edge_os_api.core import hosted_deployment, hosted_record_tool
from edge_os_api.core.hosted_deployment import canonical

GATES = hosted_deployment.HOST_GATES
GATE_DIR = "docs/qualification/hosted-gates/evidence"


def write_gates(root: Path) -> dict[str, dict[str, str]]:
    gates: dict[str, dict[str, str]] = {}
    for name in GATES:
        relative = f"{GATE_DIR}/{name}.md"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"# {name}\n\nNOT RUN.\n".encode())
        gates[name] = {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return gates


def values(root: Path, **changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "deployment_id": "hosted-demo-1",
        "public_origins": ["https://app.example.com"],
        "cors_origins": ["https://app.example.com"],
        "database_tls_mode": "require",
        "hermes_relay": {"release_id": "hermes-first-call-1", "record_sha256": "a" * 64},
        "research_release": {"release_id": "actual-moe-history2h-nansen-20261022/1", "sha256": "b" * 64},
        "host_gates": write_gates(root),
        "image_digests": {"postgres": "sha256:" + "c" * 64},
        "valid_from": "2026-10-23T00:00:00Z",
        "valid_until": "2026-11-23T00:00:00Z",
    }
    value.update(changes)
    return value


def write_values(root: Path, value: Any) -> Path:
    path = root / "values.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def invoke(arguments: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = hosted_record_tool.main(arguments)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def run(root: Path, value: Any, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    path = write_values(root, value)
    return invoke(["--values", str(path), "--root", str(root)], capsys)


def lines(output: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in output.splitlines():
        if line.startswith("{"):
            found["record"] = line
        elif line.startswith("sha256 "):
            found["sha256"] = line
        elif line.startswith("APPROVED_HOSTED_DEPLOYMENTS = "):
            found["registry"] = line
    return found


def test_it_prints_the_record_its_canonical_hash_and_the_exact_registry_line(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, output, error = run(tmp_path, values(tmp_path), capsys)
    assert (code, error) == (0, "")
    printed = lines(output)
    record = json.loads(printed["record"])
    digest = hashlib.sha256(canonical(record)).hexdigest()
    assert set(record) == hosted_deployment.RECORD_FIELDS
    assert record["schema_version"] == hosted_deployment.RECORD_VERSION
    assert "execution_release" not in record
    assert printed["sha256"] == f"sha256 {digest}"
    assert printed["registry"] == f'APPROVED_HOSTED_DEPLOYMENTS = {{"hosted-demo-1": "{digest}"}}'


def test_the_printed_record_is_the_canonical_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path)
    code, output, error = run(tmp_path, value, capsys)
    assert (code, error) == (0, "")
    record = json.loads(lines(output)["record"])
    assert lines(output)["record"] == canonical(record).decode("utf-8")
    assert len(record["host_gates"]) == 4


def test_a_gate_file_whose_hash_differs_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path)
    reference = value["host_gates"]["h1_egress"]
    (tmp_path / reference["path"]).write_bytes(b"# h1_egress\n\nPASS.\n")
    assert hashlib.sha256((tmp_path / reference["path"]).read_bytes()).hexdigest() != reference["sha256"]
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "h1_egress" in error and "hash" in error.lower()


def test_a_missing_gate_file_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path)
    value["host_gates"]["h2_runner_isolation"]["path"] = f"{GATE_DIR}/absent.md"
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "h2_runner_isolation" in error and "unreadable" in error.lower()


def test_a_gate_path_that_escapes_the_root_is_refused(tmp_path: Path,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_bytes(b"# outside\n")
    value = values(tmp_path)
    value["host_gates"]["h1_egress"]["path"] = f"{GATE_DIR}/../../../../../{outside.name}"
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "h1_egress" in error and "path" in error.lower()
    assert outside.read_bytes() == b"# outside\n"


def test_a_gate_path_outside_the_record_directory_is_refused(tmp_path: Path,
                                                             capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path)
    value["host_gates"]["h1_egress"]["path"] = "elsewhere/h1_egress.md"
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere/h1_egress.md").write_bytes(b"# h1_egress\n")
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "h1_egress" in error and "docs/qualification/" in error


def test_it_never_writes_a_file_or_changes_the_registry(tmp_path: Path,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    path = write_values(tmp_path, values(tmp_path))
    before = sorted(str(item.relative_to(tmp_path)) for item in tmp_path.rglob("*"))
    assert hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS == {}
    code, _output, error = invoke(["--values", str(path), "--root", str(tmp_path)], capsys)
    assert (code, error) == (0, "")
    assert sorted(str(item.relative_to(tmp_path)) for item in tmp_path.rglob("*")) == before
    assert hosted_deployment.APPROVED_HOSTED_DEPLOYMENTS == {}


def test_a_record_the_parser_refuses_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path, cors_origins=["https://other.example.com"])
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "hosted_deployment_invalid" in error


def test_a_version_2_field_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path, execution_release={"release_id": "inapp/1", "sha256": "d" * 64})
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "version 1" in error.lower()


def test_a_version_2_schema_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path, schema_version=hosted_deployment.RECORD_VERSION_2)
    code, output, error = run(tmp_path, value, capsys)
    assert code == 1
    assert output == ""
    assert "version 1" in error.lower()


def test_a_values_file_that_is_not_an_object_is_refused(tmp_path: Path,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    code, output, error = run(tmp_path, [], capsys)
    assert code == 1
    assert output == ""
    assert "hosted_record_values_invalid" in error


def test_the_root_flag_resolves_gate_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    value = values(tmp_path)
    path = write_values(tmp_path, value)
    monkeypatch.chdir(tmp_path)
    code, output, error = invoke(["--values", str(path)], capsys)
    assert (code, error) == (0, "")
    assert lines(output)["registry"].startswith("APPROVED_HOSTED_DEPLOYMENTS = ")
