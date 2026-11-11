"""Contract tests for scripts/test-l.sh. They do not start Fabric."""

from __future__ import annotations

from collections.abc import Callable
from subprocess import CompletedProcess


def test_help_exits_zero_and_documents_flags(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["scripts/test-l.sh", "--help"], timeout=60)
    assert result.returncode == 0
    assert "--fabric" in result.stdout
    assert "--board" in result.stdout
    assert "Zybo" in result.stdout


def test_unknown_option_exits_nonzero(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["scripts/test-l.sh", "--not-a-real-option"], timeout=60)
    assert result.returncode == 2
    assert "Unknown option" in result.stderr


def test_dry_run_excludes_fabric_and_board_without_running_them(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["scripts/test-l.sh", "--dry-run"], timeout=60)
    assert result.returncode == 0
    assert "not fabric and not board" in result.stdout
    assert "board-access: no" not in result.stdout


def test_dry_run_fabric_and_board_does_not_open_a_board(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(
        ["scripts/test-l.sh", "--dry-run", "--fabric", "--board"],
        timeout=60,
    )
    assert result.returncode == 0
    assert "-m fabric" in result.stdout
    assert "-m board" in result.stdout
    assert "board-access: no" in result.stdout
    assert "pyserial" not in result.stdout


def test_board_flag_runs_no_board_tests_and_does_not_open_a_device(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["scripts/test-l.sh", "--board"], timeout=180)
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "The board was not opened." in combined
    assert "board-access: no" in combined
