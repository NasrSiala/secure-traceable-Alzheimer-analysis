"""T3.5 : graphe et checkpoints PostgreSQL réels, crypto réelle, ledger injecté."""

import json
import os
import threading
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from saam.cases import CaseService, InvalidTransition
from saam.pipeline import worker
from saam.pipeline.graph import (
    STAGES,
    AgentOutput,
    GraphRunner,
    WorkerInterrupted,
    fake_agent,
)
from saam.pipeline.logs import list_for_case
from saam.storage import ArtifactStore
from saam.traceability import TraceabilityTool, UploadStaging
from tests.api.test_cases_create import csv_bytes
from tests.pipeline.test_traceability import MemoryLedger


@pytest.fixture
def pipeline(postgres, migrated_database, tmp_path):
    api_url = postgres.dsn(migrated_database, "app_api")
    worker_url = postgres.dsn(migrated_database, "app_worker")
    cases = CaseService(worker_url)
    case_id = str(uuid4())
    with psycopg.connect(api_url, row_factory=dict_row) as db:
        user = db.execute(
            "INSERT INTO users (email,password_hash,display_name,role) VALUES (%s,'$argon2id$synthetic','Graph test','operator') RETURNING id",
            (uuid4().hex + "@demo.test",),
        ).fetchone()["id"]
        cases.create_case(
            db,
            case_id=case_id,
            user_id=str(user),
            ecg_format="csv",
            sampling_hz=100,
            has_report=True,
        )
    key = os.urandom(32)
    uploads = UploadStaging(ArtifactStore(tmp_path / "uploads", key))
    uploads.stage(
        case_id,
        {
            "ecg.csv": ("text/csv", csv_bytes()),
            "report.txt": ("text/plain", b"public-upload-marker-ABC"),
        },
        {"ecg_format": "csv", "sampling_hz": 100, "has_report": True},
    )
    store = ArtifactStore(tmp_path / "artifacts", key)
    ledger = MemoryLedger()
    tools = {
        step: TraceabilityTool(
            worker_url, store, ledger, on_failure=cases.fail_case, sleep=lambda _: None
        )
        for step in STAGES
    }
    return cases, uploads, tools, ledger, case_id


def test_seven_nodes_seven_anchored_artifacts_and_logs(pipeline):
    cases, uploads, tools, ledger, case_id = pipeline
    job = cases.claim_job("worker-one")
    assert job is not None
    runner = GraphRunner(cases, uploads, tools)
    try:
        result = runner.run(job)
    finally:
        runner.close()
    assert result["status"] == "termine"
    assert result["decision"] == "revision_requise"
    assert len(ledger.records) == 7
    with cases.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) AS n FROM artifacts WHERE case_id=%s AND anchor_status='ancre'",
                (case_id,),
            ).fetchone()["n"]
            == 7
        )
        assert db.execute(
            "SELECT status,locked_by FROM jobs WHERE id=%s", (job.id,)
        ).fetchone() == {"status": "termine", "locked_by": None}
        for row in db.execute("SELECT blob FROM langgraph.checkpoint_blobs").fetchall():
            assert b"public-upload-marker-ABC" not in bytes(row["blob"] or b"")
    logs = list_for_case(cases.database_url, case_id)
    assert [row["agent"] for row in logs] == list(STAGES)
    assert all(row["status"] == "succes" and row["duration_ms"] >= 0 for row in logs)
    assert cases.get_case(case_id)["decision"] == "revision_requise"


@pytest.mark.parametrize("failed_step", STAGES)
def test_any_agent_error_produces_an_anchored_rejection(pipeline, failed_step):
    cases, uploads, tools, ledger, case_id = pipeline

    def agent(step, state, files):
        if step == failed_step:
            raise ValueError("private-exception-must-not-be-logged")
        return fake_agent(step, state, files)

    runner = GraphRunner(cases, uploads, tools, agents={step: agent for step in STAGES})
    try:
        result = runner.run(cases.claim_job("worker-one"))
    finally:
        runner.close()
    assert result["status"] == "termine"
    assert result["decision"] == "rejete"
    final = next(
        r for r in ledger.records.values() if r["artifactType"] == "final_result"
    )
    assert final["parentArtifactId"] in ledger.records
    assert cases.get_case(case_id)["decision"] == "rejete"
    logs = list_for_case(cases.database_url, case_id)
    assert len(logs) == 7
    assert [r["agent"] for r in logs if r["status"] == "echec"] == [failed_step]
    assert "private-exception" not in str(logs)


def test_resume_after_process_interruption_keeps_ids_and_completed_nodes(pipeline):
    cases, uploads, tools, ledger, case_id = pipeline
    calls = []
    once = [True]

    def agent(step, state, files):
        calls.append(step)
        if step == "features" and once[0]:
            once[0] = False
            raise WorkerInterrupted("Interruption de test.")
        return fake_agent(step, state, files)

    agents = {step: agent for step in STAGES}
    job = cases.claim_job("worker-one")
    runner = GraphRunner(cases, uploads, tools, agents=agents)
    try:
        with pytest.raises(WorkerInterrupted):
            runner.run(job)
    finally:
        runner.close()
    initial_ids = set(ledger.records)
    assert len(initial_ids) == 2
    with cases.connect() as db:
        db.execute(
            "UPDATE jobs SET heartbeat_at=now()-interval '6 minutes' WHERE id=%s",
            (job.id,),
        )
    assert cases.recover_jobs() == 1
    resumed = cases.claim_job("worker-two")
    assert resumed.id == job.id and resumed.attempts == 2
    runner = GraphRunner(cases, uploads, tools, agents=agents)
    try:
        result = runner.run(resumed)
    finally:
        runner.close()
    assert result["status"] == "termine"
    assert initial_ids <= set(ledger.records) and len(ledger.records) == 7
    assert calls.count("ingestion") == calls.count("preparation") == 1


def test_single_claim_heartbeat_and_stale_owner_protection(pipeline):
    cases, _, _, _, case_id = pipeline
    job = cases.claim_job("worker-one")
    assert cases.claim_job("worker-two") is None
    assert cases.heartbeat(job)
    wrong = replace(job, owner="worker-two")
    assert not cases.heartbeat(wrong)
    with pytest.raises(InvalidTransition):
        cases.finish_job(wrong, True)
    with pytest.raises(InvalidTransition):
        cases.complete_case(case_id, "accepte", job=wrong)
    cases.fail_case(case_id, job=wrong)
    assert cases.get_case(case_id)["status"] == "en_cours"


def test_exhausted_stale_job_becomes_error(pipeline):
    cases, _, _, _, case_id = pipeline
    job = cases.claim_job("worker-one")
    with cases.connect() as db:
        db.execute(
            "UPDATE jobs SET max_attempts=1,heartbeat_at=now()-interval '6 minutes' WHERE id=%s",
            (job.id,),
        )
    assert cases.recover_jobs() == 1
    assert cases.claim_job("worker-two") is None
    assert cases.get_case(case_id)["status"] == "erreur"


def test_fabric_failure_never_finishes_the_case_as_accepted(pipeline):
    cases, uploads, tools, ledger, case_id = pipeline
    ledger.failures = 100
    runner = GraphRunner(cases, uploads, tools)
    try:
        result = runner.run(cases.claim_job("worker-one"))
    finally:
        runner.close()
    assert result["status"] == "erreur_ancrage"
    assert ledger.calls == 4
    case = cases.get_case(case_id)
    assert case["status"] == "erreur_ancrage" and case["decision"] is None


def test_heartbeat_keeps_running_during_a_slow_agent(pipeline):
    cases, uploads, tools, _, _ = pipeline
    reported = threading.Event()
    reports = []

    def report(owned):
        reports.append(owned)
        reported.set()

    def slow_agent(step, state, files):
        assert reported.wait(3), "Heartbeat attendu pendant l'action d'agent."
        return fake_agent(step, state, files)

    runner = GraphRunner(
        cases, uploads, tools, agents={"ingestion": slow_agent}, heartbeat_interval=0.05
    )
    try:
        result = runner.run(cases.claim_job("worker-one"), report=report)
    finally:
        runner.close()
    assert result["status"] == "termine" and reports and all(reports)


@pytest.mark.parametrize("interruption", ["lease", "stop"])
def test_interruption_during_agent_prevents_stale_artifact_write(
    pipeline, interruption
):
    cases, uploads, tools, ledger, case_id = pipeline
    stopped = threading.Event()
    job = cases.claim_job("worker-one")

    def agent(step, state, files):
        if interruption == "stop":
            stopped.set()
        else:
            with cases.connect() as db:
                db.execute(
                    "UPDATE jobs SET locked_by='worker-two' WHERE id=%s", (job.id,)
                )
        return fake_agent(step, state, files)

    runner = GraphRunner(cases, uploads, tools, agents={"ingestion": agent})
    try:
        with pytest.raises(WorkerInterrupted):
            runner.run(job, stop=stopped)
    finally:
        runner.close()
    assert not ledger.records
    assert cases.get_case(case_id)["status"] == "en_cours"
    with cases.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM artifacts").fetchone()["n"] == 0


def test_final_agent_cannot_override_a_failure_with_acceptance(pipeline):
    cases, uploads, tools, _, _ = pipeline

    def failure(*_):
        raise ValueError("synthetic failure")

    runner = GraphRunner(
        cases,
        uploads,
        tools,
        agents={
            "prediction": failure,
            "finalization": lambda *_: AgentOutput(decision="accepte"),
        },
    )
    try:
        result = runner.run(cases.claim_job("worker-one"))
        payload = tools["finalization"].read(
            result["last_artifact_id"], "final_result.json"
        )
    finally:
        runner.close()
    assert result["decision"] == "rejete"
    assert b'"decision":"rejete"' in payload and b'"accepte"' not in payload


def test_worker_main_claims_runs_and_closes_with_final_health_status(
    pipeline, monkeypatch, tmp_path
):
    cases, uploads, tools, ledger, case_id = pipeline
    runner = GraphRunner(cases, uploads, tools)
    run = runner.run
    observed = []

    def execute(job, **kwargs):
        observed.append(job)
        try:
            return run(job, **kwargs)
        finally:
            kwargs["stop"].set()

    monkeypatch.setattr(runner, "run", execute)
    monkeypatch.setattr(worker.GraphRunner, "from_environment", lambda: runner)
    monkeypatch.setattr(worker.signal, "signal", lambda *_: None)
    status_file = tmp_path / "worker.json"
    monkeypatch.setenv("DATABASE_URL_WORKER", cases.database_url)
    monkeypatch.setenv("WORKER_STATUS_FILE", str(status_file))
    worker.main()
    assert len(observed) == 1 and observed[0].case_id == case_id
    assert cases.get_case(case_id)["status"] == "termine"
    assert len(ledger.records) == 7
    assert runner.connection.closed
    assert json.loads(status_file.read_text())["status"] == "error"
    assert not list(tmp_path.glob(".worker-status-*"))


def test_partial_environment_configuration_closes_created_http_clients(monkeypatch):
    closed = []

    def make_tool(step, **_):
        if step == "preparation":
            raise ValueError("Jeton manquant.")
        return SimpleNamespace(
            ledger=SimpleNamespace(close=lambda: closed.append(step))
        )

    monkeypatch.setattr(TraceabilityTool, "from_environment", make_tool)
    with pytest.raises(ValueError, match="Jeton manquant"):
        GraphRunner.from_environment()
    assert closed == ["ingestion"]


def test_checkpoint_setup_failure_closes_its_database_connection(pipeline, monkeypatch):
    cases, uploads, tools, _, _ = pipeline
    connections = []

    def fail_setup(saver):
        connections.append(saver.conn)
        raise psycopg.OperationalError("setup unavailable")

    monkeypatch.setattr("saam.pipeline.graph.PostgresSaver.setup", fail_setup)
    with pytest.raises(psycopg.OperationalError):
        GraphRunner(cases, uploads, tools)
    assert len(connections) == 1 and connections[0].closed


def test_crash_after_anchor_and_log_before_checkpoint_replays_without_duplicates(
    pipeline, monkeypatch
):
    cases, uploads, tools, ledger, case_id = pipeline
    runner = GraphRunner(cases, uploads, tools)
    log = runner.log
    interrupted = False

    def crash_after_log(state, step, *args):
        nonlocal interrupted
        log(state, step, *args)
        if step == "preparation" and not interrupted:
            interrupted = True
            raise WorkerInterrupted("After external commit, before checkpoint.")

    monkeypatch.setattr(runner, "log", crash_after_log)
    job = cases.claim_job("worker-one")
    try:
        with pytest.raises(WorkerInterrupted):
            runner.run(job)
    finally:
        runner.close()
    anchored = set(ledger.records)
    assert len(anchored) == 2
    with cases.connect() as db:
        db.execute(
            "UPDATE jobs SET heartbeat_at=now()-interval '6 minutes' WHERE id=%s",
            (job.id,),
        )
    assert cases.recover_jobs() == 1
    runner = GraphRunner(cases, uploads, tools)
    try:
        result = runner.run(cases.claim_job("worker-two"))
    finally:
        runner.close()
    assert result["status"] == "termine" and anchored <= set(ledger.records)
    assert len(ledger.records) == 7
    logs = list_for_case(cases.database_url, case_id)
    assert [row["agent"] for row in logs] == list(STAGES)
