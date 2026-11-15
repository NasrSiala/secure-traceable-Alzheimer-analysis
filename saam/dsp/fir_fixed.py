import numpy as np


FS = 500
NUM_TAPS = 111
DECIMATION = 5
INPUT_SAMPLES = 5000
TAIL_PADDING = 55
OUTPUT_SAMPLES = 1011

Q15_FRACTIONAL_BITS = 15
Q15_ROUNDING = 1 << 14

INT16_MIN = -32768
INT16_MAX = 32767
INT32_MAX = (1 << 31) - 1


def _validate(samples, coefficients_q15):
    samples = np.asarray(samples)
    coefficients = np.asarray(coefficients_q15)

    if samples.ndim != 1:
        raise ValueError("samples must be one-dimensional")

    if len(samples) != INPUT_SAMPLES:
        raise ValueError(
            f"samples must contain exactly {INPUT_SAMPLES} values"
        )

    if not np.issubdtype(samples.dtype, np.integer):
        raise TypeError("samples must contain integers")

    if np.any(samples < INT16_MIN) or np.any(samples > INT16_MAX):
        raise ValueError("samples must fit in signed int16")

    if coefficients.ndim != 1 or len(coefficients) != NUM_TAPS:
        raise ValueError(
            f"coefficients_q15 must contain exactly {NUM_TAPS} values"
        )

    if not np.issubdtype(coefficients.dtype, np.integer):
        raise TypeError("coefficients_q15 must contain integers")

    if np.any(coefficients < INT16_MIN) or np.any(coefficients > INT16_MAX):
        raise ValueError("coefficients must fit in signed int16")

    coefficients = coefficients.astype(np.int64)

    accumulator_bound = (
        32768 * sum(abs(int(value)) for value in coefficients)
    )

    if accumulator_bound > INT32_MAX:
        raise OverflowError(
            "The coefficient set exceeds the signed int32 accumulator bound"
        )

    return samples.astype(np.int16), coefficients


def round_shift_q15(accumulator):
    """Arithmetic Q1.15 shift with halfway cases rounded toward +infinity."""
    return (int(accumulator) + Q15_ROUNDING) >> Q15_FRACTIONAL_BITS


def saturate_int16(value):
    """Saturate an integer to the signed int16 range."""
    return max(INT16_MIN, min(INT16_MAX, int(value)))


def fir_fixed_point_decimated(samples, coefficients_q15):
    """
    Bit-exact causal FIR reference with decimation by five.

    Input:
        5000 signed int16 samples.

    Processing:
        111 Q1.15 coefficients.
        Zero initial history.
        55 zero samples appended at the end.
        Output positions: 0, 5, 10, ..., 5050.
        Arithmetic shift with rounding toward positive infinity.
        Signed int16 saturation.

    Output:
        1011 signed int16 samples.
    """
    samples, coefficients = _validate(samples, coefficients_q15)

    padded = np.concatenate([
        samples,
        np.zeros(TAIL_PADDING, dtype=np.int16),
    ])

    output = np.empty(OUTPUT_SAMPLES, dtype=np.int16)

    for m in range(OUTPUT_SAMPLES):
        n = DECIMATION * m
        accumulator = 0

        for k in range(NUM_TAPS):
            index = n - k

            if 0 <= index < len(padded):
                accumulator += (
                    int(coefficients[k]) * int(padded[index])
                )

        rounded = round_shift_q15(accumulator)
        output[m] = saturate_int16(rounded)

    return output


def fir_fixed_point_multilead(signals, coefficients_q15):
    """
    Apply the FIR independently to 12 ECG leads.

    Input shape:  (12, 5000)
    Output shape: (12, 1011)
    """
    signals = np.asarray(signals)

    if signals.ndim != 2 or signals.shape != (12, INPUT_SAMPLES):
        raise ValueError("signals must have shape (12, 5000)")

    results = np.empty((12, OUTPUT_SAMPLES), dtype=np.int16)

    for lead in range(12):
        results[lead] = fir_fixed_point_decimated(
            signals[lead],
            coefficients_q15,
        )

    return results
