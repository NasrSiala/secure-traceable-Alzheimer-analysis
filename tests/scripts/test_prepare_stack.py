"""Protection des secrets lors de la préparation de la pile Docker."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def preparation(repo_root: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "prepare_stack", repo_root / "scripts" / "prepare-stack.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stack_root(tmp_path: Path, repo_root: Path) -> Path:
    (tmp_path / ".env.example").write_bytes((repo_root / ".env.example").read_bytes())
    return tmp_path


def test_preparation_is_repeatable_without_replacing_secrets(
    preparation: ModuleType, stack_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preparation, "prepare_tls", lambda _directory: None)
    preparation.prepare(stack_root)
    original_environment = (stack_root / ".env").read_bytes()
    original_tokens = (stack_root / "secrets" / "agent-tokens.json").read_bytes()
    preparation.prepare(stack_root)
    assert (stack_root / ".env").read_bytes() == original_environment
    assert (
        stack_root / "secrets" / "agent-tokens.json"
    ).read_bytes() == original_tokens
    values = preparation.read_environment(stack_root / ".env")
    tokens = json.loads(original_tokens)
    assert len(tokens) == 9 and len(set(tokens.values())) == 9
    assert values["APP_API_PASSWORD"] != values["APP_WORKER_PASSWORD"]
    assert "postgresql://app_api:" in values["DATABASE_URL_API"]
    assert "postgresql://app_worker:" in values["DATABASE_URL_WORKER"]
    assert tokens["verifier"] == values["AGENT_TOKEN_VERIFIER"]


def test_incomplete_existing_environment_is_preserved(
    preparation: ModuleType, stack_root: Path
) -> None:
    existing = "POSTGRES_PASSWORD=private-password\n"
    (stack_root / ".env").write_text(existing, encoding="utf-8")
    with pytest.raises(ValueError, match="APP_API_PASSWORD"):
        preparation.prepare_environment(stack_root)
    assert (stack_root / ".env").read_text(encoding="utf-8") == existing


def test_exclusive_write_preserves_an_existing_file(
    preparation: ModuleType, tmp_path: Path
) -> None:
    target = tmp_path / "secret"
    target.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preparation.write_new(target, "replacement")
    assert target.read_text(encoding="utf-8") == "existing"


def test_incomplete_tls_pair_is_preserved(
    preparation: ModuleType, tmp_path: Path
) -> None:
    key = tmp_path / "localhost.key"
    key.write_text("existing-key", encoding="utf-8")
    with pytest.raises(ValueError, match="Paire TLS incomplète"):
        preparation.prepare_tls(tmp_path)
    assert key.read_text(encoding="utf-8") == "existing-key"


def test_mismatching_tokens_are_not_overwritten(
    preparation: ModuleType, stack_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preparation, "prepare_tls", lambda _directory: None)
    preparation.prepare(stack_root)
    tokens = stack_root / "secrets" / "agent-tokens.json"
    tokens.write_text('{"verifier":"existing-token"}', encoding="utf-8")
    with pytest.raises(ValueError, match="diffèrent"):
        preparation.prepare(stack_root)
    assert tokens.read_text(encoding="utf-8") == '{"verifier":"existing-token"}'
