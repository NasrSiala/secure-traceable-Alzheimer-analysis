"""IF-04 : écritures durables avant Fabric ; preuve indépendante et rejeu sûr."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from saam.hashing import artifact_hash, canonical_manifest, file_hash
from saam.ledger import DuplicateRecord, Ledger, LedgerError, LedgerUnavailable
from saam.storage import ArtifactStore, DecryptionError

AGENTS = {
    "original": "ingestion",
    "processed": "preparation",
    "features": "features",
    "prediction": "prediction",
    "validation": "validation",
    "explanation": "explanation",
    "final_result": "finalization",
}


class AnchoringError(Exception):
    """L'ancrage n'est pas prouvé ; aucune décision acceptée ne doit être émise."""


class IntegrityError(Exception):
    """Empreinte ou authentification GCM invalide."""


@dataclass(frozen=True)
class ArtifactFile:
    name: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class Artifact:
    id: str
    case_id: str
    type: str
    agent: str
    created_at: datetime
    parent_id: str | None = None
    software_version: str = "0.1.0"
    model_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    files: tuple[ArtifactFile, ...] = ()

    def manifest(self) -> dict[str, Any]:
        if self.type not in AGENTS or AGENTS[self.type] != self.agent:
            raise ValueError("Type ou agent d'artefact invalide.")
        for identifier in [
            self.id,
            self.case_id,
            *([self.parent_id] if self.parent_id else []),
        ]:
            if str(UUID(identifier)) != identifier:
                raise ValueError("Identifiant d'artefact invalide.")
        if self.created_at.tzinfo is None or (self.type == "original") != (
            self.parent_id is None
        ):
            raise ValueError("Horodatage ou parent d'artefact invalide.")
        if any(
            f.name == "manifest.json" or len(f.media_type) > 100 for f in self.files
        ):
            raise ValueError("Nom réservé ou type MIME trop long.")
        return {
            "artifact_id": self.id,
            "case_id": self.case_id,
            "type": self.type,
            "parent_artifact_id": self.parent_id,
            "created_at": self.created_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "software_version": self.software_version,
            "model_version": self.model_version,
            "metadata": self.metadata,
            "files": [
                {
                    "name": f.name,
                    "media_type": f.media_type,
                    "size": len(f.data),
                    "sha256": file_hash(f.data),
                }
                for f in self.files
            ],
        }


class TraceabilityTool:
    def __init__(
        self,
        database_url: str,
        store: ArtifactStore,
        ledger: Ledger,
        *,
        on_failure: Callable[[str], None],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database_url, self.store, self.ledger = database_url, store, ledger
        self.on_failure, self.sleep = on_failure, sleep

    def record(self, artifact: Artifact) -> dict[str, Any]:
        """Fichiers → SQL en_attente → 1 tentative + 3 réessais → SQL ancre.

        Le caller fournit on_failure via SVC-cases (propriété ADR-15) ; la
        traçabilité ne modifie jamais cases/jobs. Le verrou de session reste
        détenu entre les commits, puis est libéré à la fermeture de connexion.
        """
        manifest = artifact.manifest()
        encoded = canonical_manifest(manifest)
        digest = file_hash(encoded)
        with psycopg.connect(self.database_url, row_factory=dict_row) as db:
            db.execute(
                "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (artifact.case_id,)
            )
            prior = db.execute(
                "SELECT * FROM artifacts WHERE id = %s OR (case_id = %s AND type = %s)",
                (artifact.id, artifact.case_id, artifact.type),
            ).fetchone()
            if prior and (
                str(prior["id"]) != artifact.id
                or str(prior["case_id"]) != artifact.case_id
                or prior["sha256"] != digest
            ):
                self.on_failure(artifact.case_id)
                raise AnchoringError("Conflit d'empreinte : ancrage refusé.")
            if artifact.parent_id:
                parent = db.execute(
                    "SELECT case_id FROM artifacts WHERE id = %s", (artifact.parent_id,)
                ).fetchone()
                if not parent or str(parent["case_id"]) != artifact.case_id:
                    raise ValueError("Le parent doit appartenir au même cas.")
            paths = {
                f.name: self.store.write(artifact.id, f.name, f.data)
                for f in artifact.files
            }
            manifest_path = self.store.write(artifact.id, "manifest.json", encoded)
            if not prior:
                db.execute(
                    "INSERT INTO artifacts (id,case_id,type,parent_artifact_id,sha256,manifest_path,offchain_ref,created_by_agent,software_version,model_version,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        artifact.id,
                        artifact.case_id,
                        artifact.type,
                        artifact.parent_id,
                        digest,
                        manifest_path,
                        "artifact://" + artifact.id,
                        artifact.agent,
                        artifact.software_version,
                        artifact.model_version,
                        artifact.created_at,
                    ),
                )
                for descriptor in manifest["files"]:
                    db.execute(
                        "INSERT INTO artifact_files (artifact_id,name,media_type,size_bytes,sha256,storage_path) VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            artifact.id,
                            descriptor["name"],
                            descriptor["media_type"],
                            descriptor["size"],
                            descriptor["sha256"],
                            paths[descriptor["name"]],
                        ),
                    )
            db.commit()
            if prior and prior["anchor_status"] == "ancre":
                confirmed = self.ledger.get_record(artifact.id)
                self._proof(confirmed, artifact, digest)
                return prior
            payload = {
                "artifactId": artifact.id,
                "caseId": "CASE-" + artifact.case_id,
                "artifactType": artifact.type,
                "sha256": digest,
                "createdAt": manifest["created_at"],
                "softwareVersion": artifact.software_version,
                "modelVersion": artifact.model_version,
                "parentArtifactId": artifact.parent_id,
                "offchainRef": "artifact://" + artifact.id,
            }
            for attempt in range(1, 5):
                db.execute(
                    "UPDATE artifacts SET anchor_attempts=%s WHERE id=%s",
                    (attempt, artifact.id),
                )
                db.commit()
                try:
                    try:
                        confirmed = self.ledger.create_record(payload)
                    except DuplicateRecord:
                        confirmed = self.ledger.get_record(artifact.id)
                    tx_id = self._proof(confirmed, artifact, digest)
                    db.execute(
                        "UPDATE artifacts SET anchor_status='ancre',tx_id=%s,anchored_at=now() WHERE id=%s",
                        (tx_id, artifact.id),
                    )
                    row = db.execute(
                        "SELECT * FROM artifacts WHERE id=%s", (artifact.id,)
                    ).fetchone()
                    db.commit()
                    assert row is not None
                    return row
                except LedgerUnavailable:
                    if attempt < 4:
                        self.sleep(float(2 ** (attempt - 1)))
                        continue
                except (LedgerError, AnchoringError):
                    pass
                break
            db.execute(
                "UPDATE artifacts SET anchor_status='echec',tx_id=NULL,anchored_at=NULL WHERE id=%s",
                (artifact.id,),
            )
            db.commit()
        self.on_failure(artifact.case_id)
        raise AnchoringError(
            "Ancrage sur la blockchain impossible — résultat non émis."
        )

    @staticmethod
    def _proof(record: dict[str, Any], artifact: Artifact, digest: str) -> str:
        if (
            record.get("sha256") != digest
            or record.get("artifactId") != artifact.id
            or record.get("caseId") != "CASE-" + artifact.case_id
            or record.get("artifactType") != artifact.type
            or record.get("parentArtifactId") != artifact.parent_id
            or record.get("softwareVersion") != artifact.software_version
            or record.get("modelVersion") != artifact.model_version
            or record.get("createdAt")
            != artifact.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        ):
            raise AnchoringError("La preuve Fabric ne correspond pas à l'artefact.")
        tx_id = record.get("txId")
        if not isinstance(tx_id, str) or not re.fullmatch(r"[0-9a-f]{64}", tx_id):
            raise LedgerUnavailable()
        return tx_id

    def read_manifest(self, artifact_id: str) -> dict[str, Any]:
        try:
            manifest = json.loads(self.store.read(artifact_id, "manifest.json"))
            expected = self.ledger.get_record(artifact_id)
            if (
                expected.get("sha256") != artifact_hash(manifest)
                or manifest["artifact_id"] != artifact_id
                or expected.get("caseId") != "CASE-" + manifest["case_id"]
            ):
                raise IntegrityError("Manifeste modifié.")
            return dict(manifest)
        except (DecryptionError, ValueError, KeyError, TypeError):
            raise IntegrityError("Manifeste non vérifiable.") from None

    def read(self, artifact_id: str, name: str) -> bytes:
        manifest = self.read_manifest(artifact_id)
        descriptor = next((f for f in manifest["files"] if f["name"] == name), None)
        if descriptor is None:
            raise FileNotFoundError("Fichier absent du manifeste.")
        try:
            data = self.store.read(artifact_id, name)
        except DecryptionError:
            raise IntegrityError("Fichier modifié.") from None
        if file_hash(data) != descriptor["sha256"] or len(data) != descriptor["size"]:
            raise IntegrityError("Fichier modifié.")
        return data
