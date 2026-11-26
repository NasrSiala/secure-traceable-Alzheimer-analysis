"""Initialisation des comptes, exclusivement par SVC-identity."""

import re
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import psycopg

from saam.identity.passwords import hash_password

Role = Literal["admin", "operator", "auditor"]


@dataclass(frozen=True)
class SeedAccount:
    email: str
    password: str
    role: Role
    display_name: str


def seed_accounts(
    connection: psycopg.Connection[tuple[Any, ...]], accounts: list[SeedAccount]
) -> UUID:
    if {account.role for account in accounts} != {
        "admin",
        "operator",
        "auditor",
    } or len(accounts) != 3:
        raise ValueError("Le seed requiert un compte par rôle.")
    if len({account.email for account in accounts}) != 3:
        raise ValueError("Les adresses des comptes doivent être distinctes.")
    for account in accounts:
        if (
            account.email != account.email.lower()
            or len(account.email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", account.email)
        ):
            raise ValueError("Adresse e-mail de seed invalide.")
        if (
            not 12 <= len(account.password) <= 1024
            or not 1 <= len(account.display_name) <= 100
        ):
            raise ValueError("Mot de passe ou nom de seed invalide.")
    admin_id = None
    for account in sorted(accounts, key=lambda item: item.role != "admin"):
        existing = connection.execute(
            "SELECT id, role FROM users WHERE email = %s FOR UPDATE", (account.email,)
        ).fetchone()
        if existing:
            if existing[1] != account.role:
                raise ValueError(
                    "Un compte existant porte un autre rôle ; seed annulé."
                )
            user_id = existing[0]
        else:
            row = connection.execute(
                "INSERT INTO users (email, password_hash, role, display_name, created_by) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    account.email,
                    hash_password(account.password),
                    account.role,
                    account.display_name,
                    admin_id,
                ),
            ).fetchone()
            assert row is not None
            user_id = row[0]
        if account.role == "admin":
            admin_id = user_id
    assert isinstance(admin_id, UUID)
    return admin_id
