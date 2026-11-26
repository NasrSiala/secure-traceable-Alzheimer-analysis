"""Lecture sans écriture pour vérifier la passerelle et le chaincode existant."""

from __future__ import annotations

import httpx

PROBE_ARTIFACT_ID = "00000000-0000-0000-0000-000000000000"


async def ledger_available(client: httpx.AsyncClient, url: str, token: str) -> bool:
    if not token:
        return False
    try:
        response = await client.get(
            f"{url.rstrip('/')}/ledger/artifacts/{PROBE_ARTIFACT_ID}",
            headers={"X-Agent-Token": token},
        )
        body = response.json()
        if not isinstance(body, dict):
            return False
        if response.status_code == 404:
            return body == {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "artifactId is not on the ledger",
                    "details": {},
                }
            }
        return (
            response.status_code == 200
            and body.get("artifactId") == PROBE_ARTIFACT_ID
            and body.get("docType") == "ARTIFACT"
        )
    except (httpx.HTTPError, ValueError):
        return False
