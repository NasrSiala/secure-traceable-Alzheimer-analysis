"""Interface de lecture indépendante du pipeline pour SVC-api (AC-08.3)."""

from typing import Any

import psycopg
from psycopg.rows import dict_row


def list_for_case(database_url: str, case_id: str) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=3) as db:
        rows = db.execute(
            "SELECT id,agent,step,status,input_artifact_ids,output_artifact_id,message,details,started_at,duration_ms FROM agent_logs WHERE case_id=%s ORDER BY started_at,id",
            (case_id,),
        ).fetchall()
    return [
        {
            **row,
            "input_artifact_ids": [str(i) for i in row["input_artifact_ids"]],
            "output_artifact_id": str(row["output_artifact_id"])
            if row["output_artifact_id"]
            else None,
            "started_at": row["started_at"].isoformat(),
        }
        for row in rows
    ]
