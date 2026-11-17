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


def _services(compose: str) -> dict[str, str]:
    """Split the `services:` block of compose.yaml into {service name: block text}."""
    body = compose.split("\nservices:\n", 1)[1]
    parts = re.split(r"^  ([a-z0-9-]+):\s*$", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_every_compose_service_carries_the_ownership_label(repo_root: Path) -> None:
    """AUD-028: `network.sh stop` removes only containers labeled saam.network=medtrace.

    A one-off container without the label (an interrupted build, for example) stays
    attached to the project network and makes `stop`, and so the next `start`, fail.
    """
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    services = _services(compose)
    assert {"ca-org1", "orderer", "peer0-org1", "cc-build", "gw-build", "spike"} <= set(
        services
    )
    unlabeled = [
        name
        for name, block in services.items()
        if not re.search(r"^\s+saam\.network: medtrace\s*$", block, re.MULTILINE)
    ]
    assert unlabeled == []


def test_every_compose_image_is_pinned(repo_root: Path) -> None:
    """AUD-035: exact version tag or digest, never a moving tag such as `20-bookworm`."""
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    images = re.findall(r"^\s+image: (\S+)\s*$", compose, flags=re.MULTILINE)
    assert len(images) == len(_services(compose))
    unpinned = [
        image
        for image in images
        if not re.search(r"@sha256:[0-9a-f]{64}$", image)
        and not re.search(r":\d+\.\d+\.\d+$", image)
    ]
    assert unpinned == []


def test_spike_container_does_not_see_the_organizations_tree(repo_root: Path) -> None:
    """AUD-033: the spike runs npm code; it gets the wallet (identities and the peer's TLS
    CA certificate), never the CA keys or the admin MSPs under organizations/."""
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    block = _services(compose)["spike"]
    mounts = re.findall(r"^\s+- (\S+:\S+)\s*$", block, flags=re.MULTILINE)
    assert sorted(mounts) == ["../../ledger-gateway:/gw", "../wallet:/wallet:ro"]
    assert "organizations" not in block
    assert "PEER_TLS_CERT: /wallet/peer0-org1-tls-ca.crt" in block


def test_cleaner_service_removes_generated_files_without_a_network(
    repo_root: Path,
) -> None:
    """AUD-046: a root container deletes what root containers wrote; it must not
    recreate the project network that `stop` has just removed."""
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    block = _services(compose)["cleaner"]
    assert "network_mode: none" in block
    assert "- ..:/work/fabric" in block
    assert 'profiles: ["tools"]' in block
    assert "hyperledger/fabric-tools:2.5.16" in block


def test_running_chaincode_services_mount_their_source_read_only(
    repo_root: Path,
) -> None:
    """AUD-033: only the build service writes to the package directory."""
    compose = (repo_root / "fabric" / "compose" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    services = _services(compose)
    for name in ("cc-org1", "cc-org2"):
        assert "- ../../chaincode/provenance:/src:ro" in services[name], name
    assert "- ../../chaincode/provenance:/src\n" in services["cc-build"]


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
