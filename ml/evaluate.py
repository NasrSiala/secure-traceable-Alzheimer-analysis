"""Evaluate the saved PTB-XL CNN once on the untouched official fold 10."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ai_data.ptbxl.dataset import DEFAULT_DATASET_ROOT, PTBXLDataLoader
from ml.model import ECGResNet1D
from ml.train import DEFAULT_WEIGHTS, SUPERCLASSES, prepare_fold_cache
from saam.hashing import file_hash

DEFAULT_CACHE = REPOSITORY_ROOT / "ml" / "cache" / "ptbxl-prepared-fold10-v1"
DEFAULT_CARD = REPOSITORY_ROOT / "ml" / "artifacts" / "model_card.json"


def binary_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Compute ROC AUC with average ranks for ties (Mann–Whitney form)."""
    labels = np.asarray(labels, dtype=np.bool_)
    scores = np.asarray(scores, dtype=np.float64)
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("ROC AUC requires positive and negative examples")
    _, inverse, counts = np.unique(scores, return_inverse=True, return_counts=True)
    cumulative = np.cumsum(counts)
    average_ranks = cumulative[inverse] - (counts[inverse] - 1) / 2
    rank_sum = float(average_ranks[labels].sum())
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def classification_metrics(
    labels: np.ndarray, probabilities: np.ndarray, threshold: float = 0.5,
) -> dict[str, object]:
    truth = np.asarray(labels, dtype=np.int8)
    scores = np.asarray(probabilities, dtype=np.float64)
    if truth.shape != scores.shape or truth.ndim != 2:
        raise ValueError("labels and probabilities must have the same 2D shape")
    aucs: dict[str, float] = {}
    f1s: dict[str, float] = {}
    predictions = scores >= threshold
    for index, name in enumerate(SUPERCLASSES[: truth.shape[1]]):
        aucs[name] = binary_auc(truth[:, index], scores[:, index])
        tp = int(np.count_nonzero(predictions[:, index] & (truth[:, index] == 1)))
        fp = int(np.count_nonzero(predictions[:, index] & (truth[:, index] == 0)))
        fn = int(np.count_nonzero(~predictions[:, index] & (truth[:, index] == 1)))
        denominator = 2 * tp + fp + fn
        f1s[name] = (2 * tp / denominator) if denominator else 0.0
    return {
        "auc_by_class": aucs,
        "auc_macro": float(np.mean(list(aucs.values()))),
        "f1_by_class": f1s,
        "f1_macro": float(np.mean(list(f1s.values()))),
        "threshold": threshold,
    }


def evaluate(
    *, dataset_root: Path, weights_path: Path = DEFAULT_WEIGHTS,
    cache_dir: Path = DEFAULT_CACHE, card_path: Path = DEFAULT_CARD,
    fold: int = 10, workers: int = 4, batch_size: int = 64,
) -> dict[str, object]:
    if fold != 10:
        raise ValueError("T3.8b evaluation is fixed to official fold 10")
    checkpoint = torch.load(weights_path, map_location="cpu", weights_only=True)
    if checkpoint["config"]["class_names"] != list(SUPERCLASSES):
        raise ValueError("Model superclass order does not match PTB-XL")
    loader = PTBXLDataLoader(dataset_root)
    signals, labels, fold_sizes = prepare_fold_cache(
        loader, cache_dir, (fold,), workers=workers
    )
    ids = np.load(cache_dir / "ecg_ids.npy", allow_pickle=False)
    metadata = loader.metadata
    assert metadata is not None
    if not np.all(metadata.loc[ids, "strat_fold"].to_numpy() == fold):
        raise ValueError("Evaluation cache contains records outside fold 10")
    data = TensorDataset(
        torch.from_numpy(np.asarray(signals[:len(ids)]).copy()),
        torch.from_numpy(np.asarray(labels).copy()),
    )
    model = ECGResNet1D()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    probabilities: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    with torch.inference_mode():
        for values, batch_labels in DataLoader(data, batch_size=batch_size):
            probabilities.append(torch.sigmoid(model(values)).numpy())
            targets.append(batch_labels.numpy())
    y_score = np.concatenate(probabilities)
    y_true = np.concatenate(targets)
    metrics = classification_metrics(y_true, y_score)
    exclusions = json.loads(
        (cache_dir / "excluded_ecg_ids.json").read_text(encoding="utf-8")
    )
    result: dict[str, object] = {
        "model": "ecg-cnn1d",
        "version": "1.0.0",
        "architecture": checkpoint["config"]["architecture"],
        "weights_sha256": file_hash(weights_path.read_bytes()),
        "dataset": "PTB-XL",
        "dataset_version": "1.0.3",
        "fold": fold,
        "examples_evaluated": len(ids),
        "excluded_records": exclusions,
        "fold_sizes": fold_sizes,
        "class_names": list(SUPERCLASSES),
        "metrics": metrics,
        "training_reproducibility": checkpoint.get("reproducibility", {}),
        "target_auc_macro": 0.85,
        "target_met": metrics["auc_macro"] >= 0.85,
        "training_config": checkpoint["config"],
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "torch": str(torch.__version__),
        },
    }
    card_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = card_path.with_name(f".{card_path.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(card_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--model-card", type=Path, default=DEFAULT_CARD)
    parser.add_argument("--fold", type=int, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        evaluate(
            dataset_root=args.root, weights_path=args.weights, cache_dir=args.cache,
            card_path=args.model_card, fold=args.fold, workers=args.workers,
            batch_size=args.batch_size,
        )
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Model evaluation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
