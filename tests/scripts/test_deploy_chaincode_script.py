"""Contract tests for fabric/deploy-chaincode.sh. They start neither Fabric nor Docker.

The script is copied into a scratch `fabric/` directory (it finds its files from its own
location), so each case controls what exists under `.runtime`. Every case stops before the
script reaches `docker`.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

BashRun = Callable[..., CompletedProcess[str]]


def _scratch_fabric(repo_root: Path, tmp_path: Path) -> Path:
    fabric = tmp_path / "fabric"
    fabric.mkdir()
    shutil.copy(repo_root / "fabric" / "deploy-chaincode.sh", fabric)
    return fabric


def _run(bash_run: BashRun, fabric: Path) -> CompletedProcess[str]:
    return bash_run([(fabric / "deploy-chaincode.sh").as_posix()], timeout=60)


def test_without_a_prepared_network_it_says_what_to_run(
    bash_run: BashRun, repo_root: Path, tmp_path: Path
) -> None:
    fabric = _scratch_fabric(repo_root, tmp_path)
    result = _run(bash_run, fabric)
    assert result.returncode == 1
    assert "the medtrace network is not prepared" in result.stderr
    assert "fabric/enroll-identities.sh" in result.stderr


def test_without_chaincode_packages_it_names_the_missing_file(
    bash_run: BashRun, repo_root: Path, tmp_path: Path
) -> None:
    """AUD-060: the peer's own message for a missing package says little."""
    fabric = _scratch_fabric(repo_root, tmp_path)
    (fabric / ".runtime").mkdir()
    (fabric / ".runtime" / "ca.env").write_text("", encoding="utf-8")
    result = _run(bash_run, fabric)
    assert result.returncode == 1
    assert ".runtime/cc/org1.tgz is missing" in result.stderr
    assert "fabric/enroll-identities.sh" in result.stderr


def test_one_missing_package_is_enough_to_stop(
    bash_run: BashRun, repo_root: Path, tmp_path: Path
) -> None:
    fabric = _scratch_fabric(repo_root, tmp_path)
    (fabric / ".runtime" / "cc").mkdir(parents=True)
    (fabric / ".runtime" / "ca.env").write_text("", encoding="utf-8")
    (fabric / ".runtime" / "cc" / "org1.tgz").write_bytes(b"")
    result = _run(bash_run, fabric)
    assert result.returncode == 1
    assert ".runtime/cc/org2.tgz is missing" in result.stderr


def test_enrollment_deploys_through_this_wrapper(repo_root: Path) -> None:
    """One way to call the lifecycle script, so what the Fabric suite runs is what this
    wrapper checks."""
    enroll = (repo_root / "fabric" / "enroll-identities.sh").read_text(encoding="utf-8")
    assert "bash ./deploy-chaincode.sh" in enroll
    assert "/work/scripts/deploy-chaincode.sh" not in enroll
