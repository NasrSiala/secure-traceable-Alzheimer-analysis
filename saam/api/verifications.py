"""Routes IF-01 de vérification et de lecture de l'historique."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, Query, Response
from pydantic import BaseModel, field_validator

from saam.api.auth import current_user
from saam.api.history import LedgerFactory
from saam.cases import CaseNotFound, CaseService
from saam.identity.auth import AuthError, IdentityService, User
from saam.ledger import LedgerClient
from saam.traceability import ArtifactReader
from saam.verification import CaseVerifier, IntegrityStatus, VerificationHistory

PATH = "/api/v1/cases/{case_id}/verifications"


class VerificationItemResponse(BaseModel):
    artifact_id: UUID
    artifact_type: str
    status: IntegrityStatus
    expected_sha256: str | None
    computed_sha256: str | None
    detail: str | None


class VerificationResponse(BaseModel):
    id: UUID
    case_id: UUID
    requested_by: UUID
    requested_by_name: str
    ledger_reachable: bool
    count_valide: int
    count_modifie: int
    count_manquant: int
    count_non_verifiable: int
    started_at: datetime
    completed_at: datetime
    items: list[VerificationItemResponse]

    @field_validator("started_at", "completed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class VerificationPage(BaseModel):
    items: list[VerificationResponse]
    page: int
    size: int
    total: int


def register_verifications(
    app: FastAPI,
    cases: CaseService,
    identity: IdentityService,
    reader: ArtifactReader | None,
    ledger_factory: LedgerFactory | None,
) -> None:
    history = VerificationHistory(cases)

    @app.post(PATH, status_code=201, response_model=VerificationResponse)
    def create(
        case_id: str,
        response: Response,
        user: Annotated[User, Depends(current_user)],
    ) -> VerificationResponse:
        try:
            case = cases.get_case(case_id)
            started_at = datetime.now(UTC)
            artifacts = reader or ArtifactReader.from_environment()
            with (ledger_factory or LedgerClient.from_environment)() as ledger:
                reachable, items = CaseVerifier(cases, artifacts, ledger).inspect_case(
                    str(case["id"])
                )
            row = history.record(str(case["id"]), user.id, started_at, reachable, items)
        except CaseNotFound:
            raise AuthError(404, "NOT_FOUND", "Cas introuvable.") from None
        except (OSError, ValueError, psycopg.Error):
            raise AuthError(
                503, "VERIFICATION_UNAVAILABLE", "La vérification a échoué. Réessayer."
            ) from None
        response.headers["Cache-Control"] = "no-store"
        return VerificationResponse.model_validate(
            row | {"requested_by_name": user.display_name}
        )

    @app.get(PATH, response_model=VerificationPage)
    def list_verifications(
        case_id: str,
        response: Response,
        page: int = Query(default=1, ge=1, le=1_000_000),
        size: int = Query(default=20, ge=1, le=50),
    ) -> VerificationPage:
        try:
            result = history.list_for_case(case_id, page, size)
            names = identity.display_names(
                {str(row["requested_by"]) for row in result["items"]}
            )
        except CaseNotFound:
            raise AuthError(404, "NOT_FOUND", "Cas introuvable.") from None
        response.headers["Cache-Control"] = "no-store"
        for row in result["items"]:
            row["requested_by_name"] = names.get(str(row["requested_by"]), "")
        return VerificationPage.model_validate(result)
