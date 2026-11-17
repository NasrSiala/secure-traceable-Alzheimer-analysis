"""Run the protocol test bench of axil_reg_bringup in the Vivado simulator, on the register as it
is or on a mutated copy.

    py -3 audit/round-9/tools/xsim/run_xsim.py                 # the register as it is
    py -3 audit/round-9/tools/xsim/run_xsim.py --mutations     # each mutation must fail the bench

Everything is built in a temporary directory: nothing is written in the repository. The Vivado
simulator tools are found under SAAM_VIVADO_BIN or the default install path of this workstation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REGISTER = ROOT / "hw" / "rtl" / "axil_reg_bringup.vhd"
BENCH = Path(__file__).resolve().parent / "tb_axil_reg_bringup.vhd"
BIN = Path(os.environ.get("SAAM_VIVADO_BIN", r"E:\AMDDesignTools\2025.2\Vivado\bin"))

# Each mutation: (name, old text, new text). Every one must make the bench fail.
MUTATIONS = [
    ("strobes ignored", "if s_axi_wstrb(byte) = '1' then", "if true then"),
    (
        "response dropped without bready",
        "elsif bvalid_r = '1' and s_axi_bready = '1' then",
        "elsif bvalid_r = '1' then",
    ),
    (
        "data dropped without rready",
        "elsif rvalid_r = '1' and s_axi_rready = '1' then",
        "elsif rvalid_r = '1' then",
    ),
    (
        "a second write accepted while the response is pending",
        "write_ok <= s_axi_awvalid and s_axi_wvalid and not bvalid_r;",
        "write_ok <= s_axi_awvalid and s_axi_wvalid;",
    ),
    (
        "a second read accepted while the data waits",
        "read_ok <= s_axi_arvalid and not rvalid_r;",
        "read_ok <= s_axi_arvalid;",
    ),
    (
        "address alone is enough to write",
        "write_ok <= s_axi_awvalid and s_axi_wvalid and not bvalid_r;",
        "write_ok <= s_axi_awvalid and not bvalid_r;",
    ),
    (
        "other word addresses write the register",
        'if s_axi_awaddr(3 downto 2) = "00" then',
        "if true then",
    ),
    (
        "other word addresses read the register",
        'if s_axi_araddr(3 downto 2) = "00" then',
        "if true then",
    ),
    (
        "the register is not cleared by reset",
        "        data_reg  <= (others => '0');\n",
        "",
    ),
    (
        "bresp is not OKAY",
        's_axi_bresp   <= "00";',
        's_axi_bresp   <= "10";',
    ),
    ("rresp is not OKAY", 's_axi_rresp   <= "00";', 's_axi_rresp   <= "10";'),
    (
        "the response is not cleared by reset",
        "        bvalid_r  <= '0';\n        rvalid_r  <= '0';\n      else",
        "      else",
    ),
]


def tool(name: str) -> str:
    for suffix in (".bat", ".exe", ""):
        candidate = BIN / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    sys.exit(f"{name} not found: set SAAM_VIVADO_BIN")


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=300,
    )


def simulate(register_text: str) -> tuple[bool, str]:
    """True when the bench printed ALL TESTS PASSED; the second item is the line that says why not."""
    with tempfile.TemporaryDirectory(prefix="saam-xsim-") as directory:
        work = Path(directory)
        (work / "axil_reg_bringup.vhd").write_text(
            register_text, encoding="utf-8", newline="\n"
        )
        shutil.copyfile(BENCH, work / BENCH.name)
        for source in ("axil_reg_bringup.vhd", BENCH.name):
            done = run([tool("xvhdl"), "--2008", source], work)
            if done.returncode != 0:
                return False, "compile: " + (done.stdout + done.stderr).strip()[-400:]
        done = run(
            [tool("xelab"), "-debug", "off", "tb_axil_reg_bringup", "-s", "tb"], work
        )
        if done.returncode != 0:
            return False, "elaborate: " + (done.stdout + done.stderr).strip()[-400:]
        done = run([tool("xsim"), "tb", "-runall"], work)
        output = done.stdout + done.stderr
        if (
            "ALL TESTS PASSED" in output
            and "Failure" not in output
            and "Error" not in output
        ):
            return True, "ALL TESTS PASSED"
        lines = [
            line for line in output.splitlines() if "CHECK" in line or "Failure" in line
        ]
        return False, (lines[0].strip() if lines else output.strip()[-300:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutations", action="store_true")
    arguments = parser.parse_args()
    text = REGISTER.read_text(encoding="utf-8").replace("\r\n", "\n")

    passed, why = simulate(text)
    print(f"register as it is: {'PASS' if passed else 'FAIL'}  {why}")
    if not arguments.mutations:
        return 0 if passed else 1
    if not passed:
        return 1

    survivors = []
    for name, old, new in MUTATIONS:
        if text.count(old) != 1:
            print(f"NOT APPLIED ({text.count(old)} matches)  {name}")
            survivors.append(f"{name} (not applied)")
            continue
        ok, why = simulate(text.replace(old, new))
        print(f"{'SURVIVED' if ok else 'killed  '}  {name}  [{why}]")
        if ok:
            survivors.append(name)
    print("survivors:", survivors or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
