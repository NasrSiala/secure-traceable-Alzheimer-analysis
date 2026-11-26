"""Lecture de la version active pour /health ; les migrations sont T2.1."""

from __future__ import annotations

from typing import Any

import psycopg


def active_model(
    connection: psycopg.Connection[tuple[Any, ...]],
) -> dict[str, str] | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.models')")
        exists = cursor.fetchone()
        if exists is None or exists[0] is None:
            return None
        cursor.execute(
            "SELECT name, version FROM public.models WHERE is_active LIMIT 1"
        )
        model = cursor.fetchone()
    if model is None:
        return None
    return {"name": str(model[0]), "version": str(model[1])}
