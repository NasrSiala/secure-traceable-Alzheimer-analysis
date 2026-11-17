"""Lifecycle tests for the isolated medtrace Fabric network."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.fabric

OUR_CONTAINERS = (
    "saam-medtrace-ca-org1",
    "saam-medtrace-ca-org2",
    "saam-medtrace-ca-orderer",
    "saam-medtrace-orderer",
    "saam-medtrace-peer0-org1",
    "saam-medtrace-peer0-org2",
)
OUR_VOLUMES = (
    "saam-medtrace-orderer-ledger",
    "saam-medtrace-peer0-org1-ledger",
    "saam-medtrace-peer0-org2-ledger",
)
PEERS = ("saam-medtrace-peer0-org1", "saam-medtrace-peer0-org2")


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _lines(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _all_container_ids() -> set[str]:
    return _lines(_docker("ps", "-aq", "--no-trunc"))


def _our_container_ids() -> set[str]:
    return _lines(
        _docker("ps", "-aq", "--no-trunc", "--filter", "label=saam.network=medtrace")
    )


def _foreign_container_ids() -> set[str]:
    return _all_container_ids() - _our_container_ids()


def _existing_volumes() -> set[str]:
    return _lines(_docker("volume", "ls", "-q"))


def _our_volumes() -> set[str]:
    return _lines(
        _docker("volume", "ls", "-q", "--filter", "label=saam.network=medtrace")
    )


def _network_names() -> set[str]:
    return _lines(_docker("network", "ls", "--format", "{{.Name}}"))


def _redacted(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if "password" in lowered or "private key" in lowered or "begin " in lowered:
            kept.append("[redacted]")
        else:
            kept.append(line)
    return "\n".join(kept[-40:])


def _assert_ok(result: CompletedProcess[str], step: str) -> None:
    assert result.returncode == 0, (
        f"{step} failed with exit {result.returncode}\n"
        f"{_redacted(result.stdout)}\n{_redacted(result.stderr)}"
    )


def _peer_channels(container: str) -> str:
    result = _docker("exec", container, "peer", "channel", "list")
    assert result.returncode == 0, result.stderr
    return result.stdout


def _orderer_channel_names() -> set[str]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "saam-medtrace",
            "-f",
            "fabric/compose/compose.yaml",
            "--profile",
            "tools",
            "run",
            "-T",
            "--rm",
            "--no-deps",
            "tools",
            "-lc",
            (
                "osnadmin channel list -o orderer.example.com:7053 "
                "--ca-file /work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/ca.crt "
                "--client-cert /work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt "
                "--client-key /work/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key"
            ),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"osnadmin channel list failed with exit {result.returncode}"
    )
    start = result.stdout.find("{")
    assert start >= 0, "osnadmin returned no JSON channel list"
    payload = json.loads(result.stdout[start:])
    channels = payload.get("channels") or []
    return {
        channel["name"]
        for channel in channels
        if isinstance(channel, dict) and isinstance(channel.get("name"), str)
    }


@pytest.fixture(scope="module", autouse=True)
def _preserve_foreign_docker(bash_run: Callable[..., CompletedProcess[str]]) -> object:
    foreign_containers = _foreign_container_ids()
    foreign_networks = _network_names() - {"saam-medtrace"}
    foreign_volumes = _existing_volumes() - _our_volumes()
    yield
    stopped = bash_run(["fabric/network.sh", "stop"], timeout=180)
    assert stopped.returncode == 0, (
        f"cleanup stop failed with exit {stopped.returncode}"
    )
    assert foreign_containers <= _foreign_container_ids()
    assert foreign_networks <= (_network_names() - {"saam-medtrace"})
    assert foreign_volumes <= _existing_volumes()
    assert _our_volumes() == set()


def test_status_is_unhealthy_when_network_is_stopped(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    stopped = bash_run(["fabric/network.sh", "stop"], timeout=180)
    _assert_ok(stopped, "stop")
    status = bash_run(["fabric/network.sh", "status"], timeout=60)
    assert status.returncode != 0
    assert "state: unhealthy" in status.stdout
    assert _our_container_ids() == set()
    assert _our_volumes() == set()


def test_status_on_a_stopped_network_changes_nothing(
    bash_run: Callable[..., CompletedProcess[str]],
    repo_root: Path,
) -> None:
    """AUD-006: a status probe creates neither the Docker network nor host directories."""
    stopped = bash_run(["fabric/network.sh", "stop"], timeout=180)
    _assert_ok(stopped, "stop")
    status = bash_run(["fabric/network.sh", "status"], timeout=60)
    assert status.returncode != 0
    assert "state: unhealthy" in status.stdout
    assert "saam-medtrace" not in _network_names()
    for generated in ("organizations", "channel-artifacts", ".runtime"):
        assert not (repo_root / "fabric" / generated).exists(), generated
    assert _our_container_ids() == set()
    assert _our_volumes() == set()


def test_stop_removes_a_build_container_left_by_an_interrupted_enrollment(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-028: a one-off container from `compose run` carries the ownership label,
    so `stop` removes it instead of failing on "network has active endpoints"."""
    _assert_ok(bash_run(["fabric/network.sh", "stop"], timeout=180), "stop")
    started = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "saam-medtrace",
            "-f",
            "fabric/compose/compose.yaml",
            "--profile",
            "spike",
            "run",
            "-d",
            "-T",
            "--no-deps",
            "gw-build",
            "-lc",
            "sleep 600",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    _assert_ok(started, "start of the one-off build container")
    assert _our_container_ids() != set()
    stopped = bash_run(["fabric/network.sh", "stop"], timeout=180)
    _assert_ok(stopped, "stop with a build container left behind")
    assert _our_container_ids() == set()
    assert "saam-medtrace" not in _network_names()


def test_three_start_stop_cycles_leave_no_residue(
    bash_run: Callable[..., CompletedProcess[str]],
    repo_root: Path,
) -> None:
    foreign_before = _foreign_container_ids()
    networks_before = _network_names() - {"saam-medtrace"}
    volumes_before = _existing_volumes() - _our_volumes()

    for cycle in range(1, 4):
        started = bash_run(["fabric/network.sh", "start"], timeout=420)
        _assert_ok(started, f"cycle {cycle} start")
        assert "state: healthy" in started.stdout

        status = bash_run(["fabric/network.sh", "status"], timeout=60)
        _assert_ok(status, f"cycle {cycle} status")
        assert "state: healthy" in status.stdout
        assert "channel: medtrace" in status.stdout
        assert "state_database: goleveldb" in status.stdout
        for peer in PEERS:
            assert f"{peer}: joined" in status.stdout
            assert "medtrace" in {
                line.strip() for line in _peer_channels(peer).splitlines()
            }
            database = _docker(
                "exec", peer, "printenv", "CORE_LEDGER_STATE_STATEDATABASE"
            )
            assert database.stdout.strip() == "goleveldb"
        assert "orderer: joined" in status.stdout
        assert _orderer_channel_names() == {"medtrace"}

        tracked = subprocess.check_output(
            ["git", "ls-files"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
        )
        for line in tracked.splitlines():
            lowered = line.lower()
            assert not lowered.endswith((".pem", ".key", ".crt", "_sk"))
            assert "ca.env" not in lowered
            assert not lowered.startswith("fabric/organizations/")
            assert not lowered.startswith("fabric/.runtime/")
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", "fabric/.runtime/ca.env"],
            cwd=repo_root,
            check=False,
        )
        assert ignored.returncode == 0
        ignored_wallet = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                "--",
                "fabric/wallet/agent-ingestion/key.pem",
            ],
            cwd=repo_root,
            check=False,
        )
        assert ignored_wallet.returncode == 0

        stopped = bash_run(["fabric/network.sh", "stop"], timeout=180)
        _assert_ok(stopped, f"cycle {cycle} stop")
        for name in OUR_CONTAINERS:
            assert _docker("inspect", name).returncode != 0
        for name in OUR_VOLUMES:
            assert _docker("volume", "inspect", name).returncode != 0
        assert _our_container_ids() == set()
        assert _our_volumes() == set()
        assert "saam-medtrace" not in _network_names()
        assert foreign_before <= _foreign_container_ids()
        assert networks_before <= (_network_names() - {"saam-medtrace"})
        assert volumes_before <= _existing_volumes()
        assert not (repo_root / "fabric" / "wallet").exists()
