"""Préparer la configuration locale et TLS sans remplacer les secrets existants."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

IDENTITIES = {
    **{
        f"AGENT_TOKEN_{name.upper()}": f"agent-{name}"
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
    "AGENT_TOKEN_VERIFIER": "verifier",
    "AGENT_TOKEN_MODEL_ADMIN": "model-admin",
}


def write_new(path: Path, content: str | bytes) -> None:
    """Échouer si un fichier existe déjà, même après un autre processus."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)


def read_environment(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def prepare_environment(root: Path) -> dict[str, str]:
    target = root / ".env"
    if not target.exists():
        database = "saamstiahf"
        generated = {
            "JWT_SECRET": secrets.token_hex(32),
            "POSTGRES_PASSWORD": secrets.token_hex(32),
            "APP_API_PASSWORD": secrets.token_hex(32),
            "APP_WORKER_PASSWORD": secrets.token_hex(32),
            "AGENT_TOKEN_FILE": "./secrets/agent-tokens.json",
            **{name: secrets.token_hex(32) for name in IDENTITIES},
        }
        for role in ("API", "WORKER"):
            generated[f"DATABASE_URL_{role}"] = (
                f"postgresql://app_{role.lower()}:{generated[f'APP_{role}_PASSWORD']}"
                f"@postgres:5432/{database}"
            )
        template = (root / ".env.example").read_text(encoding="utf-8")
        lines = []
        for line in template.splitlines():
            name = line.split("=", 1)[0]
            lines.append(f"{name}={generated.pop(name)}" if name in generated else line)
        lines.extend(f"{name}={value}" for name, value in generated.items())
        write_new(target, "\n".join(lines) + "\n")
    values = read_environment(target)
    required = (
        "POSTGRES_PASSWORD",
        "APP_API_PASSWORD",
        "APP_WORKER_PASSWORD",
        "DATABASE_URL_API",
        "DATABASE_URL_WORKER",
        *IDENTITIES,
    )
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ValueError("Variables à renseigner dans .env : " + ", ".join(missing))
    return values


def find_openssl() -> str:
    found = shutil.which("openssl")
    if found:
        return found
    git_openssl = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
    if git_openssl.is_file():
        return str(git_openssl)
    raise RuntimeError("OpenSSL est requis pour créer le certificat TLS local")


def prepare_tls(directory: Path) -> None:
    certificate = directory / "localhost.crt"
    private_key = directory / "localhost.key"
    if certificate.exists() and private_key.exists():
        return
    if certificate.exists() or private_key.exists():
        raise ValueError(
            "Paire TLS incomplète ; compléter les fichiers sans les écraser"
        )
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        staging = Path(temporary)
        result = subprocess.run(
            [
                find_openssl(),
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-sha256",
                "-days",
                "30",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-keyout",
                str(staging / "localhost.key"),
                "-out",
                str(staging / "localhost.crt"),
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("La génération du certificat TLS a échoué")
        write_new(private_key, (staging / "localhost.key").read_bytes())
        write_new(certificate, (staging / "localhost.crt").read_bytes())


def prepare(root: Path) -> None:
    values = prepare_environment(root)
    directory = root / "secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    tokens = directory / "agent-tokens.json"
    expected = {identity: values[name] for name, identity in IDENTITIES.items()}
    if tokens.exists():
        if json.loads(tokens.read_text(encoding="utf-8")) != expected:
            raise ValueError(
                "Les jetons de .env et secrets/agent-tokens.json diffèrent"
            )
    else:
        write_new(tokens, json.dumps(expected, indent=2) + "\n")
    prepare_tls(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        prepare(Path(__file__).resolve().parents[1])
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    print("Configuration locale et certificat TLS prêts ; aucun secret affiché.")


if __name__ == "__main__":
    main()
