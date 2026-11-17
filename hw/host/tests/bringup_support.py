"""Host side of the bring-up console of hw/ps_app/bringup/hello.c (T1.9, l10).

Lines of text over the board's USB-UART, one request per line. Not the framed protocol of IF-14
(hw/host/zybo_client.py, T4.12). Nothing here opens a serial port by itself: the caller gives an
object with `write`, `read` and a `baudrate` attribute, which is a pyserial `Serial` on a board and
a labelled double in the offline tests.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

BANNER = "hello SAAM-BRINGUP 1"
BAUD_LOW = 115_200
BAUD_HIGH = 921_600
ECHO_MAX = 65_536
# A UART frame is 10 bits (start, 8 data, stop): the best a byte rate can be.
BITS_PER_BYTE = 10
CHUNK = 256


class BringupError(Exception):
    """The board answered something else than the console promises."""


class SerialLike(Protocol):
    baudrate: int

    def write(self, data: bytes, /) -> int | None: ...

    def read(self, size: int = 1, /) -> bytes: ...

    def reset_input_buffer(self) -> None: ...


@dataclass(frozen=True)
class Throughput:
    baud: int
    bytes: int
    seconds: float
    errors: int

    @property
    def bytes_per_second(self) -> float:
        return self.bytes / self.seconds

    @property
    def theoretical(self) -> float:
        return self.baud / BITS_PER_BYTE

    @property
    def ratio(self) -> float:
        return self.bytes_per_second / self.theoretical

    def as_json(self) -> dict[str, object]:
        data = asdict(self)
        data["bytes_per_second"] = round(self.bytes_per_second, 1)
        data["theoretical_bytes_per_second"] = round(self.theoretical, 1)
        data["ratio"] = round(self.ratio, 4)
        return data


def pattern(size: int, seed: int = 1) -> bytes:
    """Deterministic, non-repeating bytes: a dropped or doubled byte shows."""
    state = seed & 0xFFFFFFFF
    out = bytearray()
    for _ in range(size):
        state = (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
        out.append(state >> 24)
    return bytes(out)


def parse_register(reply: str) -> int:
    parts = reply.split()
    if len(parts) != 2 or parts[0] != "R" or len(parts[1]) != 8:
        raise BringupError("the register reply is not 'R <8 hex digits>'")
    try:
        return int(parts[1], 16)
    except ValueError:
        raise BringupError("the register reply is not hexadecimal") from None


class Console:
    def __init__(
        self, port: SerialLike, *, clock: Callable[[], float] = time.perf_counter
    ) -> None:
        self.port = port
        self._clock = clock

    def _line(self) -> str:
        data = bytearray()
        while not data.endswith(b"\r\n"):
            byte = self.port.read(1)
            if not byte:
                raise BringupError("no answer from the board (timeout)")
            data += byte
        return data[:-2].decode("ascii", errors="replace")

    def command(self, text: str) -> str:
        self.port.write(text.encode("ascii") + b"\n")
        return self._line()

    def hello(self) -> str:
        reply = self.command("H")
        if reply != BANNER:
            raise BringupError("the board did not say hello")
        return reply

    def write_register(self, value: int) -> None:
        if self.command(f"W {value & 0xFFFFFFFF:08x}") != "OK":
            raise BringupError("the register write was not acknowledged")

    def read_register(self) -> int:
        return parse_register(self.command("R"))

    def set_baud(self, baud: int) -> None:
        """The board answers at the old rate, then changes; the port follows."""
        if baud not in (BAUD_LOW, BAUD_HIGH):
            raise ValueError("unsupported baud rate")
        if self.command(f"B {baud}") != f"B {baud}":
            raise BringupError("the baud rate change was not acknowledged")
        self.port.baudrate = baud
        self.port.reset_input_buffer()

    def echo(self, data: bytes) -> Throughput:
        """Send `data`, read it back: the time covers the first byte out to the last byte in."""
        if not 0 < len(data) <= ECHO_MAX:
            raise ValueError("block size outside 1..65536")
        if self.command(f"E {len(data)}") != "GO":
            raise BringupError("the board did not start the echo")
        received = bytearray()
        failure: list[BaseException] = []

        def send() -> None:
            try:
                for start in range(0, len(data), CHUNK):
                    self.port.write(data[start : start + CHUNK])
            except (OSError, ValueError) as error:  # reported on the main thread
                failure.append(error)

        started = self._clock()
        writer = threading.Thread(target=send, daemon=True)
        writer.start()
        while len(received) < len(data):
            block = self.port.read(len(data) - len(received))
            if not block:
                break
            received += block
        elapsed = self._clock() - started
        writer.join(timeout=5)
        if failure:
            raise BringupError("the block could not be sent") from failure[0]
        if len(received) < len(data):
            raise BringupError("the echo stopped early (timeout)")
        # The board ends the echo with an empty line and "DONE".
        if self._line() != "" or self._line() != "DONE":
            raise BringupError("the echo did not end with DONE")
        errors = sum(
            1 for sent, back in zip(data, received, strict=True) if sent != back
        )
        return Throughput(
            baud=self.port.baudrate, bytes=len(data), seconds=elapsed, errors=errors
        )
