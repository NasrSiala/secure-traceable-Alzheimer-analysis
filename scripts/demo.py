"""Créer un cas PTB-XL et constater l'effet d'une falsification sur un seul artefact."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.tamper import KINDS, MODES, compose_tamper  # noqa: E402


def read_environment(path: Path) -> dict[str, str]:
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() and not name.lstrip().startswith("#"):
                values[name.strip()] = value.strip().strip('"').strip("'")
    return values | dict(os.environ)


def record_pair(root: Path, record: str) -> tuple[Path, Path]:
    if re.fullmatch(r"[0-9]{5}", record) is None or int(record) < 1:
        raise ValueError("Identifiant PTB-XL attendu sur cinq chiffres (ex. 00001).")
    group = f"{int(record) // 1000 * 1000:05d}"
    stem = root / "records500" / group / f"{record}_hr"
    paths = stem.with_suffix(".hea"), stem.with_suffix(".dat")
    if not all(path.is_file() for path in paths):
        raise ValueError(
            "Fichiers PTB-XL introuvables. Renseigner PTBXL_ROOT ou --data-dir."
        )
    return paths


def _object(response: httpx.Response, status: int) -> dict[str, Any]:
    if response.status_code != status:
        raise ValueError(
            f"Étape de démonstration refusée par l'API (HTTP {response.status_code})."
        )
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Réponse inattendue de l'API.")
    return body


def _authenticate(
    client: httpx.Client, values: Mapping[str, str], role: str
) -> dict[str, str]:
    prefix = f"SEED_{role.upper()}_"
    email, password = values.get(prefix + "EMAIL"), values.get(prefix + "PASSWORD")
    if not email or not password:
        raise ValueError(
            f"Configurer les identifiants de démonstration du rôle {role}."
        )
    login = _object(
        client.post("/api/v1/auth/login", json={"email": email, "password": password}),
        200,
    )
    token = login.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("Jeton de démonstration non reçu.")
    return {"Authorization": f"Bearer {token}"}


def _verify(
    client: httpx.Client, path: str, authorization: dict[str, str], changed: str | None
) -> dict[str, Any]:
    result = _object(client.post(f"{path}/verifications", headers=authorization), 201)
    if not result.get("ledger_reachable"):
        raise ValueError("Registre blockchain injoignable pendant la démonstration.")
    statuses = {item["artifact_type"]: item["status"] for item in result["items"]}
    expected = {kind: "modifie" if kind == changed else "valide" for kind in KINDS}
    if len(result["items"]) != len(KINDS) or statuses != expected:
        raise ValueError(
            "Les verdicts d'intégrité ne correspondent pas au scénario attendu."
        )
    return result


def run_demo(
    client: httpx.Client,
    pair: tuple[Path, Path],
    values: Mapping[str, str],
    tamper: Callable[[str, str, str], None],
    *,
    kind: str,
    mode: str,
    timeout: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    operator = _authenticate(client, values, "operator")
    auditor = _authenticate(client, values, "auditor")
    header, signal = pair
    with header.open("rb") as hea, signal.open("rb") as dat:
        new_case = _object(
            client.post(
                "/api/v1/cases",
                headers=operator,
                files=[
                    ("ecg_files[]", (header.name, hea, "text/plain")),
                    ("ecg_files[]", (signal.name, dat, "application/octet-stream")),
                ],
            ),
            202,
        )
    case_id = str(UUID(new_case["id"]))
    path = f"/api/v1/cases/{case_id}"
    deadline = time.monotonic() + timeout
    while True:
        detail = _object(client.get(path, headers=operator), 200)
        status = detail.get("status")
        if status == "termine" and detail.get("final_result") is not None:
            break
        if status not in {"en_attente", "en_cours"}:
            raise ValueError("Le pipeline n'a pas produit de résultat final.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Délai dépassé en attendant la fin du pipeline.")
        sleep(min(2, remaining))
    _verify(client, path, auditor, None)
    tamper(case_id, kind, mode)
    result = _verify(client, path, auditor, kind)
    return {
        "case_ref": f"CASE-{case_id}",
        "decision": detail.get("decision"),
        "simulation": detail["final_result"].get("simulation", False),
        "artifact": kind,
        "count_valide": result["count_valide"],
        "count_modifie": result["count_modifie"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", default="00001")
    parser.add_argument("--tamper", choices=KINDS, default="prediction")
    parser.add_argument("--mode", choices=MODES, default="raw")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--ca-file", type=Path)
    args = parser.parse_args()
    try:
        values = read_environment(args.env_file)
        dataset = args.data_dir or Path(
            values.get("PTBXL_ROOT") or ROOT / "ml/data/ptb-xl/1.0.3"
        )
        base_url = (
            args.base_url or f"https://localhost:{values.get('HTTPS_PORT') or '443'}"
        )
        url = httpx.URL(base_url)
        if (
            url.scheme != "https"
            or not url.host
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Une URL HTTPS de l'API, sans identifiant, est requise.")
        certificate = args.ca_file or ROOT / "secrets/localhost.crt"
        tls = ssl.create_default_context(
            cafile=str(certificate) if certificate.is_file() or args.ca_file else None
        )
        with httpx.Client(
            base_url=url, verify=tls, timeout=35, trust_env=False
        ) as client:
            result = run_demo(
                client,
                record_pair(dataset, args.record),
                values,
                lambda case, kind, mode: compose_tamper(
                    case, kind, mode, args.env_file
                ),
                kind=args.tamper,
                mode=args.mode,
            )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (
        OSError,
        httpx.HTTPError,
        httpx.InvalidURL,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
    ):
        print(
            "Démonstration interrompue. Vérifier la pile, le certificat et les données publiques PTB-XL.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
