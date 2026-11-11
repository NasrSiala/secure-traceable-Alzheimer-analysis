"""Static checks for the network lifecycle. They do not start Fabric."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess


def test_compose_pins_fabric_25_leveldb_and_isolated_names(repo_root: Path) -> None:
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    assert "hyperledger/fabric-peer:2.5.16" in compose
    assert "hyperledger/fabric-orderer:2.5.16" in compose
    assert "hyperledger/fabric-ca:1.5.17" in compose
    assert "hyperledger/fabric-tools:2.5.16" in compose
    assert "CORE_LEDGER_STATE_STATEDATABASE: goleveldb" in compose
    assert "container_name: saam-medtrace-orderer" in compose
    assert "container_name: saam-medtrace-peer0-org1" in compose
    assert "container_name: saam-medtrace-peer0-org2" in compose
    assert "name: saam-medtrace" in compose
    assert "18050:7050" in compose
    assert "18051:7051" in compose
    assert "18052:7051" in compose
    for banned in (
        "image: hyperledger/fabric-peer:latest",
        "container_name: orderer.example.com",
        "container_name: peer0.org1.example.com",
    ):
        assert banned not in compose


def _published_ports(compose: str) -> list[str]:
    return re.findall(r'^\s+- "([^"]*\d+:\d+)"\s*$', compose, re.MULTILINE)


def test_published_ports_are_bound_to_loopback(repo_root: Path) -> None:
    """AUD-004: the test network is not offered to the LAN."""
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    entries = _published_ports(compose)
    assert len(entries) == 7  # 3 CAs, orderer (2 ports), 2 peers
    assert [entry for entry in entries if not entry.startswith("127.0.0.1:")] == []


def test_host_ports_in_script_match_compose(repo_root: Path) -> None:
    """The probe in network.sh must cover exactly the ports compose publishes."""
    script = (repo_root / "fabric" / "network.sh").read_text(encoding="utf-8")
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    declared = re.search(r"^HOST_PORTS=\(([^)]*)\)", script, re.MULTILINE)
    assert declared is not None
    published = {entry.split(":")[1] for entry in _published_ports(compose)}
    assert set(declared.group(1).split()) == published


def test_network_script_documents_lifecycle_and_refuses_broad_docker_cleanup(
    repo_root: Path,
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    script = (repo_root / "fabric" / "network.sh").read_text(encoding="utf-8")
    assert "docker volume prune" not in script
    assert "docker system prune" not in script
    unfiltered = [
        line.strip()
        for line in script.splitlines()
        if "docker ps -aq" in line and "label=saam.network=medtrace" not in line
    ]
    assert unfiltered == []
    result = bash_run(["fabric/network.sh", "--help"], timeout=60)
    assert result.returncode == 0
    for word in ("start", "status", "stop", "medtrace", "saam-medtrace"):
        assert word in result.stdout


def test_unknown_network_command_exits_nonzero(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    result = bash_run(["fabric/network.sh", "destroy-everything"], timeout=60)
    assert result.returncode == 2


def test_start_fails_when_docker_is_absent(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    candidates = ("/usr/bin:/bin", r"C:\Windows\System32")
    chosen: str | None = None
    probes: list[str] = []
    for candidate in candidates:
        probe = bash_run(
            [
                "-c",
                "if command -v docker >/dev/null 2>&1; then echo FOUND; else echo MISSING; fi",
            ],
            env={"PATH": candidate},
            timeout=60,
        )
        verdict = probe.stdout.strip()
        probes.append(f"{candidate}: {verdict}")
        if probe.returncode == 0 and verdict == "MISSING":
            chosen = candidate
            break
    if chosen is None:
        raise AssertionError(
            "Could not construct a PATH without docker, so the missing-prerequisite path was not exercised.\n"
            + "\n".join(probes)
        )
    result = bash_run(["fabric/network.sh", "start"], env={"PATH": chosen}, timeout=60)
    if result.returncode == 0:
        bash_run(["fabric/network.sh", "stop"], timeout=180)
        raise AssertionError("start succeeded even though docker was not on PATH")
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Docker is required but was not found on PATH." in combined
