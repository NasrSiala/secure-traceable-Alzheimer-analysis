"""NFR-03: no health data and no direct identifier reaches the history of a case on the ledger.

T2.9. The guard walks what `GetCaseHistory` returns (through the gateway, IF-09) and refuses
every field outside the closed ARTIFACT schema (Schema 5.2), every value outside its format, and
every value that looks like a name or a date of birth.

Three layers, all on synthetic data:
  1. the guard itself, on records built in memory: clean data passes, each negative fixture is
     detected with its kind;
  2. the HTTP path (`httpx`, the fallback of plan l09 until `LedgerClient` of T2.7 exists), on a
     mock transport;
  3. the test network (marker `fabric`): a synthetic case is written through the gateway and its
     history is read back through the gateway.

Privacy of the diagnostics: a violation carries a record position, a kind and a field label, never
a value. Nothing here prints a record, a body or a token.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import phi_guard
import pytest
from fabric_support import assert_ok
from gateway_history import GatewayHistory, LedgerAccessError, ledger_path
from phi_guard import ARTIFACT_FIELDS, Violation
from process_tree import ProcessTree
from synthetic_case import PIPELINE, clean_history, client_body, synthetic_case_id

from tests.conftest import bash_executable

Records = list[dict[str, object]]
Mutation = Callable[[Records], None]


def kinds(violations: list[Violation]) -> set[str]:
    return {violation.kind for violation in violations}


def only_record(records: Records) -> dict[str, object]:
    return records[0]


# --------------------------------------------------------------------------------------------
# 1. The guard on records built in memory
# --------------------------------------------------------------------------------------------


def test_the_synthetic_history_has_the_seven_artifacts_of_a_case() -> None:
    records = clean_history("unit")

    assert [record["artifactType"] for record in records] == PIPELINE
    assert all(set(record) == set(ARTIFACT_FIELDS) for record in records)


def test_clean_data_passes() -> None:
    assert phi_guard.check_history(clean_history("unit")) == []


def test_an_empty_history_is_clean_for_the_guard() -> None:
    # "A case with no record" is a fact about the ledger, asserted by the real-path tests; the
    # guard only judges what it is given.
    assert phi_guard.check_history([]) == []


def test_a_clean_history_passes_with_a_null_and_with_a_set_model_version() -> None:
    records = clean_history("unit")
    records[3]["modelVersion"] = "ecg-cnn-1.0.0"

    assert phi_guard.check_history(records) == []


@pytest.mark.parametrize(
    "value",
    ["0.1.0", "1.0.0-rc1", "10.200.3000", "ecg-cnn-1.0.0", "v0.1.0", "0.1.0+build.7"],
)
def test_technical_versions_are_not_mistaken_for_identifiers(value: str) -> None:
    records = clean_history("unit")
    only_record(records)["softwareVersion"] = value
    only_record(records)["modelVersion"] = value

    assert phi_guard.check_history(records) == []


def test_a_hash_that_contains_digits_shaped_like_a_date_is_a_hash() -> None:
    records = clean_history("unit")
    only_record(records)["sha256"] = "19750312" * 8

    assert phi_guard.check_history(records) == []


# -- fields outside the closed schema --------------------------------------------------------

ILLEGAL_FIELDS = [
    "patientName",
    "patient_name",
    "firstName",
    "lastName",
    "nom",
    "prenom",
    "birthDate",
    "dob",
    "date_de_naissance",
    "ssn",
    "email",
    "diagnosis",
    "ecgSamples",
    "report",
    "notes",
    "file_path",
    "is_active",
    "Jean Dupont",
]


@pytest.mark.parametrize("field", ILLEGAL_FIELDS)
def test_a_field_outside_the_schema_is_detected(field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = "synthetic"

    found = phi_guard.check_history(records)

    assert "unknown_field" in kinds(found)
    assert {violation.record for violation in found} == {0}


@pytest.mark.parametrize(
    "field",
    [
        "patientName",
        "patient_name",
        "firstName",
        "lastName",
        "nom",
        "prenom",
        "birthDate",
        "dob",
        "date_de_naissance",
        "ssn",
        "email",
    ],
)
def test_a_field_named_like_an_identity_is_called_one(field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = "synthetic"

    assert "identity_field" in kinds(phi_guard.check_history(records))


@pytest.mark.parametrize(
    "field", ["diagnosis", "ecgSamples", "report", "notes", "is_active"]
)
def test_another_illegal_field_is_unknown_but_not_called_an_identity(
    field: str,
) -> None:
    records = clean_history("unit")
    only_record(records)[field] = "synthetic"

    found = kinds(phi_guard.check_history(records))

    assert "unknown_field" in found
    assert "identity_field" not in found


@pytest.mark.parametrize("value", [{"first": "x"}, ["x"], 7, None, True])
def test_an_illegal_field_is_detected_whatever_its_value_type(value: object) -> None:
    records = clean_history("unit")
    only_record(records)["extra"] = value

    assert "unknown_field" in kinds(phi_guard.check_history(records))


def test_a_doc_type_other_than_artifact_is_detected() -> None:
    records = clean_history("unit")
    only_record(records)["docType"] = "model"

    found = phi_guard.check_history(records)

    assert "format" in kinds(found)
    assert {violation.field for violation in found} == {"docType"}


def test_a_name_or_a_date_used_as_the_name_of_a_field_is_read() -> None:
    """The key of a field outside the schema can carry the identity as well as its value."""
    records = clean_history("unit")
    only_record(records)["Jean Dupont"] = 1
    only_record(records)["1975-03-12"] = 1

    found = kinds(phi_guard.check_history(records))

    assert {"unknown_field", "name_pattern", "dob_pattern"} <= found


def test_a_missing_field_is_detected() -> None:
    records = clean_history("unit")
    del only_record(records)["creatorId"]

    assert "missing_field" in kinds(phi_guard.check_history(records))


# -- the guard knows the schema of the chaincode -----------------------------------------------

ROOT = Path(__file__).resolve().parents[2]


def _chaincode_source() -> str:
    return (ROOT / "chaincode" / "provenance" / "src" / "artifact.ts").read_text(
        encoding="utf-8"
    )


def test_the_guard_knows_exactly_the_fields_of_the_chaincode() -> None:
    client = re.search(
        r"CLIENT_FIELDS = new Set<string>\(\[(.*?)\]\)", _chaincode_source(), re.DOTALL
    )
    assert client, "CLIENT_FIELDS not found in artifact.ts"
    fields = set(re.findall(r'"([^"]+)"', client.group(1)))
    chaincode_owned = {
        "docType",
        "txTimestamp",
        "creatorMspId",
        "creatorId",
        "creatorAgent",
    }

    assert set(ARTIFACT_FIELDS) == fields | chaincode_owned
    assert set(phi_guard.CLIENT_FIELDS) == fields
    assert len(ARTIFACT_FIELDS) == 14


def test_the_guard_knows_exactly_the_artifact_types_of_the_chaincode() -> None:
    declared = re.search(
        r"ARTIFACT_TYPES = \[(.*?)\] as const", _chaincode_source(), re.DOTALL
    )
    assert declared, "ARTIFACT_TYPES not found in artifact.ts"

    assert re.findall(r'"([^"]+)"', declared.group(1)) == list(phi_guard.ARTIFACT_TYPES)
    assert list(phi_guard.ARTIFACT_TYPES) == PIPELINE


# -- values outside their format ------------------------------------------------------------

BAD_FORMATS: list[tuple[str, str, object]] = [
    ("artifactId", "artifactId", "not-a-uuid"),
    ("caseId", "caseId", "CASE-1"),
    ("artifactType", "artifactType", "diagnosis"),
    ("sha256", "sha256", "AB" * 32),
    ("offchainRef", "offchainRef", "artifact://another-id"),
    ("creatorMspId", "creatorMspId", "Org 1"),
    ("creatorAgent", "creatorAgent", "Jean Dupont"),
    ("creatorId", "creatorId", "Jean Dupont"),
    ("parentArtifactId", "parentArtifactId", "parent"),
]


@pytest.mark.parametrize(
    ("label", "field", "value"), BAD_FORMATS, ids=[b[0] for b in BAD_FORMATS]
)
def test_a_value_outside_its_format_is_detected(
    label: str, field: str, value: object
) -> None:
    records = clean_history("unit")
    records[1][field] = value

    found = phi_guard.check_history(records)

    assert "format" in kinds(found)
    assert {violation.record for violation in found} == {1}
    assert field in {violation.field for violation in found}


@pytest.mark.parametrize("value", [7, ["0.1.0"], {"v": "0.1.0"}, True])
def test_a_value_of_the_wrong_type_is_detected(value: object) -> None:
    records = clean_history("unit")
    only_record(records)["softwareVersion"] = value

    assert "wrong_type" in kinds(phi_guard.check_history(records))


@pytest.mark.parametrize("record", [None, "text", 7, [], [{"a": 1}]])
def test_an_element_that_is_not_an_object_is_detected(record: object) -> None:
    found = phi_guard.check_history([record])  # type: ignore[list-item]

    assert kinds(found) == {"not_a_record"}


# -- name and date-of-birth patterns ---------------------------------------------------------

DATES_OF_BIRTH = [
    "1975-03-12",
    "1975/03/12",
    "1975.3.12",
    "12/03/1975",
    "12-03-1975",
    "12.03.1975",
    "19750312",
    "12 mars 1975",
    "12 March 1975",
    "1 janvier 2001",
    "né le 12/03/1975",
    "dob 1975-03-12",
    "born-1975-03-12",
]


@pytest.mark.parametrize("value", DATES_OF_BIRTH)
@pytest.mark.parametrize("field", ["softwareVersion", "modelVersion"])
def test_a_date_of_birth_pattern_is_detected_in_a_free_field(
    value: str, field: str
) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    found = phi_guard.check_history(records)

    assert "dob_pattern" in kinds(found)
    assert field in {violation.field for violation in found}


@pytest.mark.parametrize(
    "value", ["1975-03-12", "12/03/1975", "19750312", "12 mars 1975"]
)
def test_a_date_of_birth_pattern_is_detected_in_a_field_outside_the_schema(
    value: str,
) -> None:
    records = clean_history("unit")
    only_record(records)["extra"] = value

    assert "dob_pattern" in kinds(phi_guard.check_history(records))


BIRTH_WORDS = ["dob", "born", "naissance", "birth", "birthdate", "birthday"]


@pytest.mark.parametrize("value", BIRTH_WORDS)
@pytest.mark.parametrize("field", ["softwareVersion", "modelVersion"])
def test_a_birth_word_alone_is_detected_in_a_free_field(value: str, field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    found = phi_guard.check_history(records)

    assert "dob_pattern" in kinds(found)
    assert field in {violation.field for violation in found}


# A title followed by a full stop is not read as a name by the first pattern (a capitalised word
# and a capitalised word); the title pattern is the one that finds it.
TITLED_NAMES = ["M. Martin", "Mr. Dupont", "Dr. Dupont", "Mlle. Durand", "Pr. Curie"]


@pytest.mark.parametrize("value", TITLED_NAMES)
@pytest.mark.parametrize("field", ["softwareVersion", "modelVersion"])
def test_a_title_and_a_name_is_detected_in_a_free_field(value: str, field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    assert "name_pattern" in kinds(phi_guard.check_history(records))


NAMES = [
    "Jean Dupont",
    "DUPONT Jean",
    "Jean-Pierre Martin",
    "Marie Curie-Sklodowska",
    "Mme Martin",
    "Dr Dupont",
    "nom: dupont",
    "name=jean",
    "Élodie Bérenger",
]


@pytest.mark.parametrize("value", NAMES)
@pytest.mark.parametrize("field", ["softwareVersion", "modelVersion"])
def test_a_name_pattern_is_detected_in_a_free_field(value: str, field: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    found = phi_guard.check_history(records)

    assert "name_pattern" in kinds(found)
    assert field in {violation.field for violation in found}


@pytest.mark.parametrize("value", ["Jean Dupont", "DUPONT Jean", "Mme Martin"])
def test_a_name_pattern_is_detected_in_a_field_outside_the_schema(value: str) -> None:
    records = clean_history("unit")
    only_record(records)["extra"] = value

    assert "name_pattern" in kinds(phi_guard.check_history(records))


@pytest.mark.parametrize("value", NAMES)
def test_a_name_written_with_its_spaces_is_also_not_a_version(value: str) -> None:
    """A version is a token without space, colon or equals sign: a name does not fit it, on top of
    being recognised as a name."""
    records = clean_history("unit")
    only_record(records)["softwareVersion"] = value

    assert "format" in kinds(phi_guard.check_history(records))


NESTED: list[tuple[str, object, str]] = [
    ("a name in an object", {"first": "Jean Dupont"}, "name_pattern"),
    ("a name in a list", ["Jean Dupont"], "name_pattern"),
    ("a name as a nested key", {"Jean Dupont": 1}, "name_pattern"),
    ("a date of birth in an object", {"a": {"b": "12/03/1975"}}, "dob_pattern"),
    ("a date of birth in a list", ["x", ["1975-03-12"]], "dob_pattern"),
]


@pytest.mark.parametrize(("label", "value", "kind"), NESTED, ids=[n[0] for n in NESTED])
def test_a_value_nested_in_an_illegal_field_is_read_too(
    label: str, value: object, kind: str
) -> None:
    records = clean_history("unit")
    only_record(records)["extra"] = value

    found = kinds(phi_guard.check_history(records))

    assert kind in found
    assert "unknown_field" in found


def test_the_creator_is_the_bare_subject_the_chaincode_stores() -> None:
    """Seen on the test network: `creatorId` is the subject only. The chaincode cuts the `x509::`
    wrapper and the issuer off (artifact.ts `certificateSubject`), so the wrapped form never comes
    back from the ledger and is not accepted."""
    records = clean_history("unit")
    assert (
        records[0]["creatorId"]
        == "/C=US/ST=North Carolina/O=Hyperledger/OU=client/CN=agent-ingestion"
    )
    assert phi_guard.check_history(records) == []

    only_record(records)["creatorId"] = (
        "x509::/CN=agent-ingestion/OU=client::/CN=ca.org1.example.com"
    )

    assert "format" in kinds(phi_guard.check_history(records))


def test_a_name_in_the_subject_of_the_creator_is_detected() -> None:
    records = clean_history("unit")
    only_record(records)["creatorId"] = (
        "/C=US/ST=North Carolina/O=Hyperledger/OU=client/CN=Jean Dupont"
    )

    found = phi_guard.check_history(records)

    assert "format" in kinds(found)


def test_a_date_of_birth_in_the_subject_of_the_creator_is_detected() -> None:
    records = clean_history("unit")
    only_record(records)["creatorId"] = (
        "/C=US/ST=North Carolina/O=Hyperledger/OU=client/CN=agent-ingestion-1975-03-12"
    )

    assert "dob_pattern" in kinds(phi_guard.check_history(records))


# -- a date of birth hidden in a timestamp ---------------------------------------------------


@pytest.mark.parametrize("field", ["createdAt", "txTimestamp"])
@pytest.mark.parametrize(
    "value",
    [
        "1975-03-12T00:00:00.000Z",
        "2001-01-01T00:00:00Z",
        "2019-12-31T23:59:59Z",
        "2100-01-01T00:00:00Z",
        "2150-01-01T00:00:00.000Z",
    ],
)
def test_a_timestamp_far_from_the_project_era_is_detected(
    field: str, value: str
) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    assert "timestamp_range" in kinds(phi_guard.check_history(records))


@pytest.mark.parametrize("field", ["createdAt", "txTimestamp"])
@pytest.mark.parametrize(
    "value",
    ["2020-01-01T00:00:00Z", "2026-11-09T12:00:00.123456789Z", "2099-12-31T23:59:59Z"],
)
def test_a_timestamp_inside_the_project_era_passes(field: str, value: str) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    assert phi_guard.check_history(records) == []


@pytest.mark.parametrize("field", ["createdAt", "txTimestamp"])
@pytest.mark.parametrize(
    "value", ["12/03/2026", "2026-11-09", "not a date", "2026-11-09 12:00:00"]
)
def test_a_timestamp_that_is_not_iso_8601_utc_is_detected(
    field: str, value: str
) -> None:
    records = clean_history("unit")
    only_record(records)[field] = value

    assert "format" in kinds(phi_guard.check_history(records))


# -- the diagnostics never carry a value -----------------------------------------------------

SENTINELS = {
    "name": "Zephyrine Quillfeather",
    "birth": "1931-07-04",
    "key": "quillfeatherNom",
}


NEGATIVES: list[tuple[str, Mutation]] = [
    ("name in a version", lambda r: r[0].update(softwareVersion=SENTINELS["name"])),
    ("birth date in a version", lambda r: r[0].update(modelVersion=SENTINELS["birth"])),
    ("illegal field", lambda r: r[0].update({SENTINELS["key"]: SENTINELS["name"]})),
    ("birth date in an illegal field", lambda r: r[0].update(extra=SENTINELS["birth"])),
    (
        "birth date as a timestamp",
        lambda r: r[0].update(createdAt=f"{SENTINELS['birth']}T00:00:00Z"),
    ),
    ("name as the creator", lambda r: r[0].update(creatorId=SENTINELS["name"])),
]


@pytest.mark.parametrize(("label", "mutate"), NEGATIVES, ids=[n[0] for n in NEGATIVES])
def test_the_diagnostics_never_contain_the_value_or_the_field_name(
    label: str, mutate: Mutation
) -> None:
    records = clean_history("unit")
    mutate(records)

    found = phi_guard.check_history(records)
    text = phi_guard.describe(found)
    echoed = repr(found)

    assert found
    for sentinel in SENTINELS.values():
        assert sentinel not in text
        assert sentinel not in echoed
        assert sentinel.lower() not in text.lower()
    # A violation says where (record position, field label) and what (kind), nothing else.
    assert re.search(r"record \d+", text)


def test_an_unknown_field_is_labelled_without_its_name() -> None:
    records = clean_history("unit")
    only_record(records)[SENTINELS["key"]] = "synthetic"

    labels = {violation.field for violation in phi_guard.check_history(records)}

    assert SENTINELS["key"] not in labels
    assert any(label.startswith("<unknown field") for label in labels)


def test_the_guard_does_not_change_the_records_it_reads() -> None:
    records = clean_history("unit")
    only_record(records)["softwareVersion"] = SENTINELS["name"]
    before = copy.deepcopy(records)

    phi_guard.check_history(records)

    assert records == before


def test_assert_clean_raises_a_message_without_the_values() -> None:
    records = clean_history("unit")
    only_record(records)["softwareVersion"] = SENTINELS["name"]
    only_record(records)["extra"] = SENTINELS["birth"]

    with pytest.raises(AssertionError) as raised:
        phi_guard.assert_clean(records)

    message = str(raised.value)
    assert SENTINELS["name"] not in message
    assert SENTINELS["birth"] not in message
    assert "dob_pattern" in message
    assert "name_pattern" in message
    assert "unknown_field" in message


def test_assert_clean_returns_quietly_on_clean_data() -> None:
    phi_guard.assert_clean(clean_history("unit"))


def test_the_synthetic_fixtures_are_deterministic() -> None:
    assert clean_history("unit") == clean_history("unit")
    assert clean_history("unit") != clean_history("other")
    assert synthetic_case_id("unit") == synthetic_case_id("unit")
    assert synthetic_case_id("unit") != synthetic_case_id("other")


# --------------------------------------------------------------------------------------------
# 2. The httpx path, on a mock transport
# --------------------------------------------------------------------------------------------

TOKEN = "t" * 32


def _source(handler: Callable[[httpx.Request], httpx.Response]) -> GatewayHistory:
    return GatewayHistory(
        "http://gateway.test", TOKEN, transport=httpx.MockTransport(handler)
    )


def test_the_history_is_read_with_the_agent_token_header_only() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=clean_history("unit"))

    records = _source(handler).case_history(synthetic_case_id("unit"))

    assert records == clean_history("unit")
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == f"/ledger/cases/{synthetic_case_id('unit')}"
    assert seen[0].headers["X-Agent-Token"] == TOKEN
    assert "authorization" not in seen[0].headers
    assert seen[0].url.query == b""


def test_a_base_url_with_a_trailing_slash_does_not_double_it() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    source = GatewayHistory(
        "http://gateway.test/", TOKEN, transport=httpx.MockTransport(handler)
    )
    source.case_history(synthetic_case_id("unit"))
    source.create_artifact({})

    assert [request.url.path for request in seen] == [
        f"/ledger/cases/{synthetic_case_id('unit')}",
        "/ledger/artifacts",
    ]


def test_the_gateway_is_called_directly_whatever_the_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-110. A real server on the loopback and a proxy variable that points nowhere: with the
    environment trusted, the request would go to the proxy, token and records included."""
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *_args: object) -> None:
            return None

    # A free port, then bound by number: a server bound to port 0 refuses connections on
    # the WSL2 kernel of the workstation.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    try:
        base = f"http://127.0.0.1:{port}"
        records = GatewayHistory(base, TOKEN, timeout=10).case_history(
            synthetic_case_id("unit")
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    assert records == []
    assert seen == [f"/ledger/cases/{synthetic_case_id('unit')}"]


def test_an_artifact_is_created_through_the_gateway_with_the_body_as_given() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    body = client_body(clean_history("unit")[0])
    status = _source(handler).create_artifact(body)

    assert status == 200
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/ledger/artifacts"
    assert json.loads(seen[0].content) == body
    assert seen[0].headers["X-Agent-Token"] == TOKEN


def test_a_refused_artifact_answers_its_status_and_nothing_else() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {"code": "SCHEMA", "message": SENTINELS["name"], "details": {}}
            },
        )

    assert _source(handler).create_artifact({"a": 1}) == 400


@pytest.mark.parametrize("status", [401, 404, 500, 502])
def test_a_failed_history_raises_with_the_status_and_no_body_no_token(
    status: int,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        code = {401: "UNAUTHORIZED", 404: "NOT_FOUND"}.get(status, "UNAVAILABLE")
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": SENTINELS["name"],
                    "details": {},
                }
            },
        )

    with pytest.raises(LedgerAccessError) as raised:
        _source(handler).case_history(synthetic_case_id("unit"))

    message = str(raised.value)
    assert str(502 if status == 500 else status) in message
    assert SENTINELS["name"] not in message
    assert TOKEN not in message


@pytest.mark.parametrize("payload", [{"a": 1}, "text", 7, None])
def test_a_reply_that_is_not_a_list_is_not_an_empty_history(payload: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        # `json=None` would send no body at all: the JSON `null` is written out.
        return httpx.Response(200, content=json.dumps(payload).encode())

    with pytest.raises(LedgerAccessError, match="502"):
        _source(handler).case_history(synthetic_case_id("unit"))


def test_a_reply_that_is_not_json_raises_without_the_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SENTINELS["name"].encode())

    with pytest.raises(LedgerAccessError) as raised:
        _source(handler).case_history(synthetic_case_id("unit"))

    assert SENTINELS["name"] not in str(raised.value)


def test_an_unreachable_gateway_raises_without_the_url_or_the_token() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused http://gateway.test")

    with pytest.raises(LedgerAccessError) as raised:
        _source(handler).case_history(synthetic_case_id("unit"))

    assert TOKEN not in str(raised.value)
    assert "gateway.test" not in str(raised.value)


def test_a_case_id_outside_the_documented_form_is_not_sent() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    with pytest.raises(ValueError, match="case id"):
        _source(handler).case_history("CASE-1/../models")


def test_the_guard_uses_the_shared_ledgerclient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le basculement prévu par l09 appelle réellement IF-07, sans second client HTTP."""
    from saam.ledger import LedgerClient

    seen = []
    expected = clean_history("unit")

    def read(client: LedgerClient, case_id: str) -> list[dict[str, object]]:
        seen.append(case_id)
        return expected

    monkeypatch.setattr(LedgerClient, "get_case_history", read)
    assert ledger_path() == "ledgerclient"
    assert (
        _source(
            lambda _: pytest.fail("Le garde ne doit pas contourner IF-07")
        ).case_history(synthetic_case_id("unit"))
        == expected
    )
    assert seen == [synthetic_case_id("unit")]


# --------------------------------------------------------------------------------------------
# 3. The test network: the real path, through the gateway
# --------------------------------------------------------------------------------------------

SERVE_NAME = "saam-medtrace-gateway-serve"
SERVE_PORT = 18080
WRITER = "agent-ingestion"
READER = "verifier"


class LiveGateway:
    def __init__(
        self, writer: GatewayHistory, reader: GatewayHistory, run: str
    ) -> None:
        self.writer = writer
        self.reader = reader
        self.run = run


def test_stopping_the_serve_process_stops_what_it_started(tmp_path: Path) -> None:
    """The gateway is a grandchild of the script. After `stop` it is gone, not orphaned
    (`audit/round-8/tools/orphan-probe.sh` shows the orphan when only the script is signalled)."""
    pid_file = tmp_path / "grandchild.pid"
    tree = ProcessTree(
        [
            bash_executable(),
            "-c",
            f'sleep 300 & echo $! > "{pid_file.as_posix()}"; wait',
        ],
        cwd=ROOT,
        env=dict(os.environ),
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not (
        pid_file.exists() and pid_file.read_text().strip()
    ):
        time.sleep(0.2)
    grandchild = pid_file.read_text().strip()
    assert grandchild.isdigit(), "the script did not start its child"

    tree.stop()

    gone = False
    for _ in range(50):
        probe = subprocess.run(
            [bash_executable(), "-c", f"kill -0 {grandchild} 2>/dev/null"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            gone = True
            break
        time.sleep(0.2)
    if not gone:
        subprocess.run([bash_executable(), "-c", f"kill -9 {grandchild}"], check=False)
    assert gone, "the child of the script is still running after the stop"
    assert tree.process.poll() is not None


def _wait_until_serving(source: GatewayHistory, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the gateway stopped (exit {process.returncode})")
        try:
            source.case_history(synthetic_case_id("probe-the-server"))
        except LedgerAccessError:
            time.sleep(2)
        else:
            return
    raise AssertionError("the gateway did not answer within 240 s")


@pytest.fixture(scope="module")
def live_gateway(
    bash_run: Callable[..., subprocess.CompletedProcess[str]],
) -> Iterator[LiveGateway]:
    """The test network, the identities, and the real `server.js` of ledger-gateway behind a
    token file. One network for the module: a start costs minutes."""
    tokens_dir = Path(tempfile.mkdtemp(prefix="saam-no-phi-"))
    serve: ProcessTree | None = None
    try:
        started = bash_run(["fabric/network.sh", "start"], timeout=420)
        assert_ok(started, "start")
        enrolled = bash_run(["fabric/enroll-identities.sh"], timeout=900)
        assert_ok(enrolled, "enroll")

        writer_token = uuid.uuid4().hex + uuid.uuid4().hex
        reader_token = uuid.uuid4().hex + uuid.uuid4().hex
        token_file = tokens_dir / "tokens.json"
        token_file.write_text(json.dumps({WRITER: writer_token, READER: reader_token}))
        token_file.chmod(0o600)

        env = {
            "GATEWAY_SERVE_TOKEN_DIR": str(tokens_dir),
            "GATEWAY_SERVE_PORT": str(SERVE_PORT),
        }
        serve = ProcessTree(
            [bash_executable(), "fabric/gateway-serve.sh"],
            cwd=ROOT,
            env={**os.environ, **env},
        )
        base = f"http://127.0.0.1:{SERVE_PORT}"
        writer = GatewayHistory(base, writer_token)
        reader = GatewayHistory(base, reader_token)
        _wait_until_serving(reader, serve.process)
        yield LiveGateway(writer, reader, uuid.uuid4().hex[:12])
    finally:
        if serve is not None:
            serve.stop()
        bash_run(["-c", f"docker rm -f {SERVE_NAME}"], timeout=60)
        shutil.rmtree(tokens_dir, ignore_errors=True)
        bash_run(["fabric/network.sh", "stop"], timeout=180)


def _write_case(gateway: LiveGateway, label: str, **overrides: object) -> str:
    """Write the seven artifacts of a synthetic case; `overrides` apply to the first one."""
    case = synthetic_case_id(f"{gateway.run}-{label}")
    records = clean_history(f"{gateway.run}-{label}")
    for rank, record in enumerate(records):
        body = client_body(record)
        if rank == 0:
            body.update(overrides)
        status = gateway.writer.create_artifact(body)
        assert status == 200, (
            f"artifact {rank} of {label}: the gateway answered {status}"
        )
    assert records[0]["caseId"] == case
    return case


@pytest.mark.fabric
def test_the_history_of_a_clean_case_on_the_network_passes_the_guard(
    live_gateway: LiveGateway,
) -> None:
    case = _write_case(live_gateway, "clean")

    records = live_gateway.reader.case_history(case)

    assert len(records) == 7
    assert [record.get("artifactType") for record in records] == PIPELINE
    phi_guard.assert_clean(records)


@pytest.mark.fabric
def test_the_history_of_a_case_nobody_wrote_is_empty(live_gateway: LiveGateway) -> None:
    assert (
        live_gateway.reader.case_history(synthetic_case_id(f"{live_gateway.run}-none"))
        == []
    )


@pytest.mark.fabric
@pytest.mark.parametrize(
    "field", ["patientName", "birthDate", "diagnosis", "creatorAgent"]
)
def test_an_illegal_field_never_reaches_the_ledger(
    live_gateway: LiveGateway, field: str
) -> None:
    """The closed schema refuses the write (NFR-03), and the history stays clean."""
    label = f"field-{field}"
    case = synthetic_case_id(f"{live_gateway.run}-{label}")
    body = client_body(clean_history(f"{live_gateway.run}-{label}")[0])
    body[field] = "synthetic"

    status = live_gateway.writer.create_artifact(body)

    assert status == 400
    assert live_gateway.reader.case_history(case) == []


@pytest.mark.fabric
@pytest.mark.parametrize(
    ("label", "kind", "value"),
    [
        ("dob-iso", "dob_pattern", "1975-03-12"),
        ("dob-dotted", "dob_pattern", "12.03.1975"),
        ("name", "name_pattern", "Jean Dupont"),
    ],
)
def test_a_prohibited_pattern_that_the_schema_lets_through_is_detected_on_the_network(
    live_gateway: LiveGateway, label: str, kind: str, value: str
) -> None:
    """The schema bounds `softwareVersion` to a string of 64 characters and nothing more, so the
    chaincode stores a date or a name written there. The guard is the net under that gap."""
    case = _write_case(live_gateway, f"pattern-{label}", softwareVersion=value)

    records = live_gateway.reader.case_history(case)
    found = phi_guard.check_history(records)

    # The ledger accepted the write: seven records, and the guard finds the one that is not clean.
    assert len(records) == 7
    assert kind in kinds(found), phi_guard.describe(found)
    assert {violation.field for violation in found} == {"softwareVersion"}
    assert {violation.record for violation in found} == {0}
    # The diagnostics carry no value, whether they are read or raised.
    assert value not in phi_guard.describe(found)
    with pytest.raises(AssertionError) as raised:
        phi_guard.assert_clean(records)
    assert value not in str(raised.value)


@pytest.mark.fabric
def test_the_real_history_has_exactly_the_documented_fields(
    live_gateway: LiveGateway,
) -> None:
    case = _write_case(live_gateway, "fields")

    records = live_gateway.reader.case_history(case)

    assert all(set(record) == set(ARTIFACT_FIELDS) for record in records)
    assert all(record["docType"] == "artifact" for record in records)
    # What the chaincode adds comes from the certificate and the transaction (NFR-06).
    assert {record["creatorMspId"] for record in records} == {"Org1MSP"}
    assert {record["creatorAgent"] for record in records} == {"ingestion"}


@pytest.mark.fabric
def test_the_guard_output_on_the_network_carries_no_token_and_no_payload(
    live_gateway: LiveGateway,
) -> None:
    case = _write_case(live_gateway, "diagnostics", softwareVersion="1975-03-12")
    records = live_gateway.reader.case_history(case)

    text = phi_guard.describe(phi_guard.check_history(records))

    assert "1975" not in text
    assert live_gateway.reader.token not in text
    assert live_gateway.writer.token not in text
    assert case not in text
