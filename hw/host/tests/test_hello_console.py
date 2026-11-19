"""The console of hw/ps_app/bringup/hello.c, run on the host (AUD-117, audit round 9).

hello.c is compiled unchanged with a host C compiler, against the stub headers and `uart_stub.c`
of `hello_stub/`: the UART is a pair of pipes, the PL register is a variable, and the calls the
application makes to the hardware are written on stderr. What this proves: the parsing, the limits,
the replies and the order of the calls of the console, and that `bringup_support.Console` (the PC
side) and `hello.c` (the PS side) agree. What it does not prove: the UART, the PL, the boot, the
throughput. That is the board run of T1.9 (`test_bringup.py`, marker `board`).

Without a host C compiler (`gcc` or `cc`) every test here is skipped with the reason.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from bringup_support import BANNER, BAUD_HIGH, BAUD_LOW, Console, pattern

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HELLO = ROOT / "hw" / "ps_app" / "bringup" / "hello.c"
STUB = HERE / "hello_stub"
REGISTER = "43c00000"
START = b"\r\nhello SAAM-BRINGUP 1\r\n"


@pytest.fixture(scope="module")
def hello(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = shutil.which("gcc") or shutil.which("cc")
    if compiler is None:
        pytest.skip("no host C compiler (gcc or cc)")
    exe = tmp_path_factory.mktemp("hello") / (
        "hello_host.exe" if os.name == "nt" else "hello_host"
    )
    done = subprocess.run(
        [
            compiler,
            "-std=gnu11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(STUB),
            str(HELLO),
            str(STUB / "uart_stub.c"),
            "-o",
            str(exe),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return exe


def run(hello: Path, data: bytes) -> tuple[bytes, list[str]]:
    """Feed `data` to the console; return what it sent and what it did to the hardware."""
    done = subprocess.run(
        [str(hello)], input=data, capture_output=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return done.stdout, done.stderr.decode("ascii").splitlines()


def reply(hello: Path, request: bytes) -> bytes:
    """What the console says to one request, without its start-up lines."""
    out, _log = run(hello, request)
    assert out.startswith(START)
    return out[len(START) :]


def test_it_sets_115200_and_says_hello_at_start(hello: Path) -> None:
    out, log = run(hello, b"")
    assert out == START
    assert log == ["BAUD 115200"]


@pytest.mark.parametrize("request_line", [b"H\n", b"H\r\n"], ids=["lf", "crlf"])
def test_h_answers_the_banner(hello: Path, request_line: bytes) -> None:
    assert reply(hello, request_line) == b"hello SAAM-BRINGUP 1\r\n"


def test_the_register_is_written_and_read_at_its_address(hello: Path) -> None:
    out, log = run(hello, b"W deadbeef\nR\n")
    assert out == START + b"OK\r\nR deadbeef\r\n"
    assert log[1:] == [f"OUT32 {REGISTER} deadbeef", f"IN32 {REGISTER}"]


@pytest.mark.parametrize(
    ("request_line", "expected"),
    [
        (b"W 1\nR\n", b"R 00000001\r\n"),
        (b"W   ff\nR\n", b"R 000000ff\r\n"),
        (b"W DEADBEEF\nR\n", b"R deadbeef\r\n"),
        (b"W FfFfFfFf\nR\n", b"R ffffffff\r\n"),
        (b"W 0\nR\n", b"R 00000000\r\n"),
        (b"R\n", b"R 00000000\r\n"),
    ],
)
def test_a_register_value_is_read_back_as_eight_lower_case_digits(
    hello: Path, request_line: bytes, expected: bytes
) -> None:
    assert reply(hello, request_line).endswith(expected)


@pytest.mark.parametrize(
    "request_line",
    [
        b"W\n",
        b"W \n",
        b"W zz\n",
        b"W 123456789\n",
        b"W 0x10\n",
        b"W ff gg\n",
        b"W -1\n",
    ],
)
def test_a_write_that_is_not_one_to_eight_hex_digits_is_refused_and_nothing_is_written(
    hello: Path, request_line: bytes
) -> None:
    out, log = run(hello, request_line)
    assert out == START + b"ERR\r\n"
    assert log == ["BAUD 115200"]


def test_eight_hex_digits_are_the_limit_of_a_write(hello: Path) -> None:
    assert reply(hello, b"W 00000000\n") == b"OK\r\n"
    assert reply(hello, b"W 000000000\n") == b"ERR\r\n"


@pytest.mark.parametrize("request_line", [b"X\n", b" \n", b"hello\n", b"w 1\n"])
def test_an_unknown_command_is_err(hello: Path, request_line: bytes) -> None:
    assert reply(hello, request_line) == b"ERR\r\n"


def test_an_empty_line_gets_no_answer(hello: Path) -> None:
    assert reply(hello, b"\n\r\n\nH\n") == b"hello SAAM-BRINGUP 1\r\n"


def test_a_line_of_32_characters_is_too_long_and_one_of_31_is_not(hello: Path) -> None:
    assert reply(hello, b"H" + b"x" * 30 + b"\n") == b"hello SAAM-BRINGUP 1\r\n"
    assert reply(hello, b"H" + b"x" * 31 + b"\n") == b"ERR\r\n"
    # The console is still in step with the host after a long line.
    assert (
        reply(hello, b"H" + b"x" * 200 + b"\nH\n") == b"ERR\r\nhello SAAM-BRINGUP 1\r\n"
    )


@pytest.mark.parametrize("baud", [BAUD_HIGH, BAUD_LOW])
def test_the_baud_rate_is_acknowledged_at_the_old_rate_then_changed(
    hello: Path, baud: int
) -> None:
    out, log = run(hello, f"B {baud}\n".encode())
    assert out == START + f"B {baud}\r\n".encode()
    # The reply is out of the transmitter before the divisor changes: the FIFO is empty AND the
    # shifter is idle (AUD-118: XUartPs_SetBaudRate resets the transmitter at once, which cuts the
    # last character of the reply if it is still being sent).
    assert log[0] == "BAUD 115200"
    assert log[-1] == f"BAUD {baud}"
    assert log[-2] == "TXACTIVE 0"
    assert "TXACTIVE 1" in log
    assert "TXEMPTY" in log


@pytest.mark.parametrize(
    "request_line",
    [b"B 9600\n", b"B\n", b"B abc\n", b"B -1\n", b"B 1152000\n", b"B 921601\n"],
)
def test_a_baud_rate_that_is_not_offered_is_refused_and_not_set(
    hello: Path, request_line: bytes
) -> None:
    out, log = run(hello, request_line)
    assert out == START + b"ERR\r\n"
    assert log == ["BAUD 115200"]


def test_the_echo_sends_back_exactly_the_bytes_it_was_given(hello: Path) -> None:
    data = bytes(range(256)) + b"\r\n\n\r\x00\xff" + b"H\n"
    out = reply(hello, f"E {len(data)}\n".encode() + data)
    assert out == b"GO\r\n" + data + b"\r\nDONE\r\n"


def test_the_console_goes_on_after_an_echo(hello: Path) -> None:
    out = reply(hello, b"E 3\nxyzH\n")
    assert out == b"GO\r\nxyz\r\nDONE\r\nhello SAAM-BRINGUP 1\r\n"


def test_an_echo_of_zero_bytes_is_go_then_done(hello: Path) -> None:
    assert reply(hello, b"E 0\n") == b"GO\r\n\r\nDONE\r\n"


def test_the_largest_echo_is_65536_bytes_and_one_more_is_refused(hello: Path) -> None:
    data = pattern(65_536)
    assert reply(hello, b"E 65536\n" + data) == b"GO\r\n" + data + b"\r\nDONE\r\n"
    assert reply(hello, b"E 65537\n") == b"ERR\r\n"


@pytest.mark.parametrize(
    "request_line", [b"E\n", b"E abc\n", b"E -1\n", b"E 12345678\n", b"E 1.5\n"]
)
def test_an_echo_count_that_is_not_a_number_of_at_most_65536_is_refused(
    hello: Path, request_line: bytes
) -> None:
    assert reply(hello, request_line) == b"ERR\r\n"


# --- the PC side (bringup_support.Console) against the real console -----------------------------


class PipePort:
    """The serial port of the host side, as two pipes to the compiled console."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process
        self.baudrate = BAUD_LOW

    def write(self, data: bytes, /) -> int:
        assert self.process.stdin is not None
        self.process.stdin.write(data)
        return len(data)

    def read(self, size: int = 1, /) -> bytes:
        assert self.process.stdout is not None
        return self.process.stdout.read(size)

    def reset_input_buffer(self) -> None:
        return None


@pytest.fixture
def console(hello: Path) -> Iterator[Console]:
    process = subprocess.Popen(
        [str(hello)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )
    # A console that stops answering must not hang the run.
    watchdog = threading.Timer(60, process.kill)
    watchdog.start()
    try:
        assert process.stdout is not None
        # An unbuffered pipe hands over what has arrived, not the size asked for.
        start = b""
        while len(start) < len(START):
            chunk = process.stdout.read(len(START) - len(start))
            assert chunk, "the console closed its output before it said hello"
            start += chunk
        assert start == START
        yield Console(PipePort(process))
    finally:
        watchdog.cancel()
        process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def test_the_host_console_says_hello_to_the_real_one(console: Console) -> None:
    assert console.hello() == BANNER


@pytest.mark.parametrize(
    "value", [0xDEADBEEF, 0x00000000, 0xA5A5A5A5, 0x5A5A5A5A, 0xFFFFFFFF, 1]
)
def test_the_host_console_writes_and_reads_the_register_of_the_real_one(
    console: Console, value: int
) -> None:
    console.write_register(value)
    assert console.read_register() == value


def test_the_host_console_is_refused_a_write_that_is_not_hexadecimal(
    console: Console,
) -> None:
    console.write_register(0x12345678)
    assert console.command("W zz") == "ERR"
    assert console.read_register() == 0x12345678


@pytest.mark.parametrize("baud", [BAUD_HIGH, BAUD_LOW])
def test_the_host_console_changes_the_baud_rate_with_the_real_one(
    console: Console, baud: int
) -> None:
    console.set_baud(baud)
    assert console.hello() == BANNER


def test_the_host_console_echoes_a_block_without_error(console: Console) -> None:
    measured = console.echo(pattern(16_384, seed=7))
    assert measured.errors == 0
    assert measured.bytes == 16_384
    assert console.hello() == BANNER
