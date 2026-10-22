#!/usr/bin/env python3
"""Print the direct-route calldata pinned by one release file.

This tool reads only the given release JSON. It loads no .env, credential or wallet.
It signs nothing and sends nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from edge_os_api.execution.direct_route_quote_client import DirectRoutePins, build_calldata_hex
from edge_os_api.execution.operating_release import OperatingRelease


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("release", type=Path, help="release JSON file (an optional top-level schema key is ignored)")
    args = parser.parse_args()
    definition = json.loads(args.release.read_text(encoding="utf-8"))
    definition.pop("schema", None)
    release = OperatingRelease(definition)
    content = release.content()
    if content["quote"].get("source") != "DIRECT_V2_PROGRAM":
        raise SystemExit("release is not a DIRECT_V2_PROGRAM source")
    pins = DirectRoutePins.from_release(content)
    print(json.dumps({"to": pins.entrypoint_address, "value": "0",
                      "program_hex": pins.approved_program_hex,
                      "approved_input_raw": pins.approved_input_raw,
                      "approved_min_output_raw": pins.approved_min_output_raw,
                      "calldata": build_calldata_hex(pins)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
