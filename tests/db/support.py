"""PostgreSQL neuf pour migrations et tests métier ; aucun volume applicatif."""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

IMAGE = "postgres:16.15-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab"


@dataclass(frozen=True)
class Postgres:
    container: str
    port: int

    def dsn(self, database: str = "postgres", role: str = "postgres") -> str:
        return make_conninfo(
            host="127.0.0.1", port=self.port, dbname=database, user=role
        )

    def dump(self, database: str) -> str:
        result = subprocess.run(
            [
                "docker",
                "exec",
                self.container,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                database,
                "--schema-only",
                "--exclude-table=public.alembic_version",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return "\n".join(
            line
            for line in result.stdout.splitlines()
            if not line.startswith(("--", "\\restrict", "\\unrestrict"))
        )


@pytest.fixture(scope="session")
def postgres() -> Iterator[Postgres]:
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "saam-db-test-" + uuid4().hex,
            "--publish=127.0.0.1::5432",
            "--tmpfs=/var/lib/postgresql/data:rw",
            "--env=POSTGRES_HOST_AUTH_METHOD=trust",
            IMAGE,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    container = result.stdout.strip()
    assert re.fullmatch("[0-9a-f]{64}", container)
    try:
        port_result = subprocess.run(
            ["docker", "port", container, "5432/tcp"],
            capture_output=True,
            text=True,
            check=True,
        )
        match = re.fullmatch(r"127\.0\.0\.1:(\d+)\s*", port_result.stdout)
        assert match, port_result.stdout
        server = Postgres(container, int(match[1]))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(server.dsn(), connect_timeout=1) as connection:
                    connection.execute("SELECT 1")
                break
            except psycopg.OperationalError:
                time.sleep(0.25)
        else:
            pytest.fail("PostgreSQL temporaire indisponible")
        yield server
    finally:
        subprocess.run(
            ["docker", "rm", "-f", "-v", container],
            capture_output=True,
            check=True,
            timeout=30,
        )


@pytest.fixture
def empty_database(postgres: Postgres) -> str:
    name = "test_" + uuid4().hex
    with psycopg.connect(postgres.dsn(), autocommit=True) as connection:
        connection.execute(
            psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(name))
        )
    return name
