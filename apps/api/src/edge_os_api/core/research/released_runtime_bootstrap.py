"""The one operating release a server composes, shared by the API and the worker (#58 R58-RESEARCH-MOUNT-L2).

`main.create_app` (when no runtime is passed) and `investigation_jobs.main` both call `server_research_runtime`, so both
processes hold the same immutable runtime with the same release SHA-256; the existing admission check then refuses a
job whose frozen SHA-256 differs before any effect.

A release is composed only from a code-owned ACTUAL definition in `RELEASE_DEFINITIONS` whose exact SHA-256 is in
`operating_release.APPROVED_RELEASES`. Both are empty, so the default server composes nothing: no release, no
credential read, no socket. No setting, environment value, file or request can add a definition. Credential delivery is
a recorded `REQUIRED_DECISION`: until a credential source is composed, an approved release refuses startup. See
`docs/qualification/research-provider-composition/CONTRACT.md` section 12.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from edge_os_api.core.research import operating_release
from edge_os_api.core.research.operating_release import OperatingRelease, ReleaseRefused, release_sha256
from edge_os_api.core.research.released_source_runtime import (
    CredentialSource,
    NansenHttpFactory,
    ReleasedSourceRuntime,
    open_released_runtime,
)
from edge_os_api.research_history.http_clients import StdlibHttpTransport

# Release id -> its ACTUAL definition. Empty: every actual value is still a REQUIRED_DECISION. Adding one is a reviewed
# code change together with its `APPROVED_RELEASES` entry.
RELEASE_DEFINITIONS: Mapping[str, OperatingRelease] = {}


def server_research_runtime(settings: Any, *,
                            credentials: CredentialSource | None = None) -> ReleasedSourceRuntime | None:
    """The server's composed release, or None. Reads no credential and opens no socket. Raises `ReleaseRefused`."""
    if any(key != release.release_id for key, release in RELEASE_DEFINITIONS.items()):
        raise ReleaseRefused("operating_release_invalid", "a release definition is filed under another id")
    approved = [release for release in RELEASE_DEFINITIONS.values() if release.kind == "ACTUAL"
                and operating_release.APPROVED_RELEASES.get(release.release_id) == release_sha256(release)]
    if not approved:
        return None
    if len(approved) > 1:
        raise ReleaseRefused("operating_release_invalid", "a server composes at most one approved release")
    if credentials is None:
        raise ReleaseRefused("operating_release_credential_unavailable",
                             "no credential source is composed for the approved release; nothing was read or sent")
    release = approved[0]
    return open_released_runtime(settings, release, credentials=credentials,
                                 http_transport=StdlibHttpTransport if release.history is not None else None,
                                 nansen_transport=NansenHttpFactory() if release.nansen is not None else None)
