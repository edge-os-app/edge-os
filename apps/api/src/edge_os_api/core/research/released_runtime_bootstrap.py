"""The one operating release a server composes, shared by the API and the worker (#58 R58-RESEARCH-MOUNT-L2).

`main.create_app` (when no runtime is passed) and `investigation_jobs.main` both call `server_research_runtime`, so both
processes hold the same immutable runtime with the same release SHA-256; the existing admission check then refuses a
job whose frozen SHA-256 differs before any effect.

A release is composed only from a code-owned ACTUAL definition in `RELEASE_DEFINITIONS` whose exact SHA-256 is in
`operating_release.APPROVED_RELEASES`. Exactly one such release is registered (the Nansen-only
`actual-moe-nansen-demo-20261018/1`), so the default server composes that one release: no release is read from a
setting, environment value, file or request, and composition reads no credential and opens no socket. Removing the
definition makes the default compose nothing again. See
`docs/qualification/research-provider-composition/NANSEN_ACTUAL_RELEASE.md`.

Credentials come from the process environment: unless a caller injects its own source, an approved release is composed
with the accepted `EnvironmentCredentialSource`, which reads an allowed slot only when a job prepares it. A missing or
blank slot refuses there, before any provider attempt. See
`docs/qualification/research-provider-composition/CREDENTIAL_DELIVERY.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from edge_os_api.core.research import operating_release
from edge_os_api.core.research.environment_credentials import EnvironmentCredentialSource
from edge_os_api.core.research.operating_release import (
    NansenRelease,
    OperatingRelease,
    ReleaseRefused,
    release_sha256,
)
from edge_os_api.core.research.released_source_runtime import (
    CredentialSource,
    NansenHttpFactory,
    ReleasedSourceRuntime,
    open_released_runtime,
)
from edge_os_api.research_history.http_clients import StdlibHttpTransport

# Release id -> its ACTUAL definition. Exactly one approved actual release is registered below: the Nansen-only
# `actual-moe-nansen-demo-20261018/1` whose exact SHA-256 is in `operating_release.APPROVED_RELEASES`. Adding, changing
# or removing one is a reviewed code change together with its `APPROVED_RELEASES` entry.
RELEASE_DEFINITIONS: Mapping[str, OperatingRelease] = {
    "actual-moe-nansen-demo-20261018/1": OperatingRelease(
        release_id="actual-moe-nansen-demo-20261018/1",
        kind="ACTUAL",
        history=None,
        nansen=NansenRelease(
            endpoint="https://api.nansen.ai",
            credential_slot="NANSEN_API_KEY",
            token_address="0xd8e004acba279417c04c0633cb5a21ceca207777",
            token_symbol="MOE",
            window={"start_utc": "2026-10-17T12:00:00Z", "end_utc": "2026-10-18T12:00:00Z"},
            operations=("holders", "flows"),
            holder_query={"label_type": "all_holders", "aggregate_by_entity": False,
                          "order_field": "token_amount", "value_usd_min": None},
            flow_query={"label": "top_100_holders"},
            limits={"max_requests": 2, "max_pages": 1, "max_bytes": 2000000, "max_credits": "6", "per_page": 100},
            deadline_seconds=300,
            compute_seconds=300,
            client_bounds={"connect_timeout_seconds": 10, "max_request_bytes": 16384,
                           "max_response_bytes": 1000000},
        ),
    ),
}


def server_research_runtime(settings: Any, *,
                            credentials: CredentialSource | None = None) -> ReleasedSourceRuntime | None:
    """The server's composed release, or None. Reads no credential and opens no socket. Raises `ReleaseRefused`.

    `credentials` replaces the environment source; it is used as given, never with a fallback."""
    if any(key != release.release_id for key, release in RELEASE_DEFINITIONS.items()):
        raise ReleaseRefused("operating_release_invalid", "a release definition is filed under another id")
    approved = [release for release in RELEASE_DEFINITIONS.values() if release.kind == "ACTUAL"
                and operating_release.APPROVED_RELEASES.get(release.release_id) == release_sha256(release)]
    if not approved:
        return None
    if len(approved) > 1:
        raise ReleaseRefused("operating_release_invalid", "a server composes at most one approved release")
    release = approved[0]
    source = EnvironmentCredentialSource() if credentials is None else credentials
    return open_released_runtime(settings, release, credentials=source,
                                 http_transport=StdlibHttpTransport if release.history is not None else None,
                                 nansen_transport=NansenHttpFactory() if release.nansen is not None else None)
