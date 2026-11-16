"""Audit helper: mutate the MODEL schema on one side and check that the parity test goes red."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = [
    "tests/conftest.py",
    "tests/scripts/test_model_schema_parity.py",
    "ledger-gateway/src/app.ts",
    "chaincode/provenance/src/model.ts",
    "chaincode/provenance/src/artifact.ts",
]
MUTATIONS = [
    (
        "gateway: framework maxLength 41",
        "ledger-gateway/src/app.ts",
        'framework: { type: "string", minLength: 1, maxLength: 40 }',
        'framework: { type: "string", minLength: 1, maxLength: 41 }',
    ),
    (
        "gateway: framework minLength 0",
        "ledger-gateway/src/app.ts",
        'framework: { type: "string", minLength: 1, maxLength: 40 }',
        'framework: { type: "string", minLength: 0, maxLength: 40 }',
    ),
    (
        "gateway: name pattern allows uppercase",
        "ledger-gateway/src/app.ts",
        'MODEL_NAME = "^[a-z0-9_-]{1,60}$"',
        'MODEL_NAME = "^[a-zA-Z0-9_-]{1,60}$"',
    ),
    (
        "gateway: name length 61",
        "ledger-gateway/src/app.ts",
        '{1,60}$";\nconst MODEL_VERSION',
        '{1,61}$";\nconst MODEL_VERSION',
    ),
    (
        "gateway: version allows two parts",
        "ledger-gateway/src/app.ts",
        r'"^[0-9]+\\.[0-9]+\\.[0-9]+$"',
        r'"^[0-9]+\\.[0-9]+(\\.[0-9]+)?$"',
    ),
    (
        "gateway: sha256 uppercase",
        "ledger-gateway/src/app.ts",
        'sha256: { type: "string", pattern: "^[0-9a-f]{64}$" },\n    framework',
        'sha256: { type: "string", pattern: "^[0-9a-fA-F]{64}$" },\n    framework',
    ),
    (
        "gateway: framework not required",
        "ledger-gateway/src/app.ts",
        'required: ["name", "version", "sha256", "framework"]',
        'required: ["name", "version", "sha256"]',
    ),
    (
        "gateway: extra property allowed in modelBody",
        "ledger-gateway/src/app.ts",
        'const modelBody = {\n  type: "object",\n  additionalProperties: false,',
        'const modelBody = {\n  type: "object",\n  additionalProperties: true,',
    ),
    (
        "gateway: modelParams name without pattern",
        "ledger-gateway/src/app.ts",
        'const modelParams = {\n  type: "object",\n  required: ["name", "version"],\n  additionalProperties: false,\n  properties: {\n    name: { type: "string", pattern: MODEL_NAME },',
        'const modelParams = {\n  type: "object",\n  required: ["name", "version"],\n  additionalProperties: false,\n  properties: {\n    name: { type: "string" },',
    ),
    (
        "gateway: case pattern shorter",
        "ledger-gateway/src/app.ts",
        'caseId: { type: "string", pattern: "^CASE-[0-9a-f-]{36}$" },\n  },\n} as const;\n\n// MODEL',
        'caseId: { type: "string", pattern: "^CASE-[0-9a-f-]{35}$" },\n  },\n} as const;\n\n// MODEL',
    ),
    (
        "chaincode: add client field",
        "chaincode/provenance/src/model.ts",
        '["name", "version", "sha256", "framework"]',
        '["name", "version", "sha256", "framework", "notes"]',
    ),
    (
        "chaincode: framework max 41",
        "chaincode/provenance/src/model.ts",
        "text.length > 40",
        "text.length > 41",
    ),
    (
        "chaincode: name regex",
        "chaincode/provenance/src/model.ts",
        "const NAME = /^[a-z0-9_-]{1,60}$/;",
        "const NAME = /^[a-z0-9_.-]{1,60}$/;",
    ),
    (
        "chaincode: sha256 regex",
        "chaincode/provenance/src/artifact.ts",
        "const SHA256 = /^[0-9a-f]{64}$/;",
        "const SHA256 = /^[0-9a-f]{63,64}$/;",
    ),
]


def run(root: Path) -> tuple[int, str]:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/scripts/test_model_schema_parity.py",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return r.returncode, r.stdout.strip().splitlines()[
        -1
    ] if r.stdout.strip() else r.stderr[-200:]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for f in FILES:
            (base / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / f, base / f)
        print("unmutated:", run(base))
        for label, rel, old, new in MUTATIONS:
            path = base / rel
            original = path.read_bytes()
            text = original.decode("utf-8")
            if old not in text:
                print(f"NOT APPLIED  {label}")
                continue
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            code, tail = run(base)
            print(("killed     " if code else "SURVIVED   ") + label + "  |  " + tail)
            path.write_bytes(original)


main()
