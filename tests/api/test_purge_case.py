"""Purge admin sur PostgreSQL et vérification après suppression physique."""

from uuid import uuid4

import httpx
import psycopg
import pytest

from saam.cases import CaseService, InvalidTransition
from saam.identity.auth import AuthError
from saam.ledger import LedgerClient
from saam.storage import ArtifactStore
from saam.traceability import UploadStaging
from scripts.purge_case import purge_case, verify_purged
from tests.api import test_verifications
from tests.api.conftest import PASSWORD
from tests.api.test_cases_create import headers

api_verification = test_verifications.api_verification
verification_case = test_verifications.verification_case
traceability_case = test_verifications.traceability_case


def test_admin_purge_cascades_and_fabric_reports_missing(
    api_verification,
    auth_service,
    postgres,
    migrated_database,
    tmp_path,
):
    api, path, artifacts, store, fabric, _, _ = api_verification
    case_id = artifacts[0].case_id
    reference = f"CASE-{case_id}"
    uploads = UploadStaging(ArtifactStore(tmp_path / "uploads", b"x" * 32))
    uploads.stage(case_id, {"report.txt": ("text/plain", b"public synthetic")}, {})
    neighbor = str(uuid4())
    store.write(neighbor, "proof.json", b"unrelated")
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        db.execute(
            "UPDATE cases SET status='termine', decision='revision_requise',completed_at=now() WHERE id=%s",
            (case_id,),
        )
    auth = headers(api, "auditor")
    assert api.post(path, headers=auth).status_code == 201
    admin = auth_service.login("admin@demo.test", PASSWORD, "127.0.0.3").user
    cases = CaseService(auth_service.database_url)
    before = dict(fabric.records)

    assert purge_case(cases, admin, reference, store, uploads) == 4
    assert not uploads.store.path(case_id, "upload.json").parent.exists()
    assert all(
        not store.path(artifact.id, "manifest.json").parent.exists()
        for artifact in artifacts
    )
    assert store.read(neighbor, "proof.json") == b"unrelated"
    assert api.get(f"/api/v1/cases/{case_id}", headers=auth).status_code == 404
    assert fabric.records == before

    def history(request):
        assert (
            request.method == "GET" and request.url.path == f"/ledger/cases/{reference}"
        )
        return httpx.Response(200, json=list(fabric.records.values()))

    with LedgerClient(
        "http://test-gateway",
        "synthetic-verifier-token",
        transport=httpx.MockTransport(history),
    ) as ledger:
        statuses = verify_purged(cases, store, ledger, reference)
    assert [row["artifact_id"] for row in statuses] == [
        artifact.id for artifact in artifacts
    ]
    assert all(row["status"] == "manquant" for row in statuses)
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        assert db.execute("SELECT count(*) FROM verifications").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM verification_items").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM artifacts").fetchone() == (0,)
        events = db.execute(
            """SELECT actor_user_id::text, case_id, payload FROM audit_events
               WHERE event_type='case_purged'"""
        ).fetchall()
    assert events == [(admin.id, None, {"case_id": case_id, "nb_artefacts": 4})]


def test_purge_rejects_non_admin_and_active_processing(
    api_verification, auth_service, tmp_path
):
    _, _, artifacts, store, _, _, _ = api_verification
    case_id = artifacts[0].case_id
    uploads = UploadStaging(ArtifactStore(tmp_path / "uploads", b"x" * 32))
    cases = CaseService(auth_service.database_url)
    auditor = auth_service.login("auditor@demo.test", PASSWORD, "127.0.0.3").user
    admin = auth_service.login("admin@demo.test", PASSWORD, "127.0.0.4").user

    with pytest.raises(AuthError, match="Action non autorisée"):
        purge_case(cases, auditor, case_id, store, uploads)
    with pytest.raises(InvalidTransition, match="terminé"):
        purge_case(cases, admin, case_id, store, uploads)
    assert all(
        store.path(artifact.id, "manifest.json").exists() for artifact in artifacts
    )
