"""Second round-9 edit: the Vivado project made by hand is ignored (AUD-114), two wrong sentences
(AUD-116), and a test for the ignore rules. Bytes in, bytes out; every anchor must occur once."""

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


edit(
    ".gitignore",
    [
        (
            "hw/build/\n",
            (
                "hw/build/\n"
                "\n"
                "# --- Matériel : projet Vivado créé à la main (T1.9), quel que soit son nom et son dossier sous hw/ ---\n"
                "# Il contient des caches, des journaux et des chemins de la machine ; build.tcl le regénère.\n"
                "hw/**/*.xpr\n"
                "hw/**/*.cache/\n"
                "hw/**/*.runs/\n"
                "hw/**/*.hw/\n"
                "hw/**/*.ip_user_files/\n"
                "hw/**/*.sim/\n"
                "hw/**/*.gen/\n"
                "hw/**/*.srcs/\n"
            ),
        )
    ],
)

edit(
    "hw/host/tests/test_bringup.py",
    [
        (
            "(BOOT.bin from hw/ps_app/bringup/build_app.tcl)",
            "(BOOT.bin from hw/ps_app/bringup/build_app.py)",
        )
    ],
)

edit(
    "hw/vivado/build.tcl",
    [
        (
            (
                "# Directories can be moved with SAAM_HW_BUILD_DIR and SAAM_HW_REPORT_DIR. Nothing outside them is\n"
                "# written, and no absolute path is recorded.\n"
            ),
            (
                "# Directories can be moved with SAAM_HW_BUILD_DIR and SAAM_HW_REPORT_DIR. Apart from the Vivado\n"
                "# project itself (the block design and the runs are written in it), nothing outside them is\n"
                "# written, and no absolute path is recorded in them.\n"
            ),
        )
    ],
)

edit(
    "tests/scripts/test_bringup_config.py",
    [
        (
            (
                "def test_the_build_products_are_not_versioned() -> None:\n"
                '    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")\n'
                '    assert "hw/build/" in gitignore\n'
            ),
            (
                "def test_the_build_products_are_not_versioned() -> None:\n"
                '    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")\n'
                '    assert "hw/build/" in gitignore\n'
                "\n"
                "\n"
                "def _ignored(path: str) -> bool:\n"
                "    done = subprocess.run(\n"
                '        ["git", "check-ignore", "-q", "--no-index", path],\n'
                "        cwd=ROOT,\n"
                "        capture_output=True,\n"
                "        check=False,\n"
                "    )\n"
                "    return done.returncode == 0\n"
                "\n"
                "\n"
                "@pytest.mark.parametrize(\n"
                '    "path",\n'
                "    [\n"
                '        "hw/SAAM/SAAM.xpr",\n'
                '        "hw/SAAM/SAAM.cache/wt/synthesis.wdf",\n'
                '        "hw/SAAM/SAAM.runs/impl_1/ISEWrap.sh",\n'
                '        "hw/SAAM/SAAM.hw/SAAM.lpr",\n'
                '        "hw/SAAM/SAAM.ip_user_files/README.txt",\n'
                '        "hw/SAAM/SAAM.sim/sim_1/behav/xsim/xsim.dir/run.sh",\n'
                '        "hw/SAAM/SAAM.gen/sources_1/bd/bringup/hdl/bringup.vhd",\n'
                '        "hw/SAAM/SAAM.srcs/sources_1/bd/bringup/bringup.bd",\n'
                '        "hw/another_name/other.xpr",\n'
                '        "hw/vivado/project/zybo.runs/synth_1/runme.sh",\n'
                "    ],\n"
                ")\n"
                "def test_a_vivado_project_made_by_hand_is_never_versioned(path: str) -> None:\n"
                '    """AUD-114: the project the user creates with the board (build.tcl opens it) holds caches,\n'
                "    logs, shell scripts (which the executable-bit test would then require) and machine paths.\n"
                '    Whatever its name and its folder under hw/, it is ignored."""\n'
                "    assert _ignored(path), path\n"
                "\n"
                "\n"
                "@pytest.mark.parametrize(\n"
                '    "path",\n'
                "    [\n"
                '        "hw/rtl/axil_reg_bringup.vhd",\n'
                '        "hw/vivado/build.tcl",\n'
                '        "hw/ps_app/bringup/hello.c",\n'
                '        "hw/ps_app/bringup/build_app.py",\n'
                '        "hw/reports/bringup-utilization.rpt",\n'
                '        "hw/reports/bringup-environment.json",\n'
                '        "hw/host/tests/test_bringup.py",\n'
                '        "hw/sim/Makefile",\n'
                '        "hw/BRINGUP.md",\n'
                "    ],\n"
                ")\n"
                "def test_the_sources_and_the_reports_of_the_hardware_part_stay_versioned(path: str) -> None:\n"
                "    assert not _ignored(path), path\n"
            ),
        )
    ],
)
