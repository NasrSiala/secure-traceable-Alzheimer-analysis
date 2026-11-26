"""Historique des vérifications, lu et écrit par SVC-verification."""

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import psycopg

from saam.cases import CaseService

from .service import VerificationItem


class VerificationHistory:
    def __init__(self, cases: CaseService) -> None:
        self.cases = cases

    def record(
        self,
        case_id: str,
        requested_by: str,
        started_at: datetime,
        ledger_reachable: bool,
        items: tuple[VerificationItem, ...],
        *,
        on_recorded: Callable[
            [psycopg.Connection[dict[str, Any]], dict[str, Any]], None
        ]
        | None = None,
    ) -> dict[str, Any]:
        counts = Counter(item.status for item in items)
        details = [asdict(item) for item in items]
        completed_at = max(started_at, datetime.now(UTC))
        with self.cases.connect() as db:
            case = self.cases.get_case(case_id, db=db)
            row = db.execute(
                """INSERT INTO verifications
                   (case_id, requested_by, ledger_reachable, count_valide, count_modifie,
                    count_manquant, count_non_verifiable, started_at, completed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING
                   id, case_id, requested_by, ledger_reachable, count_valide,
                   count_modifie, count_manquant, count_non_verifiable, started_at, completed_at""",
                (
                    case["id"],
                    requested_by,
                    ledger_reachable,
                    counts["valide"],
                    counts["modifie"],
                    counts["manquant"],
                    counts["non_verifiable"],
                    started_at,
                    completed_at,
                ),
            ).fetchone()
            assert row is not None
            with db.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO verification_items
                       (verification_id, artifact_id, artifact_type, status, expected_sha256,
                        computed_sha256, detail)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (
                            row["id"],
                            item.artifact_id,
                            item.artifact_type,
                            item.status,
                            item.expected_sha256,
                            item.computed_sha256,
                            item.detail,
                        )
                        for item in items
                    ],
                )
            if on_recorded is not None:
                on_recorded(db, row)
        return row | {"items": details}

    def list_for_case(self, case_id: str, page: int, size: int) -> dict[str, Any]:
        with self.cases.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            case = self.cases.get_case(case_id, db=db)
            total = db.execute(
                "SELECT count(*) AS total FROM verifications WHERE case_id=%s",
                (case["id"],),
            ).fetchone()
            rows = db.execute(
                """SELECT id, case_id, requested_by, ledger_reachable, count_valide,
                          count_modifie, count_manquant, count_non_verifiable,
                          started_at, completed_at FROM verifications
                   WHERE case_id=%s ORDER BY completed_at DESC, id DESC LIMIT %s OFFSET %s""",
                (case["id"], size, (page - 1) * size),
            ).fetchall()
            by_id = {row["id"]: row for row in rows}
            for row in rows:
                row["items"] = []
            if by_id:
                details = db.execute(
                    """SELECT verification_id, artifact_id, artifact_type, status,
                              expected_sha256, computed_sha256, detail
                       FROM verification_items WHERE verification_id=ANY(%s::uuid[])
                       ORDER BY artifact_type, artifact_id""",
                    (list(by_id),),
                )
                for detail in details:
                    by_id[detail.pop("verification_id")]["items"].append(detail)
        assert total is not None
        return {"items": rows, "total": total["total"], "page": page, "size": size}
