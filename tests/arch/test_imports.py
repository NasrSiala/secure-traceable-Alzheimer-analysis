"""Frontières du paquet saam et preuve réelle des contrats import-linter."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.arch.checks import import_violations, modules


def test_current_modules_respect_the_architecture(repo_root: Path) -> None:
    assert [
        error
        for module, source in modules(repo_root)
        for error in import_violations(source, module)
    ] == []


@pytest.mark.parametrize(
    "source",
    [
        "import saam.pipeline.worker",
        "from saam import pipeline",
        "from ..pipeline import worker",
        "import importlib; importlib.import_module('saam.pipeline.worker')",
        "import serial",
        "from hw.host import zybo_client",
        "import grpc",
        "from saam.identity.models import User",
    ],
)
def test_api_rejects_execution_hardware_and_direct_models(source: str) -> None:
    assert import_violations(source, "saam.api.probe")


def test_domain_and_library_cannot_import_entry_points() -> None:
    assert import_violations("from saam.api import main", "saam.registry.probe")
    assert import_violations("import saam.registry", "saam.hashing.probe")
    assert import_violations("import saam.verification", "saam.registry.probe")


def test_explicit_read_only_logs_interface_remains_separate() -> None:
    assert (
        import_violations(
            "from saam.pipeline.logs import list_for_case", "saam.api.probe"
        )
        == []
    )
    assert import_violations("import saam.pipeline.logstream", "saam.api.probe")
    assert import_violations("from . import worker", "saam.pipeline.logs")
    assert import_violations("from . import health", "saam.registry.probe") == []


@pytest.mark.parametrize(
    ("source", "allowed"),
    [
        ("from saam import pipeline as pipeline", False),
        ("import serial", False),
        ("from saam.pipeline.logs import list_for_case as list_for_case", True),
    ],
)
def test_real_import_linter_enforces_the_contracts(
    repo_root: Path, tmp_path: Path, source: str, allowed: bool
) -> None:
    shutil.copytree(
        repo_root / "saam",
        tmp_path / "saam",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copyfile(repo_root / "pyproject.toml", tmp_path / "pyproject.toml")
    (tmp_path / "saam/api/probe.py").write_text(source + "\n", encoding="utf-8")
    (tmp_path / "saam/pipeline/logs.py").write_text(
        "def list_for_case(): return []\n", encoding="utf-8"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from importlinter.cli import lint_imports_command; lint_imports_command()",
            "--no-cache",
        ],
        cwd=tmp_path,
        env=os.environ | {"PYTHONPATH": str(tmp_path), "PYTHONIOENCODING": "utf-8"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert result.returncode == (0 if allowed else 1), result.stdout + result.stderr
    if not allowed:
        assert "BROKEN" in result.stdout and "saam.api.probe" in result.stdout
