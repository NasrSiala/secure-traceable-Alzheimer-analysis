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


def test_the_local_suite_never_sees_the_board_port(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-112: `SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board` runs the local suite first. A test
    in it that calls this script would open the board; the local phase gets no port, the board
    phase keeps it."""
    probe = "PYTEST=(bash -c 'echo \"seen=[${SAAM_ZYBO_PORT-unset}]\"' _)"
    result = bash_run(
        [
            "-c",
            f"source scripts/test-l.sh; {probe}; run_pytest_local -q; run_pytest -q",
        ],
        env={"SAAM_ZYBO_PORT": "COM9"},
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["seen=[unset]", "seen=[COM9]"]


def test_run_local_hands_no_port_to_any_pytest_call(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-112, end to end through run_local: every pytest call of the local phase (the tests and
    the host-side tests of the hardware part) runs without the port."""
    probe = "PYTEST=(bash -c 'echo \"seen=[${SAAM_ZYBO_PORT-unset}]\"' _)"
    result = bash_run(
        [
            "-c",
            (
                "source scripts/test-l.sh; run_npm_test() { :; }; make() { :; }; "
                f"{probe}; run_local"
            ),
        ],
        env={"SAAM_ZYBO_PORT": "COM9"},
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    seen = [line for line in result.stdout.split() if line.startswith("seen=")]
    assert seen and set(seen) == {"seen=[unset]"}, result.stdout


def _board_phase(
    bash_run: Callable[..., CompletedProcess[str]], pytest_output: str, port: str
) -> CompletedProcess[str]:
    """Run only run_board, with a pytest that prints `pytest_output` and succeeds."""
    probe = f"PYTEST=(bash -c 'echo \"{pytest_output}\"' _)"
    return bash_run(
        [
            "-c",
            f"source scripts/test-l.sh; {probe}; run_board && echo run_board-exit=0 || echo run_board-exit=$?",
        ],
        env={"SAAM_ZYBO_PORT": port},
        timeout=60,
    )


def test_a_board_run_in_which_every_test_was_skipped_is_not_board_access(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-113: the port is set but, for example, pyserial is missing: all 11 board tests skip and
    pytest exits 0. The script must not say that the board was used."""
    result = _board_phase(bash_run, "11 skipped, 489 deselected in 0.6s", "COM9")
    combined = result.stdout + result.stderr
    assert "no board test passed" in combined
    assert "board-access: no" in combined
    assert "board-access: tests-only" not in combined
    assert "run_board-exit=4" in combined


def test_a_board_run_in_which_a_test_passed_is_board_access(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = _board_phase(bash_run, "9 passed, 2 skipped, 489 deselected in 9s", "COM9")
    combined = result.stdout + result.stderr
    assert "board-access: tests-only" in combined
    assert "run_board-exit=0" in combined


def test_board_flag_without_a_port_says_why_the_board_tests_were_skipped(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """T1.9: board tests exist now; without SAAM_ZYBO_PORT they skip, and the script must not
    claim a pass or any board access."""
    result = bash_run(
        ["scripts/test-l.sh", "--board"],
        env={"SAAM_ZYBO_PORT": "", "SAAM_TEST_L_RUNNING": "1"},
        timeout=180,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-1500:]
    assert "SAAM_ZYBO_PORT is not set" in combined
    # The reason pytest gives for each skip (`-rs`), not only the script's own sentence.
    assert "nothing was opened" in combined
    assert "a skip is not a pass" in combined
    assert "board-access: no" in combined
    assert "board-access: tests-only" not in combined
    assert "skipped" in combined
    assert "passed" not in combined
