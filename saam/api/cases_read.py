"""T3.13 : liste, détail et tracé ECG pour les trois rôles authentifiés."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from saam.cases import CaseNotFound, CaseService
from saam.identity.auth import AuthError
from saam.pipeline.logs import list_for_case
from saam.traceability import ArtifactReader, IntegrityError

Status = Literal["en_attente", "en_cours", "termine", "erreur_ancrage", "erreur"]
Decision = Literal["accepte", "revision_requise", "rejete"]
StepStatus = Literal["a_venir", "en_cours", "ancre", "echec", "non_execute"]
STEPS = (
    ("ingestion", "original"),
    ("preparation", "processed"),
    ("features", "features"),
    ("prediction", "prediction"),
    ("validation", "validation"),
    ("explanation", "explanation"),
    ("finalization", "final_result"),
)
RESULTS = ("prediction", "validation", "explanation", "final_result")


class CaseSummary(BaseModel):
    id: str
    case_ref: str
    status: Status
    created_at: datetime
    predicted_class: Literal["NORM", "MI", "STTC", "CD", "HYP"] | None
    confidence: float | None
    decision: Decision | None


class CasePage(BaseModel):
    items: list[CaseSummary]
    total: int
    page: int
    size: int


class ArtifactSummary(BaseModel):
    id: str
    type: str
    parent_artifact_id: str | None
    sha256: str
    offchain_ref: str
    created_by_agent: str
    software_version: str
    model_version: str | None
    anchor_status: Literal["en_attente", "ancre", "echec"]
    anchor_attempts: int
    tx_id: str | None
    anchored_at: datetime | None
    created_at: datetime


class PipelineStep(BaseModel):
    step: str
    artifact_type: str
    status: StepStatus
    artifact_id: str | None
    sha256: str | None
    tx_id: str | None


class CaseDetail(CaseSummary):
    current_step: str | None
    ecg_format: Literal["wfdb", "csv"]
    original_sampling_hz: int
    has_report: bool
    model_id: str | None
    validation_config_id: str | None
    quality_score: float | None
    error_message: str | None
    completed_at: datetime | None
    updated_at: datetime
    artifacts: list[ArtifactSummary]
    steps: list[PipelineStep]
    prediction: dict[str, Any] | None
    validation: dict[str, Any] | None
    explanation: dict[str, Any] | None
    final_result: dict[str, Any] | None


class SignalResponse(BaseModel):
    artifact_id: str
    artifact: Literal["processed"]
    leads: list[str]
    unit: Literal["z-score"]
    source_sampling_hz: int
    sampling_hz: int
    duration_seconds: int
    time_seconds: list[float]
    values: list[list[float]]


def public_ids(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value)
        if key in {"id", "parent_artifact_id", "model_id", "validation_config_id"}
        and value is not None
        else value
        for key, value in row.items()
    }


def pipeline_steps(
    case: dict[str, Any], artifacts: list[dict[str, Any]], logs: list[dict[str, Any]]
) -> list[PipelineStep]:
    by_type = {artifact["type"]: artifact for artifact in artifacts}
    log_status = {log["step"]: log["status"] for log in logs}
    terminal = case["status"] not in {"en_attente", "en_cours"}
    steps = []
    for step, artifact_type in STEPS:
        artifact = by_type.get(artifact_type)
        status: StepStatus = "a_venir"
        if log_status.get(step) == "echec" or (
            artifact and artifact["anchor_status"] == "echec"
        ):
            status = "echec"
        elif artifact and artifact["anchor_status"] == "ancre":
            status = "ancre"
        elif log_status.get(step) == "ignore" or terminal:
            status = "non_execute"
        elif step == case["current_step"] or artifact:
            status = "en_cours"
        steps.append(
            PipelineStep(
                step=step,
                artifact_type=artifact_type,
                status=status,
                artifact_id=str(artifact["id"]) if artifact else None,
                sha256=artifact["sha256"] if artifact else None,
                tx_id=artifact["tx_id"] if artifact else None,
            )
        )
    return steps


def register_case_reads(
    app: FastAPI, service: CaseService, reader: ArtifactReader | None
) -> None:
    app.state.artifact_reader = reader

    def artifact_reader() -> ArtifactReader:
        # Configuration différée : liste et cas en attente fonctionnent sans clé AES.
        return app.state.artifact_reader or ArtifactReader.from_environment()

    @app.get("/api/v1/cases", response_model=CasePage)
    def cases(
        page: int = Query(default=1, ge=1, le=1_000_000),
        size: int = Query(default=20, ge=1, le=50),
        status: Status | None = None,
    ) -> JSONResponse:
        result = service.list_cases(page, size, status)
        result["items"] = [public_ids(row) for row in result["items"]]
        return JSONResponse(
            content=CasePage(**result).model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/v1/cases/{case_id}", response_model=CaseDetail)
    def detail(case_id: str) -> JSONResponse:
        try:
            with service.connect() as db:
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                case = service.get_case(case_id, db=db)
                artifacts = ArtifactReader.list_for_case(db, str(case["id"]))
                logs = list_for_case(service.database_url, str(case["id"]), db=db)
            results: dict[str, Any] = dict.fromkeys(RESULTS)
            for artifact in artifacts:
                kind = artifact["type"]
                if kind not in RESULTS or artifact["anchor_status"] != "ancre":
                    continue
                if kind == "final_result" and case["status"] != "termine":
                    continue
                results[kind] = artifact_reader().read_json(artifact, kind + ".json")
            payload = CaseDetail(
                **public_ids(case),
                artifacts=[ArtifactSummary(**public_ids(row)) for row in artifacts],
                steps=pipeline_steps(case, artifacts, logs),
                **results,
            )
        except CaseNotFound:
            raise AuthError(404, "NOT_FOUND", "Cas introuvable.") from None
        except (IntegrityError, OSError, ValueError, EOFError, RecursionError):
            raise AuthError(
                503, "ARTIFACT_UNAVAILABLE", "Résultat indisponible. Réessayer."
            ) from None
        return JSONResponse(
            content=payload.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/v1/cases/{case_id}/signal", response_model=SignalResponse)
    def signal(
        case_id: str, artifact: Literal["processed"] = "processed"
    ) -> JSONResponse:
        try:
            with service.connect() as db:
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                case = service.get_case(case_id, db=db)
                rows = ArtifactReader.list_for_case(db, str(case["id"]))
            processed = next(
                (
                    row
                    for row in rows
                    if row["type"] == artifact and row["anchor_status"] == "ancre"
                ),
                None,
            )
            if processed is None or "signal.npy" not in processed["files"]:
                raise AuthError(404, "SIGNAL_UNAVAILABLE", "Signal indisponible.")
            payload = SignalResponse(**artifact_reader().signal(processed))
        except CaseNotFound:
            raise AuthError(404, "NOT_FOUND", "Cas introuvable.") from None
        except (IntegrityError, OSError, ValueError, EOFError):
            raise AuthError(
                503, "ARTIFACT_UNAVAILABLE", "Signal indisponible. Réessayer."
            ) from None
        return JSONResponse(
            content=payload.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
