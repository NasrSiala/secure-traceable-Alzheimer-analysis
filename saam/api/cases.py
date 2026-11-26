"""POST /cases : multipart borné, validations S-03, transaction cas/job/audit."""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from saam.api.auth import current_user, error_response
from saam.audit.events import case_created
from saam.cases import CaseNotFound, CaseRateLimited, CaseService
from saam.identity.auth import AuthError, User
from saam.pipeline.logs import list_for_case
from saam.registry import active_refs
from saam.traceability import UploadStaging, upload_text

LIMIT = 20 * 1024 * 1024
LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
FORMATS = "Formats acceptés : .hea + .dat, .csv ; rapport : .txt."


@dataclass
class UploadError(Exception):
    message: str
    field: str = "ecg_files"


@dataclass(frozen=True)
class ValidatedUpload:
    files: dict[str, tuple[str, bytes]]
    ecg_format: str
    sampling_hz: int
    has_report: bool

    def summary(self) -> dict[str, Any]:
        return {
            "ecg_format": self.ecg_format,
            "sampling_hz": self.sampling_hz,
            "has_report": self.has_report,
        }


class CreatedCase(BaseModel):
    id: str
    case_ref: str
    status: Literal["en_attente"]


def parse_upload(content_type: str, body: bytes) -> ValidatedUpload:
    if "\r" in content_type or "\n" in content_type or len(content_type) > 1024:
        raise UploadError(FORMATS)
    try:
        message = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode(
                "ascii"
            )
            + body
        )
    except (ValueError, UnicodeError):
        raise UploadError(FORMATS) from None
    if (
        message.get_content_type() != "multipart/form-data"
        or not message.is_multipart()
        or message.defects
    ):
        raise UploadError(FORMATS)
    ecg, fields, reports = [], {}, []
    parts = list(message.iter_parts())
    if len(parts) > 5:
        raise UploadError(FORMATS)
    for part in parts:
        if part.is_multipart() or part.defects:
            raise UploadError(FORMATS)
        name = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True)
        if not isinstance(data, bytes) or part.get_content_disposition() != "form-data":
            raise UploadError(FORMATS)
        filename = part.get_filename()
        if name in {"ecg_files", "ecg_files[]"} and filename:
            ecg.append((PurePosixPath(filename.replace("\\", "/")).name, data))
        elif name == "report_file" and filename:
            reports.append((filename, data))
        elif (
            name in {"report_text", "csv_sampling_rate"}
            and not filename
            and name not in fields
        ):
            try:
                fields[name] = data.decode("utf-8")
            except UnicodeError:
                raise UploadError(FORMATS) from None
        else:
            raise UploadError("Champ de téléversement invalide.")
    if not ecg:
        raise UploadError("Champ obligatoire.")
    if sum(len(data) for _, data in ecg) > LIMIT:
        raise UploadError("Taille maximale : 20 Mo.")
    files: dict[str, tuple[str, bytes]] = {}
    if len(ecg) == 1 and PurePosixPath(ecg[0][0]).suffix.lower() == ".csv":
        try:
            sampling = int(fields.get("csv_sampling_rate", ""))
            if not 50 <= sampling <= 10000:
                raise ValueError
        except ValueError:
            raise UploadError(
                "Fréquence entre 50 et 10 000 Hz.", "csv_sampling_rate"
            ) from None
        try:
            rows = csv.reader(io.StringIO(ecg[0][1].decode("utf-8-sig"), newline=""))
            if next(rows, []) != LEADS:
                raise ValueError
            count = 0
            for row in rows:
                if len(row) != 12:
                    raise ValueError
                for value in row:
                    float(value)
                count += 1
        except (ValueError, UnicodeError, csv.Error):
            raise UploadError(
                "Le CSV doit contenir les 12 dérivations (I … V6)."
            ) from None
        if count < sampling * 10:
            raise UploadError("L'enregistrement doit durer au moins 10 secondes.")
        files["ecg.csv"] = ("text/csv", ecg[0][1])
        ecg_format = "csv"
    else:
        grouped = {
            PurePosixPath(name).suffix.lower(): (name, data) for name, data in ecg
        }
        if len(ecg) != 2 or set(grouped) != {".hea", ".dat"}:
            if set(grouped) <= {".hea", ".dat"}:
                raise UploadError(
                    "Fournissez le fichier .hea et le fichier .dat d'un même enregistrement."
                )
            raise UploadError(FORMATS)
        if (
            PurePosixPath(grouped[".hea"][0]).stem
            != PurePosixPath(grouped[".dat"][0]).stem
        ):
            raise UploadError(
                "Fournissez le fichier .hea et le fichier .dat d'un même enregistrement."
            )
        try:
            lines = grouped[".hea"][1].decode("utf-8").splitlines()
            header = lines[0].split()
            frequency = float(header[2].split("/")[0].split("(")[0])
            sampling = int(frequency)
            if (
                int(header[1]) != 12
                or len(lines) < 13
                or sampling != frequency
                or not 50 <= sampling <= 10000
            ):
                raise ValueError
            samples = int(header[3])
            header[0] = "ecg"
            lines[0] = " ".join(header)
            for index in range(1, 13):
                signal = lines[index].split()
                if len(signal) < 2:
                    raise ValueError
                signal[0] = "ecg.dat"
                lines[index] = " ".join(signal)
        except (ValueError, IndexError, UnicodeError, OverflowError):
            raise UploadError(FORMATS) from None
        if samples < sampling * 10:
            raise UploadError("L'enregistrement doit durer au moins 10 secondes.")
        if not grouped[".dat"][1]:
            raise UploadError(FORMATS)
        files["ecg.hea"] = ("text/plain", upload_text("\n".join(lines) + "\n"))
        files["ecg.dat"] = ("application/octet-stream", grouped[".dat"][1])
        ecg_format = "wfdb"
    if len(reports) > 1 or (reports and "report_text" in fields):
        raise UploadError("Choisissez un fichier rapport ou un texte.", "report")
    try:
        if reports and PurePosixPath(reports[0][0]).suffix.lower() != ".txt":
            raise UploadError(FORMATS, "report")
        report = (
            reports[0][1].decode("utf-8") if reports else fields.get("report_text", "")
        )
    except UnicodeError:
        raise UploadError(FORMATS, "report") from None
    if len(report) > 10000:
        raise UploadError("Rapport trop long (10 000 caractères max).", "report")
    if report:
        files["report.txt"] = ("text/plain", upload_text(report))
    return ValidatedUpload(files, ecg_format, sampling, bool(report))


def persist_case(app: FastAPI, user: User, upload: ValidatedUpload) -> dict[str, Any]:
    case_id = str(uuid4())
    staging: UploadStaging = app.state.uploads or UploadStaging.from_environment()
    cases: CaseService = app.state.cases
    staged = False
    try:
        with app.state.identity.connect() as db:
            cases.enforce_creation_rate(db, user.id)
            model_id, config_id = active_refs(db)
            staged = True
            staging.stage(case_id, upload.files, upload.summary())
            result = cases.create_case(
                db,
                case_id=case_id,
                user_id=user.id,
                ecg_format=upload.ecg_format,
                sampling_hz=upload.sampling_hz,
                has_report=upload.has_report,
                model_id=model_id,
                config_id=config_id,
            )
            case_created(db, user.id, case_id, upload.summary())
        return result
    except Exception:
        if staged:
            try:
                staging.discard_new_upload(case_id)
            except OSError:
                pass
        raise


def register_cases(
    app: FastAPI, service: CaseService, uploads: UploadStaging | None
) -> None:
    app.state.cases, app.state.uploads = service, uploads

    @app.get("/api/v1/cases/{case_id}/agent-logs")
    def agent_logs(case_id: str) -> JSONResponse:
        try:
            case = service.get_case(case_id)
            rows = list_for_case(service.database_url, str(case["id"]))
        except CaseNotFound:
            return error_response(AuthError(404, "NOT_FOUND", "Cas introuvable."))
        except psycopg.Error:
            return error_response(
                AuthError(
                    503, "SERVICE_UNAVAILABLE", "Service indisponible. Réessayer."
                )
            )
        return JSONResponse(content=rows, headers={"Cache-Control": "no-store"})

    @app.exception_handler(UploadError)
    async def upload_error(request: Request, error: UploadError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "BAD_REQUEST",
                    "message": error.message,
                    "details": {"field": error.field},
                }
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post(
        "/api/v1/cases",
        status_code=202,
        response_model=CreatedCase,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["ecg_files[]"],
                            "properties": {
                                "ecg_files[]": {
                                    "type": "array",
                                    "items": {"type": "string", "format": "binary"},
                                },
                                "csv_sampling_rate": {"type": "integer"},
                                "report_file": {"type": "string", "format": "binary"},
                                "report_text": {"type": "string", "maxLength": 10000},
                            },
                        }
                    }
                },
            }
        },
    )
    async def create_case(
        request: Request, user: Annotated[User, Depends(current_user)]
    ) -> JSONResponse:
        chunks, size = [], 0
        try:
            async with asyncio.timeout(60):
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > LIMIT + 512 * 1024:
                        raise UploadError("Taille maximale : 20 Mo.")
                    chunks.append(chunk)
        except TimeoutError:
            raise AuthError(
                503, "SERVICE_UNAVAILABLE", "Échec de création du cas. Réessayer."
            ) from None
        upload = await run_in_threadpool(
            parse_upload, request.headers.get("content-type", ""), b"".join(chunks)
        )
        try:
            result = await run_in_threadpool(persist_case, app, user, upload)
        except CaseRateLimited:
            return error_response(
                AuthError(
                    429, "RATE_LIMITED", "Limite de 10 analyses par minute atteinte."
                )
            )
        except (psycopg.Error, OSError, ValueError):
            return error_response(
                AuthError(
                    503, "SERVICE_UNAVAILABLE", "Échec de création du cas. Réessayer."
                )
            )
        return JSONResponse(
            status_code=202,
            content=result,
            headers={
                "Location": "/api/v1/cases/" + result["id"],
                "Cache-Control": "no-store",
            },
        )
