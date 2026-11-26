"""Seed sous le rôle app_api, idempotence et transaction réelle."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from saam.identity.passwords import verify_password


@pytest.fixture
def seed_module(repo_root: Path):
    spec = importlib.util.spec_from_file_location(
        "seed_script", repo_root / "scripts/seed.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seed_values(postgres, migrated_database: str) -> dict[str, str]:
    values = {"DATABASE_URL_API": postgres.dsn(migrated_database, "app_api")}
    for role in ("ADMIN", "OPERATOR", "AUDITOR"):
        values[f"SEED_{role}_EMAIL"] = f"{role.lower()}@demo.test"
        values[f"SEED_{role}_PASSWORD"] = f"seed-test-{role}-password"
    return values


def test_seed_is_idempotent_and_hashes_passwords(
    seed_module, seed_values, postgres, migrated_database
) -> None:
    seed_module.seed(seed_values)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        before = connection.execute(
            "SELECT id, email, password_hash, role FROM users ORDER BY email"
        ).fetchall()
        assert len(before) == 3
        assert all(
            verify_password(row[2], seed_values[f"SEED_{row[3].upper()}_PASSWORD"])
            for row in before
        )
        config = connection.execute(
            "SELECT version, conf_high::text, quality_min::text, lexicon_version, is_active FROM validation_configs"
        ).fetchall()
        assert config == [(1, "0.700", "0.900", "v1", True)]
    seed_module.seed(seed_values)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        assert (
            connection.execute(
                "SELECT id, email, password_hash, role FROM users ORDER BY email"
            ).fetchall()
            == before
        )
        connection.execute("UPDATE users SET is_active=false WHERE role='operator'")
    seed_module.seed(seed_values)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        assert (
            connection.execute(
                "SELECT is_active FROM users WHERE role='operator'"
            ).fetchone()[0]
            is False
        )


def test_conflicting_configuration_rolls_back_new_accounts(
    seed_module, seed_values, postgres, migrated_database
) -> None:
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        connection.execute(
            "INSERT INTO validation_configs (version, conf_high, quality_min, lexicon_version) VALUES (1, 0.8, 0.9, 'v1')"
        )
    with pytest.raises(ValueError, match="configuration"):
        seed_module.seed(seed_values)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0


@pytest.mark.parametrize("field", ["SEED_ADMIN_PASSWORD", "SEED_OPERATOR_EMAIL"])
def test_invalid_seed_writes_nothing(
    seed_module, seed_values, field, postgres, migrated_database
) -> None:
    seed_values[field] = ""
    with pytest.raises(ValueError):
        seed_module.seed(seed_values)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0


def test_seed_cli_twice_without_secret_output(
    repo_root, seed_values, tmp_path: Path
) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(f"{name}={value}" for name, value in seed_values.items()),
        encoding="utf-8",
    )
    env = {name: value for name, value in os.environ.items() if name not in seed_values}
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "scripts/seed.py", "--env-file", str(path)],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert all(
            value not in result.stdout + result.stderr
            for name, value in seed_values.items()
            if "PASSWORD" in name
        )
