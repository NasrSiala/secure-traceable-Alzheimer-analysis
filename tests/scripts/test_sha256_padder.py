"""T3.18 (2/2, l12-sha256-padder-multiblock): checks on the SHA-256 padder and its vectors.

What runs here without a VHDL simulator:
  - the shared patterned vectors against hashlib (the oracle, ADR-12);
  - the framing of the last word (valid byte count, 0xFF in the ignored bytes);
  - the padder source: one clock, numeric_std, the existing core, no second compressor, no bus;
  - the cocotb bench and the VHDL testbench, by reading them.
What runs when Vivado xsim is installed:
  - sha256_padder_tb, which hashes the FIPS strings and every shared vector.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "hw" / "sim"
PADDER = ROOT / "hw" / "rtl" / "sha256_padder.vhd"
TESTBENCH = SIM / "sha256_padder_tb.vhd"
COCOTB_BENCH = SIM / "test_sha256_padder.py"
VECTORS = SIM / "vectors" / "sha256_padder_random.txt"

PADDER_TEXT = PADDER.read_text(encoding="utf-8")
PADDER_CODE = "\n".join(line.split("--")[0] for line in PADDER_TEXT.splitlines())
TB_TEXT = TESTBENCH.read_text(encoding="utf-8")
BENCH = COCOTB_BENCH.read_text(encoding="utf-8")


def _support():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("sha_support", SIM / "sha_support.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vector_rows() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for line in VECTORS.read_text(encoding="ascii").splitlines():
        if not line or line.startswith("#"):
            continue
        length_text, digest = line.split(" ")
        rows.append((int(length_text), digest))
    return rows


def test_the_shared_vectors_match_hashlib_and_the_fixed_seed() -> None:
    support = _support()
    rows = _vector_rows()
    expected_lengths = list(support.EXPLICIT_LENGTHS) + support.random_lengths()
    assert [length for length, _digest in rows] == expected_lengths
    assert len(support.random_lengths()) == 1000
    for length in (55, 56, 63, 64, 119, 120, 0, 4096):
        assert length in expected_lengths
    for length, digest in rows:
        message = support.pattern_message(length)
        assert hashlib.sha256(message).hexdigest() == digest, length
        assert 0 <= length <= 4096


def test_frame_words_keep_only_the_valid_bytes_of_the_last_word() -> None:
    support = _support()
    empty = support.frame_words(b"")
    assert empty == [(0xFFFFFFFF, 0)]
    for length in (1, 2, 3, 4, 5, 55, 56, 63, 64, 119, 120):
        message = support.pattern_message(length)
        beats = support.frame_words(message)
        assert beats[-1][1] == (length % 4 or 4)
        rebuilt = bytearray()
        for index, (word, nbytes) in enumerate(beats):
            raw = word.to_bytes(4, "big")
            if index == len(beats) - 1:
                assert nbytes in (1, 2, 3, 4)
                if nbytes < 4:
                    assert raw[nbytes:] == b"\xff" * (4 - nbytes)
                rebuilt.extend(raw[:nbytes])
            else:
                assert nbytes == 4
                rebuilt.extend(raw)
        assert bytes(rebuilt) == message


def test_the_padder_wraps_the_core_and_follows_the_hardware_conventions() -> None:
    lowered = PADDER_CODE.lower()
    assert "entity work.sha256_core" in lowered
    assert 'x"428a2f98"' not in lowered
    assert "ieee.numeric_std" in lowered
    for banned in (
        "std_logic_arith",
        "std_logic_unsigned",
        "unisim",
        "xpm",
        "s_axi",
        "uart",
        "wait for",
        "after ",
    ):
        assert banned not in lowered, banned
    assert len(re.findall(r"rising_edge\s*\(", lowered)) == 1
    assert "aresetn = '0'" in lowered
    for port in (
        "init",
        "in_valid",
        "in_ready",
        "in_data",
        "in_last",
        "in_bytes",
        "busy",
        "done",
        "digest",
    ):
        assert re.search(rf"\b{port}\s*:\s*(in|out)\b", PADDER_TEXT), port
    assert re.search(r"in_bytes\s*:\s*in\s+std_logic_vector\(2 downto 0\)", PADDER_TEXT)


def test_the_vhdl_testbench_names_the_fips_messages_and_its_verdict() -> None:
    assert "SHA256_PADDER_TB PASSED" in TB_TEXT
    assert "severity failure" in TB_TEXT
    assert "constant MSG_ABC" in TB_TEXT and '"abc"' in TB_TEXT
    assert "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" in TB_TEXT
    assert hashlib.sha256(b"").hexdigest() in TB_TEXT
    assert hashlib.sha256(b"abc").hexdigest() in TB_TEXT
    assert "sha256_padder_random.txt" in TB_TEXT
    for length in ("55", "56", "63", "64", "119", "120"):
        assert length in TB_TEXT


def test_the_cocotb_bench_covers_the_required_messages_without_a_second_sha256() -> (
    None
):
    assert "import hashlib" in BENCH
    assert BENCH.count("@cocotb.test") >= 6
    for needle in (
        "abc",
        "empty",
        "55",
        "56",
        "63",
        "64",
        "119",
        "120",
        "1000",
        "reset",
    ):
        assert needle in BENCH, needle
    assert "0x53484132" in BENCH
    for forbidden in ("0x428a2f98", "0x6a09e667", "rotr"):
        assert forbidden not in BENCH.lower()


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
def test_the_padder_testbench_passes_in_vivado_xsim() -> None:
    """The padder run: FIPS strings, boundary lengths and 1000 patterned messages."""
    vivado = _vivado_bin()
    if vivado is None:
        pytest.skip(
            "no Vivado xsim (set SAAM_VIVADO_BIN or XILINX_VIVADO): the padder testbench was not run"
        )
    env = {k: v for k, v in os.environ.items() if k != "SAAM_HW_SIM_REQUIRED"}
    env["SAAM_VIVADO_BIN"] = str(vivado)
    result = subprocess.run(
        ["make", "-C", str(SIM), "xsim-padder"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-2500:]
    assert "SHA256_PADDER_TB PASSED" in combined
    assert "padder vectors:" in combined
