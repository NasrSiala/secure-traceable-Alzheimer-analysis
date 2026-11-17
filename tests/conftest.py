"""Shared helpers for the L test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.db.support import empty_database as empty_database
from tests.db.support import postgres as postgres


@pytest.fixture
def migrated_database(repo_root: Path, postgres, empty_database: str) -> str:
    from tests.db.test_migration import migrate

    migrate(repo_root, postgres, empty_database)
    return empty_database


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


def bash_executable() -> str:
    override = os.environ.get("BASH")
    if override and Path(override).is_file():
        return override
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.is_file():
        return str(git_bash)
    found = shutil.which("bash")
    if found:
        return found
    raise RuntimeError("bash is required to run the Fabric lifecycle scripts")


@pytest.fixture(scope="session")
def bash_run() -> Callable[..., subprocess.CompletedProcess[str]]:
    return run_bash


def run_bash(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [bash_executable(), *args],
        cwd=cwd or ROOT,
        env=merged,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture
def _stop_after_test(
    bash_run: Callable[..., subprocess.CompletedProcess[str]],
) -> Iterator[None]:
    """Fabric tests: whatever the test did, the test network is stopped afterwards."""
    yield
    bash_run(["fabric/network.sh", "stop"], timeout=180)
