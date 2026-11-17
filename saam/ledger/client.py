"""IF-07 : client synchrone HTTP, sans clés Fabric ni réessais implicites."""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

Record = dict[str, Any]
UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
IDENTITIES = {
    **{
        name: (f"agent-{name}", f"AGENT_TOKEN_{name.upper()}")
        for name in (
            "ingestion",
            "preparation",
            "features",
            "prediction",
            "validation",
            "explanation",
            "finalization",
        )
    },
    "verifier": ("verifier", "AGENT_TOKEN_VERIFIER"),
    "model-admin": ("model-admin", "AGENT_TOKEN_MODEL_ADMIN"),
}


class LedgerError(Exception):
    """Erreur sûre à remonter ; aucune réponse brute ni secret de transport."""

    message = "Erreur du registre."

    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(self.message)


class LedgerUnavailable(LedgerError):
    message = "Registre indisponible. Réessayer."

    def __init__(self) -> None:
        super().__init__(502, "UNAVAILABLE")


class DuplicateRecord(LedgerError):
    message = "Cet enregistrement existe déjà dans le registre."


class RecordNotFound(LedgerError):
    message = "Enregistrement introuvable dans le registre."


class InvalidRecord(LedgerError):
    message = "Enregistrement invalide ou parent manquant."


class LedgerForbidden(LedgerError):
    message = "Accès au registre non autorisé."


FAILURES: dict[int, tuple[str, type[LedgerError]]] = {
    400: ("SCHEMA", InvalidRecord),
    401: ("UNAUTHORIZED", LedgerForbidden),
    403: ("FORBIDDEN", LedgerForbidden),
    404: ("NOT_FOUND", RecordNotFound),
    409: ("DUPLICATE", DuplicateRecord),
    422: ("PARENT_MISSING", InvalidRecord),
}


class Ledger(Protocol):
    """Interface remplaçable par les domaines consommateurs (NFR-13)."""

    def create_record(self, record: Mapping[str, Any]) -> Record: ...
    def get_record(self, artifact_id: str) -> Record: ...
    def get_case_history(self, case_id: str) -> list[Record]: ...
    def register_model(self, model: Mapping[str, Any]) -> Record: ...
    def get_model(self, name: str, version: str) -> Record: ...


def checked_segment(value: str, pattern: str) -> str:
    if not re.fullmatch(pattern, value):
        raise InvalidRecord(400, "SCHEMA")
    return value


class LedgerClient:
    """Une instance par identité ; fermer le pool avec close ou un bloc with."""

    def __init__(
        self,
        base_url: str,
        agent_token: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = httpx.URL(base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("URL de passerelle invalide : origine HTTP(S) requise.")
        if (
            len(agent_token) < 16
            or not agent_token.isascii()
            or any(character.isspace() for character in agent_token)
        ):
            raise ValueError("Jeton de service invalide.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Délai HTTP positif requis.")
        self._http = httpx.Client(
            base_url=str(url),
            headers={"X-Agent-Token": agent_token},
            timeout=timeout,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )

    @classmethod
    def from_environment(cls, agent: str = "verifier") -> LedgerClient:
        if agent not in IDENTITIES:
            raise ValueError("Identité de service inconnue.")
        identity, variable = IDENTITIES[agent]
        token = os.environ.get(variable, "")
        if not token and os.environ.get("AGENT_TOKEN_FILE"):
            try:
                pairs = json.loads(
                    Path(os.environ["AGENT_TOKEN_FILE"]).read_text(encoding="utf-8")
                )
                token = pairs[identity]
                if not isinstance(token, str):
                    raise ValueError
            except (OSError, ValueError, KeyError, TypeError):
                raise ValueError(
                    "Configuration des jetons de service invalide."
                ) from None
        return cls(
            os.environ.get("LEDGER_GATEWAY_URL") or "http://ledger-gateway:8080", token
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> LedgerClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        history: bool = False,
    ) -> Record | list[Record]:
        try:
            response = self._http.request(
                method, path, json=dict(payload) if payload is not None else None
            )
        except httpx.HTTPError:
            raise LedgerUnavailable() from None
        except (TypeError, ValueError):
            raise InvalidRecord(400, "SCHEMA") from None
        try:
            body = response.json()
        except ValueError:
            raise LedgerUnavailable() from None
        if response.status_code != 200:
            failure = FAILURES.get(response.status_code)
            error = body.get("error") if isinstance(body, dict) else None
            if (
                failure
                and isinstance(error, dict)
                and error.get("code") == failure[0]
                and isinstance(error.get("message"), str)
                and error.get("details") == {}
            ):
                raise failure[1](response.status_code, failure[0])
            raise LedgerUnavailable()
        if history:
            if not isinstance(body, list) or any(
                not isinstance(item, dict) or "error" in item for item in body
            ):
                raise LedgerUnavailable()
        elif not isinstance(body, dict) or "error" in body:
            raise LedgerUnavailable()
        return cast(Record | list[Record], body)

    def create_record(self, record: Mapping[str, Any]) -> Record:
        result = self._request("POST", "/ledger/artifacts", record)
        assert isinstance(result, dict)
        return result

    def get_record(self, artifact_id: str) -> Record:
        identifier = checked_segment(artifact_id, UUID_PATTERN)
        result = self._request("GET", f"/ledger/artifacts/{identifier}")
        assert isinstance(result, dict)
        return result

    def get_case_history(self, case_id: str) -> list[Record]:
        identifier = checked_segment(case_id, "CASE-" + UUID_PATTERN)
        result = self._request("GET", f"/ledger/cases/{identifier}", history=True)
        assert isinstance(result, list)
        return result

    def register_model(self, model: Mapping[str, Any]) -> Record:
        result = self._request("POST", "/ledger/models", model)
        assert isinstance(result, dict)
        return result

    def get_model(self, name: str, version: str) -> Record:
        name = checked_segment(name, r"[a-z0-9_-]{1,60}")
        version = checked_segment(version, r"[0-9]+\.[0-9]+\.[0-9]+")
        result = self._request("GET", f"/ledger/models/{name}/{version}")
        assert isinstance(result, dict)
        return result
