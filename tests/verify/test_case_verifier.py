"""Contrat IF-08 avec PostgreSQL, artefacts AES-GCM et client HTTP Fabric."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import httpx
import psycopg
import pytest

from saam.cases import CaseNotFound, CaseService
from saam.hashing import canonical_manifest, file_hash
from saam.ledger import LedgerClient
from saam.traceability import ArtifactFile, ArtifactReader
from saam.verification import CaseVerifier, service
from tests.pipeline import test_traceability

TOKEN = "synthetic-test-verifier-token"
traceability_case = test_traceability.setup


@pytest.fixture
def verification_case(traceability_case):
    tool, fabric, store, original, worker_url, _, _ = traceability_case
    original = replace(
        original,
        files=(*original.files, ArtifactFile("report.txt", "text/plain", b"Synthetic")),
    )
    artifacts = [original]
    for kind, agent in (
        ("processed", "preparation"),
        ("features", "features"),
        ("prediction", "prediction"),
    ):
        artifacts.append(
            replace(
                original,
                id=str(uuid4()),
                type=kind,
                agent=agent,
                parent_id=artifacts[-1].id,
                created_at=original.created_at + timedelta(seconds=len(artifacts)),
                files=(ArtifactFile(f"{kind}.json", "application/json", b"{}"),),
            )
        )
    for artifact in artifacts:
        tool.record(artifact)

    reads = []
    missing = set()
    failed = set()

    def evaluate(request):
        assert request.method == "GET"
        assert request.headers["X-Agent-Token"] == TOKEN
        assert request.url.path.startswith("/ledger/artifacts/")
        artifact_id = request.url.path.rsplit("/", 1)[-1]
        reads.append(artifact_id)
        if artifact_id in failed:
            raise httpx.ConnectError("Passerelle indisponible", request=request)
        if artifact_id in missing:
            return httpx.Response(
                404,
                json={
                    "error": {"code": "NOT_FOUND", "message": "Absent", "details": {}}
                },
            )
        return httpx.Response(200, json=fabric.records[artifact_id])

    with LedgerClient(
        "http://test-gateway", TOKEN, transport=httpx.MockTransport(evaluate)
    ) as ledger:
        verifier = CaseVerifier(CaseService(worker_url), ArtifactReader(store), ledger)
        yield verifier, artifacts, store, fabric, missing, failed, reads


def test_r5_reads_four_ancestors_with_worker_permissions(
    verification_case, postgres, migrated_database
):
    verifier, artifacts, _, fabric, _, _, reads = verification_case
    results = verifier.verify_case(f"CASE-{artifacts[0].case_id}", persist=False)

    assert reads == [artifact.id for artifact in artifacts]
    assert [(item.artifact_id, item.artifact_type) for item in results] == [
        (artifact.id, artifact.type) for artifact in artifacts
    ]
    for item in results:
        assert item.status == "valide"
        assert (
            item.expected_sha256
            == item.computed_sha256
            == fabric.records[item.artifact_id]["sha256"]
        )
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        assert db.execute("SELECT count(*) FROM verifications").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM verification_items").fetchone() == (0,)


def test_four_statuses_in_one_pass(verification_case):
    verifier, artifacts, store, _, missing, _, reads = verification_case
    _, modified, absent, unanchored = artifacts
    path = store.path(modified.id, modified.files[0].name)
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    store.path(absent.id, absent.files[0].name).unlink()
    store.path(unanchored.id, "manifest.json").unlink()
    missing.add(unanchored.id)

    results = verifier.verify_case(artifacts[0].case_id)
    assert [item.status for item in results] == [
        "valide",
        "modifie",
        "manquant",
        "non_verifiable",
    ]
    assert results[2].expected_sha256 is not None
    assert results[2].computed_sha256 is None
    assert results[3].expected_sha256 is None
    assert reads == [artifact.id for artifact in artifacts]


@pytest.mark.parametrize("filename", ["ecg.csv", "report.txt", "manifest.json"])
def test_missing_encrypted_file_is_missing(verification_case, filename):
    verifier, artifacts, store, _, _, _, _ = verification_case
    original = artifacts[0]
    store.path(original.id, filename).unlink()

    assert [item.status for item in verifier.verify_case(original.case_id)] == [
        "manquant",
        "valide",
        "valide",
        "valide",
    ]


@pytest.mark.parametrize("rewrite_manifest", [False, True])
def test_reencrypted_payload_and_altered_sql_copy_still_fail(
    verification_case, postgres, migrated_database, rewrite_manifest
):
    verifier, artifacts, store, fabric, _, _, _ = verification_case
    original = artifacts[0]
    new_data = b"new synthetic ECG!!!"
    assert len(new_data) == len(original.files[0].data)
    store.write(original.id, original.files[0].name, new_data)
    modified = replace(
        original, files=(replace(original.files[0], data=new_data), *original.files[1:])
    )
    if rewrite_manifest:
        store.write(
            original.id, "manifest.json", canonical_manifest(modified.manifest())
        )
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        db.execute(
            "UPDATE artifacts SET sha256=%s WHERE id=%s",
            (file_hash(canonical_manifest(modified.manifest())), original.id),
        )
        db.execute(
            "UPDATE artifact_files SET sha256=%s WHERE artifact_id=%s",
            (file_hash(new_data), original.id),
        )

    results = verifier.verify_case(original.case_id)
    assert [item.status for item in results] == [
        "modifie",
        "valide",
        "valide",
        "valide",
    ]
    assert results[0].expected_sha256 == fabric.records[original.id]["sha256"]


def test_authentic_manifest_remains_authoritative_when_sql_descriptors_disagree(
    verification_case, postgres, migrated_database
):
    verifier, artifacts, _, _, _, _, _ = verification_case
    original = artifacts[0]
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        db.execute(
            "UPDATE artifacts SET sha256=%s WHERE id=%s", ("0" * 64, original.id)
        )
        db.execute("DELETE FROM artifact_files WHERE artifact_id=%s", (original.id,))

    assert all(
        item.status == "valide" for item in verifier.verify_case(original.case_id)
    )


@pytest.mark.parametrize("plaintext", [b"not JSON", b"{}"])
def test_manifest_reencrypted_with_invalid_content_is_modified(
    verification_case, plaintext
):
    verifier, artifacts, store, _, _, _, _ = verification_case
    original = artifacts[0]
    store.write(original.id, "manifest.json", plaintext)

    assert [item.status for item in verifier.verify_case(original.case_id)] == [
        "modifie",
        "valide",
        "valide",
        "valide",
    ]


@pytest.mark.parametrize(
    "field", ["artifactId", "caseId", "artifactType", "offchainRef", "sha256"]
)
def test_incoherent_fabric_record_is_not_verifiable(verification_case, field):
    verifier, artifacts, _, fabric, _, _, _ = verification_case
    original = artifacts[0]
    fabric.records[original.id][field] = "incoherent"

    results = verifier.verify_case(original.case_id)
    assert [item.status for item in results] == [
        "non_verifiable",
        "valide",
        "valide",
        "valide",
    ]
    assert results[0].expected_sha256 is None


def test_reencrypted_noncanonical_manifest_is_modified(verification_case):
    verifier, artifacts, store, _, _, _, _ = verification_case
    original = artifacts[0]
    canonical = store.read(original.id, "manifest.json")
    store.write(original.id, "manifest.json", canonical + b" ")

    result, *_ = verifier.verify_case(original.case_id)
    assert result.status == "modifie"


def test_fabric_budget_is_shared_across_artifacts(verification_case, monkeypatch):
    verifier, artifacts, _, _, _, _, reads = verification_case
    times = iter([100.0, 101.0, 102.0, 111.0, 112.0])
    monkeypatch.setattr(service, "monotonic", lambda: next(times))

    results = verifier.verify_case(artifacts[0].case_id)
    assert [item.status for item in results] == [
        "valide",
        "valide",
        "non_verifiable",
        "non_verifiable",
    ]
    assert reads == [artifact.id for artifact in artifacts[:2]]


def test_fabric_outage_is_reported_for_each_artifact(verification_case):
    verifier, artifacts, _, _, _, failed, reads = verification_case
    failed.update(artifact.id for artifact in artifacts)

    results = verifier.verify_case(artifacts[0].case_id)
    assert [item.status for item in results] == ["non_verifiable"] * 4
    assert reads == [artifact.id for artifact in artifacts]
    assert all(item.expected_sha256 is None for item in results)


@pytest.mark.parametrize(
    "case_id", ["invalide", "CASE-00000000-0000-0000-0000-000000000000"]
)
def test_unknown_case_does_not_call_fabric(verification_case, case_id):
    verifier, _, _, _, _, _, reads = verification_case

    with pytest.raises(CaseNotFound):
        verifier.verify_case(case_id)
    assert reads == []
