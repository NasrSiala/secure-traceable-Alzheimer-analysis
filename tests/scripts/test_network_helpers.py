"""Tests of the helper functions of fabric/network.sh (sourced, no Docker needed).

Regression tests for the audit findings AUD-005 (secret file permissions) and
AUD-007 (Python interpreter lookup and port probe diagnostics).
"""

from __future__ import annotations

import os
import re
import socket
import stat
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest

SOURCE = 'source "$NETWORK_SH"'
PASSWORD_KEYS = 9  # 3 CA bootstrap + 2 peers + 2 org admins + orderer + orderer admin


def _env(root: Path, **extra: str) -> dict[str, str]:
    return {"NETWORK_SH": (root / "fabric" / "network.sh").as_posix(), **extra}


def test_check_ports_names_a_missing_interpreter(
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(
        ["-c", f"{SOURCE}; check_ports"],
        env=_env(repo_root, PYTHON="definitely-not-a-python"),
        timeout=60,
    )
    assert result.returncode != 0
    assert "not a working Python 3 interpreter" in result.stderr
    assert "already in use" not in result.stderr


def test_check_ports_reports_a_busy_port(
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        result = bash_run(
            ["-c", f"{SOURCE}; HOST_PORTS=({port}); check_ports"],
            env=_env(repo_root),
            timeout=60,
        )
    assert result.returncode != 0
    assert "already in use" in result.stderr
    assert str(port) in result.stderr


def test_check_ports_accepts_free_ports(
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = bash_run(
        ["-c", f"{SOURCE}; HOST_PORTS=({port}); check_ports"],
        env=_env(repo_root),
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def _write_secrets(
    repo_root: Path,
    workdir: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> Path:
    # Sourcing the script changes into fabric/; $OLDPWD brings us back to workdir,
    # so .runtime/ca.env is created there and never in the real fabric/ tree.
    result = bash_run(
        ["-c", f'{SOURCE}; cd "$OLDPWD"; write_secrets'],
        env=_env(repo_root),
        cwd=workdir,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return workdir / ".runtime" / "ca.env"


def test_write_secrets_produces_a_clean_lf_env_file(
    repo_root: Path,
    tmp_path: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    raw = _write_secrets(repo_root, tmp_path, bash_run).read_bytes()
    assert b"\r" not in raw, (
        "CR characters would end up inside the passwords read by Compose"
    )
    values = dict(line.split("=", 1) for line in raw.decode("utf-8").splitlines())
    assert values["CA_ORG1_USER"] == "admin"
    passwords = [value for key, value in values.items() if key.endswith("PASSWORD")]
    assert len(passwords) == PASSWORD_KEYS
    assert all(re.fullmatch(r"[0-9a-f]{32}", password) for password in passwords)
    assert len(set(passwords)) == PASSWORD_KEYS


@pytest.mark.skipif(
    os.name == "nt", reason="NTFS does not enforce POSIX permission bits"
)
def test_write_secrets_is_owner_only(
    repo_root: Path,
    tmp_path: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    env_file = _write_secrets(repo_root, tmp_path, bash_run)
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


# --- remove_generated: root-owned files left by containers (AUD-046) -------------------


def _remove_generated(
    tmp_path: Path,
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
    *,
    host_can_delete: bool,
    container_works: bool,
    container_deletes: bool = True,
) -> tuple[CompletedProcess[str], Path]:
    """Run remove_generated in a scratch fabric/ directory with rm and compose faked.

    `rm` fails for `organizations` until the fake root container has run (as on Linux,
    where containers leave root-owned files); `compose ... cleaner` records its call.
    """
    fabric = tmp_path / "fabric"
    for name in ("organizations", "channel-artifacts", ".runtime", "wallet"):
        (fabric / name).mkdir(parents=True)
        (fabric / name / "file").write_text("x", encoding="utf-8")
    calls = tmp_path / "calls.txt"
    flag = tmp_path / "root-ran"
    script = "\n".join(
        [
            SOURCE,
            f'cd "{fabric.as_posix()}"',
            "sleep() { :; }",
            "rm() {",
            (
                f'  if [[ "{host_can_delete}" == False && "$*" == *organizations* '
                f'&& ! -e "{flag.as_posix()}" ]]; then return 1; fi'
            ),
            '  command rm "$@"',
            "}",
            "compose() {",
            f'  echo "compose $*" >> "{calls.as_posix()}"',
            f"  {'true' if container_works else 'return 1'}",
            (
                f'  touch "{flag.as_posix()}"; '
                "command rm -rf organizations channel-artifacts .runtime wallet"
                if container_deletes
                else "  true"
            ),
            "}",
            "remove_generated",
            "echo finished",
        ]
    )
    result = bash_run(["-c", script], env=_env(repo_root), timeout=60)
    return result, calls


def test_remove_generated_needs_no_container_when_the_host_can_delete(
    tmp_path: Path,
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result, calls = _remove_generated(
        tmp_path, repo_root, bash_run, host_can_delete=True, container_works=True
    )
    assert result.returncode == 0, result.stderr
    assert not calls.exists()
    assert list((tmp_path / "fabric").iterdir()) == []


def test_remove_generated_falls_back_to_a_root_container(
    tmp_path: Path,
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-046: on Linux, files written by root containers cannot be deleted by the host user."""
    result, calls = _remove_generated(
        tmp_path, repo_root, bash_run, host_can_delete=False, container_works=True
    )
    assert result.returncode == 0, result.stderr
    assert "owned by root" in result.stdout
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert len(recorded) == 1
    assert "--profile tools run" in recorded[0]
    assert "cleaner" in recorded[0]
    for name in ("organizations", "channel-artifacts", ".runtime", "wallet"):
        assert name in recorded[0]
        assert not (tmp_path / "fabric" / name).exists()


def test_remove_generated_reports_a_container_that_fails(
    tmp_path: Path,
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result, _ = _remove_generated(
        tmp_path, repo_root, bash_run, host_can_delete=False, container_works=False
    )
    assert result.returncode != 0
    assert "Could not remove the generated files in a container" in result.stderr
    assert "finished" not in result.stdout


def test_remove_generated_fails_if_a_directory_survives(
    tmp_path: Path,
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result, _ = _remove_generated(
        tmp_path,
        repo_root,
        bash_run,
        host_can_delete=False,
        container_works=True,
        container_deletes=False,
    )
    assert result.returncode != 0
    assert "Could not remove" in result.stderr
    assert "organizations" in result.stderr
