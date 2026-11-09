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
