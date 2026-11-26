"""T3.17 : cinq ECG publics jusqu'aux reçus Fabric sur la pile intégrée."""

from __future__ import annotations

import csv
import json
import os
import re
import ssl
import subprocess
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from saam.hashing import canonical_manifest, file_hash
from scripts.demo import _authenticate, _object, read_environment, record_pair

KINDS = (
    "original",
    "processed",
    "features",
    "prediction",
    "validation",
    "explanation",
    "final_result",
)
CASE_COUNT = 5
P95_LIMIT_SECONDS = 60

# Lire les manifestes dans le conteneur API, dont le volume est en lecture seule.
# Les données ECG et la clé restent dans leurs emplacements respectifs.
READ_EVIDENCE = '''
import json
import sys
from saam.identity.auth import IdentityService
from saam.storage import ArtifactStore

case_id, *artifact_ids = sys.argv[1:]
with IdentityService.from_environment().connect() as db:
    versions = db.execute("""
        SELECT m.version AS model_version, v.version AS validation_config_version
        FROM cases c LEFT JOIN models m ON m.id = c.model_id
        LEFT JOIN validation_configs v ON v.id = c.validation_config_id
        WHERE c.id = %s
    """, (case_id,)).fetchone()
store = ArtifactStore.from_environment()
manifests = [store.read(artifact_id, "manifest.json").decode("utf-8")
             for artifact_id in artifact_ids]
print(json.dumps({"versions": versions, "manifests": manifests}))
'''


def _fold10_pairs(dataset: Path) -> list[tuple[int, tuple[Path, Path]]]:
    with (dataset / "ptbxl_database.csv").open(
        encoding="utf-8-sig", newline=""
    ) as metadata:
        ids = sorted(
            {
                int(row["ecg_id"])
                for row in csv.DictReader(metadata)
                if row["strat_fold"] == "10"
            }
        )
    assert len(ids) >= CASE_COUNT, "Cinq ECG distincts du fold 10 sont requis."
    return [
        (record, record_pair(dataset, f"{record:05d}")) for record in ids[:CASE_COUNT]
    ]


def _process_case(
    client: httpx.Client, auth: dict[str, str], pair: tuple[Path, Path]
) -> tuple[str, dict]:
    header, signal = pair
    with header.open("rb") as hea, signal.open("rb") as dat:
        case = _object(
            client.post(
                "/api/v1/cases",
                headers=auth,
                files=[
                    ("ecg_files[]", (header.name, hea, "text/plain")),
                    ("ecg_files[]", (signal.name, dat, "application/octet-stream")),
                ],
            ),
            202,
        )
    case_id = str(UUID(case["id"]))
    deadline = time.monotonic() + 120
    while True:
        detail = _object(client.get(f"/api/v1/cases/{case_id}", headers=auth), 200)
        status = detail["status"]
        if status == "termine":
            final = detail["final_result"]
            assert final and not final.get("simulation"), (
                f"{case_id} : résultat réel absent."
            )
            return case_id, detail
        assert status in {"en_attente", "en_cours"}, f"{case_id} : statut {status}."
        remaining = deadline - time.monotonic()
        assert remaining > 0, f"{case_id} : résultat final absent après 120 s."
        time.sleep(min(0.5, remaining))


def _stored_evidence(root: Path, case_id: str, artifact_ids: list[str]) -> dict:
    command = ["docker", "compose", "exec", "-T", "api", "python", "-c", READ_EVIDENCE]
    result = subprocess.run(
        [*command, case_id, *artifact_ids],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"{case_id} : lecture des manifestes impossible."
    return json.loads(result.stdout)


def _check_evidence(
    case_id: str, detail: dict, history: list[dict], evidence: dict
) -> tuple[float, set[str]]:
    assert [entry["artifactType"] for entry in history] == list(KINDS)
    displayed = {artifact["type"]: artifact for artifact in detail["artifacts"]}
    assert len(detail["artifacts"]) == len(KINDS) and displayed.keys() == set(KINDS)
    versions = evidence["versions"]
    assert versions["model_version"], "Modèle du cas absent."
    assert type(versions["validation_config_version"]) is int, (
        "Configuration du cas absente."
    )

    tx_ids: set[str] = set()
    artifact_ids: set[str] = set()
    software_versions: set[str] = set()
    parent = None
    for entry, raw in zip(history, evidence["manifests"], strict=True):
        kind, artifact_id = entry["artifactType"], entry["artifactId"]
        assert entry["caseId"] == f"CASE-{case_id}"
        assert artifact_id not in artifact_ids and entry["parentArtifactId"] == parent
        artifact_ids.add(artifact_id)
        local = displayed[kind]
        tx_id = entry["txId"]
        assert re.fullmatch(r"[0-9a-f]{64}", tx_id) and tx_id not in tx_ids
        tx_ids.add(tx_id)
        assert local["anchor_status"] == "ancre" and local["id"] == artifact_id
        assert local["tx_id"] == tx_id and local["sha256"] == entry["sha256"]

        encoded = raw.encode("utf-8")
        manifest = json.loads(raw)
        assert canonical_manifest(manifest) == encoded, (
            f"{kind} : manifeste non canonique."
        )
        assert file_hash(encoded) == entry["sha256"], (
            f"{kind} : empreinte Fabric différente."
        )
        assert (manifest["artifact_id"], manifest["case_id"], manifest["type"]) == (
            artifact_id,
            case_id,
            kind,
        )
        assert manifest["parent_artifact_id"] == parent
        assert manifest["software_version"] == entry["softwareVersion"]
        assert manifest["model_version"] == entry["modelVersion"]
        software_versions.add(manifest["software_version"])
        metadata = manifest["metadata"]
        assert not metadata.get("simulation"), f"{kind} : artefact simulé."
        if kind == "processed":
            fir_coef_id = metadata.get("fir_coef_id")
            assert isinstance(fir_coef_id, str) and re.fullmatch(
                r"[0-9a-f]{8}", fir_coef_id
            )
        elif kind == "prediction":
            assert manifest["model_version"] == versions["model_version"]
        elif kind == "validation":
            version = metadata.get(
                "validation_config_version", metadata.get("config_version")
            )
            assert (
                type(version) is int
                and version == versions["validation_config_version"]
            )
        parent = artifact_id

    assert len(software_versions) == 1
    assert re.fullmatch(r"[0-9a-f]{7,40}", software_versions.pop()), (
        "SHA Git logiciel absent."
    )
    created = datetime.fromisoformat(detail["created_at"])
    anchored = datetime.fromisoformat(displayed["final_result"]["anchored_at"])
    elapsed = (anchored - created).total_seconds()
    assert elapsed >= 0, "Ancrage final daté avant la création."
    return elapsed, tx_ids


@pytest.mark.stack
@pytest.mark.skipif(
    os.environ.get("SAAM_TEST_PIPELINE") != "1",
    reason="T3.17 requiert la pile intégrée avec les agents réels ; SAAM_TEST_PIPELINE=1.",
)
def test_pipeline_fold_10(repo_root: Path) -> None:
    values = read_environment(repo_root / ".env")
    dataset = Path(values.get("PTBXL_ROOT") or repo_root / "ml/data/ptb-xl/1.0.3")
    pairs = _fold10_pairs(dataset)
    url = httpx.URL(
        values.get("SAAM_T317_URL")
        or f"https://localhost:{values.get('HTTPS_PORT') or '443'}"
    )
    assert (
        url.scheme == "https"
        and url.host
        and not url.userinfo
        and url.path in {"", "/"}
        and not url.query
        and not url.fragment
    ), "L'origine HTTPS de la pile locale est requise."
    certificate = Path(
        values.get("SAAM_T317_CA_FILE") or repo_root / "secrets/localhost.crt"
    )
    tls = ssl.create_default_context(cafile=str(certificate))
    tx_ids: set[str] = set()
    durations = []
    with httpx.Client(base_url=url, verify=tls, timeout=15, trust_env=False) as client:
        auth = _authenticate(client, values, "operator")
        for record, pair in pairs:
            case_id, detail = _process_case(client, auth, pair)
            response = client.get(f"/api/v1/cases/{case_id}/history", headers=auth)
            assert response.status_code == 200, (
                f"{case_id} : lecture Fabric indisponible."
            )
            history = response.json()
            assert len(history) == len(KINDS)
            artifact_ids = [str(UUID(entry["artifactId"])) for entry in history]
            evidence = _stored_evidence(repo_root, case_id, artifact_ids)
            duration, receipts = _check_evidence(case_id, detail, history, evidence)
            assert tx_ids.isdisjoint(receipts), f"{case_id} : reçu Fabric réutilisé."
            tx_ids.update(receipts)
            durations.append(duration)
            print(f"PTB-XL {record:05d} | CASE-{case_id} | 7 reçus | {duration:.3f} s")

    # Au rang le plus proche, ceil(0,95 × 5) = 5.
    p95 = max(durations)
    assert len(tx_ids) == CASE_COUNT * len(KINDS)
    assert p95 <= P95_LIMIT_SECONDS, f"p95 = {p95:.3f} s, limite 60 s."


def test_selects_five_distinct_fold_10_records(tmp_path: Path) -> None:
    (tmp_path / "ptbxl_database.csv").write_text(
        "ecg_id,strat_fold\n6,10\n4,10\n1,9\n5,10\n2,10\n3,10\n2,10\n7,10\n",
        encoding="utf-8",
    )
    records = tmp_path / "records500" / "00000"
    records.mkdir(parents=True)
    for record in range(2, 7):
        for extension in (".hea", ".dat"):
            (records / f"{record:05d}_hr{extension}").touch()
    assert [record for record, _ in _fold10_pairs(tmp_path)] == [2, 3, 4, 5, 6]


@pytest.mark.parametrize(
    "defect", [None, "simulation", "wrong_config", "wrong_hash", "reused_receipt"]
)
def test_evidence_checks(defect: str | None) -> None:
    case_id = str(uuid4())
    detail: dict = {"created_at": "2026-11-26T12:00:00Z", "artifacts": []}
    evidence: dict = {
        "versions": {"model_version": "1.0.0", "validation_config_version": 2},
        "manifests": [],
    }
    history = []
    parent = None
    for index, kind in enumerate(KINDS):
        artifact_id = str(uuid4())
        model_version = "1.0.0" if kind == "prediction" else None
        metadata = {
            "processed": {"fir_coef_id": "abababab"},
            "validation": {
                "validation_config_version": 1 if defect == "wrong_config" else 2
            },
            "final_result": {"simulation": defect == "simulation"},
        }.get(kind, {})
        manifest = canonical_manifest(
            {
                "artifact_id": artifact_id,
                "case_id": case_id,
                "type": kind,
                "parent_artifact_id": parent,
                "created_at": detail["created_at"],
                "software_version": "a" * 40,
                "model_version": model_version,
                "metadata": metadata,
                "files": [],
            }
        )
        digest = (
            "b" * 64
            if defect == "wrong_hash" and kind == "processed"
            else file_hash(manifest)
        )
        tx_id = f"{0 if defect == 'reused_receipt' else index:064x}"
        evidence["manifests"].append(manifest.decode())
        history.append(
            {
                "artifactType": kind,
                "artifactId": artifact_id,
                "caseId": f"CASE-{case_id}",
                "parentArtifactId": parent,
                "txId": tx_id,
                "sha256": digest,
                "softwareVersion": "a" * 40,
                "modelVersion": model_version,
            }
        )
        detail["artifacts"].append(
            {
                "type": kind,
                "id": artifact_id,
                "anchor_status": "ancre",
                "anchored_at": "2026-11-26T12:00:42Z",
                "tx_id": tx_id,
                "sha256": digest,
            }
        )
        parent = artifact_id

    if defect is None:
        seconds, receipts = _check_evidence(case_id, detail, history, evidence)
        assert seconds == 42 and len(receipts) == 7
    else:
        with pytest.raises(AssertionError):
            _check_evidence(case_id, detail, history, evidence)
