"""History and model routes through the gateway on the test network (T2.6, 2/2)."""

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


def test_five_routes_history_and_model_registry_with_real_certificates(
    bash_run: Callable[..., CompletedProcess[str]],
    _stop_after_test: object,
) -> None:
    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    assert_ok(started, "start")
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert_ok(enrolled, "enroll")

    # Twice on one network: each run writes a case and a model name of its own, so the second
    # must pass too (the ledger refuses an existing artifactId, and a model name and version).
    for run in ("first", "second"):
        checked = bash_run(["fabric/gateway-routes-check.sh"], timeout=300)
        assert_ok(checked, f"{run} routes check")
        report = report_line(checked, "ROUTES_CHECK")
        # POST and GET /ledger/artifacts, then GET /ledger/cases/{caseId}: seven artifacts,
        # parent to child, and nothing from another case.
        assert report["created"] == 7, run
        assert report["artifactRead"] == 200, run
        assert report["history"] == 200, run
        assert report["count"] == 7, run
        assert report["types"] == PIPELINE, run
        assert report["parentsOk"] is True, run
        assert report["verifierHistory"] == 200, run
        assert report["emptyCaseCount"] == 0, run
        assert report["badCase"] == 400, run
        assert report["badCaseCode"] == "SCHEMA", run
        # POST /ledger/models without role=model-admin is 403 FORBIDDEN (AC-04.3, IF-09), for an
        # agent of Org1 and for the verifier of Org2, and stores nothing.
        assert report["agentRegistration"] == 403, run
        assert report["agentRegistrationCode"] == "FORBIDDEN", run
        assert report["verifierRegistration"] == 403, run
        assert report["verifierRegistrationCode"] == "FORBIDDEN", run
        assert report["refusedStored"] is False, run
        # With role=model-admin the model is registered, signed by the certificate's subject, and
        # every identity reads it back as stored.
        assert report["registration"] == 200, run
        assert report["docType"] == "model", run
        assert "CN=model-admin" in str(report["registeredBy"]), run
        assert report["read"] == 200, run
        assert report["readBack"] is True, run
        assert report["readByVerifier"] is True, run
        assert report["readByAgent"] is True, run
        # A duplicate is 409 and changes nothing; an absent version is 404; an extra field is 400
        # and stores nothing; an unknown token is 401.
        assert report["duplicate"] == 409, run
        assert report["duplicateCode"] == "DUPLICATE", run
        assert report["duplicateChangedRecord"] is False, run
        assert report["missing"] == 404, run
        assert report["missingCode"] == "NOT_FOUND", run
        assert report["extraField"] == 400, run
        assert report["extraFieldCode"] == "SCHEMA", run
        assert report["extraFieldStored"] is False, run
        assert report["unauthorized"] == 401, run
        assert report["unauthorizedCode"] == "UNAUTHORIZED", run
        # Every refusal has the normalized envelope, and no token comes back in it.
        assert report["shape"] is True, run
        assert report["tokenLeaked"] is False, run
