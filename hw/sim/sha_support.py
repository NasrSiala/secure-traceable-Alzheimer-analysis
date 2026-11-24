"""Helpers of the SHA-256 benches: padding and word order. Pure Python, no cocotb.

The core compresses blocks that are already padded (T3.18, 1/2), so the benches pad. The oracle for
digests is `hashlib`: nothing here computes a SHA-256.
"""

from __future__ import annotations

BLOCK_BYTES = 64
WORDS_PER_BLOCK = 16


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
    return f"{vector:064x}"
