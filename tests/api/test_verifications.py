"""T4.1, HTTP/JWT, PostgreSQL et AES-GCM réels ; Fabric simulé au transport."""

from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.ledger import LedgerClient
from saam.traceability import ArtifactReader
from tests.api.test_cases_create import headers
from tests.verify import test_case_verifier

traceability_case = test_case_verifier.traceability_case
verification_case = test_case_verifier.verification_case

TOKEN = "synthetic-api-verification-token"


@pytest.fixture
def api_verification(auth_service, verification_case):
    _, artifacts, store, fabric, _, _, _ = verification_case
    case_id = artifacts[0].case_id
    effects = {"outage": False, "failed_id": None}
    calls = []
    clients = []

    def transport(request):
        assert request.method == "GET"
        assert request.headers["X-Agent-Token"] == TOKEN
        assert request.headers.get("Authorization") is None
        calls.append(request.url.path)
        identifier = request.url.path.rsplit("/", 1)[-1]
        if effects["outage"] or identifier == effects["failed_id"]:
            raise httpx.ConnectError("Fabric de test indisponible.", request=request)
        if "/ledger/cases/" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    record
                    for record in fabric.records.values()
                    if record["caseId"] == identifier
                ],
            )
        if identifier not in fabric.records:
            return httpx.Response(
                404,
                json={
                    "error": {"code": "NOT_FOUND", "message": "Absent.", "details": {}}
                },
            )
        return httpx.Response(200, json=fabric.records[identifier])

    def factory():
        ledger = LedgerClient(
            "http://test-gateway", TOKEN, transport=httpx.MockTransport(transport)
        )
        clients.append(ledger)
        return ledger

    with TestClient(
        create_app(
            identity=auth_service,
            artifact_reader=ArtifactReader(store),
            ledger_factory=factory,
        ),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as api:
        yield (
            api,
            f"/api/v1/cases/{case_id}/verifications",
            artifacts,
            store,
            fabric,
            effects,
            calls,
        )
    assert all(client._http.is_closed for client in clients)


@pytest.mark.parametrize("role", ["operator", "auditor", "admin"])
def test_create_and_read_history_with_each_role(api_verification, role):
    api, path, artifacts, _, _, effects, calls = api_verification
    auth = headers(api, role)

    empty = api.get(path, headers=auth)
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "page": 1, "size": 20, "total": 0}
    assert calls == []

    created = api.post(path, headers=auth)
    assert created.status_code == 201
    assert created.headers["Cache-Control"] == "no-store"
    result = created.json()
    assert result["case_id"] == artifacts[0].case_id
    assert result["requested_by"] == api.get("/api/v1/me", headers=auth).json()["id"]
    assert (
        result["requested_by_name"]
        == api.get("/api/v1/me", headers=auth).json()["display_name"]
    )
    assert result["completed_at"] >= result["started_at"]
    assert result["ledger_reachable"] is True
    assert result["count_valide"] == 4
    assert [item["artifact_id"] for item in result["items"]] == [
        artifact.id for artifact in artifacts
    ]
    assert len(calls) == 5

    effects["outage"] = True
    history = api.get(path, headers=auth)
    assert history.status_code == 200
    assert history.headers["Cache-Control"] == "no-store"
    assert history.json() == {"items": [result], "page": 1, "size": 20, "total": 1}
    assert len(calls) == 5


def test_four_statuses_and_artifact_present_only_in_fabric(
    api_verification, postgres, migrated_database
):
    api, path, artifacts, store, fabric, _, _ = api_verification
    original, processed, features, prediction = artifacts
    store.write(processed.id, processed.files[0].name, b'{"modified":true}')
    store.path(features.id, features.files[0].name).unlink()
    del fabric.records[prediction.id]
    orphan = str(uuid4())
    fabric.records[orphan] = {
        "artifactId": orphan,
        "caseId": f"CASE-{original.case_id}",
        "artifactType": "validation",
        "offchainRef": f"artifact://{orphan}",
        "sha256": "a" * 64,
    }

    auth = headers(api, "auditor")
    response = api.post(path, headers=auth)
    assert response.status_code == 201
    result = response.json()
    assert [
        result[f"count_{kind}"]
        for kind in ("valide", "modifie", "manquant", "non_verifiable")
    ] == [1, 1, 2, 1]
    first, changed, absent, unanchored, onchain_only = result["items"]
    assert first["computed_sha256"] == first["expected_sha256"]
    assert (
        changed["computed_sha256"]
        and changed["computed_sha256"] != changed["expected_sha256"]
    )
    assert absent["status"] == onchain_only["status"] == "manquant"
    assert onchain_only["artifact_id"] == orphan
    assert unanchored["expected_sha256"] is None
    assert unanchored["status"] == "non_verifiable"
    assert result["ledger_reachable"] is True
    assert api.get(path, headers=auth).json()["items"] == [result]
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        assert db.execute("SELECT count(*) FROM verification_items").fetchone() == (5,)


@pytest.mark.parametrize("after_inventory", [False, True])
def test_outage_is_a_persisted_result(api_verification, after_inventory):
    api, path, artifacts, _, _, effects, _ = api_verification
    if after_inventory:
        effects["failed_id"] = artifacts[-1].id
    else:
        effects["outage"] = True

    auth = headers(api, "operator")
    response = api.post(path, headers=auth)
    assert response.status_code == 201
    result = response.json()
    assert result["ledger_reachable"] is False
    assert result["count_non_verifiable"] == 4
    assert all(
        item["status"] == "non_verifiable" and item["expected_sha256"] is None
        for item in result["items"]
    )
    assert api.get(path, headers=auth).json()["items"] == [result]


def test_history_pagination_and_case_isolation(api_verification, auth_service):
    api, path, _, _, _, _, _ = api_verification
    auth = headers(api, "admin")
    first = api.post(path, headers=auth).json()
    second = api.post(path, headers=auth).json()
    assert first["id"] != second["id"]
    assert api.get(path + "?size=1", headers=auth).json() == {
        "items": [second],
        "total": 2,
        "page": 1,
        "size": 1,
    }
    assert api.get(path + "?size=1&page=2", headers=auth).json()["items"] == [first]
    invalid = api.get(path + "?size=51", headers=auth)
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "BAD_REQUEST"

    with auth_service.connect() as db:
        db.execute(
            """INSERT INTO cases (id,created_by,ecg_format,original_sampling_hz,has_report)
               VALUES (%s,%s,'csv',100,false)""",
            (other := str(uuid4()), first["requested_by"]),
        )
    assert (
        api.get(f"/api/v1/cases/{other}/verifications", headers=auth).json()["total"]
        == 0
    )


def test_auth_and_unknown_case_do_not_contact_fabric(api_verification):
    api, path, _, _, _, _, calls = api_verification
    for method in ("GET", "POST"):
        assert api.request(method, path).status_code == 401
        auth = headers(api, "auditor")
        response = api.request(
            method, f"/api/v1/cases/CASE-{uuid4()}/verifications", headers=auth
        )
        assert response.status_code == 404
    assert calls == []


def test_details_failure_rolls_back_entire_verification(
    api_verification, postgres, migrated_database
):
    api, path, _, _, _, _, _ = api_verification
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        db.execute(
            """ALTER TABLE verification_items
               ADD CONSTRAINT reject_prediction_in_test CHECK (artifact_type <> 'prediction')"""
        )
    auth = headers(api, "auditor")
    response = api.post(path, headers=auth)
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "La vérification a échoué. Réessayer."
    assert api.get(path, headers=auth).json()["total"] == 0
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        assert db.execute("SELECT count(*) FROM verification_items").fetchone() == (0,)
