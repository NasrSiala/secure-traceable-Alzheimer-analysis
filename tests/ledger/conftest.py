"""Serveur HTTP de la gateway réelle sur loopback, sans wallet ni réseau Fabric."""

import json
import os
import secrets
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def gateway(repo_root):
    node = shutil.which("node")
    assert node, "Node est requis pour les tests HTTP de contrat de la gateway."
    package = repo_root / "ledger-gateway"
    if not (package / "node_modules").is_dir():
        npm_cli = shutil.which("npm.cmd") or shutil.which("npm")
        assert npm_cli, "Installer les dépendances verrouillées avec npm ci."
        subprocess.run(
            [npm_cli, "ci", "--ignore-scripts"],
            cwd=package,
            check=True,
            capture_output=True,
            timeout=180,
        )
    subprocess.run(
        [node, "node_modules/typescript/bin/tsc"],
        cwd=package,
        check=True,
        capture_output=True,
        timeout=60,
    )
    agent, verifier = secrets.token_hex(32), secrets.token_hex(32)
    process = subprocess.Popen(
        [node, "tests/ledger/gateway-fixture.cjs"],
        cwd=repo_root,
        env=os.environ | {"TEST_AGENT_TOKEN": agent, "TEST_VERIFIER_TOKEN": verifier},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        assert process.stdout is not None
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(process.stdout.readline)
            try:
                line = future.result(timeout=20)
            except TimeoutError:
                process.kill()
                raise
        assert line, "La gateway HTTP de test n'a pas démarré."
        yield json.loads(line)["address"], agent, verifier
    finally:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
