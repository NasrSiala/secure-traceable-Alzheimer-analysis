"""T4.7 : commandes admin, PostgreSQL et contrat de lecture Fabric."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import httpx
import psycopg
import pytest

from saam.ledger import LedgerClient
from saam.registry import create_validation_config
from saam.registry.seed import seed_configuration
from scripts.registry import main
from tests.api.conftest import PASSWORD
from tests.api.conftest import auth_service as auth_service
from tests.api.test_cases_create import cases_client as cases_client
from tests.api.test_cases_create import headers, submit

MODEL = "ecg-cnn1d"
SHA256 = "a" * 64
TX_ID = "b" * 64
CONFIG_NEW = [
    "config",
    "new",
    "--conf-high",
    "0.8",
    "--quality-min",
    "1",
    "--lexicon",
    "v1",
]
CONFIG_PROMPT = (
    "Les prochains cas utiliseront la version 2. "
    "Les cas existants ne changent pas. Confirmer ? [o/N] "
)
MODEL_PROMPT = "Les prochains cas utiliseront ecg-cnn1d 2.0.0. Confirmer ? [o/N] "


@pytest.fixture
def registry(auth_service, postgres, migrated_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_API", auth_service.database_url)
    monkeypatch.setenv("JWT_SECRET", auth_service.jwt_secret)
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "admin@demo.test")
    monkeypatch.setenv("REGISTRY_ADMIN_PASSWORD", PASSWORD)
    dsn = postgres.dsn(migrated_database)
    with psycopg.connect(dsn) as db:
        admin_id = db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
        seed_configuration(db, admin_id)
        for version, active in [("1.0.0", True), ("2.0.0", False)]:
            db.execute(
                """INSERT INTO models
                     (name, version, framework, sha256, file_path, registered_tx_id, is_active)
                   VALUES (%s,%s,'pytorch',%s,'fixtures/model.pt',%s,%s)""",
                (MODEL, version, SHA256, TX_ID, active),
            )
    return dsn, admin_id


def fabric(monkeypatch, *, status=200, sha256=SHA256):
    def response(request):
        assert request.method == "GET"
        assert request.url.path == "/ledger/models/ecg-cnn1d/2.0.0"
        assert request.headers["X-Agent-Token"] == "synthetic-verifier-token"
        if status == 404:
            return httpx.Response(
                status,
                json={
                    "error": {"code": "NOT_FOUND", "message": "Absent", "details": {}}
                },
            )
        if status == 502:
            raise httpx.ConnectError("test gateway offline", request=request)
        return httpx.Response(
            200,
            json={
                "docType": "model",
                "name": MODEL,
                "version": "2.0.0",
                "sha256": sha256,
            },
        )

    def client(agent):
        assert agent == "verifier"
        return LedgerClient(
            "http://test-gateway",
            "synthetic-verifier-token",
            transport=httpx.MockTransport(response),
        )

    monkeypatch.setattr(LedgerClient, "from_environment", client)


def test_cli_activates_for_future_cases_and_audits(
    registry, cases_client, monkeypatch, capsys
):
    dsn, admin_id = registry
    fabric(monkeypatch)
    client, _, _ = cases_client
    authorization = headers(client)
    first = submit(client, authorization)
    assert first.status_code == 202
    assert main(CONFIG_NEW) == 0
    assert capsys.readouterr().out == "Version 2 créée (inactive)\n"
    with psycopg.connect(dsn) as db:
        assert db.execute(
            """SELECT version,conf_high,quality_min,lexicon_version,is_active,created_by
               FROM validation_configs WHERE version=2"""
        ).fetchone() == (2, Decimal("0.800"), Decimal("1.000"), "v1", False, admin_id)

    assert main(["model", "list"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "ecg-cnn1d 1.0.0 actif",
        "ecg-cnn1d 2.0.0 inactif",
    ]
    with monkeypatch.context() as prompts:
        answers = iter(
            [(CONFIG_PROMPT, " o "), (MODEL_PROMPT, "O"), (MODEL_PROMPT, "o")]
        )

        def confirm(prompt):
            expected, answer = next(answers)
            assert prompt == expected
            return answer

        prompts.setattr("builtins.input", confirm)
        assert main(["config", "activate", "2"]) == 0
        assert main(["model", "activate", MODEL, "2.0.0"]) == 0
        assert main(["model", "activate", MODEL, "2.0.0"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Version 2 active",
        "ecg-cnn1d 2.0.0 actif",
        "ecg-cnn1d 2.0.0 actif",
    ]
    second = submit(client, authorization)
    assert second.status_code == 202

    with psycopg.connect(dsn) as db:
        for response, model, config in [(first, "1.0.0", 1), (second, "2.0.0", 2)]:
            assert db.execute(
                """SELECT m.version,v.version FROM cases c JOIN models m ON m.id=c.model_id
                   JOIN validation_configs v ON v.id=c.validation_config_id WHERE c.id=%s""",
                (response.json()["id"],),
            ).fetchone() == (model, config)
        assert db.execute(
            """SELECT event_type,actor_user_id,case_id,payload FROM audit_events
               WHERE event_type IN ('validation_config_created','model_activated') ORDER BY id"""
        ).fetchall() == [
            ("validation_config_created", admin_id, None, {"version": 2}),
            ("model_activated", admin_id, None, {"name": MODEL, "version": "2.0.0"}),
        ]


def test_rejects_operator_and_leaves_config_active_on_cancel(
    registry, monkeypatch, capsys
):
    dsn, _ = registry
    assert main(CONFIG_NEW) == 0
    capsys.readouterr()
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert main(["config", "activate", "2"]) == 0
    assert capsys.readouterr().out == ""

    monkeypatch.setattr("builtins.input", lambda _: "o")
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "operator@demo.test")
    assert main(["config", "activate", "2"]) == 1
    assert capsys.readouterr().err == "Action non autorisée.\n"
    assert main(["model", "list"]) == 1
    assert capsys.readouterr().err == "Action non autorisée.\n"
    with psycopg.connect(dsn) as db:
        assert db.execute(
            "SELECT version FROM validation_configs WHERE is_active"
        ).fetchall() == [(1,)]


@pytest.mark.parametrize(
    "threshold", ["0", "-0.1", "1.0001", "NaN", "Infinity", "0.0001", "abc"]
)
def test_invalid_threshold_message(threshold, capsys):
    command = CONFIG_NEW.copy()
    command[command.index("--conf-high") + 1] = threshold
    assert main(command) == 1
    assert capsys.readouterr().err == "Valeur entre 0 et 1.\n"


@pytest.mark.parametrize(
    "failure,message",
    [
        ("fabric_missing", "Ce modèle n'est pas enregistré sur la blockchain."),
        ("local_missing_tx", "Ce modèle n'est pas enregistré sur la blockchain."),
        (
            "hash_mismatch",
            "L'enregistrement du modèle sur la blockchain diffère du registre local.",
        ),
        ("offline", "Registre indisponible. Réessayer."),
        ("sql_update", "Opération impossible dans le registre local."),
    ],
)
def test_model_activation_failure_preserves_active_and_audit(
    failure, message, registry, monkeypatch, capsys
):
    dsn, _ = registry
    fabric(
        monkeypatch,
        status={"fabric_missing": 404, "offline": 502}.get(failure, 200),
        sha256="c" * 64 if failure == "hash_mismatch" else SHA256,
    )
    with psycopg.connect(dsn) as db:
        if failure == "sql_update":
            db.execute(
                "ALTER TABLE models ADD CHECK (NOT is_active OR version <> '2.0.0')"
            )
        if failure == "local_missing_tx":
            db.execute("UPDATE models SET registered_tx_id=NULL WHERE version='2.0.0'")
    monkeypatch.setattr("builtins.input", lambda _: "o")
    assert main(["model", "activate", MODEL, "2.0.0"]) == 1
    assert capsys.readouterr().err == message + "\n"
    with psycopg.connect(dsn) as db:
        assert db.execute("SELECT version FROM models WHERE is_active").fetchall() == [
            ("1.0.0",)
        ]
        assert db.execute(
            "SELECT count(*) FROM audit_events WHERE event_type='model_activated'"
        ).fetchone() == (0,)


def test_database_unreachable_exit_code(registry, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL_API", "postgresql://app_api@127.0.0.1:1/registry")
    assert main(["model", "list"]) == 2
    assert capsys.readouterr().err == "Base de données injoignable.\n"


def test_concurrent_config_creation_allocates_distinct_inactive_versions(
    registry, auth_service
):
    dsn, admin_id = registry
    ready = Barrier(2)

    def create():
        with auth_service.connect() as db:
            ready.wait(timeout=5)
            return create_validation_config(
                db, str(admin_id), Decimal("0.8"), Decimal("1"), "v1"
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create)
        second = pool.submit(create)
        assert sorted([first.result(timeout=10), second.result(timeout=10)]) == [2, 3]

    with psycopg.connect(dsn) as db:
        assert db.execute(
            "SELECT version,is_active FROM validation_configs ORDER BY version"
        ).fetchall() == [(1, True), (2, False), (3, False)]
