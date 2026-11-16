"""Start a process and stop it with everything it started (AUD-106).

`fabric/gateway-serve.sh` runs the gateway as a grandchild: the script starts npm, npm starts
node. A signal to the script alone ends the script and leaves the gateway running, with its port
and its wallet (`audit/round-8/tools/orphan-probe.sh` shows it on Linux). Stopping the tree needs
the operating system's own grouping:

  - POSIX: the script is started as the leader of a session of its own, and the whole process
    group receives the signal.
  - Windows: the script is put in a job object and the job is terminated. `taskkill /T` does not
    do it: the programs that Git Bash starts do not name the bash that started them as their
    parent, so a walk down the tree misses them.

The job object is assigned right after the start. A child created in the few milliseconds before
that would escape it; the script has not started one by then.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


class ProcessTree:
    def __init__(
        self, command: Sequence[str], *, cwd: Path, env: dict[str, str]
    ) -> None:
        self.process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=sys.platform != "win32",
        )
        self._job: int | None = None
        if sys.platform == "win32":
            self._job = _job_with(self.process.pid)

    def stop(self) -> None:
        """Stop the process and what it started, then wait for the process (30 s at most)."""
        if sys.platform == "win32":
            if self._job is not None:
                _end_job(self._job)
                self._job = None
            else:
                # The job could not be made: the walk down the tree is the best that is left.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                    capture_output=True,
                    check=False,
                )
        else:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def _job_with(pid: int) -> int | None:
    """A job object that holds the process `pid`, or None when Windows refuses."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    handle = kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    assigned = bool(handle) and bool(kernel32.AssignProcessToJobObject(job, handle))
    if handle:
        kernel32.CloseHandle(handle)
    if not assigned:
        kernel32.CloseHandle(job)
        return None
    return int(job)


def _end_job(job: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.TerminateJobObject(job, 1)
    kernel32.CloseHandle(job)
