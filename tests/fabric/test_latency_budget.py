"""Seven sequential Fabric commits, and the 7.3 s anchor budget from DF-01."""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUDGET_SECONDS = 7.3
# A breach must repeat this many times in a row before the guard fails (AUD-068).
LATENCY_ATTEMPTS = 3


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


@dataclass
class Settled:
    """Result of measure_until_settled: the last run, and every run that breached."""

    outcome: str
    returncode: int
    report: dict[str, object] | None
    breaches: list[dict[str, object]] = field(default_factory=list)


def measure_until_settled(
    measure: Callable[[], tuple[int, dict[str, object] | None]],
    attempts: int = LATENCY_ATTEMPTS,
) -> Settled:
    """Run the seven-transaction probe; run it again only after a budget breach.

    Seven samples make the p95 the slowest one, so a single stalled host (a Docker engine
    that has just restarted, say) breaches the budget although BatchTimeout is fine. The
    guard exists to catch a configuration that is slow every time, so it fails when the
    breach repeats `attempts` times in a row. Each run is still judged against the same
    7.3 s. A run with no baseline (environment unavailable) is never repeated.
    """
    breaches: list[dict[str, object]] = []
    returncode, report = 0, None
    for _ in range(attempts):
        returncode, report = measure()
        outcome = classify_latency_result(returncode, report)
        if outcome != "budget-exceeded":
            return Settled(outcome, returncode, report, breaches)
        assert report is not None
        breaches.append(report)
    return Settled("budget-exceeded", returncode, report, breaches)


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
    assert 'newProposal("CreateArtifactRecord"' in source
    assert 'CONTRACT = "Provenance"' in source
    assert 'percentileMethod: "nearest-rank"' in source
    assert "p50" in source and "p95" in source and "maximum" in source
    assert '"set-to-0.5s"' in source
    assert "Run again before changing BatchTimeout" in source
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


BREACH: tuple[int, dict[str, object] | None] = (
    2,
    {"validatedCount": 7, "p50": 4.8, "p95": 9.0, "maximum": 9.0},
)
WITHIN: tuple[int, dict[str, object] | None] = (
    0,
    {"validatedCount": 7, "p50": 2.08, "p95": 2.2, "maximum": 2.2},
)
NO_BASELINE: tuple[int, dict[str, object] | None] = (1, None)


def _scripted(
    runs: list[tuple[int, dict[str, object] | None]],
) -> tuple[Callable[[], tuple[int, dict[str, object] | None]], list[int]]:
    calls: list[int] = []

    def measure() -> tuple[int, dict[str, object] | None]:
        calls.append(1)
        return runs[len(calls) - 1]

    return measure, calls


def test_a_run_within_budget_is_not_repeated() -> None:
    measure, calls = _scripted([WITHIN])
    settled = measure_until_settled(measure)
    assert (settled.outcome, len(calls), settled.breaches) == ("within-budget", 1, [])


def test_one_stalled_run_followed_by_a_normal_one_passes_and_is_kept_on_record() -> (
    None
):
    """AUD-068: a host stall is not a BatchTimeout problem."""
    measure, calls = _scripted([BREACH, WITHIN])
    settled = measure_until_settled(measure)
    assert settled.outcome == "within-budget"
    assert settled.report == WITHIN[1]
    assert len(calls) == 2
    assert [breach["p95"] for breach in settled.breaches] == [9.0]


def test_a_breach_that_repeats_fails_after_exactly_three_runs() -> None:
    measure, calls = _scripted([BREACH, BREACH, BREACH, WITHIN])
    settled = measure_until_settled(measure)
    assert settled.outcome == "budget-exceeded"
    assert len(calls) == LATENCY_ATTEMPTS == 3
    assert len(settled.breaches) == 3


def test_two_breaches_then_a_normal_run_still_passes() -> None:
    measure, calls = _scripted([BREACH, BREACH, WITHIN])
    settled = measure_until_settled(measure)
    assert (settled.outcome, len(calls), len(settled.breaches)) == (
        "within-budget",
        3,
        2,
    )


def test_a_run_without_a_baseline_is_never_repeated() -> None:
    measure, calls = _scripted([NO_BASELINE, WITHIN])
    settled = measure_until_settled(measure)
    assert (settled.outcome, len(calls)) == ("environment-unavailable", 1)


def test_the_budget_itself_is_unchanged() -> None:
    """The retry must not loosen what counts as a breach."""
    just_over: dict[str, object] = {"validatedCount": 7, "p95": 7.31}
    just_under: dict[str, object] = {"validatedCount": 7, "p95": 7.3}
    assert classify_latency_result(2, just_over) == "budget-exceeded"
    assert classify_latency_result(0, just_under) == "within-budget"
    assert BUDGET_SECONDS == 7.3


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

    runs: list[CompletedProcess[str]] = []

    def run_probe() -> tuple[int, dict[str, object] | None]:
        run = bash_run(["fabric/spike-latency.sh"], timeout=600)
        runs.append(run)
        try:
            return run.returncode, _json_object(run.stdout)
        except AssertionError:
            return run.returncode, None

    settled = measure_until_settled(run_probe)
    outcome, report = settled.outcome, settled.report
    measured = runs[-1]
    if outcome == "environment-unavailable":
        raise AssertionError(
            "environment unavailable: latency run did not validate seven transactions\n"
            f"exit {measured.returncode}\n{_redacted(measured.stdout)}\n{_redacted(measured.stderr)}"
        )
    assert report is not None
    for statistic in ("p50", "p95", "maximum"):
        assert isinstance(report[statistic], (int, float)) and not isinstance(
            report[statistic], bool
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
    # T2.5a: the probe measures the real chaincode, not the demo one.
    assert report["chaincode"] == "provenance"
    assert report["contract"] == "Provenance"
    assert report["batchTimeout"] == configured_batch_timeout()
    if outcome == "budget-exceeded":
        assert report["withinBudget"] is False
        assert report["batchTimeoutDecision"] == "set-to-0.5s"
        runs_text = "; ".join(
            f"p50={breach['p50']} p95={breach['p95']} maximum={breach['maximum']}"
            for breach in settled.breaches
        )
        pytest.fail(
            f"budget exceeded in {len(settled.breaches)} runs in a row: {runs_text}; "
            "decision=set-to-0.5s"
        )
    assert outcome == "within-budget"
    assert report["withinBudget"] is True
    assert report["batchTimeoutDecision"] == "keep"
    assert settled.returncode == 0
    if settled.breaches:
        print(
            "LATENCY_RETRY "
            + json.dumps(
                [
                    {key: breach[key] for key in ("p50", "p95", "maximum")}
                    for breach in settled.breaches
                ],
                separators=(",", ":"),
            )
        )
    _assert_a_second_run_is_not_a_duplicate(bash_run)
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


def _assert_a_second_run_is_not_a_duplicate(
    bash_run: Callable[..., CompletedProcess[str]],
) -> None:
    """AUD-057: CreateArtifactRecord refuses an existing artifactId (AC-07.3), so a probe that
    reuses its identifiers works once per network. The wrapper takes whichever branch the host
    allows, so this holds with and without Node on the host."""
    again = bash_run(["fabric/spike-latency.sh"], timeout=600)
    try:
        report: dict[str, object] | None = _json_object(again.stdout)
    except AssertionError:
        report = None
    # Completion, not latency: the budget is judged on the first run.
    assert (
        classify_latency_result(again.returncode, report) != "environment-unavailable"
    ), (
        f"a second run on the same network failed\nexit {again.returncode}\n"
        f"{_redacted(again.stdout)}\n{_redacted(again.stderr)}"
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
    assert (
        classify_latency_result(alone.returncode, report) != "environment-unavailable"
    ), f"exit {alone.returncode}\n{_redacted(alone.stdout)}\n{_redacted(alone.stderr)}"
    assert report["batchTimeout"] == configured_batch_timeout()
    assert "Org1MSP.peer" in str(report["endorsementPolicy"])
    assert "Org2MSP.peer" in str(report["endorsementPolicy"])
