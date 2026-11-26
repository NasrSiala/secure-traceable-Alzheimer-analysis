"""Contrat IF-05/ADR-04 : octets JCS et vecteurs communs aux deux OS."""

import copy
import json
from decimal import Decimal

import pytest

from saam.hashing import (
    artifact_hash,
    canonical_json,
    canonical_manifest,
    canonical_text,
    file_hash,
)


@pytest.fixture
def manifest() -> dict:
    return {
        "artifact_id": "00000000-0000-4000-8000-000000000001",
        "case_id": "00000000-0000-4000-8000-000000000002",
        "type": "prediction",
        "parent_artifact_id": "00000000-0000-4000-8000-000000000003",
        "created_at": "2026-11-24T12:00:00Z",
        "software_version": "0.1.0",
        "model_version": "1.0.0",
        "metadata": {"probability": 0.123456789, "nested": [True, None, -0.0]},
        "files": [
            {
                "name": "z.txt",
                "media_type": "text/plain",
                "size": 3,
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            },
            {
                "name": "a.json",
                "media_type": "application/json",
                "size": 2,
                "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            },
        ],
    }


def test_manifest_golden_bytes_and_hash_100_times(manifest: dict) -> None:
    expected = (
        b'{"artifact_id":"00000000-0000-4000-8000-000000000001",'
        b'"case_id":"00000000-0000-4000-8000-000000000002",'
        b'"created_at":"2026-11-24T12:00:00Z","files":['
        b'{"media_type":"application/json","name":"a.json",'
        b'"sha256":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","size":2},'
        b'{"media_type":"text/plain","name":"z.txt",'
        b'"sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","size":3}],'
        b'"metadata":{"nested":[true,null,0],"probability":0.123457},'
        b'"model_version":"1.0.0","parent_artifact_id":"00000000-0000-4000-8000-000000000003",'
        b'"software_version":"0.1.0","type":"prediction"}'
    )
    for iteration in range(100):
        candidate = (
            dict(reversed(list(manifest.items()))) if iteration % 2 else manifest
        )
        candidate = copy.deepcopy(candidate)
        if iteration % 3:
            candidate["files"].reverse()
        assert canonical_manifest(candidate) == expected
        # Constant independent of the serializer, shared by Windows/Linux CI.
        assert (
            artifact_hash(candidate)
            == "5080d2d5791a5b37ec2b1d60ca874da6db3201a82f729ee91bab0adfe6383933"
        )


def test_canonicalization_does_not_mutate_the_manifest(manifest: dict) -> None:
    before = copy.deepcopy(manifest)
    canonical_manifest(manifest)
    assert manifest == before


@pytest.mark.parametrize(
    "field",
    [
        "artifact_id",
        "case_id",
        "type",
        "created_at",
        "software_version",
        "model_version",
        "parent_artifact_id",
        "metadata",
        "files",
    ],
)
def test_every_manifest_field_contributes_to_the_hash(
    manifest: dict, field: str
) -> None:
    changed = copy.deepcopy(manifest)
    if field == "metadata":
        changed[field]["probability"] = 0.2
    elif field == "files":
        changed[field][0]["sha256"] = "0" * 64
    elif field == "type":
        changed[field] = "validation"
    else:
        changed[field] += "-changed"
    assert artifact_hash(changed) != artifact_hash(manifest)


def test_zero_payload_files_and_nullable_versions(manifest: dict) -> None:
    manifest.update(
        type="original", parent_artifact_id=None, model_version=None, files=[]
    )
    decoded = json.loads(canonical_manifest(manifest))
    assert decoded["files"] == []
    assert decoded["parent_artifact_id"] is None
    assert decoded["model_version"] is None


def test_recursive_rounding_preserves_array_order_and_boolean_types() -> None:
    assert canonical_json(
        {"z": [1.23456789, {"v": -1.23456789}], "a": [True, False, None]}
    ) == (b'{"a":[true,false,null],"z":[1.234568,{"v":-1.234568}]}')
    assert canonical_json([1, 2]) != canonical_json([2, 1])


def test_ecmascript_numbers_and_rounding_boundaries() -> None:
    assert canonical_json([1.0, -0.0, 0.0000004, 0.0000006, 1e20, 1e21]) == (
        b"[1,0,0,0.000001,100000000000000000000,1e+21]"
    )
    assert canonical_json([0.1234561]) == canonical_json([0.1234562])
    assert canonical_json([0.1234564]) != canonical_json([0.1234566])


def test_jcs_uses_utf16_key_order_and_preserves_unicode() -> None:
    # Python codepoint sorting places U+E000 before U+1F600; JCS does the reverse.
    assert canonical_json({"\ue000": "é", "😀": "e\u0301", "\r": "\n"}) == (
        '{"\\r":"\\n","😀":"e\u0301","\ue000":"é"}'.encode("utf-8")
    )
    assert canonical_json("é") != canonical_json("e\u0301")


def test_text_is_utf8_nfc_without_changing_line_endings() -> None:
    assert canonical_text("e\u0301\r\n") == "é\r\n".encode()
    assert file_hash(canonical_text("e\u0301")) == file_hash(canonical_text("é"))


@pytest.mark.parametrize(
    "data,digest",
    [
        (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        (
            b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
        ),
    ],
)
def test_file_hash_fips_vectors(data: bytes, digest: str) -> None:
    assert file_hash(data) == digest


def test_file_hash_covers_exact_bytes() -> None:
    assert file_hash(b"\x00\xff\r\n") != file_hash(b"\x00\xff\n")


@pytest.mark.parametrize(
    "bad",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        2**53,
        -(2**53),
        b"abc",
        {"bad": Decimal("0.1")},
        {1: "a"},
        {"x": {1}},
        "\ud800",
        {"\ud800": "x"},
        (1, 2),
        object(),
    ],
)
def test_non_json_or_non_jcs_values_raise_value_error(bad: object) -> None:
    with pytest.raises(ValueError):
        canonical_json(bad)


def test_cycles_raise_value_error() -> None:
    cyclic: list = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError):
        canonical_json(cyclic)


@pytest.mark.parametrize(
    "bad_files",
    [None, {}, [1], [{"name": "x"}], [{"name": 1}], [{"name": "x"}, {"name": "x"}]],
)
def test_invalid_file_lists_raise_value_error(
    manifest: dict, bad_files: object
) -> None:
    manifest["files"] = bad_files
    with pytest.raises(ValueError):
        canonical_manifest(manifest)


def test_invalid_manifest_and_text_inputs_raise_value_error() -> None:
    for bad in [None, [], {}, {"files": []}]:
        with pytest.raises(ValueError):
            canonical_manifest(bad)
    with pytest.raises(ValueError):
        canonical_text("\ud800")
    with pytest.raises(ValueError):
        file_hash("abc")


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "../report.txt"),
        ("name", ""),
        ("name", "a" * 101),
        ("name", 1),
        ("size", -1),
        ("size", True),
        ("size", 1.0),
        ("sha256", "A" * 64),
        ("sha256", "0" * 63),
        ("sha256", None),
        ("media_type", ""),
        ("media_type", None),
    ],
)
def test_invalid_file_metadata(manifest: dict, field: str, value: object) -> None:
    manifest["files"][0][field] = value
    with pytest.raises(ValueError):
        canonical_manifest(manifest)


def test_duplicate_names_with_valid_metadata_are_rejected(manifest: dict) -> None:
    manifest["files"][1]["name"] = manifest["files"][0]["name"]
    with pytest.raises(ValueError):
        canonical_manifest(manifest)


def test_repeated_references_are_not_cycles() -> None:
    shared = [0.123456789]
    assert canonical_json([shared, shared]) == b"[[0.123457],[0.123457]]"


def test_non_mapping_metadata_is_rejected(manifest: dict) -> None:
    manifest["metadata"] = []
    with pytest.raises(ValueError):
        canonical_manifest(manifest)
