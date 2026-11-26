"""Comparaison réelle pg_dump du snapshot Alembic et du schéma canonique."""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError

from tests.db.support import Postgres


def migrate(
    repo_root: Path, postgres: Postgres, database: str, direction: str = "up"
) -> None:
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="postgres",
            host="127.0.0.1",
            port=postgres.port,
            database=database,
        )
    )
    config = Config(str(repo_root / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        if direction == "up":
            command.upgrade(config, "head")
        else:
            command.downgrade(config, "base")
    engine.dispose()


def test_alembic_cli_reads_the_migration_connection(
    repo_root: Path, postgres: Postgres, empty_database: str
) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=os.environ
        | {
            "DATABASE_URL_MIGRATIONS": f"postgresql://postgres@127.0.0.1:{postgres.port}/{empty_database}"
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with psycopg.connect(postgres.dsn(empty_database)) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0001_initial"
        )


def test_initial_migration_matches_canonical_dump(
    repo_root: Path, postgres, empty_database: str
) -> None:
    baseline = empty_database
    with psycopg.connect(postgres.dsn(baseline)) as connection:
        connection.execute(
            (repo_root / "docs/specs/schema.sql").read_text(encoding="utf-8")
        )
    name = baseline + "_migrated"
    with psycopg.connect(postgres.dsn(), autocommit=True) as connection:
        connection.execute(
            psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(name))
        )
    migrate(repo_root, postgres, name)
    assert postgres.dump(name) == postgres.dump(baseline)
    # upgrade répété sans changement ; rollback puis upgrade reproduisent le schéma.
    migrate(repo_root, postgres, name)
    assert postgres.dump(name) == postgres.dump(baseline)
    migrate(repo_root, postgres, name, "down")
    with psycopg.connect(postgres.dsn(name)) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"
            ).fetchone()[0]
            == 0
        )
    migrate(repo_root, postgres, name)
    assert postgres.dump(name) == postgres.dump(baseline)


def test_schema_and_revision_are_atomic(
    repo_root: Path, postgres, empty_database: str
) -> None:
    with psycopg.connect(postgres.dsn(empty_database)) as connection:
        connection.execute("CREATE TABLE users (id integer)")
    with pytest.raises(ProgrammingError):
        migrate(repo_root, postgres, empty_database)
    with psycopg.connect(postgres.dsn(empty_database)) as connection:
        assert (
            connection.execute("SELECT to_regtype('user_role')").fetchone()[0] is None
        )
        assert (
            connection.execute("SELECT to_regclass('alembic_version')").fetchone()[0]
            is None
        )
