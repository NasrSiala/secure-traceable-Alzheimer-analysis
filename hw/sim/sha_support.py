"""Helpers of the SHA-256 benches: padding and word order. Pure Python, no cocotb.

The core compresses blocks that are already padded (T3.18, 1/2), so the direct-core bench pads.
The padder bench (T3.18, 2/2) sends unpadded beats and lets the hardware pad. The oracle for
digests is `hashlib`: nothing here computes a SHA-256.
"""

from __future__ import annotations

import random

BLOCK_BYTES = 64
WORDS_PER_BLOCK = 16

# Patterned messages shared by the cocotb bench, the VHDL testbench vectors and the pytest check.
# byte[i] = (RANDOM_SEED + i * 131) mod 256. Lengths are 0 .. MAX_MESSAGE_BYTES inclusive.
RANDOM_SEED = 0x53484132
RANDOM_COUNT = 1000
MAX_MESSAGE_BYTES = 4096
# Required boundaries plus one length for every final-word byte count (0, 1, 2, 3, 4), including
# a second block (65, 66) and the top of the supported range.
EXPLICIT_LENGTHS = (
    0,
    1,
    2,
    3,
    4,
    5,
    54,
    55,
    56,
    57,
    63,
    64,
    65,
    66,
    119,
    120,
    4095,
    4096,
)


def padded_blocks(message: bytes) -> list[bytes]:
    """FIPS 180-4 5.1.1: the message, 0x80, zeros, the length in bits on 8 bytes (big-endian),
    cut into blocks of 64 bytes."""
    length = len(message)
    zeros = (-(length + 1 + 8)) % BLOCK_BYTES
    data = message + b"\x80" + bytes(zeros) + (length * 8).to_bytes(8, "big")
    return [
        data[start : start + BLOCK_BYTES] for start in range(0, len(data), BLOCK_BYTES)
    ]


def block_words(block: bytes) -> list[int]:
    """The 16 words of a block, big-endian: the first byte of the block in bits 31..24."""
    if len(block) != BLOCK_BYTES:
        raise ValueError("a block has 64 bytes")
    return [int.from_bytes(block[i : i + 4], "big") for i in range(0, BLOCK_BYTES, 4)]


def digest_hex(vector: int) -> str:
    """The 256-bit `digest` port (H0 in bits 255..224) as hashlib's hexdigest()."""
    return f"{vector & ((1 << 256) - 1):064x}"


def pattern_message(length: int, seed: int = RANDOM_SEED) -> bytes:
    """`length` bytes, byte[i] = (seed + i * 131) mod 256. Deterministic, no RNG state."""
    if length < 0:
        raise ValueError("length is negative")
    return bytes((seed + index * 131) & 0xFF for index in range(length))


def random_lengths(
    count: int = RANDOM_COUNT,
    seed: int = RANDOM_SEED,
    max_length: int = MAX_MESSAGE_BYTES,
) -> list[int]:
    """`count` lengths in 0 .. max_length, from `random.Random(seed)` (the shared fixed seed)."""
    generator = random.Random(seed)
    return [generator.randrange(0, max_length + 1) for _ in range(count)]


def frame_words(message: bytes) -> list[tuple[int, int]]:
    """Beats `(word, valid_bytes)` for the padder, big-endian.

    The last beat carries the valid byte count: 0 for an empty message, 4 when the length is a
    multiple of 4, otherwise the remainder. Unused low bytes of a short last word are 0xFF, so a
    padder that ignores the count cannot match `hashlib`. Earlier beats are full words; their
    count is 4, and the bench drives `in_bytes` as 0 on those beats so only the final count matters.
    """
    if len(message) == 0:
        return [(0xFFFFFFFF, 0)]
    remainder = len(message) % 4
    if remainder == 0:
        full_words = len(message) // 4 - 1
        tail = message[-4:]
        tail_bytes = 4
    else:
        full_words = len(message) // 4
        tail = message[-remainder:] + b"\xff" * (4 - remainder)
        tail_bytes = remainder
    words = [
        (int.from_bytes(message[4 * index : 4 * index + 4], "big"), 4)
        for index in range(full_words)
    ]
    words.append((int.from_bytes(tail, "big"), tail_bytes))
    return words
