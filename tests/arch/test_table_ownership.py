"""Seul le propriétaire accède directement aux tables (Architecture §8)."""

import re
from pathlib import Path

import pytest

from tests.arch.checks import TABLE_OWNERS, modules, table_violations


def test_policy_covers_every_canonical_table(repo_root: Path) -> None:
    schema = (repo_root / "docs/specs/schema.sql").read_text(encoding="utf-8")
    assert set(re.findall(r"CREATE TABLE (\w+)", schema)) == set(TABLE_OWNERS)


def test_current_queries_are_in_their_owning_modules(repo_root: Path) -> None:
    assert [
        error
        for module, source in modules(repo_root)
        for error in table_violations(source, module)
    ] == []


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE users SET is_active = false",
        'INSERT INTO public."users" (email) VALUES (%s)',
        "DELETE FROM users WHERE false",
        "TRUNCATE TABLE users",
        "DROP TABLE IF EXISTS users",
        "SELECT * FROM users",
        "SELECT * FROM cases c JOIN users u ON true",
        "SELECT * FROM cases c, users u",
        "WITH u AS (SELECT * FROM users) SELECT * FROM u",
    ],
)
def test_case_module_rejects_access_to_accounts(query: str) -> None:
    assert table_violations(f"cursor.execute({query!r})", "saam.cases.probe")


def test_constants_and_concatenated_queries_are_resolved() -> None:
    source = "query = 'UPDATE ' + 'users SET is_active = false'\ncursor.execute(query)"
    assert table_violations(source, "saam.cases.probe")
    assert table_violations(source, "saam.identity.probe") == []


def test_comments_and_text_values_are_not_foreign_tables() -> None:
    query = "SELECT '-- FROM users' AS note FROM cases /* JOIN users */ -- UPDATE users"
    assert table_violations(f"cursor.execute({query!r})", "saam.cases.probe") == []


def test_dynamic_table_access_cannot_silently_pass() -> None:
    assert table_violations("cursor.execute(query)", "saam.cases.probe")
    assert table_violations(
        "cursor.execute(f'SELECT * FROM {table}')", "saam.cases.probe"
    )
    assert table_violations("cursor.execute('SELECT 1')", "saam.api.probe") == []


def test_model_declarations_follow_the_table_owner() -> None:
    source = "class User:\n    __tablename__ = 'users'"
    assert table_violations(source, "saam.identity.models") == []
    assert table_violations(source, "saam.cases.models")


def test_pipeline_logs_interface_is_read_only() -> None:
    assert (
        table_violations("db.execute('SELECT * FROM agent_logs')", "saam.pipeline.logs")
        == []
    )
    assert table_violations(
        "db.execute('DELETE FROM agent_logs')", "saam.pipeline.logs"
    )
    assert table_violations(
        "db.execute('SELECT * FROM langgraph.checkpoints')", "saam.api.probe"
    )
