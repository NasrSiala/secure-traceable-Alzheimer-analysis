"""Gateway create/read against the test network, including a stopped peer."""

from __future__ import annotations

import json
from collections.abc import Callable
from subprocess import CompletedProcess

import pytest
from fabric_support import assert_ok, report_line

pytestmark = pytest.mark.fabric


def test_gateway_create_read_duplicate_and_stopped_peer(
    bash_run: Callable[..., CompletedProcess[str]],
    _stop_after_test: object,
) -> None:
    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    assert_ok(started, "start")
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert_ok(enrolled, "enroll")

    # Twice on one network: CreateArtifactRecord refuses an existing artifactId (AC-07.3), so a
    # check that reuses an identifier passes once and fails the second time (AUD-070).
    for run in ("first", "second"):
        flow = bash_run(
            ["fabric/gateway-check.sh"],
            env={"GATEWAY_SCENARIO": "flow"},
            timeout=300,
        )
        assert_ok(flow, f"{run} flow")
        report = report_line(flow, "GATEWAY_CHECK")
        assert report["create"] == 200, run
        assert report["read"] == 200, run
        assert report["duplicate"] == 409, run
        assert report["duplicateCode"] == "DUPLICATE", run
        assert report["missing"] == 404, run
        assert report["missingCode"] == "NOT_FOUND", run
        assert report["unauthorized"] == 401, run
        assert report["unauthorizedCode"] == "UNAUTHORIZED", run
        assert report["shape"] is True, run
        # The creator comes from the certificate (NFR-06) ...
        assert report["creatorMspId"] == "Org1MSP", run
        assert report["creatorAgent"] == "ingestion", run
        assert "CN=agent-ingestion" in str(report["creatorId"]), run
        # ... and a client that names its own creator is refused and stores nothing.
        assert report["forged"] == 400, run
        assert report["forgedCode"] == "SCHEMA", run
        assert report["forgedStored"] is False, run

    stopped = bash_run(["-c", "docker stop saam-medtrace-peer0-org1"], timeout=90)
    assert_ok(stopped, "stop peer")
    down = bash_run(
        ["fabric/gateway-check.sh"],
        env={"GATEWAY_SCENARIO": "down"},
        timeout=180,
    )
    assert_ok(down, "stopped peer")
    unavailable = report_line(down, "GATEWAY_CHECK")
    assert unavailable["status"] == 502
    assert unavailable["code"] == "UNAVAILABLE"
    assert unavailable["shape"] is True
    # The 502 body is the same for every cause (AUD-071); the operator reads the cause on
    # stderr, as one JSON line, with no token and no request body.
    failure_lines = [
        line for line in down.stderr.splitlines() if '"event":"ledger-failure"' in line
    ]
    assert len(failure_lines) == 1, down.stderr
    failure = json.loads(failure_lines[0])
    assert failure["operation"] == "GetArtifactRecord"
    assert failure["status"] == 502
    assert "UNAVAILABLE" in failure["cause"]
