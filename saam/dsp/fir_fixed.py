"""Bit-exact FIR decimator (Architecture §5.6, ADR-14, IF-06).

y[m] = sat16((sum_k q[k] * x[5m - k] + 2^14) >> 15), x[n < 0] = 0.
The right shift is arithmetic: nearest, halves toward +inf. One call has no
memory of the previous call. Coefficients come from fir_coeffs.json, the file
produced by hw/gen/gen_fir_coeffs.py. fir_coef_id is SHA-256 of that file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_JSON_PATH = Path(__file__).with_name("fir_coeffs.json")
_TAPS = 111
_INT16_MIN = -32768
_INT16_MAX = 32767


def load_coeffs() -> tuple[int, ...]:
    """The 111 Q1.15 taps, in causal order (q[0] multiplies the newest sample)."""
    document = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    coeffs = document["q"]
    if len(coeffs) != _TAPS:
        raise ValueError(f"fir_coeffs.json has {len(coeffs)} taps, expected {_TAPS}")
    values = tuple(int(coef) for coef in coeffs)
    for coef in values:
        if coef < _INT16_MIN or coef > _INT16_MAX:
            raise ValueError("coefficient out of Q1.15")
    return values


def coef_id() -> str:
    """First 8 hex digits of SHA-256 of the JCS file bytes."""
    return hashlib.sha256(_JSON_PATH.read_bytes()).hexdigest()[:8]


def filter_decimate(samples: list[int] | tuple[int, ...]) -> list[int]:
    """Decimate by 5. Outputs are the raw causal stage, including the group delay."""
    values = _as_int16(samples)
    coeffs = load_coeffs()
    count = len(values)
    outputs: list[int] = []
    produced = (count - 1) // 5 + 1 if count else 0
    for step in range(produced):
        newest = 5 * step
        accumulator = 0
        for tap, coef in enumerate(coeffs):
            index = newest - tap
            if index >= 0:
                accumulator += coef * values[index]
        outputs.append(_sat16((accumulator + (1 << 14)) >> 15))
    return outputs


def _as_int16(samples: list[int] | tuple[int, ...]) -> list[int]:
    if isinstance(samples, (str, bytes)) or not isinstance(samples, (list, tuple)):
        raise ValueError("samples must be a sequence of int16")  # noqa: TRY004
    values: list[int] = []
    for sample in samples:
        if isinstance(sample, bool) or not isinstance(sample, int):
            raise ValueError("samples must be a sequence of int16")  # noqa: TRY004
        if sample < _INT16_MIN or sample > _INT16_MAX:
            raise ValueError("sample out of int16 range")
        values.append(sample)
    return values


def _sat16(value: int) -> int:
    if value > _INT16_MAX:
        return _INT16_MAX
    if value < _INT16_MIN:
        return _INT16_MIN
    return value
