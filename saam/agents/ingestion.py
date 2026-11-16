"""ECG ingestion and pseudonymization agent."""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import wfdb

from saam.agents.redaction import sanitize_report as redact_report

LEADS = (
    "I", "II", "III", "AVR", "AVL", "AVF",
    "V1", "V2", "V3", "V4", "V5", "V6",
)

CASE_ID_PATTERN = re.compile(
    r"^CASE-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

IDENTITY_LABEL_PATTERN = re.compile(
    r"(?i)\b(patient(?:\s+name)?|nom(?:\s+du\s+patient)?|"
    r"name|prénom|prenom|date\s+of\s+birth|date\s+de\s+naissance|"
    r"dob|patient\s+id|identifiant\s+patient)\s*[:=]\s*([^\r\n,;]+)"
)

DATE_PATTERNS = (
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"),
)


@dataclass(frozen=True)
class IngestionResult:
    case_id: str
    signal: np.ndarray
    sampling_rate: float
    leads: tuple[str, ...]
    units: tuple[str, ...]
    files: dict[str, bytes]
    report_text: str | None
    source_format: str


def validate_case_id(case_id: str) -> None:
    if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("case_id must have the format CASE-<UUID>.")

    try:
        parsed = uuid.UUID(case_id[5:])
    except ValueError as exc:
        raise ValueError("case_id must contain a valid UUID.") from exc

    if str(parsed) != case_id[5:].lower():
        raise ValueError("case_id must contain a canonical UUID.")


def new_case_id() -> str:
    """Generate an independent pseudonymous UUID for a submitted case.

    This helper does not create or persist a backend case record.
    """
    return f"CASE-{uuid.uuid4()}"


def sanitize_report(
    report_text: str | None,
    known_names: tuple[str, ...] = (),
) -> str | None:
    return redact_report(report_text, known_names)



def validate_signal(signal: np.ndarray, leads: tuple[str, ...]) -> None:
    if signal.ndim != 2 or signal.shape[1] != 12:
        raise ValueError("ECG must contain exactly 12 leads.")

    if tuple(name.upper() for name in leads) != LEADS:
        raise ValueError("Unexpected ECG lead names or order.")

    if signal.shape[0] < 1:
        raise ValueError("ECG signal is empty.")

    if not np.issubdtype(signal.dtype, np.number):
        raise ValueError("ECG signal must be numeric.")

    # NaN samples are preserved for the preparation agent's quality
    # assessment. Infinite values remain invalid at ingestion.
    if np.isinf(signal).any():
        raise ValueError("ECG contains infinite samples.")


def read_wfdb(header_path: Path, case_id: str):
    if header_path.suffix.lower() != ".hea":
        raise ValueError("WFDB input must be a .hea file.")

    if not header_path.is_file():
        raise FileNotFoundError("WFDB header file not found.")

    try:
        lines = [
            line.strip()
            for line in header_path.read_text(encoding="ascii").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeError):
        raise ValueError("Unable to read WFDB header.") from None

    if len(lines) < 13:
        raise ValueError("WFDB header must contain 12 signal definitions.")

    first_fields = lines[0].split()
    if len(first_fields) < 3:
        raise ValueError("Invalid WFDB record header.")

    header_values_valid = True
    try:
        signal_count = int(first_fields[1])
        frequency_parts = [float(part) for part in first_fields[2].split("/")]
    except ValueError:
        header_values_valid = False

    if (
        not header_values_valid
        or signal_count != 12
        or len(frequency_parts) not in (1, 2)
        or any(not np.isfinite(part) or part <= 0 for part in frequency_parts)
    ):
        raise ValueError("Invalid WFDB record header.")

    try:
        record = wfdb.rdrecord(str(header_path.with_suffix("")))
    except (OSError, ValueError, TypeError, IndexError):
        raise ValueError("Unable to read WFDB record.") from None

    signal = np.asarray(record.p_signal, dtype=np.float64)
    leads = tuple(str(name).upper() for name in record.sig_name)
    units = tuple(str(unit) for unit in record.units)

    validate_signal(signal, leads)

    if not record.fs or record.fs <= 0:
        raise ValueError("Invalid WFDB sampling frequency.")

    if len(units) != 12 or any(unit.lower() != "mv" for unit in units):
        raise ValueError("WFDB signals must use mV units.")

    record_name = case_id.lower().replace("-", "_")
    output_files: dict[str, bytes] = {}
    data_mapping: dict[str, str] = {}

    # Rebuild only structural fields. Optional WFDB base-date/base-time fields
    # can identify a patient and are deliberately omitted.
    new_lines = [f"{record_name} 12 {first_fields[2]} {signal.shape[0]}"]

    for line in lines[1:13]:
        fields = line.split()

        if len(fields) < 9:
            raise ValueError("Invalid WFDB signal definition.")

        original_name = fields[0]
        original_path = (header_path.parent / original_name).resolve()

        if original_path.parent != header_path.parent.resolve():
            raise ValueError("WFDB data file must be in the header directory.")

        if not original_path.is_file() or original_path.suffix.lower() != ".dat":
            raise ValueError("Missing or unsupported WFDB data file.")

        if original_name not in data_mapping:
            suffix = "" if not data_mapping else f"_{len(data_mapping)}"
            new_name = f"{record_name}{suffix}.dat"
            data_mapping[original_name] = new_name
            try:
                output_files[new_name] = original_path.read_bytes()
            except OSError:
                raise ValueError("Unable to read WFDB signal data.") from None

        fields[0] = data_mapping[original_name]
        new_lines.append(" ".join(fields))

    output_files[f"{record_name}.hea"] = (
        "\n".join(new_lines) + "\n"
    ).encode("ascii")

    return signal, float(record.fs), leads, units, output_files


def read_csv(csv_path: Path, sampling_rate: float, case_id: str):
    if not csv_path.is_file():
        raise FileNotFoundError("ECG CSV file not found.")

    if not np.isfinite(sampling_rate) or sampling_rate <= 0:
        raise ValueError("CSV sampling rate must be positive and finite.")

    try:
        table = pd.read_csv(csv_path)
    except (
        OSError,
        UnicodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        ValueError,
    ):
        raise ValueError("Unable to read ECG CSV.") from None

    table.columns = [str(column).strip().upper() for column in table.columns]

    if len(set(table.columns)) != len(table.columns):
        raise ValueError("CSV contains duplicate columns.")

    if set(table.columns) != set(LEADS):
        raise ValueError("CSV must contain exactly the 12 standard leads.")

    table = table.loc[:, list(LEADS)]

    conversion_failed = False
    try:
        signal = table.to_numpy(dtype=np.float64)
    except (TypeError, ValueError):
        conversion_failed = True

    if conversion_failed:
        raise ValueError("CSV contains non-numeric values.")

    validate_signal(signal, LEADS)

    buffer = io.StringIO()
    table.to_csv(buffer, index=False)

    filename = case_id.lower().replace("-", "_") + ".csv"

    return (
        signal,
        float(sampling_rate),
        LEADS,
        tuple("mV" for _ in LEADS),
        {filename: buffer.getvalue().encode("utf-8")},
    )


def ingest_ecg(
    ecg_path: str | Path,
    case_id: str,
    csv_sampling_rate: float | None = None,
    report_text: str | None = None,
    known_names: tuple[str, ...] = (),
) -> IngestionResult:
    validate_case_id(case_id)
    path = Path(ecg_path)

    if path.suffix.lower() == ".hea":
        signal, rate, leads, units, files = read_wfdb(path, case_id)
        source_format = "WFDB"

    elif path.suffix.lower() == ".csv":
        if csv_sampling_rate is None:
            raise ValueError("csv_sampling_rate is required for CSV input.")

        signal, rate, leads, units, files = read_csv(
            path, csv_sampling_rate, case_id
        )
        source_format = "CSV"

    else:
        raise ValueError("Unsupported format. Use WFDB (.hea) or CSV.")

    sanitized_report = sanitize_report(report_text, known_names)
    if sanitized_report is not None:
        files["report.txt"] = sanitized_report.encode("utf-8")

    return IngestionResult(
        case_id=case_id,
        signal=signal,
        sampling_rate=rate,
        leads=leads,
        units=units,
        files=files,
        report_text=sanitized_report,
        source_format=source_format,
    )
