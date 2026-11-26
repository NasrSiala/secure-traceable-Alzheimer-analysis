"""ADR-05/NFR-04 : vrai AES-GCM, AAD, chemins et écriture atomique."""

import os
from uuid import uuid4

import pytest

from saam.storage import ArtifactStore, DecryptionError


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "artifacts", os.urandom(32))


@pytest.mark.parametrize("data", [b"", b"abc", b"\x00\xff\r\n" * 100])
def test_round_trip_and_ciphertext_format(store, data):
    identifier = str(uuid4())
    relative = store.write(identifier, "signal.npy", data)
    disk = (store.root / relative).read_bytes()
    assert len(disk) == len(data) + 28
    assert disk != data
    assert store.read(identifier, "signal.npy") == data
    assert relative == identifier + "/signal.npy.gcm"


def test_every_write_uses_a_fresh_nonce(store):
    identifier = str(uuid4())
    store.write(identifier, "manifest.json", b"{}")
    first = store.path(identifier, "manifest.json").read_bytes()
    store.write(identifier, "manifest.json", b"{}")
    second = store.path(identifier, "manifest.json").read_bytes()
    assert first[:12] != second[:12]
    assert store.read(identifier, "manifest.json") == b"{}"


@pytest.mark.parametrize("offset", [0, 12, -1])
def test_tampering_nonce_ciphertext_or_tag_fails(store, offset):
    identifier = str(uuid4())
    store.write(identifier, "report.txt", b"public synthetic report")
    path = store.path(identifier, "report.txt")
    damaged = bytearray(path.read_bytes())
    damaged[offset] ^= 1
    path.write_bytes(damaged)
    with pytest.raises(DecryptionError, match="non vérifiable"):
        store.read(identifier, "report.txt")


def test_wrong_key_and_cross_file_or_artifact_substitution_fail(store):
    identifier, other = str(uuid4()), str(uuid4())
    relative = store.write(identifier, "a.txt", b"synthetic")
    disk = (store.root / relative).read_bytes()
    with pytest.raises(DecryptionError):
        ArtifactStore(store.root, os.urandom(32)).read(identifier, "a.txt")
    for aid, name in [(identifier, "b.txt"), (other, "a.txt")]:
        target = store.path(aid, name)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(disk)
        with pytest.raises(DecryptionError):
            store.read(aid, name)


@pytest.mark.parametrize(
    "name", ["../secret", "/tmp/x", "x/y", "x\\y", ".", "..", "x|y", "", "x" * 101]
)
def test_path_injection_is_refused(store, name):
    with pytest.raises(ValueError):
        store.write(str(uuid4()), name, b"x")


def test_symlinks_are_refused(store, tmp_path):
    identifier = str(uuid4())
    store.root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (store.root / identifier).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Création de liens symboliques indisponible sur ce poste")
    with pytest.raises(ValueError):
        store.write(identifier, "x.txt", b"x")
    assert list(outside.iterdir()) == []


def test_failed_replace_preserves_previous_file_and_cleans_temporary(
    store, monkeypatch
):
    identifier = str(uuid4())
    store.write(identifier, "x", b"first")

    def fail(*args):
        raise OSError("synthetic I/O failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        store.write(identifier, "x", b"second")
    assert store.read(identifier, "x") == b"first"
    assert [p.name for p in store.path(identifier, "x").parent.iterdir()] == ["x.gcm"]


@pytest.mark.parametrize("key", [b"", b"x" * 16, b"x" * 31, b"x" * 33])
def test_only_a_256_bit_key_is_accepted(tmp_path, key):
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path, key)


def test_environment_and_docker_secret_file(tmp_path, monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("ARTIFACT_KEY", key.hex())
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.delenv("ARTIFACT_KEY_FILE", raising=False)
    source = ArtifactStore.from_environment()
    identifier = str(uuid4())
    source.write(identifier, "x", b"value")
    secret = tmp_path / "key.txt"
    secret.write_text(key.hex() + "\n")
    monkeypatch.setenv("ARTIFACT_KEY_FILE", str(secret))
    monkeypatch.setenv("ARTIFACT_KEY", "invalid")
    assert ArtifactStore.from_environment().read(identifier, "x") == b"value"


def test_missing_and_truncated_files(store):
    identifier = str(uuid4())
    with pytest.raises(FileNotFoundError):
        store.read(identifier, "x")
    store.write(identifier, "x", b"x")
    store.path(identifier, "x").write_bytes(b"short")
    with pytest.raises(DecryptionError):
        store.read(identifier, "x")
