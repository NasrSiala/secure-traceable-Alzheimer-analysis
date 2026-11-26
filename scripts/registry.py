"""Administrer les versions des seuils de validation et des modèles."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saam.audit.events import model_activated, validation_config_created  # noqa: E402
from saam.identity.auth import AuthError, IdentityService  # noqa: E402
from saam.ledger import LedgerClient, LedgerError  # noqa: E402
from saam.registry import (  # noqa: E402
    activate_config,
    activate_model,
    create_validation_config,
    list_models,
    validation_threshold,
)


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt + " ").strip().casefold() == "o"
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-email", default=os.environ.get("SEED_ADMIN_EMAIL"))
    domains = parser.add_subparsers(dest="domain", required=True)
    config = domains.add_parser("config").add_subparsers(dest="action", required=True)
    new = config.add_parser("new")
    new.add_argument("--conf-high", required=True)
    new.add_argument("--quality-min", required=True)
    new.add_argument("--lexicon", required=True)
    config.add_parser("activate").add_argument("version", type=int)
    model = domains.add_parser("model").add_subparsers(dest="action", required=True)
    model.add_parser("list")
    model_activation = model.add_parser("activate")
    model_activation.add_argument("name", metavar="nom")
    model_activation.add_argument("version")
    args = parser.parse_args(argv)

    try:
        if args.action == "new":
            conf_high = validation_threshold(args.conf_high)
            quality_min = validation_threshold(args.quality_min)
        if args.domain == "config" and args.action == "activate":
            if not 0 < args.version <= 2_147_483_647:
                raise ValueError("Numéro de version invalide.")

        if not args.admin_email:
            parser.error("L'adresse de l'administrateur est requise.")

        if args.action == "activate":
            if args.domain == "config":
                prompt = (
                    f"Les prochains cas utiliseront la version {args.version}. "
                    "Les cas existants ne changent pas. Confirmer ? [o/N]"
                )
            else:
                prompt = (
                    f"Les prochains cas utiliseront {args.name} {args.version}. "
                    "Confirmer ? [o/N]"
                )
            if not _confirm(prompt):
                return 0

        identity = IdentityService.from_environment()
        password = os.environ.get("REGISTRY_ADMIN_PASSWORD") or getpass.getpass(
            "Mot de passe admin : "
        )
        session = identity.login(args.admin_email, password, "127.0.0.1")
        identity.logout(session.refresh_token)
        actor = session.user
        if actor.role != "admin":
            raise AuthError(403, "FORBIDDEN", "Action non autorisée.")

        if args.action == "new":
            with identity.connect() as db:
                version = create_validation_config(
                    db, actor.id, conf_high, quality_min, args.lexicon
                )
                validation_config_created(db, actor.id, version)
            print(f"Version {version} créée (inactive)")
        elif args.action == "list":
            with identity.connect() as db:
                models = list_models(db)
            for row in models:
                status = "actif" if row["is_active"] else "inactif"
                print(f"{row['name']} {row['version']} {status}")
            if not models:
                print("Aucun modèle enregistré.")
        elif args.domain == "config":
            with identity.connect() as db:
                activate_config(db, args.version)
            print(f"Version {args.version} active")
        else:
            with (
                LedgerClient.from_environment("verifier") as ledger,
                identity.connect() as db,
            ):
                if activate_model(db, ledger, args.name, args.version):
                    model_activated(db, actor.id, args.name, args.version)
            print(f"{args.name} {args.version} actif")
    except psycopg.OperationalError:
        print("Base de données injoignable.", file=sys.stderr)
        return 2
    except psycopg.Error:
        print("Opération impossible dans le registre local.", file=sys.stderr)
        return 1
    except AuthError as error:
        print(error.message, file=sys.stderr)
        return 1
    except (LedgerError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Opération annulée.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
