"""Seven-artifact chain: GetCaseHistory returns them parent to child."""

from __future__ import annotations

from collections.abc import Callable
from subprocess import CompletedProcess

import pytest
from fabric_support import assert_ok, report_line

pytestmark = pytest.mark.fabric

PIPELINE = [
    "original",
    "processed",
    "features",
    "prediction",
    "validation",
    "explanation",
    "final_result",
]


def test_case_history_returns_seven_records_parent_to_child(
    bash_run: Callable[..., CompletedProcess[str]],
    _stop_after_test: object,
) -> None:
    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    assert_ok(started, "start")
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert_ok(enrolled, "enroll")

    # Twice on one network: each run writes a case of its own, so the second must pass too.
    for run in ("first", "second"):
        checked = bash_run(["fabric/history-check.sh"], timeout=300)
        assert_ok(checked, f"{run} history")
        report = report_line(checked, "HISTORY_CHECK")
        assert report["count"] == 7, run
        assert report["types"] == PIPELINE, run
        assert report["creatorMspId"] == "Org1MSP", run
        assert report["creatorAgent"] == "ingestion", run
        assert "CN=agent-ingestion" in str(report["creatorId"]), run
        # Another case on the same ledger does not leak into this one, and an unknown case is
        # empty.
        assert report["otherCaseCount"] == 1, run
        assert report["emptyCaseCount"] == 0, run
        # A client that names its own creator is refused by the chaincode and stores nothing.
        assert report["forgedCode"] == "SCHEMA", run
        assert report["forgedStored"] is False, run
