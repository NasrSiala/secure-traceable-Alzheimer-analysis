import csv
from pathlib import Path

import numpy as np

from ai_data.ptbxl.fir_design import (
    design_fir,
    measure_response,
    quantize_q15,
)


def test_fir_has_expected_number_of_coefficients():
    coefficients, _ = design_fir()
    assert len(coefficients) == 4533
    assert len(coefficients) % 2 == 1


def test_fir_coefficients_are_symmetric():
    coefficients, _ = design_fir()
    quantized = quantize_q15(coefficients)

    assert np.allclose(coefficients, coefficients[::-1])
    assert np.array_equal(quantized, quantized[::-1])


def test_q15_coefficients_fit_int16():
    coefficients, _ = design_fir()
    quantized = quantize_q15(coefficients)

    assert quantized.dtype == np.int16
    assert quantized.min() >= -32768
    assert quantized.max() <= 32767


def test_q15_coefficient_sum_is_reproducible():
    coefficients, _ = design_fir()
    quantized = quantize_q15(coefficients)

    assert int(quantized.astype(np.int64).sum()) == 133


def test_float64_frequency_response():
    coefficients, _ = design_fir()
    response = measure_response(coefficients)

    assert response["low_stopband_db"] <= -55
    assert response["high_stopband_db"] <= -70
    assert response["passband_ripple_db"] <= 0.02


def test_q15_frequency_response():
    coefficients, _ = design_fir()
    quantized = quantize_q15(coefficients)

    response = measure_response(
        quantized.astype(np.float64) / (2**15)
    )

    assert response["low_stopband_db"] <= -45
    assert response["high_stopband_db"] <= -50
    assert response["passband_ripple_db"] <= 0.05


def test_q15_csv_contains_all_coefficients():
    coefficients, _ = design_fir()
    quantized = quantize_q15(coefficients)

    csv_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "fir_coefficients_q15.csv"
    )

    with csv_path.open("r", newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 4533
    assert rows[0]["index"] == "0"
    assert rows[-1]["index"] == "4532"

    csv_values = np.array(
        [int(row["coefficient_q15"]) for row in rows],
        dtype=np.int16
    )

    assert np.array_equal(csv_values, quantized)
