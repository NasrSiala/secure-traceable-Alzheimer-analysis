"""How the NFR-03 guard reaches the ledger: the gateway of IF-09, over HTTP, with `httpx`.

Plan l09: the guard goes through `LedgerClient` (`saam.ledger`, T2.7, role B). Until that library
exists the approved path is this one, an `httpx` client of the documented routes (TRD 8.2):
`POST /ledger/artifacts` and `GET /ledger/cases/{caseId}`, authenticated by `X-Agent-Token`.

An error never carries a body, a URL or a token: the gateway's answer can hold the words of a
chaincode refusal, and the guard handles data that must not be printed.
"""

from __future__ import annotations

import importlib.util
import re
from typing import Any

import httpx

_CASE_ID = re.compile(r"^CASE-[0-9a-f-]{36}$")


class LedgerAccessError(Exception):
    """The ledger could not be read or written. The message has no body, URL or token."""


def ledger_path() -> str:
    """`ledgerclient` when `saam.ledger` can be imported, else `httpx` (the approved fallback)."""
    try:
        found = importlib.util.find_spec("saam.ledger") is not None
    except ModuleNotFoundError:
        found = False
    return "ledgerclient" if found else "httpx"


class GatewayHistory:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.token = token
        self._transport = transport
        self._timeout = timeout

    def _request(
        self, method: str, path: str, *, body: dict[str, object] | None = None
    ) -> httpx.Response:
        try:
            # trust_env=False: the gateway is called directly. With the default, an
            # HTTP_PROXY of the environment would carry the token and the records to the proxy
            # (AUD-110).
            with httpx.Client(
                transport=self._transport, timeout=self._timeout, trust_env=False
            ) as client:
                return client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers={"X-Agent-Token": self.token},
                    json=body,
                )
        except httpx.HTTPError:
            raise LedgerAccessError("the gateway could not be reached") from None

    def case_history(self, case_id: str) -> list[Any]:
        """`GET /ledger/cases/{caseId}`: the records of a case, as the gateway returns them."""
        if not _CASE_ID.match(case_id):
            raise ValueError("case id outside the documented form")
        response = self._request("GET", f"/ledger/cases/{case_id}")
        if response.status_code != 200:
            raise LedgerAccessError(
                f"GET /ledger/cases answered {response.status_code}"
            )
        try:
            payload: object = response.json()
        except ValueError:
            raise LedgerAccessError(
                "GET /ledger/cases answered a body that is not JSON"
            ) from None
        if not isinstance(payload, list):
            raise LedgerAccessError(
                "GET /ledger/cases answered a body that is not a list"
            )
        return payload

    def create_artifact(self, body: dict[str, object]) -> int:
        """`POST /ledger/artifacts`: the status of the answer (200 stored, 400 refused, ...)."""
        return self._request("POST", "/ledger/artifacts", body=body).status_code
