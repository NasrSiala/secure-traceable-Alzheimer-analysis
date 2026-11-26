"""Mots de passe Argon2id ; aucune donnée claire persistée."""

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type

HASHER = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Le mot de passe doit contenir entre 12 et 1024 caractères.")
    return HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, ValueError):
        return False
