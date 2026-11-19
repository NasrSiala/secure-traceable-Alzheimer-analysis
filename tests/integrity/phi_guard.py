"""The NFR-03 guard: what may appear in the on-chain history of a case, and what may not.

It judges the records `GetCaseHistory` returns (ARTIFACT, Schema 5.2). It is test support: it
reads records and never changes them, and nothing of production depends on it.

A record is clean when
  - it has exactly the fields of the closed schema, no more and no fewer;
  - every value has the format of its field (the same formats as the chaincode and the gateway);
  - the two free technical tokens (`softwareVersion`, `modelVersion`) hold no name and no date of
    birth, the one place where the chaincode accepts any string of up to 64 characters;
  - the timestamps are ISO 8601 UTC and fall in the project era, so a date of birth cannot pass
    as a timestamp.

Diagnostics are privacy-safe by construction: a `Violation` is a record position, a field label
and a kind. It never holds a value, and a field outside the schema is labelled by its rank, not by
its name (a field name can be an identity).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

# Schema 5.2, ARTIFACT, in the order of the table. tests/integrity compares them with
# chaincode/provenance/src/artifact.ts. The chaincode sets the last five itself (NFR-06).
ARTIFACT_FIELDS = (
    "docType",
    "artifactId",
    "caseId",
    "artifactType",
    "sha256",
    "createdAt",
    "txTimestamp",
    "softwareVersion",
    "modelVersion",
    "parentArtifactId",
    "offchainRef",
    "creatorMspId",
    "creatorId",
    "creatorAgent",
)
CHAINCODE_FIELDS = (
    "docType",
    "txTimestamp",
    "creatorMspId",
    "creatorId",
    "creatorAgent",
)
CLIENT_FIELDS = tuple(
    field for field in ARTIFACT_FIELDS if field not in CHAINCODE_FIELDS
)
ARTIFACT_TYPES = (
    "original",
    "processed",
    "features",
    "prediction",
    "validation",
    "explanation",
    "final_result",
)

# The project era for a timestamp. A date of birth of an adult is far below it; the chaincode
# writes `txTimestamp` itself and a client sets `createdAt` when it creates the artifact.
TIMESTAMP_FIRST_YEAR = 2020
TIMESTAMP_LAST_YEAR = 2099

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CASE_ID = re.compile(r"^CASE-[0-9a-f-]{36}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^(\d{4})-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")
_MSP_ID = re.compile(r"^[A-Za-z0-9]+MSP$")
_AGENT = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
# A version is a technical token: no space, no colon, no equals sign. A person's name written
# with its natural spaces cannot pass for one.
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
# `creatorId` is the subject of the caller's certificate as the chaincode stores it: the `x509::`
# wrapper and the issuer are cut off (artifact.ts `certificateSubject`), the parts are slash
# separated, e.g. /C=US/ST=North Carolina/O=Hyperledger/OU=client/CN=agent-ingestion.
_CREATOR_ID = re.compile(r"^(?:/[A-Za-z]+=[^/=]+)+$")
_SUBJECT_COMMON_NAME = re.compile(r"(?:^|/)CN=([^/]+)")
_SERVICE_NAME = re.compile(r"^[a-z0-9-]+$")

_YEAR = r"(?:19|20)\d{2}"
_DAY = r"(?:0?[1-9]|[12]\d|3[01])"
_MONTH = r"(?:0?[1-9]|1[0-2])"
_MONTH_NAMES = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre"
    "|décembre|decembre|january|february|march|april|may|june|july|august|september|october"
    "|november|december"
)
_DATE_OF_BIRTH = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"(?<!\d){_YEAR}[-/.]{_MONTH}[-/.]{_DAY}(?!\d)",
        rf"(?<!\d){_DAY}[-/.]{_MONTH}[-/.]{_YEAR}(?!\d)",
        rf"(?<!\d){_YEAR}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)",
        rf"(?<!\d)\d{{1,2}}(?:er)?\s+(?:{_MONTH_NAMES})\.?\s+{_YEAR}(?!\d)",
        r"(?<![a-z])(?:dob|born|naissance|birth(?:date|day)?|n[ée]e?\s+le)(?![a-z])",
    )
)

_UPPER = "A-ZÀ-ÖØ-Þ"
_LOWER = "a-zß-öø-ÿ"
_CAPITALIZED = rf"[{_UPPER}][{_LOWER}'’]+"
_NAME = (
    # Jean Dupont, Jean-Pierre Martin, Élodie Bérenger
    re.compile(
        rf"(?<![{_UPPER}{_LOWER}]){_CAPITALIZED}(?:[ \-]+{_CAPITALIZED})+(?![{_LOWER}])"
    ),
    # DUPONT Jean
    re.compile(rf"(?<![{_UPPER}{_LOWER}])[{_UPPER}]{{2,}} +{_CAPITALIZED}"),
    # Mme Martin, Dr Dupont
    re.compile(rf"(?<![A-Za-z])(?:M|Mme|Mlle|Mr|Mrs|Ms|Mx|Dr|Pr)\.? +[{_UPPER}]"),
    # nom: dupont, name=jean
    re.compile(
        r"(?<![a-z])(?:nom|pr[ée]nom|name|patient|surname|lastname|firstname)\s*[:=]",
        re.IGNORECASE,
    ),
)

# A field named like a person or a date of birth is worse than a field outside the schema: it is
# called out on top of `unknown_field`. Compared on the letters of the name, accents removed.
_IDENTITY_WORDS = (
    "name",
    "nom",
    "prenom",
    "patient",
    "birth",
    "naissance",
    "dob",
    "born",
    "ssn",
    "mail",
    "phone",
    "address",
    "adresse",
)

NOT_A_RECORD = "not_a_record"
UNKNOWN_FIELD = "unknown_field"
IDENTITY_FIELD = "identity_field"
MISSING_FIELD = "missing_field"
WRONG_TYPE = "wrong_type"
FORMAT = "format"
TIMESTAMP_RANGE = "timestamp_range"
DOB_PATTERN = "dob_pattern"
NAME_PATTERN = "name_pattern"


@dataclass(frozen=True)
class Violation:
    """Where (record position, field label) and what (kind). Never a value, never a key name."""

    record: int
    field: str
    kind: str


def _letters(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    return "".join(
        c for c in plain if c.isalpha() and not unicodedata.combining(c)
    ).lower()


def _is_identity_name(key: str) -> bool:
    letters = _letters(key)
    return any(word in letters for word in _IDENTITY_WORDS)


def _strings(value: object) -> list[str]:
    """Every string a value holds, nested objects and lists included."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text for key, item in value.items() for text in [str(key), *_strings(item)]
        ]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _patterns(text: str, *, names: bool) -> set[str]:
    found: set[str] = set()
    if any(pattern.search(text) for pattern in _DATE_OF_BIRTH):
        found.add(DOB_PATTERN)
    if names and any(pattern.search(text) for pattern in _NAME):
        found.add(NAME_PATTERN)
    return found


def _scan(value: object, *, names: bool = True) -> set[str]:
    kinds: set[str] = set()
    for text in _strings(value):
        kinds |= _patterns(text, names=names)
    return kinds


def _check_field(field: str, value: object, record: dict[str, object]) -> set[str]:
    """The kinds of violation for one known field of one record."""
    kinds: set[str] = set()
    nullable = field in ("modelVersion", "parentArtifactId")
    if value is None and nullable:
        return kinds
    if not isinstance(value, str):
        return {WRONG_TYPE}
    ok = True
    if field == "docType":
        ok = value == "artifact"
    elif field in ("artifactId", "parentArtifactId"):
        ok = _UUID.match(value) is not None
    elif field == "caseId":
        ok = _CASE_ID.match(value) is not None
    elif field == "artifactType":
        ok = value in ARTIFACT_TYPES
    elif field == "sha256":
        ok = _SHA256.match(value) is not None
    elif field == "offchainRef":
        ok = value == f"artifact://{record.get('artifactId')}"
    elif field == "creatorMspId":
        ok = _MSP_ID.match(value) is not None
    elif field == "creatorAgent":
        ok = _AGENT.match(value) is not None
    elif field in ("createdAt", "txTimestamp"):
        match = _TIMESTAMP.match(value)
        ok = match is not None
        if (
            match is not None
            and not TIMESTAMP_FIRST_YEAR <= int(match.group(1)) <= TIMESTAMP_LAST_YEAR
        ):
            kinds.add(TIMESTAMP_RANGE)
    elif field == "creatorId":
        common = (
            _SUBJECT_COMMON_NAME.search(value) if _CREATOR_ID.match(value) else None
        )
        ok = common is not None and _SERVICE_NAME.match(common.group(1)) is not None
    elif field in ("softwareVersion", "modelVersion"):
        ok = _TOKEN.match(value) is not None
    if not ok:
        kinds.add(FORMAT)
    # A strict format cannot hold a name or a date, and a hash of digits only would look like a
    # date. What can: the two free tokens, a subject (dates only: its names are the CA's), and
    # any value that is not in its format.
    if field in ("softwareVersion", "modelVersion") or not ok:
        kinds |= _patterns(value, names=True)
    elif field == "creatorId":
        kinds |= _patterns(value, names=False)
    return kinds


def check_record(index: int, record: object) -> list[Violation]:
    if not isinstance(record, dict):
        return [Violation(index, "<record>", NOT_A_RECORD)]
    found: list[Violation] = []
    unknown = 0
    for key, value in record.items():
        if key in ARTIFACT_FIELDS:
            for kind in sorted(_check_field(key, value, record)):
                found.append(Violation(index, key, kind))
            continue
        unknown += 1
        label = f"<unknown field {unknown}>"
        found.append(Violation(index, label, UNKNOWN_FIELD))
        if _is_identity_name(str(key)):
            found.append(Violation(index, label, IDENTITY_FIELD))
        # The key and the value are both read: either can carry the identity.
        for kind in sorted(_scan(str(key)) | _scan(value)):
            found.append(Violation(index, label, kind))
    for field in ARTIFACT_FIELDS:
        if field not in record:
            found.append(Violation(index, field, MISSING_FIELD))
    return found


def check_history(records: Sequence[object]) -> list[Violation]:
    """Every violation of the history, record by record (position 0 is the first record)."""
    return [
        violation
        for index, record in enumerate(records)
        for violation in check_record(index, record)
    ]


def describe(violations: Sequence[Violation]) -> str:
    """One line per violation: record position, field label and kind. No value, no key name."""
    if not violations:
        return "no violation"
    return "\n".join(f"record {v.record}: {v.field}: {v.kind}" for v in violations)


def assert_clean(records: Sequence[object]) -> None:
    found = check_history(records)
    if found:
        raise AssertionError(
            f"NFR-03: {len(found)} violation(s) in a history of {len(records)} record(s)\n"
            f"{describe(found)}"
        )
