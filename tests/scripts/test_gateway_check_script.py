"""Contract tests for fabric/gateway-check.sh. They start neither Fabric nor Docker.

The script is sourced and `npm` / `docker` are replaced by shell functions, so both
branches (host Node and the `spike` container) run for real. AUD-077: the check compiles
first, so it never runs a `dist/` older than the sources.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest
from gateway_run_support import BashRun, CheckScript

SCRIPT = CheckScript("fabric/gateway-check.sh", "check:gateway")
FAKE_NPM = SCRIPT.fake_npm
FAKE_DOCKER = SCRIPT.fake_docker
HOST = SCRIPT.host
CONTAINER = SCRIPT.container


def _run(
    bash_run: BashRun,
    tmp_path: Path,
    setup: str,
    *,
    build: int = 0,
    check: int = 0,
    env: dict[str, str] | None = None,
) -> tuple[CompletedProcess[str], list[str]]:
    return SCRIPT.run(bash_run, tmp_path, setup, build=build, check=check, env=env)


def test_sourcing_the_script_runs_nothing(bash_run: BashRun) -> None:
    result = bash_run(
        ["-c", "source fabric/gateway-check.sh; echo sourced"], timeout=60
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
    assert "run check:gateway" in calls[1]


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


def test_the_container_is_handed_the_scenario_variable(
    bash_run: BashRun, tmp_path: Path
) -> None:
    """A variable only reaches the container when `-e NAME` names it on the docker command."""
    result, calls = _run(bash_run, tmp_path, CONTAINER)
    assert result.returncode == 0, result.stderr
    assert " -e GATEWAY_SCENARIO " in calls[1]
    assert " -e GATEWAY_SCENARIO " in calls[0]


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_the_scenario_reaches_the_check(
    bash_run: BashRun, tmp_path: Path, setup: str
) -> None:
    default, default_calls = _run(bash_run, tmp_path, setup)
    assert default.returncode == 0, default.stderr
    assert default_calls[1].endswith("scenario=flow")

    other_dir = tmp_path / "down"
    other_dir.mkdir()
    down, down_calls = _run(
        bash_run, other_dir, setup, env={"GATEWAY_SCENARIO": "down"}
    )
    assert down.returncode == 0, down.stderr
    assert down_calls[1].endswith("scenario=down")


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
