import io
import json

import numpy as np
import pytest

from saam.agents.ingestion import IngestionResult, LEADS
from saam.agents.preparation import prepare_case


CASE_ID = "CASE-12345678-1234-1234-1234-123456789abc"


def make_ingestion(signal):
    return IngestionResult(
        case_id=CASE_ID,
        signal=signal,
        sampling_rate=500.0,
        leads=LEADS,
        units=tuple("mV" for _ in LEADS),
        files={"original.csv": b"test"},
        report_text=None,
        source_format="CSV",
    )


def load_npy(content):
    return np.load(io.BytesIO(content), allow_pickle=False)


def test_valid_ecg_produces_four_processed_files():
    rng = np.random.default_rng(42)
    signal = rng.normal(0, 0.5, size=(5000, 12))

    result = prepare_case(make_ingestion(signal))

    assert result.status == "processed"
    assert set(result.files) == {
        "fir_input.npy",
        "fir_stage.npy",
        "signal.npy",
        "processing_report.json",
    }

    assert load_npy(result.files["fir_input.npy"]).shape == (12, 5000)
    assert load_npy(result.files["fir_stage.npy"]).shape == (12, 1011)

    output = load_npy(result.files["signal.npy"])
    assert output.shape == (12, 1000)
    assert output.dtype == np.float32
    assert np.isfinite(output).all()

    report = json.loads(result.files["processing_report.json"])
    assert report["fir_coef_id"] == result.report["fir_coef_id"]
    assert report["quality_score"] == pytest.approx(1.0)


def test_fifteen_percent_nan_returns_insufficient_quality():
    rng = np.random.default_rng(42)
    signal = rng.normal(0, 0.5, size=(5000, 12))
    signal[:750, 0] = np.nan

    result = prepare_case(make_ingestion(signal))

    assert result.status == "quality_insufficient"
    assert result.quality_score == pytest.approx(0.85)
    assert result.report["quality_min"] == pytest.approx(0.90)
    assert "processing_report.json" in result.files
    assert "signal.npy" not in result.files

    report = json.loads(result.files["processing_report.json"])
    assert report["quality_score"] == pytest.approx(0.85)
    assert report["quality_pass"] is False


def test_remaining_nan_samples_are_rejected_without_replacement():
    rng = np.random.default_rng(42)
    signal = rng.normal(0, 0.5, size=(5000, 12))
    signal[0, 0] = np.nan

    result = prepare_case(make_ingestion(signal))

    assert result.status == "rejected"
    assert "signal.npy" not in result.files


def test_invalid_signal_shape_is_rejected():
    result = prepare_case(make_ingestion(np.ones((5000, 11))))

    assert result.status == "rejected"
    assert "signal.npy" not in result.files


def test_wrong_units_are_rejected():
    ingestion = make_ingestion(np.ones((5000, 12)))

    invalid_ingestion = IngestionResult(
        case_id=ingestion.case_id,
        signal=ingestion.signal,
        sampling_rate=ingestion.sampling_rate,
        leads=ingestion.leads,
        units=tuple("uV" for _ in LEADS),
        files=ingestion.files,
        report_text=None,
        source_format="CSV",
    )

    result = prepare_case(invalid_ingestion)

    assert result.status == "rejected"
    assert "signal.npy" not in result.files
