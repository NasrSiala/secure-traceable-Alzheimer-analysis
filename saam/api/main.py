"""Point d'entrée FastAPI de la pile T1.5."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from saam.api.health import HealthProbe, HealthResponse, SystemProbe


def create_app(probe: HealthProbe | None = None) -> FastAPI:
    app = FastAPI(
        title="SAAMSTIAHF",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    health_probe = probe if probe is not None else SystemProbe.from_environment()

    @app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
    )
    async def health() -> JSONResponse:
        report = await health_probe.inspect()
        return JSONResponse(
            status_code=200 if report.status == "ok" else 503,
            content=report.model_dump(exclude_none=True) | {"model": report.model},
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_app()
