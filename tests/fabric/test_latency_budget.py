"""Seven sequential Fabric commits, and the 7.3 s anchor budget from DF-01."""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from subprocess import CompletedProcess

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUDGET_SECONDS = 7.3


def configured_batch_timeout() -> str:
    """BatchTimeout as the channel is created from it (fabric/config/configtx.yaml)."""
    configtx = (ROOT / "fabric" / "config" / "configtx.yaml").read_text(
        encoding="utf-8"
    )
    declared = re.search(r"^[ \t]*BatchTimeout:[ \t]*(\S+)", configtx, re.MULTILINE)
    assert declared is not None, "BatchTimeout is missing from configtx.yaml"
    return declared.group(1)


def nearest_rank(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    rank = math.ceil((percentile / 100) * len(ordered))
    index = min(len(ordered), max(1, rank)) - 1
    return ordered[index]


def classify_latency_result(
    returncode: int,
    report: Mapping[str, object] | None,
) -> str:
    """Separate a measured budget breach from a run that produced no baseline."""
    if not isinstance(report, Mapping) or report.get("validatedCount") != 7:
        return "environment-unavailable"
    p95 = report.get("p95")
    if isinstance(p95, bool) or not isinstance(p95, (int, float)):
        return "environment-unavailable"
    if p95 > BUDGET_SECONDS:
        return "budget-exceeded"
    if returncode != 0:
        return "environment-unavailable"
    return "within-budget"


def _json_object(text: str) -> dict[str, object]:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                return payload
    raise AssertionError("response did not contain a JSON object")


def _redacted(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if (
            "password" in lowered
            or "private key" in lowered
            or "begin " in lowered
            or "://" in lowered
        ):
            kept.append("[redacted]")
        else:
            kept.append(line)
    return "\n".join(kept[-40:])


def test_latency_sources_require_seven_transactions_and_the_budget_fields() -> None:
    gateway = json.loads(
        (ROOT / "ledger-gateway" / "package.json").read_text(encoding="utf-8")
    )
    assert gateway["scripts"]["spike:latency"] == "node dist/spike-latency.js"
    source = (ROOT / "ledger-gateway" / "src" / "spike-latency.ts").read_text(
        encoding="utf-8"
    )
    assert "TRANSACTION_COUNT = 7" in source
    assert "BUDGET_SECONDS = 7.3" in source
    assert 'endorsingOrganizations: ["Org1MSP", "Org2MSP"]' in source
    assert 'percentileMethod: "nearest-rank"' in source
    assert "p50" in source and "p95" in source and "maximum" in source
    assert '"set-to-0.5s"' in source
    script = (ROOT / "fabric" / "spike-latency.sh").read_text(encoding="utf-8")
    assert "environment unavailable" in script
    assert "BatchTimeout" in script


def test_nearest_rank_p95_of_seven_samples_is_the_slowest() -> None:
    samples = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 8.0]
    assert nearest_rank(samples, 50) == 1.0
    assert nearest_rank(samples, 95) == 8.0
    assert nearest_rank(samples, 95) == max(samples)


def test_budget_violation_is_not_classified_as_an_unavailable_environment() -> None:
    breach = {
        "validatedCount": 7,
        "p50": 1.0,
        "p95": 8.0,
        "maximum": 8.0,
        "withinBudget": False,
        "batchTimeoutDecision": "set-to-0.5s",
    }
    assert classify_latency_result(2, breach) == "budget-exceeded"
    assert classify_latency_result(0, breach) == "budget-exceeded"
    assert classify_latency_result(1, None) == "environment-unavailable"
    assert (
        classify_latency_result(0, {"validatedCount": 3, "p95": 1.0})
        == "environment-unavailable"
    )
    within = {"validatedCount": 7, "p50": 1.0, "p95": 2.0, "maximum": 2.0}
    assert classify_latency_result(0, within) == "within-budget"
    assert classify_latency_result(1, within) == "environment-unavailable"


def test_missing_wallet_is_an_environment_failure(
    bash_run: Callable[..., CompletedProcess[str]],
    repo_root: Path,
) -> None:
    wallet = repo_root / "fabric" / "wallet" / "peer0-org1-tls-ca.crt"
    if wallet.is_file():
        pytest.skip(
            "wallet present; the missing-wallet path is not the current environment"
        )
    result = bash_run(["fabric/spike-latency.sh"], timeout=60)
    assert result.returncode == 1
    assert "environment unavailable" in result.stderr
    assert "p50" not in result.stdout
    assert classify_latency_result(result.returncode, None) == "environment-unavailable"


def _docker_ready() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return False, detail or "docker info failed"
    return True, ""


@pytest.fixture
def _stop_after_test(bash_run: Callable[..., CompletedProcess[str]]) -> object:
    yield
    bash_run(["fabric/network.sh", "stop"], timeout=180)


@pytest.mark.fabric
def test_seven_commits_report_percentiles_and_enforce_the_budget(
    bash_run: Callable[..., CompletedProcess[str]],
    _stop_after_test: object,
) -> None:
    ready, reason = _docker_ready()
    if not ready:
        pytest.skip(f"environment unavailable: {reason}")

    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    assert started.returncode == 0, (
        "environment unavailable: network start failed\n"
        f"{_redacted(started.stdout)}\n{_redacted(started.stderr)}"
    )
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert enrolled.returncode == 0, (
        "environment unavailable: enrollment failed\n"
        f"{_redacted(enrolled.stdout)}\n{_redacted(enrolled.stderr)}"
    )

    measured = bash_run(["fabric/spike-latency.sh"], timeout=600)
    report: dict[str, object] | None
    try:
        report = _json_object(measured.stdout)
    except AssertionError:
        report = None
    outcome = classify_latency_result(measured.returncode, report)
    if outcome == "environment-unavailable":
        raise AssertionError(
            "environment unavailable: latency run did not validate seven transactions\n"
            f"exit {measured.returncode}\n{_redacted(measured.stdout)}\n{_redacted(measured.stderr)}"
        )
    assert report is not None
    for field in ("p50", "p95", "maximum"):
        assert isinstance(report[field], (int, float)) and not isinstance(
            report[field], bool
        )
    samples = report["samplesSeconds"]
    assert isinstance(samples, list) and len(samples) == 7
    numeric = [float(sample) for sample in samples]
    assert report["p50"] == pytest.approx(nearest_rank(numeric, 50))
    assert report["p95"] == pytest.approx(nearest_rank(numeric, 95))
    assert report["maximum"] == pytest.approx(max(numeric))
    assert report["validatedCount"] == 7
    assert report["validationCodes"] == ["VALID"] * 7
    assert report["measurement"] == "endorse-submit-commit-valid"
    assert report["percentileMethod"] == "nearest-rank"
    assert "Org1MSP.peer" in str(report["endorsementPolicy"])
    assert "Org2MSP.peer" in str(report["endorsementPolicy"])
    assert report["batchTimeout"] == configured_batch_timeout()
    if outcome == "budget-exceeded":
        assert report["withinBudget"] is False
        assert report["batchTimeoutDecision"] == "set-to-0.5s"
        pytest.fail(
            "budget exceeded: "
            f"p50={report['p50']} p95={report['p95']} maximum={report['maximum']} "
            "decision=set-to-0.5s"
        )
    assert outcome == "within-budget"
    assert report["withinBudget"] is True
    assert report["batchTimeoutDecision"] == "keep"
    assert measured.returncode == 0
    _assert_probe_runs_on_its_own(bash_run)
    print(
        "LATENCY_BASELINE "
        + json.dumps(
            {
                "p50": report["p50"],
                "p95": report["p95"],
                "maximum": report["maximum"],
                "samplesSeconds": report["samplesSeconds"],
                "batchTimeout": report["batchTimeout"],
                "batchTimeoutDecision": report["batchTimeoutDecision"],
            },
            separators=(",", ":"),
        )
    )


def _assert_probe_runs_on_its_own(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-049: `npm run spike:latency` is the documented command, with no wrapper variables."""
    # The wrapper's own test for "this host can run the probe". `shutil.which("npm")` is not
    # enough: under WSL a Windows npm is on the PATH without a usable `node`.
    host = bash_run(["-c", "source fabric/spike-latency.sh; host_can_run"], timeout=60)
    if host.returncode != 0:
        return  # no host Node: fabric/spike-latency.sh took the container branch above
    alone = bash_run(
        [
            "-c",
            "cd ledger-gateway && npm run build >/dev/null && npm run spike:latency",
        ],
        env={"BATCH_TIMEOUT": "", "ENDORSEMENT_POLICY": ""},
        timeout=300,
    )
    report = _json_object(alone.stdout)
    assert classify_latency_result(alone.returncode, report) == "within-budget", (
        f"exit {alone.returncode}\n{_redacted(alone.stdout)}\n{_redacted(alone.stderr)}"
    )
    assert report["batchTimeout"] == configured_batch_timeout()
    assert "Org1MSP.peer" in str(report["endorsementPolicy"])
    assert "Org2MSP.peer" in str(report["endorsementPolicy"])
