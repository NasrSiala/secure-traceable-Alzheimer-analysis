"""T4.2 : provenance et reçus lus sur Fabric, jamais dans la copie SQL."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from saam.cases import CaseNotFound, CaseService
from saam.identity.auth import AuthError
from saam.ledger import LedgerClient, LedgerError, LedgerUnavailable
from saam.ledger.client import UUID_PATTERN

HISTORY_TIMEOUT = 10.0
UNAVAILABLE = "Registre blockchain injoignable — historique indisponible. Réessayer."
LedgerFactory = Callable[[], LedgerClient]


class LedgerArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    docType: Literal["artifact"]
    artifactId: UUID
    caseId: str = Field(pattern="^CASE-" + UUID_PATTERN + "$")
    artifactType: Literal[
        "original",
        "processed",
        "features",
        "prediction",
        "validation",
        "explanation",
        "final_result",
    ]
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    createdAt: str
    txTimestamp: str
    softwareVersion: str = Field(min_length=1, max_length=64)
    modelVersion: str | None = Field(default=None, max_length=64)
    parentArtifactId: UUID | None
    offchainRef: str
    creatorMspId: str = Field(min_length=1)
    creatorId: str = Field(min_length=1)
    creatorAgent: Literal[
        "ingestion",
        "preparation",
        "features",
        "prediction",
        "validation",
        "explanation",
        "finalization",
    ]

    @field_validator("createdAt", "txTimestamp")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        if not value.endswith("Z") or datetime.fromisoformat(
            value
        ).utcoffset() != timedelta(0):
            raise ValueError("Horodatage UTC requis.")
        return value


class HistoryItem(LedgerArtifact):
    # Métadonnée de réponse HTTP ; aucun champ ajouté au schéma on-chain.
    txId: str = Field(pattern="^[0-9a-f]{64}$")


def load_history(
    service: CaseService, case_id: str, factory: LedgerFactory
) -> list[HistoryItem]:
    deadline = time.monotonic() + HISTORY_TIMEOUT

    def remaining() -> float:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise LedgerUnavailable()
        return budget

    # Vérifier le cas avant d'ouvrir le client ; aucun accès Fabric pour un 404.
    case_ref = service.get_case(case_id)["case_ref"]
    result, placed = [], set()
    with factory() as ledger:
        records = ledger.get_case_history(case_ref, timeout=remaining())
        for record in records:
            artifact = LedgerArtifact.model_validate(record)
            if (
                artifact.caseId != case_ref
                or artifact.artifactId in placed
                or (
                    artifact.parentArtifactId is not None
                    and artifact.parentArtifactId not in placed
                )
                or (artifact.artifactType == "original")
                != (artifact.parentArtifactId is None)
                or artifact.offchainRef != "artifact://" + str(artifact.artifactId)
            ):
                raise LedgerUnavailable()
            receipt_record = ledger.get_record(
                str(artifact.artifactId), timeout=remaining()
            )
            confirmed = LedgerArtifact.model_validate(
                {key: value for key, value in receipt_record.items() if key != "txId"}
            )
            if confirmed != artifact:
                raise LedgerUnavailable()
            result.append(
                HistoryItem.model_validate(
                    artifact.model_dump() | {"txId": receipt_record.get("txId")}
                )
            )
            placed.add(artifact.artifactId)
        remaining()
    return result


def register_history(
    app: FastAPI, service: CaseService, factory: LedgerFactory | None
) -> None:
    def default_client() -> LedgerClient:
        return LedgerClient.from_environment("verifier")

    ledger_factory = factory or default_client

    @app.get("/api/v1/cases/{case_id}/history", response_model=list[HistoryItem])
    async def history(case_id: str) -> JSONResponse:
        try:
            # Borne la réponse globale, y compris les lectures des sept reçus.
            # La lecture ferme le pool même si l'attente est annulée.
            async with asyncio.timeout(HISTORY_TIMEOUT):
                rows = await asyncio.to_thread(
                    load_history, service, case_id, ledger_factory
                )
        except CaseNotFound:
            raise AuthError(404, "NOT_FOUND", "Cas introuvable.") from None
        except (LedgerError, OSError, ValueError, TimeoutError):
            raise AuthError(502, "LEDGER_UNAVAILABLE", UNAVAILABLE) from None
        return JSONResponse(
            content=[row.model_dump(mode="json") for row in rows],
            headers={"Cache-Control": "no-store"},
        )
