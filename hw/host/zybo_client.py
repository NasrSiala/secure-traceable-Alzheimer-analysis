"""Host side of IF-14. The transport is injected, so the tests need no board.

One attempt plus three retries (the same count as AC-07.4). A CRC failure on every
attempt raises « Erreur de transmission ». No answer raises the unreachable-board
sentence from the App Flow.
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from uart_framing import (
    CMD_FIR,
    CMD_INFO,
    CMD_SHA256,
    STATUS_OK,
    decode_frame,
    encode_frame,
)

UNREACHABLE = "Carte injoignable — vérifiez le câble USB et le démarrage SD."
TRANSMISSION = "Erreur de transmission"
ATTEMPTS = 4  # 1 try + 3 retries

Exchange = Callable[[bytes], bytes]


class BoardUnreachable(RuntimeError):
    pass


class TransmissionError(RuntimeError):
    pass


class ZyboClient:
    def __init__(self, exchange: Exchange) -> None:
        self._exchange = exchange

    def info(self) -> tuple[int, int]:
        payload = self._request(CMD_INFO, b"")
        version, coef = struct.unpack("<II", payload)
        return version, coef

    def sha256(self, message: bytes) -> bytes:
        return self._request(CMD_SHA256, message)

    def fir(self, samples: list[int]) -> list[int]:
        payload = struct.pack("<" + "h" * len(samples), *samples)
        raw = self._request(CMD_FIR, payload)
        if len(raw) % 2 != 0:
            raise TransmissionError(TRANSMISSION)
        count = len(raw) // 2
        return list(struct.unpack("<" + "h" * count, raw))

    def _request(self, command: int, payload: bytes) -> bytes:
        frame = encode_frame(command, payload)
        for attempt in range(ATTEMPTS):
            try:
                reply = self._exchange(frame)
            except TimeoutError as exc:
                raise BoardUnreachable(UNREACHABLE) from exc
            try:
                got_cmd, body = decode_frame(reply)
            except ValueError as exc:
                if attempt == ATTEMPTS - 1:
                    raise TransmissionError(TRANSMISSION) from exc
                continue
            if got_cmd != command or not body or body[0] != STATUS_OK:
                raise TransmissionError(TRANSMISSION)
            return body[1:]
        raise TransmissionError(TRANSMISSION)
