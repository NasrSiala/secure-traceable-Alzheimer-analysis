"""Canonical artifact manifests and SHA-256 helpers (ADR-04 / IF-05)."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import rfc8785


def _normalise_json(value: Any) -> Any:
    """Round JSON floats as required by NFR-12 without mutating the input."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Les nombres flottants doivent être finis.")
        rounded = round(value, 6)
        # JCS represents both signs of zero as the JSON number 0.
        return 0.0 if rounded == 0.0 else rounded

    if isinstance(value, dict):
        return {key: _normalise_json(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_normalise_json(item) for item in value]

    return value


def canonical_manifest(manifest: dict[str, Any]) -> bytes:
    """Return the JCS (RFC 8785) bytes for a manifest.

    Floating-point values are rounded to six decimal places before JCS
    serialization, and the manifest's payload file list is sorted by name.
    """
    if not isinstance(manifest, dict):
        # IF-05 standardizes invalid/non-canonicalizable manifests as ValueError.
        raise ValueError("Le manifeste doit être un objet JSON.")  # noqa: TRY004

    normalized = _normalise_json(manifest)
    files = normalized.get("files")
    if files is not None:
        if not isinstance(files, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str)
            for item in files
        ):
            raise ValueError("Chaque fichier du manifeste doit avoir un nom textuel.")
        normalized["files"] = sorted(files, key=lambda item: item["name"])
    try:
        return rfc8785.dumps(normalized)
    except Exception as exc:
        raise ValueError("Le manifeste ne peut pas être canonisé en JCS.") from exc


def artifact_hash(manifest: dict[str, Any]) -> str:
    """Return SHA-256 hex for the canonical JSON representation of a manifest."""
    return hashlib.sha256(canonical_manifest(manifest)).hexdigest()


def file_hash(payload: bytes | bytearray | memoryview) -> str:
    """Return SHA-256 hex for the exact payload bytes, without transformation."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("La charge utile doit être fournie sous forme d'octets.")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["artifact_hash", "canonical_manifest", "file_hash"]
