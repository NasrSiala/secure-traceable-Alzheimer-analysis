import numpy as np
import pytest

from saam.dsp.prepare import (
    assess_signal_quality,
    load_fir_coefficients,
    prepare_ecg,
)


def make_ecg(samples=5000, sampling_rate=500):
    """Create a deterministic synthetic 12-lead ECG-like signal."""
    time = np.arange(samples) / sampling_rate
    signal = np.zeros((samples, 12), dtype=np.float64)

    for lead in range(12):
        signal[:, lead] = (
            0.8 * np.sin(2 * np.pi * 1.2 * time + lead * 0.1)
            + 0.15 * np.sin(2 * np.pi * 15 * time)
        )

    return signal


def test_load_fir_coefficients():
    coefficients, coef_id = load_fir_coefficients()

    assert coefficients.shape == (111,)
    assert coefficients.dtype == np.int64
    assert isinstance(coef_id, str)
    assert len(coef_id) > 0


def test_prepare_ecg_output_shapes_and_types():
    result = prepare_ecg(
        make_ecg(),
        sampling_rate=500,
        units=["mV"] * 12,
    )

    assert result["fir_input"].shape == (12, 5000)
    assert result["fir_stage"].shape == (12, 1011)
    assert result["aligned"].shape == (12, 1000)
    assert result["filtered"].shape == (12, 1000)
    assert result["signal"].shape == (12, 1000)

    assert result["fir_input"].dtype == np.int16
    assert result["fir_stage"].dtype == np.int16
    assert result["aligned"].dtype == np.int16
    assert result["filtered"].dtype == np.float32
    assert result["signal"].dtype == np.float32

    for key in ("filtered", "signal"):
        assert np.isfinite(result[key]).all()

    assert result["quality_score"] == 1.0
    assert result["report"]["quality_pass"] is True


def test_prepare_ecg_preserves_fir_identifier():
    result = prepare_ecg(make_ecg(), sampling_rate=500)
    _, expected_id = load_fir_coefficients()

    assert result["report"]["fir_coef_id"] == expected_id


def test_prepare_ecg_resamples_250_hz_to_500_hz():
    result = prepare_ecg(
        make_ecg(samples=2500, sampling_rate=250),
        sampling_rate=250,
    )

    assert result["fir_input"].shape == (12, 5000)
    assert result["report"]["sampling_rate_input_hz"] == 250.0
    assert result["report"]["sampling_rate_fir_hz"] == 500


def test_prepare_ecg_rejects_wrong_number_of_leads():
    signal = np.zeros((5000, 11))

    with pytest.raises(ValueError, match="12"):
        prepare_ecg(signal, sampling_rate=500)


def test_prepare_ecg_rejects_record_shorter_than_10_seconds():
    signal = make_ecg(samples=4000)

    with pytest.raises(ValueError, match="at least 10 seconds"):
        prepare_ecg(signal, sampling_rate=500)


def test_prepare_ecg_rejects_non_finite_samples():
    signal = make_ecg()
    signal[100, 0] = np.nan

    with pytest.raises(ValueError, match="non-finite"):
        prepare_ecg(signal, sampling_rate=500)


def test_prepare_ecg_rejects_values_outside_int16_range():
    signal = make_ecg()
    signal[100, 0] = 40.0

    with pytest.raises(ValueError, match="int16 quantization range"):
        prepare_ecg(signal, sampling_rate=500)


def test_prepare_ecg_rejects_non_mv_units():
    with pytest.raises(ValueError, match="expressed in mV"):
        prepare_ecg(
            make_ecg(),
            sampling_rate=500,
            units=["uV"] * 12,
        )


def test_prepare_ecg_rejects_invalid_quality_threshold():
    with pytest.raises(ValueError, match="quality_min"):
        prepare_ecg(
            make_ecg(),
            sampling_rate=500,
            quality_min=1.5,
        )


def test_prepare_ecg_rejects_invalid_sampling_rate():
    with pytest.raises(ValueError, match="positive and finite"):
        prepare_ecg(make_ecg(), sampling_rate=0)


def test_prepare_ecg_report_contains_processing_parameters():
    result = prepare_ecg(make_ecg(), sampling_rate=500)
    report = result["report"]

    assert report["sampling_rate_output_hz"] == 100
    assert report["fir_num_taps"] == 111
    assert report["fir_decimation"] == 5
    assert report["alignment_removed_samples"] == 11
    assert report["high_pass"]["cutoff_hz"] == 0.5
    assert report["high_pass"]["order"] == 2
    assert report["normalization"] == "per-lead z-score"


def test_prepare_ecg_rejects_quality_below_threshold():
    signal = make_ecg()
    signal[:600, 0] = np.nan

    with pytest.raises(ValueError, match="below"):
        prepare_ecg(signal, sampling_rate=500, quality_min=0.90)


def test_prepare_ecg_rejects_invalid_samples_even_above_threshold():
    signal = make_ecg()
    signal[100, 0] = np.nan

    with pytest.raises(ValueError, match="despite meeting the quality threshold"):
        prepare_ecg(signal, sampling_rate=500, quality_min=0.90)


def test_quality_assessment_marks_nan_samples_per_lead():
    signal = make_ecg()
    signal[:750, 0] = np.nan

    assessment = assess_signal_quality(signal, 500, units=["mV"] * 12)

    assert assessment["quality_score"] == pytest.approx(0.85)
    assert assessment["per_lead_quality"]["I"] == pytest.approx(0.85)
    assert assessment["per_lead_quality"]["II"] == pytest.approx(1.0)
    assert assessment["invalid_samples"] == 750
    assert assessment["invalid_reason"] == "non_finite"


def test_quality_assessment_counts_values_outside_int16_range():
    signal = make_ecg()
    signal[:750, 0] = 40.0

    assessment = assess_signal_quality(signal, 500, units=["mV"] * 12)

    assert assessment["quality_score"] == pytest.approx(0.85)
    assert assessment["per_lead_quality"]["I"] == pytest.approx(0.85)
    assert assessment["invalid_samples"] == 750
    assert assessment["invalid_reason"] == "out_of_range"

