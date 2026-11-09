"""The TypeScript check falls back to the pinned Node image when the host has no Node."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from subprocess import CompletedProcess

import pytest

pytestmark = pytest.mark.fabric


@pytest.mark.parametrize("package", ["chaincode/provenance", "ledger-gateway"])
def test_typescript_check_runs_in_the_node_image_without_host_node(
    bash_run: Callable[..., CompletedProcess[str]], package: str
) -> None:
    """AUD-037: with no Node on the host but Docker running, the check still runs.

    The package is mounted read-only and copied aside inside the container, so the
    checkout gains no file and the host's node_modules is not used.
    """
    before = subprocess.run(
        ["git", "status", "--porcelain", "--", package],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    ).stdout
    result = bash_run(
        [
            "-c",
            (
                "source scripts/test-l.sh; node_available() { return 1; }; "
                f"run_npm_test {package}"
            ),
        ],
        timeout=600,
    )
    assert result.returncode == 0, result.stdout[-800:] + result.stderr[-800:]
    assert "running npm test in node:20" in result.stdout
    assert "tsc --noEmit" in result.stdout
    after = subprocess.run(
        ["git", "status", "--porcelain", "--", package],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    ).stdout
    assert after == before


def test_a_type_error_fails_the_check_in_the_node_image(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """Negative control: the container run must turn a TypeScript error into exit != 0."""
    lines = [
        "source scripts/test-l.sh",
        "node_available() { return 1; }",
        "copy=$(mktemp -d)",
        "trap 'rm -rf \"${copy}\"' EXIT",
        "cd ledger-gateway",
        'cp -r package.json package-lock.json tsconfig.json src "${copy}/"',
        "cd ..",
        'echo \'const broken: number = "text";\' >> "${copy}/src/spike-submit.ts"',
        'run_npm_test "${copy}"',
    ]
    result = bash_run(["-c", chr(10).join(lines)], timeout=600)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined[-800:]
    assert "error TS2322" in combined
