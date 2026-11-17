"""AUD-038: list the Node/TypeScript toolchain in TRD §18 and bump to suite v2.1.4.

All-or-nothing: every replacement must match exactly once, or nothing is written.
CRLF files stay CRLF, LF files stay LF. Run from the repository root.
"""

import pathlib
import sys

S = "docs/specs/"
edits: dict[str, list[tuple[str, str]]] = {}


def E(path: str, old: str, new: str) -> None:
    edits.setdefault(path, []).append((old, new))


# --- TRD §18 and header ------------------------------------------------------
E(
    S + "02-trd.md",
    "Node : fabric-contract-api, fabric-shim, @hyperledger/fabric-gateway, @grpc/grpc-js, fastify, pino.",
    "Node : fabric-contract-api, fabric-shim, @hyperledger/fabric-gateway, @grpc/grpc-js, fastify, pino ; "
    "outillage Node : typescript, @types/node, reflect-metadata (décorateurs de fabric-contract-api), jest, eslint.",
)
E(S + "02-trd.md", "| 2.0.3 | 2026-11-09 | 2.1.3 |", "| 2.0.4 | 2026-11-09 | 2.1.4 |")

# --- Plan 08 §1 and own header ----------------------------------------------
P = S + "08-implementation-plan.md"
E(P, "| 2.1.3 | 2026-11-09 | 2.1.3 |", "| 2.1.4 | 2026-11-09 | 2.1.4 |")
E(P, "| [02-trd.md](02-trd.md) | 2.0.3 |", "| [02-trd.md](02-trd.md) | 2.0.4 |")
E(P, "| [review.md](review.md) | 2.1.3 |", "| [review.md](review.md) | 2.1.4 |")
E(P, "| [aar.md](aar.md) | 2.1.3 |", "| [aar.md](aar.md) | 2.1.4 |")

# --- Suite version in the other headers --------------------------------------
for f, old, new in [
    ("01-prd.md", "| 2.0.1 | 2026-10-23 | 2.1.3 |", "| 2.0.1 | 2026-10-23 | 2.1.4 |"),
    (
        "03-architecture.md",
        "| 1.0.2 | 2026-11-09 | 2.1.3 |",
        "| 1.0.2 | 2026-11-09 | 2.1.4 |",
    ),
    (
        "04-backend-schema.md",
        "| 2.0.3 | 2026-11-09 | 2.1.3 |",
        "| 2.0.3 | 2026-11-09 | 2.1.4 |",
    ),
    (
        "05-system-design.md",
        "| 1.0.2 | 2026-11-09 | 2.1.3 |",
        "| 1.0.2 | 2026-11-09 | 2.1.4 |",
    ),
    (
        "06-app-flow.md",
        "| 2.0.2 | 2026-11-09 | 2.1.3 |",
        "| 2.0.2 | 2026-11-09 | 2.1.4 |",
    ),
    (
        "07-design-brief.md",
        "| 2.0.1 | 2026-10-23 | 2.1.3 |",
        "| 2.0.1 | 2026-10-23 | 2.1.4 |",
    ),
    (
        "08-implementation-plan-L.md",
        "| 1.0.0 | 2026-11-09 | 2.1.3 |",
        "| 1.0.0 | 2026-11-09 | 2.1.4 |",
    ),
]:
    E(S + f, old, new)
for f in ("aar.md", "review.md", "traceability.md"):
    E(S + f, "Suite version : 2.1.3 —", "Suite version : 2.1.4 —")
E(
    S + "review.md",
    "| Même version de suite sur tous les documents | ✓ 2.1.3 |",
    "| Même version de suite sur tous les documents | ✓ 2.1.4 |",
)
E(S + "schema.sql", "suite v2.1.3, 2026-11-09", "suite v2.1.4, 2026-11-09")
E(
    "AGENTS.md",
    "Suite de specs v2.1.3 (8 documents)",
    "Suite de specs v2.1.4 (8 documents)",
)
E(
    "PROGRESS.md",
    "Suite de specs : v2.1.3 (2026-11-09)",
    "Suite de specs : v2.1.4 (2026-11-09)",
)

# --- CHANGELOG ---------------------------------------------------------------
anchor = "## Suite v2.1.3 — 2026-11-09\n"
entry = """## Suite v2.1.4 — 2026-11-09
**Change:** l'outillage Node/TypeScript est ajouté à la liste des dépendances du TRD §18 (audit de code, passe 2).  **Requested by:** utilisateur (L)  **Decision:** accord de l'utilisateur (L), 2026-11-09 ; à confirmer par B (T1.1, CI)  **From audit:** AUD-038

- TRD v2.0.4 : §18, outillage Node : `typescript`, `@types/node`, `reflect-metadata` (requis par les décorateurs de `fabric-contract-api`), `jest` et `eslint` (déjà cités par §16 et §17 pour les tests et le lint du chaincode, absents de la liste). Correctif : ces paquets découlent de la pile déjà choisie (Node 20, TypeScript, ADR-02) ; aucune bibliothèque d'exécution n'est ajoutée.
- Plan v2.1.4 : §1, version du TRD recalée. Version de suite dans les en-têtes de tous les documents, AGENTS.md, PROGRESS.md et `schema.sql` : 2.1.4. Autres documents inchangés sur le fond.

"""
E(S + "CHANGELOG.md", anchor, entry + anchor)

# --- apply -------------------------------------------------------------------
loaded: dict[str, tuple[str, bool]] = {}
for path, lst in edits.items():
    raw = pathlib.Path(path).read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    for old, new in lst:
        n = text.count(old)
        if n != 1:
            sys.exit(f"ABORT {path}: expected 1 match, found {n}: {old[:70]!r}")
        text = text.replace(old, new)
    loaded[path] = (text, crlf)

for path, (text, crlf) in loaded.items():
    data = text.replace("\n", "\r\n") if crlf else text
    pathlib.Path(path).write_bytes(data.encode("utf-8"))
print(f"updated {len(loaded)} files")
