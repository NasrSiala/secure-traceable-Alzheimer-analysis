import numpy as np

Q15_FRACTIONAL_BITS = 15
Q15_SCALE = 1 << Q15_FRACTIONAL_BITS
Q15_ROUNDING = 1 << (Q15_FRACTIONAL_BITS - 1)

INT16_MIN = -32768
INT16_MAX = 32767
INT64_MAX = (1 << 63) - 1


def round_shift_q15(accumulator):
    """Round to nearest; exact half-way cases are rounded away from zero."""
    value = int(accumulator)

    if value >= 0:
        return (value + Q15_ROUNDING) // Q15_SCALE

    return -((-value + Q15_ROUNDING) // Q15_SCALE)


def saturate_int16(value):
    """Saturate an integer to the signed int16 range."""
    return max(INT16_MIN, min(INT16_MAX, int(value)))


def fir_fixed_point_reference(samples, coefficients_q15):
    """
    Vectorized bit-exact causal FIR reference.

    - Signed Q1.15 input and coefficients.
    - Signed int64 accumulation.
    - Zero initial history.
    - Rounding to nearest, ties away from zero.
    - Signed int16 saturation.
    """
    samples = np.asarray(samples)
    coefficients = np.asarray(coefficients_q15)

    if samples.ndim != 1:
        raise ValueError("samples must be a one-dimensional array")

    if coefficients.ndim != 1 or len(coefficients) == 0:
        raise ValueError(
            "coefficients_q15 must be a non-empty one-dimensional array"
        )

    if not np.issubdtype(samples.dtype, np.integer):
        raise TypeError("samples must contain integers")

    if not np.issubdtype(coefficients.dtype, np.integer):
        raise TypeError("coefficients_q15 must contain integers")

    if np.any(samples < INT16_MIN) or np.any(samples > INT16_MAX):
        raise ValueError("samples must fit in signed int16")

    if np.any(coefficients < INT16_MIN) or np.any(coefficients > INT16_MAX):
        raise ValueError("coefficients must fit in signed int16")

    accumulator_bound = (
        (INT16_MAX + 1)
        * sum(abs(int(c)) for c in coefficients)
    )

    if accumulator_bound > INT64_MAX - Q15_ROUNDING:
        raise OverflowError(
            "FIR coefficients may overflow a signed int64 accumulator"
        )

    if len(samples) == 0:
        return np.empty(0, dtype=np.int16)

    # Integer convolution. The first len(samples) values implement
    # causal filtering with zero initial history.
    accumulated = np.convolve(
        samples.astype(np.int64),
        coefficients.astype(np.int64),
        mode="full"
    )[:len(samples)]

    # Exact signed rounding, with halfway cases away from zero.
    rounded = np.empty_like(accumulated)

    positive = accumulated >= 0
    negative = ~positive

    rounded[positive] = (
        accumulated[positive] + Q15_ROUNDING
    ) // Q15_SCALE

    rounded[negative] = -(
        (-accumulated[negative] + Q15_ROUNDING) // Q15_SCALE
    )

    # Saturate before conversion to int16.
    return np.clip(
        rounded,
        INT16_MIN,
        INT16_MAX
    ).astype(np.int16)
