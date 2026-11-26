"""Inscrire l'évaluation produite par T3.8b dans le journal d'audit."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saam.audit import model_evaluated  # noqa: E402


def record_model_card(path: Path, database_url: str) -> bool:
    card: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(card, dict) or not isinstance(card.get("metrics"), dict):
        raise ValueError("Fiche d'évaluation invalide.")
    version = card.get("version")
    auc = card["metrics"].get("auc_macro")
    f1 = card["metrics"].get("f1_macro")
    if (
        not isinstance(version, str)
        or type(auc) not in (int, float)
        or type(f1) not in (int, float)
    ):
        raise ValueError("Version ou métriques du modèle invalides.")
    if not database_url:
        raise ValueError("DATABASE_URL_API est requise.")
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=3) as db:
        return model_evaluated(db, version, auc, f1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-card", type=Path, default=ROOT / "ml/artifacts/model_card.json"
    )
    args = parser.parse_args()
    try:
        recorded = record_model_card(
            args.model_card, os.environ.get("DATABASE_URL_API", "")
        )
    except (OSError, ValueError, psycopg.Error):
        recorded = False
    if not recorded:
        print(
            "Évaluation non enregistrée. Vérifier la fiche du modèle et PostgreSQL.",
            file=sys.stderr,
        )
        return 1
    print("Évaluation du modèle enregistrée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
