"""Why the Windows branch of `process_tree.py` uses a job object and not `taskkill /T` (AUD-106).

A Git Bash script starts `sleep 300 &` and waits (the stand-in for npm and node under
gateway-serve.sh). The script is stopped twice, each time on a fresh tree: with `taskkill /F /T`,
then with a job object that the process was assigned to. After each stop, `kill -0` run by another
bash says whether the grandchild is still alive. A survivor is killed so that the probe leaves
nothing behind.

    py -3 audit/round-8/tools/windows_tree_probe.py     (Windows with Git Bash only)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if sys.platform != "win32":
    sys.exit("Windows only: the POSIX branch is checked by orphan-probe.sh")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "integrity"))

from process_tree import ProcessTree

BASH = r"C:\Program Files\Git\bin\bash.exe"


def alive(pid: str) -> bool:
    done = subprocess.run(
        [BASH, "-c", f"kill -0 {pid} 2>/dev/null"], capture_output=True, check=False
    )
    return done.returncode == 0


def start(pid_file: Path) -> ProcessTree:
    return ProcessTree(
        [BASH, "-c", f'sleep 300 & echo $! > "{pid_file.as_posix()}"; wait'],
        cwd=ROOT,
        env=dict(os.environ),
    )


def grandchild_of(pid_file: Path) -> str:
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            return pid_file.read_text().strip()
        time.sleep(0.1)
    raise SystemExit("the script did not start its child")


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        walk_file = Path(directory) / "walk.pid"
        job_file = Path(directory) / "job.pid"

        walk = start(walk_file)
        walked = grandchild_of(walk_file)
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(walk.process.pid)],
            capture_output=True,
            check=False,
        )
        time.sleep(1)
        print(f"taskkill /F /T : grandchild alive afterwards = {alive(walked)}")
        subprocess.run(
            [BASH, "-c", f"kill -9 {walked}"], capture_output=True, check=False
        )

        job = start(job_file)
        in_job = grandchild_of(job_file)
        job.stop()
        time.sleep(1)
        print(f"job object     : grandchild alive afterwards = {alive(in_job)}")
        subprocess.run(
            [BASH, "-c", f"kill -9 {in_job}"], capture_output=True, check=False
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
