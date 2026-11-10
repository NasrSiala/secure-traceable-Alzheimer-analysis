"""Contract tests for fabric/spike-latency.sh. They start neither Fabric nor Docker.

The script is sourced and `npm` / `docker` are replaced by shell functions, so both
branches (host Node and the `spike` container) and the exit-code contract run for real.
Contract: 0 = within budget, 2 = measured budget breach, 1 = no baseline.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest

BashRun = Callable[..., CompletedProcess[str]]

# `npm` records how it was called and what the probe would see in its environment.
FAKE_NPM = r"""
npm() {
  printf 'npm %s|batch=%s|policy=%s\n' "$*" "${BATCH_TIMEOUT-}" "${ENDORSEMENT_POLICY-}" >> "$LOG"
  case "$*" in
    "run build") return "${BUILD_STATUS:-0}" ;;
    "run spike:latency") return "${MEASURE_STATUS:-0}" ;;
  esac
}
"""

FAKE_DOCKER = r"""
docker() {
  printf 'docker %s\n' "$*" >> "$LOG"
  case "$*" in
    *" spike run build") return "${BUILD_STATUS:-0}" ;;
    *" spike run spike:latency") return "${MEASURE_STATUS:-0}" ;;
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
    measure: int = 0,
) -> tuple[CompletedProcess[str], list[str]]:
    log = tmp_path / "calls.log"
    result = bash_run(
        ["-c", f"source fabric/spike-latency.sh; {setup}\nmain"],
        env={
            "LOG": log.as_posix(),
            "BUILD_STATUS": str(build),
            "MEASURE_STATUS": str(measure),
        },
        timeout=60,
    )
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, lines


def test_sourcing_the_script_runs_nothing(bash_run: BashRun) -> None:
    result = bash_run(
        ["-c", "source fabric/spike-latency.sh; echo sourced"], timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sourced"


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_a_failed_build_is_no_baseline_not_a_budget_breach(
    bash_run: BashRun, tmp_path: Path, setup: str
) -> None:
    """AUD-048: tsc exits 2 on a type error; the script must not pass that on."""
    result, calls = _run(bash_run, tmp_path, setup, build=2)
    assert result.returncode == 1
    assert "environment unavailable" in result.stderr
    assert "build failed" in result.stderr
    assert len(calls) == 1 and "build" in calls[0]


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
@pytest.mark.parametrize(
    ("measure", "expected"),
    [(0, 0), (2, 2), (1, 1), (3, 1), (125, 1), (130, 1)],
)
def test_measurement_exit_codes_keep_their_meaning(
    bash_run: BashRun, tmp_path: Path, setup: str, measure: int, expected: int
) -> None:
    result, calls = _run(bash_run, tmp_path, setup, measure=measure)
    assert result.returncode == expected, result.stderr
    assert len(calls) == 2
    if expected == 1:
        assert "environment unavailable" in result.stderr
        assert f"exit status {measure}" in result.stderr


def test_host_branch_builds_then_measures_with_the_repository_settings(
    bash_run: BashRun, tmp_path: Path, repo_root: Path
) -> None:
    result, calls = _run(bash_run, tmp_path, HOST)
    assert result.returncode == 0, result.stderr
    assert [call.split("|")[0] for call in calls] == [
        "npm run build",
        "npm run spike:latency",
    ]
    configtx = (repo_root / "fabric/config/configtx.yaml").read_text(encoding="utf-8")
    declared = re.search(r"^\s*BatchTimeout:\s*(\S+)", configtx, re.MULTILINE)
    assert declared is not None
    for call in calls:
        _, batch, policy = call.split("|")
        assert batch == f"batch={declared.group(1)}"
        assert policy.startswith("policy=AND(") and "Org1MSP.peer" in policy
        assert "Org2MSP.peer" in policy and '"' not in policy


def test_container_branch_builds_then_measures_in_the_spike_service(
    bash_run: BashRun, tmp_path: Path
) -> None:
    result, calls = _run(bash_run, tmp_path, CONTAINER)
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    for call, last in zip(calls, ("run build", "run spike:latency"), strict=True):
        assert call.startswith("docker compose --project-name saam-medtrace ")
        assert "--profile spike run -T --rm --no-deps --entrypoint npm" in call
        assert "-e ENDORSEMENT_POLICY -e BATCH_TIMEOUT" in call
        assert call.endswith(f" spike {last}")


def test_without_node_and_without_a_prepared_runtime_there_is_no_baseline(
    bash_run: BashRun, tmp_path: Path
) -> None:
    setup = "wallet_present() { return 0; }; host_can_run() { return 1; }; runtime_prepared() { return 1; };"
    result, calls = _run(bash_run, tmp_path, setup)
    assert result.returncode == 1
    assert "environment unavailable: Node is not usable here" in result.stderr
    assert calls == []


def test_a_missing_wallet_stops_before_anything_runs(
    bash_run: BashRun, tmp_path: Path
) -> None:
    setup = "wallet_present() { return 1; };" + FAKE_NPM
    result, calls = _run(bash_run, tmp_path, setup)
    assert result.returncode == 1
    assert "environment unavailable: no wallet" in result.stderr
    assert calls == []
