"""Contract checks for generated Q1.15 FIR coefficient metadata."""

import json
from pathlib import Path

import numpy as np

from hw.gen.gen_fir_coeffs import measure_response
from saam.hashing import artifact_hash

ROOT = Path(__file__).resolve().parents[2]


def test_quantized_coefficients_meet_ac16_1_template() -> None:
    data = json.loads((ROOT / "saam/dsp/fir_coeffs.json").read_text())
    coefficients = np.asarray(data["coefficients_q15"], dtype=np.float64) / 32768

    response = measure_response(coefficients)

    assert response["passband_ripple_db"] <= 0.5
    assert response["stopband_attenuation_db"] >= 40


def test_fir_coefficient_id_uses_shared_hash_without_changing_id() -> None:
    data = json.loads((ROOT / "saam/dsp/fir_coeffs.json").read_text())
    expected_id = data.pop("fir_coef_id")

    assert expected_id == "b6d7a73a"
    first_id = artifact_hash(data)[:8]
    second_id = artifact_hash(data)[:8]
    assert first_id == second_id == expected_id
