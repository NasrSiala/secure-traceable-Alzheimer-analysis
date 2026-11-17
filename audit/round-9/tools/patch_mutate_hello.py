"""One-off: bring mutate_hello.py in line with the fixed hello.c (AUD-118).

The H9 mutation named the loop as it was before the fix; it now names the fixed loop, and H13 drops
only the new `XUartPs_IsTransmitActive` condition, which is the fix.
"""

from __future__ import annotations

from pathlib import Path

TOOL = Path(__file__).resolve().parent / "mutate_hello.py"
BS = chr(92)  # a backslash: the source of the tool holds the two characters \ and n

old_loop = '"    while (!XUartPs_IsTransmitEmpty(&uart)) {' + BS + "n    }" + BS + 'n"'
new_loop = (
    '"    while (!XUartPs_IsTransmitEmpty(&uart) || XUartPs_IsTransmitActive(uart_base)) {'
    + BS
    + "n    }"
    + BS
    + 'n"'
)

text = TOOL.read_text(encoding="utf-8")
assert text.count(old_loop) == 1, text.count(old_loop)
text = text.replace(old_loop, new_loop)

extra = (
    '    (\n        "H13",\n'
    '        " || XUartPs_IsTransmitActive(uart_base)",\n'
    '        "",\n'
    '        "AUD-118: the baud rate changes while the last character is still in the shifter",\n'
    "    ),\n]\n"
)
marker = "]\n\n\ndef main()"
assert text.count(marker) == 1
text = text.replace(marker, extra + "\n\ndef main()")
TOOL.write_text(text, encoding="utf-8", newline="\n")
print("patched")
