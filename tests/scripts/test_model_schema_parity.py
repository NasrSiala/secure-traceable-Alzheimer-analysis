"""The gateway validates MODEL before the chaincode does. Both copies must agree.

Same reason as test_artifact_schema_parity.py (AUD-081): `ledger-gateway/src/app.ts` repeats the
closed MODEL schema of `chaincode/provenance/src/model.ts` (Schema section 5.2). If one changes
alone, the gateway refuses what the chaincode accepts, or passes what the chaincode will refuse.
These tests read both sources and compare; they need neither Node nor Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def gateway(repo_root: Path) -> str:
    return (repo_root / "ledger-gateway" / "src" / "app.ts").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def model(repo_root: Path) -> str:
    return (repo_root / "chaincode" / "provenance" / "src" / "model.ts").read_text(
        encoding="utf-8"
    )


@pytest.fixture(scope="module")
def artifact(repo_root: Path) -> str:
    return (repo_root / "chaincode" / "provenance" / "src" / "artifact.ts").read_text(
        encoding="utf-8"
    )


def _quoted(block: str) -> list[str]:
    return re.findall(r'"([^"]+)"', block)


def _block(gateway: str, declaration: str) -> str:
    start = gateway.index(declaration)
    return gateway[start : gateway.index("} as const;", start)]


def test_the_field_lists_are_the_same(gateway: str, model: str) -> None:
    client = re.search(
        r"CLIENT_FIELDS = new Set<string>\(\[(.*?)\]\)", model, re.DOTALL
    )
    assert client, "CLIENT_FIELDS not found in model.ts"
    fields = _quoted(client.group(1))
    body = _block(gateway, "const modelBody = {")
    properties = body[body.index("properties:") :]
    assert sorted(re.findall(r"^    (\w+): ", properties, re.MULTILINE)) == sorted(
        fields
    )
    required = re.search(r"required:\s*\[(.*?)\]", body, re.DOTALL)
    assert required, "required list not found in modelBody"
    # Every client field is required: MODEL has no optional field.
    assert sorted(_quoted(required.group(1))) == sorted(fields)


@pytest.mark.parametrize(
    ("chaincode_name", "gateway_name"),
    [("NAME", "MODEL_NAME"), ("VERSION", "MODEL_VERSION")],
)
def test_the_name_and_version_patterns_are_the_same(
    gateway: str, model: str, chaincode_name: str, gateway_name: str
) -> None:
    in_chaincode = re.search(rf"const {chaincode_name} = /(.*)/;", model)
    assert in_chaincode, f"{chaincode_name} not found in model.ts"
    in_gateway = re.search(rf'const {gateway_name} = "(.*)";', gateway)
    assert in_gateway, f"{gateway_name} not found in app.ts"
    # The TypeScript string escapes the backslash that the regular expression literal has.
    assert in_gateway.group(1).replace("\\\\", "\\") == in_chaincode.group(1)


def test_the_hash_pattern_is_the_one_of_artifacts(gateway: str, artifact: str) -> None:
    in_chaincode = re.search(r"const SHA256 = /(.*)/;", artifact)
    assert in_chaincode, "SHA256 not found in artifact.ts"
    body = _block(gateway, "const modelBody = {")
    in_gateway = re.search(r'sha256: \{[^}]*pattern: "([^"]+)"', body)
    assert in_gateway, "sha256 not found in modelBody"
    assert in_gateway.group(1) == in_chaincode.group(1)


def test_the_framework_bounds_are_the_same(gateway: str, model: str) -> None:
    bound = re.search(r"text\.length < (\d+) \|\| text\.length > (\d+)", model)
    assert bound, "framework bounds not found in model.ts"
    low, high = bound.groups()
    body = _block(gateway, "const modelBody = {")
    assert re.search(
        rf'framework: \{{ type: "string", minLength: {low}, maxLength: {high} \}}', body
    )


def test_the_routes_check_the_same_patterns_as_the_body(gateway: str) -> None:
    """A lookup and a registration refuse the same names and versions."""
    params = _block(gateway, "const modelParams = {")
    assert 'name: { type: "string", pattern: MODEL_NAME }' in params
    assert 'version: { type: "string", pattern: MODEL_VERSION }' in params
    body = _block(gateway, "const modelBody = {")
    assert 'name: { type: "string", pattern: MODEL_NAME }' in body
    assert 'version: { type: "string", pattern: MODEL_VERSION }' in body


def test_the_case_pattern_is_the_one_of_artifacts(gateway: str, artifact: str) -> None:
    in_chaincode = re.search(r"const CASE_ID = /(.*)/;", artifact)
    assert in_chaincode, "CASE_ID not found in artifact.ts"
    params = _block(gateway, "const caseParams = {")
    in_gateway = re.search(r'caseId: \{[^}]*pattern: "([^"]+)"', params)
    assert in_gateway, "caseId not found in caseParams"
    assert in_gateway.group(1) == in_chaincode.group(1)
