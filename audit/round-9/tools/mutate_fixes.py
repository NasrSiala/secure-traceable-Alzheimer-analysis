"""Mutations of the round-9 fixes: each new test must fail without its fix.

One change at a time, the related tests, restore. A mutation is *killed* when a test fails.

    py -3 audit/round-9/tools/mutate_fixes.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "test-l.sh"
GITIGNORE = ROOT / ".gitignore"
SCRIPT_TESTS = [
    "tests/scripts/test_test_l.py",
    "-k",
    "never_sees or run_local_hands or every_test_was_skipped or a_test_passed or without_a_port",
]
IGNORE_TESTS = [
    "tests/scripts/test_bringup_config.py",
    "-k",
    "vivado_project or stay_versioned",
]


@dataclass(frozen=True)
class Mutation:
    key: str
    path: Path
    old: str
    new: str
    note: str
    tests: list[str]


MUTATIONS = [
    Mutation(
        "J1",
        SCRIPT,
        "    unset SAAM_ZYBO_PORT\n",
        "",
        "AUD-112: the local phase keeps the port",
        SCRIPT_TESTS,
    ),
    Mutation(
        "J2",
        SCRIPT,
        '  run_pytest_local -q -o addopts= -m "not fabric and not board" tests\n',
        '  run_pytest -q -o addopts= -m "not fabric and not board" tests\n',
        "AUD-112: the tests of the local phase get the port",
        SCRIPT_TESTS,
    ),
    Mutation(
        "J3",
        SCRIPT,
        '    run_pytest_local -q -o addopts= -m "not board" hw/host/tests\n',
        '    run_pytest -q -o addopts= -m "not board" hw/host/tests\n',
        "AUD-112: the host tests of the local phase get the port",
        SCRIPT_TESTS,
    ),
    Mutation(
        "J4",
        SCRIPT,
        "if grep -Eq '[0-9]+ passed' \"${log}\"; then",
        "if true; then",
        "AUD-113: a run with no passed test counts as board access",
        SCRIPT_TESTS,
    ),
    Mutation(
        "J5",
        SCRIPT,
        "    return 4\n",
        "    return 0\n",
        "AUD-113: no failure status",
        SCRIPT_TESTS,
    ),
    Mutation(
        "J6",
        SCRIPT,
        '"${PYTEST[@]}" -q -rs -o addopts= -m board',
        '"${PYTEST[@]}" -q -o addopts= -m board',
        "AUD-113: the reasons of the skips are hidden again",
        SCRIPT_TESTS,
    ),
]
for number, pattern in enumerate(
    [
        "hw/**/*.xpr",
        "hw/**/*.cache/",
        "hw/**/*.runs/",
        "hw/**/*.hw/",
        "hw/**/*.ip_user_files/",
        "hw/**/*.sim/",
        "hw/**/*.gen/",
        "hw/**/*.srcs/",
    ],
    start=1,
):
    MUTATIONS.append(
        Mutation(
            f"G{number}",
            GITIGNORE,
            pattern + "\n",
            "",
            f"AUD-114: `{pattern}` removed",
            IGNORE_TESTS,
        )
    )
MUTATIONS.append(
    Mutation(
        "G9",
        GITIGNORE,
        "hw/**/*.sim/\n",
        "hw/**/sim/\n",
        "AUD-114: `*.sim/` widened to every `sim/` (hw/sim is versioned)",
        IGNORE_TESTS,
    )
)


def run(tests: list[str]) -> tuple[bool, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    lines = done.stdout.strip().splitlines()
    return done.returncode != 0, lines[-1] if lines else ""


def main() -> int:
    survivors: list[str] = []
    for mutation in MUTATIONS:
        raw = mutation.path.read_bytes()
        old = mutation.old.encode()
        if raw.count(old) != 1:
            print(
                f"{mutation.key}  NOT APPLIED ({raw.count(old)} matches)  {mutation.note}"
            )
            survivors.append(f"{mutation.key}(not applied)")
            continue
        mutation.path.write_bytes(raw.replace(old, mutation.new.encode()))
        try:
            killed, last = run(mutation.tests)
        finally:
            mutation.path.write_bytes(raw)
        print(
            f"{mutation.key}  {'killed  ' if killed else 'SURVIVED'}  {mutation.note}  [{last}]"
        )
        sys.stdout.flush()
        if not killed:
            survivors.append(mutation.key)
    print("survivors:", survivors or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
