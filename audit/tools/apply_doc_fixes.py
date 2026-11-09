"""Apply the documentation fixes of the audit (AUD-003, 012-016, 019) preserving CRLF.
Every replacement must match exactly the expected number of times, otherwise nothing is written."""

import pathlib
import sys


def load(p):
    raw = pathlib.Path(p).read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


edits = {}  # path -> list of (old, new, count)


def E(path, old, new, count=1):
    edits.setdefault(path, []).append((old, new, count))


S = "docs/specs/"
# --- TRD v2.0.2 -> 2.0.3
E(S + "02-trd.md", "| 2.0.2 | 2026-11-09 | 2.1.0 |", "| 2.0.3 | 2026-11-09 | 2.1.1 |")
E(S + "02-trd.md", "`POST /api/cases` multipart", "`POST /api/v1/cases` multipart")
E(S + "02-trd.md", "`GET /api/cases/{id}/history`", "`GET /api/v1/cases/{id}/history`")
E(
    S + "02-trd.md",
    "avec les droits admin de la base (`app_worker`)",
    "avec le rôle de base `app_api` (le seul autorisé à écrire `validation_configs`, `schema.sql`) ; `scripts/register_model.py`, qui insère dans `models`, utilise `app_worker`",
)
# --- System Design 1.0.1 -> 1.0.2
E(
    S + "05-system-design.md",
    "| 1.0.1 | 2026-10-23 | 2.1.0 |",
    "| 1.0.2 | 2026-11-09 | 2.1.1 |",
)
E(
    S + "05-system-design.md",
    "le dernier démarre après ≈ 4,5 min",
    "le dernier termine après ≈ 4,5 min (il démarre après ≈ 4 min)",
)
# --- Backend Schema 2.0.1 -> 2.0.2 (schema.sql header comment only)
E(
    S + "04-backend-schema.md",
    "| 2.0.1 | 2026-10-23 | 2.1.0 |",
    "| 2.0.2 | 2026-11-09 | 2.1.1 |",
)
E(
    S + "schema.sql",
    "(Backend Schema v2.0.1, suite v2.1.0, 2026-10-23 — DDL inchangé depuis la v1.0.0)",
    "(Backend Schema v2.0.2, suite v2.1.1, 2026-11-09 — DDL inchangé depuis la v1.0.0)",
)
E(
    S + "schema.sql",
    "docs/specs/03-backend-schema.md",
    "docs/specs/04-backend-schema.md",
)
# --- Plan 2.1.0 -> 2.1.1
P = S + "08-implementation-plan.md"
E(P, "| 2.1.0 | 2026-11-09 | 2.1.0 |", "| 2.1.1 | 2026-11-09 | 2.1.1 |")
E(P, "| [02-trd.md](02-trd.md) | 2.0.1 |", "| [02-trd.md](02-trd.md) | 2.0.3 |")
E(
    P,
    "| [04-backend-schema.md](04-backend-schema.md) + [schema.sql](schema.sql) | 2.0.1 |",
    "| [04-backend-schema.md](04-backend-schema.md) + [schema.sql](schema.sql) | 2.0.2 |",
)
E(
    P,
    "| [05-system-design.md](05-system-design.md) | 1.0.1 |",
    "| [05-system-design.md](05-system-design.md) | 1.0.2 |",
)
E(
    P,
    "| [06-app-flow.md](06-app-flow.md) | 2.0.1 |",
    "| [06-app-flow.md](06-app-flow.md) | 2.0.2 |",
)
E(P, "| [review.md](review.md) | 2.1.0 |", "| [review.md](review.md) | 2.1.1 |")
E(P, "| [aar.md](aar.md) | 2.1.0 |", "| [aar.md](aar.md) | 2.1.1 |")
E(
    P,
    "| TRD §3, §6.6 (Intégration Zynq), ADR-13, D-12 |",
    "| TRD §3, Architecture §5.6 (Intégration Zynq), ADR-13, D-12 |",
)
E(
    P,
    "| US-04 | T3.8a, T3.8b, T3.9, T3.10, T3.16a, T4.7 |",
    "| US-04 | T2.5b, T3.8a, T3.8b, T3.9, T3.10, T3.16a, T4.7 |",
)
# --- traceability
T = S + "traceability.md"
E(T, "Suite version : 2.1.0 —", "Suite version : 2.1.1 —")
E(
    T,
    "| T3.8a, T3.8b, T3.9, T3.10, T3.16a, T4.7 | ready |",
    "| T2.5b, T3.8a, T3.8b, T3.9, T3.10, T3.16a, T4.7 | ready |",
)
E(T, "| C-ecg-viewer (sans saillance) |", "| C-ecg-viewer (sans saillance), T3.16b |")
E(
    T,
    "| FM-18, FM-19, FM-20 | Pannes sans écran applicatif (navigateur, PhysioNet, audit) : comportement documenté, pas de tâche dédiée |\n",
    "| FM-18, FM-19, FM-20 | Pannes sans écran applicatif (navigateur, PhysioNet, audit) : comportement documenté, pas de tâche dédiée |\n"
    "| T2.1, T2.2 | Migration initiale et seed : socle des entités, préalable à tout cas (Schema §18) |\n"
    "| S-02, T3.13, T3.14 | Liste et lecture des cas : écran d'entrée de la navigation (App Flow §5) ; le TRD §8.1 rattache `GET /cases` à US-09 |\n"
    "| T5.2 | Tests E2E des parcours J-01, J-02 et J-04 (Plan T5.2) |\n"
    "| T5.5 | Revue de sécurité : OWASP, secrets, privilèges (TRD §12, NFR-03, NFR-05) |\n"
    "| T5.6 | Tests d'utilisabilité à 2 testeurs (Design Brief §1 et §23, D-17) |\n"
    "| T6.1, T6.2, T6.4 | Livraison : machine de démo hors ligne, rapport final, tag `v1.0.0` (CDC §12, PRD §16 et §17, D-13) |\n",
)
# --- suite version string elsewhere
E(
    "AGENTS.md",
    "Suite de specs v2.1.0 (8 documents)",
    "Suite de specs v2.1.1 (8 documents)",
)
E(
    "PROGRESS.md",
    "Suite de specs : v2.1.0 (2026-11-09)",
    "Suite de specs : v2.1.1 (2026-11-09)",
)
for f, old in [
    ("01-prd.md", "| 2.0.1 | 2026-10-23 | 2.1.0 |"),
    ("03-architecture.md", "| 1.0.1 | 2026-10-23 | 2.1.0 |"),
    ("06-app-flow.md", "| 2.0.2 | 2026-11-09 | 2.1.0 |"),
    ("07-design-brief.md", "| 2.0.1 | 2026-10-23 | 2.1.0 |"),
    ("08-implementation-plan-L.md", "| 1.0.0 | 2026-11-09 | 2.1.0 |"),
]:
    E(S + f, old, old[:-6] + "2.1.1 |")
E(S + "aar.md", "Suite version : 2.1.0 —", "Suite version : 2.1.1 —")
E(S + "review.md", "Suite version : 2.1.0 —", "Suite version : 2.1.1 —")
E(
    S + "review.md",
    "| Même version de suite sur tous les documents | ✓ 2.1.0 |",
    "| Même version de suite sur tous les documents | ✓ 2.1.1 |",
)

# dry run: verify all matches first
loaded = {}
for path, lst in edits.items():
    text, crlf = load(path)
    for old, new, count in lst:
        n = text.count(old)
        if n != count:
            sys.exit(
                f"ABORT {path}: expected {count} match(es), found {n} for: {old[:70]!r}"
            )
        text = text.replace(old, new)
    loaded[path] = (text, crlf)
for path, (text, crlf) in loaded.items():
    pathlib.Path(path).write_bytes(
        (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
    )
print(
    "applied",
    sum(len(v) for v in edits.values()),
    "replacements in",
    len(edits),
    "files",
)
