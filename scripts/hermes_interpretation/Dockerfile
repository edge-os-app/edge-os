FROM python:3.14-slim-trixie@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2

ENV UV_NO_CACHE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/hermes

RUN python -m pip install --no-cache-dir uv==0.12.16
COPY hermes-agent/ /opt/hermes/
WORKDIR /opt/hermes
RUN uv sync --frozen --no-dev --no-install-project --python 3.14 \
 && .venv/bin/python -c 'from run_agent import AIAgent; print("PINNED_HERMES_IMPORT_OK")'

COPY hermes_turn_job.py /opt/p05/hermes_turn_job.py
ENTRYPOINT ["/opt/hermes/.venv/bin/python", "-B", "/opt/p05/hermes_turn_job.py"]
