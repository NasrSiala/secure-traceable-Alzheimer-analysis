"""PTB-XL dataset loading utilities."""

import ast
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import wfdb

DEFAULT_DATASET_ROOT = (
    r"C:\Users\ayedi\Datasets\PTB-XL"
    r"\ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
)

EXPECTED_LEADS = (
    "I", "II", "III", "AVR", "AVL", "AVF",
    "V1", "V2", "V3", "V4", "V5", "V6",
)


class PTBXLDataLoader:
    """Load PTB-XL metadata, official splits and ECG records."""

    def __init__(self, dataset_root: str | Path | None = None):
        root = dataset_root or os.getenv(
            "PTBXL_ROOT", DEFAULT_DATASET_ROOT
        )
        self.root = Path(root)

        if not self.root.is_dir():
            raise FileNotFoundError(
                f"PTB-XL dataset directory not found: {self.root}"
            )

        self.metadata_path = self.root / "ptbxl_database.csv"
        self.statements_path = self.root / "scp_statements.csv"

        for path in (self.metadata_path, self.statements_path):
            if not path.is_file():
                raise FileNotFoundError(f"Required file not found: {path}")

        self.metadata: pd.DataFrame | None = None
        self.statements: pd.DataFrame | None = None

    def load_metadata(self):
        """Load and validate the PTB-XL metadata."""
        metadata = pd.read_csv(self.metadata_path, index_col="ecg_id")

        required = {
            "patient_id", "strat_fold", "filename_hr", "filename_lr", "scp_codes"
        }
        missing = required.difference(metadata.columns)

        if missing:
            raise ValueError(
                f"Missing metadata columns: {sorted(missing)}"
            )

        if metadata.index.has_duplicates:
            raise ValueError("PTB-XL ECG IDs must be unique.")
        if metadata["patient_id"].isna().any():
            raise ValueError("PTB-XL patient assignments cannot be missing.")

        folds = pd.to_numeric(metadata["strat_fold"], errors="raise")
        if (
            folds.isna().any()
            or not np.isfinite(folds.to_numpy(dtype=np.float64)).all()
            or not (folds == folds.astype(int)).all()
        ):
            raise ValueError("PTB-XL folds must be integers.")
        metadata["strat_fold"] = folds.astype(int)

        if not metadata["strat_fold"].between(1, 10).all():
            raise ValueError("PTB-XL folds must be between 1 and 10.")

        def parse_scp_codes(value: Any) -> dict[str, float]:
            try:
                parsed = ast.literal_eval(value) if isinstance(value, str) else value
            except (SyntaxError, ValueError) as exc:
                raise ValueError("Invalid PTB-XL scp_codes value.") from exc
            if not isinstance(parsed, dict):
                raise TypeError("PTB-XL scp_codes entries must be mappings.")
            normalized: dict[str, float] = {}
            for code, score in parsed.items():
                if not isinstance(code, str):
                    raise TypeError("PTB-XL diagnostic codes must be strings.")
                try:
                    numeric_score = float(score)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid severity for PTB-XL code {code}."
                    ) from exc
                if not math.isfinite(numeric_score):
                    raise ValueError(
                        f"Non-finite severity for PTB-XL code {code}."
                    )
                normalized[code] = numeric_score
            return normalized

        metadata["scp_codes"] = metadata["scp_codes"].apply(parse_scp_codes)

        self.metadata = metadata
        return metadata

    def load_statements(self) -> pd.DataFrame:
        """Load diagnostic statement metadata."""
        statements = pd.read_csv(self.statements_path, index_col=0)
        required = {"diagnostic", "diagnostic_class"}
        missing = required.difference(statements.columns)
        if missing:
            raise ValueError(
                f"Missing statement columns: {sorted(missing)}"
            )
        if statements.index.has_duplicates:
            raise ValueError("PTB-XL statement codes must be unique.")
        self.statements = statements
        return statements

    def get_split(self):
        """Return patient-disjoint official train, validation and test splits."""
        metadata = self.metadata if self.metadata is not None else self.load_metadata()

        train = metadata[metadata["strat_fold"].between(1, 8)].copy()

        validation = metadata[metadata["strat_fold"] == 9].copy()

        test = metadata[metadata["strat_fold"] == 10].copy()

        train_patients = set(train["patient_id"])
        validation_patients = set(validation["patient_id"])
        test_patients = set(test["patient_id"])

        if train_patients & validation_patients:
            raise ValueError("Patient overlap between train and validation.")

        if train_patients & test_patients:
            raise ValueError("Patient overlap between train and test.")

        if validation_patients & test_patients:
            raise ValueError("Patient overlap between validation and test.")

        return {
            "train": train,
            "validation": validation,
            "test": test,
        }

    def load_ecg(self, ecg_id, sampling_rate=500):
        """Load one ECG record and return its signal and metadata."""
        if self.metadata is None:
            self.load_metadata()

        metadata = self.metadata if self.metadata is not None else self.load_metadata()
        if ecg_id not in metadata.index:
            raise KeyError(f"Unknown ECG ID: {ecg_id}")

        row = metadata.loc[ecg_id]

        if sampling_rate == 500:
            filename = row["filename_hr"]
        elif sampling_rate == 100:
            filename = row["filename_lr"]
        else:
            raise ValueError("Supported sampling rates are 100 Hz and 500 Hz.")

        record_path = (self.root / filename).resolve()
        if not record_path.is_relative_to(self.root.resolve()):
            raise ValueError("PTB-XL record path must stay inside the dataset.")
        record = wfdb.rdrecord(str(record_path))

        if record.fs != sampling_rate:
            raise ValueError(
                f"Expected {sampling_rate} Hz, got {record.fs} Hz."
            )

        if record.p_signal is None:
            raise ValueError("PTB-XL record has no physical signal samples.")
        if record.p_signal.ndim != 2 or record.p_signal.shape[1] != 12:
            raise ValueError("PTB-XL record must have exactly 12 leads.")
        if tuple(str(lead).upper() for lead in record.sig_name) != EXPECTED_LEADS:
            raise ValueError("PTB-XL record has unexpected lead names or order.")
        if len(record.units) != 12 or any(
            str(unit).lower() != "mv" for unit in record.units
        ):
            raise ValueError("PTB-XL record signals must use mV units.")
        if not np.isfinite(record.p_signal).all():
            raise ValueError("PTB-XL record contains missing or invalid samples.")

        return {
            "ecg_id": int(ecg_id),
            "signal": record.p_signal,
            "sampling_rate": record.fs,
            "leads": record.sig_name,
            "units": record.units,
            "metadata": row,
        }
