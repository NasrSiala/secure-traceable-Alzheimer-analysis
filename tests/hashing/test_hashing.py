from __future__ import annotations

import hashlib

import pytest

from saam.hashing import artifact_hash, canonical_manifest, file_hash


def test_canonical_manifest_uses_jcs_rounds_floats_and_sorts_files() -> None:
    manifest = {
        "metadata": {"quality": 0.1234567},
        "files": [
            {"name": "z.npy", "size": 9, "sha256": "b"},
            {"name": "a.npy", "size": 1, "sha256": "a"},
        ],
        "artifact_id": "artifact-1",
    }

    assert canonical_manifest(manifest) == (
        b'{"artifact_id":"artifact-1","files":[{"name":"a.npy","sha256":"a","size":1},'
        b'{"name":"z.npy","sha256":"b","size":9}],"metadata":{"quality":0.123457}}'
    )


def test_canonical_manifest_does_not_mutate_input() -> None:
    manifest = {"metadata": {"quality": 0.1234567}, "files": [{"name": "b"}, {"name": "a"}]}
    original_files = list(manifest["files"])

    canonical_manifest(manifest)

    assert manifest["metadata"]["quality"] == 0.1234567
    assert manifest["files"] == original_files


def test_artifact_hash_is_stable_for_one_hundred_calls() -> None:
    manifest = {"artifact_id": "artifact-1", "metadata": {"score": 0.76543219}}

    hashes = {artifact_hash(manifest) for _ in range(100)}

    assert len(hashes) == 1
    assert next(iter(hashes)) == hashlib.sha256(canonical_manifest(manifest)).hexdigest()


def test_file_hash_covers_exact_bytes() -> None:
    payload = b"signal\x00\xff"

    assert file_hash(payload) == hashlib.sha256(payload).hexdigest()
    assert file_hash(bytearray(payload)) == file_hash(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="finis"):
        canonical_manifest({"metadata": {"value": value}})


def test_manifest_file_entries_require_text_names() -> None:
    with pytest.raises(ValueError, match="nom textuel"):
        canonical_manifest({"files": [{"size": 1}]})


def test_non_json_values_are_reported_as_value_error() -> None:
    with pytest.raises(ValueError, match="canonisé en JCS"):
        canonical_manifest({"metadata": {"value": object()}})


def test_file_hash_rejects_text_instead_of_silently_encoding_it() -> None:
    with pytest.raises(TypeError, match="octets"):
        file_hash("payload")  # type: ignore[arg-type]
