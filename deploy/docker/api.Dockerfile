# Edge OS API image for the LOCAL Docker rehearsal. Build context: the repository root (see .dockerignore).
# One image serves the API, the explicit migration step, the research worker, the execution worker, the recurring
# producer and the loopback public entry. Each Compose service picks its own command; nothing migrates on start.
# Dependencies come only from apps/api/uv.lock (frozen, no dev group). No secret or configuration value is baked in.

ARG PYTHON_IMAGE=python:3.14-slim-trixie@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2

FROM ${PYTHON_IMAGE} AS dependencies
ENV UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/edge-os/venv
# Same installer and version as the accepted Hermes qualification image. It stays in this build stage only.
RUN python -m pip install --no-cache-dir uv==0.12.16
WORKDIR /build
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3.14

FROM ${PYTHON_IMAGE} AS runtime
ARG EDGE_OS_SOURCE_COMMIT=unknown
LABEL org.opencontainers.image.title="edge-os-api" \
      org.opencontainers.image.revision="${EDGE_OS_SOURCE_COMMIT}" \
      edge-os.profile="LOCAL"
ENV PATH=/opt/edge-os/venv/bin:${PATH} \
    PYTHONPATH=/app/apps/api/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 edgeos \
 && useradd --system --uid 10001 --gid edgeos --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin edgeos \
 && install -d -o edgeos -g edgeos -m 0750 /var/lib/edge-os/evidence
COPY --from=dependencies /opt/edge-os/venv /opt/edge-os/venv
# The application derives its repository root from module paths (parents[3] and parents[5]), so the runtime assets
# keep their repository layout under /app. A package with only Python source fails to start (P07 engine, contracts).
COPY apps/api/alembic.ini apps/api/pyproject.toml /app/apps/api/
COPY apps/api/src /app/apps/api/src
COPY apps/api/migrations /app/apps/api/migrations
COPY apps/api/tests/fixtures /app/apps/api/tests/fixtures
COPY docs/contracts /app/docs/contracts
COPY docs/qualification/p07 /app/docs/qualification/p07
COPY docs/implementation/EFFECT_COMPARISON_PROFILE.md docs/implementation/SPOT_REPLAY_RUNTIME_PROFILE.md /app/docs/implementation/
COPY scripts/hermes_interpretation /app/scripts/hermes_interpretation
COPY scripts/hermes_job_support /app/scripts/hermes_job_support
COPY deploy/local/public_entry.py deploy/local/http_probe.py /app/deploy/local/
WORKDIR /app/apps/api
USER 10001:10001
CMD ["python", "-m", "edge_os_api", "--host", "0.0.0.0", "--port", "8000"]
