"""cocotb bench of sha256_core (T3.18, 1/2, AC-15.1): pre-padded blocks against hashlib.

Needs GHDL and cocotb: `make -C hw/sim cocotb` runs this direct-core bench first, then the padder
bench hw/sim/test_sha256_padder.py (unpadded beats, final-word byte count, multi-block). Not run
by the repository tests (tests/scripts/test_sha256_core.py only checks its structure); the VHDL
testbench sha256_core_tb.vhd is the reference run in Vivado xsim.

The oracle is `hashlib.sha256` (ADR-12: one source of truth). The core does not pad: the bench pads
with sha_support.padded_blocks and feeds 16 big-endian words per block. These direct-core tests stay.
"""

from __future__ import annotations

import hashlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from sha_support import block_words, digest_hex, padded_blocks

# 64 round cycles and one cycle to add the working variables to H: busy lasts 65 cycles.
BLOCK_CYCLES = 65

FIPS = {
    "abc": b"abc",
    "448 bits": b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
    "896 bits": (
        b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmno"
        b"ijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu"
    ),
}


# The clock edges seen so far, counted by the bench itself (no simulator-time API: the argument
# names of those changed between cocotb 1.9 and 2.0).
EDGES = [0]


async def count_edges(dut) -> None:  # type: ignore[no-untyped-def]
    while True:
        await RisingEdge(dut.aclk)
        EDGES[0] += 1


def make_clock(dut) -> Clock:  # type: ignore[no-untyped-def]
    try:
        return Clock(dut.aclk, 10, unit="ns")  # cocotb 2.x
    except TypeError:
        return Clock(dut.aclk, 10, units="ns")  # cocotb 1.9


async def start(dut) -> None:  # type: ignore[no-untyped-def]
    cocotb.start_soon(make_clock(dut).start())
    cocotb.start_soon(count_edges(dut))
    dut.init.value = 0
    dut.word_valid.value = 0
    dut.word_data.value = 0
    await reset(dut)


async def reset(dut, cycles: int = 3) -> None:  # type: ignore[no-untyped-def]
    dut.aresetn.value = 0
    await ClockCycles(dut.aclk, cycles)
    dut.aresetn.value = 1
    await ClockCycles(dut.aclk, 2)


async def pulse_init(dut) -> None:  # type: ignore[no-untyped-def]
    dut.init.value = 1
    await RisingEdge(dut.aclk)
    dut.init.value = 0
    await RisingEdge(dut.aclk)


async def put_word(dut, word: int) -> int:  # type: ignore[no-untyped-def]
    """Offer one word for a single edge, once word_ready is already 1.

    Cocotb samples outputs after the clock edge. The 16th word makes word_ready
    fall on the edge that takes it, so a loop that waits for word_ready while
    word_valid stays high never sees that edge and keeps the word into the next
    block. The VHDL testbench does not have this problem: it reads word_ready
    in the same delta as the edge, and still sees the pre-edge value.
    """
    for _ in range(100000):
        await RisingEdge(dut.aclk)
        if int(dut.word_ready.value) == 1 and int(dut.word_valid.value) == 0:
            break
    else:
        raise AssertionError("word_ready stayed low")
    dut.word_data.value = word
    dut.word_valid.value = 1
    await RisingEdge(dut.aclk)
    accepted = EDGES[0]
    dut.word_valid.value = 0
    return accepted


async def run_block(dut, block: bytes) -> int:  # type: ignore[no-untyped-def]
    """Feed one padded block and wait until done. Returns the 65-cycle busy time.

    Cocotb reads busy after the edge, so the edge that clears busy already shows
    0. The VHDL bench reads the pre-edge value and therefore counts that edge too
    (65 busy cycles, done 66 cycles after the 16th word). Here the same block is
    64 edges with busy still 1, and done is visible 65 cycles after the accept.
    """
    accepted = 0
    for word in block_words(block):
        accepted = await put_word(dut, word)
    busy_cycles = 0
    while True:
        await RisingEdge(dut.aclk)
        if int(dut.busy.value) == 0:
            break
        assert int(dut.word_ready.value) == 0, "word_ready is high while busy"
        assert int(dut.done.value) == 0, "done is high while busy"
        busy_cycles += 1
    assert int(dut.done.value) == 1, "done is not set when busy falls"
    assert busy_cycles == BLOCK_CYCLES - 1
    assert EDGES[0] - accepted == BLOCK_CYCLES
    return BLOCK_CYCLES


async def hash_message(dut, message: bytes, *, restart: bool = True) -> str:  # type: ignore[no-untyped-def]
    if restart:
        await pulse_init(dut)
        assert int(dut.done.value) == 0, "done survived init"
    for block in padded_blocks(message):
        await run_block(dut, block)
    return digest_hex(int(dut.digest.value))


@cocotb.test()
async def fips_vectors_match_hashlib(dut) -> None:  # type: ignore[no-untyped-def]
    """AC-15.1: "abc", 448 bits and 896 bits, one and two blocks."""
    await start(dut)
    for name, message in FIPS.items():
        assert (
            await hash_message(dut, message) == hashlib.sha256(message).hexdigest()
        ), name


@cocotb.test()
async def two_messages_in_sequence(dut) -> None:  # type: ignore[no-untyped-def]
    """Two messages in sequence: the core is reused after done, in both orders."""
    await start(dut)
    order = ["abc", "896 bits", "448 bits", "abc", "448 bits", "896 bits"]
    for name in order:
        message = FIPS[name]
        assert (
            await hash_message(dut, message) == hashlib.sha256(message).hexdigest()
        ), name


@cocotb.test()
async def block_duration_is_65_cycles(dut) -> None:  # type: ignore[no-untyped-def]
    """One round per cycle: 64 round cycles and one to add to H."""
    await start(dut)
    await pulse_init(dut)
    for block in padded_blocks(FIPS["896 bits"]):
        assert await run_block(dut, block) == BLOCK_CYCLES


@cocotb.test()
async def reset_during_the_load_recovers(dut) -> None:  # type: ignore[no-untyped-def]
    await start(dut)
    await pulse_init(dut)
    block = padded_blocks(FIPS["448 bits"])[0]
    for word in block_words(block)[:7]:
        await put_word(dut, word)
    await reset(dut)
    assert int(dut.busy.value) == 0 and int(dut.done.value) == 0
    message = FIPS["448 bits"]
    assert await hash_message(dut, message) == hashlib.sha256(message).hexdigest()


@cocotb.test()
async def reset_during_the_rounds_recovers(dut) -> None:  # type: ignore[no-untyped-def]
    await start(dut)
    await pulse_init(dut)
    for word in block_words(padded_blocks(FIPS["896 bits"])[0]):
        await put_word(dut, word)
    await ClockCycles(dut.aclk, 20)
    assert int(dut.busy.value) == 1
    await reset(dut)
    assert int(dut.busy.value) == 0 and int(dut.done.value) == 0
    assert int(dut.word_ready.value) == 1
    for name in ("abc", "896 bits"):
        message = FIPS[name]
        assert (
            await hash_message(dut, message) == hashlib.sha256(message).hexdigest()
        ), name


@cocotb.test()
async def done_is_cleared_by_init(dut) -> None:  # type: ignore[no-untyped-def]
    await start(dut)
    assert (
        await hash_message(dut, FIPS["abc"]) == hashlib.sha256(FIPS["abc"]).hexdigest()
    )
    await ClockCycles(dut.aclk, 5)
    assert int(dut.done.value) == 1 and int(dut.word_ready.value) == 1
    await pulse_init(dut)
    assert int(dut.done.value) == 0
