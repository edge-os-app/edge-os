"""Shared constants for the relay tests. Synthetic: no provider knows these values."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RELAY = REPO / "deploy" / "rpc-relay"

# The path segment plays the QuickNode key.
SENTINEL_KEY = "qnkey0SENTINEL7f3a9c1e5b2d8046aa"
SENTINEL_HOST = "sentinel-wild-dawn.monad-mainnet.quiknode.invalid"
SENTINEL_URL = f"https://{SENTINEL_HOST}/{SENTINEL_KEY}/"
