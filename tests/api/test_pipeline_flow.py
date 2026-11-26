"""HTTP/JWT → PostgreSQL/AES/LangGraph → HTTP Fastify/chaincode TypeScript."""

import json
import os
import secrets
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.cases import CaseService
from saam.ledger import LedgerClient
from saam.pipeline.graph import STAGES, GraphRunner
from saam.storage import ArtifactStore
from saam.traceability import ArtifactReader, TraceabilityTool
from tests.api.test_cases_create import cases_client as _cases_client
from tests.api.test_cases_create import headers, submit

flow_client = _cases_client


@pytest.fixture(scope="module")
def contract_gateway(repo_root):
    node = shutil.which("node")
    assert node, "Node requis pour tester le contrat TypeScript réel."
    for relative, flags in [
        ("chaincode/provenance", ["-p", "tsconfig.test.json"]),
        ("ledger-gateway", []),
    ]:
        package = repo_root / relative
        if not (package / "node_modules").is_dir():
            npm = shutil.which("npm.cmd") or shutil.which("npm")
            assert npm
            subprocess.run(
                [npm, "ci", "--ignore-scripts"],
                cwd=package,
                check=True,
                capture_output=True,
                timeout=180,
            )
        subprocess.run(
            [node, "node_modules/typescript/bin/tsc", *flags],
            cwd=package,
            check=True,
            capture_output=True,
            timeout=60,
        )
    tokens = {
        identity: secrets.token_hex(32)
        for identity in [*("agent-" + step for step in STAGES), "verifier"]
    }
    process = subprocess.Popen(
        [node, "tests/pipeline/contract-gateway.cjs"],
        cwd=repo_root,
        env=os.environ | {"TEST_PIPELINE_TOKENS": json.dumps(tokens)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        assert process.stdout is not None

        def address():
            for line in process.stdout:
                if line.startswith('{"address":'):
                    return json.loads(line)["address"]
            raise AssertionError("La passerelle du contrat n'a pas démarré.")

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(address)
            try:
                url = future.result(timeout=20)
            except TimeoutError:
                process.kill()
                raise
        yield url, tokens
    finally:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def test_creation_to_seven_anchors_and_readable_journal(
    flow_client, contract_gateway, postgres, migrated_database, tmp_path
):
    client, uploads, _ = flow_client
    url, tokens = contract_gateway
    authorization = headers(client)
    response = submit(
        client,
        authorization,
        data={"csv_sampling_rate": "100", "report_text": "SYNTHETIC-REPORT-MARKER"},
    )
    assert response.status_code == 202
    case_id = response.json()["id"]
    cases = CaseService(postgres.dsn(migrated_database, "app_worker"))
    store = ArtifactStore(tmp_path / "artifacts", os.urandom(32))
    tools = {
        step: TraceabilityTool(
            cases.database_url,
            store,
            LedgerClient(url, tokens["agent-" + step]),
            on_failure=cases.fail_case,
        )
        for step in STAGES
    }
    runner = GraphRunner(cases, uploads, tools)
    try:
        job = cases.claim_job("http-flow-worker")
        assert job and job.case_id == case_id
        result = runner.run(job)
        assert result["status"] == "termine"
        assert result["decision"] == "revision_requise"
        assert (
            tools["ingestion"].read(result["artifacts"]["ingestion"], "report.txt")
            == b"SYNTHETIC-REPORT-MARKER"
        )
    finally:
        runner.close()
    with LedgerClient(url, tokens["verifier"]) as ledger:
        history = ledger.get_case_history("CASE-" + case_id)
        assert len(history) == 7
        records = {record["artifactId"]: record for record in history}
        parent = None
        for step in STAGES:
            record = records[result["artifacts"][step]]
            assert record["parentArtifactId"] == parent
            assert record["creatorAgent"] == step
            assert "agent-" + step in record["creatorId"]
            assert record["caseId"] == "CASE-" + case_id
            parent = record["artifactId"]
        assert "SYNTHETIC-REPORT-MARKER" not in json.dumps(history)
        assert all(
            "files" not in record and "metadata" not in record for record in history
        )
        receipts = {ledger.get_record(identifier)["txId"] for identifier in records}
        assert len(receipts) == 7
    with cases.connect() as db:
        rows = db.execute(
            "SELECT id,anchor_status,tx_id FROM artifacts WHERE case_id=%s", (case_id,)
        ).fetchall()
    assert len(rows) == 7 and all(row["anchor_status"] == "ancre" for row in rows)
    assert {row["tx_id"] for row in rows} == receipts
    with TestClient(
        create_app(
            identity=client.app.state.identity,
            ledger_factory=lambda: LedgerClient(url, tokens["verifier"]),
        ),
        base_url="https://testserver",
        client=("127.0.0.1", 50001),
    ) as provenance_client:
        for role in ("operator", "admin", "auditor"):
            provenance = provenance_client.get(
                f"/api/v1/cases/CASE-{case_id}/history",
                headers=headers(provenance_client, role),
            )
            assert provenance.status_code == 200
            assert [row["creatorAgent"] for row in provenance.json()] == list(STAGES)
            assert {row["txId"] for row in provenance.json()} == receipts
            assert all(
                row["sha256"] == records[row["artifactId"]]["sha256"]
                for row in provenance.json()
            )
            assert "SYNTHETIC-REPORT-MARKER" not in provenance.text
        assert (
            provenance_client.get(f"/api/v1/cases/{case_id}/history").status_code == 401
        )
    client.app.state.artifact_reader = ArtifactReader(store)
    detail = client.get(f"/api/v1/cases/{case_id}", headers=authorization)
    assert detail.status_code == 200
    assert detail.json()["final_result"]["simulation"] is True
    assert detail.json()["decision"] == "revision_requise"
    assert all(step["status"] == "ancre" for step in detail.json()["steps"])
    # Le graphe factice ne produit pas de signal traité ; ne pas fabriquer un ECG.
    assert (
        client.get(f"/api/v1/cases/{case_id}/signal", headers=authorization).status_code
        == 404
    )
    for role in ("operator", "admin", "auditor"):
        logs = client.get(
            f"/api/v1/cases/{case_id}/agent-logs", headers=headers(client, role)
        )
        assert logs.status_code == 200
        assert logs.headers["cache-control"] == "no-store"
        assert [row["agent"] for row in logs.json()] == list(STAGES)
        assert all(row["status"] == "succes" for row in logs.json())
    assert client.get(f"/api/v1/cases/{case_id}/agent-logs").status_code == 401


def test_journal_unknown_case_and_database_failure(flow_client, monkeypatch):
    client, _, _ = flow_client
    authorization = headers(client)
    missing = client.get(f"/api/v1/cases/{uuid4()}/agent-logs", headers=authorization)
    assert missing.status_code == 404
    assert missing.json()["error"]["message"] == "Cas introuvable."
    assert (
        client.get(
            "/api/v1/cases/not-a-uuid/agent-logs", headers=authorization
        ).status_code
        == 404
    )
    case_id = submit(client, authorization).json()["id"]

    def unavailable(*_):
        raise psycopg.OperationalError("PRIVATE-DB-ERROR")

    monkeypatch.setattr("saam.api.cases.list_for_case", unavailable)
    response = client.get(f"/api/v1/cases/{case_id}/agent-logs", headers=authorization)
    assert response.status_code == 503 and "PRIVATE-DB-ERROR" not in response.text
