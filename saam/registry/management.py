"""Création et activation des versions du registre (IF-12)."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import psycopg

from saam.ledger import Ledger, RecordNotFound

# Partagé avec le seed, qui peut créer et activer la première configuration.
CONFIG_LOCK = 7219021


class VersionNotFound(ValueError):
    """La version demandée n'existe pas localement."""


class ModelNotAnchored(ValueError):
    """Aucun ancrage vérifiable pour cette version locale."""


def validation_threshold(value: str) -> Decimal:
    try:
        threshold = Decimal(value)
        if threshold.is_finite() and 0 < threshold <= 1:
            stored = threshold.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            if stored > 0:
                return stored
    except InvalidOperation:
        pass
    raise ValueError("Valeur entre 0 et 1.")


def create_validation_config(
    db: psycopg.Connection[dict[str, Any]],
    actor_id: str,
    conf_high: Decimal,
    quality_min: Decimal,
    lexicon: str,
) -> int:
    if not lexicon.strip() or len(lexicon) > 40 or "\x00" in lexicon:
        raise ValueError("Version du lexique requise (40 caractères maximum).")
    db.execute("SELECT pg_advisory_xact_lock(%s)", (CONFIG_LOCK,))
    row = db.execute(
        """INSERT INTO validation_configs
             (version, conf_high, quality_min, lexicon_version, created_by)
           SELECT coalesce(max(version), 0) + 1, %s, %s, %s, %s
           FROM validation_configs
           RETURNING version""",
        (conf_high, quality_min, lexicon, actor_id),
    ).fetchone()
    assert row is not None
    return int(row["version"])


def activate_config(db: psycopg.Connection[dict[str, Any]], version: int) -> None:
    db.execute("SELECT pg_advisory_xact_lock(%s)", (CONFIG_LOCK,))
    target = db.execute(
        "SELECT is_active FROM validation_configs WHERE version=%s", (version,)
    ).fetchone()
    if target is None:
        raise VersionNotFound("Version de configuration introuvable.")
    if target["is_active"]:
        return
    db.execute("UPDATE validation_configs SET is_active=false WHERE is_active")
    db.execute(
        "UPDATE validation_configs SET is_active=true WHERE version=%s", (version,)
    )


def list_models(
    db: psycopg.Connection[dict[str, Any]],
) -> list[dict[str, Any]]:
    return db.execute(
        "SELECT name, version, is_active FROM models ORDER BY name, version"
    ).fetchall()


def activate_model(
    db: psycopg.Connection[dict[str, Any]],
    ledger: Ledger,
    name: str,
    version: str,
) -> bool:
    missing = "Ce modèle n'est pas enregistré sur la blockchain."
    # Vérifier Fabric avant de prendre le verrou SQL des activations.
    try:
        record = ledger.get_model(name, version)
    except RecordNotFound:
        raise ModelNotAnchored(missing) from None

    db.execute("SELECT pg_advisory_xact_lock(hashtextextended('registry:models', 0))")
    target = db.execute(
        """SELECT id, sha256, is_active, registered_tx_id FROM models
           WHERE name=%s AND version=%s FOR UPDATE""",
        (name, version),
    ).fetchone()
    if target is None:
        raise VersionNotFound("Modèle introuvable dans le registre local.")
    if target["registered_tx_id"] is None:
        raise ModelNotAnchored(missing)
    if (
        record.get("docType") != "model"
        or record.get("name") != name
        or record.get("version") != version
        or record.get("sha256") != target["sha256"]
    ):
        raise ModelNotAnchored(
            "L'enregistrement du modèle sur la blockchain diffère du registre local."
        )
    if target["is_active"]:
        return False
    db.execute("UPDATE models SET is_active=false WHERE is_active")
    db.execute("UPDATE models SET is_active=true WHERE id=%s", (target["id"],))
    return True
