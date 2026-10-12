"""The job support package stays honest: its pinned identities match the code and its documents claim nothing live."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from job_identities import compute

PACKAGE = Path(__file__).resolve().parents[2] / "docs" / "qualification" / "hermes-job-support"
SENTINEL = "sk-test-DUMMY-SENTINEL-9f3a71c2e8b54d06"


def test_the_committed_identities_equal_the_ones_computed_from_the_code() -> None:
    assert compute() == json.loads((PACKAGE / "JOB_IDENTITIES.json").read_text())  # regenerate with job_identities.py


@pytest.mark.parametrize("name", ["README.md", "ACTUAL_QUALIFICATION_PACKET.md"])
def test_each_document_labels_the_actual_path_as_not_run_and_holds_no_credential(name: str) -> None:
    text = (PACKAGE / name).read_text()

    assert "NOT_RUN" in text and re.search(r"no live request", text, re.IGNORECASE)
    assert SENTINEL not in text and not re.search(r"sk-[A-Za-z0-9]{2,}-[A-Za-z0-9]{16,}", text)
