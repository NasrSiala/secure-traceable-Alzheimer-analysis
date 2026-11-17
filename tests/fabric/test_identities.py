"""Enrollment and certificate-attribute authorization for the nine Fabric identities."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from fabric_support import assert_ok

ROOT = Path(__file__).resolve().parents[2]

EXPECTED = {
    "agent-ingestion": ("Org1MSP", "pipeline-agent", "ingestion"),
    "agent-preparation": ("Org1MSP", "pipeline-agent", "preparation"),
    "agent-features": ("Org1MSP", "pipeline-agent", "features"),
    "agent-prediction": ("Org1MSP", "pipeline-agent", "prediction"),
    "agent-validation": ("Org1MSP", "pipeline-agent", "validation"),
    "agent-explanation": ("Org1MSP", "pipeline-agent", "explanation"),
    "agent-finalization": ("Org1MSP", "pipeline-agent", "finalization"),
    "model-admin": ("Org1MSP", "model-admin", None),
    "verifier": ("Org2MSP", None, None),
}


def _json_object(text: str) -> dict[str, object]:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                return payload
    raise AssertionError("response did not contain a JSON object")


def _attributes(certificate: Path) -> dict[str, str]:
    pem = certificate.read_text(encoding="utf-8")
    body = "".join(line for line in pem.splitlines() if not line.startswith("-----"))
    raw = base64.b64decode(body).decode("latin1")
    start = raw.find('{"attrs":')
    assert start >= 0, "certificate has no Fabric attribute extension"
    depth = 0
    for index, char in enumerate(raw[start:], start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                payload = json.loads(raw[start : index + 1])
                attributes = payload["attrs"]
                assert isinstance(attributes, dict)
                return {str(name): str(value) for name, value in attributes.items()}
    raise AssertionError("certificate attribute extension is truncated")


def _assert_owned_by_current_user(roots: list[Path]) -> None:
    """AUD-041: containers run as root; on Linux the host user must still own what they
    wrote into the checkout (the wallet, node_modules, dist), or it cannot read, delete
    or rebuild them. Windows has no uid: nothing to check there."""
    if not hasattr(os, "getuid") or os.getuid() == 0:
        return
    uid = os.getuid()
    foreign = [
        str(path)
        for root in roots
        for path in (root, *root.rglob("*"))
        if path.lstat().st_uid != uid
    ]
    assert foreign == [], foreign[:5]


def _spike(
    bash_run: Callable[..., CompletedProcess[str]],
    identity: str,
    operation: str,
    key: str,
) -> CompletedProcess[str]:
    return bash_run(
        ["fabric/spike-submit.sh"],
        env={"SPIKE_IDENTITY": identity, "SPIKE_OP": operation, "SPIKE_KEY": key},
        timeout=180,
    )


def test_sources_name_nine_identities_and_refuse_writes_without_the_agent_role() -> (
    None
):
    enroll = (ROOT / "fabric" / "scripts" / "enroll-identities.sh").read_text(
        encoding="utf-8"
    )
    for name in EXPECTED:
        assert name in enroll or name.removeprefix("agent-") in enroll
    chaincode = (ROOT / "chaincode" / "provenance" / "src" / "artifact.ts").read_text(
        encoding="utf-8"
    )
    assert 'role !== "pipeline-agent"' in chaincode
    assert "FORBIDDEN" in chaincode
    gateway = json.loads(
        (ROOT / "ledger-gateway" / "package.json").read_text(encoding="utf-8")
    )
    assert gateway["scripts"]["spike:submit"] == "node dist/spike-submit.js"
    network = (ROOT / "fabric" / "network.sh").read_text(encoding="utf-8")
    assert "wallet" in network


@pytest.mark.fabric
def test_enrolled_identities_authorize_agent_writes_and_refuse_verifier(
    bash_run: Callable[..., CompletedProcess[str]],
    repo_root: Path,
    _stop_after_test: object,
) -> None:
    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    assert_ok(started, "start")
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert_ok(enrolled, "enroll")

    for name, (msp_id, role, agent) in EXPECTED.items():
        home = repo_root / "fabric" / "wallet" / name
        assert (home / "cert.pem").is_file()
        assert (home / "key.pem").is_file()
        assert (home / "msp-id").read_text(encoding="utf-8").strip() == msp_id
        attributes = _attributes(home / "cert.pem")
        assert attributes.get("role") == role
        assert attributes.get("agent") == agent

    tls_ca = repo_root / "fabric" / "wallet" / "peer0-org1-tls-ca.crt"
    assert tls_ca.read_text(encoding="utf-8").startswith("-----BEGIN CERTIFICATE-----")

    _assert_owned_by_current_user(
        [
            repo_root / "fabric" / "wallet",
            repo_root / "chaincode" / "provenance" / "node_modules",
            repo_root / "chaincode" / "provenance" / "dist",
            repo_root / "ledger-gateway" / "node_modules",
            repo_root / "ledger-gateway" / "dist",
        ]
    )

    tracked = subprocess.check_output(
        ["git", "ls-files"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
    )
    assert "fabric/wallet/" not in tracked
    assert not any(
        line.lower().endswith((".pem", ".key", "_sk")) for line in tracked.splitlines()
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", "fabric/wallet/agent-ingestion/key.pem"],
        cwd=repo_root,
        check=False,
    )
    assert ignored.returncode == 0

    accepted = _spike(bash_run, "agent-ingestion", "write", "ingestion-probe")
    assert_ok(accepted, "agent-ingestion create")
    record = _json_object(accepted.stdout)
    assert record["docType"] == "artifact"
    assert record["artifactType"] == "original"
    assert record["creatorAgent"] == "ingestion"
    assert record["creatorMspId"] == "Org1MSP"
    assert "CN=agent-ingestion" in str(record["creatorId"])

    duplicate = _spike(bash_run, "agent-ingestion", "write", "ingestion-probe")
    assert duplicate.returncode != 0
    assert "DUPLICATE" in duplicate.stdout + duplicate.stderr

    refused = _spike(bash_run, "verifier", "write", "verifier-probe")
    assert refused.returncode != 0
    assert "FORBIDDEN" in refused.stdout + refused.stderr

    visible = _spike(bash_run, "verifier", "read", "ingestion-probe")
    assert_ok(visible, "verifier read")
    read_back = _json_object(visible.stdout)
    assert read_back["artifactId"] == record["artifactId"]
    assert read_back["sha256"] == record["sha256"]
    assert read_back["creatorAgent"] == "ingestion"

    # AUD-029, AUD-031: the whole enrollment and deployment can run again on the
    # live network. Fresh keys are enrolled, the committed definition is checked
    # instead of committed twice, and the same agent can still write.
    repeated = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert_ok(repeated, "second enrollment")
    assert "already committed" in repeated.stdout + repeated.stderr
    for name, (_msp_id, role, agent) in EXPECTED.items():
        attributes = _attributes(repo_root / "fabric" / "wallet" / name / "cert.pem")
        assert attributes.get("role") == role
        assert attributes.get("agent") == agent
    again = _spike(bash_run, "agent-ingestion", "write", "ingestion-probe-again")
    assert_ok(again, "agent-ingestion create after the second enrollment")
    assert _json_object(again.stdout)["creatorAgent"] == "ingestion"
