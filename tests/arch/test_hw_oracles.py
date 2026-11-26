"""Les futurs bancs crypto/FIR réutilisent les références logicielles de saam."""

from pathlib import Path

import pytest

from tests.arch.checks import oracle_violations


def test_current_simulation_benches_do_not_duplicate_oracles(repo_root: Path) -> None:
    errors = []
    for path in (repo_root / "hw/sim").glob("test_*.py"):
        errors.extend(oracle_violations(path.read_text(encoding="utf-8"), path.stem))
    assert errors == []


@pytest.mark.parametrize(
    "source",
    [
        "import hashlib; hashlib.sha256(b'x')",
        "from saam.hashing import file_hash",
        "def sha256(data): return data",
    ],
)
def test_sha256_bench_must_call_the_shared_oracle(source: str) -> None:
    assert oracle_violations(source, "test_sha256")


def test_sha256_bench_can_use_an_aliased_shared_oracle() -> None:
    assert (
        oracle_violations(
            "from saam.hashing import file_hash as reference\nreference(b'x')",
            "test_sha256",
        )
        == []
    )


def test_fir_bench_reuses_the_fixed_point_implementation() -> None:
    assert (
        oracle_violations(
            "from saam.dsp import fir_fixed\nfir_fixed.filter_decimate(x)", "test_fir"
        )
        == []
    )
    assert oracle_violations("def filter_decimate(x): return x", "test_fir")
    assert oracle_violations(
        "from saam.dsp import fir_fixed\nimport numpy as np\nfir_fixed.filter_decimate(x)\nnp.convolve(x, h)",
        "test_fir",
    )
