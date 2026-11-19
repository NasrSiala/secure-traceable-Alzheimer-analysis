"""Mutations of hw/ps_app/bringup/hello.c: which behaviours of the console does a test pin?

Each mutation still compiles. The tests run with the real Vitis drivers (XILINX_VITIS), so the two
compile tests run too. A survivor is a behaviour that only the board run (T1.9) will check.

    py -3 audit/round-9/tools/mutate_hello.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELLO = ROOT / "hw" / "ps_app" / "bringup" / "hello.c"
VITIS = os.environ.get("XILINX_VITIS", r"E:\AMDDesignTools\2025.2\Vitis")
TESTS = ["tests/scripts/test_bringup_config.py", "hw/host/tests", "-m", "not board"]

MUTATIONS = [
    (
        "H1",
        "#define BAUD_HIGH 921600U",
        "#define BAUD_HIGH 9216000U",
        "921600 baud becomes 9216000",
    ),
    (
        "H2",
        "if (!parse_decimal(argument, &baud) || (baud != BAUD_LOW && baud != BAUD_HIGH)) {",
        "if (!parse_decimal(argument, &baud)) {",
        "any baud rate is accepted",
    ),
    ("H3", "if (digits > 8U) {", "if (digits > 9U) {", "nine hex digits are accepted"),
    (
        "H4",
        "if (!parse_decimal(argument, &count) || count > ECHO_MAX_BYTES) {",
        "if (!parse_decimal(argument, &count) || count > 2UL * ECHO_MAX_BYTES) {",
        "the echo limit is doubled",
    ),
    ("H5", 'put_text("\\r\\nDONE");', 'put_text("DONE");', "no empty line before DONE"),
    (
        "H6",
        "Xil_Out32(BRINGUP_REG_BASE, value);",
        "Xil_Out32(BRINGUP_REG_BASE + 4UL, value);",
        "the write goes to the next register",
    ),
    (
        "H7",
        'static const char digits[] = "0123456789abcdef";',
        'static const char digits[] = "0123456789ABCDEF";',
        "upper-case hex in the reply",
    ),
    (
        "H8",
        "        if (c == '\\r') {\n            continue;\n        }\n",
        "",
        "CR is no longer ignored",
    ),
    (
        "H9",
        "    while (!XUartPs_IsTransmitEmpty(&uart) || XUartPs_IsTransmitActive(uart_base)) {\n    }\n",
        "",
        "the baud rate changes without waiting for the reply to leave",
    ),
    (
        "H10",
        "#define BRINGUP_REG_BASE 0x43C00000UL",
        "#define BRINGUP_REG_BASE 0x43C10000UL",
        "register base address",
    ),
    (
        "H11",
        'put_text("hello SAAM-BRINGUP 1");\n        reply_end();\n        break;',
        'put_text("hello SAAM-BRINGUP 2");\n        reply_end();\n        break;',
        "banner of the H command",
    ),
    (
        "H12",
        "return too_long ? -1 : (int)length;",
        "return (int)length;",
        "a line that is too long is no longer reported",
    ),
    (
        "H13",
        " || XUartPs_IsTransmitActive(uart_base)",
        "",
        "AUD-118: the baud rate changes while the last character is still in the shifter",
    ),
]


def main() -> int:
    raw = HELLO.read_bytes()
    survivors = []
    try:
        for key, old, new, note in MUTATIONS:
            text = raw.decode("utf-8")
            if text.count(old) != 1:
                print(f"{key}  NOT APPLIED ({text.count(old)} matches)  {note}")
                survivors.append(f"{key}(not applied)")
                continue
            HELLO.write_bytes(text.replace(old, new).encode("utf-8"))
            done = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *TESTS,
                    "-q",
                    "-x",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "addopts=",
                ],
                cwd=ROOT,
                env={**os.environ, "XILINX_VITIS": VITIS},
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=False,
            )
            last = (done.stdout.strip().splitlines() or [""])[-1]
            killed = done.returncode != 0
            print(f"{key}  {'killed  ' if killed else 'SURVIVED'}  {note}  [{last}]")
            sys.stdout.flush()
            if not killed:
                survivors.append(key)
    finally:
        HELLO.write_bytes(raw)
    print("survivors:", survivors or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
