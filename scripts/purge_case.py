"""Purge physique d'un cas hors chaîne et contrôle depuis Fabric."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saam.audit.events import case_purged  # noqa: E402
from saam.cases import CaseNotFound, CaseService, InvalidTransition  # noqa: E402
from saam.identity.auth import AuthError, IdentityService, User  # noqa: E402
from saam.ledger import LedgerClient, LedgerError, LedgerUnavailable  # noqa: E402
from saam.storage import ArtifactStore  # noqa: E402
from saam.traceability import ArtifactReader, UploadStaging  # noqa: E402
from saam.verification.service import ARTIFACT_TYPES  # noqa: E402


def purge_case(
    cases: CaseService,
    actor: User,
    case_id: str,
    store: ArtifactStore,
    uploads: UploadStaging,
) -> int:
    if actor.role != "admin":
        raise AuthError(403, "FORBIDDEN", "Action non autorisée.")
    try:
        identifier = str(UUID(case_id.removeprefix("CASE-")))
    except ValueError:
        raise CaseNotFound("Cas introuvable.") from None

    def prepare(db: psycopg.Connection[dict[str, Any]]) -> Callable[[], int]:
        rows = ArtifactReader.list_for_case(db, identifier)
        # Valider tous les chemins avant la première suppression.
        artifact_ids = [str(row["id"]) for row in rows]
        for artifact_id in artifact_ids:
            store.path(artifact_id, "manifest.json")
        uploads.store.path(identifier, "upload.json")

        def erase() -> int:
            for artifact_id in artifact_ids:
                store.discard_bundle(artifact_id)
            uploads.discard_new_upload(identifier)
            return len(artifact_ids)

        return erase

    return cases.purge(
        identifier,
        prepare=prepare,
        on_purged=lambda db, count: case_purged(db, actor.id, identifier, count),
    )


def verify_purged(
    cases: CaseService, store: ArtifactStore, ledger: LedgerClient, case_id: str
) -> list[dict[str, str]]:
    identifier = str(UUID(case_id.removeprefix("CASE-")))
    try:
        cases.get_case(identifier)
    except CaseNotFound:
        pass
    else:
        raise ValueError("Ce cas existe encore dans PostgreSQL.")
    case_ref = f"CASE-{identifier}"
    records = ledger.get_case_history(case_ref)
    if not records:
        raise ValueError("Aucun artefact trouvé pour ce cas sur Fabric.")
    results = []
    for record in records:
        artifact_id = str(UUID(record["artifactId"]))
        kind = record.get("artifactType")
        if (
            record.get("caseId") != case_ref
            or kind not in ARTIFACT_TYPES
            or record.get("offchainRef") != f"artifact://{artifact_id}"
        ):
            raise LedgerUnavailable()
        bundle = store.path(artifact_id, "manifest.json").parent
        if bundle.exists():
            raise ValueError(
                "Des fichiers hors chaîne sont encore présents pour ce cas."
            )
        results.append(
            {"artifact_id": artifact_id, "artifact_type": kind, "status": "manquant"}
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--admin-email", default=os.environ.get("SEED_ADMIN_EMAIL"))
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--yes", action="store_true", help="confirmer la purge physique"
    )
    args = parser.parse_args()
    if not args.admin_email:
        parser.error("L'adresse de l'administrateur est requise.")
    if not args.verify_only and not args.yes:
        parser.error("Indiquer --yes pour confirmer la purge physique de ce cas.")
    try:
        identity = IdentityService.from_environment()
        password = os.environ.get("PURGE_ADMIN_PASSWORD") or getpass.getpass(
            "Mot de passe admin : "
        )
        actor = identity.login(args.admin_email, password, "127.0.0.1").user
        if actor.role != "admin":
            raise AuthError(403, "FORBIDDEN", "Action non autorisée.")
        cases = CaseService(identity.database_url)
        store = ArtifactStore.from_environment()
        if args.verify_only:
            with LedgerClient.from_environment("verifier") as ledger:
                states = verify_purged(cases, store, ledger, args.case)
            print(json.dumps(states, ensure_ascii=False))
        else:
            count = purge_case(
                cases, actor, args.case, store, UploadStaging.from_environment()
            )
            print(f"Cas purgé hors chaîne ; {count} artefact(s).")
    except (
        AuthError,
        CaseNotFound,
        InvalidTransition,
        LedgerError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (EOFError, KeyError, TypeError, OSError, psycopg.Error):
        print(
            "Opération interrompue. Vérifier PostgreSQL et les fichiers du cas.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
