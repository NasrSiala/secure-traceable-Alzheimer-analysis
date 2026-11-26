"""Nonce 96 bits || texte chiffré || tag GCM ; AAD = artifact_id|name."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_FILE_BYTES = 20 * 1024 * 1024
_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")


class DecryptionError(Exception):
    """Échec d'authentification GCM ; aucun contenu ou secret dans le message."""


class ArtifactStore:
    """Stocke les octets clairs sous des noms internes, après chiffrement.

    La clé de 32 octets est injectée. Les chemins retournés sont relatifs à
    root ; une lecture reconstruit son chemin depuis l'id et le nom validés.
    Une réécriture atomique utilise toujours un nouveau nonce aléatoire.
    """

    def __init__(self, root: Path, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("ARTIFACT_KEY doit contenir exactement 32 octets.")
        self.root = root.resolve()
        self._cipher = AESGCM(key)

    @classmethod
    def from_environment(cls, root: Path | None = None) -> ArtifactStore:
        try:
            encoded = os.environ.get("ARTIFACT_KEY", "")
            key_file = os.environ.get("ARTIFACT_KEY_FILE")
            if key_file:
                encoded = Path(key_file).read_text(encoding="ascii").strip()
            if not re.fullmatch(r"[0-9a-fA-F]{64}", encoded):
                raise ValueError
            key = bytes.fromhex(encoded)
        except (ValueError, OSError):
            raise ValueError(
                "Configurer ARTIFACT_KEY avec 64 caractères hexadécimaux."
            ) from None
        return cls(
            root or Path(os.environ.get("ARTIFACT_ROOT", "/data/artifacts")), key
        )

    def path(self, artifact_id: str, name: str) -> Path:
        try:
            identifier = str(UUID(artifact_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Identifiant d'artefact invalide.") from None
        if (
            identifier != artifact_id
            or not _NAME.fullmatch(name)
            or name in {".", ".."}
        ):
            raise ValueError("Nom ou identifiant de fichier invalide.")
        target = self.root / identifier / (name + ".gcm")
        if target.parent.is_symlink() or target.is_symlink():
            raise ValueError(
                "Un fichier d'artefact ne peut pas être un lien symbolique."
            )
        if not target.resolve().is_relative_to(self.root):
            raise ValueError("Chemin de stockage invalide.")
        return target

    @staticmethod
    def _aad(artifact_id: str, name: str) -> bytes:
        return (artifact_id + "|" + name).encode("ascii")

    def write(self, artifact_id: str, name: str, data: bytes) -> str:
        """Écriture atomique du fichier chiffré ; retourne son chemin relatif."""
        target = self.path(artifact_id, name)
        if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES:
            raise ValueError("Un fichier doit contenir au plus 20 Mo d'octets.")
        nonce = os.urandom(12)
        encoded = nonce + self._cipher.encrypt(
            nonce, data, self._aad(artifact_id, name)
        )
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Revalider après mkdir : refuser un répertoire substitué par un lien.
        self.path(artifact_id, name)
        fd, temporary = tempfile.mkstemp(prefix=".encrypted-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target.relative_to(self.root).as_posix()

    def discard_bundle(self, artifact_id: str) -> None:
        directory = self.path(artifact_id, "manifest.json").parent
        if directory.exists():
            shutil.rmtree(directory)

    def read(self, artifact_id: str, name: str) -> bytes:
        """Déchiffre et authentifie ; fichier absent = FileNotFoundError."""
        encoded = self.path(artifact_id, name).read_bytes()
        if len(encoded) < 28 or len(encoded) > MAX_FILE_BYTES + 28:
            raise DecryptionError("Fichier chiffré non vérifiable.")
        try:
            return self._cipher.decrypt(
                encoded[:12], encoded[12:], self._aad(artifact_id, name)
            )
        except InvalidTag:
            raise DecryptionError("Fichier chiffré non vérifiable.") from None
