"""Tests for PTB-XL checksum manifest validation."""

from pathlib import Path

import pytest

from ai_data.ptbxl.integrity import PTBXLIntegrityChecker
from saam.hashing import file_hash


def _checker(tmp_path: Path, manifest: str) -> PTBXLIntegrityChecker:
    (tmp_path / "SHA256SUMS.txt").write_text(manifest, encoding="utf-8")
    return PTBXLIntegrityChecker(tmp_path)


def test_verifies_file_and_rejects_paths_outside_dataset(tmp_path: Path) -> None:
    payload = tmp_path / "record.dat"
    payload.write_bytes(b"public ECG payload")
    checker = _checker(tmp_path, f"{file_hash(payload.read_bytes())}  record.dat\n")

    assert checker.verify_file("record.dat")["valid"] is True
    with pytest.raises(ValueError, match="inside"):
        checker.verify_file("../record.dat")
    with pytest.raises(ValueError, match="inside"):
        checker.verify_file(payload)


@pytest.mark.parametrize(
    "manifest",
    [
        "not-a-checksum-entry\n",
        f"{'z' * 64}  record.dat\n",
        f"{'a' * 64}  record.dat\n{'b' * 64}  record.dat\n",
    ],
)
def test_rejects_malformed_or_ambiguous_manifest(
    tmp_path: Path, manifest: str
) -> None:
    with pytest.raises(ValueError):
        _checker(tmp_path, manifest)


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-record.dat"
    outside.write_bytes(b"outside")
    payload_hash = file_hash(outside.read_bytes())
    checker = _checker(tmp_path, f"{payload_hash}  linked.dat\n")
    link = tmp_path / "linked.dat"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable on this platform.")

    with pytest.raises(ValueError, match="inside"):
        checker.verify_file("linked.dat")
