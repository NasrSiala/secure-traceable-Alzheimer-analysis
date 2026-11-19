"""cocotb bench of sha256_padder (T3.18, 2/2, AC-15.1 and AC-15.2).

Needs GHDL and cocotb: `make -C hw/sim cocotb` runs this after the direct-core bench
(test_sha256.py), which stays on sha256_core. Not collected by pytest (testpaths = tests).

The oracle is hashlib.sha256. Messages are unpadded beats from sha_support.frame_words:
the final beat carries the valid byte count, and its unused low bytes are 0xFF.
"""

from __future__ import annotations

import hashlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from sha_support import (
    EXPLICIT_LENGTHS,
    RANDOM_COUNT,
    digest_hex,
    frame_words,
    pattern_message,
    random_lengths,
)

# 64 rounds, one add to H, plus the padding beats and the skid buffer. Far above a 4096-byte message.
MESSAGE_CYCLE_LIMIT = 20000

FIPS = {
    "empty": b"",
    "abc": b"abc",
    "448 bits": b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
    "896 bits": (
        b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmno"
        b"ijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu"
    ),
}

# Seed 0x53484132, shared with hw/sim/vectors/sha256_padder_random.txt and the VHDL testbench.
BOUNDARY_LENGTHS = (55, 56, 63, 64, 119, 120)


def make_clock(dut) -> Clock:  # type: ignore[no-untyped-def]
    try:
        return Clock(dut.aclk, 10, unit="ns")  # cocotb 2.x
    except TypeError:
        return Clock(dut.aclk, 10, units="ns")  # cocotb 1.9


def read_digest(dut) -> str:  # type: ignore[no-untyped-def]
    return digest_hex(int(dut.digest.value))


async def start(dut) -> None:  # type: ignore[no-untyped-def]
    cocotb.start_soon(make_clock(dut).start())
    dut.init.value = 0
    dut.in_valid.value = 0
    dut.in_last.value = 0
    dut.in_bytes.value = 0
    dut.in_data.value = 0
    await reset(dut)


async def reset(dut, cycles: int = 3) -> None:  # type: ignore[no-untyped-def]
    dut.aresetn.value = 0
    dut.init.value = 0
    dut.in_valid.value = 0
    dut.in_last.value = 0
    await ClockCycles(dut.aclk, cycles)
    dut.aresetn.value = 1
    await ClockCycles(dut.aclk, 2)


async def pulse_init(dut) -> None:  # type: ignore[no-untyped-def]
    dut.init.value = 1
    await RisingEdge(dut.aclk)
    dut.init.value = 0
    await RisingEdge(dut.aclk)
    assert int(dut.done.value) == 0, "done survived init"
    assert int(dut.busy.value) == 1, "a message is not busy after init"
    assert int(dut.in_ready.value) == 1, "the padder does not accept a beat after init"


async def put_beat(dut, word: int, nbytes: int, last: bool) -> None:  # type: ignore[no-untyped-def]
    """Drive one beat. Ready is sampled after the edge (cocotb sees the updated value), so the
    beat is applied only once a previous edge has left in_ready high, and dropped after the
    accepting edge."""
    for _ in range(MESSAGE_CYCLE_LIMIT):
        await RisingEdge(dut.aclk)
        if int(dut.in_ready.value) == 1 and int(dut.in_valid.value) == 0:
            break
    else:
        raise AssertionError("in_ready stayed low")
    dut.in_data.value = word
    dut.in_bytes.value = nbytes
    dut.in_last.value = 1 if last else 0
    dut.in_valid.value = 1
    await RisingEdge(dut.aclk)
    dut.in_valid.value = 0
    dut.in_last.value = 0


async def send_message(dut, message: bytes) -> None:  # type: ignore[no-untyped-def]
    beats = frame_words(message)
    for index, (word, nbytes) in enumerate(beats):
        last = index == len(beats) - 1
        # in_bytes is the final-word count only. A non-final beat is driven as 0 so a padder
        # that applies the count to every beat drops the word and cannot match hashlib.
        await put_beat(dut, word, nbytes if last else 0, last)


async def hash_message(dut, message: bytes) -> str:  # type: ignore[no-untyped-def]
    await pulse_init(dut)
    await send_message(dut, message)
    for _ in range(MESSAGE_CYCLE_LIMIT):
        await RisingEdge(dut.aclk)
        if int(dut.done.value) == 1:
            assert int(dut.busy.value) == 0, "busy stayed high after done"
            return read_digest(dut)
    raise AssertionError(f"timeout waiting for a digest of {len(message)} bytes")


def expect(message: bytes, got: str) -> None:
    wanted = hashlib.sha256(message).hexdigest()
    assert got == wanted, (
        f"len={len(message)} last_bytes="
        f"{0 if not message else (len(message) % 4 or 4)} expected {wanted} got {got}"
    )


@cocotb.test()
async def empty_and_abc_match_hashlib(dut) -> None:  # type: ignore[no-untyped-def]
    """AC-15.1: the empty message and "abc", padded in hardware."""
    await start(dut)
    assert int(dut.in_ready.value) == 0, "a beat was accepted before init"
    for name in ("empty", "abc"):
        message = FIPS[name]
        expect(message, await hash_message(dut, message))


@cocotb.test()
async def fips_long_messages_match_hashlib(dut) -> None:  # type: ignore[no-untyped-def]
    """AC-15.1: the 448-bit message (one block plus padding spill) and the 896-bit message."""
    await start(dut)
    for name in ("448 bits", "896 bits"):
        message = FIPS[name]
        expect(message, await hash_message(dut, message))


@cocotb.test()
async def boundary_lengths_match_hashlib(dut) -> None:  # type: ignore[no-untyped-def]
    """AC-15.2 boundaries 55, 56, 63, 64, 119 and 120, and every final-word byte count."""
    await start(dut)
    for length in EXPLICIT_LENGTHS:
        message = pattern_message(length)
        expect(message, await hash_message(dut, message))
    assert set(BOUNDARY_LENGTHS) <= set(EXPLICIT_LENGTHS)


@cocotb.test()
async def one_thousand_random_messages_match_hashlib(dut) -> None:  # type: ignore[no-untyped-def]
    """AC-15.2: 1000 patterned messages, lengths from random.Random(0x53484132), 0 to 4096."""
    await start(dut)
    lengths = random_lengths()
    assert len(lengths) == RANDOM_COUNT
    assert min(lengths) >= 0 and max(lengths) <= 4096
    for index, length in enumerate(lengths):
        message = pattern_message(length)
        got = await hash_message(dut, message)
        wanted = hashlib.sha256(message).hexdigest()
        assert got == wanted, (
            f"random[{index}] len={length} expected {wanted} got {got}"
        )


@cocotb.test()
async def reset_during_a_message_then_reuse(dut) -> None:  # type: ignore[no-untyped-def]
    """Reset while beats are still going in, and again while the core is in its rounds."""
    await start(dut)
    await pulse_init(dut)
    partial = frame_words(pattern_message(200))
    for word, _nbytes in partial[:8]:
        await put_beat(dut, word, 0, False)
    await reset(dut)
    assert int(dut.busy.value) == 0 and int(dut.done.value) == 0
    expect(b"abc", await hash_message(dut, b"abc"))

    await pulse_init(dut)
    for word, _nbytes in partial[:16]:
        await put_beat(dut, word, 0, False)
    await ClockCycles(dut.aclk, 8)
    assert int(dut.busy.value) == 1, "the padder went idle during a block"
    await reset(dut)
    assert int(dut.busy.value) == 0 and int(dut.done.value) == 0
    expect(b"", await hash_message(dut, b""))
    expect(FIPS["896 bits"], await hash_message(dut, FIPS["896 bits"]))


@cocotb.test()
async def two_messages_back_to_back(dut) -> None:  # type: ignore[no-untyped-def]
    """Reuse after done, with no reset between messages."""
    await start(dut)
    sequence = (
        b"",
        b"abc",
        pattern_message(56),
        pattern_message(120),
        FIPS["448 bits"],
        b"",
    )
    for message in sequence:
        expect(message, await hash_message(dut, message))


@cocotb.test()
async def done_is_cleared_by_init(dut) -> None:  # type: ignore[no-untyped-def]
    await start(dut)
    expect(b"abc", await hash_message(dut, b"abc"))
    await ClockCycles(dut.aclk, 4)
    assert int(dut.done.value) == 1 and int(dut.busy.value) == 0
    await pulse_init(dut)
    assert int(dut.done.value) == 0
