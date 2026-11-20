"""The PS command loop is the C file, not the Python stand-in.

hw/host/tests/test_uart.py drives PsModel. This compiles saam_cmd.c with a stub
that keeps FIR OUT_VALID low for several status reads, then checks SHA-256 of
abc and a FIR vector. A driver that samples status once fails here.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "hw" / "ps_app" / "saam_cmd.c"
CHECK = ROOT / "hw" / "ps_app" / "saam_cmd_hostcheck.c"


@pytest.mark.skipif(shutil.which("gcc") is None, reason="no gcc")
def test_the_c_command_loop_waits_for_fir_and_hashes_abc(tmp_path: Path) -> None:
    exe = tmp_path / "saam_cmd_hostcheck"
    compiled = subprocess.run(
        ["gcc", "-Wall", "-Wextra", "-Werror", "-o", str(exe), str(CHECK), str(SRC)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
    assert ran.returncode == 0, f"{ran.returncode}\n{ran.stdout}\n{ran.stderr}"
    assert "SAAM_CMD_HOSTCHECK PASSED" in ran.stdout
