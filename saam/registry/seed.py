"""Configuration v1, propriété de SVC-registry ; versions existantes conservées."""

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg


def seed_configuration(
    connection: psycopg.Connection[tuple[Any, ...]], admin_id: UUID
) -> None:
    existing = connection.execute(
        "SELECT conf_high, quality_min, lexicon_version FROM validation_configs WHERE version=1"
    ).fetchone()
    expected = (Decimal("0.700"), Decimal("0.900"), "v1")
    if existing:
        if existing != expected:
            raise ValueError("La configuration v1 existante diffère ; seed annulé.")
        return
    connection.execute(
        "INSERT INTO validation_configs (version, conf_high, quality_min, lexicon_version, is_active, created_by) "
        "VALUES (1, %s, %s, %s, NOT EXISTS (SELECT 1 FROM validation_configs WHERE is_active), %s)",
        (*expected, admin_id),
    )
