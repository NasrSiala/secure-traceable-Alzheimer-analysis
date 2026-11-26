from __future__ import annotations

import re
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from saam.cases import CaseService
from saam.ledger import LedgerClient, LedgerError
from saam.traceability import ArtifactReader, IntegrityError

IntegrityStatus = Literal["valide", "modifie", "manquant", "non_verifiable"]
VERIFY_BUDGET_SECONDS = 10.0


@dataclass(frozen=True)
class VerificationItem:
    artifact_id: str
    artifact_type: str
    status: IntegrityStatus
    expected_sha256: str | None = None
    computed_sha256: str | None = None


class CaseVerifier:
    """Vérification des artefacts inventoriés pour le cas dans le worker (R5)."""

    def __init__(
        self, cases: CaseService, reader: ArtifactReader, ledger: LedgerClient
    ) -> None:
        self.cases = cases
        self.reader = reader
        self.ledger = ledger

    def verify_case(
        self, case_id: str, persist: Literal[False] = False
    ) -> tuple[VerificationItem, ...]:
        """Lit un instantané des artefacts du cas et renvoie un verdict par artefact."""
        if persist is not False:
            raise ValueError("La vérification R5 est en lecture seule.")
        deadline = monotonic() + VERIFY_BUDGET_SECONDS
        with self.cases.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            case = self.cases.get_case(case_id, db=db)
            identifier = str(case["id"])
            artifacts = self.reader.list_for_case(db, identifier)
        return tuple(
            self._verify_artifact(
                identifier, str(artifact["id"]), artifact["type"], deadline
            )
            for artifact in artifacts
        )

    def _verify_artifact(
        self, case_id: str, artifact_id: str, artifact_type: str, deadline: float
    ) -> VerificationItem:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return VerificationItem(artifact_id, artifact_type, "non_verifiable")
        try:
            record = self.ledger.get_record(artifact_id, timeout=remaining)
        except LedgerError:
            return VerificationItem(artifact_id, artifact_type, "non_verifiable")

        expected = record.get("sha256")
        if (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            or record.get("artifactId") != artifact_id
            or record.get("caseId") != f"CASE-{case_id}"
            or record.get("artifactType") != artifact_type
            or record.get("offchainRef") != f"artifact://{artifact_id}"
        ):
            return VerificationItem(artifact_id, artifact_type, "non_verifiable")

        try:
            computed = self.reader.verify_contents(
                artifact_id, case_id, artifact_type, expected
            )
        except FileNotFoundError:
            return VerificationItem(artifact_id, artifact_type, "manquant", expected)
        except (IntegrityError, OSError):
            return VerificationItem(artifact_id, artifact_type, "modifie", expected)
        return VerificationItem(
            artifact_id, artifact_type, "valide", expected, computed
        )
