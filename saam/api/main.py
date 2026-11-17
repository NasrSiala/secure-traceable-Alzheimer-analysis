"""Point d'entrée FastAPI de la pile T1.5."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from saam.api.auth import register_auth
from saam.api.authz import AuthorizedRoute, assert_route_policies
from saam.api.health import HealthProbe, HealthResponse, SystemProbe
from saam.identity.auth import IdentityService


def create_app(
    probe: HealthProbe | None = None, identity: IdentityService | None = None
) -> FastAPI:
    app = FastAPI(
        title="SAAMSTIAHF",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.router.route_class = AuthorizedRoute
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

    register_auth(
        app, identity if identity is not None else IdentityService.from_environment()
    )
    assert_route_policies(app)
    return app


app = create_app()
