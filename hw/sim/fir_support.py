"""Shared FIR vectors for the cocotb bench and the xsim vector file.

The oracle is saam.dsp.fir_fixed.filter_decimate. Twenty int16 signals, each
5055 samples (the pipeline length: 5000 plus 55), seed 0x46495231. Input index
0, 5, 10, ... is an output, so each signal produces 1011 samples.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saam.dsp.fir_fixed import coef_id, filter_decimate

SEED = 0x46495231
SIGNAL_COUNT = 20
INPUT_LENGTH = 5055
OUTPUT_LENGTH = 1011
VECTOR_FILE = Path(__file__).resolve().parent / "vectors" / "fir_decim_random.txt"


def signals(seed: int = SEED) -> list[list[int]]:
    rng = random.Random(seed)
    return [
        [rng.randrange(-32768, 32768) for _ in range(INPUT_LENGTH)]
        for _ in range(SIGNAL_COUNT)
    ]


def vector_lines() -> list[str]:
    lines = [
        "# fir decimator vectors",
        f"# seed=0x{SEED:08x} signals={SIGNAL_COUNT} inputs={INPUT_LENGTH}",
        f"# coef_id={coef_id()}",
        str(SIGNAL_COUNT),
        str(INPUT_LENGTH),
        coef_id(),
    ]
    for samples in signals():
        outputs = filter_decimate(samples)
        if len(outputs) != OUTPUT_LENGTH:
            raise RuntimeError(f"expected {OUTPUT_LENGTH} outputs, got {len(outputs)}")
        produced = 0
        for index, sample in enumerate(samples):
            lines.append(str(sample))
            if index % 5 == 0:
                lines.append(str(outputs[produced]))
                produced += 1
        if produced != OUTPUT_LENGTH:
            raise RuntimeError(f"wrote {produced} outputs")
    return lines


def write_vectors(path: Path = VECTOR_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(vector_lines()) + "\n").encode("ascii"))
