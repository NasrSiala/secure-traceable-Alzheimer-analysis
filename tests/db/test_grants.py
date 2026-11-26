"""Privilèges réels du schéma canonique, dans un PostgreSQL jetable isolé.

T1.11 contrôle le baseline schema.sql ; T2.1 comparera ensuite les migrations.
Docker est requis : l'absence du moteur doit échouer, pas masquer ce contrôle.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from tests.arch.checks import TABLE_OWNERS

IMAGE = (
    "postgres:16.15-alpine@sha256:"
    "0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab"
)
PRIVILEGES = {
    "app_api": {
        "SELECT": set(TABLE_OWNERS),
        "INSERT": {
            "users",
            "validation_configs",
            "refresh_tokens",
            "login_attempts",
            "cases",
            "jobs",
            "verifications",
            "verification_items",
            "audit_events",
        },
        "UPDATE": {"users", "refresh_tokens"},
        "DELETE": {"refresh_tokens", "cases", "login_attempts"},
    },
    "app_worker": {
        "SELECT": set(TABLE_OWNERS) - {"users", "refresh_tokens", "login_attempts"},
        "INSERT": {
            "artifacts",
            "artifact_files",
            "agent_logs",
            "audit_events",
            "models",
        },
        "UPDATE": {"cases", "jobs", "models"},
        "DELETE": set(),
    },
}
COLUMN_UPDATES = {
    "app_api": {"models": {"is_active"}, "validation_configs": {"is_active"}},
    "app_worker": {
        "artifacts": {"anchor_status", "anchor_attempts", "tx_id", "anchored_at"},
    },
}


def docker(
    *args: str, input: str | None = None, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        input=input,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


@dataclass(frozen=True)
class Database:
    container: str

    def sql(self, query: str) -> subprocess.CompletedProcess[str]:
        return docker(
            "exec",
            "-i",
            self.container,
            "psql",
            "-X",
            "-A",
            "-t",
            "--username=postgres",
            "--dbname=postgres",
            "--set=ON_ERROR_STOP=1",
            "--set=VERBOSITY=verbose",
            input=query,
        )

    def rows(self, query: str) -> list[dict[str, object]]:
        result = self.sql(
            f"SELECT coalesce(json_agg(row_to_json(r)), '[]') FROM ({query}) r;"
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)


@pytest.fixture(scope="session")
def canonical_db(repo_root: Path) -> Iterator[Database]:
    name = "saam-arch-test-" + uuid4().hex
    result = docker(
        "run",
        "--detach",
        "--name",
        name,
        "--network=none",
        "--tmpfs=/var/lib/postgresql/data:rw",
        "--env=POSTGRES_HOST_AUTH_METHOD=trust",
        IMAGE,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    container = result.stdout.strip()
    # Ne retirer que le conteneur neuf dont Docker a renvoyé l'identifiant complet.
    assert re.fullmatch(r"[0-9a-f]{64}", container), result.stdout
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            # Le serveur temporaire d'initdb n'écoute pas en TCP : attendre le final.
            ready = docker(
                "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"
            )
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            pytest.fail("PostgreSQL temporaire indisponible après 60 secondes")
        db = Database(container)
        applied = db.sql(
            (repo_root / "docs/specs/schema.sql").read_text(encoding="utf-8")
        )
        assert applied.returncode == 0, applied.stderr
        yield db
    finally:
        removed = docker("rm", "--force", "--volumes", container)
        assert removed.returncode == 0, removed.stderr


@pytest.mark.parametrize("role", PRIVILEGES)
def test_exact_table_privileges(canonical_db: Database, role: str) -> None:
    rows = canonical_db.rows(f"""
        SELECT c.relname AS name, p.privilege,
               has_table_privilege('{role}', c.oid, p.privilege) AS allowed
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE',
                               'TRUNCATE','REFERENCES','TRIGGER']) p(privilege)
        WHERE n.nspname = 'public' AND c.relkind = 'r'
    """)
    assert {row["name"] for row in rows} == set(TABLE_OWNERS)
    for row in rows:
        expected = row["name"] in PRIVILEGES[role].get(str(row["privilege"]), set())
        assert row["allowed"] == expected, (role, row)


@pytest.mark.parametrize("role", PRIVILEGES)
def test_exact_column_update_privileges(canonical_db: Database, role: str) -> None:
    rows = canonical_db.rows(f"""
        SELECT c.relname AS name, a.attname AS column,
               has_column_privilege('{role}', c.oid, a.attnum, 'UPDATE') AS allowed
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE n.nspname = 'public' AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
    """)
    for row in rows:
        expected = row["name"] in PRIVILEGES[role]["UPDATE"] or row[
            "column"
        ] in COLUMN_UPDATES[role].get(str(row["name"]), set())
        assert row["allowed"] == expected, (role, row)


def test_application_roles_cannot_escalate(canonical_db: Database) -> None:
    rows = canonical_db.rows("""
        SELECT rolname AS name, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
               rolreplication, rolbypassrls FROM pg_roles
        WHERE rolname IN ('app_api', 'app_worker')
    """)
    assert {row["name"] for row in rows} == set(PRIVILEGES)
    for row in rows:
        assert row["rolcanlogin"] is True
        assert all(
            row[flag] is False
            for flag in (
                "rolsuper",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
                "rolbypassrls",
            )
        )
    assert (
        canonical_db.rows("""
        SELECT m.roleid FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
        WHERE r.rolname IN ('app_api', 'app_worker')
    """)
        == []
    )


@pytest.mark.parametrize("role", PRIVILEGES)
def test_schema_and_sequence_privileges(canonical_db: Database, role: str) -> None:
    rows = canonical_db.rows(f"""
        SELECT nspname AS name, has_schema_privilege('{role}', oid, 'USAGE') AS usage,
               has_schema_privilege('{role}', oid, 'CREATE') AS create
        FROM pg_namespace WHERE nspname IN ('public', 'langgraph')
    """)
    for row in rows:
        assert row["usage"] == (row["name"] == "public" or role == "app_worker")
        assert row["create"] == (row["name"] == "langgraph" and role == "app_worker")
    sequences = canonical_db.rows(f"""
        SELECT c.relname AS name, has_sequence_privilege('{role}', c.oid, 'USAGE') AS usage,
               has_sequence_privilege('{role}', c.oid, 'SELECT') AS select,
               has_sequence_privilege('{role}', c.oid, 'UPDATE') AS update
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'S'
    """)
    assert {row["name"] for row in sequences} == {
        "login_attempts_id_seq",
        "agent_logs_id_seq",
        "audit_events_id_seq",
    }
    assert all(
        row["usage"] is True and row["select"] is False and row["update"] is False
        for row in sequences
    )


@pytest.mark.parametrize(
    ("role", "query", "allowed"),
    [
        ("app_worker", "SELECT * FROM users LIMIT 0", False),
        ("app_worker", "SELECT * FROM refresh_tokens LIMIT 0", False),
        ("app_worker", "SELECT * FROM login_attempts LIMIT 0", False),
        ("app_worker", "UPDATE artifacts SET sha256 = sha256 WHERE false", False),
        (
            "app_worker",
            "UPDATE artifacts SET anchor_attempts = anchor_attempts WHERE false",
            True,
        ),
        ("app_worker", "DELETE FROM artifacts WHERE false", False),
        ("app_worker", "UPDATE cases SET status = status WHERE false", True),
        ("app_api", "UPDATE models SET sha256 = sha256 WHERE false", False),
        ("app_api", "UPDATE models SET is_active = is_active WHERE false", True),
        (
            "app_api",
            "UPDATE validation_configs SET version = version WHERE false",
            False,
        ),
        (
            "app_api",
            "UPDATE validation_configs SET is_active = is_active WHERE false",
            True,
        ),
        ("app_api", "INSERT INTO artifacts (id) SELECT NULL::uuid WHERE false", False),
        ("app_api", "INSERT INTO jobs (case_id) SELECT NULL::uuid WHERE false", True),
        ("app_api", "DELETE FROM cases WHERE false", True),
        ("app_api", "DELETE FROM audit_events WHERE false", False),
        ("app_api", "CREATE TABLE langgraph.probe (id integer)", False),
        ("app_worker", "CREATE TABLE langgraph.probe (id integer)", True),
        ("app_worker", "CREATE ROLE privilege_probe", False),
        ("app_api", "CREATE ROLE privilege_probe", False),
    ],
)
def test_postgresql_enforces_privileges(
    canonical_db: Database, role: str, query: str, allowed: bool
) -> None:
    # Transaction annulée même pour le DDL autorisé, aucune donnée de cas créée.
    result = canonical_db.sql(f"BEGIN; SET LOCAL ROLE {role}; {query}; ROLLBACK;")
    if allowed:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "42501" in result.stderr, result.stderr  # insufficient_privilege
