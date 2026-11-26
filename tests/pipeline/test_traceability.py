"""T3.3 : PostgreSQL et AES-GCM réels, registre remplaçable pour les pannes."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from saam.ledger import DuplicateRecord, LedgerUnavailable
from saam.storage import ArtifactStore
from saam.traceability import (
    AnchoringError,
    Artifact,
    ArtifactFile,
    IntegrityError,
    TraceabilityTool,
)


class MemoryLedger:
    def __init__(self):
        self.records = {}
        self.calls = 0
        self.failures = 0
        self.ambiguous = False
        self.missing_receipt = False
        self.before_create = lambda: None

    def create_record(self, record):
        self.calls += 1
        self.before_create()
        if self.calls <= self.failures:
            raise LedgerUnavailable()
        identifier = record["artifactId"]
        if identifier in self.records:
            raise DuplicateRecord(409, "DUPLICATE")
        stored = dict(record) | {"txId": "c" * 64}
        if self.missing_receipt:
            stored.pop("txId")
        self.records[identifier] = stored
        if self.ambiguous:
            self.ambiguous = False
            raise LedgerUnavailable()
        return stored

    def get_record(self, identifier):
        return dict(self.records[identifier])

    def get_case_history(self, case_id):
        return [dict(r) for r in self.records.values() if r["caseId"] == case_id]

    def register_model(self, model):
        raise NotImplementedError

    def get_model(self, name, version):
        raise NotImplementedError


@pytest.fixture
def setup(postgres, migrated_database, tmp_path):
    case_id = str(uuid4())
    api_url = postgres.dsn(migrated_database, "app_api")
    worker_url = postgres.dsn(migrated_database, "app_worker")
    with psycopg.connect(api_url) as db:
        user = db.execute(
            "INSERT INTO users (email,password_hash,display_name,role) VALUES (%s,'$argon2id$synthetic','Synthetic','operator') RETURNING id",
            (uuid4().hex + "@demo.test",),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO cases (id,created_by,status,ecg_format,original_sampling_hz,has_report) VALUES (%s,%s,'en_cours','csv',100,false)",
            (case_id, user),
        )
    ledger = MemoryLedger()
    store = ArtifactStore(tmp_path / "artifacts", os.urandom(32))
    failures, delays = [], []

    def fail(identifier):
        failures.append(identifier)
        with psycopg.connect(worker_url) as db:
            db.execute(
                "UPDATE cases SET status='erreur_ancrage',completed_at=now() WHERE id=%s",
                (identifier,),
            )

    tool = TraceabilityTool(
        worker_url, store, ledger, on_failure=fail, sleep=delays.append
    )
    artifact = Artifact(
        str(uuid4()),
        case_id,
        "original",
        "ingestion",
        datetime(2026, 11, 24, 12, tzinfo=UTC),
        files=(ArtifactFile("ecg.csv", "text/csv", b"public synthetic ECG"),),
    )
    return tool, ledger, store, artifact, worker_url, failures, delays


def test_files_and_sql_are_durable_before_the_fabric_call(setup):
    tool, ledger, store, artifact, url, failures, _ = setup

    def before():
        with psycopg.connect(url) as db:
            row = db.execute(
                "SELECT anchor_status,anchor_attempts,tx_id FROM artifacts WHERE id=%s",
                (artifact.id,),
            ).fetchone()
            assert row == ("en_attente", 1, None)
        assert store.read(artifact.id, "ecg.csv") == artifact.files[0].data

    ledger.before_create = before
    row = tool.record(artifact)
    assert row["anchor_status"] == "ancre"
    assert row["tx_id"] == "c" * 64
    assert tool.read(artifact.id, "ecg.csv") == artifact.files[0].data
    assert failures == []


def test_idempotent_replay_and_ambiguous_commit(setup):
    tool, ledger, _, artifact, _, _, delays = setup
    ledger.ambiguous = True
    first = tool.record(artifact)
    assert ledger.calls == 2
    assert delays == [1.0]
    assert tool.record(artifact)["tx_id"] == first["tx_id"]
    assert ledger.calls == 2


def test_three_retries_then_no_accepted_result(setup):
    tool, ledger, _, artifact, url, failures, delays = setup
    ledger.failures = 100
    with pytest.raises(AnchoringError):
        tool.record(artifact)
    assert ledger.calls == 4
    assert delays == [1.0, 2.0, 4.0]
    assert failures == [artifact.case_id]
    with psycopg.connect(url) as db:
        assert db.execute(
            "SELECT status,decision FROM cases WHERE id=%s", (artifact.case_id,)
        ).fetchone() == ("erreur_ancrage", None)
        assert db.execute(
            "SELECT anchor_status,anchor_attempts,tx_id FROM artifacts WHERE id=%s",
            (artifact.id,),
        ).fetchone() == ("echec", 4, None)


def test_different_replay_is_refused_without_overwriting_the_file(setup):
    tool, _, store, artifact, _, _, _ = setup
    tool.record(artifact)
    with pytest.raises(AnchoringError):
        tool.record(
            replace(
                artifact, files=(ArtifactFile("ecg.csv", "text/csv", b"different"),)
            )
        )
    assert store.read(artifact.id, "ecg.csv") == artifact.files[0].data


def test_concurrent_replays_write_one_record(setup):
    tool, ledger, _, artifact, _, _, _ = setup
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(tool.record, [artifact, artifact]))
    assert ledger.calls == 1
    assert all(row["tx_id"] == "c" * 64 for row in results)


def test_read_uses_the_chain_and_detects_valid_gcm_with_changed_plaintext(setup):
    tool, _, store, artifact, url, _, _ = setup
    tool.record(artifact)
    with psycopg.connect(url) as db:
        # La copie SQL n'est pas l'oracle : elle ne change pas le manifeste lu.
        assert db.execute(
            "SELECT sha256 FROM artifacts WHERE id=%s", (artifact.id,)
        ).fetchone()
    store.write(artifact.id, "ecg.csv", b"tampered but authenticated")
    with pytest.raises(IntegrityError):
        tool.read(artifact.id, "ecg.csv")


def test_receipt_for_another_hash_or_missing_txid_is_not_accepted(setup):
    tool, ledger, _, artifact, _, _, _ = setup
    ledger.records[artifact.id] = {"artifactId": artifact.id, "sha256": "0" * 64}
    with pytest.raises(AnchoringError):
        tool.record(artifact)


def test_parent_type_and_agent_contracts(setup):
    tool, _, _, artifact, _, _, _ = setup
    with pytest.raises(ValueError):
        tool.record(
            replace(
                artifact, type="processed", agent="preparation", parent_id=str(uuid4())
            )
        )
    with pytest.raises(ValueError):
        tool.record(replace(artifact, agent="verifier"))


def test_missing_receipt_never_creates_a_fake_transaction_id(setup):
    tool, ledger, _, artifact, url, failures, _ = setup
    ledger.missing_receipt = True
    with pytest.raises(AnchoringError):
        tool.record(artifact)
    assert ledger.calls == 4
    assert failures == [artifact.case_id]
    with psycopg.connect(url) as db:
        assert db.execute(
            "SELECT tx_id FROM artifacts WHERE id=%s", (artifact.id,)
        ).fetchone() == (None,)


def test_manifest_verification_ignores_the_database_hash_copy(setup):
    from psycopg.conninfo import make_conninfo

    tool, _, _, artifact, url, _, _ = setup
    tool.record(artifact)
    with psycopg.connect(make_conninfo(url, user="postgres")) as db:
        db.execute(
            "UPDATE artifacts SET sha256=%s WHERE id=%s", ("0" * 64, artifact.id)
        )
    assert tool.read(artifact.id, "ecg.csv") == artifact.files[0].data
