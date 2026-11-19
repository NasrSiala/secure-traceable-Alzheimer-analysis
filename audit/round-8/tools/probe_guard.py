"""What the NFR-03 guard sees in a free technical token (`softwareVersion`).

The guard's name and date-of-birth patterns are heuristics over a field the chaincode bounds only
by length (64). This prints, for candidate values that a careless or hostile writer could use,
whether the guard flags them. It reads values from this file only and prints no record.

    py -3 audit/round-8/tools/probe_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "integrity"))

import phi_guard
from synthetic_case import clean_history

CASES = [
    # (label, value, expected to be flagged by the project's own policy)
    ("version x.y.z", "0.1.0", False),
    ("model version", "ecg-cnn-1.0.0", False),
    ("git short hash", "a1b2c3d", False),
    ("name with a space", "Jean Dupont", True),
    ("name with a hyphen", "Jean-Pierre-Martin", True),
    ("lower-case dotted name", "jean.dupont", True),
    ("single surname", "dupont", True),
    ("camel-case name", "JeanDupont", True),
    ("name and initial", "dupont.j", True),
    ("dob YYYY-MM-DD", "1975-03-12", True),
    ("dob compact YYYYMMDD", "19750312", True),
    ("dob compact DDMMYYYY", "12031975", True),
    ("dob 2-digit year", "12-03-75", True),
    ("dob before 1900", "1890-03-12", True),
    ("dob year only", "1975", True),
    ("dob month-year", "1975-03", True),
    ("dob words", "born1975", True),
    ("trailing newline", "0.1.0\n", False),
]


def main() -> int:
    missed = 0
    for label, value, should_flag in CASES:
        records = clean_history("probe")
        records[0]["softwareVersion"] = value
        flagged = bool(phi_guard.check_history(records))
        verdict = "ok" if flagged == should_flag else "NOT AS EXPECTED"
        if flagged != should_flag:
            missed += 1
        print(
            f"{label:28s} flagged={flagged!s:5s} expected={should_flag!s:5s} {verdict}"
        )
    print(f"{missed} value(s) not handled as the policy expects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
