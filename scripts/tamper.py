"""Modifier un fichier d'un cas terminé dans la pile locale de démonstration."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saam.cases import CaseNotFound, CaseService  # noqa: E402
from saam.hashing import canonical_json  # noqa: E402
from saam.storage import ArtifactStore, DecryptionError  # noqa: E402
from saam.traceability import ArtifactReader  # noqa: E402

KINDS = (
    "original",
    "processed",
    "features",
    "prediction",
    "validation",
    "explanation",
    "final_result",
)
MODES = ("raw", "reencrypt")


def tamper_case(
    cases: CaseService, store: ArtifactStore, case_id: str, kind: str, mode: str
) -> str:
    if kind not in KINDS or mode not in MODES:
        raise ValueError("Type d'artefact ou mode invalide.")
    with cases.connect() as db:
        case = cases.get_case(case_id, db=db)
        if case["status"] != "termine":
            raise ValueError("Le cas doit être terminé avant la démonstration.")
        rows = ArtifactReader.list_for_case(db, str(case["id"]))
    artifact = next(
        (
            row
            for row in rows
            if row["type"] == kind and row["anchor_status"] == "ancre"
        ),
        None,
    )
    if artifact is None or not artifact["files"]:
        raise ValueError("Aucun fichier associé à cet artefact ancré.")
    artifact_id, name = str(artifact["id"]), min(artifact["files"])
    plaintext = store.read(artifact_id, name)
    if mode == "reencrypt":
        if name.endswith(".json") and isinstance(
            payload := json.loads(plaintext), dict
        ):
            changed = canonical_json(
                payload | {"demo_tamper": not payload.get("demo_tamper", False)}
            )
        else:
            changed = (
                bytes((plaintext[0] ^ 1,)) + plaintext[1:] if plaintext else b"\x01"
            )
        store.write(artifact_id, name, changed)
    else:
        target = store.path(artifact_id, name)
        encoded = target.read_bytes()
        fd, temporary = tempfile.mkstemp(prefix=".tamper-", dir=target.parent)
        staging = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded[:-1] + bytes((encoded[-1] ^ 1,)))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staging, store.path(artifact_id, name))
        finally:
            staging.unlink(missing_ok=True)
    return name


def compose_tamper(case_id: str, kind: str, mode: str, env_file: Path) -> None:
    command = ["docker", "compose"]
    if env_file.is_file():
        command.extend(["--env-file", str(env_file.resolve())])
    subprocess.run(
        [
            *command,
            "exec",
            "-T",
            "worker",
            "python",
            "/app/scripts/tamper.py",
            "--local",
            "--case",
            case_id,
            "--artifact",
            kind,
            "--mode",
            mode,
        ],
        cwd=ROOT,
        check=True,
        timeout=30,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--artifact", choices=KINDS, required=True)
    parser.add_argument("--mode", choices=MODES, default="raw")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument(
        "--local",
        action="store_true",
        help="utiliser le stockage et PostgreSQL du processus courant",
    )
    args = parser.parse_args()
    try:
        if args.local:
            database_url = os.environ.get("DATABASE_URL_WORKER")
            if not database_url:
                raise ValueError("DATABASE_URL_WORKER est requise.")
            name = tamper_case(
                CaseService(database_url),
                ArtifactStore.from_environment(),
                args.case,
                args.artifact,
                args.mode,
            )
            print(f"Artefact {args.artifact} modifié ({name}, mode {args.mode}).")
        else:
            compose_tamper(args.case, args.artifact, args.mode, args.env_file)
    except (
        CaseNotFound,
        DecryptionError,
        ValueError,
        OSError,
        psycopg.Error,
        subprocess.SubprocessError,
    ):
        print(
            "Falsification impossible. Vérifier le cas, le stockage et le worker de démonstration.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
