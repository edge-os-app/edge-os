"""LOCAL Docker rehearsal guards. Run from apps/api: `.venv/bin/python -m pytest ../../tests/deployment_rehearsal`."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for folder in (REPO / "deploy" / "local", REPO / "scripts" / "deployment_rehearsal"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
