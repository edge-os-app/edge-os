"""Finds a secret value in files. Test support: it proves a dummy credential did not reach saved evidence."""

from __future__ import annotations

import base64
import urllib.parse
from collections.abc import Iterable
from pathlib import Path


def encodings(secret: str) -> list[bytes]:
    """The forms a secret could take if something wrote it out: plain, URL-encoded, base64 and its header form."""
    raw = secret.encode("utf-8")
    forms = [raw, urllib.parse.quote(secret, safe="").encode(), base64.b64encode(raw), base64.urlsafe_b64encode(raw),
             base64.b64encode(f"Bearer {secret}".encode()), raw[::-1]]
    return [form for form in dict.fromkeys(forms) if form]


def find_leaks(root: Path, secret: str, exclude: Iterable[Path] = ()) -> list[str]:
    """Paths under `root` whose bytes contain the secret in any known form. `exclude` lists the source files."""
    skipped = {path.resolve() for path in exclude}
    forms = encodings(secret)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in skipped:
            continue
        data = path.read_bytes()
        if any(form in data for form in forms):
            found.append(str(path.relative_to(root)))
    return found
