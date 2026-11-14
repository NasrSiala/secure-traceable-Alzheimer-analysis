"""PTB-XL dataset loading utilities."""

import ast
import os
from pathlib import Path

import pandas as pd
import wfdb


DEFAULT_DATASET_ROOT = (
    r"C:\Users\ayedi\Datasets\PTB-XL"
    r"\ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
)


class PTBXLDataLoader:
    """Load PTB-XL metadata, official splits and ECG records."""

    def __init__(self, dataset_root=None):
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

        self.metadata = None
        self.statements = None

    def load_metadata(self):
        """Load and validate the PTB-XL metadata."""
        metadata = pd.read_csv(self.metadata_path, index_col="ecg_id")

        required = {"patient_id", "strat_fold", "filename_hr", "scp_codes"}
        missing = required.difference(metadata.columns)

        if missing:
            raise ValueError(
                f"Missing metadata columns: {sorted(missing)}"
            )

        metadata["strat_fold"] = pd.to_numeric(
            metadata["strat_fold"], errors="raise"
        ).astype(int)

        if not metadata["strat_fold"].between(1, 10).all():
            raise ValueError("PTB-XL folds must be between 1 and 10.")

        metadata["scp_codes"] = metadata["scp_codes"].apply(
            lambda value: ast.literal_eval(value)
            if isinstance(value, str)
            else value
        )

        self.metadata = metadata
        return metadata

    def load_statements(self):
        """Load diagnostic statement metadata."""
        statements = pd.read_csv(self.statements_path, index_col=0)
        self.statements = statements
        return statements

    def get_split(self):
        """Return patient-disjoint official train, validation and test splits."""
        if self.metadata is None:
            self.load_metadata()

        train = self.metadata[
            self.metadata["strat_fold"].between(1, 8)
        ].copy()

        validation = self.metadata[
            self.metadata["strat_fold"] == 9
        ].copy()

        test = self.metadata[
            self.metadata["strat_fold"] == 10
        ].copy()

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

        if ecg_id not in self.metadata.index:
            raise KeyError(f"Unknown ECG ID: {ecg_id}")

        row = self.metadata.loc[ecg_id]

        if sampling_rate == 500:
            filename = row["filename_hr"]
        elif sampling_rate == 100:
            filename = row["filename_lr"]
        else:
            raise ValueError("Supported sampling rates are 100 Hz and 500 Hz.")

        record_path = self.root / filename
        record = wfdb.rdrecord(str(record_path))

        if record.fs != sampling_rate:
            raise ValueError(
                f"Expected {sampling_rate} Hz, got {record.fs} Hz."
            )

        return {
            "ecg_id": int(ecg_id),
            "signal": record.p_signal,
            "sampling_rate": record.fs,
            "leads": record.sig_name,
            "units": record.units,
            "metadata": row,
        }
