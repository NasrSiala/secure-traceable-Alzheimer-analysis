"""Événement case_created dans la même transaction que le cas et le job."""

from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def case_created(
    db: psycopg.Connection[dict[str, Any]],
    user_id: str,
    case_id: str,
    summary: dict[str, Any],
) -> None:
    db.execute(
        "INSERT INTO audit_events (event_type,actor_user_id,case_id,payload) VALUES ('case_created',%s,%s,%s)",
        (user_id, case_id, Jsonb(summary)),
    )
