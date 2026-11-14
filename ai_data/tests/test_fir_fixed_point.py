import numpy as np
import pytest

from ai_data.ptbxl.fir_fixed_point import (
    fir_fixed_point_reference,
    round_shift_q15,
    saturate_int16,
)


def test_identity_filter():
    samples = np.array([1000, -2000, 3000], dtype=np.int16)
    coefficients = np.array([32767], dtype=np.int16)

    result = fir_fixed_point_reference(samples, coefficients)

    assert result.dtype == np.int16
    assert np.array_equal(result, samples)


def test_causal_filter_uses_zero_initial_history():
    samples = np.array([16384], dtype=np.int16)
    coefficients = np.array([16384, 16384], dtype=np.int16)

    result = fir_fixed_point_reference(samples, coefficients)

    assert result.tolist() == [8192]


def test_positive_rounding_half_away_from_zero():
    assert round_shift_q15(16384) == 1


def test_negative_rounding_half_away_from_zero():
    assert round_shift_q15(-16384) == -1


def test_rounding_values_near_half():
    assert round_shift_q15(16383) == 0
    assert round_shift_q15(16385) == 1
    assert round_shift_q15(-16383) == 0
    assert round_shift_q15(-16385) == -1


def test_int16_saturation():
    assert saturate_int16(40000) == 32767
    assert saturate_int16(-40000) == -32768
    assert saturate_int16(1234) == 1234


def test_filter_output_saturates():
    samples = np.array([32767, 32767], dtype=np.int16)
    coefficients = np.array([32767, 32767], dtype=np.int16)

    result = fir_fixed_point_reference(samples, coefficients)

    assert result[0] == 32766
    assert result[1] == 32767


def test_rejects_two_dimensional_samples():
    samples = np.array([[1000, 2000]], dtype=np.int16)
    coefficients = np.array([32767], dtype=np.int16)

    with pytest.raises(ValueError):
        fir_fixed_point_reference(samples, coefficients)


def test_rejects_empty_coefficients():
    samples = np.array([1000], dtype=np.int16)
    coefficients = np.array([], dtype=np.int16)

    with pytest.raises(ValueError):
        fir_fixed_point_reference(samples, coefficients)


def test_rejects_floating_point_samples():
    samples = np.array([0.5, -0.5], dtype=np.float64)
    coefficients = np.array([32767], dtype=np.int16)

    with pytest.raises(TypeError):
        fir_fixed_point_reference(samples, coefficients)


def test_rejects_samples_outside_int16():
    samples = np.array([40000], dtype=np.int64)
    coefficients = np.array([32767], dtype=np.int16)

    with pytest.raises(ValueError):
        fir_fixed_point_reference(samples, coefficients)


def test_rejects_coefficients_outside_int16():
    samples = np.array([1000], dtype=np.int16)
    coefficients = np.array([40000], dtype=np.int64)

    with pytest.raises(ValueError):
        fir_fixed_point_reference(samples, coefficients)
