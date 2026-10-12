"""Live injected HTTP clients for the accepted P07 source seams.

This subpackage supplies the two *actual* injected clients the accepted P07
transport and corroboration expect:

- ``HttpEnvioQueryClient`` implements ``EnvioQueryClient.query(HistoryRequest)`` for
  ``EnvioHypersyncSource``.
- ``HttpQuickNodeRpcClient`` implements ``QuickNodeRpcClient.call(method, params)``
  for ``read_chain_id`` and ``corroborate_records``.

Both are library classes. They perform no I/O at import or construction, read no
environment variable or credential file, and ship no default endpoint or token. A
caller injects an explicit endpoint, credential and transport, and the finite
``ClientBounds``. The accepted package's top-level modules remain offline; this
subpackage is the one place a live transport may be wired, and only when a caller
explicitly imports and injects it. Import from here explicitly; nothing is added to
the accepted top-level package namespace.
"""

from __future__ import annotations

from edge_os_api.research_history.http_clients.client_config import (
    ClientBounds,
    ClientConfigError,
    HttpProviderError,
    endpoint_has_path,
    endpoint_path,
    safe_endpoint,
    validate_endpoint,
)
from edge_os_api.research_history.http_clients.envio_query_client import (
    BLOCK_FIELD_SELECTION,
    ENVIO_QUERY_PATH,
    LOG_FIELD_SELECTION,
    HttpEnvioQueryClient,
)
from edge_os_api.research_history.http_clients.http_transport import (
    HttpResponse,
    HttpTransport,
    StdlibHttpTransport,
)
from edge_os_api.research_history.http_clients.quicknode_rpc_client import (
    READ_ONLY_METHODS,
    HttpQuickNodeRpcClient,
)

__all__ = [
    "BLOCK_FIELD_SELECTION",
    "ClientBounds",
    "ClientConfigError",
    "ENVIO_QUERY_PATH",
    "HttpEnvioQueryClient",
    "HttpProviderError",
    "HttpQuickNodeRpcClient",
    "HttpResponse",
    "HttpTransport",
    "LOG_FIELD_SELECTION",
    "READ_ONLY_METHODS",
    "StdlibHttpTransport",
    "endpoint_has_path",
    "endpoint_path",
    "safe_endpoint",
    "validate_endpoint",
]
