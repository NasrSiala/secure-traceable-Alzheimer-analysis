"""Sauvegarde froide et restauration de la pile locale."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saam.hashing import file_hash  # noqa: E402
from saam.hashing.canonical import file_stream_hash  # noqa: E402

VOLUME_IMAGE = "postgres:16.15-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab"
STACK_VOLUMES = ("artifact-store", "uploads")
FABRIC_VOLUMES = ("orderer-ledger", "peer0-org1-ledger", "peer0-org2-ledger")
RUNTIME = ("organizations", "channel-artifacts", ".runtime", "wallet")
DATABASE_DUMP = "postgres.dump"
RUNTIME_ARCHIVE = "fabric-runtime.tar.gz"
ARCHIVES = {
    *(f"{key}.tar.gz" for key in STACK_VOLUMES + FABRIC_VOLUMES),
    DATABASE_DUMP,
    RUNTIME_ARCHIVE,
}
MUTATING_STACK_SERVICES = ("api", "worker", "frontend", "ledger-gateway")
CLIENTS = """SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()
            AND pid <> pg_backend_pid() AND backend_type = 'client backend'"""
EMPTY_DATABASE = """SELECT NOT EXISTS (
    SELECT FROM pg_namespace WHERE nspname NOT IN ('public', 'information_schema')
    AND nspname NOT LIKE 'pg_%'
) AND NOT EXISTS (
    SELECT FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
    WHERE n.nspname='public'
) AND NOT EXISTS (
    SELECT FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid
    WHERE n.nspname='public'
)"""


def docker(args: list[str], *, capture: bool = False, **streams: Any) -> str:
    result = subprocess.run(
        ["docker", *args],
        check=True,
        timeout=240,
        stdout=subprocess.PIPE if capture else streams.pop("stdout", None),
        stderr=subprocess.PIPE,
        **streams,
    )
    return result.stdout.decode("utf-8").strip() if capture else ""


def one(args: list[str], description: str) -> str:
    matches = docker(args, capture=True).splitlines()
    if len(matches) != 1:
        raise ValueError(f"Une seule ressource Docker est attendue pour {description}.")
    return matches[0]


def project_filter(project: str) -> str:
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project) is None:
        raise ValueError("Nom de projet Compose invalide.")
    return f"label=com.docker.compose.project={project}"


@dataclass(frozen=True)
class Services:
    stack: str
    fabric: str
    postgres: str
    user: str
    database: str
    volumes: dict[str, str]

    def database_command(self, *command: str) -> list[str]:
        return [
            "exec",
            "-i",
            self.postgres,
            *command,
            "-U",
            self.user,
            "-d",
            self.database,
        ]

    def query(self, sql: str) -> str:
        return docker(
            self.database_command("psql", "-XAt", "-v", "ON_ERROR_STOP=1")
            + ["-c", sql],
            capture=True,
        )

    def check_cold(self) -> None:
        for service in MUTATING_STACK_SERVICES:
            if docker(
                [
                    "ps",
                    "-q",
                    "--filter",
                    project_filter(self.stack),
                    "--filter",
                    f"label=com.docker.compose.service={service}",
                ],
                capture=True,
            ):
                raise ValueError(f"Arrêter le service {service} avant l'opération.")
        if docker(["ps", "-q", "--filter", project_filter(self.fabric)], capture=True):
            raise ValueError(
                "Arrêter le réseau Fabric avec Docker Compose avant l'opération."
            )
        for volume in self.volumes.values():
            if docker(["ps", "-q", "--filter", f"volume={volume}"], capture=True):
                raise ValueError(
                    f"Le volume {volume} est toujours monté par un conteneur actif."
                )
        if self.query(CLIENTS) != "0":
            raise ValueError(
                "Fermer les autres connexions PostgreSQL avant l'opération."
            )


def discover(stack: str, fabric: str) -> Services:
    if stack == fabric:
        raise ValueError("Les deux projets Compose doivent être distincts.")
    postgres = one(
        [
            "ps",
            "-q",
            "--filter",
            project_filter(stack),
            "--filter",
            "label=com.docker.compose.service=postgres",
        ],
        "PostgreSQL démarré",
    )
    settings = {}
    # Ne lire que les deux paramètres publics, sans collecter les autres variables.
    for key in ("POSTGRES_USER", "POSTGRES_DB"):
        settings[key] = docker(["exec", postgres, "printenv", key], capture=True)
        if not settings[key]:
            raise ValueError("Utilisateur ou base PostgreSQL non configuré.")
    volumes = {
        key: one(
            [
                "volume",
                "ls",
                "-q",
                "--filter",
                project_filter(project),
                "--filter",
                f"label=com.docker.compose.volume={key}",
            ],
            key,
        )
        for project, keys in ((stack, STACK_VOLUMES), (fabric, FABRIC_VOLUMES))
        for key in keys
    }
    return Services(
        stack,
        fabric,
        postgres,
        settings["POSTGRES_USER"],
        settings["POSTGRES_DB"],
        volumes,
    )


def volume_command(
    volume: str, tool: str, *args: str, readonly: bool = True
) -> list[str]:
    mount = f"type=volume,source={volume},target=/snapshot,volume-nocopy"
    if readonly:
        mount += ",readonly"
    return [
        "run",
        "--rm",
        "-i",
        "--pull=never",
        "--network",
        "none",
        "--user",
        "0:0",
        "--mount",
        mount,
        "--entrypoint",
        tool,
        VOLUME_IMAGE,
        *args,
    ]


def key_fingerprint(path: Path) -> str:
    key = path.read_text(encoding="ascii").strip()
    if re.fullmatch("[0-9a-fA-F]{64}", key) is None:
        raise ValueError(
            "La clé AES de la pile doit contenir 64 chiffres hexadécimaux."
        )
    return file_hash(bytes.fromhex(key))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return file_stream_hash(stream)


def validate_archive(archive: tarfile.TarFile, runtime: bool = False) -> None:
    roots = set()
    for item in archive:
        path = PurePosixPath(item.name)
        parts = path.parts
        if (
            path.is_absolute()
            or ".." in parts
            or "\\" in item.name
            or ":" in item.name
            or not (item.isfile() or item.isdir())
        ):
            raise ValueError("Contenu d'archive invalide.")
        if runtime:
            if not parts or parts[0] not in RUNTIME:
                raise ValueError("Arborescence Fabric invalide.")
            roots.add(parts[0])
    if runtime and roots != set(RUNTIME):
        raise ValueError("La configuration Fabric est incomplète.")


def backup(output: Path, fabric_root: Path, key_file: Path, services: Services) -> None:
    services.check_cold()
    key_id = key_fingerprint(key_file)
    if any(not (fabric_root / name).is_dir() for name in RUNTIME):
        raise ValueError(
            "Les fichiers d'identité et de configuration de Fabric sont incomplets."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    with (output / DATABASE_DUMP).open("wb") as stream:
        docker(
            services.database_command("pg_dump", "--format=custom", "--no-owner"),
            stdout=stream,
        )
    for key, volume in services.volumes.items():
        with (output / f"{key}.tar.gz").open("wb") as stream:
            docker(
                volume_command(volume, "tar", "-czf", "-", "-C", "/snapshot", "."),
                stdout=stream,
            )
    runtime = output / RUNTIME_ARCHIVE
    with tarfile.open(runtime, "w:gz") as archive:
        for name in RUNTIME:
            archive.add(fabric_root / name, arcname=name)
    with tarfile.open(runtime, "r:gz") as archive:
        validate_archive(archive, runtime=True)
    services.check_cold()
    manifest = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_key_sha256": key_id,
        "files": {name: digest(output / name) for name in sorted(ARCHIVES)},
    }
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)


def check_snapshot(source: Path, key_file: Path) -> None:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("Version de sauvegarde non reconnue.")
    if manifest.get("artifact_key_sha256") != key_fingerprint(key_file):
        raise ValueError("La clé des artefacts ne correspond pas à la sauvegarde.")
    checks = manifest.get("files")
    if not isinstance(checks, dict) or checks.keys() != ARCHIVES:
        raise ValueError("La sauvegarde est incomplète.")
    for name in ARCHIVES:
        path = source / name
        if not path.is_file() or path.is_symlink() or digest(path) != checks[name]:
            raise ValueError(f"Archive manquante ou altérée ({name}).")
        if name != DATABASE_DUMP:
            with tarfile.open(path, "r:gz") as archive:
                validate_archive(archive, runtime=name == RUNTIME_ARCHIVE)


def check_runtime(source: Path, fabric_root: Path) -> bool:
    if not any((fabric_root / name).exists() for name in RUNTIME):
        return True
    # Sur le même hôte, conserver la configuration déjà en place si les octets concordent.
    with tarfile.open(source / RUNTIME_ARCHIVE, "r:gz") as archive:
        for item in archive:
            target = fabric_root.joinpath(*PurePosixPath(item.name).parts)
            if target.resolve() != target.absolute() or (
                item.isdir() and not target.is_dir()
            ):
                raise ValueError(
                    "La destination Fabric contient une configuration différente."
                )
            if item.isfile():
                saved = archive.extractfile(item)
                if saved is None or not target.is_file():
                    raise ValueError(
                        "La destination Fabric contient une configuration différente."
                    )
                with saved:
                    if digest(target) != file_stream_hash(saved):
                        raise ValueError(
                            "La destination Fabric contient une configuration différente."
                        )
    return False


def restore(
    source: Path, fabric_root: Path, key_file: Path, services: Services
) -> None:
    check_snapshot(source, key_file)
    services.check_cold()
    extract_runtime = check_runtime(source, fabric_root)
    if services.query(EMPTY_DATABASE) != "t":
        raise ValueError("La base de restauration doit être vide.")
    for volume in services.volumes.values():
        if docker(volume_command(volume, "ls", "-A", "/snapshot"), capture=True):
            raise ValueError(f"Le volume de restauration {volume} doit être vide.")
    with (source / DATABASE_DUMP).open("rb") as stream:
        docker(
            ["exec", "-i", services.postgres, "pg_restore", "--list"],
            stdin=stream,
            stdout=subprocess.DEVNULL,
        )
    for key, volume in services.volumes.items():
        with (source / f"{key}.tar.gz").open("rb") as stream:
            docker(
                volume_command(
                    volume, "tar", "-xzpf", "-", "-C", "/snapshot", readonly=False
                ),
                stdin=stream,
            )
    if extract_runtime:
        fabric_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tarfile.open(source / RUNTIME_ARCHIVE, "r:gz") as archive:
            archive.extractall(fabric_root, filter="data")
    services.check_cold()
    with (source / DATABASE_DUMP).open("rb") as stream:
        docker(
            services.database_command(
                "pg_restore", "--no-owner", "--exit-on-error", "--single-transaction"
            ),
            stdin=stream,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("directory", type=Path, nargs="?")
    parser.add_argument("--stack-project", default="saam-stack")
    parser.add_argument("--fabric-project", default="saam-medtrace")
    parser.add_argument("--fabric-root", type=Path, default=ROOT / "fabric")
    parser.add_argument(
        "--key-file", type=Path, default=ROOT / "secrets/artifact-key.hex"
    )
    args = parser.parse_args()
    if args.operation == "restore" and args.directory is None:
        parser.error("Le dossier de sauvegarde est requis pour la restauration.")
    start = monotonic()
    try:
        services = discover(args.stack_project, args.fabric_project)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        directory = (args.directory or ROOT / "backups" / stamp).resolve()
        if args.operation == "backup":
            backup(directory, args.fabric_root.resolve(), args.key_file, services)
            print(f"Sauvegarde créée : {directory}")
        else:
            restore(directory, args.fabric_root.resolve(), args.key_file, services)
            print(
                f"Données restaurées en {monotonic() - start:.1f} s. Démarrer la pile restaurée avec Docker Compose."
            )
    except (subprocess.SubprocessError, OSError, tarfile.TarError):
        print(
            "Cette opération a échoué. Vérifier Docker, PostgreSQL et les fichiers de sauvegarde.",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
