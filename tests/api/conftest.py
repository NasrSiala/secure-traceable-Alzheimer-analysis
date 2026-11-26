"""Comptes synthétiques et API réelle sur PostgreSQL temporaire."""

import secrets
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.identity.auth import IdentityService
from saam.identity.seed import SeedAccount, seed_accounts

PASSWORD = "auth-test-password-12345"


@pytest.fixture
def auth_service(postgres, migrated_database: str) -> IdentityService:
    url = postgres.dsn(migrated_database, "app_api")
    with psycopg.connect(url) as connection:
        seed_accounts(
            connection,
            [
                SeedAccount("admin@demo.test", PASSWORD, "admin", "Admin démo"),
                SeedAccount(
                    "operator@demo.test", PASSWORD, "operator", "Opérateur démo"
                ),
                SeedAccount("auditor@demo.test", PASSWORD, "auditor", "Auditeur démo"),
            ],
        )
    return IdentityService(url, secrets.token_hex(32))


@pytest.fixture
def auth_client(auth_service: IdentityService) -> Iterator[TestClient]:
    with TestClient(
        create_app(identity=auth_service),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as client:
        yield client
