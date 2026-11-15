import json
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

from saam.dsp.fir_fixed import (
    FS,
    INPUT_SAMPLES,
    OUTPUT_SAMPLES,
    fir_fixed_point_multilead,
)


LEAD_COUNT = 12
DURATION_SECONDS = 10
OUTPUT_FS = 100
ALIGNMENT_SAMPLES = 11
QUALITY_MIN = 0.90
HIGH_PASS_HZ = 0.5
HIGH_PASS_ORDER = 2

INT16_MIN = -32768
INT16_MAX = 32767

COEFFICIENTS_PATH = (
    Path(__file__).resolve().parent / "fir_coeffs.json"
)


def load_fir_coefficients(path=COEFFICIENTS_PATH):
    """Load the generated FIR coefficient set."""
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    required = {
        "sample_rate_hz",
        "num_taps",
        "q_format",
        "decimation_factor",
        "coefficients_q15",
        "fir_coef_id",
    }

    missing = required.difference(data)
    if missing:
        raise ValueError(
            f"Missing FIR coefficient fields: {sorted(missing)}"
        )

    if data["sample_rate_hz"] != FS:
        raise ValueError("FIR sample rate does not match the DSP contract")

    if data["decimation_factor"] != 5:
        raise ValueError("Unexpected FIR decimation factor")

    if data["q_format"] != "Q1.15":
        raise ValueError("FIR coefficients must use Q1.15 format")

    coefficients = np.asarray(
        data["coefficients_q15"],
        dtype=np.int64,
    )

    if len(coefficients) != data["num_taps"]:
        raise ValueError("FIR coefficient count does not match num_taps")

    return coefficients, data["fir_coef_id"]


def _validate_signal(signal_mV, sampling_rate, units):
    signal = np.asarray(signal_mV, dtype=np.float64)

    if signal.ndim != 2 or signal.shape[1] != LEAD_COUNT:
        raise ValueError(
            "signal_mV must have shape (samples, 12)"
        )

    if not isinstance(sampling_rate, (int, float)):
        raise TypeError("sampling_rate must be numeric")

    if not np.isfinite(sampling_rate) or sampling_rate <= 0:
        raise ValueError("sampling_rate must be positive and finite")

    if units is not None:
        units = list(units)
        if len(units) != LEAD_COUNT:
            raise ValueError("units must contain 12 entries")
        if any(str(unit).lower() != "mv" for unit in units):
            raise ValueError("All ECG leads must be expressed in mV")

    if signal.shape[0] / sampling_rate < DURATION_SECONDS:
        raise ValueError("ECG recording must contain at least 10 seconds")

    return signal


def prepare_ecg(
    signal_mV,
    sampling_rate,
    units=None,
    quality_min=QUALITY_MIN,
):
    """
    Prepare a 12-lead ECG according to Architecture §5.3.

    Input:
        signal_mV: float array with shape (samples, 12)
        sampling_rate: source sampling frequency in Hz
        units: optional list of 12 lead units, all 'mV'

    Output dictionary:
        fir_input: int16 [12, 5000]
        fir_stage: int16 [12, 1011]
        aligned: int16 [12, 1000]
        filtered: float32 [12, 1000]
        signal: float32 [12, 1000]
        quality_score: float
        report: processing metadata

    Invalid or saturated samples are rejected. They are never silently
    interpolated or replaced.
    """
    if not 0.0 <= quality_min <= 1.0:
        raise ValueError("quality_min must be between 0 and 1")

    signal = _validate_signal(signal_mV, sampling_rate, units)

    finite_mask = np.isfinite(signal)
    finite_per_lead = finite_mask.mean(axis=0)
    quality_score = float(finite_per_lead.min())

    if quality_score < quality_min:
        raise ValueError(
            f"ECG quality {quality_score:.6f} is below "
            f"the configured threshold {quality_min:.6f} "
            "because of non-finite samples"
        )

    if not finite_mask.all():
        raise ValueError(
            "ECG contains non-finite samples despite meeting the quality "
            f"threshold; quality_score={quality_score:.6f}. "
            "Processing stopped without replacing samples."
        )

    # Resample to 500 Hz when necessary.
    if float(sampling_rate) != FS:
        ratio = Fraction(FS / float(sampling_rate)).limit_denominator(10000)
        signal = resample_poly(
            signal,
            up=ratio.numerator,
            down=ratio.denominator,
            axis=0,
        )

    required_samples = FS * DURATION_SECONDS

    if signal.shape[0] < required_samples:
        raise ValueError(
            "Resampled signal contains fewer than 5000 samples"
        )

    # Keep the first ten seconds.
    signal = signal[:required_samples, :]

    # Convert mV to signed int16 according to the architecture.
    scaled = np.rint(signal * 1000.0)

    valid_mask = (
        np.isfinite(scaled)
        & (scaled >= INT16_MIN)
        & (scaled <= INT16_MAX)
    )

    valid_per_lead = valid_mask.mean(axis=0)
    quality_score = float(valid_per_lead.min())

    if quality_score < quality_min:
        raise ValueError(
            f"ECG quality {quality_score:.6f} is below "
            f"the configured threshold {quality_min:.6f} "
            "because of samples outside the int16 quantization range"
        )

    if not valid_mask.all():
        raise ValueError(
            "ECG contains samples outside the int16 quantization range "
            "despite meeting the quality threshold; "
            f"quality_score={quality_score:.6f}. "
            "Processing stopped without clipping invalid input."
        )

    # Transpose to [12, 5000] and quantize.
    fir_input = scaled.astype(np.int16).T.copy()

    coefficients, fir_coef_id = load_fir_coefficients()

    # Bit-exact FIR oracle shared with the hardware implementation.
    fir_stage = fir_fixed_point_multilead(
        fir_input,
        coefficients,
    )

    if fir_stage.shape != (LEAD_COUNT, OUTPUT_SAMPLES):
        raise RuntimeError("Unexpected FIR output shape")

    # Remove the 11 initial outputs corresponding to group delay.
    aligned = fir_stage[:, ALIGNMENT_SAMPLES:].copy()

    if aligned.shape != (LEAD_COUNT, 1000):
        raise RuntimeError("Unexpected aligned signal shape")

    # Software high-pass stage: Butterworth order 2, 0.5 Hz,
    # zero-phase filtering at 100 Hz.
    sos = butter(
        HIGH_PASS_ORDER,
        HIGH_PASS_HZ,
        btype="highpass",
        fs=OUTPUT_FS,
        output="sos",
    )

    filtered = sosfiltfilt(
        sos,
        aligned.astype(np.float64),
        axis=1,
    )

    # Per-lead z-score.
    means = filtered.mean(axis=1, keepdims=True)
    standard_deviations = filtered.std(axis=1, keepdims=True)

    if np.any(standard_deviations == 0):
        raise ValueError(
            "Cannot z-score a lead with zero standard deviation"
        )

    normalized = (filtered - means) / standard_deviations

    filtered = filtered.astype(np.float32)
    normalized = normalized.astype(np.float32)

    report = {
        "sampling_rate_input_hz": float(sampling_rate),
        "sampling_rate_fir_hz": FS,
        "sampling_rate_output_hz": OUTPUT_FS,
        "duration_seconds": DURATION_SECONDS,
        "lead_count": LEAD_COUNT,
        "input_shape": list(fir_input.shape),
        "fir_stage_shape": list(fir_stage.shape),
        "output_shape": list(normalized.shape),
        "quantization": "int16 = sat(rint(mV * 1000))",
        "fir_coef_id": fir_coef_id,
        "fir_q_format": "Q1.15",
        "fir_num_taps": 111,
        "fir_decimation": 5,
        "alignment_removed_samples": ALIGNMENT_SAMPLES,
        "high_pass": {
            "type": "Butterworth",
            "order": HIGH_PASS_ORDER,
            "cutoff_hz": HIGH_PASS_HZ,
            "zero_phase": True,
        },
        "normalization": "per-lead z-score",
        "quality_score": quality_score,
        "quality_min": quality_min,
        "quality_pass": quality_score >= quality_min,
        "invalid_samples": 0,
        "invalid_sample_policy": (
            "reject below quality_min; otherwise reject any remaining "
            "invalid sample without interpolation or replacement"
        ),
    }

    return {
        "fir_input": fir_input,
        "fir_stage": fir_stage,
        "aligned": aligned,
        "filtered": filtered,
        "signal": normalized,
        "quality_score": quality_score,
        "report": report,
    }
