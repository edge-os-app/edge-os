"""The only writer of the AUTHORED Nansen fixture the application replays locally (#58 RESEARCH-PORTS-LOCAL).

Run `uv run python tests/nansen_authored_fixture.py` from `apps/api` to rewrite
`tests/fixtures/nansen_research_authored/nansen_authored_v1.json`.

Every token, address, count and header here is synthetic. The shapes follow the accepted package's authored test
fixtures (`tests/nansen_research/nansen_fixtures.py`, pinned OpenAPI `1.0.0`). No provider response, account or
credential exists. The credit headers are authored so a local run can show a known settlement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nansen_research.nansen_fixtures import (
    SYMBOL,
    TOKEN,
    WINDOW_END,
    WINDOW_START,
    flow_bucket,
    flow_payload,
    holder_payload,
    holder_row,
    hourly_starts,
)

OUTPUT = Path(__file__).parent / "fixtures" / "nansen_research_authored" / "nansen_authored_v1.json"


def headers(request_id: str, credits: str) -> dict[str, str]:
    return {"x-request-id": request_id, "x-nansen-credits-cost": credits, "x-nansen-credits-used": credits,
            "x-nansen-credits-remaining": "975"}


def build() -> dict[str, Any]:
    holders = holder_payload([
        holder_row("0x1000000000000000000000000000000000000001", token_amount="5000000", ownership_percentage="0.25",
                   value_usd=None, address_label="Authored exchange wallet"),
        holder_row("0x1000000000000000000000000000000000000002", token_amount="3000000", ownership_percentage="0.15",
                   value_usd=None, address_label=None),
        holder_row("0x1000000000000000000000000000000000000003", token_amount="1500000", ownership_percentage="0.075",
                   value_usd=None, address_label="Authored contract")])
    buckets = [flow_bucket(start) for start in hourly_starts(24, start_hour=10)]
    flows = flow_payload(buckets)
    return {"schema_version": "edge-os.nansen-authored-fixture/1", "label": "AUTHORED",
            "notice": ("Authored Nansen-shaped replies for local application tests. Not provider data. "
                       f"Token {SYMBOL} {TOKEN}; window {WINDOW_START} to {WINDOW_END}."),
            "tokens": {TOKEN: {
                "holders": {"1": {"status": 200, "headers": headers("authored-holders-1", "5"), "payload": holders}},
                "flows": {"1": {"status": 200, "headers": headers("authored-flows-1", "1"), "payload": flows}}}}}


def write() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    write()
