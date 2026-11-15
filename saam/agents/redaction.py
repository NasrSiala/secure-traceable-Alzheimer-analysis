"""Medical report pseudonymization utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable


ANONYMIZED = "[ANONYMISÉ]"

IDENTITY_LABEL_PATTERN = re.compile(
    r"(?i)\b(patient(?:\s+name)?|nom(?:\s+du\s+patient)?|"
    r"name|prénom|prenom|date\s+of\s+birth|date\s+de\s+naissance|"
    r"dob|patient\s+id|identifiant\s+patient)\s*[:=]\s*([^\r\n,;]+)"
)

DATE_PATTERNS = (
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"),
)

NAME = (
    r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{1,}"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{1,}){1,2}"
)

TITLED_NAME_PATTERN = re.compile(
    rf"\b(?:Dr\.?|Doctor|Mr\.?|Mrs\.?|Ms\.?|Miss|"
    rf"Mme?\.?|Monsieur|Madame)\s+{NAME}\b",
    re.IGNORECASE,
)

PATIENT_NAME_PATTERN = re.compile(
    rf"\b(?:patient|le patient|la patiente)\s+"
    rf"(?:is\s+|est\s+)?({NAME})\b",
    re.IGNORECASE,
)


def sanitize_report(
    report_text: str | None,
    known_names: Iterable[str] = (),
) -> str | None:
    """Redact identifiable names, identity fields and date values.

    Free-text name detection uses explicit known names and contextual
    patterns such as professional titles or patient introductions.
    It is a supplementary privacy control, not a guarantee of
    complete de-identification.
    """
    if report_text is None:
        return None

    if not isinstance(report_text, str):
        raise TypeError("report_text must be a string.")

    sanitized = IDENTITY_LABEL_PATTERN.sub(
        lambda match: f"{match.group(1)}: {ANONYMIZED}",
        report_text,
    )

    sanitized = TITLED_NAME_PATTERN.sub(ANONYMIZED, sanitized)

    sanitized = PATIENT_NAME_PATTERN.sub(
        lambda match: match.group(0).replace(match.group(1), ANONYMIZED),
        sanitized,
    )

    names = sorted(
        {
            name.strip()
            for name in known_names
            if isinstance(name, str) and len(name.strip()) >= 2
        },
        key=len,
        reverse=True,
    )

    for name in names:
        pattern = re.compile(
            rf"(?<!\w){re.escape(name)}(?!\w)",
            re.IGNORECASE,
        )
        sanitized = pattern.sub(ANONYMIZED, sanitized)

    for pattern in DATE_PATTERNS:
        sanitized = pattern.sub(ANONYMIZED, sanitized)

    return sanitized
