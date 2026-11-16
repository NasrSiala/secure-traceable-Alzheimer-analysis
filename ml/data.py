"""PTB-XL v1.0.3 download, integrity, split, and vector checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import requests
import wfdb

# Support the documented direct invocation, ``python ml/data.py``.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ai_data.ptbxl.dataset import DEFAULT_DATASET_ROOT, PTBXLDataLoader
from ai_data.ptbxl.diagnostics import summarize_diagnostics
from ai_data.ptbxl.integrity import PTBXLIntegrityChecker
from saam.hashing import file_hash

DATASET_VERSION = "1.0.3"
PHYSIONET_BASE_URL = f"https://physionet.org/files/ptb-xl/{DATASET_VERSION}"
VECTOR_RECORDS = {
    9: "00009_hr",
    38: "00038_hr",
    40: "00040_hr",
    57: "00057_hr",
    59: "00059_hr",
}
METADATA_FILES = ("ptbxl_database.csv", "scp_statements.csv", "SHA256SUMS.txt")
DEFAULT_VECTOR_ROOT = REPOSITORY_ROOT / "hw" / "vectors" / "ptbxl"


def default_dataset_root() -> Path:
    return Path(os.environ.get("PTBXL_ROOT", DEFAULT_DATASET_ROOT))


def _download_file(url: str, destination: Path) -> None:
    """Download one public file atomically without replacing existing data."""
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
        suffix=".part", delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        with requests.get(url, stream=True, timeout=(20, 120)) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    temporary.write(chunk)
        temporary.flush()
        os.fsync(temporary.fileno())
        if destination.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing file: {destination}"
            )
    temporary_path.replace(destination)


def download_dataset(root: str | Path) -> Path:
    """Download PTB-XL metadata and 500 Hz WFDB records into an empty folder.

    Existing files are never replaced. The dataset's official checksum
    manifest is downloaded before record files and used by the check commands.
    """
    target = Path(root).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        if not all((target / name).is_file() for name in METADATA_FILES):
            raise FileExistsError(
                f"Dataset destination is non-empty and incomplete: {target}"
            )
        if (target / "records500" / "00000" / "00001_hr.hea").is_file():
            return target
    target.mkdir(parents=True, exist_ok=True)

    for filename in METADATA_FILES:
        destination = target / filename
        if not destination.is_file():
            _download_file(f"{PHYSIONET_BASE_URL}/{filename}", destination)

    # Resolve the official high-resolution record list from metadata so that
    # the download does not also fetch the separate 100 Hz archive.
    metadata = PTBXLDataLoader(target).load_metadata()
    records = metadata["filename_hr"].astype(str).tolist()
    wfdb.dl_database(
        db_dir=f"ptb-xl/{DATASET_VERSION}",
        dl_dir=str(target),
        records=records,
        annotators=None,
        keep_subdirs=True,
        overwrite=False,
    )
    if not (target / "records500" / "00000" / "00001_hr.hea").is_file():
        raise FileNotFoundError("PTB-XL 500 Hz records did not download correctly.")
    return target


def _load_dataset(root: str | Path | None) -> tuple[
    PTBXLDataLoader, dict[str, Any]
]:
    loader = PTBXLDataLoader(root or default_dataset_root())
    metadata = loader.load_metadata()
    statements = loader.load_statements()
    splits = loader.get_split()
    summary = summarize_diagnostics(metadata, statements, splits)

    return loader, {
        "dataset": "PTB-XL",
        "version": DATASET_VERSION,
        "records": len(metadata),
        "sampling_rate_hz": 500,
        "fold_sizes": {name: len(rows) for name, rows in splits.items()},
        "diagnostic_class_counts": {
            split_name: {
                row["diagnostic_class"]: int(row["class_count"])
                for _, row in summary[summary["split"] == split_name].iterrows()
            }
            for split_name in ("train", "validation", "test")
        },
    }


def _record_checksum_paths(metadata) -> list[Path]:
    """Return the official high-resolution header/data files for all records."""
    paths = {
        Path(str(stem)).with_suffix(extension)
        for stem in metadata["filename_hr"].astype(str)
        for extension in (".hea", ".dat")
    }
    return sorted(paths)


def check_dataset(root: str | Path | None = None) -> dict[str, Any]:
    """Verify metadata checksums, labels, official folds, and split isolation."""
    loader, summary = _load_dataset(root)
    checker = PTBXLIntegrityChecker(loader.root)
    checks = checker.verify_files(METADATA_FILES[:2])
    invalid = [entry["file"] for entry in checks if not entry["valid"]]
    if invalid:
        raise ValueError(f"PTB-XL metadata checksum mismatch: {invalid}")
    record_paths = _record_checksum_paths(loader.metadata)
    record_checks = checker.verify_files(record_paths)
    invalid_records = [
        entry["file"] for entry in record_checks if not entry["valid"]
    ]
    if invalid_records:
        raise ValueError(
            f"PTB-XL records500 checksum mismatch: {invalid_records[:10]}"
        )
    summary["metadata_checksums"] = {entry["file"]: entry["actual"] for entry in checks}
    summary["metadata_integrity"] = "valid"
    summary["records500_files_checked"] = len(record_checks)
    summary["records500_integrity"] = "valid"
    return summary


def check_hw_vectors(
    root: str | Path | None = None,
    vector_root: str | Path = DEFAULT_VECTOR_ROOT,
) -> dict[str, Any]:
    """Check five fold-10 vectors against the source checksums and WFDB data."""
    loader, _ = _load_dataset(root)
    metadata = loader.metadata
    assert metadata is not None
    checker = PTBXLIntegrityChecker(loader.root)
    vectors_path = Path(vector_root)
    verified: list[dict[str, Any]] = []

    for ecg_id, record_name in VECTOR_RECORDS.items():
        if ecg_id not in metadata.index:
            raise ValueError(f"Required vector ECG ID {ecg_id} is absent.")
        row = metadata.loc[ecg_id]
        if int(row["strat_fold"]) != 10:
            raise ValueError(f"Vector ECG ID {ecg_id} is not in fold 10.")

        source_stem = Path(str(row["filename_hr"]))
        if source_stem.name != record_name:
            raise ValueError(
                f"Unexpected source record for ECG ID {ecg_id}: {source_stem.name}"
            )

        vector_stem = vectors_path / "records500" / "00000" / record_name
        for extension in (".hea", ".dat"):
            source_relative = source_stem.with_suffix(extension)
            source_check = checker.verify_file(source_relative)
            if not source_check["valid"]:
                raise ValueError(
                    f"Official checksum mismatch for {source_check['file']}"
                )

            source_bytes = (loader.root / source_relative).read_bytes()
            vector_file = vector_stem.with_suffix(extension)
            if not vector_file.is_file():
                raise FileNotFoundError(vector_file)
            if file_hash(source_bytes) != file_hash(vector_file.read_bytes()):
                raise ValueError(f"Hardware vector differs from source: {vector_file}")

        record = wfdb.rdrecord(str(vector_stem))
        if record.fs != 500 or record.p_signal is None:
            raise ValueError(f"Invalid 500 Hz WFDB vector: {record_name}")
        if record.p_signal.shape != (5000, 12):
            raise ValueError(f"Unexpected WFDB signal shape: {record_name}")
        if not np.isfinite(record.p_signal).all():
            raise ValueError(f"Non-finite samples in WFDB vector: {record_name}")
        if tuple(str(lead).upper() for lead in record.sig_name) != (
            "I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2",
            "V3", "V4", "V5", "V6",
        ):
            raise ValueError(f"Unexpected lead order in vector: {record_name}")
        if len(record.units) != 12 or any(
            str(unit).lower() != "mv" for unit in record.units
        ):
            raise ValueError(f"Unexpected units in vector: {record_name}")

        verified.append({"ecg_id": ecg_id, "record": record_name, "status": "valid"})

    return {
        "dataset": "PTB-XL",
        "version": DATASET_VERSION,
        "fold": 10,
        "vectors": verified,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="PTB-XL v1.0.3 dataset folder")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="check metadata and folds")
    action.add_argument(
        "--check-hw-vectors", action="store_true",
        help="verify the five public fold-10 hardware vectors",
    )
    action.add_argument(
        "--download", action="store_true",
        help="download PTB-XL v1.0.3 to --root or PTBXL_ROOT",
    )
    try:
        args = parser.parse_args(argv)
        root = args.root or default_dataset_root()
        if args.download:
            download_dataset(root)
            result = check_dataset(root)
        elif args.check_hw_vectors:
            result = check_hw_vectors(root)
        else:
            result = check_dataset(root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, requests.RequestException) as exc:
        print(f"PTB-XL check failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
