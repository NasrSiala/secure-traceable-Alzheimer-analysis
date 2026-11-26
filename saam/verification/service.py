"""Vérification IF-08 des artefacts contre Fabric."""

from __future__ import annotations

import re
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from saam.cases import CaseService
from saam.ledger import LedgerClient, LedgerError, LedgerUnavailable, RecordNotFound
from saam.ledger.client import UUID_PATTERN
from saam.traceability import ArtifactReader, IntegrityError

IntegrityStatus = Literal["valide", "modifie", "manquant", "non_verifiable"]
VERIFY_BUDGET_SECONDS = 10.0
ARTIFACT_TYPES = (
    "original",
    "processed",
    "features",
    "prediction",
    "validation",
    "explanation",
    "final_result",
)


@dataclass(frozen=True)
class VerificationItem:
    artifact_id: str
    artifact_type: str
    status: IntegrityStatus
    expected_sha256: str | None = None
    computed_sha256: str | None = None
    detail: str | None = None


class CaseVerifier:
    def __init__(
        self, cases: CaseService, reader: ArtifactReader, ledger: LedgerClient
    ) -> None:
        self.cases = cases
        self.reader = reader
        self.ledger = ledger

    def _snapshot(self, case_id: str) -> tuple[str, dict[str, str]]:
        with self.cases.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            case = self.cases.get_case(case_id, db=db)
            identifier = str(case["id"])
            artifacts = self.reader.list_for_case(db, identifier)
        return identifier, {str(row["id"]): row["type"] for row in artifacts}

    def verify_case(
        self, case_id: str, persist: Literal[False] = False
    ) -> tuple[VerificationItem, ...]:
        """Lecture seule des artefacts du worker, utilisée par R5."""
        if persist is not False:
            raise ValueError("La vérification R5 est en lecture seule.")
        deadline = monotonic() + VERIFY_BUDGET_SECONDS
        identifier, artifacts = self._snapshot(case_id)
        items = []
        for artifact_id, kind in artifacts.items():
            try:
                items.append(
                    self._verify_artifact(identifier, artifact_id, kind, deadline)
                )
            except LedgerError:
                items.append(_unconfirmed(artifact_id, kind))
        return tuple(items)

    def inspect_case(self, case_id: str) -> tuple[bool, tuple[VerificationItem, ...]]:
        """Inventaire SQL et Fabric pour une vérification déclenchée par l'API."""
        deadline = monotonic() + VERIFY_BUDGET_SECONDS
        identifier, artifacts = self._snapshot(case_id)
        case_ref = f"CASE-{identifier}"
        try:
            records = self.ledger.get_case_history(
                case_ref, timeout=_remaining(deadline)
            )
            onchain: dict[str, str] = {}
            for record in records:
                artifact_id = record.get("artifactId")
                kind = record.get("artifactType")
                if (
                    not isinstance(artifact_id, str)
                    or re.fullmatch(UUID_PATTERN, artifact_id) is None
                    or kind not in ARTIFACT_TYPES
                    or record.get("caseId") != case_ref
                    or artifact_id in onchain
                    or artifacts.get(artifact_id, kind) != kind
                ):
                    raise LedgerUnavailable()
                onchain[artifact_id] = kind
            artifacts.update(onchain)
            items = tuple(
                self._verify_artifact(identifier, artifact_id, kind, deadline)
                for artifact_id, kind in _ordered(artifacts)
            )
        except LedgerError:
            return False, tuple(
                _unconfirmed(artifact_id, kind)
                for artifact_id, kind in _ordered(artifacts)
            )
        return True, items

    def _verify_artifact(
        self, case_id: str, artifact_id: str, artifact_type: str, deadline: float
    ) -> VerificationItem:
        try:
            record = self.ledger.get_record(artifact_id, timeout=_remaining(deadline))
        except RecordNotFound:
            return _unconfirmed(
                artifact_id, artifact_type, "Artefact absent du registre."
            )

        expected = record.get("sha256")
        if (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            or record.get("artifactId") != artifact_id
            or record.get("caseId") != f"CASE-{case_id}"
            or record.get("artifactType") != artifact_type
            or record.get("offchainRef") != f"artifact://{artifact_id}"
        ):
            return _unconfirmed(
                artifact_id, artifact_type, "Enregistrement Fabric incohérent."
            )

        try:
            computed = self.reader.verify_contents(
                artifact_id, case_id, artifact_type, expected
            )
        except FileNotFoundError:
            return VerificationItem(
                artifact_id,
                artifact_type,
                "manquant",
                expected,
                detail="Fichier hors chaîne manquant.",
            )
        except (IntegrityError, OSError) as error:
            return VerificationItem(
                artifact_id,
                artifact_type,
                "modifie",
                expected,
                error.computed_sha256 if isinstance(error, IntegrityError) else None,
                "Intégrité du fichier ou du manifeste invalide.",
            )
        return VerificationItem(
            artifact_id, artifact_type, "valide", expected, computed
        )


def _ordered(artifacts: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(
        artifacts.items(), key=lambda item: (ARTIFACT_TYPES.index(item[1]), item[0])
    )


def _remaining(deadline: float) -> float:
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise LedgerUnavailable()
    return seconds


def _unconfirmed(
    artifact_id: str, kind: str, detail: str = "Registre blockchain injoignable."
) -> VerificationItem:
    return VerificationItem(artifact_id, kind, "non_verifiable", detail=detail)
