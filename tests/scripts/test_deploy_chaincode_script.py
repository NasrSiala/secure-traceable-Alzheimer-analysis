"""Contract tests for fabric/deploy-chaincode.sh. They start neither Fabric nor Docker.

The script is copied into a scratch `fabric/` directory (it finds its files from its own
location), so each case controls what exists under `.runtime`. Every case stops before the
script reaches `docker`.
"""

from __future__ import annotations

import re
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


def test_approval_and_commit_state_one_definition(repo_root: Path) -> None:
    """T2.5b: the definition is the same in `approveformyorg` and in `commit`, whatever number
    it carries. A mismatch makes the commit fail on a network that was approved with another."""
    script = (repo_root / "fabric" / "scripts" / "deploy-chaincode.sh").read_text(
        encoding="utf-8"
    )
    versions = re.findall(r"--version (\S+)", script)
    sequences = re.findall(r"--sequence (\S+)", script)
    assert len(versions) == 2  # approve, commit
    assert len(sequences) == 2
    assert len(set(versions)) == 1
    assert len(set(sequences)) == 1


def test_a_chaincode_with_more_transactions_needs_no_new_definition(
    repo_root: Path,
) -> None:
    """T2.5b: RegisterModel and GetModel join the contract without a new sequence.

    The package is a chaincode-as-a-service connection file: no source, no build output. Its
    identifier, and so the definition the peers approved, does not change when the contract
    does. A running network picks the new code up when enroll-identities.sh recreates the two
    chaincode services; a fresh network commits the definition once.
    """
    enroll = (repo_root / "fabric" / "enroll-identities.sh").read_text(encoding="utf-8")
    packaging = enroll[
        enroll.index("write_chaincode_packages()") : enroll.index(
            "wait_for_chaincode()"
        )
    ]
    assert 'code = tgz([("connection.json", connection)])' in packaging
    assert 'tgz([("code.tar.gz", code), ("metadata.json", metadata)])' in packaging
    for source in ("dist/", "node_modules", "chaincode/provenance", "package.json"):
        assert source not in packaging

    deploying = enroll[
        enroll.index("deploy_chaincode()") : enroll.index("cmd_enroll()")
    ]
    recreated = deploying.index(
        "docker rm -f saam-medtrace-cc-org1 saam-medtrace-cc-org2"
    )
    started = deploying.index("up -d cc-org1 cc-org2")
    assert recreated < started
