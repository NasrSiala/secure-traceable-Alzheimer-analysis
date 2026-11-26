"""Références des versions actives lors de la création d'un cas."""

from typing import Any

import psycopg


def active_refs(
    db: psycopg.Connection[dict[str, Any]],
) -> tuple[str | None, str | None]:
    versions = db.execute(
        """SELECT (SELECT id::text FROM models WHERE is_active) AS model_id,
                  (SELECT id::text FROM validation_configs WHERE is_active) AS config_id"""
    ).fetchone()
    assert versions is not None
    return versions["model_id"], versions["config_id"]
