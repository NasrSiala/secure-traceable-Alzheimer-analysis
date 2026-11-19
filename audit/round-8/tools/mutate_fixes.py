"""Mutations of the round-8 fixes, to show that each new test fails without its fix.

Same method as mutate_guard.py: one change, the related tests, restore. A mutation is *killed*
when a test fails. `D2` adds a file instead of editing one (a new script that sources the shared
library and is not named in it).

    py -3 audit/round-8/tools/mutate_fixes.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INTEGRITY = ROOT / "tests" / "integrity"
LIB = ROOT / "fabric" / "lib" / "gateway-run.sh"
SERVE = ROOT / "fabric" / "gateway-serve.sh"
INTEGRITY_TESTS = ["tests/integrity"]
DISPATCH_TESTS = ["tests/scripts/test_history_check_script.py"]


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
        "H1",
        INTEGRITY / "gateway_history.py",
        "timeout=self._timeout, trust_env=False",
        "timeout=self._timeout, trust_env=True",
        "AUD-110: the proxy variables are trusted again",
        INTEGRITY_TESTS,
    ),
    Mutation(
        "P1",
        INTEGRITY / "process_tree.py",
        "kernel32.TerminateJobObject(job, 1)",
        "pass",
        "AUD-106: the job is never terminated",
        INTEGRITY_TESTS,
    ),
    Mutation(
        "P2",
        INTEGRITY / "process_tree.py",
        "self._job = _job_with(self.process.pid)",
        "self._job = None",
        "AUD-106: no job, `taskkill /T` only (the first attempt)",
        INTEGRITY_TESTS,
    ),
    Mutation(
        "P3",
        INTEGRITY / "process_tree.py",
        "                _end_job(self._job)\n",
        "                self.process.terminate()\n",
        "AUD-106: only the script is signalled (the original behaviour)",
        INTEGRITY_TESTS,
    ),
    Mutation(
        "D1",
        LIB,
        "fabric/gateway-routes-check.sh, fabric/gateway-serve.sh and fabric/spike-latency.sh",
        "fabric/gateway-routes-check.sh and fabric/spike-latency.sh",
        "AUD-107: the library does not name gateway-serve.sh",
        DISPATCH_TESTS,
    ),
]


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
        crlf = b"\r\n" in raw
        old = mutation.old.encode()
        new = mutation.new.encode()
        if crlf:
            old = old.replace(b"\n", b"\r\n")
            new = new.replace(b"\n", b"\r\n")
        if raw.count(old) != 1:
            print(
                f"{mutation.key}  NOT APPLIED ({raw.count(old)} matches)  {mutation.note}"
            )
            survivors.append(f"{mutation.key}(not applied)")
            continue
        mutation.path.write_bytes(raw.replace(old, new))
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

    # D2: a new script that sources the shared library and is not named in it.
    stray = ROOT / "fabric" / "zz-stray.sh"
    stray.write_text(
        '#!/usr/bin/env bash\nsource "$(dirname "$0")/lib/gateway-run.sh"\n',
        newline="\n",
    )
    try:
        killed, last = run(DISPATCH_TESTS)
    finally:
        stray.unlink()
    print(
        f"D2  {'killed  ' if killed else 'SURVIVED'}  AUD-107: a new script sources the library and is not named  [{last}]"
    )
    if not killed:
        survivors.append("D2")
    print("survivors:", survivors or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
