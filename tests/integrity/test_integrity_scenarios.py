"""Les six scénarios d'intégrité de T5.1 sur l'API et les octets chiffrés réels."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from saam.cases import CaseService
from saam.traceability import AnchoringError, ArtifactFile
from scripts.tamper import tamper_case
from tests.api import conftest as api_fixtures
from tests.api import test_verifications
from tests.api.test_cases_create import headers

auth_service = api_fixtures.auth_service
api_verification = test_verifications.api_verification
traceability_case = test_verifications.traceability_case
verification_case = test_verifications.verification_case


@pytest.fixture
def seven_artifacts(api_verification, traceability_case, scenario):
    api, path, artifacts, store, fabric, effects, calls = api_verification
    tool = traceability_case[0]
    for kind, agent in (
        ("validation", "validation"),
        ("explanation", "explanation"),
        ("final_result", "finalization"),
    ):
        parent = artifacts[-1]
        artifact = replace(
            parent,
            id=str(uuid4()),
            type=kind,
            agent=agent,
            parent_id=parent.id,
            created_at=parent.created_at + timedelta(seconds=1),
            files=(ArtifactFile(f"{kind}.json", "application/json", b"{}"),),
        )
        if scenario == "absent_sur_fabric" and kind == "final_result":
            previous = fabric.failures
            fabric.failures = fabric.calls + 4
            try:
                with pytest.raises(AnchoringError):
                    tool.record(artifact)
            finally:
                fabric.failures = previous
            assert artifact.id not in fabric.records
        else:
            tool.record(artifact)
        artifacts.append(artifact)
    if scenario != "absent_sur_fabric":
        with psycopg.connect(tool.database_url) as db:
            db.execute(
                "UPDATE cases SET status='termine', decision='revision_requise',completed_at=now() WHERE id=%s",
                (artifacts[0].case_id,),
            )
    return (
        api,
        path,
        artifacts,
        store,
        fabric,
        effects,
        calls,
        CaseService(tool.database_url),
    )


@pytest.mark.parametrize(
    ("scenario", "expected", "valid", "reachable"),
    [
        ("tout_valide", "valide", 7, True),
        ("octet_chiffre_modifie", "modifie", 6, True),
        ("rechiffre_altere", "modifie", 6, True),
        ("fichier_supprime", "manquant", 6, True),
        ("absent_sur_fabric", "non_verifiable", 6, True),
        ("fabric_arrete", "non_verifiable", 0, False),
    ],
)
def test_integrity_scenarios(seven_artifacts, scenario, expected, valid, reachable):
    api, path, artifacts, store, _, effects, calls, cases = seven_artifacts
    kind = "final_result" if scenario == "absent_sur_fabric" else "prediction"
    target_artifact = next(artifact for artifact in artifacts if artifact.type == kind)
    name = target_artifact.files[0].name
    target = store.path(target_artifact.id, name)
    original = target.read_bytes()
    if scenario == "octet_chiffre_modifie":
        assert (
            tamper_case(cases, store, target_artifact.case_id, "prediction", "raw")
            == name
        )
        assert (
            sum(a != b for a, b in zip(target.read_bytes(), original, strict=True)) == 1
        )
    elif scenario == "rechiffre_altere":
        assert (
            tamper_case(
                cases, store, target_artifact.case_id, "prediction", "reencrypt"
            )
            == name
        )
        assert store.read(target_artifact.id, name) != target_artifact.files[0].data
    elif scenario == "fichier_supprime":
        target.unlink()
    elif scenario == "fabric_arrete":
        effects["outage"] = True

    auth = headers(api, "auditor")
    response = api.post(path, headers=auth)
    assert response.status_code == 201
    result = response.json()
    assert result["ledger_reachable"] is reachable
    assert result["count_valide"] == valid
    assert len(result["items"]) == 7
    for item in result["items"]:
        status = (
            expected
            if item["artifact_id"] == target_artifact.id or not reachable
            else "valide"
        )
        assert item["status"] == status
        if status == "non_verifiable":
            assert item["expected_sha256"] is None
    if scenario == "rechiffre_altere":
        altered = next(
            item for item in result["items"] if item["artifact_type"] == "prediction"
        )
        assert altered["computed_sha256"] is not None
        assert altered["computed_sha256"] != altered["expected_sha256"]
    if not reachable:
        assert len(calls) == 1
    assert api.get(path, headers=auth).json()["items"] == [result]
