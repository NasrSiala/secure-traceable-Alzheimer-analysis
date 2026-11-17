"""Contrats du lanceur matériel : choix d'outil et propagation des erreurs."""

from collections.abc import Callable
from subprocess import CompletedProcess

import pytest


def run(
    bash_run: Callable[..., CompletedProcess[str]], definitions: str
) -> CompletedProcess[str]:
    return bash_run(
        ["-c", "source scripts/test-hw.sh; " + definitions + "; main"], timeout=60
    )


def test_missing_simulator_and_docker_is_an_error(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = run(
        bash_run,
        "host_available() { return 1; }; docker_available() { return 1; }",
    )
    assert result.returncode == 3
    assert "GHDL >= 3" in result.stderr


def test_host_simulation_failure_is_not_hidden(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = run(
        bash_run,
        "host_available() { return 0; }; make() { return 13; }",
    )
    assert result.returncode == 13


@pytest.mark.parametrize("version,expected", [("2.0.0", 1), ("3.0.0", 0)])
def test_host_requires_ghdl_three_or_newer(
    bash_run: Callable[..., CompletedProcess[str]], version: str, expected: int
) -> None:
    result = bash_run(
        [
            "-c",
            "source scripts/test-hw.sh; make() { :; }; "
            f"ghdl() {{ echo 'GHDL {version}'; }}; host_available",
        ],
        timeout=60,
    )
    assert result.returncode == expected


def test_failed_docker_build_prevents_simulation(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = run(
        bash_run,
        "host_available() { return 1; }; docker_available() { return 0; }; "
        'docker() { if [[ "$1" == build ]]; then return 19; fi; echo unexpected-run; }',
    )
    assert result.returncode == 19
    assert "unexpected-run" not in result.stdout


def test_container_simulation_failure_reaches_the_caller(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = run(
        bash_run,
        "host_available() { return 1; }; docker_available() { return 0; }; "
        'docker() { echo "$*"; if [[ "$1" == run ]]; then return 23; fi; }; TEST=smoke',
    )
    assert result.returncode == 23
    assert "build -f hw/sim/Dockerfile" in result.stdout
    assert "run --rm --network none -e TEST=smoke" in result.stdout
    assert "--mount" not in result.stdout and "--publish" not in result.stdout
