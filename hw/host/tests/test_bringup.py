"""T1.9 (l10-board-bringup): the Zybo Z7-10 boots from the SD card and the bring-up console answers.

Marker `board`: never part of the default run. It needs the board, powered, booted from the SD card
(BOOT.bin from hw/ps_app/bringup/build_app.py), and its UART port in SAAM_ZYBO_PORT (for example
COM5 or /dev/ttyUSB1: the FT2232 of the board shows two ports, the UART is the second one).
Without that variable, or without pyserial, every test here is SKIPPED with the reason, and no
serial device is opened: a skip is not a pass.

    SAAM_ZYBO_PORT=COM5 scripts/test-l.sh --board

What it proves, once it runs on the board:
  1. the application boots and says hello;
  2. the PL register answers over AXI4-Lite: write from the PS, read back, several patterns;
  3. the UART keeps its throughput at 115 200 and 921 600 baud, bytes exact.
The measures are written to hw/reports/bringup-uart.json (SAAM_HW_REPORT_DIR moves it) only by a
real run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from bringup_support import (
    BANNER,
    BAUD_HIGH,
    BAUD_LOW,
    Console,
    Throughput,
    pattern,
)

pytestmark = pytest.mark.board

# Bytes sent per rate: about one second of line time at 115 200, 0.7 s at 921 600.
BLOCK = {BAUD_LOW: 16_384, BAUD_HIGH: 65_536}
# A floor for a bring-up, not a requirement: 50 % of the best the line can do. NFR-20 (one
# hash and one filter, 15 s at 115 200) has a wide margin on top of it.
MIN_RATIO = 0.5
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def console() -> Iterator[Console]:
    port_name = os.environ.get("SAAM_ZYBO_PORT", "").strip()
    if not port_name:
        pytest.skip("SAAM_ZYBO_PORT is not set: no board access, nothing was opened")
    serial = pytest.importorskip("serial", reason="pyserial is not installed (TRD 18)")
    port = serial.Serial(port_name, BAUD_LOW, timeout=3, write_timeout=10)
    try:
        port.reset_input_buffer()
        yield Console(port)
    finally:
        port.close()


def test_the_board_says_hello(console: Console) -> None:
    assert console.hello() == BANNER


@pytest.mark.parametrize(
    "value", [0xDEADBEEF, 0x00000000, 0xA5A5A5A5, 0x5A5A5A5A, 0xFFFFFFFF, 1]
)
def test_the_pl_register_keeps_what_the_ps_writes(console: Console, value: int) -> None:
    console.write_register(value)
    assert console.read_register() == value


def test_the_register_ignores_a_write_that_is_not_hexadecimal(console: Console) -> None:
    console.write_register(0x12345678)
    assert console.command("W zz") == "ERR"
    assert console.read_register() == 0x12345678


@pytest.mark.parametrize("baud", [BAUD_LOW, BAUD_HIGH])
def test_the_uart_throughput(console: Console, baud: int) -> None:
    try:
        if baud != BAUD_LOW:
            console.set_baud(baud)
        console.hello()
        measured: Throughput = console.echo(pattern(BLOCK[baud], seed=baud))
    finally:
        if console.port.baudrate != BAUD_LOW:
            console.set_baud(BAUD_LOW)

    report_dir = Path(os.environ.get("SAAM_HW_REPORT_DIR") or ROOT / "hw" / "reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "bringup-uart.json"
    previous = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    previous[str(baud)] = measured.as_json()
    report.write_text(
        json.dumps(previous, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    assert measured.errors == 0
    assert measured.ratio >= MIN_RATIO, (
        f"{measured.bytes_per_second:.0f} B/s at {baud} baud"
    )


def test_the_console_is_back_at_115200_afterwards(console: Console) -> None:
    assert console.port.baudrate == BAUD_LOW
    assert console.hello() == BANNER
