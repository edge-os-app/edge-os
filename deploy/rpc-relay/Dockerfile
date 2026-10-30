# Edge OS keyless /rpc relay image. Build context: this folder (deploy/rpc-relay, see its .dockerignore).
# The image holds the standard-library relay only: no dependency, no secret and no configuration value is baked in.
# The provider URL (which holds the key) arrives at run time as EDGE_OS_RPC_RELAY_UPSTREAM_URL. See
# docs/qualification/inapp-trade/RPC_RELAY.md.

# The same pinned base as deploy/docker/api.Dockerfile.
ARG PYTHON_IMAGE=python:3.14-slim-trixie@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2

FROM ${PYTHON_IMAGE}
ARG EDGE_OS_SOURCE_COMMIT=unknown
# LOCAL is the default; a production build passes PRODUCTION. The value is an image label only.
ARG EDGE_OS_PROFILE=LOCAL
LABEL org.opencontainers.image.title="edge-os-rpc-relay" \
      org.opencontainers.image.revision="${EDGE_OS_SOURCE_COMMIT}" \
      edge-os.profile="${EDGE_OS_PROFILE}"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 edgeos \
 && useradd --system --uid 10001 --gid edgeos --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin edgeos
COPY rpc_relay.py /app/rpc_relay.py
USER 10001:10001
EXPOSE 8545 8546
CMD ["python", "-I", "/app/rpc_relay.py"]
