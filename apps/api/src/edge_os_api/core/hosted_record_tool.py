"""Build, verify and hash one hosted deployment version 1 record. Offline, read-only, no registry change.

The tool reads a values file, verifies each host-gate file against its declared SHA-256, builds the canonical version 1
record, validates it with the production parser in `core.hosted_deployment`, and prints the record, its canonical
SHA-256 and the exact registry line. It writes no file, reads no network and never changes
`APPROVED_HOSTED_DEPLOYMENTS`.

Usage: `python -m edge_os_api.core.hosted_record_tool --values <json> [--root <repository root>]`.
Exit 0 on success, 1 on a refusal and 2 on a usage error.

Version 2 is refused on purpose: this tool builds the research-only version 1 record. A source-built image carries the
registry hash, so the record pins only images that do not depend on it (see
`docs/qualification/hosted-gates/HOSTED_RECORD_V2_RUNBOOK.md`).

`_parse` and `_strict_object` are imported from `core.hosted_deployment` on purpose. One parser stays authoritative,
and this ticket may change that module only for the registry line.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import sys
from pathlib import Path
from typing import Any

from edge_os_api.core.hosted_deployment import (
    HOST_GATES,
    RECORD_FIELDS,
    RECORD_VERSION,
    HostedDeploymentRefused,
    _parse,
    _strict_object,
    canonical,
)

VERSION_FIELD = "schema_version"
GATE_FIELDS = frozenset({"path", "sha256"})


class RecordToolRefused(RuntimeError):
    """The values file or a gate file cannot produce the approved record. The message never holds a field value."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def read_values(path: Path) -> dict[str, Any]:
    """One strict JSON object from the values file. Repeated keys and non-finite numbers are refused."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise RecordToolRefused("hosted_record_values_unreadable", "the values file cannot be read") from error
    try:
        return _strict_object(raw)
    except HostedDeploymentRefused as error:
        raise RecordToolRefused("hosted_record_values_invalid",
                                "the values file is not one strict JSON object") from error


def build(values: dict[str, Any], *, root: Path) -> tuple[dict[str, Any], str]:
    """The canonical version 1 record and its SHA-256, after every gate file and field check."""
    if "execution_release" in values or values.get(VERSION_FIELD, RECORD_VERSION) != RECORD_VERSION:
        raise RecordToolRefused("hosted_record_values_invalid", "this tool builds version 1 only")
    unknown = set(values) - RECORD_FIELDS
    missing = RECORD_FIELDS - set(values) - {VERSION_FIELD}
    if unknown or missing:
        raise RecordToolRefused("hosted_record_values_invalid",
                                "the values file does not hold exactly the version 1 fields")
    verify_gates(values["host_gates"], root.resolve())
    record = {VERSION_FIELD: RECORD_VERSION, **values}
    digest = hashlib.sha256(canonical(record)).hexdigest()
    _parse(record, digest)
    return record, digest


def verify_gates(gates: Any, base: Path) -> None:
    """Each named gate file exists inside the root and its bytes hash to the declared SHA-256."""
    if not isinstance(gates, dict) or set(gates) != set(HOST_GATES):
        raise RecordToolRefused("hosted_record_values_invalid", "the values file does not name the four host gates")
    for name in HOST_GATES:
        item = gates[name]
        if not isinstance(item, dict) or set(item) != GATE_FIELDS:
            raise RecordToolRefused("hosted_record_values_invalid", "a host gate needs exactly its path and hash")
        reference, declared = item["path"], item["sha256"]
        if not isinstance(reference, str) or not isinstance(declared, str):
            raise RecordToolRefused("hosted_record_values_invalid", "a host gate needs exactly its path and hash")
        verify_gate(name, reference, declared, base)


def verify_gate(name: str, reference: str, declared: str, base: Path) -> None:
    if not reference.startswith("docs/qualification/"):
        raise RecordToolRefused("hosted_record_gate_path_invalid",
                                f"the {name} gate path is not under docs/qualification/")
    target = (base / reference).resolve()
    if not target.is_relative_to(base):
        raise RecordToolRefused("hosted_record_gate_path_invalid", f"the {name} gate path leaves the repository")
    if not target.is_file():
        raise RecordToolRefused("hosted_record_gate_unreadable", f"the {name} gate file cannot be read")
    try:
        data = target.read_bytes()
    except OSError as error:
        raise RecordToolRefused("hosted_record_gate_unreadable", f"the {name} gate file cannot be read") from error
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), declared):
        raise RecordToolRefused("hosted_record_gate_hash_mismatch",
                                f"the {name} gate file hash differs from the declared value")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m edge_os_api.core.hosted_record_tool",
        description="Build, verify and hash one hosted deployment version 1 record.")
    parser.add_argument("--values", required=True, type=Path, help="the values file to build the record from")
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="the repository root that gate paths are resolved against (default: current directory)")
    arguments = parser.parse_args(argv)
    try:
        record, digest = build(read_values(arguments.values), root=arguments.root)
    except (RecordToolRefused, HostedDeploymentRefused) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(canonical(record).decode("utf-8"))
    print(f"sha256 {digest}")
    print(f'APPROVED_HOSTED_DEPLOYMENTS = {{"{record["deployment_id"]}": "{digest}"}}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
