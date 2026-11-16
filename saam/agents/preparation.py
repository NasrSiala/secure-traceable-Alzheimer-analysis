from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Optional

import numpy as np

from saam.agents.ingestion import IngestionResult, LEADS
from saam.dsp.prepare import QUALITY_MIN, prepare_ecg


@dataclass(frozen=True)
class PreparationResult:
    case_id: str
    status: str
    quality_score: Optional[float]
    files: dict[str, bytes]
    report: dict
    error: Optional[str] = None


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
    quality_score: Optional[float],
    report: dict,
    arrays: Optional[dict[str, np.ndarray]] = None,
    error: Optional[str] = None,
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

    base_report = {
        "case_id": ingestion.case_id,
        "source_format": ingestion.source_format,
        "quality_min": quality_min,
    }

    if (
        not isinstance(quality_min, (int, float))
        or not np.isfinite(quality_min)
        or not 0.0 <= quality_min <= 1.0
    ):
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

    try:
        signal = np.asarray(ingestion.signal, dtype=np.float64)

        if signal.ndim != 2 or signal.shape[1] != len(LEADS):
            raise ValueError("ECG must have shape (samples, 12)")

        if tuple(ingestion.leads) != LEADS:
            raise ValueError("Unexpected ECG lead names or order")

        if len(ingestion.units) != len(LEADS) or any(
            str(unit).lower() != "mv" for unit in ingestion.units
        ):
            raise ValueError("All ECG leads must be expressed in mV")

        finite_per_lead = np.isfinite(signal).mean(axis=0)
        quality_score = float(finite_per_lead.min())

        per_lead_quality = {
            lead: float(score)
            for lead, score in zip(LEADS, finite_per_lead)
        }

        quality_report = {
            **base_report,
            "quality_score": quality_score,
            "quality_min": float(quality_min),
            "quality_pass": quality_score >= quality_min,
            "per_lead_quality": per_lead_quality,
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

    except (ValueError, TypeError, OSError) as exc:
        report = {
            **base_report,
            "status": "rejected",
            "quality_pass": False,
            "reason": str(exc),
            "invalid_sample_policy": (
                "No interpolation, clipping, or replacement of "
                "invalid samples."
            ),
        }
        return _result(
            ingestion,
            "rejected",
            None,
            report,
            error=str(exc),
        )
