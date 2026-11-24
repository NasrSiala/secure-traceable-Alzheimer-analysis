"""T3.4 : vrais JWT, multipart, PostgreSQL et transit chiffré."""

import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.storage import ArtifactStore
from saam.traceability import UploadStaging
from tests.api.conftest import PASSWORD

LEADS = "I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6"


def csv_bytes(rows=1000, header=LEADS):
    return (header + "\n" + ("0," * 11 + "0\n") * rows).encode()


@pytest.fixture
def cases_client(auth_service, tmp_path):
    staging = UploadStaging(ArtifactStore(tmp_path / "uploads", os.urandom(32)))
    with TestClient(
        create_app(identity=auth_service, uploads=staging),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as client:
        yield client, staging, auth_service


def headers(client, role="operator"):
    response = client.post(
        "/api/v1/auth/login", json={"email": role + "@demo.test", "password": PASSWORD}
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def submit(client, authorization, *, data=None, files=None):
    return client.post(
        "/api/v1/cases",
        headers=authorization,
        data=data if data is not None else {"csv_sampling_rate": "100"},
        files=files
        if files is not None
        else [("ecg_files[]", ("source.csv", csv_bytes(), "text/csv"))],
    )


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_csv_creation_queues_a_job_and_audit_with_encrypted_files(cases_client, role):
    client, staging, service = cases_client
    response = submit(
        client,
        headers(client, role),
        data={"csv_sampling_rate": "100", "report_text": "Rapport public e\u0301"},
    )
    assert response.status_code == 202
    result = response.json()
    assert result["case_ref"] == "CASE-" + result["id"]
    assert result["status"] == "en_attente"
    assert response.headers["location"] == "/api/v1/cases/" + result["id"]
    metadata, files = staging.read(result["id"])
    assert files["ecg.csv"][1] == csv_bytes()
    assert files["report.txt"][1].decode() == "Rapport public é"
    assert metadata["sampling_hz"] == 100
    assert staging.store.path(result["id"], "ecg.csv").read_bytes() != csv_bytes()
    with psycopg.connect(service.database_url) as db:
        assert db.execute(
            "SELECT status FROM jobs WHERE case_id=%s", (result["id"],)
        ).fetchone() == ("en_file",)
        payload = db.execute(
            "SELECT payload FROM audit_events WHERE case_id=%s AND event_type='case_created'",
            (result["id"],),
        ).fetchone()[0]
        assert payload == {"ecg_format": "csv", "sampling_hz": 100, "has_report": True}


def test_wfdb_pair_is_validated_and_references_are_regenerated(cases_client):
    client, staging, _ = cases_client
    hea = ("source 12 500 5000\n" + "source.dat 16 1000/mV 16 0 0 0 I\n" * 12).encode()
    response = submit(
        client,
        headers(client),
        data={},
        files=[
            ("ecg_files[]", ("source.hea", hea, "text/plain")),
            (
                "ecg_files[]",
                ("source.dat", b"\x00\x01" * 12 * 5000, "application/octet-stream"),
            ),
        ],
    )
    assert response.status_code == 202
    _, files = staging.read(response.json()["id"])
    assert files["ecg.hea"][1].startswith(b"ecg 12 500 5000\n")
    assert b"source.dat" not in files["ecg.hea"][1]
    assert files["ecg.dat"][1] == b"\x00\x01" * 12 * 5000


@pytest.mark.parametrize(
    "rate,message",
    [
        ("", "Fréquence entre 50 et 10 000 Hz."),
        ("49", "Fréquence entre 50 et 10 000 Hz."),
        ("10001", "Fréquence entre 50 et 10 000 Hz."),
        ("100.5", "Fréquence entre 50 et 10 000 Hz."),
    ],
)
def test_sampling_rate_validation(cases_client, rate, message):
    client, staging, _ = cases_client
    result = submit(client, headers(client), data={"csv_sampling_rate": rate})
    assert result.status_code == 400
    assert result.json()["error"]["message"] == message
    assert not staging.store.root.exists()


@pytest.mark.parametrize(
    "content,message",
    [
        (csv_bytes(999), "L'enregistrement doit durer au moins 10 secondes."),
        (csv_bytes(header="I,II"), "Le CSV doit contenir les 12 dérivations (I … V6)."),
        (b"invalid\xff", "Le CSV doit contenir les 12 dérivations (I … V6)."),
    ],
)
def test_csv_shape_and_duration(cases_client, content, message):
    client, _, _ = cases_client
    result = submit(
        client, headers(client), files=[("ecg_files[]", ("x.csv", content, "text/csv"))]
    )
    assert result.status_code == 400
    assert result.json()["error"]["message"] == message


def test_report_length_and_conflicting_inputs(cases_client):
    client, _, _ = cases_client
    authorization = headers(client)
    result = submit(
        client,
        authorization,
        data={"csv_sampling_rate": "100", "report_text": "x" * 10001},
    )
    assert result.status_code == 400
    assert (
        result.json()["error"]["message"]
        == "Rapport trop long (10 000 caractères max)."
    )
    result = submit(
        client,
        authorization,
        data={"csv_sampling_rate": "100", "report_text": "text"},
        files=[
            ("ecg_files[]", ("x.csv", csv_bytes(), "text/csv")),
            ("report_file", ("report.txt", b"public", "text/plain")),
        ],
    )
    assert result.status_code == 400


def test_oversized_body_and_disallowed_extension(cases_client):
    client, _, _ = cases_client
    authorization = headers(client)
    response = client.post(
        "/api/v1/cases",
        headers=authorization,
        content=b"x" * (20 * 1024 * 1024 + 512 * 1024 + 1),
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Taille maximale : 20 Mo."
    assert (
        submit(
            client,
            authorization,
            files=[("ecg_files[]", ("x.exe", b"x", "application/octet-stream"))],
        ).status_code
        == 400
    )


def test_auditor_and_anonymous_cannot_upload(cases_client):
    client, staging, _ = cases_client
    assert submit(client, {}).status_code == 401
    assert submit(client, headers(client, "auditor")).status_code == 403
    assert not staging.store.root.exists()


def test_rollback_removes_new_staging_and_no_case_job_or_event(
    cases_client, monkeypatch
):
    import saam.api.cases as module

    client, staging, service = cases_client

    def fail(*args):
        raise psycopg.OperationalError("synthetic-secret-do-not-echo")

    monkeypatch.setattr(module, "case_created", fail)
    response = submit(client, headers(client))
    assert response.status_code == 503
    assert "synthetic-secret" not in response.text
    assert list(staging.store.root.iterdir()) == []
    with psycopg.connect(service.database_url) as db:
        for table in ["cases", "jobs", "audit_events"]:
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0


def test_limit_of_ten_creations_and_distinct_ids(cases_client):
    client, _, service = cases_client
    authorization = headers(client)
    ids = set()
    for _ in range(10):
        response = submit(client, authorization)
        assert response.status_code == 202
        ids.add(response.json()["id"])
    assert len(ids) == 10
    response = submit(client, authorization)
    assert response.status_code == 429
    assert (
        response.json()["error"]["message"]
        == "Limite de 10 analyses par minute atteinte."
    )
    with psycopg.connect(service.database_url) as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 10


def test_concurrent_submissions_have_separate_cases_and_jobs(cases_client):
    client, _, service = cases_client
    authorization = headers(client)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: submit(client, authorization), range(2)))
    assert all(r.status_code == 202 for r in responses)
    assert responses[0].json()["id"] != responses[1].json()["id"]
    with psycopg.connect(service.database_url) as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2


@pytest.mark.parametrize(
    "files",
    [
        [("ecg_files[]", ("source.hea", b"header", "text/plain"))],
        [
            ("ecg_files[]", ("source.hea", b"header", "text/plain")),
            ("ecg_files[]", ("other.dat", b"data", "application/octet-stream")),
        ],
    ],
)
def test_wfdb_pair_errors_use_the_app_flow_message(cases_client, files):
    client, _, _ = cases_client
    response = submit(client, headers(client), data={}, files=files)
    assert response.status_code == 400
    assert (
        response.json()["error"]["message"]
        == "Fournissez le fichier .hea et le fichier .dat d'un même enregistrement."
    )
