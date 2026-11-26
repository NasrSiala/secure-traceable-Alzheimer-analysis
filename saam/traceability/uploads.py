"""Transit chiffré API → worker ; aucune donnée d'upload dans PostgreSQL."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from saam.hashing import canonical_json, canonical_text, file_hash
from saam.storage import ArtifactStore


def upload_text(text: str) -> bytes:
    """Préparer un texte téléversé selon le format UTF-8 NFC de TRD §7.2."""
    return canonical_text(text)


class UploadStaging:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    @classmethod
    def from_environment(cls) -> UploadStaging:
        return cls(
            ArtifactStore.from_environment(
                Path(os.environ.get("UPLOAD_ROOT", "/data/uploads"))
            )
        )

    def stage(
        self,
        case_id: str,
        files: dict[str, tuple[str, bytes]],
        metadata: dict[str, Any],
    ) -> None:
        descriptors = []
        for name, (media_type, data) in files.items():
            self.store.write(case_id, name, data)
            descriptors.append(
                {"name": name, "media_type": media_type, "sha256": file_hash(data)}
            )
        self.store.write(
            case_id, "upload.json", canonical_json(metadata | {"files": descriptors})
        )

    def read(self, case_id: str) -> tuple[dict[str, Any], dict[str, tuple[str, bytes]]]:
        metadata = json.loads(self.store.read(case_id, "upload.json"))
        files = {}
        for entry in metadata["files"]:
            data = self.store.read(case_id, entry["name"])
            if file_hash(data) != entry["sha256"]:
                raise ValueError("Téléversement modifié.")
            files[entry["name"]] = (entry["media_type"], data)
        return metadata, files

    def discard_new_upload(self, case_id: str) -> None:
        """Rollback d'un UUID nouvellement créé ; cible validée avant suppression."""
        directory = self.store.path(case_id, "upload.json").parent
        if directory.is_symlink() or not directory.resolve().is_relative_to(
            self.store.root
        ):
            raise ValueError("Chemin de transit invalide.")
        if directory.exists():
            shutil.rmtree(directory)
