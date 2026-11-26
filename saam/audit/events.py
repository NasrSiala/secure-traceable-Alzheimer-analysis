"""Émission IF-13 des événements applicatifs, avec isolation par savepoint."""

import logging
import re
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

LOGGER = logging.getLogger(__name__)


def _append(
    db: psycopg.Connection[dict[str, Any]],
    event_type: str,
    *,
    case_id: str | None = None,
    actor: str | None = None,
    payload: dict[str, Any],
) -> bool:
    try:
        with db.transaction():
            db.execute(
                "INSERT INTO audit_events (event_type,actor_user_id,case_id,payload) VALUES (%s,%s,%s,%s)",
                (event_type, actor, case_id, Jsonb(payload)),
            )
    except psycopg.Error:
        LOGGER.error("Écriture du journal d’audit impossible (%s).", event_type)
        return False
    return True


def case_created(
    db: psycopg.Connection[dict[str, Any]],
    user_id: str,
    case_id: str,
    user_role: str,
    summary: dict[str, Any],
) -> None:
    _append(
        db,
        "case_created",
        actor=user_id,
        case_id=case_id,
        payload={
            "case_id": case_id,
            "user_role": user_role,
            "ecg_format": summary["ecg_format"],
            "sampling_hz": summary["sampling_hz"],
            "has_report": summary["has_report"],
        },
    )


def artifact_anchored(
    db: psycopg.Connection[dict[str, Any]], case_id: str, kind: str, tx_id: str
) -> None:
    _append(
        db,
        "artifact_anchored",
        case_id=case_id,
        payload={
            "case_id": case_id,
            "artifact_type": kind,
            "tx_id": tx_id,
        },
    )


def anchoring_failed(
    db: psycopg.Connection[dict[str, Any]], case_id: str, kind: str, error: str
) -> None:
    _append(
        db,
        "anchoring_failed",
        case_id=case_id,
        payload={
            "case_id": case_id,
            "artifact_type": kind,
            "error": error,
        },
    )


def pipeline_completed(
    db: psycopg.Connection[dict[str, Any]],
    case_id: str,
    decision: str,
    duration_ms: int,
) -> None:
    _append(
        db,
        "pipeline_completed",
        case_id=case_id,
        payload={
            "case_id": case_id,
            "duration_ms": duration_ms,
            "final_status": decision,
        },
    )


def integrity_check_completed(
    db: psycopg.Connection[dict[str, Any]], row: dict[str, Any]
) -> None:
    case_id = str(row["case_id"])
    _append(
        db,
        "integrity_check_completed",
        actor=str(row["requested_by"]),
        case_id=case_id,
        payload={
            "case_id": case_id,
            "nb_valide": row["count_valide"],
            "nb_modifie": row["count_modifie"],
            "nb_manquant": row["count_manquant"],
            "nb_non_verifiable": row["count_non_verifiable"],
        },
    )


def model_evaluated(
    db: psycopg.Connection[dict[str, Any]],
    version: str,
    auc_macro: float,
    f1_macro: float,
) -> bool:
    if (
        re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
        or not 0 <= auc_macro <= 1
        or not 0 <= f1_macro <= 1
    ):
        raise ValueError("Version ou métriques du modèle invalides.")
    return _append(
        db,
        "model_evaluated",
        payload={
            "model_version": version,
            "auc_macro": auc_macro,
            "f1_macro": f1_macro,
        },
    )


def case_purged(
    db: psycopg.Connection[dict[str, Any]], admin_id: str, case_id: str, count: int
) -> None:
    _append(
        db,
        "case_purged",
        actor=admin_id,
        payload={"case_id": case_id, "nb_artefacts": count},
    )


def validation_config_created(
    db: psycopg.Connection[dict[str, Any]], admin_id: str, version: int
) -> None:
    _append(
        db, "validation_config_created", actor=admin_id, payload={"version": version}
    )


def model_activated(
    db: psycopg.Connection[dict[str, Any]], admin_id: str, name: str, version: str
) -> None:
    _append(
        db,
        "model_activated",
        actor=admin_id,
        payload={"name": name, "version": version},
    )
