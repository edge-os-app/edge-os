"""Fixed policy for the adopted edge-os.delayed-history-replay/1 timing profile.

A decision for a source bucket happens 300 seconds after that bucket ends. An order fills only
against the next bucket's historical close at that bucket's own delayed decision time. The fill
is a hypothetical stale close, never an executable quote.
"""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType

PROFILE_VERSION = "edge-os.delayed-history-replay/1"
POLICY = MappingProxyType({
    "schema_version": PROFILE_VERSION,
    "decision_delay_seconds": 300,
    "fill_rule": "NEXT_BUCKET_DELAYED_CLOSE",
    "fill_label": "Hypothetical stale historical close",
})
DECISION_DELAY = timedelta(seconds=POLICY["decision_delay_seconds"])
