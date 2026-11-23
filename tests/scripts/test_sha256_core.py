"""T3.18 (1/2, l11-sha256-compress-core): checks on the SHA-256 compression core and its benches.

What runs here without a VHDL simulator:
  - the constants of the core (round constants K, initial hash H0) against FIPS 180-4, derived
    here from the square and cube roots of the first primes, not copied;
  - the expected digests written in the VHDL testbench against `hashlib`;
  - the conventions of the hardware part (VHDL-2008, numeric_std only, one clock, synchronous
    active-low reset, no vendor primitive);
  - the make flow: which backend it picks and how it fails or skips when no tool is there.
What runs only when a simulator is on the machine:
  - the VHDL testbench in Vivado xsim (`make -C hw/sim xsim`), skipped otherwise, with the reason.
The cocotb bench (hw/sim/test_sha256.py) needs GHDL and cocotb: it is not run by this file.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "hw" / "sim"
CORE = ROOT / "hw" / "rtl" / "sha256_core.vhd"
TESTBENCH = SIM / "sha256_core_tb.vhd"
MAKEFILE = SIM / "Makefile"
COCOTB_MK = SIM / "cocotb.mk"
COCOTB_BENCH = SIM / "test_sha256.py"

PRIMES = [
    2,
    3,
    5,
    7,
    11,
    13,
    17,
    19,
    23,
    29,
    31,
    37,
    41,
    43,
    47,
    53,
    59,
    61,
    67,
    71,
    73,
    79,
]
PRIMES += [
    83,
    89,
    97,
    101,
    103,
    107,
    109,
    113,
    127,
    131,
    137,
    139,
    149,
    151,
    157,
    163,
    167,
]
PRIMES += [
    173,
    179,
    181,
    191,
    193,
    197,
    199,
    211,
    223,
    227,
    229,
    233,
    239,
    241,
    251,
    257,
    263,
]
PRIMES += [269, 271, 277, 281, 283, 293, 307, 311]


def _icbrt(n: int) -> int:
    low, high = 0, 1 << ((n.bit_length() // 3) + 2)
    while low < high:
        mid = (low + high + 1) // 2
        if mid**3 <= n:
            low = mid
        else:
            high = mid - 1
    return low


# FIPS 180-4 5.3.3 and 4.2.2: the first 32 bits of the fractional parts of the square roots of
# the first 8 primes, and of the cube roots of the first 64 primes.
H0 = [math.isqrt(p << 64) & 0xFFFFFFFF for p in PRIMES[:8]]
K = [_icbrt(p << 96) & 0xFFFFFFFF for p in PRIMES[:64]]

CORE_TEXT = CORE.read_text(encoding="utf-8") if CORE.exists() else ""
# The code without its comments: the rules below are about what the core does, not what it says.
CORE_CODE = "\n".join(line.split("--")[0] for line in CORE_TEXT.splitlines())
TB_TEXT = TESTBENCH.read_text(encoding="utf-8") if TESTBENCH.exists() else ""


def _block(text: str, name: str) -> str:
    start = text.index(f"constant {name}")
    return text[start : text.index(");", start)]


def _words(block: str) -> list[int]:
    return [int(value, 16) for value in re.findall(r'x"([0-9a-fA-F]{8})"', block)]


def test_the_derived_constants_are_the_well_known_ones() -> None:
    # Two values everybody knows, to make sure the derivation above is right.
    assert H0[0] == 0x6A09E667
    assert H0[7] == 0x5BE0CD19
    assert K[0] == 0x428A2F98
    assert K[63] == 0xC67178F2


def test_the_round_constants_are_those_of_fips_180_4() -> None:
    assert _words(_block(CORE_TEXT, "K ")) == K


def test_the_initial_hash_values_are_those_of_fips_180_4() -> None:
    assert _words(_block(CORE_TEXT, "H_INIT")) == H0


# --------------------------------------------------------------------------------------------
# The testbench carries its expected digests as literals: check them against hashlib
# --------------------------------------------------------------------------------------------


def _vectors() -> dict[str, tuple[bytes, str]]:
    messages = dict(
        re.findall(r'constant MSG_(\w+)\s*:\s*string\s*:=\s*"([^"]*)"', TB_TEXT)
    )
    digests = dict(
        re.findall(r'constant DIGEST_(\w+)\s*:[^:]*:=\s*x"([0-9a-f]{64})"', TB_TEXT)
    )
    # DIGEST_H0 is the value of H after a reset, not the digest of a message: it has no MSG_.
    assert messages and set(messages) <= set(digests), (
        sorted(messages),
        sorted(digests),
    )
    return {name: (messages[name].encode("ascii"), digests[name]) for name in messages}


def test_the_h0_literal_of_the_testbench_is_the_initial_hash_value() -> None:
    match = re.search(r'constant DIGEST_H0\s*:[^:]*:=\s*x"([0-9a-f]{64})"', TB_TEXT)
    assert match, "DIGEST_H0 not found in the testbench"
    assert match.group(1) == "".join(f"{value:08x}" for value in H0)


def test_the_testbench_has_the_fips_vectors_of_ac_15_1() -> None:
    vectors = _vectors()
    sizes = {len(message) * 8 for message, _ in vectors.values()}
    assert {24, 448, 896} <= sizes  # "abc", 448 bits, 896 bits


def test_every_expected_digest_of_the_testbench_is_the_hashlib_one() -> None:
    for name, (message, digest) in _vectors().items():
        assert hashlib.sha256(message).hexdigest() == digest, name


def test_the_448_and_896_bit_messages_are_the_fips_ones() -> None:
    vectors = {name: message for name, (message, _) in _vectors().items()}
    assert b"abc" in vectors.values()
    assert (
        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq" in vectors.values()
    )
    assert (
        b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmno"
        b"ijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu"
    ) in vectors.values()


# --------------------------------------------------------------------------------------------
# Conventions of the hardware part (Architecture 5.6, AGENTS.md)
# --------------------------------------------------------------------------------------------

PORTS = (
    "aclk",
    "aresetn",
    "init",
    "word_valid",
    "word_data",
    "word_ready",
    "busy",
    "done",
    "digest",
)


def test_the_core_has_the_documented_entity_and_ports() -> None:
    assert re.search(r"entity\s+sha256_core\s+is", CORE_TEXT, re.IGNORECASE)
    for port in PORTS:
        assert re.search(rf"\b{port}\s*:\s*(in|out)\b", CORE_TEXT), port
    assert re.search(r"digest\s*:\s*out\s+std_logic_vector\(255 downto 0\)", CORE_TEXT)
    assert re.search(r"word_data\s*:\s*in\s+std_logic_vector\(31 downto 0\)", CORE_TEXT)


def test_the_core_follows_the_conventions_of_the_hardware_part() -> None:
    lowered = CORE_CODE.lower()
    assert "ieee.numeric_std" in lowered
    for banned in (
        "std_logic_arith",
        "std_logic_unsigned",
        "unisim",
        "xpm",
        "wait for",
        "after ",
    ):
        assert banned not in lowered, banned
    # One clock, synchronous active-low reset.
    assert len(re.findall(r"rising_edge\s*\(", lowered)) == 1
    assert "rising_edge(aclk)" in lowered
    assert "aresetn = '0'" in lowered
    assert "falling_edge" not in lowered


def test_the_core_does_no_padding_and_has_no_bus() -> None:
    lowered = CORE_CODE.lower()
    for out_of_scope in ("s_axi", "awvalid", "uart", "last_bytes", "padder", "final"):
        assert out_of_scope not in lowered, out_of_scope


def test_the_testbench_is_vhdl_2008_self_checking_and_prints_its_verdict() -> None:
    assert "entity sha256_core_tb" in TB_TEXT
    assert "SHA256_TB PASSED" in TB_TEXT
    assert "severity failure" in TB_TEXT
    # The testbench pads (the core does not) and checks the block duration.
    assert "PADDED" in TB_TEXT.upper()
    assert re.search(r"BLOCK_CYCLES\s*:\s*(natural|integer)\s*:=\s*65", TB_TEXT)


# --------------------------------------------------------------------------------------------
# hw/sim/Makefile: GHDL + cocotb, or Vivado xsim, or a loud skip
# --------------------------------------------------------------------------------------------


def _make(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged = {k: v for k, v in os.environ.items() if k not in {"SAAM_HW_SIM_REQUIRED"}}
    merged.update(env or {})
    return subprocess.run(
        ["make", "-C", str(SIM), *args],
        env=merged,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _without_tools() -> dict[str, str]:
    """A PATH that holds make, sh and the basic tools but no simulator."""
    keep = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        lowered = directory.lower()
        if any(
            name in lowered for name in ("ghdl", "vivado", "xilinx", "amddesigntools")
        ):
            continue
        keep.append(directory)
    return {"PATH": os.pathsep.join(keep), "XILINX_VIVADO": "", "SAAM_VIVADO_BIN": ""}


pytestmark_make = pytest.mark.skipif(shutil.which("make") is None, reason="no make")


@pytestmark_make
def test_without_any_simulator_the_default_target_says_skipped_and_exits_zero() -> None:
    result = _make(env=_without_tools())
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-1200:]
    assert "SKIPPED" in combined
    assert "GHDL" in combined and "xsim" in combined.lower()
    assert "PASSED" not in combined


@pytest.mark.skipif(shutil.which("make") is None, reason="no make")
def test_when_the_simulation_is_required_a_missing_simulator_is_a_failure() -> None:
    result = _make(env={**_without_tools(), "SAAM_HW_SIM_REQUIRED": "1"})
    assert result.returncode != 0
    assert "SKIPPED" not in result.stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="no make")
def test_the_xsim_target_compiles_the_core_then_the_testbench_in_vhdl_2008() -> None:
    result = _make(
        "-n", "xsim", env={"XVHDL": "xvhdl", "XELAB": "xelab", "XSIM": "xsim"}
    )
    assert result.returncode == 0, result.stderr
    text = result.stdout
    assert "--2008" in text
    assert text.index("sha256_core.vhd") < text.index("sha256_core_tb.vhd")
    assert "xelab" in text and "xsim" in text


@pytest.mark.skipif(shutil.which("make") is None, reason="no make")
def test_the_cocotb_target_runs_ghdl_in_vhdl_2008_on_the_documented_bench() -> None:
    text = COCOTB_MK.read_text(encoding="utf-8")
    assert "SIM ?= ghdl" in text or "SIM = ghdl" in text
    assert "sha256_core" in text
    assert "test_sha256" in text
    assert "--std=08" in text
    assert "cocotb-config" in text
    # Windows Python splits PYTHONPATH on ';'; a colon-only export drops sha_support.
    assert "Windows_NT" in text
    assert "PYSEP := ;" in text


def test_the_build_products_of_the_simulation_are_not_versioned() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("hw/sim/build/", "hw/sim/sim_build/", "hw/sim/results.xml"):
        assert pattern in gitignore, pattern


# --------------------------------------------------------------------------------------------
# The cocotb bench: structure only (it needs GHDL and cocotb to run)
# --------------------------------------------------------------------------------------------

BENCH = COCOTB_BENCH.read_text(encoding="utf-8") if COCOTB_BENCH.exists() else ""


def test_the_cocotb_bench_compares_with_hashlib_and_covers_the_required_cases() -> None:
    assert "import hashlib" in BENCH
    assert BENCH.count("@cocotb.test") >= 5
    for needle in ("abc", "reset", "two messages", "block"):
        assert needle in BENCH.lower(), needle


def test_the_cocotb_bench_does_not_carry_a_second_sha256() -> None:
    lowered = BENCH.lower()
    for forbidden in ("0x428a2f98", "0x6a09e667", "rotr", "sigma"):
        assert forbidden not in lowered, forbidden


# --------------------------------------------------------------------------------------------
# The padding helper of the benches (the core does not pad)
# --------------------------------------------------------------------------------------------


def _support():  # type: ignore[no-untyped-def]
    import importlib.util

    path = SIM / "sha_support.py"
    spec = importlib.util.spec_from_file_location("sha_support", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "length", [0, 1, 3, 55, 56, 57, 63, 64, 65, 111, 112, 119, 120, 127, 128]
)
def test_the_padding_helper_follows_fips_180_4(length: int) -> None:
    support = _support()
    message = bytes(range(256))[:length] if length <= 256 else b"x" * length
    blocks = support.padded_blocks(message)

    joined = b"".join(blocks)
    assert all(len(block) == 64 for block in blocks)
    assert joined[:length] == message
    assert joined[length] == 0x80
    assert joined[length + 1 : -8] == bytes(len(joined) - length - 9)
    assert int.from_bytes(joined[-8:], "big") == length * 8
    # The smallest number of blocks that holds the message, the bit and the length.
    assert len(blocks) == (length + 9 + 63) // 64


def test_the_padding_helper_words_are_big_endian() -> None:
    support = _support()
    block = bytes(range(64))
    words = support.block_words(block)
    assert len(words) == 16
    assert words[0] == 0x00010203
    assert words[15] == 0x3C3D3E3F


def test_the_digest_helper_reads_the_word_vector_from_h0_first() -> None:
    support = _support()
    vector = int.from_bytes(hashlib.sha256(b"abc").digest(), "big")
    assert support.digest_hex(vector) == hashlib.sha256(b"abc").hexdigest()
    assert support.digest_hex(vector) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# --------------------------------------------------------------------------------------------
# A real simulation, when a simulator is installed
# --------------------------------------------------------------------------------------------


def _vivado_bin() -> Path | None:
    for variable in ("SAAM_VIVADO_BIN",):
        value = os.environ.get(variable, "").strip()
        if value and Path(value).is_dir():
            return Path(value)
    root = os.environ.get("XILINX_VIVADO", "").strip()
    if root and (Path(root) / "bin").is_dir():
        return Path(root) / "bin"
    found = shutil.which("xvhdl") or shutil.which("xvhdl.bat")
    return Path(found).parent if found else None


@pytest.mark.skipif(shutil.which("make") is None, reason="no make")
def test_the_vhdl_testbench_passes_in_vivado_xsim() -> None:
    """The reference run of the core: the testbench in Vivado xsim. Skipped, with the reason, when
    Vivado is not found (set SAAM_VIVADO_BIN or XILINX_VIVADO)."""
    vivado = _vivado_bin()
    if vivado is None:
        pytest.skip(
            "no Vivado xsim (set SAAM_VIVADO_BIN or XILINX_VIVADO): the testbench was not run"
        )
    env = {"SAAM_VIVADO_BIN": str(vivado)}
    result = _make("xsim", env=env)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-2500:]
    assert "SHA256_TB PASSED" in combined
