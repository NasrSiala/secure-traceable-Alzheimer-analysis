import json
from pathlib import Path

import numpy as np
import pytest

from saam.dsp.fir_fixed import (
    fir_fixed_point_decimated,
    fir_fixed_point_multilead,
    round_shift_q15,
    saturate_int16,
)


ROOT = Path(__file__).resolve().parents[2]

with (ROOT / "saam" / "dsp" / "fir_coeffs.json").open(
    encoding="utf-8"
) as file:
    COEFFICIENTS = np.array(
        json.load(file)["coefficients_q15"],
        dtype=np.int16,
    )


def test_output_has_expected_length_and_dtype():
    signal = np.zeros(5000, dtype=np.int16)

    result = fir_fixed_point_decimated(signal, COEFFICIENTS)

    assert result.shape == (1011,)
    assert result.dtype == np.int16


def test_zero_input_produces_zero_output():
    signal = np.zeros(5000, dtype=np.int16)

    result = fir_fixed_point_decimated(signal, COEFFICIENTS)

    assert np.array_equal(result, np.zeros(1011, dtype=np.int16))


def test_rounding_halfway_cases_toward_positive_infinity():
    assert round_shift_q15(16384) == 1
    assert round_shift_q15(-16384) == 0
    assert round_shift_q15(49152) == 2
    assert round_shift_q15(-49152) == -1


def test_rounding_near_halfway_cases():
    assert round_shift_q15(16383) == 0
    assert round_shift_q15(16385) == 1
    assert round_shift_q15(-16383) == 0
    assert round_shift_q15(-16385) == -1


def test_int16_saturation():
    assert saturate_int16(40000) == 32767
    assert saturate_int16(-40000) == -32768
    assert saturate_int16(1234) == 1234


def test_multilead_output_shape():
    signals = np.zeros((12, 5000), dtype=np.int16)

    result = fir_fixed_point_multilead(signals, COEFFICIENTS)

    assert result.shape == (12, 1011)
    assert result.dtype == np.int16


def test_multilead_processes_leads_independently():
    signals = np.zeros((12, 5000), dtype=np.int16)
    signals[0, 100] = 10000

    result = fir_fixed_point_multilead(signals, COEFFICIENTS)

    assert np.any(result[0] != 0)
    assert np.all(result[1:] == 0)


def test_rejects_wrong_signal_length():
    signal = np.zeros(4999, dtype=np.int16)

    with pytest.raises(ValueError):
        fir_fixed_point_decimated(signal, COEFFICIENTS)


def test_rejects_wrong_number_of_coefficients():
    signal = np.zeros(5000, dtype=np.int16)

    with pytest.raises(ValueError):
        fir_fixed_point_decimated(signal, COEFFICIENTS[:-1])


def test_rejects_floating_point_samples():
    signal = np.zeros(5000, dtype=np.float64)

    with pytest.raises(TypeError):
        fir_fixed_point_decimated(signal, COEFFICIENTS)


def test_rejects_wrong_multilead_shape():
    signals = np.zeros((10, 5000), dtype=np.int16)

    with pytest.raises(ValueError):
        fir_fixed_point_multilead(signals, COEFFICIENTS)


def test_filter_matches_independent_reference_equation():
    rng = np.random.default_rng(2026)
    signal = rng.integers(
        -32768, 32768, size=5000, dtype=np.int16
    )

    result = fir_fixed_point_decimated(signal, COEFFICIENTS)

    padded = np.pad(signal, (0, 55))
    expected = []

    for m in range(1011):
        n = 5 * m

        accumulator = sum(
            int(COEFFICIENTS[k]) * int(padded[n - k])
            for k in range(111)
            if 0 <= n - k < len(padded)
        )

        rounded = (accumulator + (1 << 14)) >> 15
        expected.append(max(-32768, min(32767, rounded)))

    assert np.array_equal(result, np.array(expected, dtype=np.int16))


def test_filter_applies_real_output_saturation():
    positive_signal = np.full(5000, 32767, dtype=np.int16)
    negative_signal = np.full(5000, -32768, dtype=np.int16)

    positive_result = fir_fixed_point_decimated(
        positive_signal, COEFFICIENTS
    )
    negative_result = fir_fixed_point_decimated(
        negative_signal, COEFFICIENTS
    )

    # After 110 input samples, the complete FIR history is filled.
    # Before the end padding starts affecting the window, saturation
    # must occur for both positive and negative full-scale inputs.
    assert np.all(positive_result[22:1000] == 32767)
    assert np.all(negative_result[22:1000] == -32768)
