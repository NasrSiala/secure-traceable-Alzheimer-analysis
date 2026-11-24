"""Mutation run on the NFR-03 guard and its HTTP path (T2.9).

Each mutation changes one line of tests/integrity/phi_guard.py or gateway_history.py, runs the
tests that need no network, and restores the file. A mutation is *killed* when a test fails. The
files are edited as bytes, so their line endings are kept, and restored in a `finally`.

    py -3 audit/round-8/tools/mutate_guard.py            # all
    py -3 audit/round-8/tools/mutate_guard.py M11 G2     # some
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "tests" / "integrity" / "phi_guard.py"
HISTORY = ROOT / "tests" / "integrity" / "gateway_history.py"


@dataclass(frozen=True)
class Mutation:
    key: str
    path: Path
    old: str
    new: str
    note: str


M = [
    Mutation(
        "M01", GUARD, 'ok = value == "artifact"', "ok = True", "docType not checked"
    ),
    Mutation(
        "M02", GUARD, "ok = _UUID.match(value) is not None", "ok = True", "uuid format"
    ),
    Mutation(
        "M03",
        GUARD,
        "ok = _CASE_ID.match(value) is not None",
        "ok = True",
        "caseId format",
    ),
    Mutation(
        "M04", GUARD, "ok = value in ARTIFACT_TYPES", "ok = True", "artifactType enum"
    ),
    Mutation(
        "M05",
        GUARD,
        "ok = _SHA256.match(value) is not None",
        "ok = True",
        "sha256 format",
    ),
    Mutation(
        "M06",
        GUARD,
        "ok = value == f\"artifact://{record.get('artifactId')}\"",
        "ok = True",
        "offchainRef not tied to artifactId",
    ),
    Mutation(
        "M07", GUARD, "ok = _MSP_ID.match(value) is not None", "ok = True", "msp id"
    ),
    Mutation(
        "M08", GUARD, "ok = _AGENT.match(value) is not None", "ok = True", "agent"
    ),
    Mutation(
        "M09",
        GUARD,
        "TIMESTAMP_FIRST_YEAR = 2020",
        "TIMESTAMP_FIRST_YEAR = 1900",
        "era start",
    ),
    Mutation(
        "M10",
        GUARD,
        "TIMESTAMP_LAST_YEAR = 2099",
        "TIMESTAMP_LAST_YEAR = 9999",
        "era end",
    ),
    Mutation(
        "M11",
        GUARD,
        'if field in ("softwareVersion", "modelVersion") or not ok:',
        "if not ok:",
        "free tokens not scanned",
    ),
    Mutation(
        "M12",
        GUARD,
        "kinds |= _patterns(value, names=False)",
        "pass",
        "creatorId dates not scanned",
    ),
    Mutation(
        "M13",
        GUARD,
        'nullable = field in ("modelVersion", "parentArtifactId")',
        'nullable = field in ("modelVersion",)',
        "parentArtifactId may no longer be null",
    ),
    Mutation(
        "M14",
        GUARD,
        "for kind in sorted(_scan(str(key)) | _scan(value)):",
        "for kind in sorted(_scan(value)):",
        "key not read for patterns",
    ),
    Mutation(
        "M15",
        GUARD,
        "return any(word in letters for word in _IDENTITY_WORDS)",
        "return False",
        "identity field names",
    ),
    Mutation(
        "M16",
        GUARD,
        'label = f"<unknown field {unknown}>"',
        "label = str(key)",
        "field name leaks into the label",
    ),
    Mutation("M17", GUARD, "if field not in record:", "if False:", "missing field"),
    Mutation(
        "M18", GUARD, "if not isinstance(record, dict):", "if False:", "not a record"
    ),
    Mutation(
        "M19",
        GUARD,
        "text for key, item in value.items() for text in [str(key), *_strings(item)]",
        "text for key, item in value.items() for text in [*_strings(item)]",
        "nested keys not read",
    ),
    Mutation(
        "M20",
        GUARD,
        "if isinstance(value, list):",
        "if isinstance(value, tuple):",
        "lists not read",
    ),
    Mutation(
        "M21",
        GUARD,
        'rf"(?<!\\d){_YEAR}[-/.]{_MONTH}[-/.]{_DAY}(?!\\d)",',
        'r"(?!)",',
        "dob YYYY-MM-DD",
    ),
    Mutation(
        "M22",
        GUARD,
        'rf"(?<!\\d){_DAY}[-/.]{_MONTH}[-/.]{_YEAR}(?!\\d)",',
        'r"(?!)",',
        "dob DD/MM/YYYY",
    ),
    Mutation(
        "M23",
        GUARD,
        'rf"(?<!\\d){_YEAR}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\\d|3[01])(?!\\d)",',
        'r"(?!)",',
        "dob YYYYMMDD",
    ),
    Mutation(
        "M24",
        GUARD,
        'rf"(?<!\\d)\\d{{1,2}}(?:er)?\\s+(?:{_MONTH_NAMES})\\.?\\s+{_YEAR}(?!\\d)",',
        'r"(?!)",',
        "dob 12 mars 1975",
    ),
    Mutation(
        "M25",
        GUARD,
        'r"(?<![a-z])(?:dob|born|naissance|birth(?:date|day)?|n[ée]e?\\s+le)(?![a-z])",',
        'r"(?!)",',
        "dob words",
    ),
    Mutation(
        "M26",
        GUARD,
        'rf"(?<![{_UPPER}{_LOWER}]){_CAPITALIZED}(?:[ \\-]+{_CAPITALIZED})+(?![{_LOWER}])"',
        'r"(?!)"',
        "name Jean Dupont",
    ),
    Mutation(
        "M27",
        GUARD,
        're.compile(rf"(?<![{_UPPER}{_LOWER}])[{_UPPER}]{{2,}} +{_CAPITALIZED}"),',
        're.compile(r"(?!)"),',
        "name DUPONT Jean",
    ),
    Mutation(
        "M28",
        GUARD,
        're.compile(rf"(?<![A-Za-z])(?:M|Mme|Mlle|Mr|Mrs|Ms|Mx|Dr|Pr)\\.? +[{_UPPER}]"),',
        're.compile(r"(?!)"),',
        "name Mme Martin",
    ),
    Mutation(
        "M29",
        GUARD,
        'r"(?<![a-z])(?:nom|pr[ée]nom|name|patient|surname|lastname|firstname)\\s*[:=]",',
        'r"(?!)",',
        "name nom:",
    ),
    Mutation(
        "M30",
        GUARD,
        '_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")',
        '_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+ -]{0,63}$")',
        "a space is allowed in a version",
    ),
    Mutation(
        "M31",
        GUARD,
        '_SERVICE_NAME = re.compile(r"^[a-z0-9-]+$")',
        '_SERVICE_NAME = re.compile(r"^.*$")',
        "any common name",
    ),
    Mutation(
        "M32", GUARD, "    if found:", "    if False:", "assert_clean never raises"
    ),
    Mutation(
        "M33",
        GUARD,
        "for index, record in enumerate(records)",
        "for index, record in enumerate(records, 1)",
        "record positions start at 1",
    ),
    Mutation(
        "M34",
        GUARD,
        '_CASE_ID = re.compile(r"^CASE-[0-9a-f-]{36}$")',
        '_CASE_ID = re.compile(r"^CASE-.*$")',
        "caseId loosened",
    ),
    Mutation(
        "M35",
        GUARD,
        '_AGENT = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")',
        '_AGENT = re.compile(r"^.*$")',
        "agent loosened",
    ),
    Mutation(
        "M36",
        GUARD,
        '_MSP_ID = re.compile(r"^[A-Za-z0-9]+MSP$")',
        '_MSP_ID = re.compile(r"^.*$")',
        "msp loosened",
    ),
    Mutation(
        "G01",
        HISTORY,
        'headers={"X-Agent-Token": self.token},',
        'headers={"Authorization": self.token},',
        "wrong auth header",
    ),
    Mutation(
        "G02",
        HISTORY,
        "if response.status_code != 200:",
        "if False:",
        "status not checked",
    ),
    Mutation(
        "G03",
        HISTORY,
        "if not isinstance(payload, list):",
        "if False:",
        "non-list accepted",
    ),
    Mutation(
        "G04",
        HISTORY,
        "if not _CASE_ID.match(case_id):",
        "if False:",
        "case id not checked",
    ),
    Mutation(
        "G05",
        HISTORY,
        'raise LedgerAccessError("the gateway could not be reached") from None',
        'raise LedgerAccessError(f"the gateway {self._base_url} could not be reached") from None',
        "url in the error",
    ),
    Mutation(
        "G06",
        HISTORY,
        'return "ledgerclient" if found else "httpx"',
        'return "httpx" if found else "ledgerclient"',
        "path swapped",
    ),
    Mutation(
        "G07",
        HISTORY,
        'self._base_url = base_url.rstrip("/")',
        "self._base_url = base_url",
        "no rstrip",
    ),
    Mutation(
        "G08",
        HISTORY,
        'f"GET /ledger/cases answered {response.status_code}"',
        'f"GET /ledger/cases answered {response.status_code} {response.text}"',
        "body in the error",
    ),
    Mutation(
        "G09",
        HISTORY,
        'return self._request("POST", "/ledger/artifacts", body=body).status_code',
        'return self._request("PUT", "/ledger/artifacts", body=body).status_code',
        "wrong method",
    ),
    Mutation(
        "G10",
        HISTORY,
        'response = self._request("GET", f"/ledger/cases/{case_id}")',
        'response = self._request("GET", f"/ledger/cases/{case_id}?x=1")',
        "query string",
    ),
]


def run_tests() -> tuple[bool, str]:
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integrity",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    return done.returncode != 0, last


def main(selected: list[str]) -> int:
    originals = {path: path.read_bytes() for path in (GUARD, HISTORY)}
    survivors: list[str] = []
    try:
        for mutation in M:
            if selected and mutation.key not in selected:
                continue
            raw = originals[mutation.path]
            old = mutation.old.encode()
            if mutation.old.endswith("\n"):
                # The source has CRLF or LF: match the line ending it really uses.
                old = old.replace(b"\n", b"\r\n") if b"\r\n" in raw else old
            if raw.count(old) != 1:
                print(
                    f"{mutation.key}  NOT APPLIED ({raw.count(old)} matches)  {mutation.note}"
                )
                survivors.append(f"{mutation.key}(not applied)")
                continue
            new = mutation.new.encode()
            if mutation.new.endswith("\n") and b"\r\n" in raw:
                new = new.replace(b"\n", b"\r\n")
            mutation.path.write_bytes(raw.replace(old, new))
            try:
                killed, last = run_tests()
            finally:
                mutation.path.write_bytes(raw)
            print(
                f"{mutation.key}  {'killed  ' if killed else 'SURVIVED'}  {mutation.note}  [{last}]"
            )
            sys.stdout.flush()
            if not killed:
                survivors.append(mutation.key)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
    print("survivors:", survivors or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
