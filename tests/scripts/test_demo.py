"""J-04 avec l'API, le vrai stockage et le graphe factice."""

import json

import pytest
from fastapi.testclient import TestClient

from saam.api.main import create_app
from saam.cases import CaseService
from saam.ledger import LedgerClient
from saam.pipeline.graph import STAGES, GraphRunner
from saam.storage import ArtifactStore
from saam.traceability import ArtifactReader, TraceabilityTool
from scripts import tamper
from scripts.demo import record_pair, run_demo
from scripts.tamper import tamper_case
from tests.api import conftest as api_fixtures
from tests.api import test_cases_create, test_pipeline_flow

auth_service = api_fixtures.auth_service
cases_client = test_cases_create.cases_client
contract_gateway = test_pipeline_flow.contract_gateway


def test_demo_replays_three_times_without_input(
    cases_client, contract_gateway, postgres, migrated_database, tmp_path
):
    api, uploads, _ = cases_client
    url, tokens = contract_gateway
    record = tmp_path / "records500/00000/00001_hr"
    record.parent.mkdir(parents=True)
    record.with_suffix(".hea").write_text(
        "00001_hr 12 500 5000\n" + "00001_hr.dat 16 1000/mV 16 0 0 0 I\n" * 12,
        encoding="ascii",
    )
    record.with_suffix(".dat").write_bytes(b"\x00\x01" * 12 * 5000)
    pair = record_pair(tmp_path, "00001")

    cases = CaseService(postgres.dsn(migrated_database, "app_worker"))
    store = ArtifactStore(tmp_path / "artifacts", b"d" * 32)
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
    credentials = {
        f"SEED_{role.upper()}_{key}": value
        for role in ("operator", "auditor")
        for key, value in (
            ("EMAIL", f"{role}@demo.test"),
            ("PASSWORD", api_fixtures.PASSWORD),
        )
    }

    def finish_job(_):
        job = cases.claim_job("demo-test-worker")
        assert job is not None and runner.run(job)["status"] == "termine"

    results = []
    try:
        with TestClient(
            create_app(
                identity=api.app.state.identity,
                uploads=uploads,
                artifact_reader=ArtifactReader(store),
                ledger_factory=lambda: LedgerClient(url, tokens["verifier"]),
            ),
            base_url="https://testserver",
            client=("127.0.0.1", 51003),
        ) as web:

            def alter(case_id, kind, mode):
                assert (
                    tamper_case(cases, store, case_id, kind, mode) == "prediction.json"
                )

            for mode in ("raw", "reencrypt", "raw"):
                results.append(
                    run_demo(
                        web,
                        pair,
                        credentials,
                        alter,
                        kind="prediction",
                        mode=mode,
                        sleep=finish_job,
                    )
                )
            assert len({result["case_ref"] for result in results}) == 3
            assert all(result["simulation"] for result in results)
            assert all(
                (result["count_valide"], result["count_modifie"]) == (6, 1)
                for result in results
            )
            auth = test_cases_create.headers(web, "auditor")
            history = web.get(
                f"/api/v1/cases/{results[1]['case_ref']}/verifications", headers=auth
            ).json()
            assert history["total"] == 2
            assert history["items"][0]["count_modifie"] == 1
            assert history["items"][1]["count_valide"] == 7
            prediction = next(
                row
                for row in history["items"][0]["items"]
                if row["artifact_type"] == "prediction"
            )
            payload = store.read(prediction["artifact_id"], "prediction.json")
            assert json.loads(payload)["demo_tamper"] is True
    finally:
        runner.close()


@pytest.mark.parametrize("invalid", ["../01", "1", "00000", "12a45", "00001"])
def test_record_requires_valid_id_and_both_files(tmp_path, invalid):
    with pytest.raises(ValueError, match="PTB-XL"):
        record_pair(tmp_path, invalid)


def test_tamper_cli_uses_worker_storage_and_passes_only_explicit_arguments(
    tmp_path, monkeypatch
):
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_ORIGIN=https://localhost", encoding="utf-8")
    calls = []

    def run(args, *, cwd, check, timeout):
        calls.append((args, cwd, check, timeout))

    monkeypatch.setattr(tamper.subprocess, "run", run)
    case = "CASE-00000000-0000-0000-0000-000000000001"
    tamper.compose_tamper(case, "prediction", "reencrypt", env_file)
    assert calls == [
        (
            [
                "docker",
                "compose",
                "--env-file",
                str(env_file.resolve()),
                "exec",
                "-T",
                "worker",
                "python",
                "/app/scripts/tamper.py",
                "--local",
                "--case",
                case,
                "--artifact",
                "prediction",
                "--mode",
                "reencrypt",
            ],
            tamper.ROOT,
            True,
            30,
        )
    ]
