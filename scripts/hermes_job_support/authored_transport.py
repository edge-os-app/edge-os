"""The AUTHORED provider transport: it plays a hand-written provider reply inside the no-network container. Test support.

It satisfies `ProviderTransport` the way a later network transport must: one send per attempt, the host request exactly
as given, a reply bounded by the route. The reply itself comes from the accepted P05 fake provider (`player`), so request
receipts, usage and hang behavior stay those of the accepted job. A script may add one transport fault:

- `lost_reply`: the provider did its work and the reply never arrives (`TransportLost`);
- `oversized_reply`: the reply is larger than the route allows;
- `crash_after_send`: the job process dies after the provider did its work.

It opens no socket and reads no file. It never sees a real credential: tests mount a dummy one.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from provider_transport import HostRequest, TransportLost, TransportReply, TransportRoute

__all__ = ["AuthoredTransport", "FAULTS"]

FAULTS = frozenset({"lost_reply", "oversized_reply", "crash_after_send"})


class AuthoredTransport:
    def __init__(self, route: TransportRoute, player: Callable[[Any], Any], credential: str | None,
                 script: Mapping[str, Any]) -> None:
        fault = script.get("transport_fault")
        if route.kind != "AUTHORED" or (fault is not None and fault not in FAULTS):
            raise ValueError("an authored transport needs an AUTHORED route and a known fault")
        self._route, self._player, self._credential, self._fault = route, player, credential, fault
        self._attempts: set[str] = set()
        self.credential_attached: bool | None = None  # whether the host request carried exactly the host credential

    def send(self, request: HostRequest) -> TransportReply:
        import httpx

        if request.attempt_id in self._attempts or request.route_id != self._route.route_id:
            raise RuntimeError("one send per attempt, on this route only")
        self._attempts.add(request.attempt_id)
        expected = f"Bearer {self._credential}" if self._credential is not None else None
        self.credential_attached = dict(request.headers).get("authorization") == expected
        response = self._player(httpx.Request("POST", request.url, headers=list(request.headers), content=request.body))
        if self._fault == "crash_after_send":
            os._exit(70)  # the provider worked; the job dies before anyone sees its reply
        if self._fault == "lost_reply":
            raise TransportLost("the reply did not arrive")
        body = response.read()
        if self._fault == "oversized_reply":
            body += b" " * self._route.max_reply_bytes
        return TransportReply(response.status_code, body)
