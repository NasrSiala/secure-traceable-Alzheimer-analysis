"""Checks for the isolated FIR scale experiment helpers."""

import numpy as np
import pytest

from scripts.experiments.fir_scale_x2 import (
    _float_reference,
    _rsb,
    double_int16_input,
)


def test_scale_x2_preserves_values_without_clipping() -> None:
    samples = np.array([[-1200, 0, 1200]], dtype=np.int16)

    scaled, clip_count = double_int16_input(samples)

    assert scaled.dtype == np.int64
    assert np.array_equal(scaled, [[-2400, 0, 2400]])
    assert clip_count == 0


def test_scale_x2_rejects_values_that_would_wrap_int16() -> None:
    samples = np.array([[16384]], dtype=np.int16)

    with pytest.raises(OverflowError, match="would clip 1 int16 input samples"):
        double_int16_input(samples)


def test_scale_x2_accepts_exact_signed_int16_lower_boundary() -> None:
    samples = np.array([[-16384, 16383]], dtype=np.int16)

    scaled, clip_count = double_int16_input(samples)

    assert np.array_equal(scaled, [[-32768, 32766]])
    assert clip_count == 0


def test_scale_x2_rejects_negative_overflow_boundary() -> None:
    samples = np.array([[-16385]], dtype=np.int16)

    with pytest.raises(OverflowError, match="would clip 1 int16 input samples"):
        double_int16_input(samples)


def test_float_reference_has_contractual_decimated_shape() -> None:
    samples = np.zeros((12, 5000), dtype=np.int16)
    coefficients = np.zeros(111, dtype=np.int16)
    coefficients[55] = 32768 - 1

    reference = _float_reference(samples, coefficients)

    assert reference.shape == (12, 1011)
    assert np.count_nonzero(reference) == 0


def test_rsb_uses_aggregate_signal_and_error_power() -> None:
    reference = np.array([3.0, 4.0])
    fixed = np.array([3.0, 3.0])

    result = _rsb(reference, fixed)

    assert result["rsb_db"] == pytest.approx(10 * np.log10(25.0))
    assert result["error_rms"] == pytest.approx(np.sqrt(0.5))


@pytest.mark.parametrize(
    "reference,fixed",
    [
        (np.zeros(3), np.zeros(3)),
        (np.ones(3), np.ones(3)),
    ],
)
def test_rsb_rejects_zero_signal_or_zero_error(
    reference: np.ndarray, fixed: np.ndarray
) -> None:
    with pytest.raises(ValueError, match="RSB is undefined"):
        _rsb(reference, fixed)
