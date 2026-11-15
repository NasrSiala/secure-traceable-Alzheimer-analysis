from pathlib import Path
import uuid

import numpy as np
import pandas as pd
import pytest
import wfdb

from saam.agents.ingestion import ingest_ecg, sanitize_report


CASE_ID = f"CASE-{uuid.uuid4()}"


def create_csv(path: Path, samples: int = 1000) -> Path:
    data = np.random.default_rng(42).normal(
        size=(samples, 12)
    )
    frame = pd.DataFrame(
        data,
        columns=[
            "I", "II", "III", "AVR", "AVL", "AVF",
            "V1", "V2", "V3", "V4", "V5", "V6",
        ],
    )
    frame.to_csv(path, index=False)
    return path


def create_wfdb_record(directory: Path) -> Path:
    signal = np.random.default_rng(42).normal(
        size=(1000, 12)
    )

    record_name = "patient_private_record"

    wfdb.wrsamp(
        record_name=record_name,
        fs=500,
        units=["mV"] * 12,
        sig_name=[
            "I", "II", "III", "AVR", "AVL", "AVF",
            "V1", "V2", "V3", "V4", "V5", "V6",
        ],
        p_signal=signal,
        fmt=["16"] * 12,
        write_dir=str(directory),
    )

    return directory / f"{record_name}.hea"


def test_csv_ingestion_returns_12_leads(tmp_path):
    csv_path = create_csv(tmp_path / "ecg.csv")

    result = ingest_ecg(
        csv_path,
        CASE_ID,
        csv_sampling_rate=500,
    )

    assert result.source_format == "CSV"
    assert result.signal.shape == (1000, 12)
    assert result.sampling_rate == 500
    assert len(result.leads) == 12
    assert result.leads[0] == "I"
    assert result.leads[-1] == "V6"
    assert len(result.files) == 1


def test_csv_output_contains_only_ecg_leads(tmp_path):
    csv_path = create_csv(tmp_path / "ecg.csv")

    result = ingest_ecg(
        csv_path,
        CASE_ID,
        csv_sampling_rate=500,
    )

    content = next(iter(result.files.values())).decode("utf-8")
    header = content.splitlines()[0]

    assert header == "I,II,III,AVR,AVL,AVF,V1,V2,V3,V4,V5,V6"
    assert "patient" not in content.lower()


def test_wfdb_ingestion_removes_original_record_name(tmp_path):
    header_path = create_wfdb_record(tmp_path)

    result = ingest_ecg(header_path, CASE_ID)

    assert result.source_format == "WFDB"
    assert result.signal.shape == (1000, 12)
    assert result.sampling_rate == 500

    sanitized_header = next(
        content.decode("ascii")
        for name, content in result.files.items()
        if name.endswith(".hea")
    )

    assert "patient_private_record" not in sanitized_header
    assert "#" not in sanitized_header
    assert CASE_ID.lower().replace("-", "_") in sanitized_header


def test_wfdb_output_contains_data_file(tmp_path):
    header_path = create_wfdb_record(tmp_path)

    result = ingest_ecg(header_path, CASE_ID)

    assert any(name.endswith(".hea") for name in result.files)
    assert any(name.endswith(".dat") for name in result.files)


def test_report_removes_labeled_personal_information():
    report = (
        "Patient Name: John Smith\n"
        "Date of birth: 1980-04-12\n"
        "Patient ID: PATIENT-123\n"
        "Conclusion: Normal ECG."
    )

    sanitized = sanitize_report(report)

    assert "John Smith" not in sanitized
    assert "1980-04-12" not in sanitized
    assert "PATIENT-123" not in sanitized
    assert "[ANONYMISÉ]" in sanitized
    assert "Normal ECG" in sanitized


def test_csv_requires_sampling_rate(tmp_path):
    csv_path = create_csv(tmp_path / "ecg.csv")

    with pytest.raises(ValueError, match="csv_sampling_rate"):
        ingest_ecg(csv_path, CASE_ID)


def test_invalid_case_id_is_rejected(tmp_path):
    csv_path = create_csv(tmp_path / "ecg.csv")

    with pytest.raises(ValueError, match="case_id"):
        ingest_ecg(
            csv_path,
            "INVALID-ID",
            csv_sampling_rate=500,
        )


def test_csv_with_wrong_number_of_leads_is_rejected(tmp_path):
    frame = pd.DataFrame({
        "I": [0.1, 0.2],
        "II": [0.3, 0.4],
    })
    csv_path = tmp_path / "invalid.csv"
    frame.to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="12 standard leads"):
        ingest_ecg(csv_path, CASE_ID, csv_sampling_rate=500)


def test_csv_with_non_finite_values_is_rejected(tmp_path):
    data = np.ones((10, 12))
    data[0, 0] = np.nan

    csv_path = tmp_path / "invalid.csv"
    pd.DataFrame(
        data,
        columns=[
            "I", "II", "III", "AVR", "AVL", "AVF",
            "V1", "V2", "V3", "V4", "V5", "V6",
        ],
    ).to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="non-finite"):
        ingest_ecg(csv_path, CASE_ID, csv_sampling_rate=500)


def test_unsupported_file_format_is_rejected(tmp_path):
    unsupported = tmp_path / "ecg.txt"
    unsupported.write_text("not an ECG")

    with pytest.raises(ValueError, match="Unsupported format"):
        ingest_ecg(unsupported, CASE_ID)
