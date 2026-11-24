"""Deterministic synthetic data for the NFR-03 guard. Nothing here comes from a real person.

`clean_history(label)` is the history of one case as `GetCaseHistory` returns it: seven ARTIFACT
records, parent to child, with the fields the chaincode adds. The same label gives the same
records, so a failure can be reproduced; two labels give two cases that do not collide on a
ledger that keeps everything.
"""

from __future__ import annotations

import hashlib
import uuid

from phi_guard import ARTIFACT_TYPES, CLIENT_FIELDS

PIPELINE = list(ARTIFACT_TYPES)

_NAMESPACE = uuid.UUID("0b5a3f40-6d2c-4f43-9c7e-2f1d8a4b9e10")

# The subject of the certificate of an agent of Org1 on the test network, as the chaincode
# stores it in `creatorId`.
_CREATOR_ID = "/C=US/ST=North Carolina/O=Hyperledger/OU=client/CN=agent-ingestion"


def synthetic_case_id(label: str) -> str:
    return f"CASE-{uuid.uuid5(_NAMESPACE, f'{label}/case')}"


def _artifact_id(label: str, rank: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{label}/artifact/{rank}"))


def clean_history(label: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for rank, artifact_type in enumerate(PIPELINE):
        artifact_id = _artifact_id(label, rank)
        records.append(
            {
                "docType": "artifact",
                "artifactId": artifact_id,
                "caseId": synthetic_case_id(label),
                "artifactType": artifact_type,
                "sha256": hashlib.sha256(f"{label}/{rank}".encode()).hexdigest(),
                "createdAt": f"2026-11-09T12:00:{rank:02d}.000Z",
                "txTimestamp": f"2026-11-09T12:00:{rank:02d}.500Z",
                "softwareVersion": "0.1.0",
                "modelVersion": None,
                "parentArtifactId": _artifact_id(label, rank - 1) if rank > 0 else None,
                "offchainRef": f"artifact://{artifact_id}",
                "creatorMspId": "Org1MSP",
                "creatorId": _CREATOR_ID,
                "creatorAgent": "ingestion",
            }
        )
    return records


def client_body(record: dict[str, object]) -> dict[str, object]:
    """What a client sends to create the artifact: the fields the chaincode does not set."""
    return {field: record[field] for field in CLIENT_FIELDS}
