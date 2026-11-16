from __future__ import annotations

import io
import json
from dataclasses import dataclass

import numpy as np

from saam.agents.ingestion import LEADS, IngestionResult, validate_case_id
from saam.dsp.prepare import (
    QUALITY_MIN,
    assess_signal_quality,
    prepare_ecg,
)


@dataclass(frozen=True)
class PreparationResult:
    case_id: str
    status: str
    quality_score: float | None
    files: dict[str, bytes]
    report: dict
    error: str | None = None


def _npy_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, array, allow_pickle=False)
    return buffer.getvalue()


def _report_bytes(report: dict) -> bytes:
    return json.dumps(
        report,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _result(
    ingestion: IngestionResult,
    status: str,
    quality_score: float | None,
    report: dict,
    arrays: dict[str, np.ndarray] | None = None,
    error: str | None = None,
) -> PreparationResult:
    files: dict[str, bytes] = {}

    if arrays:
        for filename, array in arrays.items():
            files[filename] = _npy_bytes(array)

    files["processing_report.json"] = _report_bytes(report)

    return PreparationResult(
        case_id=ingestion.case_id,
        status=status,
        quality_score=quality_score,
        files=files,
        report=report,
        error=error,
    )


def prepare_case(
    ingestion: IngestionResult,
    quality_min: float = QUALITY_MIN,
) -> PreparationResult:
    """Prepare an ingested ECG and produce the T3.7 processed artifacts."""

    if not isinstance(ingestion, IngestionResult):
        raise TypeError("ingestion must be an IngestionResult")

    validate_case_id(ingestion.case_id)

    valid_quality_min = (
        isinstance(quality_min, (int, float))
        and np.isfinite(quality_min)
        and 0.0 <= quality_min <= 1.0
    )
    base_report = {
        "case_id": ingestion.case_id,
        "source_format": ingestion.source_format,
        "quality_min": float(quality_min) if valid_quality_min else None,
    }

    if not valid_quality_min:
        report = {
            **base_report,
            "quality_pass": False,
            "status": "rejected",
            "reason": "quality_min must be between 0 and 1",
        }
        return _result(
            ingestion, "rejected", None, report,
            error=report["reason"],
        )

    quality_assessment = None
    try:
        signal = np.asarray(ingestion.signal, dtype=np.float64)

        if tuple(ingestion.leads) != LEADS:
            raise ValueError("Unexpected ECG lead names or order")
        if ingestion.source_format not in {"WFDB", "CSV"}:
            raise ValueError("Unsupported ECG source format")

        quality_assessment = assess_signal_quality(
            signal,
            ingestion.sampling_rate,
            units=ingestion.units,
        )
        quality_score = float(quality_assessment["quality_score"])
        per_lead_quality = quality_assessment["per_lead_quality"]

        quality_report = {
            **base_report,
            "quality_score": quality_score,
            "quality_min": float(quality_min),
            "quality_pass": quality_score >= quality_min,
            "per_lead_quality": per_lead_quality,
            "invalid_samples": quality_assessment["invalid_samples"],
            "invalid_reason": quality_assessment["invalid_reason"],
            "invalid_sample_policy": (
                "No interpolation or replacement; invalid samples "
                "are rejected."
            ),
        }

        if quality_score < quality_min:
            report = {
                **quality_report,
                "status": "quality_insufficient",
                "reason": (
                    f"ECG quality {quality_score:.6f} is below "
                    f"the required threshold {quality_min:.6f}"
                ),
            }
            return _result(
                ingestion,
                "quality_insufficient",
                quality_score,
                report,
                error=report["reason"],
            )

        prepared = prepare_ecg(
            signal,
            ingestion.sampling_rate,
            units=ingestion.units,
            quality_min=float(quality_min),
        )

        report = {
            **prepared["report"],
            "case_id": ingestion.case_id,
            "source_format": ingestion.source_format,
            "per_lead_quality": per_lead_quality,
            "status": "processed",
        }

        arrays = {
            "fir_input.npy": prepared["fir_input"],
            "fir_stage.npy": prepared["fir_stage"],
            "signal.npy": prepared["signal"],
        }

        return _result(
            ingestion,
            "processed",
            float(prepared["quality_score"]),
            report,
            arrays=arrays,
        )

    except (ValueError, TypeError, OSError, OverflowError):
        quality_score = (
            float(quality_assessment["quality_score"])
            if quality_assessment is not None
            else None
        )
        per_lead_quality = (
            quality_assessment["per_lead_quality"]
            if quality_assessment is not None
            else None
        )
        report = {
            **base_report,
            "quality_score": quality_score,
            "per_lead_quality": per_lead_quality,
            "invalid_samples": (
                quality_assessment["invalid_samples"]
                if quality_assessment is not None
                else None
            ),
            "invalid_reason": (
                quality_assessment["invalid_reason"]
                if quality_assessment is not None
                else None
            ),
            "status": "rejected",
            "quality_pass": False,
            "reason": "préparation impossible",
            "error_code": (
                "INVALID_SIGNAL"
                if quality_assessment is not None
                and quality_assessment["invalid_reason"] is not None
                else "PREPARATION_ERROR"
            ),
            "invalid_sample_policy": (
                "No interpolation, clipping, or replacement of "
                "invalid samples."
            ),
        }
        return _result(
            ingestion,
            "rejected",
            quality_score,
            report,
            error=report["reason"],
        )
