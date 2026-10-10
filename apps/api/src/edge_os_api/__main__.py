"""`python -m edge_os_api`: validate configuration and the schema revision, then serve. Plain failure messages."""

import sys

import uvicorn

from edge_os_api.core.database import SchemaMismatch
from edge_os_api.main import create_app
from edge_os_api.core.settings import ConfigError


def main() -> None:
    host, port = "127.0.0.1", 8000
    args = sys.argv[1:]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    if "--host" in args:
        host = args[args.index("--host") + 1]
    try:
        app = create_app()
    except (ConfigError, SchemaMismatch) as error:
        sys.exit(f"edge-os-api: {error}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
