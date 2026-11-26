"""T4.11 : audit avec les transactions et les privilèges applicatifs réels."""

import json

import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.cases import CaseService
from saam.ledger import LedgerClient
from saam.pipeline.graph import STAGES, GraphRunner
from saam.storage import ArtifactStore
from saam.traceability import AnchoringError, ArtifactReader, TraceabilityTool
from scripts.audit_model_evaluation import record_model_card
from tests.api import test_cases_create, test_pipeline_flow
from tests.pipeline import test_traceability

cases_client = test_cases_create.cases_client
contract_gateway = test_pipeline_flow.contract_gateway
traceability_case = test_traceability.setup


def events(db_url):
    with psycopg.connect(db_url) as db:
        return db.execute(
            "SELECT event_type, actor_user_id::text, case_id::text, payload FROM audit_events ORDER BY id"
        ).fetchall()


def test_audit_from_case_creation_to_final_verification(
    cases_client, contract_gateway, postgres, migrated_database, tmp_path
):
    client, uploads, _ = cases_client
    url, tokens = contract_gateway
    operator = test_cases_create.headers(client)
    submitted = test_cases_create.submit(client, operator)
    assert submitted.status_code == 202
    case_id = submitted.json()["id"]
    cases = CaseService(postgres.dsn(migrated_database, "app_worker"))
    store = ArtifactStore(tmp_path / "artifacts", b"k" * 32)
    runner = GraphRunner(
        cases,
        uploads,
        {
            stage: TraceabilityTool(
                cases.database_url,
                store,
                LedgerClient(url, tokens["agent-" + stage]),
                on_failure=cases.fail_case,
            )
            for stage in STAGES
        },
    )
    try:
        job = cases.claim_job("audit-test-worker")
        assert job is not None and runner.run(job)["status"] == "termine"
    finally:
        runner.close()
    with TestClient(
        create_app(
            identity=client.app.state.identity,
            artifact_reader=ArtifactReader(store),
            ledger_factory=lambda: LedgerClient(url, tokens["verifier"]),
        ),
        base_url="https://testserver",
        client=("127.0.0.1", 51001),
    ) as verifier:
        auth = test_cases_create.headers(verifier, "auditor")
        response = verifier.post(f"/api/v1/cases/{case_id}/verifications", headers=auth)
        assert response.status_code == 201 and response.json()["count_valide"] == 7
    rows = events(cases.database_url)
    assert [row[0] for row in rows] == [
        "case_created",
        *(["artifact_anchored"] * 7),
        "pipeline_completed",
        "integrity_check_completed",
    ]
    assert all(row[2] == case_id and row[3]["case_id"] == case_id for row in rows)
    assert rows[0][3]["user_role"] == "operator"
    anchors = rows[1:8]
    assert len({row[3]["tx_id"] for row in anchors}) == 7
    assert all(row[1] is None for row in anchors)
    assert rows[8][3]["final_status"] == "revision_requise"
    assert rows[8][3]["duration_ms"] >= 0
    assert rows[9][1] == response.json()["requested_by"]
    assert rows[9][3] == {
        "case_id": case_id,
        "nb_valide": 7,
        "nb_modifie": 0,
        "nb_manquant": 0,
        "nb_non_verifiable": 0,
    }


def test_retry_exhaustion_and_successful_replay_are_audited_once(traceability_case):
    tool, ledger, _, artifact, url, *_ = traceability_case
    ledger.failures = 100
    with pytest.raises(AnchoringError):
        tool.record(artifact)
    assert ledger.calls == 4
    assert events(url) == [
        (
            "anchoring_failed",
            None,
            artifact.case_id,
            {
                "case_id": artifact.case_id,
                "artifact_type": "original",
                "error": "LEDGER_UNAVAILABLE",
            },
        )
    ]
    ledger.failures = 0
    result = tool.record(artifact)
    tool.record(artifact)
    assert [row[0] for row in events(url)] == ["anchoring_failed", "artifact_anchored"]
    assert events(url)[-1][3]["tx_id"] == result["tx_id"]


def test_audit_failure_does_not_cancel_case_transaction(
    cases_client, postgres, migrated_database, caplog
):
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        db.execute("ALTER TABLE audit_events ADD CHECK (event_type <> 'case_created')")
    client, _, _ = cases_client

    response = test_cases_create.submit(client, test_cases_create.headers(client))
    assert response.status_code == 202
    assert "Écriture du journal" in caplog.text
    with psycopg.connect(postgres.dsn(migrated_database)) as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone() == (1,)
        assert db.execute("SELECT count(*) FROM audit_events").fetchone() == (0,)


@pytest.mark.parametrize("auc,expected", [(0.87, True), (2, False), (True, False)])
def test_model_evaluation_ingests_only_version_and_metrics(
    postgres, migrated_database, tmp_path, auc, expected
):
    card = tmp_path / "model_card.json"
    url = postgres.dsn(migrated_database, "app_api")
    card.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "metrics": {"auc_macro": auc, "f1_macro": 0.72},
                "training_config": {"sample": "marker-never-in-audit"},
            }
        ),
        encoding="utf-8",
    )
    if expected:
        assert record_model_card(card, url)
        assert events(url) == [
            (
                "model_evaluated",
                None,
                None,
                {
                    "model_version": "1.0.0",
                    "auc_macro": 0.87,
                    "f1_macro": 0.72,
                },
            )
        ]
    else:
        with pytest.raises(ValueError):
            record_model_card(card, url)
        assert events(url) == []
