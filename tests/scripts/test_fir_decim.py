"""Locks the generated FIR coefficients and the xsim bench of fir_decim (T3.19, 1/2)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saam.dsp.fir_fixed import coef_id, filter_decimate, load_coeffs

SIM = ROOT / "hw" / "sim"
RTL = ROOT / "hw" / "rtl" / "fir_decim.vhd"
PKG = ROOT / "hw" / "rtl" / "fir_coeffs_pkg.vhd"
JSON_PATH = ROOT / "saam" / "dsp" / "fir_coeffs.json"
TB = SIM / "fir_decim_tb.vhd"
BENCH = SIM / "test_fir.py"
SUPPORT = SIM / "fir_support.py"


def _vectors():
    sys.path.insert(0, str(SIM))
    from fir_support import VECTOR_FILE, vector_lines

    return VECTOR_FILE, vector_lines


def test_the_json_is_jcs_and_its_hash_is_the_package_id() -> None:
    payload = JSON_PATH.read_bytes()
    assert b"\n" not in payload
    document = json.loads(payload)
    assert list(document) == ["decimation", "fs_hz", "q", "taps"]
    canonical = json.dumps(
        document, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert payload == canonical
    identifier = hashlib.sha256(payload).hexdigest()[:8]
    assert identifier == coef_id()
    assert f'x"{identifier}"' in PKG.read_text(encoding="utf-8")
    assert "Do not edit" in PKG.read_text(encoding="utf-8")


def test_the_package_holds_the_same_taps_as_the_json() -> None:
    text = PKG.read_text(encoding="utf-8")
    body = text.split(":= (", 1)[1].split(");", 1)[0]
    packaged = [int(item) for item in re.findall(r"-?\d+", body)]
    assert packaged == list(load_coeffs())
    assert len(packaged) == 111
    assert packaged == packaged[::-1]
    assert sum(abs(coef) for coef in packaged) == 62379


def test_filter_decimate_matches_the_contract_on_length_and_edges() -> None:
    assert filter_decimate([]) == []
    assert filter_decimate([0, 0, 0, 0, 0]) == [0]
    assert len(filter_decimate([0] * 5055)) == 1011
    coeffs = load_coeffs()
    alone = filter_decimate([1000])
    assert alone == [((coeffs[0] * 1000 + (1 << 14)) >> 15)]
    first = filter_decimate([1, 2, 3])
    second = filter_decimate([4, 5, 6])
    high = filter_decimate([32767] * 111)
    low = filter_decimate([-32768] * 111)
    assert high[12] == 32767 and high[22] == 32767
    assert low[12] == -32768 and low[22] == -32768
    assert all(-32768 <= sample <= 32767 for sample in high + low)
    assert filter_decimate([1, 2, 3]) == first
    assert filter_decimate([4, 5, 6]) == second
    with pytest.raises(ValueError):
        filter_decimate([32768])
    with pytest.raises(ValueError):
        filter_decimate([True])  # type: ignore[list-item]


def test_the_vector_file_is_the_oracle_for_twenty_signals() -> None:
    path, vector_lines = _vectors()
    assert path.read_text(encoding="ascii").splitlines() == vector_lines()
    assert "0x46495231" in path.read_text(encoding="ascii")


def test_the_rtl_is_one_mac_and_has_no_bus() -> None:
    text = RTL.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "ieee.numeric_std" in lowered
    assert "ieee.std_logic_arith" not in lowered
    assert lowered.count("rising_edge") == 1
    assert "aresetn" in lowered
    assert text.count("* tap_sample") == 1
    for name in ("s_axi", "awvalid", "uart", "xpm_", "unimacro"):
        assert name not in lowered
    assert "fir_coeffs_pkg" in lowered
    assert "TAP_COUNT" in text


def test_the_vhdl_bench_covers_the_required_cases() -> None:
    text = TB.read_text(encoding="utf-8")
    assert "FIR_DECIM_TB PASSED" in text
    assert "fir_decim_random.txt" in text
    assert "5055" in text and "1011" in text
    assert "do_clear" in text and "do_reset" in text
    assert "MAC_EDGES" in text


def test_the_axi_cocotb_bench_uses_fir_fixed_and_holds_the_output() -> None:
    text = (SIM / "test_fir_axi.py").read_text(encoding="utf-8")
    assert "filter_decimate" in text
    assert "IN_READY high while an output is pending" in text
    assert "@cocotb.test" in text
    make = (SIM / "Makefile").read_text(encoding="utf-8")
    assert "TOPLEVEL=fir_axi MODULE=test_fir_axi" in make


def test_the_cocotb_bench_uses_fir_fixed_and_covers_the_required_cases() -> None:
    text = BENCH.read_text(encoding="utf-8")
    assert "filter_decimate" in text
    assert "coef_id" in text
    assert "@cocotb.test" in text
    for needle in ("5055", "1011", "clear", "reset", "20"):
        assert needle in text
    support = SUPPORT.read_text(encoding="utf-8")
    assert "0x46495231" in support
    assert "hashlib" not in text
    assert "sha256" not in text.lower()


def _vivado_bin() -> Path | None:
    value = os.environ.get("SAAM_VIVADO_BIN", "").strip()
    if value and Path(value).is_dir():
        return Path(value)
    root = os.environ.get("XILINX_VIVADO", "").strip()
    if root and (Path(root) / "bin").is_dir():
        return Path(root) / "bin"
    found = shutil.which("xvhdl") or shutil.which("xvhdl.bat")
    return Path(found).parent if found else None


@pytest.mark.skipif(shutil.which("make") is None, reason="no make")
def test_the_fir_testbench_passes_in_vivado_xsim() -> None:
    vivado = _vivado_bin()
    if vivado is None:
        pytest.skip(
            "no Vivado xsim (set SAAM_VIVADO_BIN or XILINX_VIVADO): the FIR testbench was not run"
        )
    env = {k: v for k, v in os.environ.items() if k != "SAAM_HW_SIM_REQUIRED"}
    env["SAAM_VIVADO_BIN"] = str(vivado)
    result = subprocess.run(
        ["make", "-C", str(SIM), "xsim-fir"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-2500:]
    assert "FIR_DECIM_TB PASSED" in combined
    assert "fir vectors: 20" in combined
