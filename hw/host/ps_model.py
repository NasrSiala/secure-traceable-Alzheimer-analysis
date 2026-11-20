"""Software model of the PS command loop (IF-14), for tests without the board.

SHA-256 is hashlib. FIR is saam.dsp.fir_fixed.filter_decimate. The same framing
as zybo_client: the response payload is a status byte then the body.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

from uart_framing import (
    CMD_FIR,
    CMD_INFO,
    CMD_SHA256,
    STATUS_OK,
    decode_frame,
    encode_frame,
)

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from saam.dsp.fir_fixed import coef_id, filter_decimate


def _coef_word(identifier: str) -> int:
    return int(identifier, 16)


class PsModel:
    def __init__(self, version: int = 0, coef: str | None = None) -> None:
        self.version = version & 0xFFFFFFFF
        self.coef = _coef_word(coef if coef is not None else coef_id())

    def exchange(self, frame: bytes) -> bytes:
        command, payload = decode_frame(frame)
        if command == CMD_INFO:
            body = struct.pack("<II", self.version, self.coef)
        elif command == CMD_SHA256:
            body = hashlib.sha256(payload).digest()
        elif command == CMD_FIR:
            if len(payload) % 2 != 0:
                raise ValueError("échantillons")
            count = len(payload) // 2
            samples = list(struct.unpack("<" + "h" * count, payload))
            outputs = filter_decimate(samples)
            body = struct.pack("<" + "h" * len(outputs), *outputs)
        else:
            raise ValueError("commande")
        return encode_frame(command, bytes((STATUS_OK,)) + body)
