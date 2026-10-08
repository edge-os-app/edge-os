"""The supplied P43 design inputs stay byte-identical to the identities recorded in docs/design/p43/README.md."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
P43 = REPO / "docs" / "design" / "p43"


def test_supplied_files_match_recorded_hashes():
    readme = (P43 / "README.md").read_text()
    recorded = dict(re.findall(r"\| `(r9/[^`]+)` \| `([0-9a-f]{64})` \|", readme))
    assert len(recorded) == 5, recorded
    for relative, expected in recorded.items():
        actual = hashlib.sha256((P43 / relative).read_bytes()).hexdigest()
        assert actual == expected, f"{relative} differs from the supplied identity"
