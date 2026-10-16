"""Checks saved Kuru Flow runtime bytecode and compares it with a compiled artifact. Standard library only.

`inspect` verifies a saved runtime fixture against its expected length and SHA256, prints the Solidity metadata tail and
counts how many PUSH instructions push each requested constant. `compare` reports an exact byte match or the first
differing offset between deployed runtime code and a candidate artifact. Neither command normalizes immutables or
metadata; any such normalization must be reported separately from an exact match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

_HEX_FIXTURE = re.compile(r"0x((?:[0-9a-f]{2})+)\n?")
_PUSH1, _PUSH32 = 0x60, 0x7F


def load_runtime(path: Path) -> bytes:
    """Read one runtime fixture: lowercase `0x` hex with an optional single trailing newline."""
    match = _HEX_FIXTURE.fullmatch(path.read_text(encoding="ascii"))
    if match is None:
        raise ValueError(f"{path}: expected lowercase 0x-prefixed even-length hex and at most one trailing newline")
    return bytes.fromhex(match.group(1))


def metadata_tail(code: bytes) -> bytes:
    """Return the CBOR metadata that solc appends, located by the final two-byte length."""
    if len(code) < 2:
        raise ValueError("runtime code is shorter than the two-byte metadata length")
    length = int.from_bytes(code[-2:], "big")
    if length > len(code) - 2:
        raise ValueError(f"metadata length {length} exceeds code size {len(code)}")
    return code[-2 - length : -2]


def push_values(code: bytes) -> Counter[int]:
    """Count the values pushed by PUSH1..PUSH32 in the instruction stream before the metadata tail.

    The walk skips push data, so a byte pattern inside another instruction's data is not counted.
    """
    end = len(code) - 2 - len(metadata_tail(code))
    values: Counter[int] = Counter()
    offset = 0
    while offset < end:
        opcode = code[offset]
        if _PUSH1 <= opcode <= _PUSH32:
            width = opcode - _PUSH1 + 1
            if offset + 1 + width > end:
                raise ValueError(f"PUSH{width} at offset {offset} runs past the instruction stream")
            values[int.from_bytes(code[offset + 1 : offset + 1 + width], "big")] += 1
            offset += 1 + width
        else:
            offset += 1
    return values


def first_difference(deployed: bytes, candidate: bytes) -> int | None:
    """Return the first differing byte offset, or None when both byte strings are identical."""
    for offset, (left, right) in enumerate(zip(deployed, candidate)):
        if left != right:
            return offset
    return None if len(deployed) == len(candidate) else min(len(deployed), len(candidate))


def inspect_fixture(path: Path, sha256: str, length: int, constants: list[str]) -> dict[str, object]:
    """Verify a fixture's identity and report its metadata tail and constant push counts."""
    code = load_runtime(path)
    actual_sha = hashlib.sha256(code).hexdigest()
    if len(code) != length or actual_sha != sha256:
        raise ValueError(f"{path}: expected {length} bytes/{sha256}, got {len(code)} bytes/{actual_sha}")
    pushed = push_values(code)
    return {
        "fixture": str(path),
        "bytes": len(code),
        "sha256": actual_sha,
        "metadata_cbor_hex": metadata_tail(code).hex(),
        "constant_push_counts": {value: pushed[int(value, 16)] for value in constants},
    }


def compare_runtime(deployed_path: Path, candidate_path: Path) -> dict[str, object]:
    """Compare deployed runtime code with a candidate artifact byte for byte."""
    deployed, candidate = load_runtime(deployed_path), load_runtime(candidate_path)
    offset = first_difference(deployed, candidate)
    return {
        "result": "EXACT_MATCH" if offset is None else "MISMATCH",
        "deployed": {"bytes": len(deployed), "sha256": hashlib.sha256(deployed).hexdigest()},
        "candidate": {"bytes": len(candidate), "sha256": hashlib.sha256(candidate).hexdigest()},
        "first_difference_offset": offset,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser("inspect", help="verify a fixture and count constant pushes")
    inspect_cmd.add_argument("fixture", type=Path)
    inspect_cmd.add_argument("--sha256", required=True)
    inspect_cmd.add_argument("--length", type=int, required=True)
    inspect_cmd.add_argument("--constant", action="append", default=[], help="hex value without 0x; repeatable")
    compare_cmd = commands.add_parser("compare", help="exact byte comparison; exit 1 on mismatch")
    compare_cmd.add_argument("deployed", type=Path)
    compare_cmd.add_argument("candidate", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            for value in args.constant:
                if re.fullmatch(r"[0-9a-f]+", value) is None:
                    raise ValueError(f"--constant {value!r}: expected lowercase hex without 0x")
            report = inspect_fixture(args.fixture, args.sha256, args.length, args.constant)
        else:
            report = compare_runtime(args.deployed, args.candidate)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 1 if report.get("result") == "MISMATCH" else 0


if __name__ == "__main__":
    sys.exit(main())
