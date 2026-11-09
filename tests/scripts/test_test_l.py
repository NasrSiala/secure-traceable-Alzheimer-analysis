"""Contract tests for scripts/test-l.sh. They do not start Fabric."""

from __future__ import annotations

import re
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


def _run_npm_test_without(
    bash_run: Callable[..., CompletedProcess[str]],
    *,
    node: bool,
    docker: bool,
    extra_env: dict[str, str] | None = None,
) -> CompletedProcess[str]:
    """Source test-l.sh and call run_npm_test with Node and/or Docker made unavailable.

    The availability probes are plain functions, so the test replaces them: it does
    not depend on what is installed on the machine that runs it.
    """
    probes = (
        f"node_available() {{ return {0 if node else 1}; }}; "
        f"docker_available() {{ return {0 if docker else 1}; }}; "
    )
    return bash_run(
        [
            "-c",
            "source scripts/test-l.sh; "
            + probes
            + "run_npm_test chaincode/provenance; echo reached-end",
        ],
        env=extra_env,
        timeout=60,
    )


def test_typescript_check_fails_when_neither_node_nor_docker_exists(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-037: a green run must not mean the TypeScript was never looked at."""
    result = _run_npm_test_without(
        bash_run, node=False, docker=False, extra_env={"SAAM_TEST_SKIP_NODE": ""}
    )
    assert result.returncode == 3
    assert "needs Node 20 or a running Docker daemon" in result.stderr
    assert "SAAM_TEST_SKIP_NODE=1" in result.stderr
    assert "reached-end" not in result.stdout


def test_typescript_check_can_be_skipped_only_on_request_and_says_so(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = _run_npm_test_without(
        bash_run, node=False, docker=False, extra_env={"SAAM_TEST_SKIP_NODE": "1"}
    )
    assert result.returncode == 0
    assert "SKIPPED: chaincode/provenance npm test" in result.stdout
    assert "reached-end" in result.stdout


def test_node_image_comes_from_compose_and_is_pinned(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(
        [
            "-c",
            "source scripts/test-l.sh; node_image",
        ],
        timeout=60,
    )
    assert result.returncode == 0
    assert re.fullmatch(
        r"node:\d+\.\d+\.\d+-bookworm@sha256:[0-9a-f]{64}", result.stdout.strip()
    ), result.stdout


def _select_pytest_with(
    bash_run: Callable[..., CompletedProcess[str]], definitions: str
) -> CompletedProcess[str]:
    """Source test-l.sh, replace the interpreters by shell functions, call select_pytest."""
    return bash_run(
        [
            "-c",
            "source scripts/test-l.sh; "
            + definitions
            + 'select_pytest; echo "picked: ${PYTEST[*]}"',
        ],
        timeout=60,
    )


def test_pytest_is_found_through_python3_alone(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-045: stock Ubuntu has `python3` and no `python`; the script used to give up."""
    result = _select_pytest_with(
        bash_run,
        'python3() { [[ "$1" == -c ]]; }; python() { return 127; }; py() { return 127; }; ',
    )
    assert result.returncode == 0, result.stderr
    assert "picked: python3 -m pytest" in result.stdout


def test_pytest_falls_back_to_python_then_the_windows_launcher(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    python_only = _select_pytest_with(
        bash_run,
        'python3() { return 1; }; python() { [[ "$1" == -c ]]; }; py() { return 127; }; ',
    )
    assert "picked: python -m pytest" in python_only.stdout
    launcher_only = _select_pytest_with(
        bash_run,
        'python3() { return 1; }; python() { return 1; }; py() { [[ "$1 $2" == "-3 -c" ]]; }; ',
    )
    assert "picked: py -3 -m pytest" in launcher_only.stdout


def test_missing_pytest_is_reported_with_exit_3(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = _select_pytest_with(
        bash_run,
        "python3() { return 1; }; python() { return 1; }; py() { return 1; }; ",
    )
    assert result.returncode == 3
    assert "pytest is not available" in result.stderr


def test_help_documents_the_typescript_check(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["scripts/test-l.sh", "--help"], timeout=60)
    assert "SAAM_TEST_SKIP_NODE=1" in result.stdout
    assert "fails" in result.stdout


def test_sourcing_the_script_runs_nothing(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["-c", "source scripts/test-l.sh; echo loaded"], timeout=60)
    assert result.returncode == 0
    assert result.stdout.strip() == "loaded"


def test_board_flag_runs_no_board_tests_and_does_not_open_a_device(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["scripts/test-l.sh", "--board"], timeout=180)
    combined = result.stdout + result.stderr
    assert result.returncode == 0
    assert "The board was not opened." in combined
    assert "board-access: no" in combined
