"""Gateway create/read against the test network, including a stopped peer."""

from __future__ import annotations

import json
from collections.abc import Callable
from subprocess import CompletedProcess

import pytest

pytestmark = pytest.mark.fabric


def _redacted(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if (
            "password" in lowered
            or "private key" in lowered
            or "begin " in lowered
            or "x-agent-token" in lowered
            or "://" in lowered
        ):
            kept.append("[redacted]")
        else:
            kept.append(line)
    return "\n".join(kept[-40:])


def _assert_ok(result: CompletedProcess[str], step: str) -> None:
    assert result.returncode == 0, (
        f"{step} failed with exit {result.returncode}\n"
        f"{_redacted(result.stdout)}\n{_redacted(result.stderr)}"
    )


def _report(result: CompletedProcess[str]) -> dict[str, object]:
    for line in reversed(result.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("GATEWAY_CHECK "):
            payload = json.loads(stripped.removeprefix("GATEWAY_CHECK "))
            if isinstance(payload, dict):
                return payload
    raise AssertionError(
        f"no GATEWAY_CHECK line\n{_redacted(result.stdout)}\n{_redacted(result.stderr)}"
    )


@pytest.fixture
def _stop_after_test(bash_run: Callable[..., CompletedProcess[str]]) -> object:
    yield
    bash_run(["fabric/network.sh", "stop"], timeout=180)


def test_gateway_create_read_duplicate_and_stopped_peer(
    bash_run: Callable[..., CompletedProcess[str]],
    _stop_after_test: object,
) -> None:
    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    _assert_ok(started, "start")
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    _assert_ok(enrolled, "enroll")

    # Twice on one network: CreateArtifactRecord refuses an existing artifactId (AC-07.3), so a
    # check that reuses an identifier passes once and fails the second time (AUD-070).
    for run in ("first", "second"):
        flow = bash_run(
            ["fabric/gateway-check.sh"],
            env={"GATEWAY_SCENARIO": "flow"},
            timeout=300,
        )
        _assert_ok(flow, f"{run} flow")
        report = _report(flow)
        assert report["create"] == 200, run
        assert report["read"] == 200, run
        assert report["duplicate"] == 409, run
        assert report["duplicateCode"] == "DUPLICATE", run
        assert report["missing"] == 404, run
        assert report["missingCode"] == "NOT_FOUND", run
        assert report["unauthorized"] == 401, run
        assert report["unauthorizedCode"] == "UNAUTHORIZED", run
        assert report["shape"] is True, run

    stopped = bash_run(["-c", "docker stop saam-medtrace-peer0-org1"], timeout=90)
    _assert_ok(stopped, "stop peer")
    down = bash_run(
        ["fabric/gateway-check.sh"],
        env={"GATEWAY_SCENARIO": "down"},
        timeout=180,
    )
    _assert_ok(down, "stopped peer")
    unavailable = _report(down)
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
