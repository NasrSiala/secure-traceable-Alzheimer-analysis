"""Offline tests of the host side of the bring-up console. No board, no serial device.

`FakePort` is a test double written from hw/ps_app/bringup/hello.c: it lets the host code be
checked (framing, parsing, baud switch order, byte comparison, throughput arithmetic). It proves
nothing about the board, and nothing it returns may be reported as a board result.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from bringup_support import (
    BANNER,
    BAUD_HIGH,
    BAUD_LOW,
    BringupError,
    Console,
    Throughput,
    parse_register,
    pattern,
)

HERE = Path(__file__).resolve().parent


class FakePort:
    """What hello.c does, in Python. `mode` injects the failures a board could show."""

    def __init__(self, mode: str = "ok") -> None:
        self.baudrate = BAUD_LOW
        self.mode = mode
        self.register = 0
        self.written: list[bytes] = []
        self.baud_when_acknowledged: list[int] = []
        self._line = bytearray()
        self._rx = bytearray()
        self._echo_left = 0
        self._cond = threading.Condition()

    def _reply(self, text: str) -> None:
        with self._cond:
            self._rx += text.encode("ascii") + b"\r\n"
            self._cond.notify_all()

    def reset_input_buffer(self) -> None:
        with self._cond:
            self._rx.clear()

    def write(self, data: bytes, /) -> int:
        self.written.append(bytes(data))
        for byte in data:
            if self._echo_left > 0:
                self._echo_left -= 1
                out = (
                    byte ^ 0x01
                    if (self.mode == "corrupt" and self._echo_left == 5)
                    else byte
                )
                stalled = self.mode == "stall" and self._echo_left <= 5
                if not stalled and not (self.mode == "drop" and self._echo_left == 5):
                    with self._cond:
                        self._rx.append(out)
                        self._cond.notify_all()
                if self._echo_left == 0 and self.mode not in ("no-done", "stall"):
                    self._reply("")
                    self._reply("DONE")
                continue
            if byte == 0x0A:
                self._command(self._line.decode("ascii"))
                self._line.clear()
            else:
                self._line.append(byte)
        return len(data)

    def _command(self, line: str) -> None:
        if self.mode == "silent":
            return
        match line[:1]:
            case "H":
                self._reply(BANNER if self.mode != "wrong-banner" else "hello other")
            case "W":
                try:
                    self.register = int(line[1:].strip(), 16)
                    self._reply("OK")
                except ValueError:
                    self._reply("ERR")
            case "R":
                self._reply(f"R {self.register:08x}")
            case "B":
                baud = int(line[1:])
                self.baud_when_acknowledged.append(self.baudrate)
                self._reply(f"B {baud}")
            case "E":
                self._reply("GO")
                self._echo_left = int(line[1:])
            case _:
                self._reply("ERR")

    def read(self, size: int = 1, /) -> bytes:
        with self._cond:
            if not self._rx:
                self._cond.wait(timeout=1.0)
            taken = bytes(self._rx[:size])
            del self._rx[:size]
            return taken


def test_the_board_says_hello() -> None:
    assert Console(FakePort()).hello() == BANNER


def test_another_banner_is_not_hello() -> None:
    with pytest.raises(BringupError, match="hello"):
        Console(FakePort("wrong-banner")).hello()


def test_a_silent_board_is_a_timeout_not_a_hang() -> None:
    with pytest.raises(BringupError, match="timeout"):
        Console(FakePort("silent")).hello()


@pytest.mark.parametrize("value", [0, 1, 0xDEADBEEF, 0xFFFFFFFF])
def test_a_register_value_is_written_as_eight_hex_digits_and_read_back(
    value: int,
) -> None:
    port = FakePort()
    console = Console(port)

    console.write_register(value)

    assert port.written[-1] == f"W {value:08x}\n".encode("ascii")
    assert console.read_register() == value


@pytest.mark.parametrize(
    "reply", ["", "R", "R 1234", "R 123456789", "X 00000000", "R zzzzzzzz"]
)
def test_a_register_reply_that_is_not_r_and_eight_hex_digits_is_refused(
    reply: str,
) -> None:
    with pytest.raises(BringupError):
        parse_register(reply)


def test_the_baud_change_is_acknowledged_at_the_old_rate_then_the_port_follows() -> (
    None
):
    port = FakePort()

    Console(port).set_baud(BAUD_HIGH)

    assert port.baud_when_acknowledged == [BAUD_LOW]
    assert port.baudrate == BAUD_HIGH


@pytest.mark.parametrize("baud", [9600, 230400, 0, -1])
def test_a_baud_rate_the_board_does_not_offer_is_not_sent(baud: int) -> None:
    port = FakePort()
    with pytest.raises(ValueError, match="baud"):
        Console(port).set_baud(baud)
    assert port.written == []


def test_an_exact_echo_has_no_error_and_the_rate_of_the_clock() -> None:
    ticks = iter([10.0, 11.0])
    console = Console(FakePort(), clock=lambda: next(ticks))
    data = pattern(11_520)

    measured = console.echo(data)

    assert measured.errors == 0
    assert measured.bytes == 11_520
    assert measured.seconds == pytest.approx(1.0)
    assert measured.baud == BAUD_LOW
    assert measured.ratio == pytest.approx(1.0)


def test_a_corrupted_byte_is_counted() -> None:
    assert Console(FakePort("corrupt")).echo(pattern(300)).errors == 1


def test_an_echo_that_stops_is_a_timeout() -> None:
    with pytest.raises(BringupError, match="stopped early"):
        Console(FakePort("stall")).echo(pattern(300))


def test_a_dropped_byte_is_refused() -> None:
    # The end of the echo then shifts by one byte: it is read as data, and DONE is not found.
    with pytest.raises(BringupError):
        Console(FakePort("drop")).echo(pattern(300))


def test_an_echo_without_done_is_refused() -> None:
    with pytest.raises(BringupError):
        Console(FakePort("no-done")).echo(pattern(300))


@pytest.mark.parametrize("data", [b"", b"x" * 65_537], ids=["empty", "65537-bytes"])
def test_a_block_outside_the_console_limit_is_not_sent(data: bytes) -> None:
    port = FakePort()
    with pytest.raises(ValueError, match="block size"):
        Console(port).echo(data)
    assert port.written == []


def test_the_block_is_sent_in_chunks_and_the_echo_command_first() -> None:
    port = FakePort()
    Console(port).echo(pattern(700))

    assert port.written[0] == b"E 700\n"
    assert b"".join(port.written[1:]) == pattern(700)
    assert max(len(chunk) for chunk in port.written[1:]) <= 256


def test_the_pattern_is_deterministic_and_does_not_repeat_early() -> None:
    assert pattern(1000, seed=3) == pattern(1000, seed=3)
    assert pattern(1000, seed=3) != pattern(1000, seed=4)
    assert len(set(pattern(1000))) > 100
    assert pattern(0) == b""


def test_the_throughput_arithmetic() -> None:
    measured = Throughput(baud=BAUD_HIGH, bytes=92_160, seconds=2.0, errors=0)

    assert measured.bytes_per_second == pytest.approx(46_080)
    assert measured.theoretical == pytest.approx(92_160)
    assert measured.ratio == pytest.approx(0.5)
    data = measured.as_json()
    assert data["ratio"] == 0.5
    assert data["errors"] == 0


# --- the marker: no board access unless asked ------------------------------------------------


def _pytest(*args: str, port: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "SAAM_ZYBO_PORT"}
    if port is not None:
        env["SAAM_ZYBO_PORT"] = port
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-rs", *args],
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_board_tests_are_skipped_with_a_reason_when_no_port_is_given() -> None:
    result = _pytest("test_bringup.py", "-m", "board", port=None)

    assert result.returncode == 0, result.stdout[-1500:]
    assert "passed" not in result.stdout
    assert "skipped" in result.stdout
    assert "SAAM_ZYBO_PORT is not set" in result.stdout


def test_board_tests_are_left_out_of_the_default_run() -> None:
    result = _pytest("test_bringup.py", "-m", "not board", port=None)

    assert "deselected" in result.stdout
    assert "passed" not in result.stdout


def test_the_serial_device_is_only_opened_after_the_port_variable_is_read() -> None:
    source = (HERE / "test_bringup.py").read_text(encoding="utf-8")
    assert source.count("serial.Serial(") == 1
    assert source.index("SAAM_ZYBO_PORT") < source.index("serial.Serial(")
    assert source.index("pytest.skip(") < source.index("serial.Serial(")
