from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from saam.agents.ingestion import ingest_ecg
from saam.agents.redaction import sanitize_report


def test_redacts_name_after_professional_title():
    report = "ECG reviewed by Dr. John Smith."
    result = sanitize_report(report)

    assert "John Smith" not in result
    assert "[ANONYMISÉ]" in result


def test_redacts_name_after_patient_introduction():
    report = "Le patient John Smith présente un rythme normal."
    result = sanitize_report(report)

    assert "John Smith" not in result
    assert "rythme normal" in result


def test_redacts_known_name_in_free_text():
    report = "Examination performed for Alice Dupont."
    result = sanitize_report(
        report,
        known_names=["Alice Dupont"],
    )

    assert "Alice Dupont" not in result
    assert "[ANONYMISÉ]" in result


def test_known_names_are_case_insensitive():
    report = "Patient record: ALICE DUPONT."
    result = sanitize_report(
        report,
        known_names=["Alice Dupont"],
    )

    assert "ALICE DUPONT" not in result


def test_preserves_medical_conclusions():
    report = (
        "Conclusion: Sinus Rhythm. "
        "No significant ST elevation. "
        "Normal ventricular function."
    )
    result = sanitize_report(report)

    assert result == report


def test_redacts_identity_fields_and_dates():
    report = (
        "Patient Name: John Smith\n"
        "DOB: 1980-04-12\n"
        "Patient ID: PATIENT-123"
    )
    result = sanitize_report(report)

    assert "John Smith" not in result
    assert "1980-04-12" not in result
    assert "PATIENT-123" not in result


def test_none_report_is_supported():
    assert sanitize_report(None) is None


def test_non_string_report_is_rejected():
    with pytest.raises(TypeError):
        sanitize_report(123)


def test_ingestion_uses_known_names(tmp_path: Path):
    leads = [
        "I", "II", "III", "AVR", "AVL", "AVF",
        "V1", "V2", "V3", "V4", "V5", "V6",
    ]

    csv_path = tmp_path / "ecg.csv"
    pd.DataFrame(
        np.ones((10, 12)),
        columns=leads,
    ).to_csv(csv_path, index=False)

    result = ingest_ecg(
        csv_path,
        "CASE-12345678-1234-1234-1234-123456789012",
        csv_sampling_rate=500,
        report_text="Examination of Alice Dupont.",
        known_names=("Alice Dupont",),
    )

    assert "Alice Dupont" not in result.report_text
    assert "[ANONYMISÉ]" in result.report_text
