"""Contract tests for fabric/gateway-serve.sh. They start neither Fabric nor Docker.

Same method as test_history_check_script.py: the script is sourced and `npm` / `docker` are
replaced by shell functions, so both branches (host Node and the `spike` container) run for
real. The script serves the real gateway (`npm run start`) for tests/integrity; it must compile
first, publish the port on the loopback only, and hand the token file over as a read-only mount,
never as a value on a command line.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest
from gateway_run_support import BashRun, CheckScript

SCRIPT = CheckScript("fabric/gateway-serve.sh", "start")
FAKE_NPM = SCRIPT.fake_npm
FAKE_DOCKER = SCRIPT.fake_docker
HOST = SCRIPT.host
CONTAINER = SCRIPT.container
PORT = "18080"
SECRET = "s3cr3t-token-value"


@pytest.fixture
def tokens(tmp_path: Path) -> Path:
    directory = tmp_path / "tokens"
    directory.mkdir()
    (directory / "tokens.json").write_text(
        f'{{"agent-ingestion": "{SECRET}"}}', encoding="utf-8"
    )
    return directory


def _run(
    bash_run: BashRun,
    tmp_path: Path,
    setup: str,
    tokens: Path | None,
    *,
    port: str = PORT,
    build: int = 0,
    check: int = 0,
) -> tuple[CompletedProcess[str], list[str]]:
    env = {"GATEWAY_SERVE_PORT": port}
    if tokens is not None:
        env["GATEWAY_SERVE_TOKEN_DIR"] = tokens.as_posix()
    return SCRIPT.run(bash_run, tmp_path, setup, build=build, check=check, env=env)


def test_sourcing_the_script_runs_nothing(bash_run: BashRun) -> None:
    result = bash_run(
        ["-c", "source fabric/gateway-serve.sh; echo sourced"], timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sourced"


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_it_compiles_before_it_serves(
    bash_run: BashRun, tmp_path: Path, tokens: Path, setup: str
) -> None:
    result, calls = _run(bash_run, tmp_path, setup, tokens)
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    assert "run build" in calls[0]
    assert "run start" in calls[1]


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_a_failed_build_stops_before_the_server(
    bash_run: BashRun, tmp_path: Path, tokens: Path, setup: str
) -> None:
    result, calls = _run(bash_run, tmp_path, setup, tokens, build=2)
    assert result.returncode == 1
    assert "build failed" in result.stderr
    assert len(calls) == 1 and "run build" in calls[0]


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_a_gateway_that_stops_fails_the_script(
    bash_run: BashRun, tmp_path: Path, tokens: Path, setup: str
) -> None:
    result, _calls = _run(bash_run, tmp_path, setup, tokens, check=3)
    assert result.returncode != 0


def test_the_container_gets_the_port_on_the_loopback_and_a_read_only_token_mount(
    bash_run: BashRun, tmp_path: Path, tokens: Path
) -> None:
    result, calls = _run(bash_run, tmp_path, CONTAINER, tokens)
    assert result.returncode == 0, result.stderr
    serve = calls[1]
    assert f"-p 127.0.0.1:{PORT}:8080" in serve
    assert "--name saam-medtrace-gateway-serve" in serve
    assert f"-v {tokens.as_posix()}:/tokens:ro" in serve
    assert "-e AGENT_TOKEN_FILE=/tokens/tokens.json" in serve
    assert "-e GATEWAY_HOST=0.0.0.0" in serve
    assert "-e GATEWAY_PORT=8080" in serve


@pytest.mark.parametrize("setup", [HOST, CONTAINER], ids=["host", "container"])
def test_a_token_value_never_reaches_a_command_line_or_the_output(
    bash_run: BashRun, tmp_path: Path, tokens: Path, setup: str
) -> None:
    result, calls = _run(bash_run, tmp_path, setup, tokens)
    assert SECRET not in "\n".join(calls)
    assert SECRET not in result.stdout + result.stderr


def test_the_host_branch_hands_the_file_and_the_port_to_node_through_the_environment(
    bash_run: BashRun, tmp_path: Path, tokens: Path
) -> None:
    probe = (
        "wallet_present() { return 0; }; host_can_run() { return 0; };"
        'npm() { printf "npm %s|file=%s|port=%s\n" "$*" "${AGENT_TOKEN_FILE-}" '
        '"${GATEWAY_PORT-}" >> "$LOG"; }'
    )
    result, calls = _run(bash_run, tmp_path, probe, tokens)
    assert result.returncode == 0, result.stderr
    assert calls[1] == f"npm run start|file={tokens.as_posix()}/tokens.json|port={PORT}"


@pytest.mark.parametrize("port", ["", "abc", "80", "1023", "65536", "18080;ls", "-1"])
def test_a_port_outside_the_unprivileged_range_runs_nothing(
    bash_run: BashRun, tmp_path: Path, tokens: Path, port: str
) -> None:
    result, calls = _run(bash_run, tmp_path, HOST, tokens, port=port)
    assert result.returncode == 1
    assert "GATEWAY_SERVE_PORT" in result.stderr
    assert calls == []


def test_without_a_token_directory_nothing_runs(
    bash_run: BashRun, tmp_path: Path
) -> None:
    result, calls = _run(bash_run, tmp_path, HOST, None)
    assert result.returncode == 1
    assert "GATEWAY_SERVE_TOKEN_DIR" in result.stderr
    assert calls == []


def test_without_a_token_file_nothing_runs(bash_run: BashRun, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result, calls = _run(bash_run, tmp_path, HOST, empty)
    assert result.returncode == 1
    assert "tokens.json" in result.stderr
    assert calls == []


def test_without_a_wallet_nothing_runs(
    bash_run: BashRun, tmp_path: Path, tokens: Path
) -> None:
    result, calls = _run(
        bash_run,
        tmp_path,
        "wallet_present() { return 1; };" + FAKE_NPM + FAKE_DOCKER,
        tokens,
    )
    assert result.returncode == 1
    assert "no wallet" in result.stderr
    assert calls == []


def test_it_uses_the_shared_dispatch_and_the_package_script(repo_root: Path) -> None:
    script = (repo_root / "fabric" / "gateway-serve.sh").read_text(encoding="utf-8")
    assert "lib/gateway-run.sh" in script
    assert "host_can_run()" not in script
    assert "wallet_present()" not in script
    package = (repo_root / "ledger-gateway" / "package.json").read_text(
        encoding="utf-8"
    )
    assert '"start": "node dist/server.js"' in package
