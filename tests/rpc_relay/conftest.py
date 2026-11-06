"""RPC relay tests. Fakes only: no provider, key, network or Docker daemon is used.

The upstream URL is a synthetic sentinel (relay_support.py); the HTTP-layer tests bind the relay to 127.0.0.1 with a
fake upstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in (HERE.parents[1] / "deploy" / "rpc-relay", HERE):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
