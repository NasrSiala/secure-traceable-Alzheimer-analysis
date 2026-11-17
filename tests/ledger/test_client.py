"""Contrat IF-07/IF-09 : HTTP réel Fastify, erreurs et transports remplaçables."""

import json
import secrets
from uuid import uuid4

import httpx
import pytest

from saam.ledger import (
    DuplicateRecord,
    InvalidRecord,
    LedgerClient,
    LedgerForbidden,
    LedgerUnavailable,
    RecordNotFound,
)

ID = "11111111-1111-4111-8111-111111111111"
CASE = "CASE-" + ID
TOKEN = "test-agent-token-" + secrets.token_hex(16)


def artifact(identifier=ID):
    return {
        "artifactId": identifier,
        "caseId": CASE,
        "artifactType": "original",
        "sha256": "ab" * 32,
        "createdAt": "2026-11-17T12:00:00.000Z",
        "softwareVersion": "0.1.0",
        "modelVersion": None,
        "parentArtifactId": None,
        "offchainRef": "artifact://" + identifier,
    }


def test_real_gateway_create_read_duplicate_and_identity(gateway) -> None:
    url, agent, verifier = gateway
    record = artifact(str(uuid4()))
    with LedgerClient(url, agent) as client:
        created = client.create_record(record)
        assert created["docType"] == "ARTIFACT"
        assert created["creatorMspId"] == "Org1MSP"
        assert all(created[key] == value for key, value in record.items())
        assert client.get_record(record["artifactId"]) == created
        with pytest.raises(DuplicateRecord) as duplicate:
            client.create_record(record)
        assert (duplicate.value.status, duplicate.value.code) == (409, "DUPLICATE")
    with LedgerClient(url, verifier) as reader:
        assert reader.get_record(record["artifactId"]) == created
        with pytest.raises(LedgerForbidden) as refusal:
            reader.create_record(artifact(str(uuid4())))
        assert refusal.value.status == 403
    with LedgerClient(url, TOKEN) as unknown:
        with pytest.raises(LedgerForbidden) as invalid:
            unknown.get_record(record["artifactId"])
        assert invalid.value.status == 401


def test_real_gateway_closed_schema_missing_parent_and_unavailable(gateway) -> None:
    url, agent, _ = gateway
    with LedgerClient(url, agent) as client:
        with pytest.raises(InvalidRecord) as extra:
            client.create_record(artifact(str(uuid4())) | {"patientName": "synthetic"})
        assert (extra.value.status, extra.value.code) == (400, "SCHEMA")
        with pytest.raises(InvalidRecord) as parent:
            client.create_record(
                artifact(str(uuid4()))
                | {"artifactType": "processed", "parentArtifactId": ID}
            )
        assert (parent.value.status, parent.value.code) == (422, "PARENT_MISSING")
        with pytest.raises(RecordNotFound):
            client.get_record(str(uuid4()))
        with pytest.raises(LedgerUnavailable):
            client.get_record("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


@pytest.mark.parametrize(
    "operation,method,path,payload,result",
    [
        (
            "create_record",
            "POST",
            "/ledger/artifacts",
            artifact(),
            {"docType": "ARTIFACT"},
        ),
        ("get_record", "GET", "/ledger/artifacts/" + ID, ID, {"docType": "ARTIFACT"}),
        (
            "get_case_history",
            "GET",
            "/ledger/cases/" + CASE,
            CASE,
            [{"artifactId": ID}],
        ),
        (
            "register_model",
            "POST",
            "/ledger/models",
            {"name": "ecg-cnn1d"},
            {"docType": "MODEL"},
        ),
        (
            "get_model",
            "GET",
            "/ledger/models/ecg-cnn1d/1.0.0",
            ("ecg-cnn1d", "1.0.0"),
            {"docType": "MODEL"},
        ),
    ],
)
def test_five_http_contracts(operation, method, path, payload, result) -> None:
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == method and request.url.path == path
        assert request.headers["X-Agent-Token"] == TOKEN
        if method == "POST":
            assert json.loads(request.content) == payload
        assert request.extensions["timeout"]["read"] == 10
        return httpx.Response(200, json=result)

    with LedgerClient(
        "http://gateway:8080", TOKEN, transport=httpx.MockTransport(handle)
    ) as client:
        args = payload if isinstance(payload, tuple) else (payload,)
        assert getattr(client, operation)(*args) == result
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,code,exception",
    [
        (400, "SCHEMA", InvalidRecord),
        (401, "UNAUTHORIZED", LedgerForbidden),
        (403, "FORBIDDEN", LedgerForbidden),
        (404, "NOT_FOUND", RecordNotFound),
        (409, "DUPLICATE", DuplicateRecord),
        (422, "PARENT_MISSING", InvalidRecord),
        (502, "UNAVAILABLE", LedgerUnavailable),
    ],
)
def test_error_mapping_never_exposes_gateway_secrets(status, code, exception) -> None:
    def handle(request):
        return httpx.Response(
            status, json={"error": {"code": code, "message": TOKEN, "details": {}}}
        )

    with LedgerClient(
        "http://gateway", TOKEN, transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(exception) as error:
            client.get_record(ID)
    assert error.value.status == status and error.value.code == code
    assert TOKEN not in str(error.value) + repr(error.value)


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError]
)
def test_transport_errors_have_no_implicit_retry(failure) -> None:
    calls = []

    def handle(request):
        calls.append(request)
        raise failure(TOKEN, request=request)

    with LedgerClient(
        "http://gateway", TOKEN, transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(LedgerUnavailable) as error:
            client.create_record(artifact())
    assert len(calls) == 1 and TOKEN not in str(error.value)


@pytest.mark.parametrize(
    "status,body",
    [
        (200, []),
        (200, {"error": {}}),
        (200, None),
        (409, {"error": {"code": "FORBIDDEN", "message": "wrong", "details": {}}}),
        (
            401,
            {
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "x",
                    "details": {"token": TOKEN},
                }
            },
        ),
        (500, {"error": {"code": "UNKNOWN", "message": TOKEN, "details": {}}}),
    ],
)
def test_invalid_response_is_unavailable(status, body) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    with LedgerClient("http://gateway", TOKEN, transport=transport) as client:
        with pytest.raises(LedgerUnavailable):
            client.get_record(ID)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not JSON"),
        httpx.Response(307, headers={"Location": "http://elsewhere/ledger/artifacts"}),
    ],
)
def test_invalid_json_and_redirects_do_not_resend_token(response) -> None:
    calls = []

    def handle(request):
        calls.append(request)
        return response

    with LedgerClient(
        "http://gateway", TOKEN, transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(LedgerUnavailable):
            client.get_record(ID)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [{}, [1], [{"error": {}}]])
def test_history_must_be_a_list_of_records(body) -> None:
    with LedgerClient(
        "http://gateway",
        TOKEN,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
    ) as client:
        with pytest.raises(LedgerUnavailable):
            client.get_case_history(CASE)


def test_empty_history_is_valid() -> None:
    with LedgerClient(
        "http://gateway",
        TOKEN,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    ) as client:
        assert client.get_case_history(CASE) == []


@pytest.mark.parametrize(
    "operation,args",
    [
        ("get_record", ("../../admin",)),
        ("get_case_history", ("../models",)),
        ("get_model", ("..", "1.0.0")),
        ("get_model", ("ecg", "1/../../")),
    ],
)
def test_path_injection_is_rejected_before_network(operation, args) -> None:
    def handle(request):
        pytest.fail("Un identifiant invalide ne doit pas atteindre le réseau.")

    with LedgerClient(
        "http://gateway", TOKEN, transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(InvalidRecord):
            getattr(client, operation)(*args)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/x",
        "http://user:secret@gateway",
        "http://gateway/other",
        "http://gateway?secret=x",
        "http://gateway#x",
    ],
)
def test_gateway_origin_is_explicit(url) -> None:
    with pytest.raises(ValueError):
        LedgerClient(url, TOKEN)


@pytest.mark.parametrize("token", ["", "short", "a" * 32 + "\r\nX-Role: admin"])
def test_bad_service_token_is_rejected_without_echo(token) -> None:
    with pytest.raises(ValueError) as error:
        LedgerClient("http://gateway", token)
    assert str(error.value) == "Jeton de service invalide."


def test_environment_selects_distinct_identity_and_file_fallback(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("LEDGER_GATEWAY_URL", "http://gateway")
    monkeypatch.setenv("AGENT_TOKEN_INGESTION", TOKEN)
    with LedgerClient.from_environment("ingestion") as client:
        assert client._http.headers["X-Agent-Token"] == TOKEN
    monkeypatch.delenv("AGENT_TOKEN_INGESTION")
    tokens = tmp_path / "tokens.json"
    tokens.write_text(
        json.dumps({"agent-ingestion": TOKEN, "verifier": "other-" + TOKEN})
    )
    monkeypatch.setenv("AGENT_TOKEN_FILE", str(tokens))
    with LedgerClient.from_environment("ingestion") as client:
        assert client._http.headers["X-Agent-Token"] == TOKEN
    monkeypatch.setenv("AGENT_TOKEN_VERIFIER", "")
    with LedgerClient.from_environment("verifier") as client:
        assert client._http.headers["X-Agent-Token"] == "other-" + TOKEN
    tokens.write_text("invalid " + TOKEN)
    with pytest.raises(ValueError) as error:
        LedgerClient.from_environment("ingestion")
    assert TOKEN not in str(error.value)
    with pytest.raises(ValueError):
        LedgerClient.from_environment("unknown")


def test_pool_is_closed_by_context_manager() -> None:
    with LedgerClient("http://gateway", TOKEN) as client:
        assert not client._http.is_closed
    assert client._http.is_closed


@pytest.mark.parametrize("value", [object(), float("nan")])
def test_non_json_payload_is_invalid_before_network(value) -> None:
    def handle(request):
        pytest.fail("Un corps non sérialisable ne doit pas atteindre le réseau.")

    with LedgerClient(
        "http://gateway", TOKEN, transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(InvalidRecord) as error:
            client.create_record(artifact() | {"sha256": value})
    assert (error.value.status, error.value.code) == (400, "SCHEMA")
