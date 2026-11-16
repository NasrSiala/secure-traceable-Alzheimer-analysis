"""Unit tests for dataset labels and safe public-file downloads."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.data import _download_file, _record_checksum_paths
from ml.train import SUPERCLASSES, _fold_indices, _labels, set_seed


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        yield b"public metadata"


def test_download_writes_complete_file_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ml.data

    monkeypatch.setattr(ml.data.requests, "get", lambda *_a, **_k: _Response())
    destination = tmp_path / "metadata.csv"

    _download_file("https://example.invalid/metadata.csv", destination)
    assert destination.read_bytes() == b"public metadata"
    with pytest.raises(FileExistsError):
        _download_file("https://example.invalid/metadata.csv", destination)


def test_record_checksum_paths_cover_each_high_resolution_pair() -> None:
    metadata = pd.DataFrame(
        {"filename_hr": ["records500/00000/00001_hr", "records500/00000/00002_hr"]}
    )

    paths = _record_checksum_paths(metadata)

    assert [path.as_posix() for path in paths] == [
        "records500/00000/00001_hr.dat",
        "records500/00000/00001_hr.hea",
        "records500/00000/00002_hr.dat",
        "records500/00000/00002_hr.hea",
    ]


def test_superclass_labels_use_only_diagnostic_codes() -> None:
    metadata = pd.DataFrame(
        {"scp_codes": [{"MI_CODE": 100}, {"RHYTHM": 100}, {"NORM_CODE": 50}]}
    )
    statements = pd.DataFrame(
        {
            "diagnostic": [1, 0, 1],
            "diagnostic_class": ["MI", "STTC", "NORM"],
        },
        index=["MI_CODE", "RHYTHM", "NORM_CODE"],
    )

    labels = _labels(metadata, statements)

    assert labels.shape == (3, len(SUPERCLASSES))
    assert labels[0, SUPERCLASSES.index("MI")] == 1
    assert labels[1].sum() == 0
    assert labels[2, SUPERCLASSES.index("NORM")] == 1


def test_fold_indices_keep_fold_9_out_of_training_and_reject_fold_10() -> None:
    metadata = pd.DataFrame({"strat_fold": [1, 8, 9, 10]}, index=[11, 12, 13, 14])

    train, validation = _fold_indices(metadata, np.array([11, 12, 13]))

    assert train.tolist() == [0, 1]
    assert validation.tolist() == [2]
    with pytest.raises(ValueError, match="outside folds 1–9"):
        _fold_indices(metadata, np.array([11, 12, 13, 14]))


def test_seed_reproduces_model_initialization() -> None:
    import torch

    from ml.model import ECGResNet1D

    set_seed(42)
    first = ECGResNet1D().state_dict()
    set_seed(42)
    second = ECGResNet1D().state_dict()

    assert all(torch.equal(first[name], second[name]) for name in first)


def test_preparation_worker_records_flat_lead_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ml._prepare_worker as worker

    class Loader:
        def load_ecg(self, _ecg_id: int, *, sampling_rate: int) -> dict[str, object]:
            assert sampling_rate == 500
            return {"signal": np.zeros((5000, 12)), "sampling_rate": 500,
                    "units": ["mV"] * 12}

    monkeypatch.setattr(worker, "_LOADER", Loader())

    def reject_flat_lead(*_args: object, **_kwargs: object) -> None:
        raise ValueError("Cannot z-score a lead with zero standard deviation")

    monkeypatch.setattr(worker, "prepare_ecg", reject_flat_lead)
    signal, reason = worker.prepare_record(12722)

    assert signal is None
    assert reason == "Cannot z-score a lead with zero standard deviation"


def test_fold10_metrics_compute_auc_with_ties_and_macro_f1() -> None:
    from ml.evaluate import classification_metrics

    labels = np.array([[1, 0, 1, 0, 1], [0, 1, 0, 1, 0], [1, 0, 0, 1, 0]])
    scores = np.array([[0.9, 0.8, 0.5, 0.7, 0.6],
                       [0.2, 0.7, 0.5, 0.3, 0.1],
                       [0.8, 0.1, 0.2, 0.6, 0.2]])

    metrics = classification_metrics(labels, scores)

    assert metrics["auc_by_class"]["NORM"] == 1.0
    assert metrics["auc_by_class"]["STTC"] == 0.75
    assert metrics["auc_by_class"]["CD"] == 0.0
    assert metrics["f1_macro"] == pytest.approx(23 / 30)
