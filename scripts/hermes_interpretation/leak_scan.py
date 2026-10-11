"""Finds a secret value in files. Test support: it proves a dummy credential did not reach saved evidence."""

from __future__ import annotations

import base64
import urllib.parse
from collections.abc import Iterable
from pathlib import Path


def _unaligned_base64(raw: bytes, url_safe: bool) -> list[bytes]:
    """Base64 text of the secret when it sits at an offset of 1 or 2 bytes inside a longer encoded value.

    The first characters of a group depend on the bytes before the secret and the last on the bytes after it, so only the
    characters that the secret alone decides are kept.
    """
    encode = base64.urlsafe_b64encode if url_safe else base64.b64encode
    return [encode(b"\0" * offset + raw).rstrip(b"=")[start:-2] for offset, start in ((1, 2), (2, 3))]


def encodings(secret: str) -> list[bytes]:
    """The forms a secret could take if something wrote it out.

    Plain, upper and lower case, URL-encoded, reversed, hex, base64 (aligned and offset), its Authorization header form,
    and with punctuation or every character written as a JSON \\u escape. A secret that is split, compressed or encrypted
    is NOT covered.
    """
    raw = secret.encode("utf-8")
    escaped_punctuation = "".join(c if c.isalnum() else f"\\u{ord(c):04x}" for c in secret)
    escaped_all = "".join(f"\\u{ord(c):04x}" for c in secret)
    forms = [raw, secret.upper().encode(), secret.lower().encode(), urllib.parse.quote(secret, safe="").encode(), raw[::-1],
             raw.hex().encode(), raw.hex().upper().encode(), base64.b64encode(raw), base64.urlsafe_b64encode(raw),
             base64.b64encode(f"Bearer {secret}".encode()), escaped_punctuation.encode(), escaped_punctuation.upper().encode(),
             escaped_all.encode(), escaped_all.upper().encode(),
             *_unaligned_base64(raw, False), *_unaligned_base64(raw, True)]
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
