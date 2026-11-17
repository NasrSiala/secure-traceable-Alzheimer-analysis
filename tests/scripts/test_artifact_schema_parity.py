"""The gateway validates ARTIFACT before the chaincode does. Both copies must agree.

AUD-081: `ledger-gateway/src/app.ts` repeats the closed schema of
`chaincode/provenance/src/artifact.ts` (Schema section 5.2). If one changes alone, the gateway
refuses what the chaincode accepts, or passes what the chaincode will refuse. These tests read
both sources and compare; they need neither Node nor Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def gateway(repo_root: Path) -> str:
    return (repo_root / "ledger-gateway" / "src" / "app.ts").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def chaincode(repo_root: Path) -> str:
    return (repo_root / "chaincode" / "provenance" / "src" / "artifact.ts").read_text(
        encoding="utf-8"
    )


def _quoted(block: str) -> list[str]:
    return re.findall(r'"([^"]+)"', block)


def _gateway_object(gateway: str) -> str:
    start = gateway.index("const artifactBody = {")
    return gateway[start : gateway.index("} as const;", start)]


def _gateway_required(gateway: str) -> list[str]:
    block = _gateway_object(gateway)
    match = re.search(r"required:\s*\[(.*?)\]", block, re.DOTALL)
    assert match, "required list not found in app.ts"
    return _quoted(match.group(1))


def _gateway_properties(gateway: str) -> list[str]:
    block = _gateway_object(gateway)
    properties = block[block.index("properties:") :]
    return re.findall(r"^    (\w+): ", properties, re.MULTILINE)


def test_the_type_list_is_the_same_and_in_the_same_order(
    gateway: str, chaincode: str
) -> None:
    match = re.search(r"enum:\s*\[(.*?)\]", _gateway_object(gateway), re.DOTALL)
    assert match, "artifactType enum not found in app.ts"
    declared = re.search(r"ARTIFACT_TYPES = \[(.*?)\] as const", chaincode, re.DOTALL)
    assert declared, "ARTIFACT_TYPES not found in artifact.ts"
    assert _quoted(match.group(1)) == _quoted(declared.group(1))
    assert len(_quoted(declared.group(1))) == 7


def test_the_field_lists_are_the_same(gateway: str, chaincode: str) -> None:
    client = re.search(
        r"CLIENT_FIELDS = new Set<string>\(\[(.*?)\]\)", chaincode, re.DOTALL
    )
    assert client, "CLIENT_FIELDS not found in artifact.ts"
    fields = _quoted(client.group(1))
    assert sorted(_gateway_properties(gateway)) == sorted(fields)
    # modelVersion is the one optional field, in both places.
    assert sorted(_gateway_required(gateway)) == sorted(set(fields) - {"modelVersion"})
    assert "modelVersion" in chaincode.split("function parseClientArtifact")[1]


@pytest.mark.parametrize(
    ("name", "gateway_field"),
    [("UUID", "artifactId"), ("CASE_ID", "caseId"), ("SHA256", "sha256")],
)
def test_the_patterns_are_the_same(
    gateway: str, chaincode: str, name: str, gateway_field: str
) -> None:
    in_chaincode = re.search(rf"const {name} = /(.*)/;", chaincode)
    assert in_chaincode, f"{name} not found in artifact.ts"
    if name == "UUID":
        in_gateway = re.search(r'const UUID = "(.*)";', gateway)
    else:
        in_gateway = re.search(
            rf'{gateway_field}: \{{[^}}]*pattern: "([^"]+)"', gateway
        )
    assert in_gateway, f"{name} not found in app.ts"
    assert in_gateway.group(1) == in_chaincode.group(1)


def test_the_length_bounds_are_the_same(gateway: str, chaincode: str) -> None:
    bound = re.search(r"text\.length < (\d+) \|\| text\.length > (\d+)", chaincode)
    assert bound, "boundedString not found in artifact.ts"
    low, high = bound.groups()
    block = _gateway_object(gateway)
    bounded = rf'\{{ type: "string", minLength: {low}, maxLength: {high} \}}'
    assert re.search(rf"softwareVersion: {bounded}", block), "softwareVersion"
    assert re.search(
        rf'modelVersion: \{{\s*anyOf: \[\{{ type: "null" \}}, {bounded}\],?\s*\}}',
        block,
    ), "modelVersion"


def test_the_off_chain_reference_rule_is_the_same(gateway: str, chaincode: str) -> None:
    rule = "artifact://${artifactId}"
    assert f"offchainRef !== `{rule}`" in chaincode
    assert "body.offchainRef !== `artifact://${body.artifactId}`" in gateway
