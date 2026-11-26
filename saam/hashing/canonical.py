"""Règle TRD §7.2 : SHA-256 du manifeste JCS et des fichiers clairs."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping
from typing import IO, TypeAlias

import rfc8785

JSONValue: TypeAlias = (
    "None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]"
)

_MANIFEST_FIELDS = {
    "artifact_id",
    "case_id",
    "type",
    "parent_artifact_id",
    "created_at",
    "software_version",
    "model_version",
    "metadata",
    "files",
}
_FILE_FIELDS = {"name", "media_type", "size", "sha256"}
_FILE_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _normalize(value: object) -> JSONValue:
    """Copie JSON avec arrondi récursif ; JCS conserve les chaînes Unicode."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Un flottant JSON doit être fini.")
        return round(value, 6)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Une clé JSON doit être une chaîne.")
            result[key] = _normalize(item)
        return result
    raise ValueError("Le contenu doit contenir uniquement des valeurs JSON.")


def canonical_json(value: object) -> bytes:
    """Retourne les octets JCS RFC 8785 après arrondi à six décimales.

    L'ordre des tableaux et les chaînes Unicode sont conservés. NaN, infinis,
    entiers hors du domaine exact IEEE 754, cycles et Unicode invalide sont
    refusés par ``ValueError``. Le contenu de l'entrée n'est jamais journalisé.
    """
    try:
        return rfc8785.dumps(_normalize(value))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError("Le contenu JSON n'est pas canonisable.") from error


def canonical_text(text: str) -> bytes:
    """Encode le texte en UTF-8 NFC, sans modifier ses fins de ligne."""
    if not isinstance(text, str):
        raise ValueError("Le texte doit être une chaîne Unicode.")
    try:
        return unicodedata.normalize("NFC", text).encode("utf-8")
    except UnicodeError as error:
        raise ValueError(
            "Le texte contient des caractères Unicode invalides."
        ) from error


def canonical_manifest(manifest: Mapping[str, object]) -> bytes:
    """Canonise un manifeste TRD §7.2 ; trie ses fichiers par nom.

    Chaque fichier possède name, media_type, size et sha256. Les noms doivent
    être uniques : l'ordre fourni ne peut pas départager deux fichiers de même
    nom. Les identifiants, versions et horodatages restent ceux du producteur ;
    leur validation métier appartient à la couche de traçabilité.
    """
    if not isinstance(manifest, Mapping) or set(manifest) != _MANIFEST_FIELDS:
        raise ValueError("Le manifeste doit contenir les champs du TRD §7.2.")
    files = manifest["files"]
    if not isinstance(files, list) or not isinstance(manifest["metadata"], Mapping):
        raise ValueError(
            "Le manifeste doit contenir une liste de fichiers et des métadonnées."
        )
    by_name: dict[str, dict[str, object]] = {}
    for entry in files:
        if not isinstance(entry, Mapping) or set(entry) != _FILE_FIELDS:
            raise ValueError(
                "Une entrée de fichier doit contenir name, media_type, size et sha256."
            )
        name = entry["name"]
        if (
            not isinstance(name, str)
            or not _FILE_NAME.fullmatch(name)
            or name in by_name
        ):
            raise ValueError("Les fichiers doivent avoir des noms valides et uniques.")
        size, digest, media_type = entry["size"], entry["sha256"], entry["media_type"]
        if (
            type(size) is not int
            or size < 0
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            or not isinstance(media_type, str)
            or not media_type
        ):
            raise ValueError("Les métadonnées du fichier ne sont pas valides.")
        by_name[name] = dict(entry)
    candidate = dict(manifest)
    candidate["files"] = [by_name[name] for name in sorted(by_name)]
    return canonical_json(candidate)


def file_hash(data: bytes) -> str:
    """SHA-256 hexadécimal minuscule des octets exacts d'un fichier clair."""
    if not isinstance(data, bytes):
        raise ValueError("Le hachage d'un fichier exige des octets.")
    return hashlib.sha256(data).hexdigest()


def file_stream_hash(stream: IO[bytes]) -> str:
    """Empreinte d'un fichier lu par blocs à partir de sa position courante."""
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(manifest: Mapping[str, object]) -> str:
    """Empreinte d'un artefact = SHA-256(canonical_manifest(manifest))."""
    return file_hash(canonical_manifest(manifest))
