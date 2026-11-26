"""T3.13 : HTTP/JWT, PostgreSQL et fichiers AES réels, données synthétiques."""

import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.hashing import file_hash
from saam.storage import ArtifactStore
from saam.traceability import (
    Artifact,
    ArtifactFile,
    ArtifactReader,
    TraceabilityTool,
    UploadStaging,
    json_file,
)
from tests.api.test_cases_create import headers, submit
from tests.pipeline.test_traceability import MemoryLedger


def npy(array):
    stream = io.BytesIO()
    np.save(stream, array, allow_pickle=False)
    return stream.getvalue()


@pytest.fixture
def read_case(auth_service, postgres, migrated_database, tmp_path):
    store = ArtifactStore(tmp_path / "artifacts", os.urandom(32))
    reader = ArtifactReader(store)
    uploads = UploadStaging(ArtifactStore(tmp_path / "uploads", os.urandom(32)))
    worker_url = postgres.dsn(migrated_database, "app_worker")
    ledger = MemoryLedger()
    tool = TraceabilityTool(
        worker_url, store, ledger, on_failure=lambda _: pytest.fail("Ancrage échoué")
    )
    with TestClient(
        create_app(identity=auth_service, uploads=uploads, artifact_reader=reader),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as client:
        authorization = headers(client)
        case_id = submit(client, authorization).json()["id"]
        array = np.arange(12000, dtype=np.float32).reshape(12, 1000) / 1000
        payloads = {
            "prediction": {
                "predicted_class": "NORM",
                "probabilities": {
                    "NORM": 0.8,
                    "MI": 0.1,
                    "STTC": 0.04,
                    "CD": 0.03,
                    "HYP": 0.03,
                },
            },
            "validation": {
                "decision": "revision_requise",
                "rules": [{"id": "R1", "passed": True}],
            },
            "explanation": {"text": "Exemple synthétique, aucune conclusion clinique."},
            "final_result": {
                "decision": "revision_requise",
                "message": "Prototype pédagogique — pas un diagnostic médical.",
            },
        }
        parent, artifacts = None, {}
        for kind, agent in [
            ("original", "ingestion"),
            ("processed", "preparation"),
            ("features", "features"),
            ("prediction", "prediction"),
            ("validation", "validation"),
            ("explanation", "explanation"),
            ("final_result", "finalization"),
        ]:
            if kind == "original":
                files = (
                    ArtifactFile(
                        "report.txt", "text/plain", b"PRIVATE-SYNTHETIC-REPORT-MARKER"
                    ),
                )
            elif kind == "processed":
                files = (
                    ArtifactFile("signal.npy", "application/octet-stream", npy(array)),
                )
            else:
                files = (
                    json_file(kind + ".json", payloads.get(kind, {"synthetic": True})),
                )
            artifact = Artifact(
                str(uuid4()),
                case_id,
                kind,
                agent,
                datetime(2026, 11, 26, 12, tzinfo=UTC),
                parent_id=parent,
                files=files,
            )
            tool.record(artifact)
            artifacts[kind] = artifact
            parent = artifact.id
            with psycopg.connect(worker_url) as db:
                db.execute(
                    "INSERT INTO agent_logs (case_id,agent,step,status,message,started_at,duration_ms) VALUES (%s,%s,%s,'succes','Étape terminée.',now(),0)",
                    (case_id, agent, agent),
                )
        with psycopg.connect(worker_url) as db:
            db.execute(
                "UPDATE cases SET status='termine',current_step='finalization',decision='revision_requise',predicted_class='NORM',confidence=0.8,quality_score=1,completed_at=now() WHERE id=%s",
                (case_id,),
            )

        def forbidden_read(_):
            pytest.fail("Une lecture d'affichage ne doit pas appeler Fabric.")

        ledger.get_record = forbidden_read
        yield {
            "client": client,
            "store": store,
            "reader": reader,
            "url": worker_url,
            "admin_url": postgres.dsn(migrated_database),
            "id": case_id,
            "artifacts": artifacts,
            "array": array,
            "payloads": payloads,
            "headers": authorization,
        }


@pytest.mark.parametrize("role", ["operator", "auditor", "admin"])
def test_three_roles_read_all_cases_and_local_results(read_case, role):
    setup = read_case
    client, case_id = setup["client"], setup["id"]
    authorization = headers(client, role)
    listing = client.get("/api/v1/cases", headers=authorization)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    summary = listing.json()["items"][0]
    assert summary["id"] == case_id and summary["confidence"] == 0.8
    response = client.get("/api/v1/cases/CASE-" + case_id, headers=authorization)
    assert response.status_code == 200
    result = response.json()
    for kind, expected in setup["payloads"].items():
        assert result[kind] == expected
    assert len(result["artifacts"]) == len(result["steps"]) == 7
    assert all(
        step["status"] == "ancre" and step["tx_id"] == "c" * 64
        for step in result["steps"]
    )
    assert result["created_at"].endswith("Z")
    assert "PRIVATE-SYNTHETIC-REPORT-MARKER" not in response.text
    assert all(
        key not in response.text
        for key in ["storage_path", "manifest_path", "password_hash", "locked_by"]
    )
    assert (
        listing.headers["cache-control"]
        == response.headers["cache-control"]
        == "no-store"
    )
    signal = client.get(
        f"/api/v1/cases/{case_id}/signal?artifact=processed", headers=authorization
    )
    assert signal.status_code == 200
    assert signal.json()["artifact_id"] == setup["artifacts"]["processed"].id


def test_pagination_status_filter_and_stable_sort(auth_client, auth_service):
    authorization = headers(auth_client)
    with psycopg.connect(auth_service.database_url) as db:
        user = db.execute("SELECT id FROM users WHERE role='operator'").fetchone()[0]
        identifiers = sorted(str(uuid4()) for _ in range(3))
        for index, identifier in enumerate(identifiers):
            db.execute(
                "INSERT INTO cases (id,created_by,ecg_format,original_sampling_hz,has_report,status,created_at) VALUES (%s,%s,'csv',100,false,%s,'2026-11-26T12:00:00Z')",
                (identifier, user, "en_cours" if index == 1 else "en_attente"),
            )
    pages = [
        auth_client.get(
            f"/api/v1/cases?page={page}&size=1", headers=authorization
        ).json()
        for page in range(1, 5)
    ]
    assert [page["items"][0]["id"] for page in pages[:3]] == list(reversed(identifiers))
    assert all(page["total"] == 3 for page in pages)
    assert pages[-1]["items"] == []
    filtered = auth_client.get(
        "/api/v1/cases?status=en_cours", headers=authorization
    ).json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == identifiers[1]
    assert (
        auth_client.get("/api/v1/cases?status=termine", headers=authorization).json()[
            "items"
        ]
        == []
    )


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=x",
        "page=1000001",
        "size=0",
        "size=51",
        "status=rejete",
        "status=';DROP TABLE cases;--",
    ],
)
def test_invalid_query_is_safe_french_bad_request(auth_client, query):
    response = auth_client.get("/api/v1/cases?" + query, headers=headers(auth_client))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    assert "DROP TABLE" not in response.text
    assert response.json()["error"]["message"] == "Paramètres de lecture invalides."


def test_waiting_case_empty_results_and_signal_not_ready(auth_client, auth_service):
    authorization = headers(auth_client)
    assert auth_client.get("/api/v1/cases", headers=authorization).json() == {
        "items": [],
        "page": 1,
        "size": 20,
        "total": 0,
    }
    with psycopg.connect(auth_service.database_url) as db:
        user = db.execute("SELECT id FROM users WHERE role='operator'").fetchone()[0]
        case_id = str(
            db.execute(
                "INSERT INTO cases (created_by,ecg_format,original_sampling_hz,has_report) VALUES (%s,'csv',100,false) RETURNING id",
                (user,),
            ).fetchone()[0]
        )
    response = auth_client.get("/api/v1/cases/" + case_id, headers=authorization)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "en_attente" and result["decision"] is None
    assert all(step["status"] == "a_venir" for step in result["steps"])
    assert result["artifacts"] == [] and all(
        result[kind] is None
        for kind in ["prediction", "validation", "explanation", "final_result"]
    )
    signal = auth_client.get(f"/api/v1/cases/{case_id}/signal", headers=authorization)
    assert (
        signal.status_code == 404
        and signal.json()["error"]["code"] == "SIGNAL_UNAVAILABLE"
    )


@pytest.mark.parametrize("identifier", ["missing", "CASE-invalid", str(uuid4())])
def test_missing_case_404_after_authentication(auth_client, identifier):
    authorization = headers(auth_client)
    for suffix in ["", "/signal"]:
        path = "/api/v1/cases/" + identifier + suffix
        assert auth_client.get(path).status_code == 401
        response = auth_client.get(path, headers=authorization)
        assert response.status_code == 404
        assert response.json()["error"] == {
            "code": "NOT_FOUND",
            "message": "Cas introuvable.",
            "details": {},
        }
    assert auth_client.get("/api/v1/cases").status_code == 401


def test_rejection_and_anchor_failure_steps_and_final_result_gate(read_case):
    setup = read_case
    with psycopg.connect(setup["admin_url"]) as db:
        db.execute(
            "UPDATE cases SET status='erreur_ancrage',decision=NULL,current_step='prediction',error_message='Ancrage sur la blockchain impossible — résultat non émis.' WHERE id=%s",
            (setup["id"],),
        )
        db.execute(
            "UPDATE artifacts SET anchor_status='echec',tx_id=NULL,anchored_at=NULL WHERE id=%s",
            (setup["artifacts"]["prediction"].id,),
        )
        db.execute(
            "UPDATE agent_logs SET status='echec' WHERE case_id=%s AND step='prediction'",
            (setup["id"],),
        )
    result = (
        setup["client"]
        .get("/api/v1/cases/" + setup["id"], headers=setup["headers"])
        .json()
    )
    assert (
        result["decision"] is None
        and result["final_result"] is None
        and result["prediction"] is None
    )
    assert result["steps"][3]["status"] == "echec"
    assert result["steps"][3]["tx_id"] is None
    with psycopg.connect(setup["admin_url"]) as db:
        db.execute(
            "UPDATE cases SET status='termine',decision='rejete',current_step='finalization' WHERE id=%s",
            (setup["id"],),
        )
        db.execute(
            "UPDATE agent_logs SET status='ignore' WHERE case_id=%s AND step IN ('validation','explanation')",
            (setup["id"],),
        )
        db.execute(
            "UPDATE artifacts SET anchor_status='en_attente',tx_id=NULL,anchored_at=NULL WHERE id=%s",
            (setup["artifacts"]["final_result"].id,),
        )
    result = (
        setup["client"]
        .get("/api/v1/cases/" + setup["id"], headers=setup["headers"])
        .json()
    )
    assert result["decision"] == "rejete" and result["final_result"] is None


@pytest.mark.parametrize("mode", ["missing", "tag", "reencrypted"])
def test_unreadable_result_returns_503_without_private_content(read_case, mode):
    setup = read_case
    artifact_id = setup["artifacts"]["prediction"].id
    path = setup["store"].path(artifact_id, "prediction.json")
    if mode == "missing":
        path.unlink()
    elif mode == "tag":
        data = path.read_bytes()
        path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    else:
        setup["store"].write(
            artifact_id,
            "prediction.json",
            b'{"secret":"PRIVATE-SYNTHETIC-REPORT-MARKER"}',
        )
    response = setup["client"].get(
        "/api/v1/cases/" + setup["id"], headers=setup["headers"]
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ARTIFACT_UNAVAILABLE"
    assert "PRIVATE-SYNTHETIC" not in response.text and str(path) not in response.text


def test_signal_decimation_values_time_and_units(read_case):
    setup = read_case
    response = setup["client"].get(
        f"/api/v1/cases/CASE-{setup['id']}/signal", headers=setup["headers"]
    )
    result = response.json()
    assert result["unit"] == "z-score" and result["sampling_hz"] == 50
    assert result["source_sampling_hz"] == 100 and result["duration_seconds"] == 10
    assert result["leads"] == [
        "I",
        "II",
        "III",
        "aVR",
        "aVL",
        "aVF",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
    ]
    assert len(result["time_seconds"]) == 500 and result["time_seconds"][-1] == 9.98
    np.testing.assert_array_equal(result["values"], setup["array"][:, ::2])
    assert response.headers["cache-control"] == "no-store"
    assert (
        setup["client"]
        .get(
            f"/api/v1/cases/{setup['id']}/signal?artifact=original",
            headers=setup["headers"],
        )
        .status_code
        == 400
    )


@pytest.mark.parametrize(
    "mode",
    ["object", "huge", "nan", "truncated", "fortran", "bad_json", "overflow_json"],
)
def test_payload_format_validation_without_pickle_or_large_allocation(read_case, mode):
    setup = read_case
    kind, name = (
        ("prediction", "prediction.json")
        if mode in {"bad_json", "overflow_json"}
        else ("processed", "signal.npy")
    )
    artifact_id = setup["artifacts"][kind].id
    if mode == "object":
        stream = io.BytesIO()
        np.save(stream, np.array([["unsafe-object"]], dtype=object))
        encoded = stream.getvalue()
    elif mode == "huge":
        stream = io.BytesIO()
        np.lib.format.write_array_header_1_0(
            stream, {"descr": "<f4", "fortran_order": False, "shape": (12, 10**12)}
        )
        encoded = stream.getvalue()
    elif mode == "nan":
        array = setup["array"].copy()
        array[0, 0] = np.nan
        encoded = npy(array)
    elif mode == "truncated":
        encoded = npy(setup["array"])[:-4]
    elif mode == "fortran":
        encoded = npy(np.asfortranarray(setup["array"]))
    else:
        encoded = (
            b'{"probability":NaN}' if mode == "bad_json" else b'{"probability":1e400}'
        )
    setup["store"].write(artifact_id, name, encoded)
    # Injection de corruption dans la base temporaire ; aucun droit modifié.
    with psycopg.connect(setup["admin_url"]) as db:
        db.execute(
            "UPDATE artifact_files SET sha256=%s,size_bytes=%s WHERE artifact_id=%s AND name=%s",
            (file_hash(encoded), len(encoded), artifact_id, name),
        )
    suffix = "" if kind == "prediction" else "/signal"
    response = setup["client"].get(
        f"/api/v1/cases/{setup['id']}{suffix}", headers=setup["headers"]
    )
    assert response.status_code == (200 if mode == "fortran" else 503)
    if mode == "fortran":
        np.testing.assert_array_equal(response.json()["values"], setup["array"][:, ::2])


def test_database_unavailable_safe_service_error(read_case):
    setup = read_case
    setup[
        "client"
    ].app.state.cases.database_url = (
        "host=127.0.0.1 port=1 dbname=absent connect_timeout=1"
    )
    for path in [
        "/api/v1/cases",
        f"/api/v1/cases/{setup['id']}",
        f"/api/v1/cases/{setup['id']}/signal",
    ]:
        response = setup["client"].get(path, headers=setup["headers"])
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert "port=1" not in response.text


def test_detail_p95_under_300ms_with_five_concurrent_readers(read_case):
    setup = read_case
    path = "/api/v1/cases/" + setup["id"]

    with setup["client"].app.state.identity.connect() as db:
        # Deux comptes synthétiques de plus, avec le même mot de passe de test.
        for index in (4, 5):
            db.execute(
                "INSERT INTO users (email,password_hash,display_name,role) SELECT %s,password_hash,%s,'operator' FROM users WHERE email='operator@demo.test'",
                (f"reader{index}@demo.test", f"Lecteur {index}"),
            )
    authorizations = [
        headers(setup["client"], name)
        for name in ["operator", "auditor", "admin", "reader4", "reader5"]
    ]

    def read_batch(authorization):
        timings = []
        for _ in range(100):
            started = time.perf_counter()
            response = setup["client"].get(path, headers=authorization)
            assert response.status_code == 200
            assert response.json()["final_result"] == setup["payloads"]["final_result"]
            timings.append((time.perf_counter() - started) * 1000)
        return timings

    with ThreadPoolExecutor(5) as pool:
        timings = sorted(
            value for batch in pool.map(read_batch, authorizations) for value in batch
        )
    p95 = timings[474]
    print(
        json.dumps(
            {
                "T3.13": "GET detail",
                "requests": 500,
                "concurrency": 5,
                "p95_ms": round(p95, 3),
            }
        )
    )
    assert p95 <= 300


def test_read_openapi_contract_has_authentication_and_bounds(auth_client):
    schema = auth_client.app.openapi()
    for path in [
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/signal",
    ]:
        route = schema["paths"][path]["get"]
        assert route["security"] == [{"HTTPBearer": []}]
        assert (
            "$ref" in route["responses"]["200"]["content"]["application/json"]["schema"]
        )
    parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"]["/api/v1/cases"]["get"]["parameters"]
    }
    assert parameters["size"]["maximum"] == 50 and parameters["page"]["minimum"] == 1


def test_partial_case_marks_current_failed_and_skipped_steps(
    auth_client, auth_service, postgres, migrated_database
):
    authorization = headers(auth_client)
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        user = db.execute("SELECT id FROM users WHERE role='operator'").fetchone()[0]
        case_id = str(
            db.execute(
                "INSERT INTO cases (created_by,ecg_format,original_sampling_hz,has_report,status,current_step) VALUES (%s,'csv',100,false,'en_cours','preparation') RETURNING id",
                (user,),
            ).fetchone()[0]
        )
    path = "/api/v1/cases/" + case_id
    detail = auth_client.get(path, headers=authorization).json()
    assert (
        detail["steps"][1]["status"] == "en_cours"
        and detail["steps"][2]["status"] == "a_venir"
    )
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        db.execute(
            "INSERT INTO agent_logs (case_id,agent,step,status,message,started_at,duration_ms) VALUES (%s,'preparation','preparation','echec','Étape interrompue.',now(),0)",
            (case_id,),
        )
        db.execute(
            "INSERT INTO agent_logs (case_id,agent,step,status,message,started_at,duration_ms) VALUES (%s,'features','features','ignore','Étape non exécutée.',now(),0)",
            (case_id,),
        )
        db.execute(
            "UPDATE cases SET current_step='finalization' WHERE id=%s", (case_id,)
        )
    detail = auth_client.get(path, headers=authorization).json()
    assert (
        detail["steps"][1]["status"] == "echec"
        and detail["steps"][2]["status"] == "non_execute"
    )
    assert detail["steps"][-1]["status"] == "en_cours"
    assert detail["final_result"] is None and detail["decision"] is None
