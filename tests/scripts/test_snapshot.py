"""T5.7 : aller-retour d'une sauvegarde sur des ressources Docker jetables."""

import io
import json
import subprocess
import tarfile
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import pytest

from scripts.snapshot import (
    FABRIC_VOLUMES,
    RUNTIME,
    STACK_VOLUMES,
    VOLUME_IMAGE,
    docker,
    volume_command,
)


@pytest.fixture
def recovery_stack():
    tag = "saam-recovery-test-" + uuid4().hex[:12]
    containers, volumes = [], []

    def new_stack(suffix):
        stack = f"{tag}-{suffix}-stack"
        fabric = f"{tag}-{suffix}-fabric"
        name = f"{tag}-{suffix}-pg"
        docker(
            [
                "run",
                "-d",
                "--pull=never",
                "--name",
                name,
                "--label",
                f"com.docker.compose.project={stack}",
                "--label",
                "com.docker.compose.service=postgres",
                "--env",
                "POSTGRES_USER=postgres",
                "--env",
                "POSTGRES_DB=trace",
                "--env",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "--tmpfs",
                "/var/lib/postgresql/data:rw",
                VOLUME_IMAGE,
            ],
            capture=True,
        )
        containers.append(name)
        deadline = monotonic() + 30
        while True:
            try:
                assert query(name, "SELECT 1") == "1"
                break
            except subprocess.CalledProcessError:
                if monotonic() >= deadline:
                    raise
                sleep(0.3)
        mapping = {}
        for project, keys in ((stack, STACK_VOLUMES), (fabric, FABRIC_VOLUMES)):
            for key in keys:
                volume = f"{project}-{key}"
                docker(
                    [
                        "volume",
                        "create",
                        "--label",
                        f"com.docker.compose.project={project}",
                        "--label",
                        f"com.docker.compose.volume={key}",
                        volume,
                    ],
                    capture=True,
                )
                volumes.append(volume)
                mapping[key] = volume
        return stack, fabric, name, mapping

    try:
        yield new_stack("from"), new_stack("to")
    finally:
        for name in containers:
            docker(["rm", "-f", name], capture=True)
        for name in volumes:
            docker(["volume", "rm", name], capture=True)


def query(container, sql):
    return docker(
        [
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "trace",
            "-qXAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        capture=True,
    )


def put_marker(volume, marker):
    payload = marker.encode("ascii")
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w") as archive:
        item = tarfile.TarInfo("fixture")
        item.size = len(payload)
        archive.addfile(item, io.BytesIO(payload))
    docker(
        volume_command(volume, "tar", "-xf", "-", "-C", "/snapshot", readonly=False),
        input=tar_bytes.getvalue(),
    )


def run_script(bash_run, script, snapshot, projects, fabric_root, key):
    return bash_run(
        [
            f"scripts/{script}.sh",
            Path(snapshot).as_posix(),
            "--stack-project",
            projects[0],
            "--fabric-project",
            projects[1],
            "--fabric-root",
            Path(fabric_root).as_posix(),
            "--key-file",
            Path(key).as_posix(),
        ],
        timeout=180,
    )


def test_scripts_roundtrip_restore_database_volumes_and_fabric_configuration(
    recovery_stack,
    bash_run,
    tmp_path,
):
    origin, target = recovery_stack
    runtime = tmp_path / "fabric-source"
    for name in RUNTIME:
        directory = runtime / name
        directory.mkdir(parents=True)
        (directory / "fixture").write_text(name, encoding="utf-8")
    key = tmp_path / "key"
    key.write_text("ab" * 32, encoding="ascii")
    wrong_key = tmp_path / "wrong-key"
    wrong_key.write_text("cd" * 32, encoding="ascii")
    query(
        origin[2],
        "CREATE TABLE restored_case (reference text); INSERT INTO restored_case VALUES ('CASE-SYNTHETIC')",
    )
    for name, volume in origin[3].items():
        put_marker(volume, name)
    snapshot = tmp_path / "backup"
    destination = tmp_path / "restored" / "fabric"
    backed_up = run_script(bash_run, "backup", snapshot, origin, runtime, key)
    assert backed_up.returncode == 0, backed_up.stderr
    metadata = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert len(metadata["files"]) == 7 and "ab" * 32 not in str(metadata)

    wrong = run_script(bash_run, "restore", snapshot, target, destination, wrong_key)
    assert wrong.returncode != 0 and "clé" in wrong.stderr
    assert not destination.exists()

    archive = snapshot / "uploads.tar.gz"
    original = archive.read_bytes()
    archive.write_bytes(original + b"invalid")
    corrupted = run_script(bash_run, "restore", snapshot, target, destination, key)
    assert corrupted.returncode != 0 and "altérée" in corrupted.stderr
    assert not destination.exists()
    archive.write_bytes(original)

    start = monotonic()
    restored = run_script(bash_run, "restore", snapshot, target, destination, key)
    assert restored.returncode == 0, (restored.stdout, restored.stderr)
    duration = monotonic() - start
    assert duration < 30 * 60
    print(f"Restauration isolée PostgreSQL et volumes : {duration:.2f} s.")
    assert query(target[2], "SELECT reference FROM restored_case") == "CASE-SYNTHETIC"
    assert query(origin[2], "SELECT reference FROM restored_case") == "CASE-SYNTHETIC"
    for name, volume in target[3].items():
        assert (
            docker(volume_command(volume, "cat", "/snapshot/fixture"), capture=True)
            == name
        )
    for name in RUNTIME:
        assert (destination / name / "fixture").read_text(encoding="utf-8") == name

    repeated = run_script(bash_run, "restore", snapshot, target, destination, key)
    assert repeated.returncode != 0 and "doit être vide" in repeated.stderr
    assert query(target[2], "SELECT count(*) FROM restored_case") == "1"


def test_archive_rejects_links_and_parent_traversal():
    from scripts.snapshot import validate_archive

    for name, filetype in (
        ("../outside", tarfile.REGTYPE),
        ("nested/link", tarfile.SYMTYPE),
    ):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            item = tarfile.TarInfo(name)
            item.type = filetype
            item.linkname = "../outside"
            archive.addfile(item)
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            with pytest.raises(ValueError, match="archive"):
                validate_archive(archive)
