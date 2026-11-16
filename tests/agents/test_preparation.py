import io
import json

import numpy as np
import pandas as pd
import pytest

from saam.agents.ingestion import (
    LEADS,
    IngestionResult,
    ingest_ecg,
    new_case_id,
)
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


def test_out_of_range_samples_above_ten_percent_are_quality_insufficient():
    rng = np.random.default_rng(42)
    signal = rng.normal(0, 0.5, size=(5000, 12))
    signal[:750, 0] = 40.0

    result = prepare_case(make_ingestion(signal))

    assert result.status == "quality_insufficient"
    assert result.quality_score == pytest.approx(0.85)
    assert result.report["per_lead_quality"]["I"] == pytest.approx(0.85)
    assert result.report["invalid_samples"] == 750
    assert result.report["invalid_reason"] == "out_of_range"
    assert "fir_stage.npy" not in result.files


def test_small_invalid_fraction_is_rejected_without_sample_values_in_report():
    rng = np.random.default_rng(42)
    signal = rng.normal(0, 0.5, size=(5000, 12))
    signal[0, 0] = 40.0

    result = prepare_case(make_ingestion(signal))
    report_bytes = result.files["processing_report.json"]

    assert result.status == "rejected"
    assert result.quality_score == pytest.approx(0.9998)
    assert result.report["reason"] == "préparation impossible"
    assert result.report["invalid_reason"] == "out_of_range"
    assert b"40.0" not in report_bytes


def test_invalid_quality_threshold_still_returns_valid_json_report():
    result = prepare_case(make_ingestion(np.ones((5000, 12))), quality_min=float("nan"))

    report = json.loads(result.files["processing_report.json"])

    assert result.status == "rejected"
    assert report["quality_min"] is None
    assert report["reason"] == "quality_min must be between 0 and 1"


def test_ingestion_to_preparation_produces_twelve_lead_processed_artifacts(
    tmp_path,
):
    rng = np.random.default_rng(2026)
    signal = rng.normal(0, 0.4, size=(5000, 12))
    source_path = tmp_path / "patient_private_source.csv"
    pd.DataFrame(signal, columns=LEADS).to_csv(source_path, index=False)
    ingestion = ingest_ecg(
        source_path,
        new_case_id(),
        csv_sampling_rate=500,
        report_text="Patient Name: John Smith",
    )

    result = prepare_case(ingestion)

    assert result.status == "processed"
    assert set(result.files) == {
        "fir_input.npy",
        "fir_stage.npy",
        "signal.npy",
        "processing_report.json",
    }
    fir_input = load_npy(result.files["fir_input.npy"])
    assert np.array_equal(fir_input, np.rint(signal * 1000).astype(np.int16).T)
    report = json.loads(result.files["processing_report.json"])
    assert report["fir_coef_id"] == result.report["fir_coef_id"]
    assert report["quantization"] == "int16 = sat(rint(mV * 1000))"
    assert "John Smith" not in result.files["processing_report.json"].decode("utf-8")
