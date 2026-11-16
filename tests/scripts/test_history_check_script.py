"""Contract tests for fabric/history-check.sh. They start neither Fabric nor Docker.

The script is sourced and `npm` / `docker` are replaced by shell functions, so both branches
(host Node and the `spike` container) run for real. It must compile first, so it never runs a
`dist/` older than the sources, and a failed check must fail the script.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest

BashRun = Callable[..., CompletedProcess[str]]

FAKE_NPM = r"""
npm() {
  printf 'npm %s\n' "$*" >> "$LOG"
  case "$*" in
    "run build") return "${BUILD_STATUS:-0}" ;;
    "run check:history") return "${CHECK_STATUS:-0}" ;;
  esac
}
"""

FAKE_DOCKER = r"""
docker() {
  printf 'docker %s\n' "$*" >> "$LOG"
  case "$*" in
    *" spike run build") return "${BUILD_STATUS:-0}" ;;
    *" spike run check:history") return "${CHECK_STATUS:-0}" ;;
  esac
}
"""

HOST = "wallet_present() { return 0; }; host_can_run() { return 0; };" + FAKE_NPM
CONTAINER = (
    "wallet_present() { return 0; }; host_can_run() { return 1; }; "
    "runtime_prepared() { return 0; };" + FAKE_DOCKER
)


def _run(
    bash_run: BashRun,
    tmp_path: Path,
    setup: str,
    *,
    build: int = 0,
    check: int = 0,
) -> tuple[CompletedProcess[str], list[str]]:
    log = tmp_path / "calls.log"
    result = bash_run(
        ["-c", f"source fabric/history-check.sh; {setup}\nmain"],
        env={
            "LOG": log.as_posix(),
            "BUILD_STATUS": str(build),
            "CHECK_STATUS": str(check),
        },
        timeout=60,
    )
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, lines


def test_sourcing_the_script_runs_nothing(bash_run: BashRun) -> None:
    result = bash_run(
        ["-c", "source fabric/history-check.sh; echo sourced"], timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sourced"


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_it_compiles_before_it_checks(
    bash_run: BashRun, tmp_path: Path, setup: str
) -> None:
    result, calls = _run(bash_run, tmp_path, setup)
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    assert "run build" in calls[0]
    assert "run check:history" in calls[1]


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_a_failed_build_stops_before_the_check(
    bash_run: BashRun, tmp_path: Path, setup: str
) -> None:
    result, calls = _run(bash_run, tmp_path, setup, build=2)
    assert result.returncode == 1
    assert "environment unavailable" in result.stderr
    assert "build failed" in result.stderr
    assert len(calls) == 1 and "run build" in calls[0]


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
@pytest.mark.parametrize("check", [1, 2, 130])
def test_a_failed_check_fails_the_script(
    bash_run: BashRun, tmp_path: Path, setup: str, check: int
) -> None:
    result, calls = _run(bash_run, tmp_path, setup, check=check)
    assert result.returncode != 0
    assert len(calls) == 2


def test_the_container_gets_no_scenario_variable(
    bash_run: BashRun, tmp_path: Path
) -> None:
    """The history check has one scenario: nothing is handed to the container."""
    result, calls = _run(bash_run, tmp_path, CONTAINER)
    assert result.returncode == 0, result.stderr
    assert " -e " not in calls[1]


def test_without_a_wallet_nothing_runs(bash_run: BashRun, tmp_path: Path) -> None:
    result, calls = _run(
        bash_run,
        tmp_path,
        "wallet_present() { return 1; };" + FAKE_NPM + FAKE_DOCKER,
    )
    assert result.returncode == 1
    assert "no wallet" in result.stderr
    assert calls == []


def test_without_usable_node_or_runtime_nothing_runs(
    bash_run: BashRun, tmp_path: Path
) -> None:
    result, calls = _run(
        bash_run,
        tmp_path,
        "wallet_present() { return 0; }; host_can_run() { return 1; }; "
        "runtime_prepared() { return 1; };" + FAKE_NPM + FAKE_DOCKER,
    )
    assert result.returncode == 1
    assert "environment unavailable" in result.stderr
    assert calls == []


def test_the_three_scripts_share_one_dispatch(repo_root: Path) -> None:
    """The host-or-container logic lives in fabric/lib/gateway-run.sh, not in three copies."""
    lib = (repo_root / "fabric" / "lib" / "gateway-run.sh").read_text(encoding="utf-8")
    assert "run_gateway_script()" in lib
    assert "host_can_run()" in lib
    for name in ("gateway-check.sh", "history-check.sh", "spike-latency.sh"):
        script = (repo_root / "fabric" / name).read_text(encoding="utf-8")
        assert "lib/gateway-run.sh" in script, name
        assert "host_can_run()" not in script, name
        assert "wallet_present()" not in script, name
