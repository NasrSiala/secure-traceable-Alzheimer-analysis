"""Isolated scale-by-two FIR experiment; production contracts stay untouched."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import wfdb
from scipy.signal import butter, lfilter, sosfiltfilt

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_data.ptbxl.dataset import DEFAULT_DATASET_ROOT, PTBXLDataLoader
from ml.data import check_hw_vectors
from saam.dsp.fir_fixed import (
    DECIMATION,
    INT16_MAX,
    INT16_MIN,
    OUTPUT_SAMPLES,
    TAIL_PADDING,
    fir_fixed_point_multilead,
)
from saam.dsp.prepare import (
    ALIGNMENT_SAMPLES,
    HIGH_PASS_HZ,
    HIGH_PASS_ORDER,
    OUTPUT_FS,
    prepare_ecg,
)

SCALE = 2
SEED = 20261116
OFFICIAL_VECTOR_RECORDS = {
    9: "00009_hr",
    38: "00038_hr",
    40: "00040_hr",
    57: "00057_hr",
    59: "00059_hr",
}
DEFAULT_OUTPUT = ROOT / ".cache" / "fir-scale-x2-experiment-20261116.json"


def double_int16_input(samples: np.ndarray) -> tuple[np.ndarray, int]:
    """Scale integer inputs without wrapping; return int64 values and clips."""
    values = np.asarray(samples)
    if not np.issubdtype(values.dtype, np.integer):
        raise TypeError("FIR scale experiment requires integer samples")
    wide = values.astype(np.int64) * SCALE
    clip_count = int(np.count_nonzero((wide < INT16_MIN) | (wide > INT16_MAX)))
    if clip_count:
        raise OverflowError(
            f"Scale x{SCALE} would clip {clip_count} int16 input samples"
        )
    return wide, clip_count


def _rsb(reference: np.ndarray, fixed: np.ndarray) -> dict[str, float]:
    reference64 = np.asarray(reference, dtype=np.float64)
    error = reference64 - np.asarray(fixed, dtype=np.float64)
    signal_power = float(np.sum(reference64 * reference64, dtype=np.float64))
    error_power = float(np.sum(error * error, dtype=np.float64))
    if signal_power == 0.0 or error_power == 0.0:
        raise ValueError("RSB is undefined for zero signal or zero error")
    return {
        "rsb_db": float(10.0 * np.log10(signal_power / error_power)),
        "signal_power": signal_power,
        "error_power": error_power,
        "reference_rms": float(np.sqrt(np.mean(reference64 * reference64))),
        "error_rms": float(np.sqrt(np.mean(error * error))),
        "error_max_abs": float(np.max(np.abs(error))),
    }


def _float_reference(
    samples: np.ndarray, coefficients_q15: np.ndarray
) -> np.ndarray:
    """Float64 causal FIR with the same Q1.15 coefficients and decimation."""
    coefficients = np.asarray(coefficients_q15, dtype=np.float64) / 32768.0
    padded = np.pad(
        np.asarray(samples, dtype=np.float64),
        ((0, 0), (0, TAIL_PADDING)),
    )
    output = np.stack(
        [lfilter(coefficients, [1.0], lead)[::DECIMATION] for lead in padded]
    )
    if output.shape != (12, OUTPUT_SAMPLES):
        raise RuntimeError(f"Unexpected float reference shape: {output.shape}")
    return output


def _postprocess_compensated(aligned: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply production high-pass/z-score after restoring the base scale."""
    sos = butter(
        HIGH_PASS_ORDER,
        HIGH_PASS_HZ,
        btype="highpass",
        fs=OUTPUT_FS,
        output="sos",
    )
    filtered = sosfiltfilt(sos, aligned.astype(np.float64), axis=1)
    standard_deviations = filtered.std(axis=1, keepdims=True)
    if np.any(standard_deviations == 0.0):
        raise ValueError("Scale-compensated lead has zero standard deviation")
    normalized = (filtered - filtered.mean(axis=1, keepdims=True)) / standard_deviations
    return filtered.astype(np.float32), normalized.astype(np.float32)


def _select_expanded_ids(loader: PTBXLDataLoader) -> list[int]:
    """Select five deterministic records from each official fold."""
    metadata = loader.load_metadata()
    generator = np.random.default_rng(SEED)
    selected: set[int] = set(OFFICIAL_VECTOR_RECORDS)
    for fold in range(1, 11):
        fold_ids = metadata.index[metadata["strat_fold"] == fold].to_numpy()
        if len(fold_ids) < 5:
            raise ValueError(f"Fold {fold} has fewer than five records")
        selected.update(
            int(ecg_id)
            for ecg_id in generator.choice(fold_ids, size=5, replace=False)
        )
    return sorted(selected)


def _analyze_record(
    loader: PTBXLDataLoader,
    ecg_id: int,
    coefficients_q15: np.ndarray,
    vector_root: Path | None = None,
) -> dict[str, Any]:
    if vector_root is None:
        source = loader.load_ecg(ecg_id, sampling_rate=500)
    else:
        record_name = OFFICIAL_VECTOR_RECORDS[ecg_id]
        vector_path = vector_root / "records500" / "00000" / record_name
        vector = wfdb.rdrecord(str(vector_path))
        metadata = loader.metadata
        if metadata is None:
            raise RuntimeError("PTB-XL metadata must be loaded first")
        source = {
            "signal": vector.p_signal,
            "sampling_rate": vector.fs,
            "units": vector.units,
            "leads": vector.sig_name,
            "metadata": metadata.loc[ecg_id],
        }
    record = prepare_ecg(
        source["signal"],
        source["sampling_rate"],
        units=source["units"],
    )
    base_input = record["fir_input"]
    doubled_wide, input_clips = double_int16_input(base_input)
    doubled_input = doubled_wide.astype(np.int16)

    base_output = record["fir_stage"]
    doubled_output = fir_fixed_point_multilead(doubled_input, coefficients_q15)
    base_reference = _float_reference(base_input, coefficients_q15)
    doubled_reference = _float_reference(doubled_input, coefficients_q15)

    # The FIR stage remains at x2 units; compensation is applied only to a
    # separate float view before the production software high-pass stage.
    compensated_aligned = (
        doubled_output[:, ALIGNMENT_SAMPLES:].astype(np.float64) / SCALE
    )
    filtered_x2, normalized_x2 = _postprocess_compensated(compensated_aligned)
    base_filtered = record["filtered"]
    base_normalized = record["signal"]

    q_abs_sum = int(np.abs(coefficients_q15.astype(np.int64)).sum())
    max_scaled_input = int(np.abs(doubled_wide).max())
    accumulator_bound = max_scaled_input * q_abs_sum
    accumulator_40bit_limit = (1 << 39) - 1
    if accumulator_bound > accumulator_40bit_limit:
        raise OverflowError("Scale x2 exceeds the signed 40-bit FIR bound")

    # Values beyond the rounded int16 interval would be saturated by the
    # fixed contract. Count them independently of the returned saturated data.
    rounded_reference = np.floor(doubled_reference + 0.5)
    output_clips = int(
        np.count_nonzero(
            (rounded_reference < INT16_MIN) | (rounded_reference > INT16_MAX)
        )
    )
    base_rounded_reference = np.floor(base_reference + 0.5)
    lead_metrics = []
    for lead_index, lead_name in enumerate(source["leads"]):
        lead_metrics.append(
            {
                "lead": str(lead_name),
                "base": _rsb(base_reference[lead_index], base_output[lead_index]),
                "scale_x2": _rsb(
                    doubled_reference[lead_index], doubled_output[lead_index]
                ),
            }
        )

    return {
        "ecg_id": ecg_id,
        "fold": int(source["metadata"]["strat_fold"]),
        "status": "prepared",
        "input": {
            "base_max_abs": int(np.abs(base_input.astype(np.int64)).max()),
            "base_rms": float(np.sqrt(np.mean(base_input.astype(np.float64) ** 2))),
            "scaled_max_abs": max_scaled_input,
            "input_clip_count": input_clips,
        },
        "accumulator": {
            "absolute_bound": accumulator_bound,
            "signed_40bit_limit": accumulator_40bit_limit,
            "bound_within_limit": accumulator_bound <= accumulator_40bit_limit,
        },
        "output": {
            "base_max_abs": int(np.abs(base_output.astype(np.int64)).max()),
            "scaled_max_abs": int(np.abs(doubled_output.astype(np.int64)).max()),
            "base_boundary_value_count": int(
                np.count_nonzero(
                    (base_output == INT16_MIN) | (base_output == INT16_MAX)
                )
            ),
            "scaled_boundary_value_count": int(
                np.count_nonzero(
                    (doubled_output == INT16_MIN)
                    | (doubled_output == INT16_MAX)
                )
            ),
            "scaled_output_clip_count": output_clips,
            "base_output_clip_count": int(
                np.count_nonzero(
                    (base_rounded_reference < INT16_MIN)
                    | (base_rounded_reference > INT16_MAX)
                )
            ),
        },
        "rsb": {
            "base": _rsb(base_reference, base_output),
            "scale_x2": _rsb(doubled_reference, doubled_output),
            "scale_x2_aligned": _rsb(
                doubled_reference[:, ALIGNMENT_SAMPLES:],
                doubled_output[:, ALIGNMENT_SAMPLES:],
            ),
            "per_lead": lead_metrics,
        },
        "compensated_downstream": {
            "filtered_max_abs_delta": float(
                np.max(np.abs(filtered_x2 - base_filtered))
            ),
            "filtered_rmse": float(
                np.sqrt(np.mean((filtered_x2 - base_filtered) ** 2))
            ),
            "normalized_max_abs_delta": float(
                np.max(np.abs(normalized_x2 - base_normalized))
            ),
            "normalized_rmse": float(
                np.sqrt(np.mean((normalized_x2 - base_normalized) ** 2))
            ),
        },
        "quality": {
            "base_quality_score": float(record["quality_score"]),
            "base_quality_pass": bool(record["report"]["quality_pass"]),
        },
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [record for record in records if record["status"] == "prepared"]
    if not successful:
        raise ValueError("No records were successfully prepared")

    result: dict[str, Any] = {
        "records_attempted": len(records),
        "records_prepared": len(successful),
        "folds_present": sorted({item["fold"] for item in successful}),
        "record_count_by_fold": {
            str(fold): sum(item["fold"] == fold for item in successful)
            for fold in range(1, 11)
            if any(item["fold"] == fold for item in successful)
        },
    }
    for mode in ("base", "scale_x2", "scale_x2_aligned"):
        rsb_values = [record["rsb"][mode] for record in successful]
        signal_power = sum(item["signal_power"] for item in rsb_values)
        error_power = sum(item["error_power"] for item in rsb_values)
        result[mode] = {
            "rsb_db": float(10.0 * np.log10(signal_power / error_power)),
            "per_record_min_db": min(item["rsb_db"] for item in rsb_values),
            "per_record_max_db": max(item["rsb_db"] for item in rsb_values),
        }
    lead_names = [
        item["lead"] for item in successful[0]["rsb"]["per_lead"]
    ]
    per_lead = {}
    for lead_index, lead_name in enumerate(lead_names):
        per_lead[lead_name] = {}
        for mode in ("base", "scale_x2"):
            lead_results = [
                record["rsb"]["per_lead"][lead_index][mode]
                for record in successful
            ]
            signal_power = sum(item["signal_power"] for item in lead_results)
            error_power = sum(item["error_power"] for item in lead_results)
            per_lead[lead_name][mode] = {
                "rsb_db": float(10.0 * np.log10(signal_power / error_power)),
                "per_record_min_db": min(
                    item["rsb_db"] for item in lead_results
                ),
            }
    result["per_lead_rsb"] = per_lead
    result["minimum_per_lead_scale_x2_rsb_db"] = min(
        values["scale_x2"]["rsb_db"] for values in per_lead.values()
    )

    result["input_clip_count"] = sum(
        item["input"]["input_clip_count"] for item in successful
    )
    result["scaled_output_clip_count"] = sum(
        item["output"]["scaled_output_clip_count"] for item in successful
    )
    result["base_output_clip_count"] = sum(
        item["output"]["base_output_clip_count"] for item in successful
    )
    result["max_accumulator_bound"] = max(
        item["accumulator"]["absolute_bound"] for item in successful
    )
    result["signed_40bit_limit"] = successful[0]["accumulator"]["signed_40bit_limit"]
    result["input_amplitude_extremes"] = {
        "lowest_rms_ecg_id": min(
            successful,
            key=lambda item: item["input"]["base_rms"],
        )["ecg_id"],
        "highest_peak_ecg_id": max(
            successful,
            key=lambda item: item["input"]["base_max_abs"],
        )["ecg_id"],
        "min_base_input_rms": min(
            item["input"]["base_rms"] for item in successful
        ),
        "max_base_input_rms": max(
            item["input"]["base_rms"] for item in successful
        ),
        "max_abs_input_base": max(
            item["input"]["base_max_abs"] for item in successful
        ),
        "max_abs_input_scale_x2": max(
            item["input"]["scaled_max_abs"] for item in successful
        ),
    }
    result["max_compensated_normalized_delta"] = max(
        item["compensated_downstream"]["normalized_max_abs_delta"]
        for item in successful
    )
    result["compensated_downstream"] = {
        "filtered_max_abs_delta": max(
            item["compensated_downstream"]["filtered_max_abs_delta"]
            for item in successful
        ),
        "filtered_rmse_global": float(
            np.sqrt(
                np.mean(
                    [
                        item["compensated_downstream"]["filtered_rmse"] ** 2
                        for item in successful
                    ]
                )
            )
        ),
        "normalized_max_abs_delta": result["max_compensated_normalized_delta"],
        "normalized_rmse_global": float(
            np.sqrt(
                np.mean(
                    [
                        item["compensated_downstream"]["normalized_rmse"] ** 2
                        for item in successful
                    ]
                )
            )
        ),
    }
    result["max_scaled_output_abs"] = max(
        item["output"]["scaled_max_abs"] for item in successful
    )
    return result


def run_experiment(
    dataset_root: Path,
    *,
    expanded_sample: bool = True,
) -> dict[str, Any]:
    loader = PTBXLDataLoader(dataset_root)
    metadata = loader.load_metadata()
    coefficients_path = ROOT / "saam" / "dsp" / "fir_coeffs.json"
    coefficient_data = json.loads(coefficients_path.read_text(encoding="utf-8"))
    coefficients_q15 = np.asarray(
        coefficient_data["coefficients_q15"], dtype=np.int16
    )
    if coefficient_data["fir_coef_id"] != "b6d7a73a":
        raise ValueError("Unexpected coefficient ID; experiment stopped")

    official_ids = sorted(OFFICIAL_VECTOR_RECORDS)
    expanded_ids = _select_expanded_ids(loader) if expanded_sample else official_ids
    groups: dict[str, list[int]] = {"official_fold_10_vectors": official_ids}
    if expanded_sample:
        groups["expanded_deterministic_sample"] = expanded_ids

    report: dict[str, Any] = {
        "experiment": "FIR input/output scale x2, isolated",
        "seed": SEED,
        "scale_factor": SCALE,
        "dataset_version": "1.0.3",
        "coefficients": {
            "fir_coef_id": coefficient_data["fir_coef_id"],
            "num_taps": int(coefficient_data["num_taps"]),
            "q_format": coefficient_data["q_format"],
            "unchanged": True,
        },
        "method": {
            "reference": "float64 causal FIR with same Q1.15 coefficients",
            "formula": "10*log10(sum(reference**2)/sum((reference-fixed)**2))",
            "samples": "all leads and all 1011 FIR outputs; aggregate power ratio",
            "scale_compensation": "divide x2-aligned FIR output by 2 before software high-pass",
            "production_changed": False,
            "caches_or_models_changed": False,
        },
        "groups": {},
        "invalid_input_probes": {},
    }
    vector_root = ROOT / "hw" / "vectors" / "ptbxl"
    report["official_vector_integrity"] = check_hw_vectors(
        dataset_root, vector_root
    )

    for group_name, ids in groups.items():
        records: list[dict[str, Any]] = []
        for ecg_id in ids:
            try:
                records.append(
                    _analyze_record(
                        loader,
                        ecg_id,
                        coefficients_q15,
                        vector_root
                        if group_name == "official_fold_10_vectors"
                        else None,
                    )
                )
            except (OSError, ValueError, TypeError, OverflowError) as exc:
                records.append(
                    {
                        "ecg_id": ecg_id,
                        "fold": int(metadata.loc[ecg_id, "strat_fold"]),
                        "status": "rejected",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
        report["groups"][group_name] = {
            "summary": _summarize(records),
            "records": records,
        }

    # Verify that the production preparation continues to reject invalid
    # inputs; no softened quality or clipping behavior is introduced here.
    invalid = np.zeros((5000, 12), dtype=np.float64)
    invalid[0, 0] = np.nan
    out_of_range = np.zeros((5000, 12), dtype=np.float64)
    out_of_range[0, 0] = 40.0
    probes = {
        "non_finite_nan": invalid,
        "outside_int16_quantization_range": out_of_range,
        "constant_zero_signal": np.zeros((5000, 12), dtype=np.float64),
    }
    for probe_name, signal in probes.items():
        try:
            prepare_ecg(signal, 500, units=["mV"] * 12)
        except (ValueError, TypeError) as exc:
            report["invalid_input_probes"][probe_name] = {
                "status": "rejected",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        else:
            report["invalid_input_probes"][probe_name] = {"status": "accepted"}

    overflow_probe = np.full((12, 5000), 16384, dtype=np.int16)
    try:
        double_int16_input(overflow_probe)
    except OverflowError as exc:
        report["invalid_input_probes"]["scale_x2_int16_boundary"] = {
            "status": "rejected",
            "reason": str(exc),
        }
    else:
        report["invalid_input_probes"]["scale_x2_int16_boundary"] = {
            "status": "accepted",
        }

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--official-only",
        action="store_true",
        help="run only the five official fold-10 hardware vectors",
    )
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite experiment report: {output}")

    report = run_experiment(args.root, expanded_sample=not args.official_only)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    summaries = {}
    for name, details in report["groups"].items():
        summary = dict(details["summary"])
        summary.pop("per_lead_rsb", None)
        summaries[name] = summary
    print(
        json.dumps(
            {
                "report": str(output),
                "groups": summaries,
                "invalid_input_probes": report["invalid_input_probes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
