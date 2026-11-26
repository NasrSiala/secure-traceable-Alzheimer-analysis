"""Seed dev/démo idempotent : comptes et config ; mots de passe depuis .env."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saam.identity.seed import SeedAccount, seed_accounts  # noqa: E402
from saam.registry.management import CONFIG_LOCK  # noqa: E402
from saam.registry.seed import seed_configuration  # noqa: E402


def seed(values: dict[str, str]) -> None:
    accounts = [
        SeedAccount(
            values.get(f"SEED_{role.upper()}_EMAIL", "").strip().lower(),
            values.get(f"SEED_{role.upper()}_PASSWORD", ""),
            role,
            name,
        )
        for role, name in (
            ("admin", "Administrateur démo"),
            ("operator", "Opérateur démo"),
            ("auditor", "Auditeur démo"),
        )
    ]
    url = values.get("DATABASE_URL_API", "")
    if not url:
        raise ValueError("DATABASE_URL_API est requise.")
    with psycopg.connect(url, connect_timeout=3) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (CONFIG_LOCK,))
        admin_id = seed_accounts(connection, accounts)
        seed_configuration(connection, admin_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    values = {}
    if args.env_file.is_file():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip().strip('"').strip("'")
    values.update(os.environ)
    try:
        seed(values)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except psycopg.Error:
        print(
            "Initialisation impossible ; vérifier la migration et la connexion.",
            file=sys.stderr,
        )
        return 1
    print("Initialisation terminée : 3 comptes et configuration v1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
