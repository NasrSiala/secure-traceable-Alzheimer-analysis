# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

# Base commune du Backend. API, worker et /health seront ajoutés dans T1.5.
FROM python:3.11-slim-bookworm AS backend-base
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY saam ./saam
RUN python -m compileall -q saam

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
USER node
EXPOSE 8080
CMD ["node", "dist/server.js"]

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
