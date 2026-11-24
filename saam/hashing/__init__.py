"""Canonisation et hachage partagés selon ADR-04 (SVC-hashing, IF-05).

Les fichiers binaires sont hachés tels quels. Les producteurs utilisent
``canonical_json`` ou ``canonical_text`` pour leurs charges utiles textuelles,
puis consignent taille et SHA-256 de ces octets dans le manifeste.
"""

from .canonical import (
    artifact_hash,
    canonical_json,
    canonical_manifest,
    canonical_text,
    file_hash,
)

__all__ = [
    "artifact_hash",
    "canonical_json",
    "canonical_manifest",
    "canonical_text",
    "file_hash",
]
