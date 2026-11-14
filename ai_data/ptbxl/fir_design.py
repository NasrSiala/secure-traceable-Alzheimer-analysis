import numpy as np
from scipy.signal import firwin, freqz, kaiserord

# ============================================================
# FIR FILTER SPECIFICATION
# ============================================================

FS = 500
PASSBAND_LOW = 0.5
PASSBAND_HIGH = 40.0
STOPBAND_LOW = 0.1
STOPBAND_HIGH = 42.0

ATTENUATION_TARGET_DB = 60
MIN_Q15_ATTENUATION_DB = 45
MAX_Q15_RIPPLE_DB = 0.05

Q15_SCALE = 2**15
NUM_FREQ_POINTS = 524288


def design_fir():
    """Design a linear-phase Kaiser-window FIR bandpass filter."""
    transition_width = (PASSBAND_LOW - STOPBAND_LOW) / (FS / 2)

    numtaps, beta = kaiserord(
        ATTENUATION_TARGET_DB,
        transition_width
    )

    if numtaps % 2 == 0:
        numtaps += 1

    coefficients = firwin(
        numtaps=numtaps,
        cutoff=[
            (STOPBAND_LOW + PASSBAND_LOW) / 2,
            (PASSBAND_HIGH + STOPBAND_HIGH) / 2
        ],
        window=("kaiser", beta),
        pass_zero=False,
        fs=FS,
        scale=True
    )

    return coefficients, beta


def quantize_q15(coefficients):
    """Quantize floating-point coefficients to signed Q1.15."""
    quantized = np.clip(
        np.rint(coefficients * Q15_SCALE),
        -32768,
        32767
    ).astype(np.int16)

    return quantized


def measure_response(coefficients):
    """Measure stopband attenuation and passband ripple."""
    frequencies, response = freqz(
        coefficients,
        worN=NUM_FREQ_POINTS,
        fs=FS
    )

    magnitude_db = 20 * np.log10(
        np.maximum(np.abs(response), 1e-15)
    )

    low_stopband = frequencies <= STOPBAND_LOW
    passband = (
        (frequencies >= PASSBAND_LOW)
        & (frequencies <= PASSBAND_HIGH)
    )
    high_stopband = frequencies >= STOPBAND_HIGH

    return {
        "low_stopband_db": float(np.max(magnitude_db[low_stopband])),
        "passband_min_db": float(np.min(magnitude_db[passband])),
        "passband_max_db": float(np.max(magnitude_db[passband])),
        "passband_ripple_db": float(
            np.max(magnitude_db[passband])
            - np.min(magnitude_db[passband])
        ),
        "high_stopband_db": float(np.max(magnitude_db[high_stopband]))
    }


def main():
    coefficients, beta = design_fir()
    quantized = quantize_q15(coefficients)

    print("=== FIR DESIGN ===")
    print("Sampling frequency:", FS, "Hz")
    print("Number of coefficients:", len(coefficients))
    print("Filter order:", len(coefficients) - 1)
    print("Group delay:", (len(coefficients) - 1) / (2 * FS), "seconds")
    print("Kaiser beta:", beta)

    print("\n=== Q1.15 COEFFICIENTS ===")
    print("Minimum:", int(quantized.min()))
    print("Maximum:", int(quantized.max()))
    print("Sum:", int(quantized.astype(np.int64).sum()))
    print("Symmetry:", np.array_equal(quantized, quantized[::-1]))

    print("\n=== FLOAT64 RESPONSE ===")
    for name, value in measure_response(coefficients).items():
        print(f"{name}: {value:.4f} dB")

    print("\n=== Q1.15 RESPONSE ===")
    for name, value in measure_response(
        quantized.astype(np.float64) / Q15_SCALE
    ).items():
        print(f"{name}: {value:.4f} dB")


if __name__ == "__main__":
    main()
