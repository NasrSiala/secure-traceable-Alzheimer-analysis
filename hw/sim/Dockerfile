FROM ghcr.io/astral-sh/uv:0.13.8 AS uv
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates ghdl make && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_PYTHON_INSTALL_DIR=/opt/python
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /workspace
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --python 3.11
COPY saam ./saam
COPY hw/sim ./hw/sim
COPY hw/rtl ./hw/rtl
CMD ["make", "-C", "hw/sim"]
