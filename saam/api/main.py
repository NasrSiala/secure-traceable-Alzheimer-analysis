"""Point d'entrée FastAPI de la pile T1.5."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from saam.api.auth import register_auth
from saam.api.authz import AuthorizedRoute, assert_route_policies
from saam.api.cases import register_cases
from saam.api.cases_read import register_case_reads
from saam.api.health import HealthProbe, HealthResponse, SystemProbe
from saam.api.history import LedgerFactory, register_history
from saam.cases import CaseService
from saam.identity.auth import IdentityService
from saam.traceability import ArtifactReader, UploadStaging


def create_app(
    probe: HealthProbe | None = None,
    identity: IdentityService | None = None,
    cases: CaseService | None = None,
    uploads: UploadStaging | None = None,
    artifact_reader: ArtifactReader | None = None,
    ledger_factory: LedgerFactory | None = None,
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
    register_cases(app, cases or CaseService(app.state.identity.database_url), uploads)
    register_case_reads(app, app.state.cases, artifact_reader)
    register_history(app, app.state.cases, ledger_factory)
    assert_route_policies(app)
    return app


app = create_app()
