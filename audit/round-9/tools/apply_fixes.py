"""Round-9 edits to the owner's l10 files. Bytes in, bytes out; every anchor must occur once.

Run it once on the tree as the owner left it; a second run stops at the first anchor it no longer
finds.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def edit(relative: str, pairs: list[tuple[str, str]]) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"{relative} has CRLF"
    text = raw.decode("utf-8")
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{relative}: anchor found {text.count(old)} times: {old[:70]!r}")
        text = text.replace(old, new)
    path.write_bytes(text.encode("utf-8"))
    print("edited", relative)


# --- AUD-112 and AUD-113: scripts/test-l.sh ---------------------------------------------------
edit(
    "scripts/test-l.sh",
    [
        (
            """run_pytest() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "pytest-args: $*"
    return 0
  fi
  "${PYTEST[@]}" "$@"
}
""",
            """run_pytest() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "pytest-args: $*"
    return 0
  fi
  "${PYTEST[@]}" "$@"
}

# The local suite never sees the board port. A test inside it that calls this script (or opens a
# serial port) would otherwise reach the board during the local phase of
# `SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board` (AUD-112).
run_pytest_local() {
  (
    unset SAAM_ZYBO_PORT
    run_pytest "$@"
  )
}
""",
        ),
        (
            '  run_pytest -q -o addopts= -m "not fabric and not board" tests\n',
            '  run_pytest_local -q -o addopts= -m "not fabric and not board" tests\n',
        ),
        (
            '    run_pytest -q -o addopts= -m "not board" hw/host/tests\n',
            '    run_pytest_local -q -o addopts= -m "not board" hw/host/tests\n',
        ),
        (
            """  echo "Running tests marked board."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    run_pytest -q -o addopts= -m board "${targets[@]}"
    echo "board-access: no"
    return 0
  fi
  set +e
  "${PYTEST[@]}" -q -o addopts= -m board "${targets[@]}"
  local rc=$?
  set -e
""",
            """  echo "Running tests marked board."
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    run_pytest -q -rs -o addopts= -m board "${targets[@]}"
    echo "board-access: no"
    return 0
  fi
  # -rs prints why a test was skipped; the output is kept to tell a run that used the board from
  # one in which every board test was skipped (AUD-113).
  local log
  log=$(mktemp)
  set +e
  "${PYTEST[@]}" -q -rs -o addopts= -m board "${targets[@]}" 2>&1 | tee "${log}"
  local rc=${PIPESTATUS[0]}
  set -e
  local passed=0
  if grep -Eq '[0-9]+ passed' "${log}"; then
    passed=1
  fi
  rm -f "${log}"
""",
        ),
        (
            """  echo "board-access: tests-only"
}
""",
            """  if [[ "${passed}" -eq 0 ]]; then
    echo "SAAM_ZYBO_PORT is set but no board test passed: they were skipped (reasons above), so the board was not used."
    echo "board-access: no"
    return 4
  fi
  echo "board-access: tests-only"
}
""",
        ),
    ],
)

# --- AUD-112 and AUD-113: tests of the script -------------------------------------------------
edit(
    "tests/scripts/test_test_l.py",
    [
        (
            """def test_board_flag_without_a_port_says_why_the_board_tests_were_skipped(""",
            '''def test_the_local_suite_never_sees_the_board_port(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-112: `SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board` runs the local suite first. A test
    in it that calls this script would open the board; the local phase gets no port, the board
    phase keeps it."""
    probe = "PYTEST=(bash -c 'echo \\"seen=[${SAAM_ZYBO_PORT-unset}]\\"' _)"
    result = bash_run(
        ["-c", f"source scripts/test-l.sh; {probe}; run_pytest_local -q; run_pytest -q"],
        env={"SAAM_ZYBO_PORT": "COM9"},
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["seen=[unset]", "seen=[COM9]"]


def _board_phase(
    bash_run: Callable[..., CompletedProcess[str]], pytest_output: str, port: str
) -> CompletedProcess[str]:
    """Run only run_board, with a pytest that prints `pytest_output` and succeeds."""
    probe = f"PYTEST=(bash -c 'echo \\"{pytest_output}\\"' _)"
    return bash_run(
        ["-c", f"source scripts/test-l.sh; {probe}; run_board; echo run_board-exit=$?"],
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


def test_board_flag_without_a_port_says_why_the_board_tests_were_skipped(''',
        ),
    ],
)

# --- AUD-115: the Tcl interpreter is typed, the misplaced `type: ignore` goes ------------------
edit(
    "tests/scripts/test_bringup_config.py",
    [
        (
            "import zipfile\nfrom pathlib import Path\n\nimport pytest\n",
            (
                "import zipfile\nfrom pathlib import Path\nfrom typing import TYPE_CHECKING\n\nimport pytest\n\n"
                "if TYPE_CHECKING:\n    from tkinter import Tk\n"
            ),
        ),
        (
            """class Recorder:
    def __init__(self, interp: object) -> None:
        self.interp = interp

    def answer(self, command: str, value: str) -> None:
        self.interp.eval(f"mock_answer {{{command}}} {{{value}}}")  # type: ignore[attr-defined]
""",
            """class Recorder:
    def __init__(self, interp: Tk) -> None:
        self.interp = interp

    def answer(self, command: str, value: str) -> None:
        self.interp.eval(f"mock_answer {{{command}}} {{{value}}}")
""",
        ),
        (
            """        self.interp.eval(f"info script {{{script.as_posix()}}}")  # type: ignore[attr-defined]
        self.interp.eval(text)  # type: ignore[attr-defined]
""",
            """        self.interp.eval(f"info script {{{script.as_posix()}}}")
        self.interp.eval(text)
""",
        ),
        (
            """        raw = self.interp.eval("set ::calls")  # type: ignore[attr-defined]
        return [
            list(self.interp.splitlist(call)) for call in self.interp.splitlist(raw)
        ]  # type: ignore[attr-defined]
""",
            """        raw = self.interp.eval("set ::calls")
        return [
            list(self.interp.splitlist(call)) for call in self.interp.splitlist(raw)
        ]
""",
        ),
    ],
)
# The three `tcl.interp.eval(` calls of the test file carry the same ignore: all go.
config = ROOT / "tests" / "scripts" / "test_bringup_config.py"
config_text = config.read_bytes().decode("utf-8")
marker = "tcl.interp.eval(  # type: ignore[attr-defined]\n"
if config_text.count(marker) != 3:
    sys.exit(
        f"expected 3 `tcl.interp.eval(` ignores, found {config_text.count(marker)}"
    )
config.write_bytes(config_text.replace(marker, "tcl.interp.eval(\n").encode("utf-8"))
print("edited tests/scripts/test_bringup_config.py (three more)")
