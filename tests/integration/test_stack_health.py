"""Tests explicites sur la pile locale T1.5 déjà démarrée."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.stack,
    pytest.mark.skipif(
        os.environ.get("SAAM_TEST_STACK") != "1",
        reason="Pile T1.5 requise ; SAAM_TEST_STACK=1",
    ),
]


def health() -> tuple[int, dict[str, object]]:
    url = os.environ.get("SAAM_STACK_URL", "https://localhost/api/v1/health")
    context = ssl._create_unverified_context()
    try:
        response = urllib.request.urlopen(url, timeout=8, context=context)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def compose(root: Path, *args: str) -> None:
    subprocess.run(
        ["docker", "compose", *args], cwd=root, check=True, capture_output=True
    )


def wait_healthy() -> dict[str, object]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status, body = health()
        if status == 200 and body["status"] == "ok":
            return body
        time.sleep(1)
    raise AssertionError("La pile n'est pas revenue au vert en 60 s")


def test_https_health_and_five_containers(repo_root: Path) -> None:
    body = wait_healthy()
    assert body["services"] == {
        "api": "ok",
        "postgres": "ok",
        "worker": "ok",
        "ledger-gateway": "ok",
        "frontend": "ok",
    }
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=repo_root,
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
        )
        containers = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip()
        ]
        if len(containers) == 5 and all(
            container["Health"] == "healthy" for container in containers
        ):
            break
        time.sleep(1)
    else:
        raise AssertionError("Les cinq conteneurs ne sont pas tous healthy en 60 s")
    security = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "ledger-gateway",
            "sh",
            "-c",
            "grep '^Uid:' /proc/1/status; stat -c '%u:%g %a' /run/ledger-wallet/verifier/key.pem",
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    identity, key_permissions = security.stdout.splitlines()
    assert identity.split()[1:] == ["1000", "1000", "1000", "1000"]
    assert key_permissions == "1000:1000 600"


@pytest.mark.parametrize("service", ["worker", "ledger-gateway", "postgres"])
def test_stopped_dependency_turns_health_red_then_recovers(
    repo_root: Path, service: str
) -> None:
    wait_healthy()
    try:
        compose(repo_root, "stop", service)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status, body = health()
            if status == 503 and body["services"][service] == "error":
                break
            time.sleep(1)
        else:
            raise AssertionError(f"L'arrêt de {service} n'a pas rendu /health rouge")
        assert body["error"]["code"] == "UNAVAILABLE"
    finally:
        compose(repo_root, "start", service)
        wait_healthy()
