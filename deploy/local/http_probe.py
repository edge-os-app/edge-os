"""Container health probe: exit 0 only when the URL answers HTTP 200. Prints the status or reason code only."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def probe(url: str, timeout: float = 4.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - container-local URL
            return 0 if response.status == 200 else 1
    except urllib.error.HTTPError as error:
        try:
            reason = json.loads(error.read() or b"{}").get("reason", "")
        except ValueError:
            reason = ""
        print(f"HTTP {error.code} {reason}".strip(), file=sys.stderr)
    except OSError as error:
        print(type(error).__name__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: http_probe.py URL")
    sys.exit(probe(sys.argv[1]))
