"""Contrat public de santé et détection des services indisponibles."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import psycopg
import pytest

from saam.api.health import (
    ErrorDetail,
    HealthProbe,
    HealthResponse,
    SystemProbe,
    worker_available,
)
from saam.api.main import create_app
from saam.ledger.health import PROBE_ARTIFACT_ID, ledger_available

SERVICES = ("api", "postgres", "worker", "ledger-gateway", "frontend")


class FixedProbe:
    def __init__(self, failed: str | None = None) -> None:
        self.failed = failed

    async def inspect(self) -> HealthResponse:
        return HealthResponse(
            status="ok" if self.failed is None else "degraded",
            services={
                name: "error" if name == self.failed else "ok" for name in SERVICES
            },
            version="0.1.0",
            model=None,
            error=None
            if self.failed is None
            else ErrorDetail(
                code="UNAVAILABLE",
                message="Service partiellement indisponible.",
                details={},
            ),
        )


def get_health(probe: HealthProbe) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(probe))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api"
        ) as client:
            return await client.get("/api/v1/health")

    return asyncio.run(request())


def test_public_health_includes_five_services_and_versions() -> None:
    response = get_health(FixedProbe())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "ok",
        "services": {name: "ok" for name in SERVICES},
        "version": "0.1.0",
        "model": None,
    }


@pytest.mark.parametrize("service", SERVICES[1:])
def test_failed_dependency_returns_503_and_names_the_service(service: str) -> None:
    response = get_health(FixedProbe(service))
    assert response.status_code == 503
    assert response.json()["services"][service] == "error"
    assert response.json()["status"] == "degraded"
    assert response.json()["error"] == {
        "code": "UNAVAILABLE",
        "message": "Service partiellement indisponible.",
        "details": {},
    }


def test_openapi_documents_both_health_results() -> None:
    schema = create_app(FixedProbe()).openapi()
    responses = schema["paths"]["/api/v1/health"]["get"]["responses"]
    assert {"200", "503"} <= responses.keys()
    assert "HealthResponse" in schema["components"]["schemas"]


@pytest.mark.parametrize(
    "heartbeat,expected",
    [
        ({"status": "ok", "timestamp": 995}, True),
        ({"status": "ok", "timestamp": 989}, False),
        ({"status": "ok", "timestamp": 1001}, False),
        ({"status": "error", "timestamp": 995}, False),
        ({"status": "ok", "timestamp": True}, False),
        ({"status": "ok", "timestamp": "995"}, False),
        ({"status": "ok", "timestamp": float("nan")}, False),
        ({"status": "ok"}, False),
        ([], False),
    ],
)
def test_worker_health_requires_a_recent_valid_heartbeat(
    tmp_path: Path, heartbeat: object, expected: bool
) -> None:
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(heartbeat), encoding="utf-8")
    assert worker_available(path, now=1000) is expected


def test_missing_or_incomplete_worker_status_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "worker.json"
    assert worker_available(path) is False
    path.write_text('{"status":', encoding="utf-8")
    assert worker_available(path) is False


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (
            404,
            {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "artifactId is not on the ledger",
                    "details": {},
                }
            },
            True,
        ),
        (200, {"docType": "ARTIFACT", "artifactId": PROBE_ARTIFACT_ID}, True),
        (
            404,
            {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "route inconnue",
                    "details": {},
                }
            },
            False,
        ),
        (401, {"error": {"code": "UNAUTHORIZED"}}, False),
        (502, {"error": {"code": "UNAVAILABLE"}}, False),
        (200, {"status": "ok"}, False),
        (200, [], False),
    ],
)
def test_gateway_probe_requires_a_real_chaincode_answer(
    status: int, body: object, expected: bool
) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["x-agent-token"] == "test-verifier-token"
        assert request.url.path == f"/ledger/artifacts/{PROBE_ARTIFACT_ID}"
        return httpx.Response(status, json=body)

    async def run() -> bool:
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            return await ledger_available(
                client, "http://gateway", "test-verifier-token"
            )

    assert asyncio.run(run()) is expected


def test_gateway_connection_failure_is_unhealthy() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-token must not be exposed", request=request)

    async def run() -> bool:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unavailable)
        ) as client:
            return await ledger_available(
                client, "http://gateway", "test-verifier-token"
            )

    assert asyncio.run(run()) is False


def test_database_connection_failure_does_not_expose_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise psycopg.OperationalError("password=private-password")

    monkeypatch.setattr(psycopg, "connect", unavailable)
    probe = SystemProbe(
        "postgresql://private-password",
        "http://gateway",
        "token",
        tmp_path,
        "http://frontend",
    )
    assert probe.database() == (False, None)
