"""T4.2 : API/JWT/PostgreSQL réels et transport Fabric remplaçable pour les pannes."""

import copy
import threading
import time
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.ledger import LedgerClient
from tests.api.test_cases_create import headers

MESSAGE = "Registre blockchain injoignable — historique indisponible. Réessayer."
STAGES = [
    ("original", "ingestion"),
    ("processed", "preparation"),
    ("features", "features"),
    ("prediction", "prediction"),
    ("validation", "validation"),
    ("explanation", "explanation"),
    ("final_result", "finalization"),
]
SERVICE_TOKEN = "verifier-test-token-0123456789"


def records(case_id):
    parent, chain, receipts = None, [], {}
    for index, (kind, agent) in enumerate(STAGES):
        identifier = str(uuid4())
        chain.append(
            {
                "docType": "artifact",
                "artifactId": identifier,
                "caseId": "CASE-" + case_id,
                "artifactType": kind,
                "sha256": f"{index + 1:064x}",
                "createdAt": "2026-11-26T12:00:00Z",
                # L'horloge peut reculer ; l'ordre doit suivre les parents.
                "txTimestamp": f"2026-11-26T12:00:0{6 - index}Z",
                "softwareVersion": "0.1.0",
                "modelVersion": "1.0.0",
                "parentArtifactId": parent,
                "offchainRef": "artifact://" + identifier,
                "creatorMspId": "Org1MSP",
                "creatorId": "/CN=agent-" + agent,
                "creatorAgent": agent,
            }
        )
        receipts[identifier] = uuid4().hex * 2
        parent = identifier
    return chain, receipts


@pytest.fixture
def history_client(auth_service, postgres, migrated_database):
    with auth_service.connect() as db:
        user = db.execute("SELECT id FROM users WHERE role='operator'").fetchone()["id"]
        case_id = str(
            db.execute(
                "INSERT INTO cases (created_by,ecg_format,original_sampling_hz,has_report) VALUES (%s,'csv',100,false) RETURNING id",
                (user,),
            ).fetchone()["id"]
        )
    chain, receipts = records(case_id)
    setup = {
        "id": case_id,
        "chain": chain,
        "receipts": receipts,
        "requests": [],
        "clients": [],
        "mode": None,
        "admin_url": postgres.dsn(migrated_database),
    }

    def transport(request):
        setup["requests"].append(request)
        mode = setup["mode"]
        if mode == "connect":
            raise httpx.ConnectError("PRIVATE-ERROR-token", request=request)
        if mode == "timeout":
            raise httpx.ReadTimeout("PRIVATE-ERROR-token", request=request)
        if mode in {401, 403, 404, 502}:
            code = {
                401: "UNAUTHORIZED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                502: "UNAVAILABLE",
            }[mode]
            return httpx.Response(
                mode,
                json={
                    "error": {
                        "code": code,
                        "message": "PRIVATE-ERROR-token",
                        "details": {},
                    }
                },
            )
        if mode == "html":
            return httpx.Response(200, text="PRIVATE-ERROR-token")
        if "/ledger/cases/" in request.url.path:
            return httpx.Response(200, json=setup["chain"])
        identifier = request.url.path.rsplit("/", 1)[-1]
        item = next(row for row in setup["chain"] if row["artifactId"] == identifier)
        if mode == "receipt_missing":
            return httpx.Response(200, json=item)
        if mode == "receipt_changed":
            item = item | {"sha256": "a" * 64}
        if mode == "receipt_failure":
            return httpx.Response(
                502,
                json={
                    "error": {
                        "code": "UNAVAILABLE",
                        "message": "PRIVATE-ERROR-token",
                        "details": {},
                    }
                },
            )
        return httpx.Response(
            200,
            json=item,
            headers={"X-Fabric-Transaction-Id": setup["receipts"][identifier]},
        )

    def factory():
        client = LedgerClient(
            "http://test-gateway",
            SERVICE_TOKEN,
            transport=httpx.MockTransport(transport),
        )
        setup["clients"].append(client)
        return client

    with TestClient(
        create_app(identity=auth_service, ledger_factory=factory),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as client:
        setup["client"] = client
        setup["headers"] = headers(client)
        yield setup
    assert all(client._http.is_closed for client in setup["clients"])


@pytest.mark.parametrize("role", ["operator", "auditor", "admin"])
@pytest.mark.parametrize("prefix", ["", "CASE-"])
def test_three_roles_read_fabric_parent_order_and_receipts(
    history_client, role, prefix
):
    setup = history_client
    response = setup["client"].get(
        f"/api/v1/cases/{prefix}{setup['id']}/history",
        headers=headers(setup["client"], role),
    )
    assert response.status_code == 200
    result = response.json()
    assert result == [
        row | {"txId": setup["receipts"][row["artifactId"]]} for row in setup["chain"]
    ]
    assert len({item["txId"] for item in result}) == 7
    assert response.headers["cache-control"] == "no-store"
    assert len(setup["requests"]) == 8
    assert setup["requests"][0].url.path == "/ledger/cases/CASE-" + setup["id"]
    assert all(
        request.headers["X-Agent-Token"] == SERVICE_TOKEN
        and "Authorization" not in request.headers
        for request in setup["requests"]
    )
    assert all(client._http.is_closed for client in setup["clients"])


def test_sql_artifact_copy_is_never_used_as_fabric_fallback(history_client):
    setup = history_client
    artifact_id = setup["chain"][0]["artifactId"]
    with psycopg.connect(setup["admin_url"]) as db:
        db.execute(
            "INSERT INTO artifacts (id,case_id,type,sha256,manifest_path,offchain_ref,created_by_agent,software_version,anchor_status,tx_id,anchored_at) VALUES (%s,%s,'original',%s,'private-path',%s,'ingestion','sql-stale','ancre',%s,now())",
            (artifact_id, setup["id"], "f" * 64, "artifact://" + artifact_id, "b" * 64),
        )
    path = f"/api/v1/cases/{setup['id']}/history"
    response = setup["client"].get(path, headers=setup["headers"])
    assert response.json()[0]["sha256"] == setup["chain"][0]["sha256"]
    assert response.json()[0]["txId"] == setup["receipts"][artifact_id]
    assert "sql-stale" not in response.text
    setup["mode"] = "connect"
    assert setup["client"].get(path, headers=setup["headers"]).status_code == 502


def test_empty_and_partial_history_are_live_fabric_results(history_client):
    setup = history_client
    path = f"/api/v1/cases/{setup['id']}/history"
    saved = list(setup["chain"])
    setup["chain"] = []
    response = setup["client"].get(path, headers=setup["headers"])
    assert response.status_code == 200 and response.json() == []
    setup["chain"] = saved[:2]
    response = setup["client"].get(path, headers=setup["headers"])
    assert len(response.json()) == 2
    setup["chain"] = saved
    response = setup["client"].get(path, headers=setup["headers"])
    assert len(response.json()) == 7


@pytest.mark.parametrize("identifier", ["not-a-case", "CASE-invalid", str(uuid4())])
def test_unknown_case_before_any_fabric_access(history_client, identifier):
    setup = history_client
    response = setup["client"].get(
        f"/api/v1/cases/{identifier}/history", headers=setup["headers"]
    )
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "Cas introuvable.",
        "details": {},
    }
    assert setup["requests"] == setup["clients"] == []


def test_session_and_disabled_account_checked_before_fabric(history_client):
    setup = history_client
    client, path = setup["client"], f"/api/v1/cases/{setup['id']}/history"
    assert client.get(path).status_code == 401
    assert (
        client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    )
    with psycopg.connect(setup["admin_url"]) as db:
        db.execute("UPDATE users SET is_active=false WHERE role='operator'")
    assert client.get(path, headers=setup["headers"]).status_code == 403
    assert setup["requests"] == setup["clients"] == []


@pytest.mark.parametrize(
    "mode",
    [
        "connect",
        "timeout",
        "html",
        401,
        403,
        404,
        502,
        "receipt_missing",
        "receipt_changed",
        "receipt_failure",
    ],
)
def test_unavailable_ledger_and_receipts_return_safe_502(history_client, mode):
    setup = history_client
    setup["mode"] = mode
    response = setup["client"].get(
        f"/api/v1/cases/{setup['id']}/history", headers=setup["headers"]
    )
    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "LEDGER_UNAVAILABLE",
        "message": MESSAGE,
        "details": {},
    }
    assert "PRIVATE-ERROR" not in response.text
    assert SERVICE_TOKEN not in response.text
    assert all(client._http.is_closed for client in setup["clients"])


@pytest.mark.parametrize(
    "mode",
    [
        "other_case",
        "duplicate",
        "child_first",
        "extra_phi",
        "invalid_hash",
        "invalid_time",
    ],
)
def test_incoherent_history_is_not_presented_as_provenance(history_client, mode):
    setup = history_client
    chain = copy.deepcopy(setup["chain"])
    if mode == "other_case":
        chain[0]["caseId"] = "CASE-" + str(uuid4())
    elif mode == "duplicate":
        chain.append(chain[0])
    elif mode == "child_first":
        chain[0], chain[1] = chain[1], chain[0]
    elif mode == "extra_phi":
        chain[0]["patientName"] = "PRIVATE-SYNTHETIC-PHI"
    elif mode == "invalid_hash":
        chain[0]["sha256"] = "not-a-hash"
    else:
        chain[0]["txTimestamp"] = "2026-11-26T12:00:00"
    setup["chain"] = chain
    response = setup["client"].get(
        f"/api/v1/cases/{setup['id']}/history", headers=setup["headers"]
    )
    assert (
        response.status_code == 502 and response.json()["error"]["message"] == MESSAGE
    )
    assert "PRIVATE-SYNTHETIC-PHI" not in response.text


def test_missing_verifier_configuration_is_safe_502(history_client, monkeypatch):
    setup = history_client

    def missing(_):
        assert _ == "verifier"
        raise ValueError("PRIVATE-CONFIG")

    monkeypatch.setattr(LedgerClient, "from_environment", missing)
    with TestClient(
        create_app(identity=setup["client"].app.state.identity),
        base_url="https://testserver",
    ) as client:
        response = client.get(
            f"/api/v1/cases/{setup['id']}/history", headers=setup["headers"]
        )
    assert response.status_code == 502 and "PRIVATE-CONFIG" not in response.text


def test_total_timeout_closes_client_and_stops_receipt_requests(
    history_client, monkeypatch
):
    setup = history_client
    monkeypatch.setattr("saam.api.history.HISTORY_TIMEOUT", 0.1)
    completed = threading.Event()

    def slow(request):
        setup["requests"].append(request)
        time.sleep(0.4)
        completed.set()
        return httpx.Response(200, json=setup["chain"])

    # Remplacer uniquement le transport du client créé pour cette requête.
    original_init = LedgerClient.__init__

    def init(client, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(slow)
        original_init(client, *args, **kwargs)

    monkeypatch.setattr(LedgerClient, "__init__", init)
    started = time.monotonic()
    response = setup["client"].get(
        f"/api/v1/cases/{setup['id']}/history", headers=setup["headers"]
    )
    assert response.status_code == 502 and time.monotonic() - started < 0.35
    assert completed.wait(2)
    for _ in range(100):
        if all(client._http.is_closed for client in setup["clients"]):
            break
        time.sleep(0.01)
    assert len(setup["requests"]) == 1
    assert all(client._http.is_closed for client in setup["clients"])


def test_database_error_and_openapi_contract(history_client, monkeypatch):
    setup = history_client
    app = setup["client"].app
    route = app.openapi()["paths"]["/api/v1/cases/{case_id}/history"]["get"]
    assert route["security"] == [{"HTTPBearer": []}]
    assert (
        route["responses"]["200"]["content"]["application/json"]["schema"]["type"]
        == "array"
    )

    def database_error(_):
        raise psycopg.OperationalError("PRIVATE-DATABASE")

    monkeypatch.setattr(app.state.cases, "get_case", database_error)
    response = setup["client"].get(
        f"/api/v1/cases/{setup['id']}/history", headers=setup["headers"]
    )
    assert response.status_code == 503 and "PRIVATE-DATABASE" not in response.text
    assert setup["requests"] == []
