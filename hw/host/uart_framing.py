"""IF-14 frames: 0xA5, command, little-endian length, payload, CRC-32 (IEEE)."""

from __future__ import annotations

import struct
import zlib

SYNC = 0xA5
CMD_INFO = 0x01
CMD_SHA256 = 0x10
CMD_FIR = 0x20
STATUS_OK = 0
MAX_PAYLOAD = 1_048_576

_HEADER = 6
_CRC = 4


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def encode_frame(command: int, payload: bytes) -> bytes:
    if not 0 <= command <= 0xFF:
        raise ValueError("commande hors octet")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("charge trop longue")
    head = bytes((SYNC, command)) + struct.pack("<I", len(payload)) + payload
    return head + struct.pack("<I", crc32(head))


def decode_frame(frame: bytes) -> tuple[int, bytes]:
    """Return command and payload. Raise ValueError on a malformed frame."""
    if len(frame) < _HEADER + _CRC:
        raise ValueError("trame trop courte")
    if frame[0] != SYNC:
        raise ValueError("synchronisation")
    command = frame[1]
    length = struct.unpack_from("<I", frame, 2)[0]
    if length > MAX_PAYLOAD:
        raise ValueError("longueur")
    end = _HEADER + length
    if len(frame) != end + _CRC:
        raise ValueError("longueur")
    payload = frame[_HEADER:end]
    found = struct.unpack_from("<I", frame, end)[0]
    if found != crc32(frame[:end]):
        raise ValueError("crc")
    return command, payload
