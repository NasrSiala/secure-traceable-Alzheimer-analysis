"""Train ADR-08's CPU-capable multi-label ECG ResNet on official folds."""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ai_data.ptbxl.dataset import DEFAULT_DATASET_ROOT, PTBXLDataLoader
from ml._prepare_worker import initialize_worker, prepare_record
from ml.model import ECGResNet1D, parameter_count

SUPERCLASSES = ("NORM", "MI", "STTC", "CD", "HYP")
DEFAULT_CACHE = REPOSITORY_ROOT / "ml" / "cache" / "ptbxl-prepared-v1"
DEFAULT_WEIGHTS = REPOSITORY_ROOT / "ml" / "artifacts" / "ecg-cnn1d-1.0.0.pt"


def set_seed(seed: int) -> None:
    """Set supported CPU RNGs for reproducible data order and initialization."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def _labels(metadata, statements) -> np.ndarray:
    class_for_code = {
        str(code): str(row["diagnostic_class"])
        for code, row in statements.iterrows()
        if row["diagnostic"] == 1 and row["diagnostic_class"] in SUPERCLASSES
    }
    result = np.zeros((len(metadata), len(SUPERCLASSES)), dtype=np.float32)
    class_index = {name: index for index, name in enumerate(SUPERCLASSES)}
    for row_index, codes in enumerate(metadata["scp_codes"]):
        for code in codes:
            superclass = class_for_code.get(code)
            if superclass is not None:
                result[row_index, class_index[superclass]] = 1.0
    return result


def _fold_indices(metadata, ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return train folds 1–8 and validation fold 9, rejecting leakage."""
    if len(np.unique(ids)) != len(ids):
        raise ValueError("Prepared ECG IDs contain duplicates")
    folds = metadata.loc[ids, "strat_fold"].to_numpy()
    if not np.isin(folds, np.arange(1, 10)).all():
        raise ValueError("Training cache contains records outside folds 1–9")
    train_indices = np.flatnonzero(folds <= 8)
    validation_indices = np.flatnonzero(folds == 9)
    train_ids = set(ids[train_indices].tolist())
    validation_ids = set(ids[validation_indices].tolist())
    if train_ids & validation_ids or len(train_ids | validation_ids) != len(ids):
        raise ValueError("Training and validation folds overlap or omit records")
    return train_indices, validation_indices


def prepare_fold_cache(
    loader: PTBXLDataLoader,
    cache_dir: Path,
    folds: tuple[int, ...],
    workers: int = 4,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Prepare selected official folds through production IF-06 preparation."""
    if not folds or any(fold < 1 or fold > 10 for fold in folds):
        raise ValueError("folds must contain official PTB-XL folds 1–10")
    metadata = loader.load_metadata()
    statements = loader.load_statements()
    splits = loader.get_split()
    selected = metadata[metadata["strat_fold"].isin(folds)].sort_index()
    cache_dir.mkdir(parents=True, exist_ok=True)
    signals_path = cache_dir / "signals.npy"
    labels_path = cache_dir / "labels.npy"
    ids_path = cache_dir / "ecg_ids.npy"
    exclusions_path = cache_dir / "excluded_ecg_ids.json"

    if any(path.exists() for path in (signals_path, labels_path, ids_path, exclusions_path)):
        if not all(path.is_file() for path in (signals_path, labels_path, ids_path, exclusions_path)):
            raise FileExistsError(f"Incomplete prepared cache at {cache_dir}")
        signals = np.load(signals_path, mmap_mode="r", allow_pickle=False)
        labels = np.load(labels_path, mmap_mode="r", allow_pickle=False)
        ids = np.load(ids_path, allow_pickle=False)
        excluded = json.loads(exclusions_path.read_text(encoding="utf-8"))
        expected_ids = selected.index.to_numpy(dtype=np.int64)
        expected_valid_ids = np.array(
            [ecg_id for ecg_id in expected_ids if str(int(ecg_id)) not in excluded],
            dtype=np.int64,
        )
        if signals.shape != (len(selected), 12, 1000) or labels.shape != (
            len(ids), len(SUPERCLASSES)
        ) or not np.array_equal(ids, expected_valid_ids):
            raise ValueError(f"Prepared cache does not match current PTB-XL folds: {cache_dir}")
        return signals, labels, {name: len(rows) for name, rows in splits.items()}

    temp_signals = cache_dir / ".signals.npy.incomplete"
    temp_labels = cache_dir / ".labels.incomplete.npy"
    temp_ids = cache_dir / ".ecg_ids.incomplete.npy"
    temp_exclusions = cache_dir / ".excluded_ecg_ids.incomplete.json"
    if any(path.exists() for path in (temp_signals, temp_labels, temp_ids, temp_exclusions)):
        raise FileExistsError(f"Interrupted prepared cache exists at {cache_dir}")

    signals = np.lib.format.open_memmap(
        temp_signals, mode="w+", dtype=np.float32,
        shape=(len(selected), 12, 1000),
    )
    targets = _labels(selected, statements)
    valid_positions: list[int] = []
    excluded: dict[str, str] = {}
    started = time.perf_counter()
    progress_every = 250
    executor = ProcessPoolExecutor(
        max_workers=workers,
        initializer=initialize_worker,
        initargs=(str(loader.root),),
    )
    try:
        record_ids = (int(ecg_id) for ecg_id in selected.index)
        for index, (signal, exclusion_reason) in enumerate(
            executor.map(prepare_record, record_ids, chunksize=8)
        ):
            if signal is None:
                excluded[str(int(selected.index[index]))] = exclusion_reason or "rejected"
            else:
                signals[len(valid_positions)] = signal
                valid_positions.append(index)
            if (index + 1) % progress_every == 0 or index + 1 == len(selected):
                signals.flush()
                print(
                    f"prepared {index + 1}/{len(selected)} records "
                    f"({time.perf_counter() - started:.1f}s)",
                    flush=True,
                )
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    signals.flush()
    del signals
    valid_ids = selected.index.to_numpy(dtype=np.int64)[valid_positions]
    np.save(temp_labels, targets[valid_positions], allow_pickle=False)
    np.save(temp_ids, valid_ids, allow_pickle=False)
    temp_exclusions.write_text(json.dumps(excluded, sort_keys=True), encoding="utf-8")
    # Publish the cache only after its signals, labels, IDs and exclusions are ready.
    temp_signals.replace(signals_path)
    temp_labels.replace(labels_path)
    temp_ids.replace(ids_path)
    temp_exclusions.replace(exclusions_path)
    signals = np.load(signals_path, mmap_mode="r", allow_pickle=False)
    return signals, np.load(labels_path, mmap_mode="r", allow_pickle=False), {
        name: len(rows) for name, rows in splits.items()
    }


def _epoch(
    model: nn.Module,
    loader: DataLoader,
    loss_fn: nn.Module,
    optimizer: torch.optim.Optimizer | None,
) -> float:
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    total_samples = 0
    for values, labels in loader:
        values = values.to(dtype=torch.float32)
        labels = labels.to(dtype=torch.float32)
        if training:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(training):
            logits = model(values)
            loss = loss_fn(logits, labels)
            if training:
                loss.backward()
                optimizer.step()
        total_loss += float(loss.detach()) * len(values)
        total_samples += len(values)
    return total_loss / total_samples


def _loss_on_batch(model: nn.Module, loss_fn: nn.Module, values: torch.Tensor,
                   labels: torch.Tensor) -> float:
    model.eval()
    with torch.inference_mode():
        return float(loss_fn(model(values), labels))


def train(
    *,
    dataset_root: Path,
    cache_dir: Path = DEFAULT_CACHE,
    weights_path: Path = DEFAULT_WEIGHTS,
    epochs: int = 1,
    batch_size: int = 64,
    seed: int = 20261116,
    workers: int = 4,
) -> dict[str, object]:
    if epochs < 1 or batch_size < 1 or workers < 1:
        raise ValueError("epochs, batch_size and workers must be positive")
    if weights_path.exists():
        raise FileExistsError(f"Refusing to overwrite model weights: {weights_path}")
    loader = PTBXLDataLoader(dataset_root)
    signals, labels, fold_sizes = prepare_fold_cache(
        loader, cache_dir, tuple(range(1, 10)), workers=workers
    )
    # Cache construction may start worker processes; reset all RNGs afterward
    # so model initialization and shuffled batch order are independent of it.
    set_seed(seed)
    ids = np.load(cache_dir / "ecg_ids.npy", allow_pickle=False)
    exclusions = json.loads(
        (cache_dir / "excluded_ecg_ids.json").read_text(encoding="utf-8")
    )
    metadata = loader.metadata
    assert metadata is not None
    train_indices, validation_indices = _fold_indices(metadata, ids)
    training_data = TensorDataset(
        torch.from_numpy(np.asarray(signals[train_indices]).copy()),
        torch.from_numpy(np.asarray(labels[train_indices]).copy()),
    )
    validation_data = TensorDataset(
        torch.from_numpy(np.asarray(signals[validation_indices]).copy()),
        torch.from_numpy(np.asarray(labels[validation_indices]).copy()),
    )
    generator = torch.Generator().manual_seed(seed)
    training_loader = DataLoader(
        training_data, batch_size=batch_size, shuffle=True, generator=generator,
    )
    validation_loader = DataLoader(
        validation_data, batch_size=batch_size, shuffle=False,
    )
    model = ECGResNet1D()
    if parameter_count(model) > 600_000:
        raise RuntimeError("CNN exceeds the ADR-08 lightweight parameter budget")
    loss_fn = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    fixed_values = torch.from_numpy(
        np.asarray(signals[train_indices[:batch_size]]).copy()
    )
    fixed_labels = torch.from_numpy(
        np.asarray(labels[train_indices[:batch_size]]).copy()
    )
    fixed_loss_before = _loss_on_batch(model, loss_fn, fixed_values, fixed_labels)
    history = []
    for epoch_index in range(epochs):
        train_loss = _epoch(model, training_loader, loss_fn, optimizer)
        validation_loss = _epoch(model, validation_loader, loss_fn, None)
        fixed_loss_after = _loss_on_batch(model, loss_fn, fixed_values, fixed_labels)
        history.append({
            "epoch": epoch_index + 1,
            "train_bce_loss": train_loss,
            "validation_bce_loss": validation_loss,
            "fixed_batch_train_bce_before": fixed_loss_before,
            "fixed_batch_train_bce_after": fixed_loss_after,
        })
        print(json.dumps(history[-1], sort_keys=True), flush=True)

    weights_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_weights = weights_path.with_name(f".{weights_path.name}.tmp")
    config = {
        "architecture": "lightweight-1d-resnet",
        "model_parameters": parameter_count(model),
        "input_shape": [12, 1000],
        "class_names": list(SUPERCLASSES),
        "optimizer": "Adam",
        "learning_rate": 1e-3,
        "loss": "BCEWithLogitsLoss",
        "batch_size": batch_size,
        "epochs": epochs,
        "seed": seed,
        "deterministic_algorithms": True,
        "train_folds": list(range(1, 9)),
        "validation_fold": 9,
        "dataset": "PTB-XL",
        "dataset_version": "1.0.3",
        "preparation": "saam.dsp.prepare.prepare_ecg",
        "rejected_records": exclusions,
    }
    versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "torch": str(torch.__version__),
    }
    # Verify the actual serialized checkpoint before publishing it.
    probe = torch.from_numpy(np.asarray(signals[validation_indices[:1]]).copy())
    model.eval()
    with torch.inference_mode():
        expected_probe = model(probe)
    torch.save({
        "state_dict": model.state_dict(),
        "config": config,
        "versions": versions,
        "history": history,
        "rejected_record_count": len(exclusions),
    }, temporary_weights)
    reloaded = ECGResNet1D()
    checkpoint = torch.load(temporary_weights, map_location="cpu", weights_only=True)
    reloaded.load_state_dict(checkpoint["state_dict"])
    reloaded.eval()
    with torch.inference_mode():
        actual_probe = reloaded(probe)
    if not torch.equal(expected_probe, actual_probe):
        temporary_weights.unlink()
        raise RuntimeError("Reloaded checkpoint does not reproduce its probe prediction")
    if weights_path.exists():
        temporary_weights.unlink()
        raise FileExistsError(f"Refusing to overwrite model weights: {weights_path}")
    temporary_weights.replace(weights_path)
    config_path = weights_path.with_suffix(".json")
    temporary_config = config_path.with_name(f".{config_path.name}.tmp")
    result: dict[str, object] = {
        "model": "ecg-cnn1d",
        "version": "1.0.0",
        **config,
        "versions": versions,
        "fold_sizes": fold_sizes,
        "training_examples": len(train_indices),
        "validation_examples": len(validation_indices),
        "rejected_record_count": len(exclusions),
        "history": history,
        "weights": str(weights_path),
        "reload_prediction_check": "passed",
    }
    temporary_config.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary_config.replace(config_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="PTB-XL dataset root")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    root = args.root or Path(os.environ.get("PTBXL_ROOT", DEFAULT_DATASET_ROOT))
    try:
        train(
            dataset_root=root,
            cache_dir=args.cache,
            weights_path=args.weights,
            epochs=args.epochs,
            batch_size=args.batch_size,
            seed=args.seed,
            workers=args.workers,
        )
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Model training failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
