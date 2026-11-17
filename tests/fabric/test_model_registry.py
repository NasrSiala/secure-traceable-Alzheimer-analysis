"""Model registry on the test network: RegisterModel and GetModel with the real certificates."""

from __future__ import annotations

from collections.abc import Callable
from subprocess import CompletedProcess

import pytest
from fabric_support import assert_ok, report_line

pytestmark = pytest.mark.fabric


def test_model_admin_registers_and_every_identity_reads(
    bash_run: Callable[..., CompletedProcess[str]],
    _stop_after_test: object,
) -> None:
    started = bash_run(["fabric/network.sh", "start"], timeout=420)
    assert_ok(started, "start")
    enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
    assert_ok(enrolled, "enroll")

    # Twice on one network: each run registers a model name of its own, so the second must
    # pass too (RegisterModel refuses an existing name and version).
    for run in ("first", "second"):
        checked = bash_run(["fabric/model-check.sh"], timeout=300)
        assert_ok(checked, f"{run} model check")
        report = report_line(checked, "MODEL_CHECK")
        # AC-04.3: the identity with role=model-admin registers, and the subject is the
        # certificate's, not the client's.
        assert report["docType"] == "model", run
        assert "CN=model-admin" in str(report["registeredBy"]), run
        assert report["registeredAt"], run
        # The record reads back as stored, for the admin and for identities without the role
        # (the verifier of Org2, an agent of Org1).
        assert report["readBack"] is True, run
        assert report["readByVerifier"] is True, run
        assert report["readByAgent"] is True, run
        # A second registration of the same name and version is refused and changes nothing.
        assert report["duplicateCode"] == "DUPLICATE", run
        assert report["duplicateChangedRecord"] is False, run
        # Only role=model-admin registers: nothing is stored for the refused callers.
        assert report["verifierCode"] == "FORBIDDEN", run
        assert report["agentCode"] == "FORBIDDEN", run
        assert report["refusedStored"] is False, run
        # Closed schema (NFR-03): an extra field is refused and nothing is stored.
        assert report["extraFieldCode"] == "SCHEMA", run
        assert report["extraFieldStored"] is False, run
        # A model that was never registered is a typed error, and a malformed lookup a schema one.
        assert report["absentCode"] == "NOT_FOUND", run
        assert report["malformedCode"] == "SCHEMA", run
