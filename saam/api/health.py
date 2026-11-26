"""Sondes bornées : base, processus worker, registre et proxy HTTP."""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx
import psycopg
from pydantic import BaseModel

from saam.ledger.health import ledger_available
from saam.registry.health import active_model

ServiceStatus = Literal["ok", "error"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    services: dict[str, ServiceStatus]
    version: str
    model: dict[str, str] | None
    error: ErrorDetail | None = None


class HealthProbe(Protocol):
    async def inspect(self) -> HealthResponse: ...


def worker_available(path: Path, *, now: float | None = None) -> bool:
    try:
        heartbeat = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(heartbeat, dict) or heartbeat.get("status") != "ok":
            return False
        timestamp = heartbeat.get("timestamp")
        if isinstance(timestamp, bool) or not isinstance(timestamp, int | float):
            return False
        age = (time.time() if now is None else now) - timestamp
        return math.isfinite(age) and 0 <= age <= 10
    except (OSError, ValueError):
        return False


def software_version() -> str:
    project = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return str(tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"])


@dataclass(frozen=True)
class SystemProbe:
    database_url: str
    gateway_url: str
    verifier_token: str
    worker_status: Path
    frontend_url: str

    @classmethod
    def from_environment(cls) -> SystemProbe:
        return cls(
            database_url=os.environ.get("DATABASE_URL_API", ""),
            gateway_url=os.environ.get(
                "LEDGER_GATEWAY_URL", "http://ledger-gateway:8080"
            ),
            verifier_token=os.environ.get("AGENT_TOKEN_VERIFIER", ""),
            worker_status=Path(
                os.environ.get("WORKER_STATUS_FILE", "/run/saam/worker.json")
            ),
            frontend_url=os.environ.get("FRONTEND_URL", "http://frontend"),
        )

    def database(self) -> tuple[bool, dict[str, str] | None]:
        if not self.database_url:
            return False, None
        try:
            with psycopg.connect(
                self.database_url,
                connect_timeout=2,
                options="-c statement_timeout=1500",
                autocommit=True,
            ) as connection:
                connection.execute("SELECT 1").fetchone()
                return True, active_model(connection)
        except psycopg.Error:
            return False, None

    async def frontend(self, client: httpx.AsyncClient) -> bool:
        try:
            response = await client.get(self.frontend_url)
            return response.status_code == 301 and response.headers.get(
                "location", ""
            ).startswith("https://")
        except httpx.HTTPError:
            return False

    async def inspect(self) -> HealthResponse:
        async with httpx.AsyncClient(
            timeout=2, follow_redirects=False, trust_env=False
        ) as client:
            database, ledger, frontend = await asyncio.gather(
                asyncio.to_thread(self.database),
                ledger_available(client, self.gateway_url, self.verifier_token),
                self.frontend(client),
            )
        database_ok, model = database
        checks = {
            "api": True,
            "postgres": database_ok,
            "worker": worker_available(self.worker_status),
            "ledger-gateway": ledger,
            "frontend": frontend,
        }
        healthy = all(checks.values())
        services: dict[str, ServiceStatus] = {
            name: "ok" if ready else "error" for name, ready in checks.items()
        }
        return HealthResponse(
            status="ok" if healthy else "degraded",
            services=services,
            version=software_version(),
            model=model,
            error=None
            if healthy
            else ErrorDetail(
                code="UNAVAILABLE",
                message="Service partiellement indisponible.",
                details={},
            ),
        )
