"""AUD-011: complete the gateway error table (IF-07 / IF-09) and bump to suite v2.1.3.
All-or-nothing; each replacement must match exactly once; CRLF preserved; explicit new strings (no slicing)."""

import pathlib
import sys

edits = {}


def E(path, old, new):
    edits.setdefault(path, []).append((old, new))


S = "docs/specs/"
A = S + "03-architecture.md"
E(
    A,
    "| `saam/ledger/__init__.py` | Interne | `LedgerUnavailable`, `DuplicateRecord`, `RecordNotFound` | sync |",
    "| `saam/ledger/__init__.py` | Interne | `LedgerUnavailable` (502), `DuplicateRecord` (409), `RecordNotFound` (404), `InvalidRecord` (400, 422), `LedgerForbidden` (401, 403) | sync |",
)
E(
    A,
    "| TRD §8.2 | Préfixe `/ledger` | 401 jeton, 409 doublon, 404 absent, 502 Fabric | sync |",
    "| TRD §8.2 | Préfixe `/ledger` | Corps d'erreur TRD §8, `code` = code du chaincode. 401 jeton inconnu ou absent ; 403 `FORBIDDEN` ; 404 absent ; 409 `DUPLICATE` ; 400 `SCHEMA` ; 422 `PARENT_MISSING` ; 502 Fabric injoignable | sync |",
)
E(A, "| 1.0.1 | 2026-10-23 | 2.1.2 |", "| 1.0.2 | 2026-11-09 | 2.1.3 |")
E(
    S + "08-implementation-plan.md",
    "| 2.1.2 | 2026-11-09 | 2.1.2 |",
    "| 2.1.3 | 2026-11-09 | 2.1.3 |",
)
E(
    S + "08-implementation-plan.md",
    "| [03-architecture.md](03-architecture.md) | 1.0.1 |",
    "| [03-architecture.md](03-architecture.md) | 1.0.2 |",
)
E(
    S + "08-implementation-plan.md",
    "| [review.md](review.md) | 2.1.2 |",
    "| [review.md](review.md) | 2.1.3 |",
)
E(
    S + "08-implementation-plan.md",
    "| [aar.md](aar.md) | 2.1.2 |",
    "| [aar.md](aar.md) | 2.1.3 |",
)
E(
    "AGENTS.md",
    "Suite de specs v2.1.2 (8 documents)",
    "Suite de specs v2.1.3 (8 documents)",
)
E(
    "PROGRESS.md",
    "Suite de specs : v2.1.2 (2026-11-09)",
    "Suite de specs : v2.1.3 (2026-11-09)",
)
for f, old, new in [
    ("01-prd.md", "| 2.0.1 | 2026-10-23 | 2.1.2 |", "| 2.0.1 | 2026-10-23 | 2.1.3 |"),
    ("02-trd.md", "| 2.0.3 | 2026-11-09 | 2.1.2 |", "| 2.0.3 | 2026-11-09 | 2.1.3 |"),
    (
        "04-backend-schema.md",
        "| 2.0.3 | 2026-11-09 | 2.1.2 |",
        "| 2.0.3 | 2026-11-09 | 2.1.3 |",
    ),
    (
        "05-system-design.md",
        "| 1.0.2 | 2026-11-09 | 2.1.2 |",
        "| 1.0.2 | 2026-11-09 | 2.1.3 |",
    ),
    (
        "06-app-flow.md",
        "| 2.0.2 | 2026-11-09 | 2.1.2 |",
        "| 2.0.2 | 2026-11-09 | 2.1.3 |",
    ),
    (
        "07-design-brief.md",
        "| 2.0.1 | 2026-10-23 | 2.1.2 |",
        "| 2.0.1 | 2026-10-23 | 2.1.3 |",
    ),
    (
        "08-implementation-plan-L.md",
        "| 1.0.0 | 2026-11-09 | 2.1.2 |",
        "| 1.0.0 | 2026-11-09 | 2.1.3 |",
    ),
]:
    E(S + f, old, new)
for f in ("aar.md", "review.md", "traceability.md"):
    E(S + f, "Suite version : 2.1.2 —", "Suite version : 2.1.3 —")
E(
    S + "review.md",
    "| Même version de suite sur tous les documents | ✓ 2.1.2 |",
    "| Même version de suite sur tous les documents | ✓ 2.1.3 |",
)
E(S + "schema.sql", "suite v2.1.2, 2026-11-09", "suite v2.1.3, 2026-11-09")
anchor = "## Suite v2.1.2 — 2026-11-09\n"
entry = """## Suite v2.1.3 — 2026-11-09
**Change:** table complète des erreurs de la passerelle ledger (IF-09) et du client (IF-07), issue de l'audit de code (AUD-011).  **Requested by:** utilisateur  **Decision:** accord de l'utilisateur (L), 2026-11-09 ; à confirmer par B (T2.7, `LedgerClient`)  **From audit:** AUD-011

- Architecture v1.0.2 : IF-09, `code` = code du chaincode ; 401 jeton, 403 `FORBIDDEN`, 404 absent, 409 `DUPLICATE`, 400 `SCHEMA`, 422 `PARENT_MISSING`, 502 Fabric injoignable. IF-07, exceptions ajoutées avec leur statut : `InvalidRecord` (400, 422), `LedgerForbidden` (401, 403) en plus de `LedgerUnavailable` (502), `DuplicateRecord` (409), `RecordNotFound` (404). Correctif : le 403 était déjà prévu par le plan de L (l08) ; aucun code n'est implémenté.
- Plan v2.1.3 : §1, versions recalées. Version de suite dans les en-têtes de tous les documents, AGENTS.md, PROGRESS.md et `schema.sql` : 2.1.3. Autres documents inchangés sur le fond.
- Pour l05, l06, l08 (passerelle, chaincode) et T2.7 : utiliser cette table.

"""
E(S + "CHANGELOG.md", anchor, entry + anchor)

loaded = {}
for path, lst in edits.items():
    raw = pathlib.Path(path).read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    for old, new in lst:
        n = text.count(old)
        if n != 1:
            sys.exit(f"ABORT {path}: expected 1, found {n}: {old[:70]!r}")
        text = text.replace(old, new)
    loaded[path] = (text, crlf)
text, crlf = loaded["PROGRESS.md"]
i = text.index("| 2026-11-09 | Table complète des codes d'erreur de la passerelle")
text = text[:i] + text[text.index("\n", i) + 1 :]
k = text.index("\n## Problèmes\n")
row = "| 2026-11-09 | Table des erreurs de la passerelle (IF-09/IF-07) : 401 jeton, 403 `FORBIDDEN`, 404, 409 `DUPLICATE`, 400 `SCHEMA`, 422 `PARENT_MISSING`, 502 Fabric | Constat AUD-011 ; décidé par L (Nasr Siala) | Oui : Architecture §7, CHANGELOG v2.1.3. À confirmer par B avant T2.7 |\n"
text = text[:k].rstrip("\n") + "\n" + row + text[k:]
loaded["PROGRESS.md"] = (text, crlf)
for path, (text, crlf) in loaded.items():
    pathlib.Path(path).write_bytes(
        (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
    )
print("applied to", len(loaded), "files")
