"""Process-local PTB-XL preparation worker used by the training cache builder."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ai_data.ptbxl.dataset import PTBXLDataLoader
from saam.dsp.prepare import prepare_ecg

_LOADER: PTBXLDataLoader | None = None


def initialize_worker(dataset_root: str) -> None:
    global _LOADER
    _LOADER = PTBXLDataLoader(Path(dataset_root))
    _LOADER.load_metadata()


def prepare_record(ecg_id: int) -> tuple[np.ndarray | None, str | None]:
    if _LOADER is None:
        raise RuntimeError("PTB-XL preparation worker was not initialized")
    record = _LOADER.load_ecg(ecg_id, sampling_rate=500)
    try:
        prepared = prepare_ecg(
            record["signal"], record["sampling_rate"], units=record["units"]
        )
    except ValueError as exc:
        if str(exc) == "Cannot z-score a lead with zero standard deviation":
            return None, str(exc)
        raise
    return prepared["signal"], None
