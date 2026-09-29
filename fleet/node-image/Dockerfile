# Flower SuperNode with Agent Warden's Python dependencies already in the uv
# cache, so AgentApp runs install from local disk instead of the network.
FROM flwr/supernode:1.39.0

COPY --chown=app:app pyproject.toml /tmp/warm/pyproject.toml
RUN cd /tmp/warm \
    && UV_PROJECT_ENVIRONMENT=/tmp/warm/.venv uv sync \
        --python /python/venv/bin/python \
        --no-install-project \
        --no-install-package flwr \
        --inexact \
    && rm -rf /tmp/warm
