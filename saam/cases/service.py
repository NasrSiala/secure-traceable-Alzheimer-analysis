"""IF-03 : cas et jobs, avec transactions fournies par le point d'entrée."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class CaseNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


class CaseRateLimited(Exception):
    pass


@dataclass(frozen=True)
class Job:
    id: str
    case_id: str
    owner: str
    attempts: int


class CaseService:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=3,
            options="-c statement_timeout=5000",
        )

    def list_cases(
        self, page: int, size: int, status: str | None = None
    ) -> dict[str, Any]:
        """Liste récente et total calculés dans le même instantané SQL."""
        with self.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            total = db.execute(
                "SELECT count(*) AS total FROM cases WHERE (%s::case_status IS NULL OR status=%s::case_status)",
                (status, status),
            ).fetchone()
            rows = db.execute(
                "SELECT id,case_ref,status,created_at,predicted_class,confidence,decision FROM cases WHERE (%s::case_status IS NULL OR status=%s::case_status) ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
                (status, status, size, (page - 1) * size),
            ).fetchall()
        assert total is not None
        return {"items": rows, "total": total["total"], "page": page, "size": size}

    def get_case(
        self, case_id: str, *, db: psycopg.Connection[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        try:
            identifier = str(UUID(case_id.removeprefix("CASE-")))
        except ValueError:
            raise CaseNotFound("Cas introuvable.") from None
        if db is None:
            with self.connect() as connection:
                return self.get_case(identifier, db=connection)
        row = db.execute("SELECT * FROM cases WHERE id=%s", (identifier,)).fetchone()
        if not row:
            raise CaseNotFound("Cas introuvable.")
        return row

    def claim_job(self, worker_id: str) -> Job | None:
        if not worker_id or len(worker_id) > 100:
            raise ValueError("Identifiant worker invalide.")
        with self.connect() as db:
            while True:
                row = db.execute(
                    "SELECT * FROM jobs WHERE status='en_file' AND attempts < max_attempts ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1"
                ).fetchone()
                if not row:
                    return None
                case = db.execute(
                    "SELECT status FROM cases WHERE id=%s", (row["case_id"],)
                ).fetchone()
                if not case or case["status"] not in {"en_attente", "en_cours"}:
                    status = (
                        "termine" if case and case["status"] == "termine" else "echec"
                    )
                    db.execute(
                        "UPDATE jobs SET status=%s,locked_by=NULL,locked_at=NULL WHERE id=%s",
                        (status, row["id"]),
                    )
                    continue
                db.execute(
                    "UPDATE jobs SET status='en_cours',attempts=attempts+1,locked_by=%s,locked_at=now(),heartbeat_at=now() WHERE id=%s",
                    (worker_id, row["id"]),
                )
                db.execute(
                    "UPDATE cases SET status='en_cours' WHERE id=%s", (row["case_id"],)
                )
                return Job(
                    str(row["id"]), str(row["case_id"]), worker_id, row["attempts"] + 1
                )

    def heartbeat(self, job: Job) -> bool:
        with self.connect() as db:
            return (
                db.execute(
                    "UPDATE jobs SET heartbeat_at=now() WHERE id=%s AND status='en_cours' AND locked_by=%s RETURNING id",
                    (job.id, job.owner),
                ).fetchone()
                is not None
            )

    def update_progress(self, job: Job, step: str) -> None:
        with self.connect() as db:
            row = db.execute(
                "UPDATE cases SET current_step=%s WHERE id=%s AND status='en_cours' AND EXISTS (SELECT 1 FROM jobs WHERE id=%s AND status='en_cours' AND locked_by=%s) RETURNING id",
                (step, job.case_id, job.id, job.owner),
            ).fetchone()
            if not row:
                raise InvalidTransition("Le worker ne détient plus ce job.")

    def complete_case(
        self,
        case_id: str,
        decision: str,
        *,
        job: Job,
        on_complete: Callable[[psycopg.Connection[dict[str, Any]], int], None]
        | None = None,
    ) -> None:
        if decision not in {"accepte", "revision_requise", "rejete"}:
            raise ValueError("Décision invalide.")
        with self.connect() as db:
            lease = db.execute(
                "SELECT id FROM jobs WHERE id=%s AND case_id=%s AND status='en_cours' AND locked_by=%s FOR UPDATE",
                (job.id, case_id, job.owner),
            ).fetchone()
            if not lease:
                raise InvalidTransition("Le worker ne détient plus ce job.")
            row = db.execute(
                "UPDATE cases SET status='termine',decision=%s,completed_at=now() WHERE id=%s AND status='en_cours' RETURNING created_at,completed_at",
                (decision, case_id),
            ).fetchone()
            if not row:
                raise InvalidTransition("Le cas ne peut pas être terminé.")
            if on_complete is not None:
                elapsed = row["completed_at"] - row["created_at"]
                on_complete(db, max(0, int(elapsed.total_seconds() * 1000)))

    def fail_case(
        self, case_id: str, status: str = "erreur_ancrage", *, job: Job | None = None
    ) -> None:
        if status not in {"erreur", "erreur_ancrage"}:
            raise ValueError("Statut d'erreur invalide.")
        message = (
            "Ancrage sur la blockchain impossible — résultat non émis."
            if status == "erreur_ancrage"
            else "Traitement interrompu. Réessayer."
        )
        with self.connect() as db:
            if job is not None:
                lease = db.execute(
                    "SELECT id FROM jobs WHERE id=%s AND case_id=%s AND status='en_cours' AND locked_by=%s FOR UPDATE",
                    (job.id, case_id, job.owner),
                ).fetchone()
                if not lease:
                    return
            db.execute(
                "UPDATE cases SET status=%s,error_message=%s,completed_at=now() WHERE id=%s AND status IN ('en_attente','en_cours')",
                (status, message, case_id),
            )

    def finish_job(self, job: Job, succeeded: bool) -> None:
        with self.connect() as db:
            row = db.execute(
                "UPDATE jobs SET status=%s,locked_by=NULL,locked_at=NULL,heartbeat_at=now(),last_error=%s WHERE id=%s AND status='en_cours' AND locked_by=%s RETURNING id",
                (
                    "termine" if succeeded else "echec",
                    None if succeeded else "Traitement interrompu.",
                    job.id,
                    job.owner,
                ),
            ).fetchone()
            if not row:
                raise InvalidTransition("Le worker ne détient plus ce job.")

    def recover_jobs(self) -> int:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE status='en_cours' AND COALESCE(heartbeat_at,locked_at,created_at) < now()-interval '5 minutes' FOR UPDATE SKIP LOCKED"
            ).fetchall()
            for row in rows:
                case = db.execute(
                    "SELECT status FROM cases WHERE id=%s", (row["case_id"],)
                ).fetchone()
                if case and case["status"] == "termine":
                    status = "termine"
                elif (
                    not case
                    or case["status"] in {"erreur", "erreur_ancrage"}
                    or row["attempts"] >= row["max_attempts"]
                ):
                    status = "echec"
                    db.execute(
                        "UPDATE cases SET status='erreur',error_message='Traitement interrompu. Réessayer.',completed_at=now() WHERE id=%s AND status IN ('en_attente','en_cours')",
                        (row["case_id"],),
                    )
                else:
                    status = "en_file"
                db.execute(
                    "UPDATE jobs SET status=%s,locked_by=NULL,locked_at=NULL,heartbeat_at=NULL,last_error='Worker interrompu.' WHERE id=%s",
                    (status, row["id"]),
                )
            return len(rows)

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
