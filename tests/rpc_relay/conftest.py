"""RPC relay tests. Fakes only: no provider, key, network or Docker daemon is used.

The upstream URL is a synthetic sentinel; the HTTP-layer tests bind the relay to 127.0.0.1 with a fake upstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RELAY = REPO / "deploy" / "rpc-relay"
if str(RELAY) not in sys.path:
    sys.path.insert(0, str(RELAY))

# Synthetic: no provider knows these. The path segment plays the QuickNode key.
SENTINEL_KEY = "qnkey0SENTINEL7f3a9c1e5b2d8046aa"
SENTINEL_HOST = "sentinel-wild-dawn.monad-mainnet.quiknode.invalid"
SENTINEL_URL = f"https://{SENTINEL_HOST}/{SENTINEL_KEY}/"
