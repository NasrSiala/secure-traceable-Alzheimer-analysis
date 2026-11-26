# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

# Base commune des deux processus Python.
FROM python:3.11-slim-bookworm AS backend-base
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY saam ./saam
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY scripts/seed.py ./scripts/seed.py
RUN python -m compileall -q saam
RUN groupadd --gid 1000 saam && useradd --uid 1000 --gid saam --no-create-home saam \
    && mkdir -p /run/saam /data/artifacts /data/uploads \
    && chown saam:saam /run/saam /data/artifacts /data/uploads
USER saam

FROM backend-base AS api
COPY scripts/purge_case.py ./scripts/purge_case.py
COPY scripts/registry.py ./scripts/registry.py
EXPOSE 8000
CMD ["uvicorn", "saam.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM backend-base AS worker
COPY scripts/tamper.py ./scripts/tamper.py
CMD ["python", "-m", "saam.pipeline.worker"]

FROM node:20.20.2-bookworm-slim AS gateway-build
WORKDIR /app
COPY ledger-gateway/package.json ledger-gateway/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts --no-audit --no-fund
COPY ledger-gateway/src ./src
COPY ledger-gateway/tsconfig.json ./
RUN npm run build

FROM node:20.20.2-bookworm-slim AS ledger-gateway
ENV NODE_ENV=production
ENV GATEWAY_HOST=0.0.0.0
WORKDIR /app
COPY ledger-gateway/package.json ledger-gateway/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY --from=gateway-build /app/dist ./dist
COPY deploy/check-gateway.cjs ./check-gateway.cjs
COPY deploy/start-gateway.sh ./start-gateway.sh
USER node
EXPOSE 8080
ENTRYPOINT ["sh", "/app/start-gateway.sh"]

FROM node:20.20.2-bookworm-slim AS chaincode-build
WORKDIR /app
COPY chaincode/provenance/package.json chaincode/provenance/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts --no-audit --no-fund
COPY chaincode/provenance/src ./src
COPY chaincode/provenance/tsconfig.json ./
RUN npm run build

FROM node:20.20.2-bookworm-slim AS chaincode
ENV NODE_ENV=production
WORKDIR /app
COPY chaincode/provenance/package.json chaincode/provenance/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY --from=chaincode-build /app/dist ./dist
USER node
EXPOSE 9999
CMD ["npm", "start"]

FROM nginx:stable-bookworm@sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609 AS frontend
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY frontend/ /srv/frontend/
