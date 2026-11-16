"""Helpers for the contract tests of the fabric/*-check.sh scripts. They start neither Fabric
nor Docker.

A script is sourced, then `npm` and `docker` are replaced by shell functions that log their
arguments and return the statuses the test asks for. Both branches of `run_gateway_script`
in fabric/lib/gateway-run.sh (host Node, `spike` container) therefore run for real. One copy
of these helpers serves every script (AUD-092); each test file keeps its own tests.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

BashRun = Callable[..., CompletedProcess[str]]

_FAKE_NPM = r"""
npm() {
  printf 'npm %s|scenario=%s\n' "$*" "${GATEWAY_SCENARIO-}" >> "$LOG"
  case "$*" in
    "run build") return "${BUILD_STATUS:-0}" ;;
    "run NPM_SCRIPT") return "${CHECK_STATUS:-0}" ;;
  esac
}
"""

_FAKE_DOCKER = r"""
docker() {
  printf 'docker %s|scenario=%s\n' "$*" "${GATEWAY_SCENARIO-}" >> "$LOG"
  case "$*" in
    *" spike run build") return "${BUILD_STATUS:-0}" ;;
    *" spike run NPM_SCRIPT") return "${CHECK_STATUS:-0}" ;;
  esac
}
"""


class CheckScript:
    """One fabric/<name>.sh script and the npm script of ledger-gateway it runs."""

    def __init__(self, script: str, npm_script: str) -> None:
        self.script = script
        self.fake_npm = _FAKE_NPM.replace("NPM_SCRIPT", npm_script)
        self.fake_docker = _FAKE_DOCKER.replace("NPM_SCRIPT", npm_script)
        # Host Node is usable; the wallet exists.
        self.host = (
            "wallet_present() { return 0; }; host_can_run() { return 0; };"
            + self.fake_npm
        )
        # Host Node is not usable; the runtime of the `spike` service is prepared.
        self.container = (
            "wallet_present() { return 0; }; host_can_run() { return 1; }; "
            "runtime_prepared() { return 0; };" + self.fake_docker
        )

    def run(
        self,
        bash_run: BashRun,
        tmp_path: Path,
        setup: str,
        *,
        build: int = 0,
        check: int = 0,
        env: dict[str, str] | None = None,
    ) -> tuple[CompletedProcess[str], list[str]]:
        """Source the script, apply `setup`, run `main`; return the result and the logged calls."""
        log = tmp_path / "calls.log"
        result = bash_run(
            ["-c", f"source {self.script}; {setup}\nmain"],
            env={
                "LOG": log.as_posix(),
                "BUILD_STATUS": str(build),
                "CHECK_STATUS": str(check),
                **(env or {}),
            },
            timeout=60,
        )
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result, lines
