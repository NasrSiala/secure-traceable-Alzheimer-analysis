"""IF-03 : cas et jobs, avec transactions fournies par le point d'entrée."""

from __future__ import annotations

from typing import Any

import psycopg


class CaseNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


class CaseRateLimited(Exception):
    pass


class CaseService:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def enforce_creation_rate(
        self, db: psycopg.Connection[dict[str, Any]], user_id: str
    ) -> None:
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", (user_id,))
        row = db.execute(
            "SELECT count(*) AS count FROM cases WHERE created_by=%s AND created_at > now()-interval '1 minute'",
            (user_id,),
        ).fetchone()
        if row and row["count"] >= 10:
            raise CaseRateLimited()

    def create_case(
        self,
        db: psycopg.Connection[dict[str, Any]],
        *,
        case_id: str,
        user_id: str,
        ecg_format: str,
        sampling_hz: int,
        has_report: bool,
        model_id: str | None = None,
        config_id: str | None = None,
    ) -> dict[str, Any]:
        row = db.execute(
            "INSERT INTO cases (id,created_by,ecg_format,original_sampling_hz,has_report,model_id,validation_config_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id,case_ref,status",
            (
                case_id,
                user_id,
                ecg_format,
                sampling_hz,
                has_report,
                model_id,
                config_id,
            ),
        ).fetchone()
        db.execute("INSERT INTO jobs (case_id) VALUES (%s)", (case_id,))
        assert row is not None
        return {
            "id": str(row["id"]),
            "case_ref": row["case_ref"],
            "status": row["status"],
        }
