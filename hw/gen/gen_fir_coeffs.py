import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import freqz, remez

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saam.hashing import artifact_hash

FS = 500
NUM_TAPS = 111
PASSBAND_EDGE = 40.0
STOPBAND_EDGE = 50.0
Q15_SCALE = 1 << 15
INT16_MIN = -32768
INT16_MAX = 32767


def design_coefficients():
    """Design a 111-tap low-pass FIR using the Parks-McClellan algorithm."""
    coefficients = remez(
        NUM_TAPS,
        [0.0, PASSBAND_EDGE, STOPBAND_EDGE, FS / 2],
        [1.0, 0.0],
        weight=[1.0, 10.0],
        fs=FS,
        maxiter=1000,
        grid_density=32,
    )

    return coefficients


def quantize_q15(coefficients):
    """Quantize coefficients to signed Q1.15."""
    scaled = np.rint(coefficients * Q15_SCALE)

    if np.any(scaled < INT16_MIN) or np.any(scaled > INT16_MAX):
        raise ValueError("A coefficient exceeds the signed Q1.15 range")

    quantized = scaled.astype(np.int16)

    if not np.array_equal(quantized, quantized[::-1]):
        raise ValueError("Quantized coefficients are not symmetric")

    return quantized


def measure_response(coefficients):
    """Measure passband ripple and stopband attenuation."""
    frequencies, response = freqz(
        coefficients,
        worN=524288,
        fs=FS,
    )

    magnitude = np.maximum(np.abs(response), 1e-15)
    magnitude_db = 20.0 * np.log10(magnitude)

    passband = frequencies <= PASSBAND_EDGE
    stopband = frequencies >= STOPBAND_EDGE

    passband_db = magnitude_db[passband]
    stopband_db = magnitude_db[stopband]

    return {
        "passband_ripple_db": float(
            np.max(passband_db) - np.min(passband_db)
        ),
        "stopband_attenuation_db": float(-np.max(stopband_db)),
    }


def generate_json(quantized):
    payload = {
        "sample_rate_hz": FS,
        "num_taps": NUM_TAPS,
        "q_format": "Q1.15",
        "decimation_factor": 5,
        "coefficients_q15": [int(value) for value in quantized],
    }

    coef_id = artifact_hash(payload)[:8]
    payload["fir_coef_id"] = coef_id

    output = ROOT / "saam" / "dsp" / "fir_coeffs.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    return coef_id


def generate_vhdl(quantized, coef_id):
    values = ",\n".join(
        f"        {index} => {int(value)}"
        for index, value in enumerate(quantized)
    )

    source = f"""library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package fir_coeffs_pkg is
    constant FIR_NUM_TAPS : positive := {NUM_TAPS};
    constant FIR_DECIMATION : positive := 5;
    constant FIR_COEF_ID : string := "{coef_id}";

    type fir_coeff_array_t is array (0 to FIR_NUM_TAPS - 1)
        of integer range -32768 to 32767;

    constant FIR_COEFFS_Q15 : fir_coeff_array_t := (
{values}
    );
end package fir_coeffs_pkg;
"""

    output = ROOT / "hw" / "rtl" / "fir_coeffs_pkg.vhd"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(source, encoding="utf-8")


def main():
    coefficients = design_coefficients()
    quantized = quantize_q15(coefficients)

    coef_id = generate_json(quantized)
    generate_vhdl(quantized, coef_id)

    float_response = measure_response(coefficients)
    fixed_response = measure_response(
        quantized.astype(np.float64) / Q15_SCALE
    )

    print("=== FIR COEFFICIENT GENERATION ===")
    print("Sampling frequency:", FS, "Hz")
    print("Number of taps:", NUM_TAPS)
    print("Group delay:", (NUM_TAPS - 1) // 2, "samples")
    print("Decimation factor: 5")
    print("Q format: Q1.15")
    print("Coefficient ID:", coef_id)
    print("Coefficient sum:", int(quantized.astype(np.int64).sum()))
    print("Coefficient symmetry:", np.array_equal(quantized, quantized[::-1]))
    print("Minimum coefficient:", int(quantized.min()))
    print("Maximum coefficient:", int(quantized.max()))

    print("\n=== FLOATING-POINT RESPONSE ===")
    for name, value in float_response.items():
        print(f"{name}: {value:.4f}")

    print("\n=== QUANTIZED Q1.15 RESPONSE ===")
    for name, value in fixed_response.items():
        print(f"{name}: {value:.4f}")

    print("\nGenerated:")
    print(" - saam/dsp/fir_coeffs.json")
    print(" - hw/rtl/fir_coeffs_pkg.vhd")


if __name__ == "__main__":
    main()
