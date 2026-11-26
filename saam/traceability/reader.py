"""Lecture d'affichage IF-04 : AES et empreintes locales, sans accès Fabric."""

from __future__ import annotations

import io
import json
import math
from typing import Any

import numpy as np
import psycopg

from saam.hashing import artifact_hash, canonical_manifest, file_hash
from saam.storage import ArtifactStore, DecryptionError
from saam.traceability.tool import IntegrityError

LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")


class ArtifactReader:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    @classmethod
    def from_environment(cls) -> ArtifactReader:
        return cls(ArtifactStore.from_environment())

    @staticmethod
    def list_for_case(
        db: psycopg.Connection[dict[str, Any]], case_id: str
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            "SELECT id,type,parent_artifact_id,sha256,offchain_ref,created_by_agent,software_version,model_version,anchor_status,anchor_attempts,tx_id,anchored_at,created_at FROM artifacts WHERE case_id=%s ORDER BY created_at,id",
            (case_id,),
        ).fetchall()
        files = db.execute(
            "SELECT f.artifact_id,f.name,f.sha256,f.size_bytes FROM artifact_files f JOIN artifacts a ON a.id=f.artifact_id WHERE a.case_id=%s",
            (case_id,),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        for row in rows:
            row["files"] = {}
        for descriptor in files:
            by_id[descriptor["artifact_id"]]["files"][descriptor["name"]] = descriptor
        return rows

    def read(self, artifact: dict[str, Any], name: str) -> bytes:
        descriptor = artifact["files"].get(name)
        if descriptor is None:
            raise FileNotFoundError("Fichier indisponible.")
        try:
            data = self.store.read(str(artifact["id"]), name)
        except DecryptionError:
            raise IntegrityError("Fichier non vérifiable.") from None
        if (
            len(data) != descriptor["size_bytes"]
            or file_hash(data) != descriptor["sha256"]
        ):
            raise IntegrityError("Fichier non vérifiable.")
        return data

    def verify_contents(
        self, artifact_id: str, case_id: str, artifact_type: str, expected_sha256: str
    ) -> str:
        """Vérifie le manifeste et chaque fichier décrit par l'empreinte Fabric."""
        try:
            encoded = self.store.read(artifact_id, "manifest.json")
            manifest = json.loads(encoded)
            canonical = canonical_manifest(manifest)
            digest = file_hash(encoded)
            if (
                encoded != canonical
                or digest != expected_sha256
                or manifest["artifact_id"] != artifact_id
                or manifest["case_id"] != case_id
                or manifest["type"] != artifact_type
            ):
                raise IntegrityError("Manifeste modifié.", computed_sha256=digest)
            files = []
            for descriptor in manifest["files"]:
                data = self.store.read(artifact_id, descriptor["name"])
                files.append(
                    descriptor | {"size": len(data), "sha256": file_hash(data)}
                )
            if files != manifest["files"]:
                computed = artifact_hash(manifest | {"files": files})
                raise IntegrityError("Fichier modifié.", computed_sha256=computed)
        except (DecryptionError, ValueError, RecursionError):
            raise IntegrityError("Artefact non vérifiable.") from None
        return digest

    def read_json(self, artifact: dict[str, Any], name: str) -> dict[str, Any]:
        def reject_constant(value: str) -> None:
            raise ValueError("Nombre JSON invalide.")

        def finite_float(value: str) -> float:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Nombre JSON invalide.")
            return number

        payload = json.loads(
            self.read(artifact, name),
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
        if not isinstance(payload, dict):
            raise ValueError("Objet JSON attendu.")
        return payload

    def signal(self, artifact: dict[str, Any]) -> dict[str, Any]:
        """Tracé à 50 Hz ; aucune pickle ni allocation selon un en-tête externe."""
        encoded = self.read(artifact, "signal.npy")
        stream = io.BytesIO(encoded)
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                stream, max_header_size=1024
            )
        elif version == (2, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_2_0(
                stream, max_header_size=1024
            )
        else:
            raise ValueError("Format NPY invalide.")
        if shape != (12, 1000) or dtype.kind != "f" or dtype.itemsize != 4:
            raise ValueError("Signal traité invalide.")
        data = stream.read()
        if len(data) != 12 * 1000 * 4:
            raise ValueError("Taille du signal invalide.")
        signal = np.frombuffer(data, dtype=dtype).reshape(
            shape, order="F" if fortran else "C"
        )
        if not np.isfinite(signal).all():
            raise ValueError("Signal non fini.")
        return {
            "artifact_id": str(artifact["id"]),
            "artifact": "processed",
            "leads": list(LEADS),
            "unit": "z-score",
            "source_sampling_hz": 100,
            "sampling_hz": 50,
            "duration_seconds": 10,
            "time_seconds": [index / 100 for index in range(0, 1000, 2)],
            "values": signal[:, ::2].tolist(),
        }
