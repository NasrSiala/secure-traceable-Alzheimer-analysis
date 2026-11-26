"""Références des versions actives lors de la création d'un cas."""

from typing import Any

import psycopg


def active_refs(
    db: psycopg.Connection[dict[str, Any]],
) -> tuple[str | None, str | None]:
    model = db.execute("SELECT id FROM models WHERE is_active").fetchone()
    config = db.execute("SELECT id FROM validation_configs WHERE is_active").fetchone()
    return (str(model["id"]) if model else None, str(config["id"]) if config else None)
