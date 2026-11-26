"""Accès du garde NFR-03 au registre via le client partagé IF-07 (T2.7)."""

from __future__ import annotations

import re
from typing import Any

import httpx

from saam.ledger import LedgerClient, LedgerError

_CASE_ID = re.compile(r"CASE-[0-9a-f-]{36}")


class LedgerAccessError(Exception):
    """Le registre est inaccessible ; message sans corps, URL ou jeton."""


def ledger_path() -> str:
    """Le garde utilise exclusivement LedgerClient (IF-07)."""
    return "ledgerclient"


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

    def _client(self) -> LedgerClient:
        return LedgerClient(
            self._base_url, self.token, transport=self._transport, timeout=self._timeout
        )

    def case_history(self, case_id: str) -> list[Any]:
        """Lit l'historique, ou refuse toute réponse illisible/non vérifiable."""
        if not _CASE_ID.fullmatch(case_id):
            raise ValueError("case id outside the documented form")
        try:
            with self._client() as client:
                return client.get_case_history(case_id)
        except LedgerError as error:
            raise LedgerAccessError(
                f"GET /ledger/cases answered {error.status}"
            ) from None

    def create_artifact(self, body: dict[str, object]) -> int:
        """Écriture : statut IF-09 sans exposer le contenu d'une erreur."""
        try:
            with self._client() as client:
                client.create_record(body)
            return 200
        except LedgerError as error:
            return error.status
